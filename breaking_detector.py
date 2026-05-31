"""
Pipeline B — Breaking News Detector

Runs every 2 hours (breaking_detector.yml).
Phase 1 (lightweight, always): keyword pre-check only — no ML.
Phase 2 (full ML, conditional): runs only when Phase 1 finds a breaking signal.
Scans the last 120 minutes of RSS, scores articles, and fast-posts
anything that hits the breaking threshold while staying safely
within daily/hourly caps.
"""

import os
import re
import json
import hashlib
import logging
import tempfile
from datetime import datetime, timezone, timedelta

import feedparser
import pytz
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PKT            = pytz.timezone("Asia/Karachi")
DATA_DIR       = "data"
STATE_FILE     = os.path.join(DATA_DIR, "breaking_state.json")

SCORE_POST  = 60   # immediate post
SCORE_QUEUE = 40   # add to queue

BREAKING_KEYWORDS = [
    "breaking", "just in", "urgent", "explosion", "attack", "killed",
    "earthquake", "flood", "crash", "resignation", "arrested",
    "missile", "blast", "wicket", "century", "hat-trick", "match result",
]
PAKISTAN_KEYWORDS = [
    "islamabad", "karachi", "lahore", "pti", "army", "pm pakistan",
    "pakistan vs", "pak vs", "pcb", "pakistan cricket",
]

# Sports importance keywords — any major global sports event gets +20
SPORTS_IMPORTANCE_KEYWORDS = [
    "world cup final", "champions league", "icc final", "ipl final",
    "psl final", "ashes", "world cup semi", "asia cup final",
    "grand slam", "olympic", "world championship",
]

RSS_SOURCES = [
    # ── Pakistan ──────────────────────────────────────────────────────────
    "https://www.geo.tv/rss/1/0",
    "https://arynews.tv/feed/",
    "https://www.dawn.com/feeds/home",
    "https://tribune.com.pk/feed",
    "https://www.thenews.com.pk/rss/1/1",
    "https://www.samaa.tv/feed/",
    "https://dunyanews.tv/index.php/en?format=feed&type=rss",
    # ── International wire / broadcast ────────────────────────────────────
    "https://feeds.reuters.com/reuters/worldNews",
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://rss.cnn.com/rss/cnn_topstories.rss",
    "https://feeds.foxnews.com/foxnews/world",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://rss.dw.com/rdf/rss-en-world",
    "https://www.france24.com/en/rss",
    "https://www.theguardian.com/world/rss",
    "https://news.yahoo.com/rss/",
    # ── South Asia ────────────────────────────────────────────────────────
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "https://feeds.feedburner.com/ndtvnews-top-stories",
    # ── Sports ────────────────────────────────────────────────────────────
    "https://www.espncricinfo.com/rss/content/story/feeds/0.xml",
    "https://feeds.bbci.co.uk/sport/rss.xml",
    "https://www.skysports.com/rss/12040",
    # ── Google News (topic queries) ───────────────────────────────────────
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=breaking+news&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=pakistan+breaking+news&hl=en&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/search?q=pakistan+cricket&hl=en&gl=PK&ceid=PK:en",
    "https://news.google.com/rss/search?q=world+breaking+news+today&hl=en&gl=US&ceid=US:en",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (BreakingBot/1.0)"}


# ── State I/O ──────────────────────────────────────────────────────────────

def _load_state():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "posted_today":    [],
        "last_post_time":  {"facebook": None, "instagram": None, "telegram": None},
        "posts_this_hour": 0,
        "hour_window_start": None,
    }


def _save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Fetch recent articles (< 15 min) ──────────────────────────────────────

def _fetch_recent(max_age_minutes=15):
    """Return articles published within max_age_minutes, with published_at set."""
    cutoff  = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    results = []
    seen    = set()

    for url in RSS_SOURCES:
        try:
            r    = requests.get(url, headers=HEADERS, timeout=10)
            feed = feedparser.parse(r.text)
        except Exception as e:
            logger.warning(f"Feed fetch failed {url}: {e}")
            continue

        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        for entry in feed.entries:
            if not hasattr(entry, "published_parsed") or not entry.published_parsed:
                continue
            try:
                pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
            if pub_dt < cutoff:
                continue

            link = getattr(entry, "link", None) or ""
            if not link or link in seen:
                continue
            seen.add(link)

            from html import unescape
            import re
            def clean(t):
                t = re.sub(r"<[^>]+>", "", t or "")
                return unescape(re.sub(r"\s+", " ", t)).strip()

            title   = clean(getattr(entry, "title", ""))
            summary = clean(entry.get("summary", title))
            if not title:
                continue

            results.append({
                "title":        title,
                "summary":      summary,
                "url":          link,
                "domain":       domain,
                "published_at": pub_dt.isoformat(),
                "hash":         hashlib.md5(link.encode()).hexdigest(),
            })

    return results


