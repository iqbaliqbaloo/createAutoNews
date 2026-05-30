"""
Trending Keyword Detector — pure Python, zero cost.

Counts word frequency across all articles fetched in the current run.
If 8 of 30 articles mention "Gaza" — that topic is trending right now.
Injects those keywords into captions as hashtags automatically.
"""

import re
from collections import Counter

_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "been",
    "will", "were", "they", "their", "about", "after", "when", "over",
    "more", "also", "than", "into", "some", "what", "which", "would",
    "could", "said", "says", "report", "reports", "according", "amid",
    "amid", "week", "month", "year", "years", "time", "government",
    "country", "president", "minister", "people", "officials", "told",
    "news", "world", "state", "states", "make", "made", "take", "took",
    "come", "came", "want", "needs", "many", "most", "other", "through",
    "where", "while", "there", "here", "being", "each", "such", "then",
    "first", "last", "next", "just", "still", "back", "even", "those",
    "only", "both", "three", "four", "five", "six", "seven", "eight",
}


def detect_trending(articles: list, top_n: int = 6) -> list:
    """
    Return top N trending keywords as hashtag strings e.g. ['#Gaza', '#IMF'].
    Analyzes titles + summaries of all fetched articles.
    """
    counter = Counter()
    for a in articles:
        text = ((a.get("title") or "") + " " + (a.get("summary") or "")).lower()
        words = re.findall(r'\b[a-z]{4,}\b', text)
        counter.update(w for w in words if w not in _STOP)

    trending = []
    for word, count in counter.most_common(top_n * 3):
        if count >= 2:               # must appear in at least 2 articles
            trending.append(f"#{word.capitalize()}")
        if len(trending) == top_n:
            break

    return trending


def trending_context_string(articles: list) -> str:
    """Return a compact string to inject into the caption prompt."""
    tags = detect_trending(articles)
    if not tags:
        return ""
    return "Currently trending topics across today's news: " + " ".join(tags)
