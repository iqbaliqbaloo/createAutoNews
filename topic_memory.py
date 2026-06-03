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
    tmp = MEMORY_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(memory, f, indent=2)
        tmp.replace(MEMORY_FILE)
    except Exception as e:
        logger.warning(f"Topic memory save failed: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass


# ── Public API ─────────────────────────────────────────────────────────────

def is_on_cooldown(intent, memory=None):
    """True if this intent was posted less than 2 hours ago."""
    if memory is None:
        memory = _load()
    last = memory.get(intent)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt < timedelta(hours=COOLDOWN_HOURS)
    except Exception:
        return False


def cooldown_remaining(intent, memory=None):
    """Seconds remaining until cooldown expires (0 if not on cooldown)."""
    if memory is None:
        memory = _load()
    last = memory.get(intent)
    if not last:
        return 0
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - last_dt
        remaining = timedelta(hours=COOLDOWN_HOURS) - elapsed
        return max(0, remaining.total_seconds())
    except Exception:
        return 0


def get_last_posted_intent(memory=None):
    """Return the intent that was most recently posted (or None)."""
    if memory is None:
       memory = _load()
    last_intent = None
    last_ts     = None
    for intent, ts in memory.items():
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if last_ts is None or dt > last_ts:
                last_ts     = dt
                last_intent = intent
        except Exception:
            pass
    return last_intent


def get_best_intent(articles_with_intents):
    """
    Given [(article, intent_result), …], return the pair whose primary intent
    is NOT on cooldown AND is not the same as the last posted intent.
    Falls back gracefully if all options are suboptimal.
    """
    memory = _load()
    last_intent = get_last_posted_intent(memory)


    # First pass: not on cooldown AND not a consecutive repeat
    for article, intent_result in articles_with_intents:
        primary = intent_result.get("intent", {}).get("primary")
        if not primary:
            continue
        if not is_on_cooldown(primary, memory) and primary != last_intent:
            logger.info(f"Topic memory: {primary} selected (diverse, off cooldown)")
            return article, intent_result

    # Second pass: not on cooldown (allow repeat if no diverse option)
    for article, intent_result in articles_with_intents:
        primary = intent_result.get("intent", {}).get("primary")
        if not primary:
            continue
        if not is_on_cooldown(primary, memory):
            logger.info(f"Topic memory: {primary} selected (off cooldown, repeat allowed)")
            return article, intent_result

    # All on cooldown — pick lowest remaining cooldown
    logger.info("All intents on cooldown — picking lowest remaining")
    return min(
        articles_with_intents,
        key=lambda pair: cooldown_remaining(
            pair[1].get("intent", {}).get("primary", ""), memory
        ),
    )


def get_ordered_intents(articles_with_intents):
    """
    Return all (article, intent_result) pairs sorted by posting priority:
      1. Not on cooldown AND diverse (different from last posted intent)
      2. Not on cooldown (repeat allowed)
      3. On cooldown — sorted by lowest remaining time
    Used by the multi-post loop in main.py.
    """
    memory      = _load()
    last_intent = get_last_posted_intent(memory)

    def _priority(pair):
        primary    = pair[1].get("intent", {}).get("primary", "")
        on_cd      = is_on_cooldown(primary, memory)
        is_repeat  = (primary == last_intent)
        remaining  = cooldown_remaining(primary, memory)
        if not on_cd and not is_repeat:
            return (0, remaining)
        if not on_cd:
            return (1, remaining)
        return (2, remaining)

    return sorted(articles_with_intents, key=_priority)


def mark_intent_posted(intent):
    """Record that this intent was just posted."""
    memory = _load()
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    memory[intent] = ts
    _save(memory)
    logger.info(f"Topic memory updated: {intent} → {ts}")
