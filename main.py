import os
import sys
import time
import pytz
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── DB / infra (import order matters for shared model singletons) ──────────
from db import init_db, already_posted, title_already_posted, mark_posted, get_today_count

# ── Step 1: Fetch ─────────────────────────────────────────────────────────
from fetcher import fetch_articles

# ── Step 2: Fake news filter ──────────────────────────────────────────────
from fake_news_filter import score_article as fake_news_score

# ── Steps 3 & 4: Semantic filter + dedup (MiniLM model loaded here) ───────
from deduplicator import deduplicate            # loads all-MiniLM-L6-v2
from semantic_filter import embed_article, passes_semantic_filter

# ── Steps 5 & 10: Intent + captions ──────────────────────────────────────
from intent_classifier import classify_and_generate
from virality_scorer import rank_by_virality

# ── Step 6: Topic memory ──────────────────────────────────────────────────
from topic_memory import get_best_intent, get_ordered_intents, mark_intent_posted

# ── Steps 7 & 8: Scene selection + image search ───────────────────────────
from pixabay_searcher import search_with_clip_validation

# ── Step 9: Image composition ─────────────────────────────────────────────
from image_composer import save_platform_images

# ── Step 11: Scheduler queue ──────────────────────────────────────────────
from scheduler_queue import (
    get_platforms_ready,
    mark_posted as queue_mark_posted,
    next_available,
)

# ── Step 12: Post + log ───────────────────────────────────────────────────
from publisher import post_to_facebook, post_to_instagram, post_to_telegram, send_error_email
from results_logger import log_result, best_hours
from trend_detector import trending_context_string

# ── Config ────────────────────────────────────────────────────────────────
PKT            = pytz.timezone("Asia/Karachi")
FB_DAILY_LIMIT = 9999   # no limit
IG_DAILY_LIMIT = 45
TG_DAILY_LIMIT = 30
ARTICLE_CAP    = 100   # hard cap per run (Step 1)
CLASSIFY_TOP   = 10   # classify top-N fresh articles for intent selection
MAX_PER_RUN    = 5    # max posts per pipeline run
FB_QUIET_START = 0    # FB quiet hours: 12 AM PKT (hour 0)
FB_QUIET_END   = 5    # FB quiet hours end: 5 AM PKT (hour 5)


def _sep(char="─", width=60):
    print(char * width)


