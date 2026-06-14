import json
import logging
import os
import random

logger = logging.getLogger(__name__)

INTENTS = ["WAR", "POLITICS", "ECONOMY", "DISASTER", "HEALTH", "SPORTS", "TECHNOLOGY", "ENTERTAINMENT"]

# Topic label shown at the very top of every Facebook and Instagram caption
TOPIC_LABELS = {
    "WAR":           "⚔️ WAR & CONFLICT",
    "POLITICS":      "🏛️ POLITICS",
    "ECONOMY":       "📈 ECONOMY",
    "DISASTER":      "🚨 DISASTER ALERT",
    "HEALTH":        "🏥 HEALTH ALERT",
    "SPORTS":        "🏆 SPORTS",
    "TECHNOLOGY":    "💡 TECHNOLOGY",
    "ENTERTAINMENT": "🎬 ENTERTAINMENT",
}

_SYSTEM_PROMPT = """\
You are a news classifier and social media writer. Given a news article, you must:
1. Classify it into exactly one of: WAR, POLITICS, ECONOMY, DISASTER, HEALTH, SPORTS, TECHNOLOGY, ENTERTAINMENT
2. Write platform-specific captions for Facebook, Instagram, and Telegram

Respond ONLY with valid JSON — no markdown fences, no commentary.\
"""

_INTENT_HASHTAGS = {
    "WAR":           "#Conflict #BreakingNews #WorldNews #WarNews #GlobalCrisis #LiveUpdates #MustShare #UrgentNews",
    "POLITICS":      "#Politics #BreakingNews #WorldNews #GlobalPolitics #CurrentAffairs #PoliticalNews #MustRead #TopStory",
    "ECONOMY":       "#Economy #Finance #WorldNews #MarketNews #Inflation #EconomicCrisis #MoneyMatters #MustKnow",
    "DISASTER":      "#Disaster #BreakingNews #WorldNews #NaturalDisaster #EmergencyAlert #PrayersNeeded #HumanityFirst #UrgentNews",
    "HEALTH":        "#Health #BreakingNews #WorldNews #HealthAlert #PublicHealth #Outbreak #MedicalNews #StaySafe #UrgentNews",
    "SPORTS":        "#Sports #BreakingNews #WorldNews #Cricket #Football #PSL #SportsUpdate #GameChanger #MustWatch",
    "TECHNOLOGY":    "#Technology #Tech #AI #Innovation #Digital #Gadgets #TechNews #FutureTech #MustRead #TechUpdate",
    "ENTERTAINMENT": "#Entertainment #Bollywood #Lollywood #Celebrity #Movies #Music #Trending #MustWatch #PopCulture #Viral",
}

# Viral hook openers by intent — chosen randomly to avoid repetition
_VIRAL_HOOKS = {
    "WAR":           [
        "This is happening RIGHT NOW and the world needs to know:",
        "Nobody is talking about this — but they should be:",
        "This changes everything. Here is what is unfolding:",
        "URGENT: A situation the world cannot ignore is developing:",
    ],
    "POLITICS":      [
        "A decision that will affect millions of people was just made:",
        "This is the political story everyone is watching right now:",
        "Something major just shifted on the global stage:",
        "Leaders just made a move that will impact your life:",
    ],
    "ECONOMY":       [
        "Your money, your future — this news matters to every family:",
        "The economic news you cannot afford to miss right now:",
        "A financial shift is happening — here is what you need to know:",
        "This economic development is affecting millions of people:",
    ],
    "DISASTER":      [
        "Prayers and thoughts needed — a crisis is unfolding:",
        "This is devastating. Here is what is happening right now:",
        "Lives are at stake. Share this so the world responds:",
        "A tragedy is unfolding — the world must see this:",
    ],
    "HEALTH":        [
        "This health alert affects millions of people worldwide:",
        "An urgent medical situation is developing — here is what you need to know:",
        "Public health officials are responding to this developing situation:",
        "This is the health story everyone needs to be aware of right now:",
    ],
    "SPORTS":        [
        "A major development just emerged from the sporting world:",
        "Here is what unfolded in today's match:",
        "A significant result has been recorded:",
        "The latest from today's live fixture:",
    ],
    "TECHNOLOGY":    [
        "This tech news is about to change how you live:",
        "The biggest technology story right now — here is what happened:",
        "A major breakthrough just happened in the tech world:",
        "This is the technology update everyone is talking about:",
    ],
    "ENTERTAINMENT": [
        "The entertainment world is talking about this right now:",
        "Big news just broke from the world of movies and music:",
        "This celebrity story has everyone talking:",
        "The latest from Bollywood and the entertainment industry:",
    ],
}


