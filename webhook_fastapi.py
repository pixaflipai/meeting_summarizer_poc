# webhook_fastapi.py
import os, time, requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo
from cache_manager import get_summary, save_summary
from create_bot import req_bot


# --- timezone (Asia/Kolkata) ---
IST = ZoneInfo("Asia/Kolkata")

load_dotenv()
REGION  = os.getenv("RECALLAI_REGION", "us-west-2")
API_KEY = os.getenv("RECALLAI_API_KEY", "")
SECRET  = os.getenv("WEBHOOK_TOKEN", "")
TRANSCRIPTS_DIR = Path("transcripts_txt")

BASE = f"https://{REGION}.recall.ai/api/v1"
HEAD = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}

ROOT    = Path.cwd()
OUT_TXT = ROOT / "transcripts_txt"; OUT_TXT.mkdir(exist_ok=True)

# Polling parameters
MAX_WAIT_SEC   = 300   # up to 5 min
POLL_START_SEC = 2
POLL_MAX_SEC   = 15

app = FastAPI()

# ---------- helpers ----------
def ts_strings() -> tuple[str, str]:
    """('dd/mm/yyyy at HH:MM', 'dd-mm-yyyy at HH.MM') in Asia/Kolkata."""
    now = datetime.now(IST)
    return now.strftime("%d/%m/%Y at %H:%M"), now.strftime("%d-%m-%Y at %H.%M")

def normalize_segments(tj: Any) -> List[Dict[str, Any]]:
    """Unify Recall transcript JSON → [{speaker,start,end,text}]."""
    out: List[Dict[str, Any]] = []

    # Case 1: dict with segments/results/utterances/data
    if isinstance(tj, dict):
        for k in ("segments", "results", "utterances", "data"):
            v = tj.get(k)
            if isinstance(v, list):
                for seg in v:
                    out.append(_map_segment(seg))
                return out

    # Case 2: list of participants with words[]
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

def save_txt_from_url(url: str) -> str:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    human, safe = ts_strings()

    tj = r.json()
    segments = normalize_segments(tj)
    txt_body = as_plaintext(segments)

    txt_path = OUT_TXT / f"meeting_{safe}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Meeting transcript — {human} (Asia/Kolkata)\n")
        f.write("-" * 60 + "\n")
        f.write(txt_body)

    print("[saved txt]", txt_path)
    return str(txt_path)

# ---------- routes ----------
@app.get("/health")
def health(): return {"ok": True}

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

    download_url  = data.get("download_url")
    bot_id        = data.get("bot_id") or (data.get("bot") or {}).get("id")
    transcript_id = data.get("transcript_id") or (data.get("transcript") or {}).get("id")

    if download_url:
        txt_path = save_txt_from_url(download_url)
        return {"ok": True, "txt": txt_path, "source": "direct"}

    url = wait_for_transcript_url(bot_id, transcript_id)
    if not url:
        return JSONResponse({"ok": True, "note": "transcript not ready yet"}, status_code=200)

    txt_path = save_txt_from_url(url)
    return {"ok": True, "txt": txt_path, "source": "polled"}

@app.post("/start_bot")
def start_bot(payload: dict = Body(...)):
    """
    Start a Recall bot for a given meeting link.
    Expected JSON:
    { "meeting_url": "https://meet.google.com/xxx-xxxx-xxx", "bot_name": "Pixabot" (optional) }
    """
    meet_url = (payload.get("meeting_url") or "").strip()
    bot_name = (payload.get("bot_name") or "SummarizerBot").strip()

    if not meet_url:
        return {"error": "meeting_url is required"}

    try:
        bot = req_bot(meet_url, bot_name=bot_name)
        return {"ok": True, "bot_id": bot.get("id"), "bot": bot}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    
@app.get("/transcripts")
def list_transcripts():
    """Return available transcripts files for frontend dropdown."""
    files= sorted(
        TRANSCRIPTS_DIR.glob("meeting_*.txt"),
        key=lambda p:p.stat().st_mtime,
        reverse=True
    )
    return [
        {"label": f.stem.replace("meeting_",""), "filename": f.name}
        for f in files
    ]
@app.post("/sumamrize")
async def summarize(req:Request):
    """Frontend calls this with transcript text, we return cached summary if available)."""
    data= await req.json()
    text= data.get("text","").strip()
    if not text:
        return {"error":"no text provided"}
    
    cached= get_summary(text)
    if cached:
        return {"summary":cached, "cached": True}
    
    # yet to add pipleine here 