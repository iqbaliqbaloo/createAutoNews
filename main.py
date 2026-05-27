import os
import sys
import pytz
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# UTF-8 safe output (GitHub Actions fix)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db import (
    init_db,
    already_posted,
    title_already_posted,
    mark_posted,
    get_today_count
)

from fetcher import fetch_articles
from deduplicator import deduplicate
from scorer import score_article
from generator import generate_post, generate_image
from publisher import post_to_facebook, post_to_instagram
from trending import get_trending_topics


PKT = pytz.timezone("Asia/Karachi")

FB_DAILY_LIMIT = 10
POST_DELAY_SECONDS = 60   # 🔥 FIX: prevent burst posting


def run_pipeline():

    now = datetime.now(PKT)

    print("\n" + "=" * 60)
    print(f"PIPELINE START: {now.strftime('%d %b %Y %I:%M %p PKT')}")
    print("=" * 60)

    # ---------------- TRENDING ---------------- #
    print("\nFetching trending topics...")
    trending_topics = get_trending_topics()

    # ---------------- DB INIT ---------------- #
    conn = init_db()

    try:
        fb_count = get_today_count(conn, "facebook")
        print(f"\nFacebook today: {fb_count}/{FB_DAILY_LIMIT}")

        if fb_count >= FB_DAILY_LIMIT:
            print("Daily limit reached. Exiting.")
            return

        # ---------------- FETCH ---------------- #
        articles = fetch_articles()

        if not articles:
            print("No articles found.")
            return

        # ---------------- DEDUP ---------------- #
        merged = deduplicate(articles)
        print(f"Unique stories: {len(merged)}")

        # ---------------- FILTER + SCORE ---------------- #
        fresh = []

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
            fresh.append(a)

        fresh.sort(key=lambda x: x["score"], reverse=True)

        print(f"\nQualified articles: {len(fresh)}")

        if not fresh:
            print("No strong articles found.")
            return

        # ---------------- POST LOOP ---------------- #
        for article in fresh:

            if fb_count >= FB_DAILY_LIMIT:
                break

            print("\n" + "-" * 60)
            print(f"Processing: {article['title']}")
            print(f"Score: {article['score']} | Level: {article['level']}")

            # ---------- TEXT GENERATION ---------- #
            content = generate_post(article)

            if not content:
                print("❌ Post generation failed")
                continue

            print("Post generated ✔")

            # ---------- IMAGE GENERATION ---------- #
            image_path = None

            try:
                image_path = generate_image(
                    content["image_keywords"],
                    content.get("image_headline", article["title"]),
                    article["source_type"],
                    article["level"] == 1
                )
            except Exception as e:
                print(f"Image error: {e}")

            if not image_path:
                print("❌ Image failed")
                continue

            # ---------- FACEBOOK POST ---------- #
            fb_result = post_to_facebook(content["post_text"], image_path)

            if fb_result is None:
                print("❌ Fatal FB error (token issue)")
                return

            if fb_result:

                mark_posted(conn, article["hash"], article["title"], "facebook")
                fb_count += 1

                print(f"[FB {fb_count}/{FB_DAILY_LIMIT}] Posted ✔")

                # ---------- INSTAGRAM ---------- #
                ig_result = post_to_instagram(content["post_text"], image_path)

                if ig_result:
                    mark_posted(conn, article["hash"], article["title"], "instagram")
                    print("[IG] Posted ✔")

                # ---------- IMPORTANT FIX: delay between posts ----------
                if fb_count < FB_DAILY_LIMIT:
                    print(f"Sleeping {POST_DELAY_SECONDS}s before next post...")
                    time.sleep(POST_DELAY_SECONDS)

                break  # important: prevents multiple posts per run

            else:
                print("FB failed, trying next article...")

            # cleanup image
            try:
                os.unlink(image_path)
            except:
                pass

        # ---------------- SUMMARY ---------------- #
        print("\n" + "=" * 60)
        print(f"FINAL FB COUNT: {fb_count}/{FB_DAILY_LIMIT}")
        print(f"END TIME: {datetime.now(PKT).strftime('%I:%M %p PKT')}")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()