# ── Plain Groq call (no JSON system prompt) — for caption regeneration ─────

def _groq_plain_call(user_prompt):
    """Simple Groq call without JSON system prompt — for caption regeneration."""
    from groq import Groq
    for env_var in ("GROQ_API_KEY", "GROQ_API_KEY_2"):
        key = os.getenv(env_var)
        if not key:
            continue
        try:
            resp = Groq(api_key=key).chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.4,
                max_tokens=600,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"{env_var} regen failed: {e}")
    return None


# ── Groq call with key-1 → key-2 fallback ─────────────────────────────────

def _groq_call(user_prompt, groq_client=None):
    """
    Try groq_client first (if provided), then GROQ_API_KEY, then GROQ_API_KEY_2.
    Returns raw response content string, or None if all attempts fail.
    """
    from groq import Groq

    def _call(client):
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1600,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content

    # 1. Use caller-provided client (backward-compat for breaking_detector etc.)
    if groq_client:
        try:
            return _call(groq_client)
        except Exception as e:
            logger.warning(f"Provided groq client failed: {e} — trying env keys")

    # 2. Try env keys in order
    for env_var in ("GROQ_API_KEY", "GROQ_API_KEY_2"):
        key = os.getenv(env_var)
        if not key:
            continue
        try:
            return _call(Groq(api_key=key))
        except Exception as e:
            logger.warning(f"{env_var} failed: {e}")

    return None


# ── Main entry point ───────────────────────────────────────────────────────

