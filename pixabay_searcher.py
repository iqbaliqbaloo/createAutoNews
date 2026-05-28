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

CLIP_ACCEPT_THRESHOLD  = 0.27   # calibrated to real-world CLIP text↔image scores
MAX_RETRY_LOOPS        = 3      # 0,1,2,3 → 4 attempts total
PIXABAY_RESULTS_PER_CALL = 5


# ── CLIP scoring ───────────────────────────────────────────────────────────

def _clip_score(image_path, scene_keywords):
    """
    Score image vs the SCENE KEYWORD STRING (not raw article text).
    CLIP validates that the image visually matches the scene type.
    """
    keyword_str = " ".join(scene_keywords)[:200]
    img = Image.open(image_path).convert("RGB")
    text_emb = clip_model.encode([keyword_str])
    img_emb  = clip_model.encode([img])
    return float(cosine_similarity(text_emb, img_emb)[0][0])


# ── Pixabay search ─────────────────────────────────────────────────────────

def _search_pixabay(keywords):
    """
    Try each keyword PHRASE individually until results are found.
    Never joins all phrases into one long query — Pixabay times out on long strings.
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return []

    phrases = keywords if isinstance(keywords, list) else [keywords]
    seen, results = set(), []

    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key":          api_key,
                    "q":            phrase,
                    "image_type":   "photo",
                    "per_page":     PIXABAY_RESULTS_PER_CALL,
                    "safesearch":   "true",
                    "orientation":  "horizontal",
                    "min_width":    1000,
                },
                timeout=12,
            )
            for h in r.json().get("hits", []):
                url = h.get("largeImageURL")
                if url and url not in seen:
                    seen.add(url)
                    results.append(url)
            if results:
                break   # stop on first phrase that returns hits
        except Exception as e:
            logger.warning(f"Pixabay '{phrase}': {e}")
            continue    # try next phrase on timeout / error

    return results[:PIXABAY_RESULTS_PER_CALL]


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
        logger.warning(f"Download failed ({url}): {e}")
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

    KEY DESIGN: the best-scoring image file is KEPT on disk and returned to
    the caller as `best_path`.  The image_composer uses it directly — no
    re-download — which eliminates blank images caused by network failures
    between scoring and composition.  Caller is responsible for cleanup.

    Retry strategy:
      Loop 0 → primary scene keywords
      Loop 1 → secondary keywords
      Loop 2 → tertiary keywords (primary intent)
      Loop 3 → generic fallback keyword
    After all retries → use highest-scoring image regardless of CLIP score.
    Never skip an article over image quality.

    Returns (image_url, best_clip_score, retry_count, best_image_path)
    """
    best_url   = None
    best_score = 0.0
    best_path  = None   # kept on disk until caller cleans up

    for loop in range(MAX_RETRY_LOOPS + 1):
        keywords = get_search_keywords(intent_result, retry_loop=loop)
        logger.info(f"Image search loop={loop} keywords={keywords}")
        print(f"  [Image loop {loop}] keywords: {keywords}")

        for img_url in _search_pixabay(keywords):
            path = _download_tmp(img_url)
            if not path:
                continue

            try:
                score = _clip_score(path, keywords)
            except Exception as e:
                logger.warning(f"CLIP error: {e}")
                _cleanup(path)
                continue

            logger.info(f"CLIP {score:.4f} | loop={loop} | url={img_url}")
            print(f"    CLIP={score:.3f}")

            if score > best_score:
                _cleanup(best_path)   # discard previous best
                best_score = score
                best_url   = img_url
                best_path  = path     # keep this file — do NOT clean up
            else:
                _cleanup(path)        # not better, discard immediately

            if best_score >= CLIP_ACCEPT_THRESHOLD:
                print(f"  Accepted (CLIP={best_score:.3f}, loop={loop})")
                return best_url, best_score, loop, best_path

        if loop >= MAX_RETRY_LOOPS:
            break

    # ── Broad fallback: if no Pixabay result survived download, try safe terms ──
    if best_path is None:
        print("  All specific searches failed — trying broad fallback")
        for fallback in ["world news", "global city skyline", "news background", "city crowd"]:
            for img_url in _search_pixabay([fallback]):
                path = _download_tmp(img_url)
                if not path:
                    continue
                try:
                    score = _clip_score(path, [fallback])
                except Exception:
                    _cleanup(path)
                    continue
                if score > best_score:
                    _cleanup(best_path)
                    best_score = score
                    best_url   = img_url
                    best_path  = path
                else:
                    _cleanup(path)
            if best_path:
                break

    print(f"  Best available: CLIP={best_score:.3f} retries={MAX_RETRY_LOOPS} path={'ok' if best_path else 'NONE'}")
    return best_url, best_score, MAX_RETRY_LOOPS, best_path
