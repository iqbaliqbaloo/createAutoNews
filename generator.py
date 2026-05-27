import os, re, json, time, requests, random, tempfile, textwrap
from groq import Groq, RateLimitError
from langdetect import detect
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# ─── GROQ CLIENTS ─────────────────────────────────────────

_key_1 = (os.getenv("GROQ_API_KEY") or "").strip()
_key_2 = (os.getenv("GROQ_API_KEY_2") or "").strip()

_client_1 = Groq(api_key=_key_1) if _key_1 else None
_client_2 = Groq(api_key=_key_2) if _key_2 else None


# ─── FONT SETUP ───────────────────────────────────────────

_FONT_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "arialbd.ttf",
]

_FONT_REGULAR = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "arial.ttf",
]


def _load_font(size, bold=False):
    for path in (_FONT_BOLD if bold else _FONT_REGULAR):
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def _text_width(draw, text, font):
    try:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0]
    except:
        return draw.textsize(text, font=font)[0]


def _draw_rounded_rect(draw, bbox, radius, fill):
    try:
        draw.rounded_rectangle(bbox, radius=radius, fill=fill)
    except:
        draw.rectangle(bbox, fill=fill)


def _shadow_text(draw, pos, text, font, fill="white", shadow=(0, 0, 0)):
    x, y = pos
    for dx, dy in [(-1,-1),(1,-1),(-1,1),(1,1),(0,2),(2,0)]:
        draw.text((x+dx, y+dy), text, fill=shadow, font=font)
    draw.text((x, y), text, fill=fill, font=font)


# ─── LANGUAGE DETECTION ──────────────────────────────────

def detect_language(article):
    try:
        text = (article.get("title","") + " " + article.get("summary","")).strip()
        return detect(text) if text else "en"
    except:
        return "en"


# ─── SAFE HELPERS ─────────────────────────────────────────

def safe_get(article, key, default=""):
    return article.get(key, default) or default


def safe_json(text):
    try:
        text = re.sub(r"```json|```", "", text)
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except:
        return None


# ─── POST LENGTH RULE ────────────────────────────────────

def get_post_length(score, level):
    if level == 1:
        return "6-10 sentences major breaking news"
    elif level == 2:
        return "5-7 sentences important news"
    else:
        return "3-5 sentences short update"


# ─── IMAGE OVERLAY ───────────────────────────────────────

def add_text_overlay(image_path, headline, source_type="world", is_breaking=False):
    tmp_path = None
    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((1200, 630), Image.LANCZOS)
        w, h = img.size

        accent = (0,160,72) if source_type == "pakistan" else (210,30,30)
        tag    = "PAKISTAN NEWS" if source_type == "pakistan" else "WORLD NEWS"

        font_tag = _load_font(22, True)
        font_h   = _load_font(46, True)

        draw = ImageDraw.Draw(img)

        draw.rectangle([(0,0),(w,50)], fill=(0,0,0))

        draw.text((20, 12), tag, fill=accent, font=font_tag)

        if is_breaking:
            draw.text((250, 12), "BREAKING", fill=(255,0,0), font=font_tag)

        y = h - 200
        wrapped = textwrap.wrap(headline, width=40)[:3]

        for line in wrapped:
            _shadow_text(draw, (20, y), line, font_h)
            y += 55

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp_path = out.name
        img.save(tmp_path, "JPEG", quality=95)
        out.close()

        return tmp_path

    except:
        return image_path


# ─── GROQ CALL ───────────────────────────────────────────

def _call_groq(client, prompt):
    r = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=600,
    )
    return r.choices[0].message.content


# ─── MAIN POST GENERATOR ─────────────────────────────────

def generate_post(article):

    if not article:
        return None

    title   = safe_get(article, "title")
    summary = safe_get(article, "summary")
    source  = article.get("source_type", "world")

    if not title or not summary:
        return None

    lang = detect_language(article)

    instruction = "Translate to English if needed." if lang != "en" else "English article."

    score = article.get("score", 50)
    level = article.get("level", 3)

    post_length = get_post_length(score, level)

    source_label = "Pakistan" if source == "pakistan" else "World"

    prompt = f"""
Write a professional news post.

TITLE: {title}
DETAILS: {summary[:600]}
SOURCE: {source_label}
{instruction}

RULES:
- factual only
- strong opening line
- {post_length}
- hashtags at end (5-7)
- no fake info

Return JSON ONLY:
{{
 "post_text": "...",
 "image_keywords": "...",
 "image_headline": "..."
}}
"""

    providers = [("Groq-1", _client_1), ("Groq-2", _client_2)]

    for name, client in providers:
        if not client:
            continue

        for _ in range(2):
            try:
                text = _call_groq(client, prompt)
                result = safe_json(text)

                if not result:
                    continue

                if not result.get("post_text"):
                    continue

                return result

            except RateLimitError:
                break
            except:
                time.sleep(2)

    # fallback (IMPORTANT)
    return {
        "post_text": f"{title}\n\n{summary[:200]}",
        "image_keywords": "news update world report",
        "image_headline": title[:80]
    }


# ─── IMAGE GENERATION ────────────────────────────────────

def generate_image(keywords, headline, source_type="world", is_breaking=False):

    clean = keywords.lower()

    clean = re.sub(r"\b(news|breaking|media|photo|image|scene)\b", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    words = clean.split()

    search_terms = []

    if len(words) >= 3:
        search_terms.append(" ".join(words[:3]))

    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))

    if words:
        search_terms.append(words[0])

    search_terms.append(
        "pakistan protest crowd" if source_type == "pakistan"
        else "global crisis war news"
    )

    for term in search_terms:

        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": os.getenv("PIXABAY_API_KEY"),
                    "q": term,
                    "image_type": "photo",
                    "per_page": 10,
                    "safesearch": "true"
                },
                timeout=10
            )

            data = r.json()
            if not data.get("hits"):
                continue

            hit = data["hits"][0]   # FIXED (no randomness)

            img_url = hit["largeImageURL"]

            img_data = requests.get(img_url, timeout=15).content

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(img_data)
            tmp.close()

            return add_text_overlay(tmp.name, headline, source_type, is_breaking)

        except:
            continue

    return None