def classify_and_generate(article, groq_client=None, trending_context=""):
    """
    Single LLM call: intent classification + 3 platform captions (FB, IG, Telegram).
    groq_client  — optional; key selection handled internally with fallback.
    trending_context — optional string from trend_detector to inject into prompt.
    Returns dict with keys: 'intent', 'captions'.
    """
    from caption_scorer import score_caption, optimize_length

    title       = article.get("title", "")
    description = (article.get("summary", "") or article.get("description", "") or "")[:500]
    intent_tags = " | ".join(f"{k}: {v}" for k, v in _INTENT_HASHTAGS.items())

    user_prompt = f"""\
Article Title: {title}
Article Description: {description}

Classify this article and generate captions. Return ONLY this JSON structure:

{{
  "intent": {{
    "intents": [
      {{"label": "WAR",           "score": 0.00}},
      {{"label": "POLITICS",      "score": 0.00}},
      {{"label": "ECONOMY",       "score": 0.00}},
      {{"label": "DISASTER",      "score": 0.00}},
      {{"label": "HEALTH",        "score": 0.00}},
      {{"label": "SPORTS",        "score": 0.00}},
      {{"label": "TECHNOLOGY",    "score": 0.00}},
      {{"label": "ENTERTAINMENT", "score": 0.00}}
    ],
    "primary": "LABEL",
    "secondary": "LABEL",
    "ambiguous": false
  }},
  "captions": {{
    "facebook":       "...",
    "instagram":      "...",
    "telegram":       "...",
    "image_headline": "...",
    "image_subtext":  "line 1 here\noptional line 2 here"
  }}
}}

STRICT RULE (all captions): NEVER mention any news channel, outlet, website, or media organisation (e.g. Al Jazeera, BBC, Reuters, CNN, Dawn, Geo, ARY). Write as original reporting.

RULES — Intent:
- All 5 scores must sum to exactly 1.0
- Set ambiguous=true if top score < 0.50
- primary = highest-score label; secondary = second-highest

LANGUAGE RULES (apply to ALL captions):
- Write like you are texting a friend. Very simple words only.
- Short sentences. Max 10 words per sentence.
- No big or hard words. If a 10-year-old cannot understand it, rewrite it.
- Do NOT use words like: unprecedented, escalation, geopolitical, bilateral, amid, pursuant, commenced, alleged, pertaining, whilst, nevertheless, henceforth.
- Use simple words instead: started, said, killed, won, lost, happened, now, because, but, so.

RULES — Image Headline (big bold text on image, max 6 words):
- Write exactly 4-6 very simple words — the single most important fact
- No emojis, no hashtags, no punctuation at the end
- Good: "Pakistan Beats India By 5 Wickets" / "Flood Kills 200 In Pakistan"
- Bad: anything over 6 words, hard words, hashtags

RULES — Image Subtext (smaller text below headline, max 2 lines):
- Line 1: One simple sentence, max 10 words — WHO did WHAT
- Line 2 (optional): max 10 words — WHERE or WHEN
- Separate with \n. No emojis, no hashtags.
- Good: "Australia beat Turkey 2-0 in World Cup\nMatch played in Dallas, USA"

RULES — Facebook caption:
- Line 1 (TOPIC LABEL): Start with:
  WAR → "⚔️ WAR & CONFLICT |"  POLITICS → "🏛️ POLITICS |"
  ECONOMY → "📈 ECONOMY |"  DISASTER → "🚨 DISASTER ALERT |"  HEALTH → "🏥 HEALTH ALERT |"
  SPORTS → "🏆 SPORTS |"  TECHNOLOGY → "💡 TECHNOLOGY |"  ENTERTAINMENT → "🎬 ENTERTAINMENT |"
  Then write ONE clear simple sentence about what happened.
- Body: Tell the full story in simple words. Cover WHO, WHAT, WHERE, WHY it matters.
  • Sports result: score, who scored, what it means for the team (4-5 sentences)
  • War/disaster/health: what happened, how many affected, what is being done (4-6 sentences)
  • Politics/economy: what was decided, who decided it, how it affects people (4-5 sentences)
  • Each sentence on its own line. Max 10 words per sentence.
- End with ONLY 3 hashtags: #VisionaryMinds #BreakingNews and ONE topic tag
- No URLs. Max 1 emoji in the body.

RULES — Instagram caption:
- Same topic label as Facebook on line 1
- Same body content as Facebook — tell the full story simply
- Each sentence on its own line
- Add: "Follow @VisionaryMinds for live updates 👇"
- End with ONLY 5 hashtags: #VisionaryMinds #BreakingNews #WorldNews and TWO topic tags
- Do NOT include any URL or link

RULES — Telegram caption:
- Start: "🔴 **BREAKING — {{one clear simple sentence}}**"
- Body: Tell the full story. Same depth as Facebook.
- Each sentence on its own line. Max 10 words per sentence.
- End with ONLY 3 hashtags: #VisionaryMinds #BreakingNews and ONE topic tag
- Do NOT include any URL or link
- Bold only the opening line

{f"Trending context (use only if directly relevant): {trending_context}" if trending_context else ""}
"""

    raw = None
    try:
        raw = _groq_call(user_prompt, groq_client)
        if not raw:
            raise ValueError("All Groq keys exhausted")
        result = json.loads(raw)

        intent_data = result.get("intent", {})
        _normalise_intent(intent_data)

        captions = result.get("captions", {})

        # ── Caption quality gate ───────────────────────────────────────────
        fb_caption = captions.get("facebook", "")
        fb_score   = score_caption(fb_caption)
        logger.info(f"FB caption score: {fb_score}/100")

        if fb_score < 55 and fb_caption:
            # One regeneration attempt with stricter hook+CTA instructions
            regen_prompt = (
                f"Rewrite this Facebook caption to score higher on engagement. "
                f"Requirements: (1) Start with a powerful non-generic hook — NOT 'BREAKING:'. "
                f"(2) Keep it under 80 words before hashtags. "
                f"(3) Keep the same hashtags. Return ONLY the improved caption text.\n\n"
                f"Original caption:\n{fb_caption}"
            )
            improved = _groq_plain_call(regen_prompt)
            if improved and improved.strip():
                captions["facebook"] = improved.strip()
                logger.info(f"Caption regenerated (was {fb_score}/100)")

        # ── Length optimisation ────────────────────────────────────────────
        if captions.get("facebook"):
            captions["facebook"] = optimize_length(captions["facebook"], max_words=100)
        if captions.get("instagram"):
            captions["instagram"] = optimize_length(captions["instagram"], max_words=80)
        if captions.get("telegram"):
            captions["telegram"] = optimize_length(captions["telegram"], max_words=120)

        # ── Guaranteed hashtag + CTA footer (never rely on LLM alone) ─────
        primary = intent_data.get("primary", "POLITICS")
        if captions.get("facebook"):
            captions["facebook"] = _ensure_fb_footer(captions["facebook"], primary)
        if captions.get("instagram"):
            captions["instagram"] = _ensure_ig_footer(captions["instagram"], primary)

        # ── Enforce image headline 8-word limit ───────────────────────────
        if captions.get("image_headline"):
            words = captions["image_headline"].split()
            if len(words) > 6:
                captions["image_headline"] = " ".join(words[:6])

        if captions.get("image_subtext"):
            raw_lines = captions["image_subtext"].replace("\\n", "\n").split("\n")[:2]
            trimmed = []
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                words = line.split()
                if len(words) > 12:
                    # Try to cut at last sentence boundary before word 12
                    chunk = " ".join(words[:12])
                    for punct in (".", ",", "—", "-"):
                        idx = chunk.rfind(punct)
                        if idx > len(chunk) // 2:
                            chunk = chunk[:idx].strip()
                            break
                    line = chunk
                trimmed.append(line)
            captions["image_subtext"] = "\n".join(trimmed) if trimmed else ""

        return {"intent": intent_data, "captions": captions}

    except Exception as e:
        logger.error(f"classify_and_generate failed: {e}. Raw: {raw}")
        return _fallback_result(article)


