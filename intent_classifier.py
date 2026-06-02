import json
import logging
import os
import random

logger = logging.getLogger(__name__)

INTENTS = ["WAR", "POLITICS", "ECONOMY", "DISASTER", "SPORTS"]

# Topic label shown at the very top of every Facebook and Instagram caption
TOPIC_LABELS = {
    "WAR":      "⚔️ WAR & CONFLICT",
    "POLITICS": "🏛️ POLITICS",
    "ECONOMY":  "📈 ECONOMY",
    "DISASTER": "🚨 DISASTER ALERT",
    "SPORTS":   "🏆 SPORTS",
}

_SYSTEM_PROMPT = """\
You are a news classifier and social media writer. Given a news article, you must:
1. Classify it into exactly one of: WAR, POLITICS, ECONOMY, DISASTER, SPORTS
2. Write platform-specific captions for Facebook, Instagram, and Telegram

Respond ONLY with valid JSON — no markdown fences, no commentary.\
"""

_INTENT_HASHTAGS = {
    "WAR":      "#Conflict #BreakingNews #WorldNews #WarNews #GlobalCrisis #LiveUpdates #MustShare #UrgentNews",
    "POLITICS": "#Politics #BreakingNews #WorldNews #GlobalPolitics #CurrentAffairs #PoliticalNews #MustRead #TopStory",
    "ECONOMY":  "#Economy #Finance #WorldNews #MarketNews #Inflation #EconomicCrisis #MoneyMatters #MustKnow",
    "DISASTER": "#Disaster #BreakingNews #WorldNews #NaturalDisaster #EmergencyAlert #PrayersNeeded #HumanityFirst #UrgentNews",
    "SPORTS":   "#Sports #BreakingNews #WorldNews #Cricket #Football #PSL #SportsUpdate #GameChanger #MustWatch",
}

