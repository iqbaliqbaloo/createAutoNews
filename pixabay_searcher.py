import os
import json
import random
import logging
import tempfile
from datetime import datetime, timezone
import requests


from generator import clip_score as _compute_clip_score
from scene_selector import get_search_keywords, BROAD_FALLBACKS

logger = logging.getLogger(__name__)

CLIP_ACCEPT_THRESHOLD    = 0.27
MAX_RETRY_LOOPS          = 3
PIXABAY_RESULTS_PER_CALL = 5

DATA_DIR            = "data"
IMAGE_CACHE_FILE    = os.path.join(DATA_DIR, "image_cache.json")
RATE_LIMIT_FILE     = os.path.join(DATA_DIR, "rate_limit.json")
USED_IMAGES_FILE    = os.path.join(DATA_DIR, "used_images.json")
IMAGE_LIBRARY_DIR   = "image_library"

IMAGE_CACHE_TTL_SECONDS = 21600   # 6 hours
PIXABAY_HOURLY_LIMIT    = 80
# Images are PERMANENTLY blacklisted once used — no TTL, no recycling.


# ── Image cache ────────────────────────────────────────────────────────────

def _load_cache():
    try:
        with open(IMAGE_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(IMAGE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Cache save failed: {e}")


def _get_cached_urls(cache_key):
    cache = _load_cache()
    entry = cache.get(cache_key)
    if not entry:
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(
            entry["cached_at"].replace("Z", "+00:00")
        )).total_seconds()
        if age < IMAGE_CACHE_TTL_SECONDS:
            logger.info(f"Image cache HIT: {cache_key} (age {int(age)}s)")
            urls = list(entry["urls"])
            random.shuffle(urls)   # shuffle so we don't always score the same "best" first
            return urls
    except Exception:
        pass
    return None


def _store_cached_urls(cache_key, urls):
    if not urls:
        return
    cache = _load_cache()
    cache[cache_key] = {
        "urls":      urls,
        "cached_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _save_cache(cache)


# ── Recently-used image tracking ───────────────────────────────────────────

def _has_been_used(url):
    """True if this URL has EVER been posted — permanent, no expiry."""
    if not url:
        return False
    try:
        with open(USED_IMAGES_FILE) as f:
            return url in json.load(f)
    except Exception:
        return False


def _mark_image_used(url):
    """Permanently record that this URL was used. Never removed."""
    if not url:
        return
    try:
        try:
            with open(USED_IMAGES_FILE) as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[url] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(USED_IMAGES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Used-images save failed: {e}")


# ── Rate-limit tracking ────────────────────────────────────────────────────

def _load_rate():
    try:
        with open(RATE_LIMIT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_rate(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(RATE_LIMIT_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Rate limit save failed: {e}")


def _pixabay_calls_this_hour():
    data = _load_rate()
    pix  = data.get("pixabay", {})
    start_str = pix.get("window_start")
    if not start_str:
        return 0
    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        if elapsed > 3600:
            return 0   # window expired
        return pix.get("calls_this_hour", 0)
    except Exception:
        return 0


def _increment_pixabay_count():
    data  = _load_rate()
    pix   = data.get("pixabay", {})
    start_str = pix.get("window_start")
    reset = False
    if start_str:
        try:
            start   = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if elapsed > 3600:
                reset = True
        except Exception:
            reset = True
    else:
        reset = True

    if reset:
        pix = {
            "calls_this_hour": 1,
            "window_start":    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    else:
        pix["calls_this_hour"] = pix.get("calls_this_hour", 0) + 1

    data["pixabay"] = pix
    _save_rate(data)


# ── CLIP scoring ───────────────────────────────────────────────────────────

def _clip_score(image_path, scene_keywords):
    keyword_str = " ".join(scene_keywords)[:200]
    return _compute_clip_score(keyword_str, image_path)


# ── Pixabay search ─────────────────────────────────────────────────────────

def _search_pixabay_raw(keywords):
    """Call Pixabay API (no cache, no rate-gate)."""
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
                    "key":         api_key,
                    "q":           phrase,
                    "image_type":  "photo",
                    "per_page":    PIXABAY_RESULTS_PER_CALL,
                    "safesearch":  "true",
                    "orientation": "horizontal",
                    "min_width":   1000,
                },
                timeout=12,
            )
            for h in r.json().get("hits", []):
                url = h.get("largeImageURL")
                if url and url not in seen:
                    seen.add(url)
                    results.append(url)
            if results:
                break
        except Exception as e:
            logger.warning(f"Pixabay '{phrase}': {e}")
            continue

    return results[:PIXABAY_RESULTS_PER_CALL]


# ── Pexels search ──────────────────────────────────────────────────────────

def _search_pexels(keywords):
    """Search Pexels API as fallback when Pixabay hourly limit is hit."""
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    phrases = keywords if isinstance(keywords, list) else [keywords]

    for phrase in phrases:
        phrase = phrase.strip()
        if not phrase:
            continue
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": phrase, "per_page": PIXABAY_RESULTS_PER_CALL, "orientation": "landscape"},
                headers={"Authorization": api_key},
                timeout=12,
            )
            photos = r.json().get("photos", [])
            urls = [u for p in photos if p.get("src")
                    for u in [p["src"].get("large2x") or p["src"].get("large")] if u]
            if urls:
                return urls[:PIXABAY_RESULTS_PER_CALL]
        except Exception as e:
            logger.warning(f"Pexels '{phrase}': {e}")
            continue

    return []


# ── Local image library fallback ──────────────────────────────────────────

def _local_library_path(intent):
    """Return a random local image path for the given intent, or None."""
    folder = os.path.join(IMAGE_LIBRARY_DIR, intent.upper())
    if not os.path.isdir(folder):
        return None
    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if not files:
        return None
    return random.choice(files)


# ── Unified image search (cache → Pixabay → Pexels → local library) ───────

def _search_images(keywords, cache_key):
    """
    1. Try image cache (6-hour TTL)
    2. If Pixabay under limit → call Pixabay, store in cache
    3. If Pixabay at limit → call Pexels, store in cache
    Returns list of URLs (possibly empty).
    """
    cached = _get_cached_urls(cache_key)
    if cached:
        return cached

    if _pixabay_calls_this_hour() < PIXABAY_HOURLY_LIMIT:
        _increment_pixabay_count()
        urls = _search_pixabay_raw(keywords)
        source = "Pixabay"
    else:
        logger.info("Pixabay hourly limit reached — switching to Pexels")
        urls = _search_pexels(keywords)
        source = "Pexels"

    if urls:
        logger.info(f"{source} returned {len(urls)} URLs for key={cache_key}")
        _store_cached_urls(cache_key, urls)
    return urls


# ── Image download ─────────────────────────────────────────────────────────

def _download_tmp(url):
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
    Steps 7 + 8: scene-keyword-driven image search with CLIP validation.

    Fallback chain per retry loop:
      Cache → Pixabay (or Pexels if rate-limited) → local image_library (last resort)

    Returns (image_url, best_clip_score, retry_count, best_image_path)
    """
    intent_label = intent_result["intent"]["primary"]
    best_url   = None
    best_score = 0.0
    best_path  = None

    loop = 0
    for loop in range(MAX_RETRY_LOOPS + 1):
        keywords  = get_search_keywords(intent_result, article=article, retry_loop=loop)
        cache_key = f"{intent_label}_{keywords[0].replace(' ', '_')}" if keywords else f"{intent_label}_news"
        logger.info(f"Image search loop={loop} keywords={keywords}")
        print(f"  [Image loop {loop}] keywords: {keywords}")

        for img_url in _search_images(keywords, cache_key):
            if _has_been_used(img_url):
                logger.info(f"Skipping recently used image: {img_url}")
                continue

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
                _cleanup(best_path)
                best_score = score
                best_url   = img_url
                best_path  = path
            else:
                _cleanup(path)

            if best_score >= CLIP_ACCEPT_THRESHOLD:
                print(f"  Accepted (CLIP={best_score:.3f}, loop={loop})")
                _mark_image_used(best_url)
                return best_url, best_score, loop, best_path

        if loop >= MAX_RETRY_LOOPS:
            break

    # ── Intent-specific broad fallback (never generic) ────────────────────
    if best_path is None:
        print("  All specific searches failed — trying intent-specific broad fallback")
        broad_terms = BROAD_FALLBACKS.get(intent_label, BROAD_FALLBACKS.get("POLITICS", ["news"]))
        for fallback in broad_terms:
            fallback_key = f"{intent_label}_broad_{fallback[:20].replace(' ', '_')}"
            for img_url in _search_images([fallback], fallback_key):
                if _has_been_used(img_url):
                    continue
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

    if best_url:
        _mark_image_used(best_url)

    # ── Local image library — final fallback ──────────────────────────────
    if best_path is None:
        local = _local_library_path(intent_label)
        if local:
            print(f"  Using local library image: {local}")
            best_path  = local
            best_url   = ""
            best_score = 0.0

    print(f"  Best available: CLIP={best_score:.3f} retries={loop} path={'ok' if best_path else 'NONE'}")
    return best_url, best_score, loop, best_path