def run_pipeline():
    now = datetime.now(PKT)
    print()
    _sep("═")
    print(f"PIPELINE START: {now.strftime('%d %b %Y %I:%M %p PKT')}")
    _sep("═")

    conn = init_db()

    try:
        fb_count = get_today_count(conn, "facebook")
        ig_count = get_today_count(conn, "instagram")
        tg_count = get_today_count(conn, "telegram")
        print(f"\nFacebook posts today:  {fb_count}/{FB_DAILY_LIMIT}")
        print(f"Instagram posts today: {ig_count}/{IG_DAILY_LIMIT}")
        print(f"Telegram posts today:  {tg_count}/{TG_DAILY_LIMIT}")

        # ── ENGAGEMENT TIME PREDICTOR ──────────────────────────────────────
        best_hours()   # prints best PKT hours once enough history exists

        if fb_count >= FB_DAILY_LIMIT:
            print(f"Facebook daily limit reached ({fb_count}/{FB_DAILY_LIMIT}) — skipping Facebook only.")

        # ── STEP 1: FETCH ──────────────────────────────────────────────────
        _sep()
        print("[STEP 1] FETCH")
        _sep()
        articles = fetch_articles()[:ARTICLE_CAP]
        print(f"Fetched {len(articles)} articles (cap={ARTICLE_CAP})")
        if not articles:
            print("No articles found.")
            return

        # ── TRENDING KEYWORD DETECTION ─────────────────────────────────────
        trending_ctx = trending_context_string(articles)
        if trending_ctx:
            print(f"  {trending_ctx}")

        # ── STEP 2: FAKE NEWS FILTER ───────────────────────────────────────
        _sep()
        print("[STEP 2] FAKE NEWS FILTER")
        _sep()
        trusted = []
        for a in articles:
            trust = fake_news_score(a)
            if trust >= 0.80:
                a["trust_score"] = trust
                trusted.append(a)
            else:
                print(f"  REJECT trust={trust:.2f}: {a['title'][:70]}")
        print(f"Passed: {len(trusted)}/{len(articles)}")
        if not trusted:
            return

        # ── STEP 3: SEMANTIC EMBEDDING FILTER ─────────────────────────────
        _sep()
        print("[STEP 3] SEMANTIC EMBEDDING FILTER")
        _sep()
        relevant = []
        for a in trusted:
            emb = embed_article(a)
            ok, reason = passes_semantic_filter(emb)
            if ok:
                a["_embedding"] = emb
                relevant.append(a)
            else:
                print(f"  REJECT {reason}: {a['title'][:70]}")
        print(f"Passed: {len(relevant)}/{len(trusted)}")
        if not relevant:
            return

        # ── STEP 4: DUPLICATE CLUSTERING ──────────────────────────────────
        _sep()
        print("[STEP 4] DUPLICATE CLUSTERING (threshold=0.85)")
        _sep()
        unique = deduplicate(relevant, threshold=0.85)

        # Remove already-posted articles
        # An article is skipped only when every platform has received it;
        # if even one platform missed it, keep it so that platform can retry.
        _ALL_PLATFORMS = ("facebook", "instagram", "telegram")
        fresh = []
        for a in unique:
            if all(already_posted(conn, a["hash"], p) for p in _ALL_PLATFORMS):
                continue
            if title_already_posted(conn, a["title"]):
                continue
            fresh.append(a)
        print(f"Fresh unique stories: {len(fresh)}")
        if not fresh:
            print("All articles already posted.")
            return

        # ── VIRALITY RANKING ───────────────────────────────────────────────
        fresh = rank_by_virality(fresh)
        if fresh and "virality_score" not in fresh[0]:
            print("  WARNING: virality_score key missing — rank_by_virality may have failed")
        else:
            print(f"  Top virality: {[(a['title'][:40], a.get('virality_score', 'n/a')) for a in fresh[:3]]}")

        # ── STEP 5: INTENT CLASSIFICATION + CAPTION GENERATION ────────────
        _sep()
        print(f"[STEP 5] INTENT CLASSIFICATION + CAPTIONS (top {CLASSIFY_TOP} articles)")
        _sep()
        classified = []
        for a in fresh[:CLASSIFY_TOP]:
            print(f"  → {a['title'][:70]}")
            result = classify_and_generate(a, trending_context=trending_ctx)
            primary   = result["intent"]["primary"]
            top_score = max(
                (i["score"] for i in result["intent"]["intents"] if i["label"] == primary),
                default=0.0,
            )
            ambiguous = result["intent"].get("ambiguous", False)
            print(f"     intent={primary} ({top_score:.2f}){' [ambiguous]' if ambiguous else ''}")
            classified.append((a, result))

        if not classified:
            return

        # ── STEP 6: ORDER ALL ARTICLES BY INTENT PRIORITY ─────────────────
        _sep()
        print(f"[STEP 6] ORDERING {len(classified)} ARTICLES BY INTENT PRIORITY")
        _sep()
        ordered = get_ordered_intents(classified)
        for i, (a, r) in enumerate(ordered):
            print(f"  {i+1}. [{r['intent']['primary']}] {a['title'][:65]}")

        # ── ONE-TIME COOLDOWN CHECK before the loop ────────────────────────
        _sep()
        print("[STEP 11] SCHEDULER QUEUE (pre-check)")
        _sep()

        top_virality = max((a.get("virality_score", 0) for a in fresh), default=0)
        has_high_virality = top_virality > 85

        def _apply_limits(pl):
            if fb_count >= FB_DAILY_LIMIT:
                pl = [p for p in pl if p != "facebook"]
            if ig_count >= IG_DAILY_LIMIT:
                pl = [p for p in pl if p != "instagram"]
            if tg_count >= TG_DAILY_LIMIT:
                pl = [p for p in pl if p != "telegram"]
            # Facebook quiet hours 12 AM–5 AM PKT — bypassed for high-virality stories
            if FB_QUIET_START <= datetime.now(PKT).hour < FB_QUIET_END:
                if has_high_virality:
                    print(f"  High-virality ({top_virality}) — bypassing FB quiet hours in pre-check")
                else:
                    pl = [p for p in pl if p != "facebook"]
                    print(f"  Facebook quiet hours ({FB_QUIET_START}AM–{FB_QUIET_END}AM PKT) — skipping FB")
            return pl

        platforms_ready = _apply_limits(get_platforms_ready())

        if not platforms_ready:
            now_utc  = datetime.now(timezone.utc)
            max_wait = max(
                max(0, (next_available(p) - now_utc).total_seconds())
                for p in ["facebook", "instagram", "telegram"]
            )
            if max_wait <= 1200:
                print(f"  Cooldowns expire in {int(max_wait)}s — waiting...")
                time.sleep(max_wait + 5)
                platforms_ready = _apply_limits(get_platforms_ready())
            else:
                print(f"  Cooldowns expire in {int(max_wait / 60)}m — skipping run.")
                return

        print(f"Platforms ready: {platforms_ready}")
        if not platforms_ready:
            print("No platforms available — exiting.")
            return

        # ── STEPS 8-12 LOOP: post up to MAX_PER_RUN articles ──────────────
        _sep()
        print(f"[STEP 8–12] MULTI-POST LOOP (max {MAX_PER_RUN} per run)")
        _sep()
        posts_this_run = 0
        _ALL_PLATFORMS = ["facebook", "instagram", "telegram"]

        def _inrun_platforms(virality=0):
            """Within a run — skip cooldowns, only check daily limits + quiet hours.
            High-virality articles (score > 85) bypass FB quiet hours."""
            pl = list(_ALL_PLATFORMS)
            if fb_count >= FB_DAILY_LIMIT:
                pl = [p for p in pl if p != "facebook"]
            if ig_count >= IG_DAILY_LIMIT:
                pl = [p for p in pl if p != "instagram"]
            if tg_count >= TG_DAILY_LIMIT:
                pl = [p for p in pl if p != "telegram"]
            if FB_QUIET_START <= datetime.now(PKT).hour < FB_QUIET_END:
                if virality > 85:
                    print(f"  High-virality ({virality}) — bypassing FB quiet hours")
                else:
                    pl = [p for p in pl if p != "facebook"]
            return pl

        for article, intent_result in ordered:
            if posts_this_run >= MAX_PER_RUN:
                break

            # Inside loop: only check limits + quiet hours — NOT cooldowns
            platforms_ready = _inrun_platforms(virality=article.get("virality_score", 0))
            if not platforms_ready:
                print(f"  No platforms available — stopping loop at post {posts_this_run}")
                break

            primary_intent = intent_result["intent"]["primary"]
            print(f"\n  [{posts_this_run + 1}/{MAX_PER_RUN}] {primary_intent}: {article['title'][:60]}")

            # ── IMAGE SEARCH ──────────────────────────────────────────────
            image_url, best_clip, retry_count, best_image_path = search_with_clip_validation(
                intent_result, article
            )
            print(f"    CLIP={best_clip:.3f} retries={retry_count}")

            # ── IMAGE COMPOSITION ─────────────────────────────────────────
            captions       = intent_result["captions"]
            image_headline = (captions.get("image_headline") or article["title"]).strip()
            image_subtext  = captions.get("image_subtext", "")
            platform_images = save_platform_images(
                image_url,
                primary_intent,
                image_headline,
                article.get("domain", "Unknown"),
                article.get("published_at"),
                image_path=best_image_path,
                image_subtext=image_subtext,
            )

            if not platform_images:
                print("    Image composition failed — skipping article")
                continue

            # ── POST ──────────────────────────────────────────────────────
            posted_platforms = []

            if "facebook" in platforms_ready and "facebook" in platform_images:
                if already_posted(conn, article["hash"], "facebook"):
                    print("    Facebook already posted (another pipeline) — skipping")
                else:
                    fb_ok = post_to_facebook(captions["facebook"], platform_images["facebook"])
                    if fb_ok:
                        queue_mark_posted("facebook")
                        mark_posted(conn, article["hash"], article["title"], "facebook")
                        fb_count += 1
                        posted_platforms.append("facebook")
                        print(f"    Facebook ✔ [FB {fb_count}/{FB_DAILY_LIMIT}]")
                    else:
                        print("    Facebook failed")

            if "instagram" in platforms_ready and "instagram" in platform_images:
                if already_posted(conn, article["hash"], "instagram"):
                    print("    Instagram already posted (another pipeline) — skipping")
                else:
                    ig_ok = post_to_instagram(captions["instagram"], platform_images["instagram"])
                    if ig_ok:
                        queue_mark_posted("instagram")
                        mark_posted(conn, article["hash"], article["title"], "instagram")
                        ig_count += 1
                        posted_platforms.append("instagram")
                        print(f"    Instagram ✔ [IG {ig_count}/{IG_DAILY_LIMIT}]")
                    else:
                        print("    Instagram failed")

            if "telegram" in platforms_ready and "telegram" in platform_images:
                if already_posted(conn, article["hash"], "telegram"):
                    print("    Telegram already posted (another pipeline) — skipping")
                else:
                    tg_ok = post_to_telegram(captions["telegram"], platform_images["telegram"])
                    if tg_ok:
                        queue_mark_posted("telegram")
                        mark_posted(conn, article["hash"], article["title"], "telegram")
                        tg_count += 1
                        posted_platforms.append("telegram")
                        print(f"    Telegram ✔ [TG {tg_count}/{TG_DAILY_LIMIT}]")
                    else:
                        print("    Telegram failed")

            # ── LOG + TOPIC MEMORY ────────────────────────────────────────
            if posted_platforms:
                mark_intent_posted(primary_intent)
                posts_this_run += 1

            status = "success" if posted_platforms else "failed"
            log_result(
                article_url=article.get("url", ""),
                intent=primary_intent,
                clip_score=best_clip,
                image_url=image_url or "",
                platforms=posted_platforms,
                status=status,
                retry_count=retry_count,
            )

            if status == "failed":
                send_error_email(
                    "Scheduled Post FAILED — no platform posted",
                    f"📰 Title: {article.get('title', '')[:150]}\n"
                    f"🏷️  Intent: {primary_intent}\n"
                    f"📊 CLIP: {best_clip:.3f}\n\n"
                    f"Check GitHub Actions logs for the full error.",
                )

            # ── CLEANUP ───────────────────────────────────────────────────
            for path in platform_images.values():
                try:
                    os.unlink(path)
                except Exception:
                    pass
            try:
                if best_image_path and os.path.exists(best_image_path):
                    os.unlink(best_image_path)
            except Exception:
                pass

        # ── FINAL SUMMARY ──────────────────────────────────────────────────
        _sep("═")
        print(f"RUN COMPLETE: {posts_this_run} post(s) published")
        print(f"FB COUNT:  {fb_count}/{FB_DAILY_LIMIT}")
        print(f"IG COUNT:  {ig_count}/{IG_DAILY_LIMIT}")
        print(f"TG COUNT:  {tg_count}/{TG_DAILY_LIMIT}")
        print(f"END:       {datetime.now(PKT).strftime('%I:%M %p PKT')}")
        _sep("═")

    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()