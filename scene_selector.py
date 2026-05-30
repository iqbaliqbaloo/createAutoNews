import re

# Maps intent labels to Pixabay search keyword groups.
# Used by pixabay_searcher.py to drive image search + CLIP retry loops.

SCENE_TEMPLATES = {
    "WAR": {
        "primary":   ["battlefield military", "soldiers troops combat", "tanks armed forces", "military operation"],
        "secondary": ["conflict zone destruction", "war damage rubble", "military vehicles", "armed conflict"],
        "tertiary":  ["war refugees crisis", "military base", "defense forces"],
    },
    "POLITICS": {
        "primary":   ["press conference podium", "parliament building hall", "leader speech microphone"],
        "secondary": ["political summit meeting", "voting election ballot", "government officials"],
        "tertiary":  ["capitol building government", "diplomat handshake", "political rally"],
    },
    "ECONOMY": {
        "primary":   ["stock market trading screen", "financial charts graphs", "currency exchange rates"],
        "secondary": ["banking finance building", "economic data analysis", "wall street traders"],
        "tertiary":  ["business meeting corporate", "money finance coins", "economic growth chart"],
    },
    "DISASTER": {
        "primary":   ["flood rescue emergency", "earthquake destruction rubble", "disaster emergency response"],
        "secondary": ["rescue teams search", "destroyed buildings collapse", "humanitarian aid relief"],
        "tertiary":  ["emergency services helicopter", "natural disaster aftermath", "crisis response"],
    },
    "SPORTS": {
        "primary":   ["stadium crowd match", "sports action competition athlete", "football cricket match"],
        "secondary": ["trophy ceremony celebration", "athletic competition race", "team sport players"],
        "tertiary":  ["sports fan crowd cheering", "championship victory", "olympic sports"],
    },
    "SPORTS_CRICKET": {
        "primary":   ["cricket match stadium crowd", "cricket bat ball pitch", "cricket players action"],
        "secondary": ["cricket celebration wicket", "cricket boundary six four", "cricket umpire field"],
        "tertiary":  ["cricket fans cheering", "cricket trophy cup", "cricket team"],
    },
    "SPORTS_FOOTBALL": {
        "primary":   ["football match stadium crowd", "soccer goal celebration", "football players action"],
        "secondary": ["football penalty kick", "football referee card", "football trophy league"],
        "tertiary":  ["football fans supporters", "football pitch aerial", "soccer team"],
    },
    "SPORTS_LIVE": {
        "primary":   ["live sports action stadium", "sports match crowd excitement", "athletes competition"],
        "secondary": ["sports celebration victory", "sports fans cheering", "championship match"],
        "tertiary":  ["stadium lights night match", "sports trophy award", "team sport"],
    },
}

FALLBACK_KEYWORDS = {
    "WAR":             ["conflict"],
    "POLITICS":        ["government"],
    "ECONOMY":         ["finance"],
    "DISASTER":        ["emergency"],
    "SPORTS":          ["athletics"],
    "SPORTS_CRICKET":  ["cricket"],
    "SPORTS_FOOTBALL": ["football"],
    "SPORTS_LIVE":     ["sports"],
}

# Words that add no search value when extracted from a headline
_SKIP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "has", "have", "had", "be",
    "been", "this", "that", "says", "said", "report", "reports", "reported",
    "breaking", "update", "latest", "new", "may", "will", "can", "over",
    "into", "it", "its", "as", "by", "from", "not", "after", "amid",
    "sources", "officials", "government", "world", "news", "just",
}


def _article_keywords(title, max_words=4):
    """
    Extract meaningful Pixabay search terms from a news headline.
    Returns a list with one compound phrase built from the most significant words.
    """
    if not title:
        return []
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    words = [w for w in clean.split() if w not in _SKIP_WORDS and len(w) > 2]
    if not words:
        return []
    phrase = " ".join(words[:max_words])
    return [phrase]


def get_search_keywords(intent_result, article=None, retry_loop=0):
    """
    Return a list of Pixabay search terms based on intent and retry loop.

    retry_loop:
      0 → article-specific keywords extracted from headline (unique per story)
          falls back to intent primary if no article provided
      1 → intent primary keywords (or merged primary+secondary if ambiguous)
      2 → intent secondary keywords
      3 → intent tertiary keywords
      4+ → generic fallback keyword
    """
    primary   = intent_result["intent"]["primary"]
    secondary = intent_result["intent"].get("secondary", primary)
    ambiguous = intent_result["intent"].get("ambiguous", False)
    primary_score = max(
        (i["score"] for i in intent_result["intent"]["intents"] if i["label"] == primary),
        default=0.0,
    )

    tmpl_primary   = SCENE_TEMPLATES.get(primary,   SCENE_TEMPLATES["POLITICS"])
    tmpl_secondary = SCENE_TEMPLATES.get(secondary, tmpl_primary)

    if retry_loop == 0:
        # Use article-specific keywords so each story gets a unique, topic-matched image
        if article:
            kws = _article_keywords(article.get("title", ""))
            if kws:
                return kws
        # No article — fall straight to intent primary
        if not ambiguous and primary_score >= 0.50:
            return list(tmpl_primary["primary"])
        merged = list(tmpl_primary["primary"]) + list(tmpl_secondary["primary"])
        seen, out = set(), []
        for kw in merged:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out[:4]

    elif retry_loop == 1:
        # Intent primary (was loop=0) — first intent-level fallback
        if not ambiguous and primary_score >= 0.50:
            return list(tmpl_primary["primary"])
        merged = list(tmpl_primary["primary"]) + list(tmpl_secondary["primary"])
        seen, out = set(), []
        for kw in merged:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out[:4]

    elif retry_loop == 2:
        return list(tmpl_primary["secondary"])

    elif retry_loop == 3:
        return list(tmpl_primary["tertiary"])

    else:
        return list(FALLBACK_KEYWORDS.get(primary, ["news"]))
