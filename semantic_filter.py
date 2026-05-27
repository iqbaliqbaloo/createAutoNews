import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Reuse the MiniLM model already loaded by deduplicator to avoid double-loading.
# Import order in main.py must ensure deduplicator is imported first.
from deduplicator import model as _minilm

ALLOWED_TOPICS = [
    "war military conflict troops soldiers combat battlefield",
    "politics government parliament election president diplomacy",
    "economy finance stock market inflation trade recession banking",
    "natural disaster earthquake flood hurricane emergency rescue",
    "sports football cricket tennis match championship tournament",
    "international relations treaty sanctions geopolitics",
    "terrorism bombing explosion attack security threat",
    "climate change environment pollution energy crisis",
    "human rights protest demonstration civil unrest",
    "health pandemic disease outbreak medical emergency",
    "nuclear weapons missile defense military technology",
    "crime law court justice police investigation arrest",
    "humanitarian crisis refugees aid displacement",
]

BLOCKED_TOPICS = [
    "celebrity gossip entertainment tabloid rumor dating breakup",
    "pornography adult content explicit sexual material",
    "social media viral meme tiktok influencer challenge trend",
    "advertisement promotion marketing sale discount offer",
    "horoscope astrology zodiac prediction fortune telling",
    "cooking recipe food diet nutrition lifestyle tips",
    "fashion beauty makeup cosmetics style trends",
    "gaming video games esports streamer entertainment",
    "cryptocurrency bitcoin nft blockchain investment scheme",
]

_allowed_embeddings = None
_blocked_embeddings = None


def _get_topic_embeddings():
    global _allowed_embeddings, _blocked_embeddings
    if _allowed_embeddings is None:
        _allowed_embeddings = _minilm.encode(ALLOWED_TOPICS, convert_to_numpy=True)
        _blocked_embeddings = _minilm.encode(BLOCKED_TOPICS, convert_to_numpy=True)
    return _allowed_embeddings, _blocked_embeddings


def embed_article(article):
    """Return a numpy embedding vector for the article's title + description."""
    title = article.get("title", "") or ""
    desc = article.get("summary", "") or article.get("description", "") or ""
    text = f"{title} {desc}".strip()[:1000]
    return _minilm.encode([text], convert_to_numpy=True)[0]


def passes_semantic_filter(article_embedding):
    """
    Returns (passes: bool, reason: str).
    - Blocked if similarity to any blocked topic > 0.75
    - Allowed if similarity to any allowed topic > 0.70
    - Rejected otherwise (low topic relevance)
    """
    allowed_embs, blocked_embs = _get_topic_embeddings()
    vec = article_embedding.reshape(1, -1)

    blocked_scores = cosine_similarity(vec, blocked_embs)[0]
    allowed_scores = cosine_similarity(vec, allowed_embs)[0]

    max_blocked = float(np.max(blocked_scores))
    max_allowed = float(np.max(allowed_scores))

    if max_blocked > 0.75:
        return False, f"blocked topic sim={max_blocked:.2f}"

    if max_allowed > 0.70:
        return True, f"allowed topic sim={max_allowed:.2f}"

    return False, f"low relevance (allowed_max={max_allowed:.2f})"
