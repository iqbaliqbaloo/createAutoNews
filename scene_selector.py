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
}

FALLBACK_KEYWORDS = {
    "WAR":      ["conflict"],
    "POLITICS": ["government"],
    "ECONOMY":  ["finance"],
    "DISASTER": ["emergency"],
    "SPORTS":   ["athletics"],
}


def get_search_keywords(intent_result, retry_loop=0):
    """
    Return a list of Pixabay search terms based on intent and retry loop.

    retry_loop:
      0 → primary keywords (or merged primary+secondary if ambiguous)
      1 → secondary keywords
      2 → tertiary keywords
      3+ → generic fallback keyword
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
        if not ambiguous and primary_score >= 0.50:
            return list(tmpl_primary["primary"])
        # Ambiguous → merge primary + secondary pools
        merged = list(tmpl_primary["primary"]) + list(tmpl_secondary["primary"])
        # Deduplicate while preserving order
        seen, out = set(), []
        for kw in merged:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out[:4]

    elif retry_loop == 1:
        return list(tmpl_primary["secondary"])

    elif retry_loop == 2:
        return list(tmpl_secondary["tertiary"])

    else:
        return list(FALLBACK_KEYWORDS.get(primary, ["news"]))
