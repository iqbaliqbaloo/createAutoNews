"""
Step 11 — Scheduler Queue

Prevents API rate-limit errors when GitHub Actions triggers multiple posts
simultaneously. Tracks last-posted timestamp per platform and enforces:
  - Facebook:  minimum 30-minute gap between posts
  - Instagram: minimum 45-minute gap between posts
                AND at least 15 minutes after the last Facebook post

State is persisted in data/queue.json across GitHub Actions runs.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR  = Path(__file__).parent / "data"
QUEUE_FILE = DATA_DIR / "queue.json"

COOLDOWNS = {
    "facebook":  timedelta(minutes=30),
    "instagram": timedelta(minutes=45),
    "telegram":  timedelta(minutes=20),
}
# Instagram must trail Facebook by at least this much within the same session
IG_FB_OFFSET = timedelta(minutes=15)


# ── I/O ────────────────────────────────────────────────────────────────────

def _load():
    DATA_DIR.mkdir(exist_ok=True)
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_posted": {"facebook": None, "instagram": None, "telegram": None}}


def _save(data):
    DATA_DIR.mkdir(exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(QUEUE_FILE)
    except Exception as e:
        logger.warning(f"Queue save failed: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


# ── Helpers ────────────────────────────────────────────────────────────────

def _last_dt(data, platform):
    ts = data["last_posted"].get(platform)
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc)


# ── Public API ─────────────────────────────────────────────────────────────

def can_post_now(platform):
    """
    True if the platform cooldown has expired AND (for Instagram) at least
    IG_FB_OFFSET has passed since the last Facebook post.
    """
    data = _load()
    now  = _now()

    last = _last_dt(data, platform)
    if last and (now - last) < COOLDOWNS[platform]:
        logger.info(f"{platform} on cooldown — {COOLDOWNS[platform] - (now - last)} remaining")
        return False

    if platform == "instagram":
        fb_last = _last_dt(data, "facebook")
        if fb_last and (now - fb_last) < IG_FB_OFFSET:
            logger.info(f"Instagram waiting for FB offset — {IG_FB_OFFSET - (now - fb_last)} remaining")
            return False

    return True


def get_platforms_ready():
    """Return list of platforms whose cooldowns have expired."""
    return [p for p in COOLDOWNS if can_post_now(p)]


def mark_posted(platform):
    """Record that `platform` posted successfully right now."""
    data = _load()
    ts   = _now().isoformat().replace("+00:00", "Z")
    data["last_posted"][platform] = ts
    _save(data)
    logger.info(f"Queue updated: {platform} → {ts}")


def next_available(platform):
    """Return datetime when platform will next be available (utc)."""
    data = _load()
    last = _last_dt(data, platform)
    if not last:
        return _now()
    return last + COOLDOWNS[platform]