# ── Story-cluster trending: group articles by shared keywords ─────────────

_STOPWORDS = {
    "this", "that", "with", "from", "have", "been", "will", "were", "they",
    "their", "says", "said", "also", "more", "after", "over", "just", "time",
    "news", "world", "year", "first", "last", "most", "into", "when", "what",
    "would", "could", "about", "which", "there", "where", "than", "some",
    "report", "update", "today", "breaking", "latest",
}


def _story_key(title):
    """Extract up to 4 meaningful words as a story signature."""
    words = re.findall(r'\b[a-z]{4,}\b', title.lower())
    key   = [w for w in words if w not in _STOPWORDS][:4]
    return " ".join(sorted(key)) if len(key) >= 2 else ""


def _build_story_clusters(articles):
    """
    Return dict: article_hash → number of unique domains covering the same story.
    'Same story' = 2+ shared meaningful keywords in the title.
    This is true trending detection — not per-domain article count.
    """
    from collections import defaultdict

    sig_domains = defaultdict(set)
    sig_hashes  = defaultdict(list)

    for article in articles:
        sig = _story_key(article.get("title", ""))
        if sig:
            sig_domains[sig].add(article.get("domain", ""))
            sig_hashes[sig].append(article.get("hash", ""))

    clusters = {}
    for sig, hashes in sig_hashes.items():
        domain_count = len(sig_domains[sig])
        for h in hashes:
            clusters[h] = domain_count

    return clusters


# ── Breaking score ────────────────────────────────────────────────────────

def _breaking_score(article, story_clusters=None, source_counts=None):
    score = 0
    text  = (article.get("title", "") + " " + article.get("summary", "")).lower()

    # True trending: how many unique domains cover this same story
    # 5+ domains = massive trend (+50); 3+ = trending (+35); 2 = gaining traction (+20)
    cluster_size = (story_clusters or {}).get(article.get("hash", ""), 1)
    if cluster_size >= 5:
        score += 50
    elif cluster_size >= 3:
        score += 35
    elif cluster_size >= 2:
        score += 20

    # Breaking keyword match: +25
    for kw in BREAKING_KEYWORDS:
        if kw in text:
            score += 25
            break

    # Pakistan keyword: +15
    for kw in PAKISTAN_KEYWORDS:
        if kw in text:
            score += 15
            break

    # Major global sports event: +20
    for kw in SPORTS_IMPORTANCE_KEYWORDS:
        if kw in text:
            score += 20
            break

    # Recency bonus — tiered across the full 120-min window
    pub = article.get("published_at")
    if pub:
        try:
            dt      = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            age_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60
            if age_min < 15:
                score += 20
            elif age_min < 30:
                score += 15
            elif age_min < 45:
                score += 10
        except Exception:
            pass

    return score


# ── Similarity helpers ────────────────────────────────────────────────────

def _embed(text):
    from semantic_filter import embed_article
    return embed_article({"title": text}).tolist()


def _cosine(a, b):
    import numpy as np
    a, b = np.array(a), np.array(b)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _check_posted_similarity(title, posted_today):
    """
    Returns:
      ('duplicate', story)  if similarity > 0.80
      ('update',    story)  if 0.70 <= similarity <= 0.85 and update_count < 2
      ('new',       None)   otherwise
    """
    if not posted_today:
        return "new", None

    try:
        emb = _embed(title)
    except Exception:
        return "new", None

    for story in posted_today:
        stored_emb = story.get("embedding")
        if not stored_emb:
            continue
        sim = _cosine(emb, stored_emb)
        if sim > 0.80:
            return "duplicate", story
        if sim >= 0.70 and story.get("update_count", 0) < 2:
            return "update", story

    return "new", None


def _prune_old_stories(posted_today, max_age_hours=2):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return [
        s for s in posted_today
        if datetime.fromisoformat(s["posted_at"].replace("Z", "+00:00")) > cutoff
    ]


# ── Posts-this-hour check ─────────────────────────────────────────────────

def _can_post_hour(state, max_per_hour=4):
    start_str = state.get("hour_window_start")
    if start_str:
        try:
            start   = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if elapsed > 3600:
                state["posts_this_hour"]   = 0
                state["hour_window_start"] = None
            elif state.get("posts_this_hour", 0) >= max_per_hour:
                return False
        except Exception:
            state["posts_this_hour"]   = 0
            state["hour_window_start"] = None
    return True


