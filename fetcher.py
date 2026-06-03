import feedparser
import hashlib
import re
import requests
from fake_news_filter import _strip_prefixes
from html import unescape
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
DOMAIN_PRIORITY = {
    "reuters.com": 1.0,
    "reutersagency.com": 1.0,   # feeds.reuters.com / reutersagency.com
    "bbc.com": 1.0,
    "bbci.co.uk": 1.0,          # feeds.bbci.co.uk strips to bbci.co.uk
    "aljazeera.com": 0.92,
    "dawn.com": 0.88,
    "theguardian.com": 0.92,
    "france24.com": 0.90,
    "dw.com": 0.92,
    "npr.org": 0.92,
    "geo.tv": 0.82,
    "arynews.tv": 0.80,
}
PAKISTAN_SOURCES = [
    "https://www.geo.tv/rss/1/0",
    "https://arynews.tv/feed/",
    "https://www.dawn.com/feeds/home",
    "https://www.thenews.com.pk/rss/1/1",
    "https://www.samaa.tv/feed",
    "https://tribune.com.pk/feed/",
    "https://www.bbc.com/urdu/index.xml",
]

WORLD_SOURCES = [
    "https://www.reutersagency.com/feed/",
    "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.france24.com/en/rss",
    "https://www.theguardian.com/world/rss",
    "https://www.theguardian.com/international/rss",
    "https://www.independent.co.uk/news/world/rss",
    "https://rss.dw.com/atom/en-all",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.smh.com.au/rss/world.xml",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (NewsBot/1.0)"}


# ---------------- CLEAN ---------------- #

def clean_text(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------- FRESHNESS ---------------- #

def is_fresh(entry, hours=1):
    if not hasattr(entry, "published_parsed") or not entry.published_parsed:
        return True
    try:
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - published) <= timedelta(hours=hours)
    except Exception:
        return True


# ---------------- FETCH FEED ---------------- #

def fetch_feed(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)

        # BASIC VALIDATION — accept RSS, Atom, and plain-XML feeds
        content_type = r.headers.get("Content-Type", "").lower()
        if "xml" not in content_type and "rss" not in content_type:
            text_start = r.text[:500].lower()
            if not any(tag in text_start for tag in ("<rss", "<feed", "<channel", "<?xml")):
                print(f"  ✗ Invalid RSS response: {url}")
                return None

        return feedparser.parse(r.text)

    except requests.Timeout:
        print(f"  ✗ Timeout: {url}")
        return None
    except Exception as e:
        print(f"  ✗ Error {url}: {e}")
        return None


# ---------------- EVENT KEY (IMPORTANT FIX) ---------------- #

def generate_event_key(title, summary):
    text = (title + " " + summary).lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.md5(text.encode()).hexdigest()


# ---------------- MAIN FETCH ---------------- #

def fetch_articles():
    articles = []
    seen_urls = set()

    def process(url, source_type):
        feed = fetch_feed(url)
        if not feed:
            return

        
        domain = _strip_prefixes(urlparse(url).netloc.lower())
        count  = 0

        for entry in feed.entries:
            if not is_fresh(entry):
                continue

            link = getattr(entry, "link", None)
            if not link or link in seen_urls:
                continue

            seen_urls.add(link)

            title = clean_text(getattr(entry, "title", "") or "")
            if not title:
                continue
            summary = clean_text(getattr(entry, "summary", None) or title)

            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(
                        *entry.published_parsed[:6], tzinfo=timezone.utc
                    ).isoformat()
                except Exception:
                    pass

            articles.append({
                "title":        title,
                "summary":      summary,
                "url":          link,
                "source_url":   url,
                "source_type":  source_type,
                "published_at": published_at,
                "event_id":     generate_event_key(title, summary),
                "domain":       domain,
                "hash":         hashlib.md5(link.encode()).hexdigest(),
            })

            count += 1

        print(f"  ✓ {domain} → {count} articles")

    print("Fetching Pakistan sources...")
    for u in PAKISTAN_SOURCES:
        process(u, "pakistan")

    print("Fetching World sources...")
    for u in WORLD_SOURCES:
        process(u, "world")

    print(f"\nTotal fetched: {len(articles)} articles")
    articles.sort(key=lambda a: (
       0 if a["source_type"] == "world" else 1,
       -DOMAIN_PRIORITY.get(a["domain"], 0.5)
    ), reverse=False)
    return articles