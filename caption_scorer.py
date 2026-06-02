"""
Caption Strength Scorer + Length Optimizer — pure Python, zero cost.

Scores a Facebook caption 0-100 on predicted engagement quality.
A score < 55 triggers one automatic regeneration attempt via Groq.

Also trims Facebook captions that are too long (> 80 words lose reach
because Facebook collapses them behind "See More" before the CTA).
"""

import re as _re

_EMOTIONAL = {
    "shocking", "devastating", "urgent", "critical", "historic", "massive",
    "record", "worst", "biggest", "first", "unprecedented", "crisis",
    "breaking", "exposed", "scandal", "leaked", "collapse", "tragedy",
    "emergency", "catastrophic", "alarming",
}

_CTA_PATTERNS = ["share", "tag", "comment", "react", "drop a", "let us know",
                 "tell us", "what do you think", "spread the word"]

_GENERIC_HOOKS = [
    "breaking:", "breaking news:", "in a major", "in a significant",
    "in a new development", "according to reports",
]


def score_caption(caption: str) -> int:
    """Return 0-100 quality score for a Facebook caption."""
    if not caption:
        return 0

    text  = caption.lower()
    lines = caption.strip().split("\n")
    first = lines[0].lower() if lines else ""
    words = caption.split()

    score = 0

    # Hook quality: first line is not a generic opener
    if not any(g in first for g in _GENERIC_HOOKS):
        score += 20

    # CTA present — use word-boundary matching to avoid false positives
    # (e.g. "react" inside "reaction", "tag" inside "pentagon")
    if any(
        _re.search(rf"\b{_re.escape(c)}\b", text)
        for c in _CTA_PATTERNS
    ):
        score += 25

    # Emotional / high-arousal words
    word_set = set(_re.findall(r'\b\w+\b', text))
    if word_set & _EMOTIONAL:
        score += 20

    # Optimal length: 40-80 words (visible before Facebook's "See More")
    wc = len(words)
    if 40 <= wc <= 80:
        score += 20
    elif wc < 40:
        score += 10
    # > 80 words: no length bonus (CTA might be hidden)

    # Numbers signal concrete facts
    if _re.search(r'\b\d+\b', caption):
        score += 10

    # Hashtags present
    if "#" in caption:
        score += 5

    return min(100, score)


def optimize_length(caption: str, max_words: int = 80) -> str:
    """
    Trim a Facebook caption so the CTA and hook are never hidden behind
    Facebook's 'See More' button (triggered around 80 words).
    Preserves hashtag block at the end.
    """
    # Separate hashtag block from body
    lines = caption.strip().split("\n")
    hashtag_lines, body_lines = [], []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("#") or all(
            w.startswith("#") for w in stripped.split() if w
        ):
            hashtag_lines.insert(0, line)
        else:
            body_lines.insert(0, line)
    # If everything ended up in body, just work with the full text
    if not body_lines:
        body_lines = hashtag_lines
        hashtag_lines = []

    body = "\n".join(body_lines).strip()
    words = body.split()

    if len(words) <= max_words:
        # Already within limit
        if hashtag_lines:
            return body + "\n\n" + "\n".join(hashtag_lines)
        return caption

    # Trim to last complete sentence ending before max_words
    trimmed = " ".join(words[:max_words])
    for punct in (".", "!", "?"):
        idx = trimmed.rfind(punct)
        if idx > len(trimmed) // 2:           # found one in the second half
            trimmed = trimmed[:idx + 1]
            break

    result = trimmed
    if hashtag_lines:
        result += "\n\n" + "\n".join(hashtag_lines)
    return result
