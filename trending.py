import time
import requests
from collections import Counter


# ─────────────────────────────────────────────
# MAIN TREND ENGINE
# ─────────────────────────────────────────────

def get_trending_topics():

    trending = []
    scores = Counter()

    # ───────────── METHOD 1: PYTRENDS (SAFE) ─────────────
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(
            hl="en-US",
            tz=300,
            timeout=(5, 10)
        )

        # safer region handling
        regions = ["pakistan", "united_states"]

        for region in regions:
            try:
                data = pytrends.trending_searches(pn=region)

                if data is not None and len(data) > 0:
                    items = data[0].tolist()[:8]
                    trending.extend(items)

                time.sleep(2)  # safer delay

            except Exception:
                continue

    except Exception as e:
        print(f"  pytrends unavailable: {e}")


    # ───────────── METHOD 2: RSS INTELLIGENCE ─────────────
    try:
        rss_trends = _get_rss_trending()
        trending.extend(rss_trends)
        print(f"  RSS trends found: {len(rss_trends)}")

    except Exception as e:
        print(f"  RSS error: {e}")


    # ───────────── METHOD 3: FALLBACK GLOBAL CORE ─────────
    if not trending:
        trending = [
            "pakistan economy", "imf loan", "gaza war",
            "russia ukraine war", "china us tension",
            "inflation crisis", "election results",
            "army operation", "flood disaster"
        ]
        print("  Using fallback trends")


    # ───────────── CLEANING + NORMALIZATION ─────────────
    cleaned = []

    for t in trending:
        if not t:
            continue

        t = t.lower().strip()

        # remove noise words
        noise = {
            "the", "a", "an", "breaking", "news",
            "update", "latest", "live"
        }

        words = [
            w for w in t.split()
            if w not in noise and len(w) > 2
        ]

        if words:
            cleaned.append(" ".join(words))


    # ───────────── SCORING SYSTEM (IMPORTANT FIX) ────────
    for item in cleaned:
        scores[item] += 1


    # boost multi-source overlap
    final_trends = [
        topic for topic, count in scores.items()
        if count >= 2 or len(topic.split()) >= 2
    ]


    print(f"  Total trending topics: {len(final_trends)}")

    return final_trends


# ─────────────────────────────────────────────
# RSS TREND ENGINE (IMPROVED VERSION)
# ─────────────────────────────────────────────

def _get_rss_trending():

    import feedparser

    SOURCES = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://feeds.reuters.com/reuters/topNews",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ]

    word_count = Counter()

    SKIP = {
        "the","and","for","with","that","this","from","have",
        "has","was","were","are","will","said","says","into",
        "after","over","more","new","out","about"
    }

    for url in SOURCES:

        try:
            r = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            feed = feedparser.parse(r.text)

            for entry in feed.entries[:20]:

                title = entry.get("title", "").lower()

                # phrase-level capture (IMPORTANT FIX)
                phrases = [
                    title,
                    " ".join(title.split()[:2]),
                    " ".join(title.split()[:3])
                ]

                for phrase in phrases:

                    words = phrase.split()

                    for w in words:
                        w = w.strip(".,!?\"'()[]{}")

                        if w and w not in SKIP and len(w) > 3:
                            word_count[w] += 1

        except Exception:
            continue


    # strong filter
    return [
        word for word, count in word_count.items()
        if count >= 3
    ]