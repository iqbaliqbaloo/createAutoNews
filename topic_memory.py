import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MEMORY_FILE = DATA_DIR / "topic_memory.json"
COOLDOWN_HOURS = 2

INTENTS = [
    "WAR", "POLITICS", "ECONOMY", "DISASTER", "SPORTS",
    "SPORTS_CRICKET", "SPORTS_FOOTBALL", "SPORTS_LIVE",
]


# ── I/O ────────────────────────────────────────────────────────────────────

def _load():
    DATA_DIR.mkdir(exist_ok=True)
    defaults = {intent: None for intent in INTENTS}
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r") as f:
                stored = json.load(f)
            defaults.update(stored)   # old keys preserved; new keys defaulted
            return defaults
        except Exception:
            pass
    return defaults


def _save(memory):
    DATA_DIR.mkdir(exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


# ── Public API ─────────────────────────────────────────────────────────────

def is_on_cooldown(intent):
    """True if this intent was posted less than 2 hours ago."""
    last = _load().get(intent)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt < timedelta(hours=COOLDOWN_HOURS)
    except Exception:
        return False


def cooldown_remaining(intent):
    """Seconds remaining until cooldown expires (0 if not on cooldown)."""
    last = _load().get(intent)
    if not last:
        return 0
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - last_dt
        remaining = timedelta(hours=COOLDOWN_HOURS) - elapsed
        return max(0, remaining.total_seconds())
    except Exception:
        return 0


def get_best_intent(articles_with_intents):
    """
    Given [(article, intent_result), …], return the pair whose primary intent
    is NOT on cooldown.  If ALL are on cooldown, return the one with the least
    remaining cooldown time.
    """
    # First pass: any article not on cooldown
    for article, intent_result in articles_with_intents:
        primary = intent_result["intent"]["primary"]
        if not is_on_cooldown(primary):
            logger.info(f"Topic memory: {primary} is available")
            return article, intent_result

    # All on cooldown — pick lowest remaining cooldown
    logger.info("All intents on cooldown — picking lowest remaining")
    return min(
        articles_with_intents,
        key=lambda pair: cooldown_remaining(pair[1]["intent"]["primary"]),
    )


def mark_intent_posted(intent):
    """Record that this intent was just posted."""
    memory = _load()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    memory[intent] = ts
    _save(memory)
    logger.info(f"Topic memory updated: {intent} → {ts}")
