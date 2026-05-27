import os
import re
import requests
import tempfile
from dotenv import load_dotenv
from PIL import Image, ImageDraw

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
# POST GENERATOR (FIXED)
# ─────────────────────────────
def generate_post(article):

    title = article.get("title", "")
    summary = article.get("summary", "")
    source = article.get("source_type", "world")

    if not title or not summary:
        return None

    return {
        "post_text": f"{title}\n\n{summary[:300]}...",
        "image_keywords": f"{title} {summary[:120]}",
        "image_headline": title,
        "source_type": source
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
def add_text_overlay(image_path, headline, source_type="world", is_breaking=False):

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((1200, 630))

        draw = ImageDraw.Draw(img)

        tag = "PAKISTAN NEWS" if source_type == "pakistan" else "WORLD NEWS"
        color = (0, 160, 72) if source_type == "pakistan" else (210, 30, 30)

        draw.rectangle([(0, 0), (1200, 50)], fill=(0, 0, 0))
        draw.text((20, 15), tag, fill=color)

        if is_breaking:
            draw.text((250, 15), "BREAKING", fill=(255, 0, 0))

        draw.text((40, 500), headline[:100], fill="white")

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

    # fallback image (always safe)
    img = Image.new("RGB", (1200, 630), (20, 20, 20))
    draw = ImageDraw.Draw(img)
    draw.text((50, 300), headline[:100], fill="white")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    img.save(tmp.name, "JPEG", quality=95)

    return tmp.name