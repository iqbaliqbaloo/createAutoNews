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


# ── Story cluster builder (used by main pipeline for source verification) ──

_CLUSTER_STOP = {
    "this", "that", "with", "from", "have", "been", "will", "were", "they",
    "their", "says", "said", "also", "more", "after", "over", "just", "time",
    "news", "world", "year", "first", "last", "most", "into", "when", "what",
    "would", "could", "about", "which", "there", "where", "than", "some",
    "report", "update", "today", "breaking", "latest",
}


def _story_sig(title: str) -> str:
    """Extract 3-4 meaningful words as a story signature for clustering."""
    words = re.findall(r'\b[a-z]{4,}\b', title.lower())
    key   = [w for w in words if w not in _CLUSTER_STOP][:4]
    return " ".join(key) if len(key) >= 2 else ""


def build_story_clusters(articles: list) -> dict:
    """
    Return dict: article_hash → number of unique domains covering the same story.
    Used by the main pipeline to verify multi-source coverage before posting.
    """
    from collections import defaultdict

    sig_domains: dict = defaultdict(set)
    sig_hashes:  dict = defaultdict(list)

    for a in articles:
        sig = _story_sig(a.get("title", ""))
        if sig:
            sig_domains[sig].add(a.get("domain", ""))
            sig_hashes[sig].append(a.get("hash", ""))

    clusters = {}
    for sig, hashes in sig_hashes.items():
        count = len(sig_domains[sig])
        for h in hashes:
            clusters[h] = count

    return clusters
