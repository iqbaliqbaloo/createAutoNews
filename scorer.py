import re
from constants import *

def normalize(text):
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def contains_any(text, keywords):
    return any(k in text for k in keywords)


def score_article(article, trending_topics=None):

    title   = normalize(article.get("title", ""))
    summary = normalize(article.get("summary", ""))
    text    = title + " " + summary

    source  = article.get("source_type", "world")

    # ❌ BLOCK CHECK (FIXED)
    for kw in BLOCKED_KEYWORDS:
        if kw in text:
            print(f"✗ Blocked: {article.get('title','')[:50]}")
            return 0, 5

    if len(summary.strip()) < 80:
        return 0, 5

    score = 0

    # ---------------- TREND BOOST ----------------
    if trending_topics:
        for t in trending_topics:
            t = t.lower()
            if len(t) > 3 and t in text:
                score += 25
                break

    # ---------------- PAKISTAN ----------------
    if source == "pakistan":

        if not contains_any(text, PAKISTAN_KEYWORDS):
            return 0, 5

        important = contains_any(text, WORLD_MAJOR_KEYWORDS)
        breaking   = contains_any(text, BREAKING_KEYWORDS)

        if not (important or breaking):
            return 0, 5

        score += 40

        if breaking:
            score += 35

    # ---------------- WORLD ----------------
    else:

        major    = contains_any(text, WORLD_MAJOR_KEYWORDS)
        breaking = contains_any(text, BREAKING_KEYWORDS)

        if not (major or breaking):
            return 0, 5

        score += 30

        if breaking:
            score += 30

    score += min(len(summary) // 120, 10)
    score = min(score, 100)

    if score > 80:
        level = 1
    elif score > 60:
        level = 2
    elif score > 40:
        level = 3
    else:
        level = 5

    return score, level