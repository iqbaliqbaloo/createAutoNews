import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Reuse the MiniLM model already loaded by deduplicator to avoid double-loading.
# Import order in main.py must ensure deduplicator is imported first.
from deduplicator import model as _minilm

ALLOWED_TOPICS = [
    # War / military
    "troops killed military attack war soldiers conflict zone airstrike",
    "missile strike army navy warfare weapons defense combat",
    # Politics / diplomacy
    "president prime minister government parliament election vote sanctions",
    "diplomatic talks peace deal treaty summit United Nations",
    # Economy / finance
    "stock market inflation recession trade tariff GDP unemployment central bank",
    "oil prices currency crisis debt bonds economic growth",
    # Natural disasters / humanitarian
    "earthquake flood hurricane wildfire disaster victims rescue emergency",
    "humanitarian crisis refugees displaced civilians famine aid",
    # Health / pandemic
    "disease outbreak pandemic virus deaths hospital WHO health emergency",
    "Ebola cholera epidemic casualties medical response",
    # Crime / security / terrorism
    "attack bombing explosion arrested killed police investigation FBI",
    "terrorism extremist militant threat national security crime",
    # Geopolitics / international
    "Iran Russia China India nuclear deal agreement ceasefire occupation",
    "Ukraine Gaza Israel Lebanon West Bank NATO alliance",
    # Protest / civil unrest
    "protest demonstration riot crackdown opposition rally arrests detained",
    # Environment / climate
    "climate change carbon emissions fossil fuels warming drought flooding",
    # Sports (competitive / major events only)
    "World Cup Olympics championship match tournament final league squad",
]

BLOCKED_TOPICS = [
    "celebrity gossip Taylor Swift Harry Styles pop star dating rumors",
    "fashion beauty makeup skincare cosmetics diet tips lifestyle",
    "cooking recipe food nutrition wellness horoscope astrology",
    "social media viral tiktok influencer meme challenge entertainment",
    "reality TV show streaming Netflix drama comedy actor awards",
    "cryptocurrency bitcoin NFT investment scheme promotion advertisement",
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

    if max_blocked > 0.45:
        return False, f"blocked topic sim={max_blocked:.2f}"

    if max_allowed > 0.25:
        return True, f"allowed topic sim={max_allowed:.2f}"

    return False, f"low relevance (allowed_max={max_allowed:.2f})"
