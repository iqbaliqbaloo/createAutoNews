import re

# Maps intent labels to Pixabay search keyword groups.
# Used by pixabay_searcher.py to drive image search + CLIP retry loops.

SCENE_TEMPLATES = {
    "WAR": {
        "primary":   ["battlefield military soldiers", "troops armed forces combat", "tanks military operation", "soldiers weapons war zone"],
        "secondary": ["conflict zone destruction rubble", "war damage buildings", "military vehicles convoy", "armed conflict zone"],
        "tertiary":  ["war refugees displaced crisis", "military base operation", "defense forces troops"],
    },
    "POLITICS": {
        "primary":   ["press conference podium microphone", "parliament building government", "leader speech podium politics"],
        "secondary": ["political summit meeting leaders", "voting election ballot box", "government officials delegation"],
        "tertiary":  ["capitol building government hall", "diplomat handshake agreement", "political rally crowd"],
    },
    "ECONOMY": {
        "primary":   ["stock market trading screen numbers", "financial charts graphs economy", "currency exchange rates finance"],
        "secondary": ["banking finance skyscraper building", "economic data analysis business", "wall street traders floor"],
        "tertiary":  ["business meeting corporate boardroom", "money finance coins bills", "economic growth chart finance"],
    },
    "DISASTER": {
        "primary":   ["flood rescue emergency water", "earthquake destruction rubble collapse", "disaster emergency response team"],
        "secondary": ["rescue teams search rubble", "destroyed buildings collapse aftermath", "humanitarian aid relief workers"],
        "tertiary":  ["emergency helicopter rescue operation", "natural disaster aftermath destruction", "crisis response firefighters"],
    },
    "SPORTS": {
        "primary":   ["stadium crowd sports match action", "sports athletes competition field", "sports fans cheering stadium"],
        "secondary": ["trophy ceremony celebration winners", "athletic competition race track", "team sport players match"],
        "tertiary":  ["sports fans crowd cheering", "championship victory celebration", "olympic sports athletes"],
    },
    "SPORTS_CRICKET": {
        "primary":   ["cricket match stadium crowd players", "cricket bat ball pitch action", "cricket bowler batsman wicket"],
        "secondary": ["cricket celebration wicket boundary", "cricket six four boundary shot", "cricket umpire field match"],
        "tertiary":  ["cricket fans cheering stadium", "cricket trophy cup ceremony", "cricket team celebration"],
    },
    "SPORTS_FOOTBALL": {
        "primary":   ["football soccer match stadium crowd", "soccer goal celebration players", "football players action pitch"],
        "secondary": ["football penalty kick goalkeeper", "football referee yellow card", "football trophy league champions"],
        "tertiary":  ["football fans supporters stadium", "football pitch aerial view", "soccer team huddle"],
    },
    "SPORTS_LIVE": {
        "primary":   ["live sports action stadium crowd", "sports match crowd excitement", "athletes competition stadium"],
        "secondary": ["sports celebration victory trophy", "sports fans cheering stadium", "championship final match"],
        "tertiary":  ["stadium lights night match", "sports trophy award ceremony", "team sport final"],
    },
    "TENNIS": {
        "primary":   ["tennis match court players action", "tennis player serve racket ball", "tennis grand slam tournament"],
        "secondary": ["tennis racket ball court clay", "tennis tournament championship match", "tennis doubles singles players"],
        "tertiary":  ["wimbledon tennis court grass", "tennis player victory celebration", "tennis crowd stadium"],
    },
    "F1": {
        "primary":   ["formula 1 racing car track", "f1 grand prix race circuit", "formula one car speed race"],
        "secondary": ["racing pit stop team mechanics", "formula one drivers podium", "race track circuit aerial"],
        "tertiary":  ["motorsport competition car race", "racing championship trophy", "f1 crash race incident"],
    },
    "BOXING": {
        "primary":   ["boxing match fight ring punch", "boxer punch knockout gloves", "boxing ring fighters crowd"],
        "secondary": ["boxing championship belt bout", "mma ufc fighters cage", "boxing arena crowd fight"],
        "tertiary":  ["boxing training athlete gloves", "combat sport fight martial arts", "boxing champion belt"],
    },
    "BASKETBALL": {
        "primary":   ["basketball nba game court players", "basketball player dunk shot", "basketball arena crowd match"],
        "secondary": ["basketball shoot hoop net", "basketball game action players", "basketball championship final"],
        "tertiary":  ["basketball team sport players", "basketball arena fans cheering", "basketball trophy victory"],
    },
}

