import hashlib,json
from pathlib import Path
from datetime import datetime, timezone
import time

CACHE_DIR=Path("summary_cache")
CACHE_DIR.mkdir(exist_ok=True)

RETENTION_DAYS=15

def _cache_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def get_summary(text:str) ->str | None:
    "This returns summary if already cached and not expired"
    key=_cache_key(text)
    f=CACHE_DIR/f"{key}.json"
    if not f.exists():
        return None
    
    cutoff=time.time() - (RETENTION_DAYS * 24 * 3600)
    if f.stat().st_mtime < cutoff:
        try:
            f.unlink()
        except Exception:
            pass
        return None
    return json.loads(f.read_text(encoding="utf-8")).get("summary")

def save_summary(text:str, summary:str):
    "Cache new summary for text"
    key=_cache_key(text)
    f=CACHE_DIR/f"{key}.json"
    obj= {
        "summary": summary,
        "created_at:": datetime.now(timezone.utc).isoformat()
    }
    f.write_text(json.dumps(obj, ensure_ascii=False , indent=2), encoding="utf-8")
    return str(f)