"""
Pipeline C — Sports Tracker

Runs every 30 minutes (sports_tracker.yml).
Reads data/sports_state.json for active matches.
No active match → exits in < 5 seconds.
Active match → fetches latest score → posts if triggered.

Match types: cricket_t20, cricket_odi, cricket_test, football
Match states: PRE_MATCH, LIVE, RESULT, POST_MATCH
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

import feedparser
import pytz
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PKT        = pytz.timezone("Asia/Karachi")
DATA_DIR   = "data"
STATE_FILE = os.path.join(DATA_DIR, "sports_state.json")

FOOTBALL_API = "https://api.football-data.org/v4"

COOLDOWN_MINUTES = 20

MAX_POSTS = {
    "cricket_t20":  8,
    "cricket_odi":  6,
    "cricket_test": 4,
    "football":     6,
}

# League → tag label + colour (RGB)
LEAGUE_TAGS = {
    "PSL":     ("PSL",      (  0,  99,  65)),
    "IPL":     ("IPL",      (  0,  75, 160)),
    "UCL":     ("UCL",      (  0,  29,  61)),
    "EPL":     ("EPL",      ( 56,   0,  60)),
    "CRICKET": ("CRICKET",  (108,  43, 217)),
    "FOOTBALL":("FOOTBALL", (  5, 122,  85)),
}

# Cricket RSS feeds (score updates appear as news items)
CRICKET_RSS = [
    "https://www.espncricinfo.com/rss/content/story/feeds/0.xml",
    "https://news.google.com/rss/search?q=cricket+live+score+match&hl=en&gl=PK&ceid=PK:en",
]


# ── State I/O ──────────────────────────────────────────────────────────────

def _load_state():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"active_matches": []}


def _save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Cricket score fetching (RSS-based) ────────────────────────────────────

def _fetch_cricket_updates(match):
    """
    Search cricket RSS feeds for score-related entries mentioning the match teams.
    Returns list of dicts with keys: title, description, event_type
    """
    team1 = match["teams"][0].lower().split()[0]   # first word of team name
    team2 = match["teams"][1].lower().split()[0]
    updates = []

    for rss_url in CRICKET_RSS:
        try:
            r    = requests.get(rss_url, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0 (SportsBot/1.0)"})
            feed = feedparser.parse(r.text)
        except Exception as e:
            logger.warning(f"Cricket RSS fetch failed {rss_url}: {e}")
            continue

        for entry in feed.entries:
            title = (getattr(entry, "title", "") or "").lower()
            desc  = (entry.get("summary", "") or "").lower()
            text  = title + " " + desc

            if team1 not in text and team2 not in text:
                continue

            event_type = _classify_cricket_event(text)
            updates.append({
                "title":      getattr(entry, "title", ""),
                "description": entry.get("summary", ""),
                "event_type": event_type,
            })

        if updates:
            break   # stop at first feed that has results

    return updates


def _classify_cricket_event(text):
    if any(w in text for w in ["wicket", "out", "bowled", "caught", "lbw", "run out"]):
        return "WICKET"
    if any(w in text for w in ["century", "100", "hundred"]):
        return "CENTURY"
    if any(w in text for w in ["fifty", "50 run", "half century"]):
        return "FIFTY"
    if any(w in text for w in ["six", "boundary", "four", "six runs"]):
        return "BOUNDARY"
    if "last 5 overs" in text or "last five overs" in text or "final over" in text:
        return "DEATH_OVERS"
    if any(w in text for w in ["won", "wins", "victory", "defeated", "lost by"]):
        return "RESULT"
    if any(w in text for w in ["innings break", "drinks break", "lunch break", "tea break"]):
        return "BREAK"
    return "UPDATE"


def _is_instant_trigger_cricket(event_type):
    return event_type in ("WICKET", "CENTURY", "DEATH_OVERS", "RESULT")


# ── Football score fetching (football-data.org) ───────────────────────────

def _fetch_football_match(match_id):
    """Fetch a specific match from football-data.org API."""
    api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        logger.warning("FOOTBALL_DATA_API_KEY not set")
        return None
    try:
        r = requests.get(
            f"{FOOTBALL_API}/matches/{match_id}",
            headers={"X-Auth-Token": api_key},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"Football API error: {e}")
    return None


def _classify_football_event(prev_snapshot, current_data):
    """Compare snapshots to detect goal, red card, half/full time."""
    if not prev_snapshot or not current_data:
        return "UPDATE"

    prev_home = prev_snapshot.get("home_score", 0)
    prev_away = prev_snapshot.get("away_score", 0)
    curr      = current_data.get("score", {}).get("fullTime", {})
    curr_home = curr.get("home", 0) or 0
    curr_away = curr.get("away", 0) or 0

    if curr_home > prev_home or curr_away > prev_away:
        return "GOAL"

    status = current_data.get("status", "")
    if status == "PAUSED":
        return "HALF_TIME"
    if status in ("FINISHED", "AWARDED"):
        return "FULL_TIME"

    # Red card check via bookings (simplified — not all tiers expose this)
    bookings = current_data.get("bookings", [])
    if any(b.get("card") == "RED_CARD" for b in bookings
           if b.get("minute", 0) > prev_snapshot.get("last_minute", 0)):
        return "RED_CARD"

    return "UPDATE"


def _is_instant_trigger_football(event_type):
    return event_type in ("GOAL", "RED_CARD", "HALF_TIME", "FULL_TIME")


# ── Caption builder ───────────────────────────────────────────────────────

def _build_caption(match, event_type, score_text, update_text):
    team1, team2 = match["teams"][0], match["teams"][1]
    league = match.get("league", "SPORTS")
    tag    = LEAGUE_TAGS.get(league.upper(), ("SPORTS", (204, 41, 54)))[0]

    emoji_map = {
        "GOAL":        "⚽ GOAL!",
        "WICKET":      "🏏 WICKET!",
        "CENTURY":     "💯 CENTURY!",
        "FIFTY":       "🏏 FIFTY!",
        "RED_CARD":    "🟥 RED CARD!",
        "HALF_TIME":   "⏸ HALF TIME",
        "FULL_TIME":   "🏁 FULL TIME",
        "RESULT":      "🏆 RESULT",
        "DEATH_OVERS": "🔥 DEATH OVERS",
        "UPDATE":      "🔄 LIVE UPDATE",
        "BREAK":       "☕ INNINGS BREAK",
    }
    headline = emoji_map.get(event_type, "🔄 LIVE UPDATE")

    base = (
        f"{headline}\n\n"
        f"{team1} vs {team2}\n"
        f"{score_text}\n\n"
        f"{update_text}\n\n"
        f"#{tag} #{team1.replace(' ', '')} #LiveScore #VisionaryMinds"
    )
    return {
        "facebook":  base[:500],
        "instagram": base[:300] + "\n\n#Cricket #Football #LiveSports #VMUpdates",
        "telegram":  base[:800],
    }


# ── Cooldown check ────────────────────────────────────────────────────────

def _can_post(match, instant=False):
    if instant:
        return True
    last = match.get("last_post_time")
    if not last:
        return True
    try:
        dt      = datetime.fromisoformat(last.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - dt).total_seconds() / 60
        return elapsed >= COOLDOWN_MINUTES
    except Exception:
        return True


def _at_post_limit(match):
    match_type = match.get("type", "cricket_t20")
    limit = MAX_POSTS.get(match_type, 6)
    # For Test cricket, limit is per day
    if match_type == "cricket_test":
        today_count = sum(
            1 for ts in match.get("post_history", [])
            if _same_day(ts)
        )
        return today_count >= limit
    return match.get("post_count", 0) >= limit


def _same_day(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(PKT)
        return dt.date() == datetime.now(PKT).date()
    except Exception:
        return False


# ── Post helper ───────────────────────────────────────────────────────────

def _post_sports_update(match, captions, headline_text, league):
    from pixabay_searcher  import search_with_clip_validation
    from image_composer    import save_platform_images, TAG_COLORS
    from publisher         import post_to_facebook, post_to_instagram, post_to_telegram

    sport_key = "SPORTS_CRICKET" if "cricket" in match.get("type", "") else "SPORTS_FOOTBALL"
    tag_label, tag_color = LEAGUE_TAGS.get(league.upper(), ("SPORTS", None))

    fake_intent_result = {
        "intent": {
            "primary":   sport_key,
            "secondary": "SPORTS",
            "ambiguous": False,
            "intents":   [{"label": sport_key, "score": 1.0}],
        },
        "captions": captions,
    }

    fake_article = {"title": headline_text}
    image_url, _, _, best_image_path = search_with_clip_validation(fake_intent_result, article=fake_article)

    platform_images = save_platform_images(
        image_url,
        tag_label,
        headline_text,
        match.get("league", "Sports"),
        tag_color=tag_color,
        image_path=best_image_path,
    )

    posted = []
    if "facebook" in platform_images:
        if post_to_facebook(captions["facebook"], platform_images["facebook"]):
            posted.append("facebook")

    if "instagram" in platform_images:
        if post_to_instagram(captions["instagram"], platform_images["instagram"]):
            posted.append("instagram")

    if "telegram" in platform_images:
        if post_to_telegram(captions["telegram"], platform_images["telegram"]):
            posted.append("telegram")

    for path in platform_images.values():
        try: os.unlink(path)
        except: pass
    if best_image_path:
        try: os.unlink(best_image_path)
        except: pass

    return posted


# ── Match processing ──────────────────────────────────────────────────────

def _process_cricket(match):
    updates = _fetch_cricket_updates(match)
    if not updates:
        logger.info(f"  No cricket updates found for {match['teams']}")
        return match

    top = updates[0]
    event_type = top["event_type"]
    instant    = _is_instant_trigger_cricket(event_type)

    if event_type == "RESULT":
        match["state"] = "RESULT"

    if _at_post_limit(match):
        logger.info(f"  Post limit reached for {match['id']}")
        return match

    if not _can_post(match, instant=instant):
        logger.info(f"  Cooldown active for {match['id']}")
        return match

    score_text  = top["description"][:120] if top["description"] else top["title"]
    update_text = top["title"]
    captions    = _build_caption(match, event_type, score_text, update_text)
    headline    = f"{match['teams'][0]} vs {match['teams'][1]} | {top['title'][:60]}"
    league      = match.get("league", "CRICKET")

    logger.info(f"  Posting cricket {event_type} for {match['id']}")
    posted = _post_sports_update(match, captions, headline, league)

    if posted:
        now_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        match["last_post_time"] = now_ts
        match["post_count"]     = match.get("post_count", 0) + 1
        match.setdefault("post_history", []).append(now_ts)

    return match


def _process_football(match):
    match_id = match.get("football_api_id")
    if not match_id:
        logger.warning(f"  No football_api_id set for {match['id']}")
        return match

    data = _fetch_football_match(match_id)
    if not data:
        return match

    status = data.get("status", "")
    if status in ("FINISHED", "AWARDED"):
        match["state"] = "RESULT"
    elif status in ("IN_PLAY", "PAUSED", "LIVE"):
        match["state"] = "LIVE"

    event_type = _classify_football_event(match.get("score_snapshot", {}), data)
    instant    = _is_instant_trigger_football(event_type)

    curr_score = data.get("score", {}).get("fullTime", {})
    home_score = curr_score.get("home", 0) or 0
    away_score = curr_score.get("away", 0) or 0
    match["score_snapshot"] = {
        "home_score":  home_score,
        "away_score":  away_score,
        "last_minute": data.get("minute", 0),
    }

    if _at_post_limit(match):
        logger.info(f"  Post limit reached for {match['id']}")
        return match

    if not _can_post(match, instant=instant):
        logger.info(f"  Cooldown active for {match['id']}")
        return match

    team1, team2 = match["teams"][0], match["teams"][1]
    score_text   = f"{team1} {home_score} – {away_score} {team2}"
    update_text  = f"Minute: {data.get('minute') or '?'}" if event_type != "FULL_TIME" else "Full Time"
    captions     = _build_caption(match, event_type, score_text, update_text)
    headline     = f"{score_text} | {event_type.replace('_', ' ').title()}"
    league       = match.get("league", "FOOTBALL")

    logger.info(f"  Posting football {event_type} for {match['id']}")
    posted = _post_sports_update(match, captions, headline, league)

    if posted:
        now_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        match["last_post_time"] = now_ts
        match["post_count"]     = match.get("post_count", 0) + 1
        match.setdefault("post_history", []).append(now_ts)

    return match


# ── Main ──────────────────────────────────────────────────────────────────

def run():
    state   = _load_state()
    matches = state.get("active_matches", [])

    if not matches:
        logger.info("No active matches — exiting")
        return

    now = datetime.now(timezone.utc)
    updated = []

    for match in matches:
        match_state = match.get("state", "PRE_MATCH")
        start_str   = match.get("start_time", "")

        # Transition PRE_MATCH → LIVE when start time is reached
        if match_state == "PRE_MATCH" and start_str:
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if now >= start_dt:
                    match["state"] = "LIVE"
                    match_state    = "LIVE"
                    logger.info(f"Match {match['id']} is now LIVE")
            except Exception:
                pass

        if match_state in ("RESULT", "POST_MATCH"):
            # Keep result matches for 2 hours then drop them
            last_post = match.get("last_post_time", match.get("start_time", ""))
            if last_post:
                try:
                    dt = datetime.fromisoformat(last_post.replace("Z", "+00:00"))
                    if (now - dt).total_seconds() > 7200:
                        logger.info(f"Dropping finished match {match['id']}")
                        continue
                except Exception:
                    pass
            updated.append(match)
            continue

        if match_state != "LIVE":
            updated.append(match)
            continue

        match_type = match.get("type", "cricket_t20")
        logger.info(f"Processing {match_type} match: {match['id']}")

        if "cricket" in match_type:
            match = _process_cricket(match)
        elif match_type == "football":
            match = _process_football(match)

        updated.append(match)

    state["active_matches"] = updated
    _save_state(state)
    logger.info("Sports tracker run complete")


if __name__ == "__main__":
    run()
