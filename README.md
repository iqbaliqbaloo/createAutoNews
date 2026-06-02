# VisionaryMinds News Autoposter

An automated, multi-pipeline news system that fetches breaking world and Pakistan news, filters it with AI, composes branded platform images, and posts to **Facebook**, **Instagram**, and **Telegram** via GitHub Actions — fully hands-free.

---

## Architecture — Three Pipelines

| Pipeline | Workflow | Schedule | Purpose |
|----------|----------|----------|---------|
| **A — Main** | `post.yml` | Every 4 hours | Fetches, filters, classifies, and posts one high-quality story per run |
| **B — Breaking** | `breaking_detector.yml` | Every 5 minutes | Scans last 15 minutes of RSS; fast-posts anything above breaking threshold |
| **C — Sports** | `sports_tracker.yml` | Every 30 minutes | Tracks live cricket and football matches; posts score updates and results |

All three pipelines share the same publisher, image composer, and CLIP validator.

---

## Pipeline A — 13-Step Flow

```
FETCH → TRENDING DETECTION → FAKE NEWS FILTER → SEMANTIC FILTER → DEDUP
    → VIRALITY RANKING → INTENT + CAPTIONS → TOPIC MEMORY → SCENE SELECTION
    → IMAGE SEARCH + CLIP → IMAGE COMPOSE → SCHEDULER → POST → LOG
```

| Step | Module | What it does |
|------|--------|--------------|
| 1 | `fetcher.py` | Pulls up to 100 fresh articles (≤ 8 h old) from 20 RSS feeds; sorted world-first by domain priority |
| 2 | `trend_detector.py` | Counts word frequency across all fetched articles; identifies trending topics for hashtag injection |
| 3 | `fake_news_filter.py` | Domain trust scoring (5-tier, 60+ domains) + clickbait penalty + caps penalty; rejects trust score < 0.40 |
| 4 | `semantic_filter.py` | MiniLM embedding; rejects celebrity gossip, lifestyle, ads |
| 5 | `deduplicator.py` | Cosine clustering (≥ 0.85); keeps highest-trust article per cluster; checks DB for already-posted |
| 6 | `virality_scorer.py` | Pure-Python scorer (0–100): recency, emotional intensity, Pakistan relevance, title characteristics; re-ranks articles before classification |
| 7 | `intent_classifier.py` | Single Groq LLaMA-3.3-70B call: 5-class intent score + Facebook / Instagram / Telegram captions; injects trending context |
| 7a | `caption_scorer.py` | Scores FB caption 0–100; triggers one Groq regeneration attempt if score < 55; trims all captions to optimal word counts |
| 8 | `topic_memory.py` | Enforces 2-hour cooldown per intent; avoids consecutive same-intent posts; picks freshest diverse article |
| 9 | `scene_selector.py` | Maps intent → Pixabay keyword tiers (article-specific → primary → secondary → tertiary → broad fallback) |
| 10 | `pixabay_searcher.py` | Searches Pixabay (falls back to Pexels, then local library); validates each image with CLIP (threshold 0.27); permanently blacklists used images |
| 11 | `image_composer.py` | Builds a separate branded image per platform with correct canvas, gradient overlays, logo, and intent-coloured tag |
| 12 | `scheduler_queue.py` | Checks per-platform cooldowns; waits up to 20 min if cooldown expires soon |
| 13 | `publisher.py` + `results_logger.py` | Posts to all ready platforms; logs result to `data/results.json`; sends Gmail alert on total failure |

---

## Posting Architecture — Make.com as Intermediary

Facebook and Instagram are posted **indirectly through Make.com** webhooks. The pipeline sends a JSON payload; Make.com uses its own approved Meta app to publish, bypassing the need for developer review.

```
GitHub Actions
    └─► ImgBB (permanent image URL)
    └─► Make.com Webhook (primary MAKE_WEBHOOK_URL)
            └─► fallback: MAKE_WEBHOOK_URL_1  (if primary quota exhausted)
                    └─► Facebook Page
                    └─► Instagram Business Account

    └─► Telegram Bot API  (direct — no intermediary)
```

Images are uploaded to ImgBB first (permanent, no expiry) so Make.com can fetch the URL at any time.

