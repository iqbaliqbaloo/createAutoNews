"""
Step 12 — Result Logger

Appends every post attempt to data/results.json.
Used as the raw data source for Phase 2 learning loop analysis.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR     = Path(__file__).parent / "data"
RESULTS_FILE = DATA_DIR / "results.json"
MAX_ENTRIES  = 500   # keep rolling window — older entries are pruned


def log_result(article_url, intent, clip_score, image_url,
               platforms, status, retry_count=0,
               breaking=False, pipeline="A",
               cache_hit=False, library_fallback=False):
    """
    Append one entry to results.json.

    Fields:
      article_url      — source article URL
      intent           — primary intent label
      clip_score       — best CLIP score achieved
      image_url        — image URL selected
      posted_at        — UTC ISO timestamp
      platforms        — platforms posted to
      status           — "success" | "failed" | "queued"
      retry_count      — image-search retry loops used
      breaking         — True if posted via Pipeline B
      pipeline         — "A" | "B" | "C"
      cache_hit        — True if image came from cache
      library_fallback — True if image came from local library
    """
    DATA_DIR.mkdir(exist_ok=True)

    entries = []
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "r") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    entry = {
        "article_url":       article_url,
        "intent":            intent,
        "clip_score":        round(float(clip_score), 4) if clip_score is not None else None,
        "image_url":         image_url or "",
        "posted_at":         datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platforms":         platforms or [],
        "status":            status,
        "retry_count":       retry_count,
        "breaking":          breaking,
        "pipeline":          pipeline,
        "cache_hit":         cache_hit,
        "library_fallback":  library_fallback,
    }

    entries.append(entry)

    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    tmp = RESULTS_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(entries, f, indent=2)
        tmp.replace(RESULTS_FILE)
    except Exception as e:
        logger.error(f"results.json save failed: {e}")
        try:
            tmp.unlink()
        except Exception:
            pass

    logger.info(f"Logged: {status} | pipeline={pipeline} | intent={intent} | platforms={platforms}")


def best_hours(min_entries: int = 10) -> list:
    """
    Engagement Time Predictor.
    Reads results.json and returns the top 3 PKT hours that have produced
    the most successful posts. Prints insights to stdout.
    Returns list of best hours (int) or [] if not enough data yet.
    """
    import pytz
    from collections import Counter

    PKT = pytz.timezone("Asia/Karachi")

    if not RESULTS_FILE.exists():
        return []

    try:
        with open(RESULTS_FILE, "r") as f:
            entries = json.load(f)
    except Exception:
        return []

    successes = [e for e in entries if e.get("status") == "success"]
    if len(successes) < min_entries:
        print(f"  Engagement predictor: need {min_entries} posts, have {len(successes)} — building history")
        return []

    hour_counter = Counter()
    for e in successes:
        try:
            utc_dt = datetime.fromisoformat(e["posted_at"].replace("Z", "+00:00"))
            pkt_dt = utc_dt.astimezone(PKT)
            hour_counter[pkt_dt.hour] += 1
        except Exception:
            pass

    top_hours = [h for h, _ in hour_counter.most_common(3)]
    top_str   = ", ".join(f"{h:02d}:00 PKT" for h in top_hours)
    print(f"  Best posting hours (from {len(successes)} posts): {top_str}")
    return top_hours
