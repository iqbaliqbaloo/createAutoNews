import re

# Maps intent labels to Pixabay search keyword groups.
# Used by pixabay_searcher.py to drive image search + CLIP retry loops.

SCENE_TEMPLATES = {
    "WAR": {
        "primary":    ["battlefield military soldiers", "troops armed forces combat", "tanks military operation", "soldiers weapons war zone"],
        "secondary":  ["conflict zone destruction rubble", "war damage buildings", "military vehicles convoy", "armed conflict zone"],
        "tertiary":   ["war refugees displaced crisis", "military base operation", "defense forces troops"],
        "quaternary": ["warplane jet fighter military", "navy warship sea military", "sniper rifle military operation", "army camp soldiers tent"],
        "quinary":    ["military helicopter gunship", "bomb explosion fire war", "frontline trench soldiers combat", "missile launch military strike"],
    },
    "POLITICS": {
        "primary":    ["press conference podium microphone", "parliament building government", "leader speech podium politics"],
        "secondary":  ["political summit meeting leaders", "voting election ballot box", "government officials delegation"],
        "tertiary":   ["capitol building government hall", "diplomat handshake agreement", "political rally crowd"],
        "quaternary": ["united nations assembly hall", "president oval office meeting", "senate congress chamber hall", "prime minister speech crowd"],
        "quinary":    ["ambassador foreign minister meeting", "election campaign rally crowd", "government protest demonstration", "political debate stage microphone"],
    },
    "ECONOMY": {
        "primary":    ["stock market trading screen numbers", "financial charts graphs economy", "currency exchange rates finance"],
        "secondary":  ["banking finance skyscraper building", "economic data analysis business", "wall street traders floor"],
        "tertiary":   ["business meeting corporate boardroom", "money finance coins bills", "economic growth chart finance"],
        "quaternary": ["oil refinery energy industry", "cargo ship port trade", "factory workers manufacturing industry", "imf world bank finance"],
        "quinary":    ["inflation prices grocery shopping", "unemployment job seekers office", "crypto bitcoin digital currency", "housing market real estate"],
    },
    "DISASTER": {
        "primary":    ["flood rescue emergency water", "earthquake destruction rubble collapse", "disaster emergency response team"],
        "secondary":  ["rescue teams search rubble", "destroyed buildings collapse aftermath", "humanitarian aid relief workers"],
        "tertiary":   ["emergency helicopter rescue operation", "natural disaster aftermath destruction", "crisis response firefighters"],
        "quaternary": ["wildfire forest burning flames", "cyclone hurricane storm damage", "landslide mudslide destruction", "tsunami wave coastal damage"],
        "quinary":    ["volcano eruption lava flow", "drought cracked earth famine", "avalanche snow mountain rescue", "chemical spill hazmat emergency"],
    },
    "HEALTH": {
        "primary":    ["doctor hospital medical emergency", "health workers protective gear outbreak", "medical team treating patients hospital"],
        "secondary":  ["nurses doctors hospital ward", "medical equipment laboratory health", "ambulance emergency medical response"],
        "tertiary":   ["WHO health officials press conference", "vaccine injection medical clinic", "disease outbreak public health"],
        "quaternary": ["protest demonstration healthcare policy", "medical research laboratory scientists", "quarantine isolation health facility", "emergency room hospital crisis"],
        "quinary":    ["public health announcement crowd", "medicine pills pharmaceutical health", "global health crisis response team", "hospital bed patient medical care"],
    },
    "SPORTS": {
        "primary":    ["stadium crowd sports match action", "sports athletes competition field", "sports fans cheering stadium"],
        "secondary":  ["trophy ceremony celebration winners", "athletic competition race track", "team sport players match"],
        "tertiary":   ["sports fans crowd cheering", "championship victory celebration", "olympic sports athletes"],
        "quaternary": ["sports press conference podium", "athlete training practice field", "sports medal ceremony podium", "team locker room celebration"],
        "quinary":    ["sports injury medical field", "referee decision controversial sport", "sports transfer signing deal", "young athlete training sports"],
    },
    "SPORTS_CRICKET": {
        "primary":    ["cricket match stadium crowd players", "cricket bat ball pitch action", "cricket bowler batsman wicket"],
        "secondary":  ["cricket celebration wicket boundary", "cricket six four boundary shot", "cricket umpire field match"],
        "tertiary":   ["cricket fans cheering stadium", "cricket trophy cup ceremony", "cricket team celebration"],
        "quaternary": ["cricket drs review decision umpire", "cricket opening batsman crease", "cricket fast bowler run up", "cricket fielding catch outfield"],
        "quinary":    ["cricket test match white clothing", "cricket ipl t20 night match", "cricket world cup trophy", "cricket spin bowler delivery"],
    },
    "SPORTS_FOOTBALL": {
        "primary":    ["football soccer match stadium crowd", "soccer goal celebration players", "football players action pitch"],
        "secondary":  ["football penalty kick goalkeeper", "football referee yellow card", "football trophy league champions"],
        "tertiary":   ["football fans supporters stadium", "football pitch aerial view", "soccer team huddle"],
        "quaternary": ["football corner kick players", "football header aerial duel", "football tackle sliding pitch", "football manager touchline coaching"],
        "quinary":    ["football champions league trophy", "football world cup celebration", "football free kick wall", "football transfer signing contract"],
    },
    "SPORTS_LIVE": {
        "primary":    ["live sports action stadium crowd", "sports match crowd excitement", "athletes competition stadium"],
        "secondary":  ["sports celebration victory trophy", "sports fans cheering stadium", "championship final match"],
        "tertiary":   ["stadium lights night match", "sports trophy award ceremony", "team sport final"],
        "quaternary": ["live score board scoreboard", "sports commentator broadcast booth", "sports tv camera crew pitch", "match official referee decision"],
        "quinary":    ["stadium atmosphere flares fans", "substitution player bench sport", "injury time stoppage sport", "penalty shootout tension sport"],
    },
    "TENNIS": {
        "primary":    ["tennis match court players action", "tennis player serve racket ball", "tennis grand slam tournament"],
        "secondary":  ["tennis racket ball court clay", "tennis tournament championship match", "tennis doubles singles players"],
        "tertiary":   ["wimbledon tennis court grass", "tennis player victory celebration", "tennis crowd stadium"],
        "quaternary": ["tennis tiebreak decisive point", "tennis player backhand forehand", "tennis net approach volley", "tennis umpire chair court"],
        "quinary":    ["us open tennis hard court", "french open clay court tennis", "australian open tennis night", "tennis player injury retirement"],
    },
    "F1": {
        "primary":    ["formula 1 racing car track", "f1 grand prix race circuit", "formula one car speed race"],
        "secondary":  ["racing pit stop team mechanics", "formula one drivers podium", "race track circuit aerial"],
        "tertiary":   ["motorsport competition car race", "racing championship trophy", "f1 crash race incident"],
        "quaternary": ["formula 1 qualifying lap time", "f1 safety car track circuit", "racing driver helmet cockpit", "f1 grid start lights"],
        "quinary":    ["monaco grand prix street circuit", "silverstone f1 race crowd", "f1 fastest lap champion", "racing car rear wing drs"],
    },
    "BOXING": {
        "primary":    ["boxing match fight ring punch", "boxer punch knockout gloves", "boxing ring fighters crowd"],
        "secondary":  ["boxing championship belt bout", "mma ufc fighters cage", "boxing arena crowd fight"],
        "tertiary":   ["boxing training athlete gloves", "combat sport fight martial arts", "boxing champion belt"],
        "quaternary": ["boxing weigh in face off", "boxing corner cut man trainer", "knockout punch boxing crowd", "boxing referee count knockdown"],
        "quinary":    ["heavyweight boxing championship bout", "boxing judges scorecard decision", "boxer entrance ring walk", "boxing sparring training gym"],
    },
    "BASKETBALL": {
        "primary":    ["basketball nba game court players", "basketball player dunk shot", "basketball arena crowd match"],
        "secondary":  ["basketball shoot hoop net", "basketball game action players", "basketball championship final"],
        "tertiary":   ["basketball team sport players", "basketball arena fans cheering", "basketball trophy victory"],
        "quaternary": ["basketball three point shot crowd", "basketball fast break layup", "basketball pick roll play", "basketball timeout coach players"],
        "quinary":    ["nba playoffs basketball arena", "basketball slam dunk contest", "basketball foul free throw", "basketball draft pick celebrate"],
    },
    "TECHNOLOGY": {
        "primary":    ["artificial intelligence robot technology", "smartphone modern technology device", "tech innovation digital future"],
        "secondary":  ["computer code software developer", "electric car technology innovation", "space rocket satellite technology"],
        "tertiary":   ["cybersecurity hacker data network", "tech startup office team", "virtual reality headset digital"],
        "quaternary": ["silicon chip processor technology", "cloud computing data center", "drone aerial tech innovation", "5g network tower technology"],
        "quinary":    ["robot ai machine learning", "tech conference presentation stage", "apple google tech launch event", "quantum computer science lab"],
    },
    "ENTERTAINMENT": {
        "primary":    ["bollywood film movie actor stage", "celebrity red carpet award ceremony", "concert stage music crowd performance"],
        "secondary":  ["movie film production camera crew", "music artist singer stage lights", "award trophy ceremony celebration"],
        "tertiary":   ["actor actress film premiere crowd", "music concert crowd fans", "entertainment industry glamour fashion"],
        "quaternary": ["film set director camera action", "theatre performance stage audience", "television studio broadcast show", "celebrity interview press media"],
        "quinary":    ["streaming platform digital entertainment", "music video production studio", "film award nomination announcement", "celebrity couple fashion event"],
    },
}

