import json
import logging
import os

logger = logging.getLogger(__name__)

INTENTS = ["WAR", "POLITICS", "ECONOMY", "DISASTER", "SPORTS"]

_SYSTEM_PROMPT = """\
You are a news classifier and social media writer. Given a news article, you must:
1. Classify it into exactly one of: WAR, POLITICS, ECONOMY, DISASTER, SPORTS
2. Write platform-specific captions for Facebook, Instagram, Twitter, and Telegram

Respond ONLY with valid JSON — no markdown fences, no commentary.\
"""

_INTENT_HASHTAGS = {
    "WAR":      "#Conflict #BreakingNews #WorldNews",
    "POLITICS": "#Politics #BreakingNews #WorldNews",
    "ECONOMY":  "#Economy #Finance #WorldNews",
    "DISASTER": "#Disaster #BreakingNews #WorldNews",
    "SPORTS":   "#Sports #Athletics #WorldNews",
}


def classify_and_generate(article, groq_client=None):
    """
    Single LLM call: intent classification + all 4 platform captions.
    Returns dict with keys: 'intent', 'captions'.
    """
    if groq_client is None:
        from groq import Groq
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    title = article.get("title", "")
    description = (article.get("summary", "") or article.get("description", "") or "")[:500]
    source = article.get("domain", "Unknown")
    intent_tags = " | ".join(
        f"{k}: {v}" for k, v in _INTENT_HASHTAGS.items()
    )

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
    "twitter":   "...",
    "telegram":  "..."
  }}
}}

RULES — Intent:
- All 5 scores must sum to exactly 1.0
- Set ambiguous=true if top score < 0.50
- primary = highest-score label; secondary = second-highest

RULES — Facebook caption (max 500 chars):
- Start: "BREAKING: {{one-sentence summary}}"
- 2-3 factual sentences, present tense, no speculation
- End with 3-5 hashtags including #VisionaryMinds #BreakingNews
- Do NOT include any URL or link
- Max 2 emojis, none in first line

RULES — Instagram caption (max 300 visible chars):
- Start: "BREAKING: {{summary}} 🔴"
- 1-2 punchy sentences, each on its own line
- Do NOT include any URL or link — no "link in bio", no article link
- 15-20 hashtags including #VisionaryMinds #BreakingNews #WorldNews
- Detect location → add as hashtag if found

RULES — Twitter caption (HARD LIMIT 280 chars total):
- Start: "🔴 BREAKING: {{max 15-word summary}}"
- 1 sentence context max
- End with MAX 2 hashtags including #VisionaryMinds
- Do NOT include any URL or link
- MUST be under 280 chars

RULES — Telegram caption (max 800 chars):
- Start: "🔴 **BREAKING: {{summary}}**"
- 3-4 factual sentences (most detailed version)
- Include who/what/where/when
- End with 3-5 hashtags including #VisionaryMinds #BreakingNews
- Do NOT include any URL or link
- Use **bold** for headline only

Intent hashtag reference: {intent_tags}
Brand tags always include: #VisionaryMinds #VMUpdates
"""

    raw = None
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)

        intent_data = result.get("intent", {})
        _normalise_intent(intent_data)

        captions = result.get("captions", {})
        captions = _validate_captions(captions, article, intent_data, groq_client)

        return {"intent": intent_data, "captions": captions}

    except Exception as e:
        logger.error(f"classify_and_generate failed: {e}. Raw: {raw}")
        return _fallback_result(article)


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalise_intent(intent_data):
    """Normalise scores so they sum to 1.0 and set ambiguous flag."""
    intents = intent_data.get("intents", [])
    if not intents:
        return

    total = sum(i.get("score", 0) for i in intents)
    if total > 0:
        for i in intents:
            i["score"] = round(i["score"] / total, 4)

    sorted_i = sorted(intents, key=lambda x: x["score"], reverse=True)
    top_score = sorted_i[0]["score"] if sorted_i else 0
    intent_data["ambiguous"] = top_score < 0.50
    intent_data["primary"]   = sorted_i[0]["label"] if sorted_i else "POLITICS"
    intent_data["secondary"] = sorted_i[1]["label"] if len(sorted_i) > 1 else intent_data["primary"]


def _validate_captions(captions, article, intent_data, groq_client):
    """Ensure Twitter caption fits within 280 chars."""
    twitter = captions.get("twitter", "")
    if len(twitter) > 280:
        captions["twitter"] = _trim_twitter(twitter, article, groq_client)
    return captions


def _trim_twitter(caption, article, groq_client):
    title = article.get("title", "")[:100]
    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You write ultra-concise tweets. Return ONLY the tweet text — no quotes, no URLs, no explanation.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Rewrite this tweet to be UNDER 280 characters. No URLs. Keep #VisionaryMinds and one other hashtag.\n\n"
                        f"Original: {caption}\nArticle: {title}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=120,
        )
        trimmed = resp.choices[0].message.content.strip()
        return trimmed[:280]
    except Exception:
        return caption[:277] + "..."


def _fallback_result(article):
    title = (article.get("title", "Breaking News") or "Breaking News")[:120]
    return {
        "intent": {
            "intents": [{"label": l, "score": 0.2} for l in INTENTS],
            "primary":   "POLITICS",
            "secondary": "WAR",
            "ambiguous": True,
        },
        "captions": {
            "facebook": (
                f"BREAKING: {title}\n\n"
                f"#BreakingNews #WorldNews #VisionaryMinds #VMUpdates"
            ),
            "instagram": (
                f"BREAKING: {title} 🔴\n\n"
                f"#BreakingNews #WorldNews #VisionaryMinds #VMUpdates #News #CurrentEvents"
            ),
            "twitter": (
                f"🔴 BREAKING: {title[:240]} #VisionaryMinds"
            )[:280],
            "telegram": (
                f"🔴 **BREAKING: {title}**\n\n"
                f"#BreakingNews #WorldNews #VisionaryMinds #VMUpdates"
            ),
        },
    }