# ── Helpers ────────────────────────────────────────────────────────────────

_FB_FOOTER = {
    "WAR":           "#VisionaryMinds #BreakingNews #WorldNews",
    "POLITICS":      "#VisionaryMinds #BreakingNews #Politics",
    "ECONOMY":       "#VisionaryMinds #BreakingNews #Economy",
    "DISASTER":      "#VisionaryMinds #BreakingNews #Disaster",
    "HEALTH":        "#VisionaryMinds #BreakingNews #Health",
    "SPORTS":        "#VisionaryMinds #BreakingNews #Sports",
    "TECHNOLOGY":    "#VisionaryMinds #BreakingNews #Technology",
    "ENTERTAINMENT": "#VisionaryMinds #BreakingNews #Entertainment",
}

_IG_FOOTER = {
    "WAR":           "#VisionaryMinds #BreakingNews #WorldNews #WarNews #Conflict",
    "POLITICS":      "#VisionaryMinds #BreakingNews #WorldNews #Politics #CurrentAffairs",
    "ECONOMY":       "#VisionaryMinds #BreakingNews #WorldNews #Economy #Finance",
    "DISASTER":      "#VisionaryMinds #BreakingNews #WorldNews #Disaster #Emergency",
    "HEALTH":        "#VisionaryMinds #BreakingNews #WorldNews #Health #Outbreak",
    "SPORTS":        "#VisionaryMinds #BreakingNews #WorldNews #Sports #LiveScore",
    "TECHNOLOGY":    "#VisionaryMinds #BreakingNews #WorldNews #Technology #Tech",
    "ENTERTAINMENT": "#VisionaryMinds #BreakingNews #WorldNews #Entertainment #Bollywood",
}


def _ensure_fb_footer(caption: str, intent: str) -> str:
    """Guarantee the Facebook caption ends with brand hashtags."""
    footer = _FB_FOOTER.get(intent, _FB_FOOTER["POLITICS"])
    # Strip any existing hashtag block so we don't duplicate
    lines = caption.strip().split("\n")
    body_lines = [
        l for l in lines
        if not (l.strip().startswith("#") or all(w.startswith("#") for w in l.split() if w))
    ]
    body = "\n".join(body_lines).strip()
    return body + "\n\n" + footer