FALLBACK_KEYWORDS = {
    "WAR":              ["war military conflict"],
    "POLITICS":         ["government politics"],
    "ECONOMY":          ["finance economy"],
    "DISASTER":         ["disaster emergency"],
    "HEALTH":           ["hospital medical health"],
    "SPORTS":           ["sports stadium"],
    "SPORTS_CRICKET":   ["cricket match"],
    "SPORTS_FOOTBALL":  ["football soccer"],
    "SPORTS_LIVE":      ["live sports"],
    "TENNIS":           ["tennis court"],
    "F1":               ["formula 1 race"],
    "BOXING":           ["boxing fight"],
    "BASKETBALL":       ["basketball court"],
    "TECHNOLOGY":       ["technology innovation"],
    "ENTERTAINMENT":    ["entertainment celebrity"],
}

# Intent-specific broad fallbacks — used instead of generic "city crowd"
# so even worst-case images are topically relevant
BROAD_FALLBACKS = {
    "WAR":              ["war soldiers military conflict", "battlefield armed forces", "military troops weapons"],
    "POLITICS":         ["parliament government politics", "political leader speech", "government summit diplomacy"],
    "ECONOMY":          ["stock market finance economy", "business trading finance", "economic growth chart"],
    "DISASTER":         ["natural disaster emergency response", "rescue operation crisis", "disaster aftermath destruction"],
    "HEALTH":           ["hospital medical emergency health", "doctor nurse patient care", "public health outbreak response"],
    "SPORTS":           ["sports stadium crowd match", "athletes competition action", "championship sports"],
    "SPORTS_CRICKET":   ["cricket match stadium players", "cricket bat ball pitch", "cricket players action"],
    "SPORTS_FOOTBALL":  ["football soccer match stadium", "soccer players pitch goal", "football crowd stadium"],
    "SPORTS_LIVE":      ["live sports match stadium", "sports crowd fans action", "championship final sports"],
    "TENNIS":           ["tennis court players match", "tennis grand slam tournament", "tennis racket ball court"],
    "F1":               ["formula 1 racing track", "grand prix race circuit", "racing car motorsport"],
    "BOXING":           ["boxing ring match fighters", "boxing bout punch gloves", "boxing arena crowd"],
    "BASKETBALL":       ["basketball court nba game", "basketball players dunk", "basketball match arena"],
    "TECHNOLOGY":       ["artificial intelligence technology", "tech innovation digital future", "smartphone modern technology"],
    "ENTERTAINMENT":    ["bollywood celebrity entertainment", "concert stage music crowd", "award ceremony red carpet"],
}

