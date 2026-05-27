import os
import re
import requests
import tempfile
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

# ─────────────────────────────
# CLIP MODEL (LOAD ONCE)
# ─────────────────────────────
clip_model = SentenceTransformer("clip-ViT-B-32")


# ─────────────────────────────
# CLIP SCORE (FIXED)
# ─────────────────────────────
def clip_score(text, image_path):
    try:
        if not image_path or not os.path.exists(image_path):
            return 0.0

        # CLIP text encoder hard limit is 77 tokens; ~50 words stays safely under it
        text = " ".join(text.split()[:50])

        img = Image.open(image_path).convert("RGB")

        text_emb = clip_model.encode([text])
        img_emb = clip_model.encode([img])

        score = cosine_similarity(text_emb, img_emb)[0][0]
        return float(score)

    except Exception as e:
        print("CLIP error:", e)
        return 0.0


# ─────────────────────────────
# GROQ-POWERED POST GENERATOR
# ─────────────────────────────
def _generate_with_groq(title, summary, source):
    keys = [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY_2")]
    for key in keys:
        if not key:
            continue
        try:
            from groq import Groq
            client = Groq(api_key=key)
            tag = "Pakistan" if source == "pakistan" else "World"
            resp = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Write a short, engaging Facebook post about this {tag} news story.\n"
                        f"Rules:\n"
                        f"- 2-3 sentences only\n"
                        f"- Open with a strong attention-grabbing hook\n"
                        f"- Include the key facts\n"
                        f"- End with 4-5 relevant hashtags including #VisionaryMinds\n"
                        f"- No emojis\n"
                        f"- Plain text only\n\n"
                        f"Title: {title}\n"
                        f"Summary: {summary[:250]}"
                    )
                }],
                max_tokens=220,
                temperature=0.7,
            )
            text = resp.choices[0].message.content.strip()
            if text:
                return text
        except Exception as e:
            print(f"Groq error: {e}")
    return None


def generate_post(article):

    title   = article.get("title", "")
    summary = article.get("summary", "")
    source  = article.get("source_type", "world")

    if not title or not summary:
        return None

    post_text = _generate_with_groq(title, summary, source)

    if not post_text:
        tag   = "#PakistanNews" if source == "pakistan" else "#WorldNews"
        short = summary[:200].rsplit(" ", 1)[0]
        post_text = (
            f"{title}\n\n"
            f"{short}...\n\n"
            f"{tag} #BreakingNews #VisionaryMinds"
        )

    return {
        "post_text":      post_text,
        "image_keywords": f"{title} {summary[:80]}",
        "image_headline": title,
        "source_type":    source,
    }


# ─────────────────────────────
# SAFE IMAGE DOWNLOAD (IMPORTANT FIX)
# ─────────────────────────────
def safe_download(url):
    try:
        r = requests.get(url, timeout=15)

        # ❌ reject bad responses
        if r.status_code != 200:
            return None

        # ❌ reject HTML / tiny files
        if len(r.content) < 10000:
            return None

        # ❌ extra validation (prevents corrupted jpg)
        if b"<html" in r.content[:200] or b"<HTML" in r.content[:200]:
            return None

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(r.content)
        tmp.close()

        return tmp.name

    except Exception as e:
        print("Download error:", e)
        return None


# ─────────────────────────────
# IMAGE OVERLAY
# ─────────────────────────────
def _load_fonts():
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, 28), ImageFont.truetype(p, 44)
        except OSError:
            continue
    return ImageFont.load_default(), ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        w = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines[:3]


def add_text_overlay(image_path, headline, source_type="world", is_breaking=False):

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((1200, 630))

        font_tag, font_headline = _load_fonts()

        brand_color = (0, 160, 72) if source_type == "pakistan" else (210, 30, 30)
        tag = "PAKISTAN NEWS" if source_type == "pakistan" else "WORLD NEWS"

        # ── semi-transparent dark gradient at bottom ──────────────
        rgba = img.convert("RGBA")
        overlay = Image.new("RGBA", (1200, 630), (0, 0, 0, 0))
        ov = ImageDraw.Draw(overlay)
        ov.rectangle([(0, 390), (1200, 630)], fill=(0, 0, 0, 185))
        img = Image.alpha_composite(rgba, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── top bar ───────────────────────────────────────────────
        draw.rectangle([(0, 0), (1200, 58)], fill=(0, 0, 0))
        draw.text((20, 14), tag, fill=brand_color, font=font_tag)

        if is_breaking:
            draw.text((310, 14), "● BREAKING", fill=(255, 80, 80), font=font_tag)

        # VisionaryMinds — right-aligned in top bar
        vm = "VisionaryMinds"
        vm_w = draw.textbbox((0, 0), vm, font=font_tag)[2]
        draw.text((1200 - vm_w - 20, 14), vm, fill=(255, 255, 255), font=font_tag)

        # ── wrapped headline at bottom ────────────────────────────
        lines = _wrap_text(draw, headline, font_headline, 1120)
        y = 415
        for line in lines:
            draw.text((40, y), line, fill="white", font=font_headline)
            y += 54

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(tmp.name, "JPEG", quality=95)
        return tmp.name

    except Exception as e:
        print("Overlay error:", e)
        return image_path


# ─────────────────────────────
# IMAGE GENERATION (FINAL FIXED VERSION)
# ─────────────────────────────
def generate_image(keywords, headline, source_type="world", is_breaking=False):

    clean = keywords.lower()
    clean = re.sub(r"\b(news|breaking|photo|image|scene|report)\b", "", clean)
    words = clean.split()

    search_terms = []

    if len(words) >= 3:
        search_terms.append(" ".join(words[:3]))

    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))

    if words:
        search_terms.append(words[0])

    # smart fallback queries
    search_terms.extend([
        "war news crowd protest",
        "breaking news city",
        "global crisis report" if source_type == "world" else "pakistan crowd protest"
    ])

    best_img = None
    best_score = 0.0
    done = False

    for term in search_terms:
        if done:
            break

        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": os.getenv("PIXABAY_API_KEY"),
                    "q": term,
                    "image_type": "photo",
                    "per_page": 5,
                    "safesearch": "true"
                },
                timeout=10
            )

            data = r.json()
            hits = data.get("hits", [])

            for hit in hits:

                img_url = hit.get("largeImageURL")
                if not img_url:
                    continue

                img_path = safe_download(img_url)
                if not img_path:
                    continue

                score = clip_score(keywords + " " + headline, img_path)

                print(f"CLIP score: {score}")

                if score > best_score:
                    # discard previous best before replacing it
                    if best_img:
                        try:
                            os.unlink(best_img)
                        except OSError:
                            pass
                    best_score = score
                    best_img = img_path
                else:
                    # this download lost — clean it up now
                    try:
                        os.unlink(img_path)
                    except OSError:
                        pass

                if best_score >= 0.35:
                    done = True
                    break

        except Exception as e:
            print("Image search error:", e)

    # ─────────────────────────────
    # FINAL DECISION RULE
    # ─────────────────────────────
    if best_img and best_score >= 0.20:
        result = add_text_overlay(best_img, headline, source_type, is_breaking)
        try:
            os.unlink(best_img)
        except OSError:
            pass
        return result

    if best_img:
        try:
            os.unlink(best_img)
        except OSError:
            pass

    print("❌ No good match → fallback image")

    # dark slate background — still gets the full overlay treatment
    img = Image.new("RGB", (1200, 630), (20, 20, 20))
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    img.save(tmp.name, "JPEG", quality=95)

    return add_text_overlay(tmp.name, headline, source_type, is_breaking)