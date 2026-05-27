import re

# =========================
# KEYWORDS (ALL IN ONE FILE)
# =========================

PAKISTAN_KEYWORDS = [
    "pakistan", "karachi", "lahore", "islamabad", "rawalpindi",
    "peshawar", "quetta", "sindh", "punjab", "kpk", "balochistan",
    "rupee", "sbp", "imran", "pmln", "pti", "army", "ispr",
    "shehbaz", "nawaz", "zardari", "bilawal",
    "pakistan army", "pakistan cricket", "pcb",
    "shaheen", "babar azam", "pakistan economy",
    "flood", "election"
]

PAKISTAN_IMPORTANT_TOPICS = [
    "election", "parliament", "senate", "assembly", "cabinet",
    "prime minister", "president", "court", "supreme court",
    "arrest", "resign", "imran khan", "pti", "pmln",
    "army", "military", "attack", "blast", "terror",
    "imf", "rupee", "inflation", "budget", "economy",
    "flood", "earthquake", "disaster",
    "india", "china", "us", "iran", "saudi"
]

TRENDING_KEYWORDS = [
    "breaking", "urgent", "live", "confirmed", "official",
    "major", "massive", "historic"
]

BREAKING_KEYWORDS = [
    "breaking", "urgent", "killed", "dead", "attack",
    "blast", "bomb", "earthquake", "flood", "fire",
    "crash", "resign", "war", "missile", "strike",
    "protest", "emergency", "explosion", "casualties"
]

WORLD_MAJOR_KEYWORDS = [
    "war", "nuclear", "nato", "tsunami", "earthquake",
    "assassination", "coup", "pandemic",
    "china", "russia", "israel", "gaza", "iran",
    "climate", "recession", "missile", "airstrike",
    "terror", "conflict"
]

BLOCKED_KEYWORDS = [
    "porn", "xxx", "nude", "sex", "onlyfans",
    "gossip", "rumor", "rumour",
    "tiktok trend", "meme", "viral video",
    "bollywood gossip", "hollywood gossip",
    "fashion tips", "beauty tips", "weight loss"
]

# =========================
# HELPERS
# =========================

def normalize(text):
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())

def contains_any(text, keywords):
    return any(k in text for k in keywords)

# =========================
# MAIN SCORING FUNCTION
# =========================

def score_article(article, trending_topics=None):

    title   = normalize(article.get("title", ""))
    summary = normalize(article.get("summary", ""))
    text    = title + " " + summary
    source  = article.get("source_type", "world")

    score = 0

    # ---------------- BLOCK FILTER ----------------
    for kw in BLOCKED_KEYWORDS:
        if kw in text:
            print(f"  ✗ Blocked: {article.get('title','')[:60]} [{kw}]")
            return 0, 5

    # ---------------- QUALITY FILTER ----------------
    if len(summary.strip()) < 80:
        return 0, 5

    # ---------------- TREND BOOST ----------------
    if trending_topics:
        for t in trending_topics:
            t = t.lower().strip()
            if len(t) > 3 and t in text:
                score += 25
                break

    # ================= PAKISTAN =================
    if source == "pakistan":

        if not contains_any(text, PAKISTAN_KEYWORDS):
            return 0, 5

        important = contains_any(text, PAKISTAN_IMPORTANT_TOPICS)
        breaking   = contains_any(text, BREAKING_KEYWORDS)

        if not (important or breaking):
            return 0, 5

        score += 40  # base relevance

        if breaking:
            score += 35

        if important:
            score += 25

        if contains_any(title, TRENDING_KEYWORDS):
            score += 10

    # ================= WORLD =================
    else:

        major   = contains_any(text, WORLD_MAJOR_KEYWORDS)
        breaking = contains_any(text, BREAKING_KEYWORDS)

        if not (major or breaking):
            return 0, 5

        score += 30

        if breaking:
            score += 30

        if major:
            score += 25

        if contains_any(title, TRENDING_KEYWORDS):
            score += 10

    # ---------------- DETAIL BOOST ----------------
    score += min(len(summary) // 120, 10)

    # ---------------- FINAL LIMIT ----------------
    score = min(score, 100)

    # ---------------- LEVEL SYSTEM ----------------
    if score > 80:
        level = 1
    elif score > 60:
        level = 2
    elif score > 40:
        level = 3
    else:
        level = 5

    return score, level