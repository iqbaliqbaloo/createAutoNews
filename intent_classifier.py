import json
import logging
import os

logger = logging.getLogger(__name__)

INTENTS = ["WAR", "POLITICS", "ECONOMY", "DISASTER", "SPORTS"]

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

    import random
    primary_guess = title  # will be refined by LLM; used only to pick a hook sample
    hook_samples  = "\n".join(f'  "{h}"' for h in list(_VIRAL_HOOKS.values())[0][:2])

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
    "facebook":  "...",
    "instagram": "...",
    "telegram":  "..."
  }}
}}

RULES — Intent:
- All 5 scores must sum to exactly 1.0
- Set ambiguous=true if top score < 0.50
- primary = highest-score label; secondary = second-highest

RULES — Facebook caption (MAXIMUM ORGANIC REACH — max 480 chars):
GOAL: Make people STOP scrolling, REACT, COMMENT, and SHARE. Facebook's algorithm pushes posts to non-followers when engagement is high in the first hour.
- Line 1 (HOOK): Write a powerful news-style opening sentence that reports the key development. Do NOT start with "BREAKING:". Write as a news broadcaster, NOT as someone addressing an audience. NEVER use phrases like "fans need to know", "you need to see this", "every [X] fan", "don't miss this", or any language that targets or addresses a specific group of people. Examples: "A major political shift is unfolding as leaders reach a historic agreement." or "A powerful earthquake has struck, leaving thousands displaced."
- Line 2-3: 2 punchy factual sentences in present tense that reveal the key facts
- Line 4 (CTA): End with ONE of these share calls-to-action (vary it): "Share this so your friends are informed." / "Tag someone who needs to see this." / "Share this — everyone deserves to know." / "Drop a reaction if this shocked you."
- Final line: 5-8 hashtags including #VisionaryMinds #BreakingNews and 3-4 topic-specific tags from: {intent_tags}
- No URLs. Max 2 emojis, never in line 1.

RULES — Instagram caption (max 300 visible chars + hashtags):
- Line 1: Short punchy hook ending with 🔴 emoji
- 2 short punchy sentences on separate lines
- Add: "Follow @VisionaryMinds for live updates 👇"
- Do NOT include any URL or link
- 25-30 hashtags including #VisionaryMinds #BreakingNews #WorldNews #News #CurrentAffairs #Trending #Viral #MustSee #TopStory
- Add location-specific hashtags if a country/city is mentioned
- Detect intent → add from: {intent_tags}

RULES — Telegram caption (max 800 chars):
- Start: "🔴 **BREAKING: {{summary}}**"
- 3-4 factual sentences (most detailed version)
- Include who/what/where/when
- End with 3-5 hashtags including #VisionaryMinds #BreakingNews
- Do NOT include any URL or link
- Use **bold** for headline only

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
                f"(2) Include an explicit share CTA like 'Share this so your friends know.' "
                f"(3) Keep it under 80 words before hashtags. "
                f"(4) Keep the same hashtags. Return ONLY the improved caption text.\n\n"
                f"Original caption:\n{fb_caption}"
            )
            improved = _groq_call(regen_prompt, groq_client)
            if improved and improved.strip():
                captions["facebook"] = improved.strip()
                logger.info(f"Caption regenerated (was {fb_score}/100)")

        # ── Length optimisation ────────────────────────────────────────────
        if captions.get("facebook"):
            captions["facebook"] = optimize_length(captions["facebook"], max_words=80)

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
    import random
    title = (article.get("title", "Breaking News") or "Breaking News")[:120]
    hook  = random.choice(_VIRAL_HOOKS["POLITICS"])
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
                f"Share this so your friends are informed.\n\n"
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
