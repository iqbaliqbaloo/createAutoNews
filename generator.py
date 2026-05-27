import os, re, json, time, requests, random, tempfile, textwrap
from groq import Groq, RateLimitError
from langdetect import detect
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from clip_validator import image_matches_text

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


def _shadow_text(draw, pos, text, font, fill="white"):
    x, y = pos
    for dx, dy in [(-1,-1),(1,-1),(-1,1),(1,1),(0,2)]:
        draw.text((x+dx, y+dy), text, fill="black", font=font)
    draw.text((x, y), text, fill=fill, font=font)


# ─── LANGUAGE DETECTION ──────────────────────────────────

def detect_language(article):
    try:
        text = (article.get("title","") + " " + article.get("summary","")).strip()
        return detect(text) if text else "en"
    except:
        return "en"


# ─── SAFE JSON PARSER ────────────────────────────────────

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
    return "3-5 sentences short update"


# ─── IMAGE OVERLAY ───────────────────────────────────────

def add_text_overlay(image_path, headline, source_type="world", is_breaking=False):
    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((1200, 630), Image.LANCZOS)
        w, h = img.size

        accent = (0,160,72) if source_type == "pakistan" else (210,30,30)
        tag    = "PAKISTAN NEWS" if source_type == "pakistan" else "WORLD NEWS"

        font_tag = _load_font(22, True)
        font_h   = _load_font(44, True)

        draw = ImageDraw.Draw(img)

        # top bar
        draw.rectangle([(0,0),(w,50)], fill=(0,0,0))
        draw.text((20,12), tag, fill=accent, font=font_tag)

        if is_breaking:
            draw.text((250,12), "BREAKING", fill=(255,0,0), font=font_tag)

        # headline
        y = h - 200
        wrapped = textwrap.wrap(headline, width=38)[:3]

        for line in wrapped:
            _shadow_text(draw, (20, y), line, font_h)
            y += 55

        out = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(out.name, "JPEG", quality=95)

        return out.name

    except Exception as e:
        print("Overlay error:", e)
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

    title   = article.get("title","")
    summary = article.get("summary","")
    source  = article.get("source_type","world")

    lang = detect_language(article)
    instruction = "Translate to English" if lang != "en" else "English article"

    score = article.get("score", 50)
    level = article.get("level", 3)

    post_length = get_post_length(score, level)

    prompt = f"""
Write professional news post.

TITLE: {title}
DETAILS: {summary[:600]}
SOURCE: {source}
{instruction}

RULES:
- factual only
- strong opening line
- {post_length}
- hashtags at end
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

                if result and result.get("post_text"):
                    return result

            except RateLimitError:
                break
            except:
                time.sleep(2)

    # fallback
    return {
        "post_text": f"{title}\n\n{summary[:200]}",
        "image_keywords": "news update world report",
        "image_headline": title[:80]
    }


# ─── IMAGE GENERATION (FIXED + CLIP CHECK) ───────────────

def generate_image(keywords, headline, source_type="world", is_breaking=False):

    clean = keywords.lower()
    clean = re.sub(r"\b(news|breaking|media|photo|image|scene)\b", "", clean)
    clean = " ".join(clean.split())

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
            hits = data.get("hits", [])

            if not hits:
                continue

            # ── CLIP FILTER ──
            best_url = None
            for h in hits[:5]:
                url = h["largeImageURL"]
                if image_matches_text(url, headline):
                    best_url = url
                    break

            if not best_url:
                continue

            img_data = requests.get(best_url, timeout=15).content

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(img_data)
            tmp.close()

            return add_text_overlay(tmp.name, headline, source_type, is_breaking)

        except Exception as e:
            print("Image error:", e)
            continue

    return None