---

## Output Images

A separate branded image is composed for each active platform:

| Platform | Canvas | Headline size | Status |
|----------|--------|---------------|--------|
| Facebook | 1200 × 630 px | 52 px bold | Active |
| Instagram | 1080 × 1080 px | 60 px bold | Active |
| Telegram | 1280 × 720 px | 54 px bold | Active |
| Twitter / X | 1200 × 675 px | 46 px bold | Commented out in `image_composer.py` |

**Intent tag colours**

| Intent | Tag colour |
|--------|------------|
| WAR | Red `#CC2936` |
| POLITICS | Blue `#1A56DB` |
| ECONOMY | Green `#057A55` |
| DISASTER | Orange `#D03801` |
| SPORTS | Purple `#6C2BD9` |

Sports pipelines use league-specific colours: PSL `#006341`, IPL `#004BA0`, UCL `#001D3D`, EPL `#38003C`.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

Requires Python 3.11+. On Linux, also install system fonts:

```bash
sudo apt-get install fonts-dejavu fonts-liberation
```

### 3. Create `.env`

```env
# LLM — intent classification + caption generation (key 2 is fallback)
GROQ_API_KEY=your_primary_groq_key
GROQ_API_KEY_2=your_backup_groq_key

# Make.com webhooks — FB and IG posting (key 2 used when primary quota runs out)
MAKE_WEBHOOK_URL=https://hook.eu2.make.com/your-primary-webhook
MAKE_WEBHOOK_URL_1=https://hook.eu2.make.com/your-fallback-webhook

# Image search
PIXABAY_API_KEY=your_pixabay_key
PEXELS_API_KEY=your_pexels_key          # used as Pixabay fallback

# Image hosting (permanent URL passed to Make.com)
IMGBB_API_KEY=your_imgbb_key

# Telegram (direct Bot API)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@your_channel_or_chat_id

# Error notifications via Gmail SMTP
GMAIL_USER=your_gmail_address@gmail.com
GMAIL_APP_PASSWORD=your_gmail_app_password   # 16-char App Password, not account password
NOTIFY_EMAIL=recipient@example.com           # optional; defaults to GMAIL_USER
```

### 4. Run locally

```bash
python main.py
```

---

## GitHub Actions — Required Secrets

Add each key under **Settings → Secrets and variables → Actions**:

```
GROQ_API_KEY          GROQ_API_KEY_2
MAKE_WEBHOOK_URL      MAKE_WEBHOOK_URL_1
PIXABAY_API_KEY       PEXELS_API_KEY
IMGBB_API_KEY
TELEGRAM_BOT_TOKEN    TELEGRAM_CHANNEL_ID
GMAIL_USER            GMAIL_APP_PASSWORD    NOTIFY_EMAIL
```

The workflow caches HuggingFace model weights, the SQLite post-history database, and all `data/` state files between runs so each run starts warm.

**On total pipeline failure** (all platforms fail to post) a Gmail alert is sent automatically via SMTP.

---

## News Sources

**Pakistan** — Geo.tv, ARY News, Dawn, The News, Samaa TV, Tribune, BBC Urdu

**World** — Reuters, BBC, Al Jazeera, France 24, The Guardian, The Independent, Deutsche Welle, Sky News, NPR, Sydney Morning Herald

---

## Data Files

All runtime state is written to `data/` (created automatically on first run, persisted via GitHub Actions cache):

| File | Purpose |
|------|---------|
| `data/topic_memory.json` | Last post timestamp per intent — enforces 2-hour intent cooldown and consecutive-intent diversity |
| `data/queue.json` | Last post timestamp per platform — enforces per-platform cooldowns |
| `data/results.json` | Rolling log of last 500 post attempts (intent, CLIP score, virality score, image URL, platforms, status) |
| `data/image_cache.json` | Pixabay/Pexels URL cache (6-hour TTL) — reduces API calls |
| `data/used_images.json` | Permanently blacklisted image URLs — images are never reused once posted |
| `data/rate_limit.json` | Pixabay hourly call counter — switches to Pexels when limit approached |
| `data/breaking_state.json` | Pipeline B state: posted stories, hourly post count, cooldowns |
| `data/sports_state.json` | Pipeline C state: active matches, scores, post history |