def _ensure_ig_footer(caption: str, intent: str) -> str:
    """Guarantee the Instagram caption ends with follow CTA + brand hashtags."""
    hashtags = _IG_FOOTER.get(intent, _IG_FOOTER["POLITICS"])
    cta = "Follow @VisionaryMinds for live updates 👇"
    lines = caption.strip().split("\n")
    body_lines = [
        l for l in lines
        if not (l.strip().startswith("#") or all(w.startswith("#") for w in l.split() if w))
        and cta not in l
    ]
    body = "\n".join(body_lines).strip()
    return body + "\n\n" + cta + "\n\n" + hashtags


def _normalise_intent(intent_data):
    """Normalise scores to sum to 1.0 and set ambiguous flag."""
    intents = intent_data.get("intents", [])
    if not intents:
        return

    total = sum(i.get("score", 0) for i in intents)
    if total > 0:
        for i in intents:
            i["score"] = round(i["score"] / total, 4)

    sorted_i  = sorted(intents, key=lambda x: x["score"], reverse=True)
    top_score = sorted_i[0]["score"] if sorted_i else 0
    intent_data["ambiguous"] = top_score < 0.50
    intent_data["primary"]   = sorted_i[0]["label"] if sorted_i else "POLITICS"
    intent_data["secondary"] = sorted_i[1]["label"] if len(sorted_i) > 1 else intent_data["primary"]


def _fallback_result(article):
    title = (article.get("title", "Breaking News") or "Breaking News")[:120]
    title_lower = title.lower()
    if any(w in title_lower for w in ["war", "attack", "bomb", "missile", "soldiers", "killed"]):
        hook_key = "WAR"
    elif any(w in title_lower for w in ["economy", "gdp", "inflation", "market", "trade", "imf"]):
        hook_key = "ECONOMY"
    elif any(w in title_lower for w in ["earthquake", "flood", "disaster", "emergency", "rescue"]):
        hook_key = "DISASTER"
    elif any(w in title_lower for w in ["virus", "disease", "outbreak", "pandemic", "vaccine", "ebola", "hospital", "health", "epidemic", "infection"]):
        hook_key = "HEALTH"
    elif any(w in title_lower for w in ["match", "cricket", "football", "sports", "goal", "wicket"]):
        hook_key = "SPORTS"
    elif any(w in title_lower for w in ["ai", "tech", "apple", "google", "phone", "software", "cyber", "robot"]):
        hook_key = "TECHNOLOGY"
    elif any(w in title_lower for w in ["bollywood", "film", "movie", "actor", "singer", "celebrity", "drama", "award"]):
        hook_key = "ENTERTAINMENT"
    else:
        hook_key = "POLITICS"
    hook = random.choice(_VIRAL_HOOKS[hook_key])
    return {
        "intent": {
            "intents":   [{"label": l, "score": round(1/len(INTENTS), 4)} for l in INTENTS],
            "primary":   "POLITICS",
            "secondary": "WAR",
            "ambiguous": True,
        },
        "captions": {
            "facebook": (
                f"{hook}\n\n"
                f"{title}\n\n"
                f"#BreakingNews #WorldNews #CurrentAffairs #MustRead #VisionaryMinds #VMUpdates"
            ),
            "instagram": (
                f"This story cannot be ignored 🔴\n\n"
                f"{title}\n\n"
                f"Follow @VisionaryMinds for live updates 👇\n\n"
                f"#BreakingNews #WorldNews #VisionaryMinds #VMUpdates #News #CurrentAffairs "
                f"#Trending #Viral #MustSee #TopStory #NewsAlert #LiveUpdates #GlobalNews "
                f"#InformationIsPower #StayInformed #Breaking #WorldUpdate #NowNews "
                f"#NewsOfTheDay #ImportantNews #MustRead #ShareThis #FollowForNews "
                f"#VMUpdates #VisionaryMinds"
            ),
            "telegram": (
                f"🔴 **BREAKING: {title}**\n\n"
                f"#BreakingNews #WorldNews #VisionaryMinds #VMUpdates"
            ),
        },
    }