# Viral hook openers by intent — chosen randomly to avoid repetition
_VIRAL_HOOKS = {
    "WAR":      [
        "This is happening RIGHT NOW and the world needs to know:",
        "Nobody is talking about this — but they should be:",
        "This changes everything. Here is what is unfolding:",
        "URGENT: A situation the world cannot ignore is developing:",
    ],
    "POLITICS": [
        "A decision that will affect millions of people was just made:",
        "This is the political story everyone is watching right now:",
        "Something major just shifted on the global stage:",
        "Leaders just made a move that will impact your life:",
    ],
    "ECONOMY":  [
        "Your money, your future — this news matters to every family:",
        "The economic news you cannot afford to miss right now:",
        "A financial shift is happening — here is what you need to know:",
        "This economic development is affecting millions of people:",
    ],
    "DISASTER": [
        "Prayers and thoughts needed — a crisis is unfolding:",
        "This is devastating. Here is what is happening right now:",
        "Lives are at stake. Share this so the world responds:",
        "A tragedy is unfolding — the world must see this:",
    ],
    "SPORTS":   [
        "A major development just emerged from the sporting world:",
        "Here is what unfolded in today's match:",
        "A significant result has been recorded:",
        "The latest from today's live fixture:",
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
    source      = article.get("domain", "Unknown")
    intent_tags = " | ".join(f"{k}: {v}" for k, v in _INTENT_HASHTAGS.items())

    user_prompt = f"""\
Article Title: {title}
Article Description: {description}
Source Domain: {source}

Classify this article and generate captions. Return ONLY this JSON structure:

{{
  "intent": {{
    "intents": [
      {{"label": "WAR",      "score": 0.00}},
      {{"label": "POLITICS", "score": 0.00}},
      {{"label": "ECONOMY",  "score": 0.00}},
      {{"label": "DISASTER", "score": 0.00}},
      {{"label": "SPORTS",   "score": 0.00}}
    ],
    "primary": "LABEL",
    "secondary": "LABEL",
    "ambiguous": false
  }},
  "captions": {{
    "facebook":      "...",
    "instagram":     "...",
    "telegram":      "...",
    "image_headline": "..."
  }}
}}

RULES — Intent:
- All 5 scores must sum to exactly 1.0
- Set ambiguous=true if top score < 0.50
- primary = highest-score label; secondary = second-highest

RULES — Image Headline (overlay text printed on the image, max 8 words):
- Write 5-8 plain words that state the single most important fact
- Simple words — write as if telling a friend what happened
- No emojis, no hashtags, no punctuation at the end
- Good examples: "Storm Delays Gujarat Titans Arrival in Ahmedabad" / "Trump Cancels US 250th Anniversary Concerts"
- Bad examples: anything over 8 words, anything with hashtags or emojis

RULES — Facebook caption (max 480 chars):
GOAL: Easy to read, easy to share. Write in simple plain English — like a knowledgeable friend explaining the news.
- Line 1 (TOPIC LABEL): Start with:
  WAR → "⚔️ WAR & CONFLICT |"  POLITICS → "🏛️ POLITICS |"
  ECONOMY → "📈 ECONOMY |"       DISASTER → "🚨 DISASTER ALERT |"  SPORTS → "🏆 SPORTS |"
  Then write one clear sentence about what happened. Example: "🏆 SPORTS | The match was delayed because of a sudden storm."
- Lines 2-3: 2 short, simple sentences. Use easy words. Say who, what, where.
- Final line: 5-8 hashtags including #VisionaryMinds #BreakingNews and topic-specific tags from: {intent_tags}
- No URLs. Max 2 emojis.

RULES — Instagram caption (max 300 visible chars + hashtags):
- Write in simple, easy-to-understand English. Short sentences. Clear words.
- Line 1: Topic label + one clear sentence about what happened
  e.g. "🏆 SPORTS 🔴 Gujarat Titans flight was delayed due to a storm."
- Lines 2-3: 2 short simple facts on separate lines
- Add: "Follow @VisionaryMinds for live updates 👇"
- Do NOT include any URL or link
- 25-30 hashtags including #VisionaryMinds #BreakingNews #WorldNews #News #CurrentAffairs #Trending #Viral #MustSee #TopStory
- Add location hashtags if a country/city is mentioned
- Add topic-specific tags from: {intent_tags}

RULES — Telegram caption (max 800 chars):
- Start: "🔴 **BREAKING: {{one sentence summary}}**"
- 3-4 factual sentences in simple plain English. Include who/what/where/when.
- End with 3-5 hashtags including #VisionaryMinds #BreakingNews
- Do NOT include any URL or link
- Use **bold** for the opening headline only

Brand tags always include: #VisionaryMinds #VMUpdates
{f"Trending now — weave these into hashtags if relevant: {trending_context}" if trending_context else ""}
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
            captions["facebook"] = optimize_length(captions["facebook"], max_words=80)
        if captions.get("instagram"):
            captions["instagram"] = optimize_length(captions["instagram"], max_words=60)
        if captions.get("telegram"):
            captions["telegram"] = optimize_length(captions["telegram"], max_words=120)

        # ── Enforce image headline 8-word limit ───────────────────────────
        if captions.get("image_headline"):
            words = captions["image_headline"].split()
            if len(words) > 8:
                captions["image_headline"] = " ".join(words[:8])

        return {"intent": intent_data, "captions": captions}

    except Exception as e:
        logger.error(f"classify_and_generate failed: {e}. Raw: {raw}")
        return _fallback_result(article)


# ── Helpers ────────────────────────────────────────────────────────────────

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
    elif any(w in title_lower for w in ["match", "cricket", "football", "sports", "goal", "wicket"]):
        hook_key = "SPORTS"
    else:
        hook_key = "POLITICS"
    hook = random.choice(_VIRAL_HOOKS[hook_key])
    return {
        "intent": {
            "intents":   [{"label": l, "score": 0.2} for l in INTENTS],
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