FALLBACK_KEYWORDS = {
    "WAR":              ["war military conflict"],
    "POLITICS":         ["government politics"],
    "ECONOMY":          ["finance economy"],
    "DISASTER":         ["disaster emergency"],
    "SPORTS":           ["sports stadium"],
    "SPORTS_CRICKET":   ["cricket match"],
    "SPORTS_FOOTBALL":  ["football soccer"],
    "SPORTS_LIVE":      ["live sports"],
    "TENNIS":           ["tennis court"],
    "F1":               ["formula 1 race"],
    "BOXING":           ["boxing fight"],
    "BASKETBALL":       ["basketball court"],
}

# Intent-specific broad fallbacks — used instead of generic "city crowd"
# so even worst-case images are topically relevant
BROAD_FALLBACKS = {
    "WAR":              ["war soldiers military conflict", "battlefield armed forces", "military troops weapons"],
    "POLITICS":         ["parliament government politics", "political leader speech", "government summit diplomacy"],
    "ECONOMY":          ["stock market finance economy", "business trading finance", "economic growth chart"],
    "DISASTER":         ["natural disaster emergency response", "rescue operation crisis", "disaster aftermath destruction"],
    "SPORTS":           ["sports stadium crowd match", "athletes competition action", "championship sports"],
    "SPORTS_CRICKET":   ["cricket match stadium players", "cricket bat ball pitch", "cricket players action"],
    "SPORTS_FOOTBALL":  ["football soccer match stadium", "soccer players pitch goal", "football crowd stadium"],
    "SPORTS_LIVE":      ["live sports match stadium", "sports crowd fans action", "championship final sports"],
    "TENNIS":           ["tennis court players match", "tennis grand slam tournament", "tennis racket ball court"],
    "F1":               ["formula 1 racing track", "grand prix race circuit", "racing car motorsport"],
    "BOXING":           ["boxing ring match fighters", "boxing bout punch gloves", "boxing arena crowd"],
    "BASKETBALL":       ["basketball court nba game", "basketball players dunk", "basketball match arena"],
}

# Prepended to article-extracted keywords so Pixabay gets topic context
INTENT_CONTEXT_PREFIX = {
    "WAR":              "war military conflict",
    "POLITICS":         "politics government",
    "ECONOMY":          "economy finance",
    "DISASTER":         "disaster emergency",
    "SPORTS":           "sports match",
    "SPORTS_CRICKET":   "cricket match",
    "SPORTS_FOOTBALL":  "football soccer match",
    "SPORTS_LIVE":      "live sports",
    "TENNIS":           "tennis court match",
    "F1":               "formula 1 race",
    "BOXING":           "boxing fight",
    "BASKETBALL":       "basketball game",
}

# Words that add no search value when extracted from a headline
_SKIP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "has", "have", "had", "be",
    "been", "this", "that", "says", "said", "report", "reports", "reported",
    "breaking", "update", "latest", "new", "may", "will", "can", "over",
    "into", "it", "its", "as", "by", "from", "not", "after",
    "sources", "officials", "government", "world", "news", "just", "amid",
    "vs", "against", "between",
}


def _article_keywords(title, intent="POLITICS", max_words=3):
    """
    Extract article-specific keywords from the headline and prepend the
    intent context prefix — so Pixabay always knows what topic we want.

    Example: title="Pakistan wins first ODI", intent="SPORTS_CRICKET"
             → "cricket match pakistan wins odi"
    """
    if not title:
        return []
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    words = [w for w in clean.split() if w not in _SKIP_WORDS and len(w) > 2]
    prefix = INTENT_CONTEXT_PREFIX.get(intent, "news")
    if not words:
        return [prefix]
    article_phrase = " ".join(words[:max_words])
    return [f"{prefix} {article_phrase}"]


def get_search_keywords(intent_result, article=None, retry_loop=0):
    """
    Return a list of Pixabay search terms based on intent and retry loop.

    retry_loop:
      0 → article-specific keywords prefixed with intent context (unique per story)
      1 → intent primary template keywords
      2 → intent secondary template keywords
      3 → intent tertiary template keywords
      4+ → generic fallback keyword for this intent
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
        if article:
            kws = _article_keywords(article.get("title", ""), intent=primary)
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
        return list(tmpl_primary["secondary"])

    elif retry_loop == 2:
        return list(tmpl_primary["tertiary"])

    elif retry_loop == 3:
        merged = list(tmpl_primary["tertiary"]) + list(tmpl_secondary["tertiary"])
        seen, out = set(), []
        for kw in merged:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out[:4]

    else:
        return list(FALLBACK_KEYWORDS.get(primary, ["news"]))
