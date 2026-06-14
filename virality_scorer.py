"""
Virality Scorer — pure Python, zero API calls, zero cost.

Scores each article 0-100 on predicted organic reach potential.
Facebook's algorithm amplifies posts that trigger reactions/shares in the
first 30-60 minutes. High-emotion, fresh, relevant stories do that consistently.
"""

import re
from datetime import datetime, timezone, timedelta

_HIGH_EMOTION = {
    "kill", "killed", "dead", "death", "die", "died", "dies",
    "war", "attack", "attacked", "bomb", "explosion", "blast", "fire",
    "crash", "disaster", "earthquake", "flood", "hurricane", "tsunami",
    "terror", "terrorist", "hostage", "massacre", "genocide",
    "collapse", "crisis", "emergency", "urgent", "breaking",
    "shocking", "massive", "historic", "record", "worst", "biggest",
    "unprecedented", "scandal", "corruption", "betrayal", "exposed", "leaked",
}

_MED_EMOTION = {
    "arrest", "arrested", "accused", "charged", "indicted",
    "resign", "resigned", "fired", "sacked", "removed",
    "ban", "banned", "sanction", "sanctioned",
    "protest", "strike", "riot", "unrest", "uprising",
    "victory", "defeat", "win", "won", "lost", "election", "vote",
    "controversial", "outrage", "outraged", "fury", "anger",
}

_WORLD_CUP_SIGNAL = {
    "world cup", "fifa", "worldcup", "wc2026", "world cup 2026",
    "group stage", "knockout", "quarter final", "semi final", "final",
}

_PAKISTAN_SIGNAL = {
    "pakistan", "karachi", "lahore", "islamabad", "rawalpindi", "peshawar",
    "quetta", "multan", "faisalabad", "imran", "nawaz", "shehbaz",
    "pti", "pmln", "ppp", "mqm", "army", "ispr", "isi",
    "punjab", "sindh", "kpk", "balochistan", "rupee", "pkr", "sbp",
}

_NUMBER_RE     = re.compile(r'\b\d+\b')
_QUESTION_RE   = re.compile(r'\?')
_SUPERLATIVE_RE = re.compile(
    r'\b(most|least|best|worst|largest|smallest|highest|lowest|first|last|only|never|always)\b',
    re.IGNORECASE,
)


def virality_score(article: dict) -> float:
    title   = (article.get("title",   "") or "").lower()
    summary = (article.get("summary", "") or "").lower()
    text    = title + " " + summary

    score = 50.0

    # Recency
    published_at = article.get("published_at")
    if published_at:
        try:
            if isinstance(published_at, str):
                pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            else:
                pub = published_at
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - pub
            if age < timedelta(hours=1):
                score += 20
            elif age < timedelta(hours=3):
                score += 14
            elif age < timedelta(hours=6):
                score += 8
            elif age < timedelta(hours=12):
                score += 3
            elif age > timedelta(hours=36):
                score -= 12
        except Exception:
            pass

    # Emotional intensity
    words     = set(re.findall(r'\b\w+\b', text))
    high_hits = len(words & _HIGH_EMOTION)
    med_hits  = len(words & _MED_EMOTION)
    if high_hits >= 2:
        score += 18
    elif high_hits == 1:
        score += 10
    if med_hits >= 2:
        score += 8
    elif med_hits == 1:
        score += 4

    # World Cup boost — highest priority sports event
    if any(kw in text for kw in _WORLD_CUP_SIGNAL):
        score += 20

    # Pakistan relevance
    pak_hits = len(words & _PAKISTAN_SIGNAL)
    if pak_hits >= 2:
        score += 10
    elif pak_hits == 1:
        score += 5

    # Title characteristics
    title_orig = article.get("title", "") or ""
    if _NUMBER_RE.search(title_orig):
        score += 5
    if _QUESTION_RE.search(title_orig):
        score += 5
    if _SUPERLATIVE_RE.search(title_orig):
        score += 4
    if 50 <= len(title_orig) <= 90:
        score += 3

    # Trust score bonus from fake-news filter
    trust = article.get("trust_score", 0.5)
    score += (trust - 0.5) * 10

    return round(min(100.0, max(0.0, score)), 1)


def rank_by_virality(articles: list) -> list:
    """Sort articles descending by virality score. Adds 'virality_score' key."""
    for a in articles:
        a["virality_score"] = virality_score(a)
    return sorted(articles, key=lambda a: a["virality_score"], reverse=True)
