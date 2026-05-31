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

# ── Steps 5 & 10: Intent + captions (loads CLIP via generator import) ─────
from generator import clip_score               # loads clip-ViT-B-32
from intent_classifier import classify_and_generate
from virality_scorer import rank_by_virality

# ── Step 6: Topic memory ──────────────────────────────────────────────────
from topic_memory import get_best_intent, mark_intent_posted

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
from publisher import post_to_facebook, post_to_instagram, post_to_telegram
from results_logger import log_result, best_hours
from trend_detector import trending_context_string

# ── Config ────────────────────────────────────────────────────────────────
PKT            = pytz.timezone("Asia/Karachi")
FB_DAILY_LIMIT = 10
IG_DAILY_LIMIT = 45
ARTICLE_CAP    = 30   # hard cap per run (Step 1)
CLASSIFY_TOP   = 10   # classify top-N fresh articles for intent selection


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
        print(f"\nFacebook posts today:  {fb_count}/{FB_DAILY_LIMIT}")
        print(f"Instagram posts today: {ig_count}/{IG_DAILY_LIMIT}")

        # ── ENGAGEMENT TIME PREDICTOR ──────────────────────────────────────
        best_hours()   # prints best PKT hours once enough history exists

        if fb_count >= FB_DAILY_LIMIT:
            print("Facebook daily limit reached — exiting.")
            return

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
            if trust >= 0.40:
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
        fresh = []
        for a in unique:
            if already_posted(conn, a["hash"]):
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
        print(f"  Top virality: {[(a['title'][:40], a['virality_score']) for a in fresh[:3]]}")

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

        # ── STEP 6: TOPIC MEMORY CHECK ─────────────────────────────────────
        _sep()
        print("[STEP 6] TOPIC MEMORY CHECK")
        _sep()
        article, intent_result = get_best_intent(classified)
        primary_intent = intent_result["intent"]["primary"]
        print(f"Selected article: [{primary_intent}] {article['title'][:70]}")

        # ── STEP 7: SCENE TEMPLATE SELECTION ──────────────────────────────
        # (handled inside pixabay_searcher — it calls scene_selector per loop)

        # ── STEP 8: IMAGE SEARCH + CLIP VALIDATION ─────────────────────────
        _sep()
        print("[STEP 8] IMAGE SEARCH + CLIP VALIDATION")
        _sep()
        image_url, best_clip, retry_count, best_image_path = search_with_clip_validation(
            intent_result, article
        )
        print(f"Image selected: CLIP={best_clip:.3f}, retries={retry_count}, file={'ok' if best_image_path else 'NONE'}")
        if not best_image_path:
            print("  WARNING: no image file — dark placeholder will be used")

        # ── STEP 9: IMAGE COMPOSITION ──────────────────────────────────────
        _sep()
        print("[STEP 9] IMAGE COMPOSITION (per platform)")
        _sep()
        captions       = intent_result["captions"]
        image_headline = (captions.get("image_headline") or article["title"]).strip()
        source_display = article.get("domain", "Unknown")
        published_at   = article.get("published_at")

        platform_images = save_platform_images(
            image_url,
            primary_intent,
            image_headline,
            source_display,
            published_at,
            image_path=best_image_path,
        )
        print(f"Images composed: {list(platform_images.keys())}")

        if not platform_images:
            print("Image composition failed for all platforms — aborting.")
            return

        # ── STEP 11: SCHEDULER QUEUE ───────────────────────────────────────
        _sep()
        print("[STEP 11] SCHEDULER QUEUE")
        _sep()
        platforms_ready = get_platforms_ready()
        print(f"Platforms ready: {platforms_ready}")

        if not platforms_ready:
            # If cooldowns expire within 10 minutes, wait rather than discard this run.
            now_utc = datetime.now(timezone.utc)
            max_wait = max(
                max(0, (next_available(p) - now_utc).total_seconds())
                for p in ["facebook", "instagram"]
            )
            if max_wait <= 1200:   # wait up to 20 min; GH Actions timeout is 35 min
                print(f"  Cooldowns expire in {int(max_wait)}s — waiting...")
                time.sleep(max_wait + 5)
                platforms_ready = get_platforms_ready()
            else:
                print(f"  Cooldowns expire in {int(max_wait / 60)}m — queuing for next run.")
                log_result(
                    article_url=article.get("url", ""),
                    intent=primary_intent,
                    clip_score=best_clip,
                    image_url=image_url or "",
                    platforms=[],
                    status="queued",
                    retry_count=retry_count,
                )
                # Images were composed but won't be posted — clean up now
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
                return

        # ── STEP 12: POST + LOG ────────────────────────────────────────────
        _sep()
        print("[STEP 12] POST + LOG")
        _sep()
        posted_platforms = []

        if "facebook" in platforms_ready and "facebook" in platform_images:
            fb_ok = post_to_facebook(captions["facebook"], platform_images["facebook"])
            if fb_ok:
                queue_mark_posted("facebook")
                mark_posted(conn, article["hash"], article["title"], "facebook")
                fb_count += 1
                posted_platforms.append("facebook")
                print(f"  Facebook [FB {fb_count}/{FB_DAILY_LIMIT}] ✔")
            else:
                print("  Facebook failed")

        if ig_count >= IG_DAILY_LIMIT:
            print(f"  Instagram daily limit reached ({ig_count}/{IG_DAILY_LIMIT}) — skipping")
        elif "instagram" in platforms_ready and "instagram" in platform_images:
            ig_ok = post_to_instagram(captions["instagram"], platform_images["instagram"])
            if ig_ok:
                queue_mark_posted("instagram")
                mark_posted(conn, article["hash"], article["title"], "instagram")
                ig_count += 1
                posted_platforms.append("instagram")
                print("  Instagram ✔")
            else:
                print("  Instagram failed")

        if "telegram" in platforms_ready and "telegram" in platform_images:
            tg_ok = post_to_telegram(captions["telegram"], platform_images["telegram"])
            if tg_ok:
                queue_mark_posted("telegram")
                mark_posted(conn, article["hash"], article["title"], "telegram")
                posted_platforms.append("telegram")
                print("  Telegram ✔")
            else:
                print("  Telegram failed")

        # Update topic memory only if at least one platform posted
        if posted_platforms:
            mark_intent_posted(primary_intent)

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
            from publisher import send_error_email
            send_error_email(
                "Scheduled Post FAILED — no platform posted",
                f"The scheduled pipeline selected an article but failed to post it.\n\n"
                f"📰 Title: {article.get('title', '')[:150]}\n"
                f"🏷️  Intent: {primary_intent}\n"
                f"📊 CLIP score: {best_clip:.3f}\n\n"
                f"Check GitHub Actions logs for the full error.",
            )

        # Cleanup temp image files only on success; keep on failure for artifact upload
        if posted_platforms:
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

        # ── Summary ────────────────────────────────────────────────────────
        _sep("═")
        print(f"STATUS:    {status.upper()}")
        print(f"POSTED TO: {posted_platforms}")
        print(f"INTENT:    {primary_intent}")
        print(f"VIRALITY:  {article.get('virality_score', 'n/a')}/100")
        print(f"CLIP:      {best_clip:.3f}")
        print(f"FB COUNT:  {fb_count}/{FB_DAILY_LIMIT}")
        print(f"IG COUNT:  {ig_count}/{IG_DAILY_LIMIT}")
        print(f"END:       {datetime.now(PKT).strftime('%I:%M %p PKT')}")
        _sep("═")

    finally:
        conn.close()


if __name__ == "__main__":
    run_pipeline()
