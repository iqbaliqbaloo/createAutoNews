import os
import sys
import pytz
from datetime import datetime
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

load_dotenv()

from db           import init_db, already_posted, title_already_posted, mark_posted, get_today_count
from fetcher      import fetch_articles
from deduplicator import deduplicate
from scorer       import score_article
from generator    import generate_post, generate_image
from publisher    import post_to_facebook, post_to_instagram
from trending     import get_trending_topics

PKT            = pytz.timezone("Asia/Karachi")
FB_DAILY_LIMIT = 10
MIN_SCORE      = 40   # 🔥 IMPORTANT FIX


def run_pipeline():

    now = datetime.now(PKT)
    print("\n" + "=" * 50)
    print(f"Pipeline started: {now.strftime('%d %b %Y %I:%M %p PKT')}")
    print("=" * 50)

    print("\nFetching trending topics...")
    trending_topics = get_trending_topics()

    conn = init_db()

    try:

        fb_count = get_today_count(conn, "facebook")
        print(f"FB: {fb_count}/{FB_DAILY_LIMIT}")

        if fb_count >= FB_DAILY_LIMIT:
            print("Daily FB limit reached. Stopping.")
            return

        articles = fetch_articles()

        if not articles:
            print("No articles fetched.")
            return

        merged = deduplicate(articles)

        fresh = []

        # ───────────── FILTER STAGE ─────────────
        for a in merged:

            if already_posted(conn, a["hash"]):
                continue

            if title_already_posted(conn, a["title"]):
                continue

            score, level = score_article(a, trending_topics)

            if level == 5:
                continue

            a["score"] = score
            a["level"] = level

            if score >= MIN_SCORE:   # 🔥 FIXED FILTER
                fresh.append(a)

        fresh.sort(key=lambda x: x["score"], reverse=True)

        print(f"Qualified articles: {len(fresh)}")

        if not fresh:
            print("No important articles found.")
            return

        # ───────────── POST LOOP ─────────────
        for article in fresh:

            if fb_count >= FB_DAILY_LIMIT:
                break

            print("\nProcessing:", article["title"])
            print(f"Score: {article['score']} | Type: {article['source_type']}")

            # ───── AI GENERATION ─────
            content = generate_post(article)

            if not content:
                print("AI failed → skipping article")
                continue

            print("Post:", content.get("post_text", "")[:100])

            # ───── IMAGE GENERATION ─────
            image_path = None

            try:
                image_path = generate_image(
                    content["image_keywords"],
                    content.get("image_headline", article["title"]),
                    article["source_type"],
                    article.get("level", 3) == 1
                )
            except Exception as e:
                print("Image error:", e)

            # 🔥 FIX: TEXT-ONLY fallback
            if not image_path:
                print("No image → posting text only")

                fb_result = post_to_facebook(content["post_text"])

            else:
                fb_result = post_to_facebook(content["post_text"], image_path)

            # ───── FACEBOOK RESULT ─────
            if fb_result is None:
                print("Fatal FB error → stopping pipeline")
                return

            if fb_result:

                mark_posted(conn, article["hash"], article["title"], "facebook")
                fb_count += 1

                print(f"[FB {fb_count}/{FB_DAILY_LIMIT}] Posted ✅")

                # ───── INSTAGRAM ─────
                ig_result = post_to_instagram(content["post_text"], image_path)

                if ig_result:
                    mark_posted(conn, article["hash"], article["title"], "instagram")
                    print("[IG] Posted ✅")

            else:
                print("FB failed → continuing next article")

        # ───────────── SUMMARY ─────────────
        print("\n" + "=" * 50)
        print(f"Facebook: {fb_count}/{FB_DAILY_LIMIT}")
        print(f"Finished: {datetime.now(PKT).strftime('%I:%M %p PKT')}")
        print("=" * 50)

    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()