# Prepended to article-extracted keywords so Pixabay gets topic context
INTENT_CONTEXT_PREFIX = {
    "WAR":              "war military conflict",
    "POLITICS":         "politics government",
    "ECONOMY":          "economy finance",
    "DISASTER":         "disaster emergency",
    "HEALTH":           "health medical hospital",
    "SPORTS":           "sports match",
    "SPORTS_CRICKET":   "cricket match",
    "SPORTS_FOOTBALL":  "football soccer match",
    "SPORTS_LIVE":      "live sports",
    "TENNIS":           "tennis court match",
    "F1":               "formula 1 race",
    "BOXING":           "boxing fight",
    "BASKETBALL":       "basketball game",
    "TECHNOLOGY":       "technology innovation digital",
    "ENTERTAINMENT":    "entertainment celebrity bollywood",
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


def _article_keywords(title, intent="POLITICS", max_words=5):
    """
    Extract article-specific keywords from the headline — NO generic prefix.
    Pure topic words give Pixabay the best chance of finding a relevant image.

    Example: title="Israel Lebanon talks opens after strikes"
             → "israel lebanon talks opens strikes"  (specific to THIS story)
    """
    if not title:
        return []
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    words = [w for w in clean.split() if w not in _SKIP_WORDS and len(w) > 2]
    if not words:
        # Fallback to intent prefix only if title has no usable words
        return [INTENT_CONTEXT_PREFIX.get(intent, "news")]
    return [" ".join(words[:max_words])]


def _extract_article_words(title, max_words=3):
    """Extract 3 meaningful words from article title for use in retry loops."""
    if not title:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    words = [w for w in clean.split() if w not in _SKIP_WORDS and len(w) > 3]
    return " ".join(words[:max_words])


def _mix(article_words, template_kws):
    """
    Prepend article-specific words to the first template keyword so every
    article gets unique search terms even in fallback loops.
    e.g. article_words="israel lebanon" + "conflict zone destruction rubble"
         → ["israel lebanon conflict zone", "war damage buildings", ...]
    """
    if not article_words or not template_kws:
        return list(template_kws)
    mixed = [f"{article_words} {template_kws[0]}"] + list(template_kws[1:])
    return mixed


def get_search_keywords(intent_result, article=None, retry_loop=0):
    """
    Return a list of Pixabay search terms based on intent and retry loop.
    Article-specific words are injected into ALL loops so every story gets
    unique image searches even when the first loop fails CLIP validation.

    retry_loop:
      0 → article-specific keywords prefixed with intent context
      1 → article words + intent secondary template
      2 → article words + intent tertiary template
      3 → article words + quaternary template
      4 → article words + quinary template
      5+ → generic fallback
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

    # Extract article-specific words — used in ALL loops
    art_words = _extract_article_words(article.get("title", "") if article else "")

    if retry_loop == 0:
        if article:
            kws = _article_keywords(article.get("title", ""), intent=primary)
            if kws:
                return kws
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
        return _mix(art_words, tmpl_primary["secondary"])

    elif retry_loop == 2:
        return _mix(art_words, tmpl_primary["tertiary"])

    elif retry_loop == 3:
        return _mix(art_words, tmpl_primary.get("quaternary", tmpl_primary["tertiary"]))

    elif retry_loop == 4:
        return _mix(art_words, tmpl_primary.get("quinary", tmpl_primary["tertiary"]))

    else:
        return list(FALLBACK_KEYWORDS.get(primary, ["news"]))
