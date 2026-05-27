import re
from urllib.parse import urlparse

# Domain → trust score (0.0–1.0). Below 0.4 is treated as untrusted.
DOMAIN_SCORES = {
    # Tier 1 — wire services & major broadcasters
    "reuters.com": 1.0,
    "apnews.com": 1.0,
    "afp.com": 1.0,
    "bbc.com": 1.0,
    "bbc.co.uk": 1.0,
    "voanews.com": 0.95,
    "rferl.org": 0.90,
    "bloomberg.com": 0.95,
    "ft.com": 0.95,
    "wsj.com": 0.95,
    "economist.com": 0.95,
    "nytimes.com": 0.95,
    "washingtonpost.com": 0.95,
    # Tier 2 — established international news
    "aljazeera.com": 0.92,
    "dw.com": 0.92,
    "france24.com": 0.90,
    "theguardian.com": 0.92,
    "independent.co.uk": 0.88,
    "skynews.com": 0.88,
    "sky.com": 0.85,
    "npr.org": 0.92,
    "smh.com.au": 0.88,
    "abcnews.go.com": 0.85,
    "cbsnews.com": 0.85,
    "nbcnews.com": 0.85,
    "cnn.com": 0.82,
    "time.com": 0.82,
    "aa.com.tr": 0.78,
    # Tier 3 — Pakistani news
    "geo.tv": 0.82,
    "dawn.com": 0.88,
    "thenews.com.pk": 0.82,
    "tribune.com.pk": 0.82,
    "arynews.tv": 0.80,
    "express.com.pk": 0.72,
    # Tier 4 — opinionated but legitimate
    "foxnews.com": 0.65,
    "thehill.com": 0.72,
    "politico.com": 0.82,
    "newsweek.com": 0.72,
    "dailywire.com": 0.48,
    "nypost.com": 0.55,
    "xinhuanet.com": 0.52,
    # Tier 5 — known low-credibility / propaganda
    "rt.com": 0.30,
    "sputniknews.com": 0.28,
    "globalresearch.ca": 0.18,
    "infowars.com": 0.05,
    "naturalnews.com": 0.05,
    "breitbart.com": 0.30,
    "theonion.com": 0.05,
    "babylonbee.com": 0.05,
}

CLICKBAIT_PATTERNS = [
    r"shocking",
    r"you won'?t believe",
    r"do this now",
    r"must[ -]see",
    r"secret revealed",
    r"they don'?t want you to know",
    r"what happens next will",
    r"the truth about",
    r"number \d+ will (shock|surprise|amaze)",
    r"this one (weird|simple) trick",
    r"doctors hate",
    r"click here",
    r"share before (it'?s? )?(deleted|removed|banned)",
    r"mind[ -]blowing",
    r"gone viral",
    r"explosive revelation",
]


def score_article(article):
    """
    Returns a trust score 0.0–1.0.
    Caller should reject if score < 0.4.
    Runs on the SOURCE article only — never on generated captions.
    """
    title = article.get("title", "") or ""
    url = article.get("url", "") or article.get("source_url", "") or ""
    domain = article.get("domain", "") or ""

    score = _domain_score(url, domain)
    score = _apply_clickbait_penalty(score, title)
    score = _apply_caps_penalty(score, title)
    return round(max(0.0, min(1.0, score)), 3)


def _domain_score(url, known_domain):
    """Resolve domain from URL or known_domain field, look up trust score."""
    candidates = []

    if url:
        try:
            netloc = urlparse(url).netloc.lower()
            candidates.append(_strip_prefixes(netloc))
        except Exception:
            pass

    if known_domain:
        candidates.append(_strip_prefixes(known_domain.lower()))

    for candidate in candidates:
        # Exact match
        if candidate in DOMAIN_SCORES:
            return DOMAIN_SCORES[candidate]
        # Subdomain match (e.g. feeds.reuters.com → reuters.com)
        for domain, score in DOMAIN_SCORES.items():
            if candidate.endswith("." + domain):
                return score

    return 0.60  # Unknown domain — neutral, pass with no boost


def _strip_prefixes(domain):
    """Remove common subdomains that don't carry reputation info."""
    return re.sub(r"^(feeds?|rss|news|www|m|mobile|amp)\.", "", domain)


def _apply_clickbait_penalty(score, title):
    title_lower = title.lower()
    penalty = 0.0
    for pattern in CLICKBAIT_PATTERNS:
        if re.search(pattern, title_lower):
            penalty += 0.15
    return score - min(penalty, 0.45)


def _apply_caps_penalty(score, title):
    """Penalise titles that are majority uppercase (sensationalism signal)."""
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 10:
        return score
    caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if caps_ratio > 0.60:
        return score - 0.25
    return score
