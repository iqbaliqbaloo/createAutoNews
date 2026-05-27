import os
import logging
import tempfile
import requests
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity

# Reuse the CLIP model already loaded by generator.py to avoid double-loading.
from generator import clip_model
from scene_selector import get_search_keywords

logger = logging.getLogger(__name__)

CLIP_ACCEPT_THRESHOLD = 0.30   # per spec
MAX_RETRY_LOOPS = 3             # 0,1,2,3 → 4 attempts total
PIXABAY_RESULTS_PER_CALL = 5


# ── CLIP scoring ───────────────────────────────────────────────────────────

def _clip_score(image_path, scene_keywords):
    """
    Score image vs the SCENE KEYWORD STRING (not raw article text).
    This is intentional: CLIP validates that the image visually matches
    the scene type, not that it contains every word from the article.
    """
    keyword_str = " ".join(scene_keywords)[:200]
    try:
        img = Image.open(image_path).convert("RGB")
        text_emb = clip_model.encode([keyword_str])
        img_emb  = clip_model.encode([img])
        return float(cosine_similarity(text_emb, img_emb)[0][0])
    except Exception as e:
        logger.warning(f"CLIP scoring error: {e}")
        return 0.0


# ── Pixabay search ─────────────────────────────────────────────────────────

def _search_pixabay(keywords):
    """Return list of largeImageURLs from Pixabay (up to PIXABAY_RESULTS_PER_CALL)."""
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return []
    query = " ".join(keywords) if isinstance(keywords, list) else keywords
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": api_key,
                "q": query,
                "image_type": "photo",
                "per_page": PIXABAY_RESULTS_PER_CALL,
                "safesearch": "true",
                "orientation": "horizontal",
                "min_width": 1000,
            },
            timeout=12,
        )
        hits = r.json().get("hits", [])
        return [h["largeImageURL"] for h in hits if h.get("largeImageURL")]
    except Exception as e:
        logger.error(f"Pixabay search error for '{query}': {e}")
        return []


# ── Image download ─────────────────────────────────────────────────────────

def _download_tmp(url):
    """Download image to a temp file; returns path or None on failure."""
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or len(r.content) < 8000:
            return None
        if b"<html" in r.content[:200].lower():
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(r.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.warning(f"Image download failed ({url}): {e}")
        return None


def _cleanup(path):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass


# ── Main entry point ───────────────────────────────────────────────────────

def search_with_clip_validation(intent_result, article=None):
    """
    Steps 7 + 8: scene-keyword-driven Pixabay search with CLIP validation.

    Retry strategy (per spec):
      Loop 0 → primary scene keywords
      Loop 1 → secondary keywords
      Loop 2 → tertiary keywords
      Loop 3 → generic fallback keyword
    After all retries → use highest-scoring image regardless of score.
    Never skip an article over image quality.

    Returns (image_url: str | None, best_clip_score: float, retry_count: int)
    """
    best_url   = None
    best_score = 0.0

    for loop in range(MAX_RETRY_LOOPS + 1):
        keywords = get_search_keywords(intent_result, retry_loop=loop)
        logger.info(f"Image search loop={loop} keywords={keywords}")
        print(f"  [Image loop {loop}] keywords: {keywords}")

        image_urls = _search_pixabay(keywords)

        for img_url in image_urls:
            path = _download_tmp(img_url)
            if not path:
                continue
            try:
                score = _clip_score(path, keywords)
                # Log every CLIP score for future learning loop analysis
                logger.info(f"CLIP {score:.4f} | loop={loop} | url={img_url} | kw={' '.join(keywords)}")
                print(f"    CLIP={score:.3f}")

                if score > best_score:
                    best_score = score
                    best_url   = img_url

                if score >= CLIP_ACCEPT_THRESHOLD:
                    print(f"  Accepted (CLIP={score:.3f}, loop={loop})")
                    return best_url, best_score, loop

            finally:
                _cleanup(path)

        if loop >= MAX_RETRY_LOOPS:
            break

    # All loops exhausted — use best available image (never skip article)
    print(f"  Best available image: CLIP={best_score:.3f} after {MAX_RETRY_LOOPS} retries")
    return best_url, best_score, MAX_RETRY_LOOPS
