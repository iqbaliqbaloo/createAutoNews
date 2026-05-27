import re

def normalize(text):
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def contains_any(text, keywords):
    return any(k in text for k in keywords)


def score_article(article, trending_topics=None):
    title   = normalize(article["title"])
    summary = normalize(article["summary"])
    text    = title + " " + summary
    source  = article.get("source_type", "world")

    score = 0

    # ---------------- SAFETY FILTER ---------------- #
    for kw in BLOCKED_KEYWORDS:
        if kw in text:
            print(f"  ✗ Blocked: {article['title'][:50]} [{kw}]")
            return 0, 5

    # ---------------- QUALITY FILTER ---------------- #
    if len(summary.strip()) < 80:
        return 0, 5

    # ---------------- TREND BOOST ---------------- #
    if trending_topics:
        for t in trending_topics:
            t = t.lower()
            if len(t) > 3 and t in text:
                score += 25
                break

    # ---------------- PAKISTAN LOGIC ---------------- #
    if source == "pakistan":

        pk_signal = contains_any(text, PAKISTAN_KEYWORDS)
        if not pk_signal:
            return 0, 5

        important = contains_any(text, PAKISTAN_IMPORTANT_TOPICS)
        breaking   = contains_any(text, BREAKING_KEYWORDS)

        if not (important or breaking):
            return 0, 5

        score += 40  # base Pakistan relevance

        if breaking:
            score += 35

        if important:
            score += 25

        if contains_any(title, TRENDING_KEYWORDS):
            score += 10

    # ---------------- WORLD LOGIC ---------------- #
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

    # ---------------- DETAIL BOOST ---------------- #
    score += min(len(summary) // 120, 10)

    # ---------------- FINAL NORMALIZATION ---------------- #
    score = min(score, 100)

    # ---------------- LEVEL SYSTEM ---------------- #
    if score > 80:
        level = 1
    elif score > 60:
        level = 2
    elif score > 40:
        level = 3
    else:
        level = 5

    return score, level