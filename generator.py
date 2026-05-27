import os
import re
import time
import requests
import tempfile
from dotenv import load_dotenv
from PIL import Image, ImageDraw

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

# ─────────────────────────────────────────────
# CLIP MODEL
# ─────────────────────────────────────────────
clip_model = SentenceTransformer("clip-ViT-B-32")

GRAPH_URL = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────
# CLIP SCORE (SAFE)
# ─────────────────────────────────────────────
def clip_score(text, image_path):
    try:
        img = Image.open(image_path).convert("RGB")

        text_emb = clip_model.encode([text])
        img_emb = clip_model.encode([img])

        score = cosine_similarity(text_emb, img_emb)[0][0]
        return float(score)

    except Exception as e:
        print("CLIP error:", e)
        return 0.0


# ─────────────────────────────────────────────
# FALLBACK IMAGE (IMPORTANT FIX)
# ─────────────────────────────────────────────
def fallback_image(headline):
    img = Image.new("RGB", (1200, 630), (25, 25, 25))
    draw = ImageDraw.Draw(img)

    draw.text((50, 250), headline[:80], fill="white")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    img.save(tmp.name, "JPEG", quality=95)

    return tmp.name


# ─────────────────────────────────────────────
# IMAGE DOWNLOAD SAFE
# ─────────────────────────────────────────────
def safe_download(url):
    try:
        r = requests.get(url, timeout=15)

        if r.status_code != 200:
            return None

        if len(r.content) < 8000:
            return None

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(r.content)
        tmp.close()

        return tmp.name

    except:
        return None


# ─────────────────────────────────────────────
# IMAGE OVERLAY
# ─────────────────────────────────────────────
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

    except:
        return image_path


# ─────────────────────────────────────────────
# MAIN IMAGE GENERATION (FIXED LOGIC)
# ─────────────────────────────────────────────
def generate_image(keywords, headline, source_type="world", is_breaking=False):

    clean = keywords.lower()
    clean = re.sub(r"\b(news|breaking|photo|image|scene)\b", "", clean)
    words = clean.split()

    search_terms = []

    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))

    if words:
        search_terms.append(words[0])

    search_terms.append(
        "war protest news crowd"
        if source_type == "world"
        else "pakistan protest crowd"
    )

    best_img = None
    best_score = -1

    # ─────────────────────────────
    # SEARCH LOOP (FIXED)
    # ─────────────────────────────
    for term in search_terms:

        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": os.getenv("PIXABAY_API_KEY"),
                    "q": term,
                    "image_type": "photo",
                    "per_page": 3,
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

                # keep best match
                if score > best_score:
                    best_score = score
                    best_img = img_path

                # early stop if good enough
                if best_score > 0.30:
                    break

        except Exception as e:
            print("Image fetch error:", e)

    # ─────────────────────────────
    # FINAL DECISION (IMPORTANT FIX)
    # ─────────────────────────────
    threshold = 0.18 if source_type == "world" else 0.20

    if best_img and best_score >= threshold:
        return add_text_overlay(best_img, headline, source_type, is_breaking)

    print("❌ No good match → using fallback image")
    return fallback_image(headline)