def _record_hour_post(state):
    if not state.get("hour_window_start"):
        state["hour_window_start"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state["posts_this_hour"] = state.get("posts_this_hour", 0) + 1


# ── Fast pipeline ─────────────────────────────────────────────────────────

def _run_fast_pipeline(article, caption_prefix="", score=0):
    """
    Skips: semantic_filter, deduplicator (full), scheduler cooldown.
    Runs:  fake_news_filter → intent_classifier → scene_selector →
           pixabay_searcher (1 retry max) → image_composer → publisher.
    Returns list of platforms successfully posted.
    """
    import os
    from groq import Groq

    from fake_news_filter      import score_article as fake_news_score
    from intent_classifier     import classify_and_generate
    from pixabay_searcher      import search_with_clip_validation
    from image_composer        import save_platform_images
    from publisher             import post_to_facebook, post_to_instagram, post_to_telegram
    from db                    import init_db, already_posted, mark_posted

    # Lower trust threshold for breaking news
    trust = fake_news_score(article)
    if trust < 0.30:
        logger.info(f"Breaking trust too low ({trust:.2f}), skipping")
        return []

    groq_client  = Groq(api_key=os.getenv("GROQ_API_KEY"))
    intent_result = classify_and_generate(article, groq_client)
    primary_intent = intent_result["intent"]["primary"]

    # 1 retry max for breaking news speed
    import pixabay_searcher as _ps
    orig_loops = _ps.MAX_RETRY_LOOPS
    _ps.MAX_RETRY_LOOPS = 1

    image_url, best_clip, retry_count, best_image_path = search_with_clip_validation(
        intent_result, article
    )
    _ps.MAX_RETRY_LOOPS = orig_loops

    captions = intent_result["captions"]
    image_headline = (captions.get("image_headline") or article["title"]).strip()

    platform_images = save_platform_images(
        image_url,
        primary_intent,
        image_headline,
        article.get("domain", "Unknown"),
        article.get("published_at"),
        image_path=best_image_path,
    )
    if caption_prefix:
        for p in captions:
            captions[p] = caption_prefix + captions[p]

    # Instagram only for massive trending stories (score >= 80) — daily limit conservation
    post_instagram = score >= 80

    posted = []
    conn   = init_db()
    try:
        if "facebook" in platform_images:
            if post_to_facebook(captions["facebook"], platform_images["facebook"]):
                mark_posted(conn, article["hash"], article["title"], "facebook")
                posted.append("facebook")

        if "instagram" in platform_images and post_instagram:
            if post_to_instagram(captions["instagram"], platform_images["instagram"]):
                mark_posted(conn, article["hash"], article["title"], "instagram")
                posted.append("instagram")

        if "telegram" in platform_images:
            if post_to_telegram(captions["telegram"], platform_images["telegram"]):
                mark_posted(conn, article["hash"], article["title"], "telegram")
                posted.append("telegram")
    finally:
        conn.close()

    for path in platform_images.values():
        try: os.unlink(path)
        except: pass
    if best_image_path:
        try: os.unlink(best_image_path)
        except: pass

    return posted


# ── Admin notification ────────────────────────────────────────────────────

def _notify_admin(article, platforms, score, story_clusters, kind="BREAKING"):
    """
    Send a private Telegram alert so the admin can see exactly what was
    detected, why it triggered, and where it was posted.
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    channel = os.getenv("TELEGRAM_CHANNEL_ID")
    if not token or not channel:
        return

    cluster_size = (story_clusters or {}).get(article.get("hash", ""), 1)
    plat_str     = " + ".join(p.upper() for p in platforms) if platforms else "NONE"
    now_pkt      = datetime.now(PKT).strftime("%I:%M %p PKT")
    title        = article.get("title", "")[:120]
    domain       = article.get("domain", "?")

    if cluster_size >= 5:
        trend_reason = f"Trending hard — {cluster_size} different sources covering it"
    elif cluster_size >= 3:
        trend_reason = f"Trending — {cluster_size} sources covering it"
    elif cluster_size >= 2:
        trend_reason = f"Gaining traction — {cluster_size} sources"
    else:
        trend_reason = "Breaking keyword / sports signal detected"

    msg = (
        f"🚨 {kind} POST ALERT\n\n"
        f"📰 {title}\n"
        f"🌐 Source: {domain}\n\n"
        f"📊 Score: {score}\n"
        f"📡 Why: {trend_reason}\n"
        f"📱 Posted to: {plat_str}\n"
        f"🕒 {now_pkt}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": channel, "text": msg},
            timeout=10,
        )
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────

def run():
    state = _load_state()
    state["posted_today"] = _prune_old_stories(state.get("posted_today", []))

    threshold = SCORE_POST

    articles = _fetch_recent(max_age_minutes=45)
    logger.info(f"Fetched {len(articles)} recent articles (< 45 min)")

    if not articles:
        logger.info("No recent articles — exiting")
        return

    # True trending: count unique domains per story cluster
    story_clusters = _build_story_clusters(articles)

    processed = 0
    for article in articles:
        score = _breaking_score(article, story_clusters=story_clusters)
        logger.info(f"Score={score} | {article['title'][:80]}")

        if score < SCORE_QUEUE:
            continue

        kind, matched_story = _check_posted_similarity(article["title"], state["posted_today"])

        if kind == "duplicate":
            logger.info("  → duplicate, skipping")
            continue

        if kind == "update" and matched_story:
            # Post update if 15 min have passed since matched story was last posted
            last_update = matched_story.get("last_update_at") or matched_story["posted_at"]
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(
                last_update.replace("Z", "+00:00")
            )).total_seconds() / 60
            if elapsed < 15:
                logger.info("  → update too soon, skipping")
                continue
            if not _can_post_hour(state):
                logger.info("  → hourly cap reached")
                break

            logger.info(f"  → posting UPDATE (sim match, {elapsed:.0f} min since last)")
            posted = _run_fast_pipeline(article, caption_prefix="🔄 UPDATE: ", score=score)
            if posted:
                matched_story["update_count"]   = matched_story.get("update_count", 0) + 1
                matched_story["last_update_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                _record_hour_post(state)
                _notify_admin(article, posted, score, story_clusters, kind="UPDATE")
                processed += 1
            continue

        # New breaking story
        if score < threshold:
            logger.info(f"  → score {score} below threshold {threshold}, queuing")
            # Write to queue.json for main pipeline to pick up
            _write_queue(article)
            continue

        if not _can_post_hour(state):
            logger.info("  → hourly cap reached")
            break

        logger.info(f"  → BREAKING (score={score}) — running fast pipeline")
        posted = _run_fast_pipeline(article, score=score)
        if not posted:
            from publisher import send_error_email
            send_error_email(
                "Breaking/Trending Post FAILED",
                f"Detected a breaking/trending story but posting failed on all platforms.\n\n"
                f"📰 Title: {article.get('title', '')[:150]}\n"
                f"🌐 Source: {article.get('domain', '?')}\n"
                f"📊 Score: {score} | Trending domains: "
                f"{(story_clusters or {}).get(article.get('hash', ''), 1)}\n\n"
                f"Check GitHub Actions logs for the full error.",
            )
        if posted:
            try:
                emb = _embed(article["title"])
            except Exception:
                emb = []
            state["posted_today"].append({
                "story_id":      hashlib.md5(article["title"].encode()).hexdigest(),
                "embedding":     emb,
                "posted_at":     datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "breaking_score": score,
                "update_count":  0,
            })
            for p in posted:
                state["last_post_time"][p] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _record_hour_post(state)
            _notify_admin(article, posted, score, story_clusters, kind="BREAKING/TRENDING")
            processed += 1
            break   # one breaking story per 5-min run

    _save_state(state)
    logger.info(f"Breaking detector done — processed {processed} posts")


def _write_queue(article):
    """Append a score-40–59 article to data/queue.json for the main pipeline."""
    queue_file = os.path.join(DATA_DIR, "breaking_queue.json")
    try:
        if os.path.exists(queue_file):
            with open(queue_file) as f:
                q = json.load(f)
        else:
            q = []
        q.append({
            "article":    article,
            "queued_at":  datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        with open(queue_file, "w") as f:
            json.dump(q, f, indent=2)
    except Exception as e:
        logger.warning(f"Queue write failed: {e}")


def check_only():
    """
    Phase-1 pre-check: keyword scoring only — no ML, no heavy imports.
    Prints "true" if a breaking article was found, "false" otherwise.
    Called by breaking_detector.yml before installing full requirements.
    """
    state     = _load_state()
    threshold = SCORE_POST
    articles  = _fetch_recent(max_age_minutes=45)

    story_clusters = _build_story_clusters(articles)

    for article in articles:
        score = _breaking_score(article, story_clusters=story_clusters)
        if score >= threshold:
            logger.info(f"Breaking signal: score={score} | {article['title'][:70]}")
            print("true")
            return

    logger.info("No breaking signal found")
    print("false")


if __name__ == "__main__":
    import sys
    if "--check-only" in sys.argv:
        check_only()
    else:
        run()
