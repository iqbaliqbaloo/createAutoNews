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
               platforms, status, retry_count=0):
    """
    Append one entry to results.json.

    Fields logged (per spec):
      article_url  — source article URL
      intent       — primary intent label (WAR / POLITICS / …)
      clip_score   — best CLIP score achieved during image search
      image_url    — Pixabay image URL selected
      posted_at    — UTC ISO timestamp
      platforms    — list of platforms successfully posted to
      status       — "success" | "failed"
      retry_count  — number of image-search retry loops used
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
        "article_url":  article_url,
        "intent":       intent,
        "clip_score":   round(float(clip_score), 4) if clip_score is not None else None,
        "image_url":    image_url or "",
        "posted_at":    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platforms":    platforms or [],
        "status":       status,
        "retry_count":  retry_count,
    }

    entries.append(entry)

    # Keep rolling window
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    with open(RESULTS_FILE, "w") as f:
        json.dump(entries, f, indent=2)

    logger.info(f"Logged result: {status} | intent={intent} | platforms={platforms} | clip={clip_score:.3f}")
