# webhook_fastapi.py
import os, time, requests, shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from cache_manager import cleanup_cache, save_summary, get_summary
from create_bot import req_bot
from summarizer import run_summary

# --- timezone ---
IST = ZoneInfo("Asia/Kolkata")

load_dotenv()
REGION  = os.getenv("RECALLAI_REGION", "us-west-2")
API_KEY = os.getenv("RECALLAI_API_KEY", "")
SECRET  = os.getenv("WEBHOOK_TOKEN", "")

BASE = f"https://{REGION}.recall.ai/api/v1"
HEAD = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}

ROOT          = Path.cwd()
PROJECTS_ROOT = ROOT / "transcripts_projects"
PROJECTS_ROOT.mkdir(exist_ok=True)

# Polling parameters
MAX_WAIT_SEC   = 300
POLL_START_SEC = 2
POLL_MAX_SEC   = 15

# Auto-delete cutoff
RETENTION_DAYS = 15

# ---------- helpers ----------
def ts_strings() -> tuple[str, str]:
    now = datetime.now(IST)
    return now.strftime("%d/%m/%Y at %H:%M"), now.strftime("%d-%m-%Y at %H.%M")

def normalize_segments(tj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(tj, dict):
        for k in ("segments", "results", "utterances", "data"):
            v = tj.get(k)
            if isinstance(v, list):
                for seg in v:
                    out.append(_map_segment(seg))
                return out
    if isinstance(tj, list):
        for entry in tj:
            participant = entry.get("participant") or {}
            name = participant.get("name") or participant.get("id") or "Unknown"
            for w in entry.get("words", []):
                out.append({
                    "speaker": name,
                    "start": w.get("start_timestamp", {}).get("absolute"),
                    "end": w.get("end_timestamp", {}).get("absolute"),
                    "text": w.get("text", "")
                })
        return out
    return out

def _map_segment(seg: Dict[str, Any]) -> Dict[str, Any]:
    p = seg.get("participant") or seg.get("speaker") or {}
    if isinstance(p, dict):
        name = p.get("name") or p.get("display_name") or p.get("id")
    else:
        name = str(p)
    return {
        "speaker": name or "Unknown",
        "start": seg.get("start"),
        "end": seg.get("end"),
        "text": seg.get("text") or seg.get("utterance") or ""
    }

def as_plaintext(segments: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"{s.get('speaker','Unknown')}: {(s.get('text') or '').strip()}"
        for s in segments if (s.get('text') or '').strip()
    )

def get_bot_media_shortcuts(bot_id: str) -> Dict[str, Any]:
    if not (API_KEY and bot_id): return {}
    r = requests.get(f"{BASE}/bot/{bot_id}/", headers=HEAD, timeout=30)
    r.raise_for_status()
    info = r.json()
    return (info.get("recordings") or {}).get("media_shortcuts") or {}

def get_transcript_url_by_id(transcript_id: str) -> Optional[str]:
    if not (API_KEY and transcript_id): return None
    r = requests.get(f"{BASE}/transcript/{transcript_id}/", headers=HEAD, timeout=30)
    r.raise_for_status()
    obj = r.json() or {}
    data = obj.get("data") if isinstance(obj, dict) else None
    if isinstance(data, dict) and "download_url" in data:
        return data["download_url"]
    return obj.get("download_url")

def find_transcript_url(bot_id: Optional[str], transcript_id: Optional[str]) -> Optional[str]:
    if transcript_id:
        url = get_transcript_url_by_id(transcript_id)
        if url: return url
    if bot_id:
        media = get_bot_media_shortcuts(bot_id)
        t = (media.get("transcript") or {}).get("data", {})
        if t.get("download_url"):
            return t["download_url"]
    return None

def wait_for_transcript_url(bot_id: Optional[str], transcript_id: Optional[str]) -> Optional[str]:
    deadline = time.time() + MAX_WAIT_SEC
    delay = POLL_START_SEC
    url = find_transcript_url(bot_id, transcript_id)
    while not url and time.time() < deadline:
        time.sleep(delay)
        delay = min(int(delay * 1.5) or 1, POLL_MAX_SEC)
        url = find_transcript_url(bot_id, transcript_id)
    return url

def ensure_project(project: str) -> Path:
    proj_dir = PROJECTS_ROOT / project
    (proj_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    return proj_dir

def invalid_project_name(name: str) -> bool:
    """Basic sanitation to avoid path traversal / invalid FS chars."""
    if not name or name.strip() == "":
        return True
    bad_chars = set('\\/:*?"<>|')
    return any(c in bad_chars for c in name) or ".." in name or name.startswith(".")

def save_txt_from_url(url: str, project: str) -> str:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    human, safe = ts_strings()

    tj = r.json()
    segments = normalize_segments(tj)
    txt_body = as_plaintext(segments)

    proj_dir = ensure_project(project)
    txt_path = proj_dir / "transcripts" / f"meeting_{safe}.txt"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Meeting transcript — {human} (Asia/Kolkata)\n")
        f.write("-" * 60 + "\n")
        f.write(txt_body)

    print("[saved txt]", txt_path)
    return str(txt_path)

def cleanup_old_transcripts(days: int = RETENTION_DAYS):
    cutoff = datetime.now(IST) - timedelta(days=days)
    for proj in PROJECTS_ROOT.iterdir():
        if not proj.is_dir(): continue
        tdir = proj / "transcripts"
        for f in tdir.glob("meeting_*.txt"):
            if datetime.fromtimestamp(f.stat().st_mtime, IST) < cutoff:
                f.unlink()
                print(f"[deleted old transcript] {f}")

def resolve_project_from_bot(bot_id: Optional[str], fallback: str = "default") -> str:
    """
    If possible, fetch the bot and read metadata.project.
    """
    project = fallback or "default"
    if not bot_id:
        return project
    try:
        r = requests.get(f"{BASE}/bot/{bot_id}/", headers=HEAD, timeout=30)
        r.raise_for_status()
        bot_info = r.json() or {}
        meta = bot_info.get("metadata") or {}
        p = (meta.get("project") or "").strip()
        if p:
            project = p
    except Exception as e:
        print("[webhook] could not fetch bot metadata:", e)
    return project

# ---------- lifespan (startup/shutdown) ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        cleanup_cache()
    except Exception as e:
        print("[startup] cleanup_cache failed:", e)
    try:
        cleanup_old_transcripts()
    except Exception as e:
        print("[startup] cleanup_old_transcripts failed:", e)
    yield

# Create FastAPI app with lifespan handler
app = FastAPI(lifespan=lifespan)

# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}

# ---- Project CRUD ----
@app.post("/create_project")
def create_project(payload: dict = Body(...)):
    project_name = (payload.get("project_name") or "").strip()
    if invalid_project_name(project_name):
        return {"error": "invalid project_name"}
    proj_dir = ensure_project(project_name)
    return {"ok": True, "project": project_name, "path": str(proj_dir)}

@app.patch("/projects/{project}")
def rename_project(project: str, payload: dict = Body(...)):
    if invalid_project_name(project):
        return {"error": "invalid current project name"}
    new_name = (payload.get("new_name") or "").strip()
    if invalid_project_name(new_name):
        return {"error": "invalid new_name"}
    old_dir = PROJECTS_ROOT / project
    if not old_dir.exists() or not old_dir.is_dir():
        return {"error": f"project '{project}' not found"}
    new_dir = PROJECTS_ROOT / new_name
    if new_dir.exists():
        return {"error": f"project '{new_name}' already exists"}
    old_dir.rename(new_dir)
    return {"ok": True, "old": project, "new": new_name, "path": str(new_dir)}

@app.delete("/projects/{project}")
def delete_project(project: str, payload: dict = Body(None)):
    if invalid_project_name(project):
        return {"error": "invalid project name"}
    confirm = bool(isinstance(payload, dict) and payload.get("confirm"))
    if not confirm:
        return {"error": "set 'confirm': true to delete project"}
    proj_dir = PROJECTS_ROOT / project
    if not proj_dir.exists() or not proj_dir.is_dir():
        return {"error": f"project '{project}' not found"}
    shutil.rmtree(proj_dir)
    return {"ok": True, "deleted": project}

# ---- Webhook ----
@app.post("/recall/webhook")
async def recall_webhook(req: Request):
    if req.headers.get("content-type","").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="content-type must be application/json")

    token_h = req.headers.get("X-Webhook-Token")
    token_q = req.query_params.get("token")
    if SECRET and token_h != SECRET and token_q != SECRET:
        raise HTTPException(status_code=401, detail="bad token")

    event = await req.json()
    etype = event.get("type") or event.get("event") or "unknown"
    data  = event.get("data", {}) or {}
    print("[webhook]", etype)

    # IDs/URL from webhook event
    download_url  = data.get("download_url")
    bot_id        = data.get("bot_id") or (data.get("bot") or {}).get("id")
    transcript_id = data.get("transcript_id") or (data.get("transcript") or {}).get("id")

    # Decide project: ?project=... OR bot.metadata.project OR "default"
    project = (req.query_params.get("project") or "").strip()
    if not project or project == "default":
        project = resolve_project_from_bot(bot_id, fallback="default")

    # Save via direct URL if present; else poll
    if download_url:
        txt_path = save_txt_from_url(download_url, project)
        return {"ok": True, "project": project, "txt": txt_path, "source": "direct"}

    url = wait_for_transcript_url(bot_id, transcript_id)
    if not url:
        return JSONResponse({"ok": True, "note": "transcript not ready yet"}, status_code=200)

    txt_path = save_txt_from_url(url, project)
    return {"ok": True, "project": project, "txt": txt_path, "source": "polled"}

# ---- Bot ----
@app.post("/start_bot")
def start_bot(payload: dict = Body(...)):
    meet_url = (payload.get("meeting_url") or "").strip()
    project  = (payload.get("project_name") or "default").strip()
    bot_name = (payload.get("bot_name") or "SummarizerBot").strip()

    if not meet_url:
        return {"error": "meeting_url is required"}

    try:
        # pass project into req_bot so it's stored in bot.metadata
        bot = req_bot(meet_url, project_name=project, bot_name=bot_name)
        return {"ok": True, "bot_id": bot.get("id"), "bot": bot, "project": project}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---- Listing ----
@app.get("/projects")
def list_projects():
    cleanup_old_transcripts()
    projects = [p.name for p in PROJECTS_ROOT.iterdir() if p.is_dir()]
    return {"projects": projects}

@app.get("/transcripts/{project}")
def list_transcripts(project: str):
    proj_dir = ensure_project(project)
    files = sorted(
        (proj_dir / "transcripts").glob("meeting_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return {"project": project,
            "transcripts": [{"label": f.stem.replace("meeting_",""), "filename": f.name} for f in files]}

# ---- Summarization ----
@app.post("/summarize")
async def summarize(req: Request):
    data = await req.json()
    project = (data.get("project_name") or "default").strip()
    transcript_file = (data.get("transcript_file") or "").strip()

    proj_dir = ensure_project(project)
    tdir = proj_dir / "transcripts"
    tpath = tdir / transcript_file

    if not tpath.exists():
        return {"error": f"{transcript_file} not found in project {project}"}

    text = tpath.read_text(encoding="utf-8")

    cached = get_summary(text)
    if cached:
        return {"summary": cached, "cached": True}

    result = run_summary(text)
    save_summary(text, result)

    return {"summary": result, "cached": False}