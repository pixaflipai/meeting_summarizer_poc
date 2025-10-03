# cache_manager.py
import hashlib, json, time
from pathlib import Path
from datetime import datetime, timezone

# Root cache folder
CACHE_DIR = Path("summary_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Default retention for cached summaries
RETENTION_DAYS = 15


def _cache_key(text: str, project: str | None = None, filename: str | None = None) -> str:
    """
    Build a stable key. Backward-compatible with text-only,
    but can also scope by project and/or filename to avoid collisions.
    """
    base = text
    if project:
        base = f"{project}::{base}"
    if filename:
        base = f"{filename}::{base}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def get_summary(
    text: str,
    project: str | None = None,
    filename: str | None = None,
    retention_days: int = RETENTION_DAYS,
) -> str | None:
    """
    Return cached summary if present and not expired.
    Backwards compatible: calling with only (text) still works.
    """
    key = _cache_key(text, project=project, filename=filename)
    f = CACHE_DIR / f"{key}.json"
    if not f.exists():
        return None

    cutoff = time.time() - (retention_days * 24 * 3600)
    if f.stat().st_mtime < cutoff:
        try:
            f.unlink()
        except Exception:
            pass
        return None

    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("summary")
    except Exception:
        # Corrupt cache → remove and miss
        try:
            f.unlink()
        except Exception:
            pass
        return None


def save_summary(
    text: str,
    summary: str,
    project: str | None = None,
    filename: str | None = None,
) -> str:
    """
    Save (or update) a cached summary. Backwards compatible with text-only.
    """
    key = _cache_key(text, project=project, filename=filename)
    f = CACHE_DIR / f"{key}.json"
    obj = {
        "summary": summary,
        # FIXED: proper key name + timezone-aware timestamp
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "filename": filename,
    }
    f.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(f)


def cleanup_cache(retention_days: int = RETENTION_DAYS) -> int:
    """Delete cache files older than retention_days. Returns number deleted."""
    cutoff = time.time() - (retention_days * 24 * 3600)
    deleted = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            pass
    return deleted