---

## Limits and Thresholds

| Rule | Value |
|------|-------|
| Articles fetched per run | 100 (hard cap) |
| Article freshness window | 8 hours |
| Articles classified for intent | Top 10 (after virality re-rank) |
| Facebook daily post limit | 10 |
| Instagram daily post limit | 45 (platform max is 50) |
| Telegram daily post limit | 30 |
| Facebook posting cooldown | 5 minutes |
| Instagram posting cooldown | 45 minutes |
| Per-intent topic cooldown | 2 hours |
| Cooldown wait-and-retry window | Up to 20 minutes |
| CLIP acceptance threshold | 0.27 |
| Image search retry loops | 3 article-specific loops + intent broad fallback + local library |
| Pixabay hourly call limit | 80 (then switches to Pexels) |
| Image used-again cooldown | Permanent (no recycling) |
| Duplicate clustering threshold | Cosine similarity ≥ 0.85 |
| Title duplicate threshold (DB) | Cosine similarity ≥ 0.78 over last 3 days |
| Fake news rejection threshold | Trust score < 0.40 |
| Caps penalty trigger | > 60% uppercase letters in title → −0.25 |
| FB caption quality threshold | Score < 55/100 → one Groq regeneration attempt |
| Breaking news post threshold | Score ≥ 60 (night: ≥ 80) |
| Webhook fallback trigger | Primary webhook returns non-200 |
| Make.com webhook retries | 2 per URL, across up to 2 URLs |
| ImgBB upload retries | 3 attempts with 2-second backoff |

---

## Project Structure

```
main.py                      # Pipeline A orchestrator (13 steps)
breaking_detector.py         # Pipeline B — fast breaking news detector
sports_tracker.py            # Pipeline C — live sports score tracker
fetcher.py                   # RSS feed ingestion + published_at extraction (sorted by domain priority)
fake_news_filter.py          # Source trust scoring (5-tier, 60+ domains) + clickbait + caps penalty
semantic_filter.py           # MiniLM embedding-based topic gating
deduplicator.py              # Semantic duplicate clustering
virality_scorer.py           # Pure-Python virality scorer (0-100) — recency, emotion, Pakistan signal
trend_detector.py            # Trending keyword detector across fetched articles — injects hashtags
intent_classifier.py         # Groq LLaMA zero-shot intent + 3-platform captions + trending context
caption_scorer.py            # FB caption quality scorer; triggers regeneration if score < 55
topic_memory.py              # Per-intent cooldown + consecutive-intent diversity
scene_selector.py            # Intent → Pixabay keyword tiers (incl. Tennis, F1, Boxing, Basketball)
pixabay_searcher.py          # Image search: Pixabay → Pexels → broad fallback → local library
image_composer.py            # Per-platform branded image composition (Pillow)
scheduler_queue.py           # Per-platform posting rate limiter
publisher.py                 # Make.com webhook (FB + IG) + Telegram Bot API + Gmail error alerts
results_logger.py            # Post result logging
generator.py                 # CLIP model singleton + image download helpers
clip_validator.py            # CLIP text-image similarity utility
db.py                        # SQLite post-history (WAL mode, embedding cache)
scorer.py                    # Keyword relevance scorer
constants.py                 # Keyword lists (Pakistan locations, breaking, blocked)
permanent_token.py           # One-time utility: exchanges FB short-lived token for permanent page token
debug.py                     # API connectivity tester
trending.py                  # pytrends + RSS trend engine (standalone utility)
requirements.txt
scripts/
    refresh_image_library.py # Refreshes local image library by intent
.github/
    workflows/
        post.yml             # Pipeline A — every 4 hours
        breaking_detector.yml # Pipeline B — every 5 minutes
        sports_tracker.yml   # Pipeline C — every 30 minutes
        image_library_refresh.yml  # Refreshes local image library daily
data/
    topic_memory.json
    queue.json
    results.json
    image_cache.json
    used_images.json
    rate_limit.json
    breaking_state.json
    sports_state.json
image_library/               # Local fallback images organised by intent
    WAR/  POLITICS/  ECONOMY/  DISASTER/  SPORTS/  CRICKET/  FOOTBALL/
```
