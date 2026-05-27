import os
import re
import json
import time
import requests
import tempfile
import textwrap
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

# ─────────────────────────────────────────────
# CLIP MODEL (GLOBAL LOAD)
# ─────────────────────────────────────────────
clip_model = SentenceTransformer("clip-ViT-B-32")

GRAPH_URL = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────
# CLIP SCORE (FIXED + STABLE)
# ─────────────────────────────────────────────
def clip_score(text, image_path):
    try:
        image = Image.open(image_path).convert("RGB")

        text_emb = clip_model.encode([text], convert_to_tensor=True)
        img_emb  = clip_model.encode([image], convert_to_tensor=True)

        score = cosine_similarity(
            text_emb.cpu().numpy(),
            img_emb.cpu().numpy()
        )[0][0]

        return float(score)

    except Exception as e:
        print(f"CLIP error: {e}")
        return 0.0


# ─────────────────────────────────────────────
# IMGBB UPLOAD
# ─────────────────────────────────────────────
def upload_to_imgbb(image_path, retries=3):

    if not image_path or not os.path.exists(image_path):
        return None

    api_key = os.getenv("IMGBB_API_KEY")
    if not api_key:
        print("❌ IMGBB key missing")
        return None

    for attempt in range(retries):
        try:
            print(f"  imgbb upload attempt {attempt+1}...")

            with open(image_path, "rb") as f:
                r = requests.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        "key": api_key,
                        "expiration": 3600
                    },
                    files={"image": f},
                    timeout=30
                )

            data = r.json()

            if data.get("success"):
                print("  imgbb upload success")
                return data["data"]["url"]

        except Exception as e:
            print(f"  imgbb error: {e}")
            time.sleep(2)

    return None


# ─────────────────────────────────────────────
# IMAGE OVERLAY
# ─────────────────────────────────────────────
def add_text_overlay(image_path, headline, source_type="world", is_breaking=False):

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((1200, 630), Image.LANCZOS)

        draw = ImageDraw.Draw(img)

        accent = (0,160,72) if source_type == "pakistan" else (210,30,30)
        tag = "PAKISTAN NEWS" if source_type == "pakistan" else "WORLD NEWS"

        font = ImageFont.load_default()

        # top bar
        draw.rectangle([(0,0),(1200,50)], fill=(0,0,0))
        draw.text((20,15), tag, fill=accent, font=font)

        if is_breaking:
            draw.text((250,15), "BREAKING", fill=(255,0,0), font=font)

        # headline
        y = 500
        wrapped = textwrap.wrap(headline, width=40)

        for line in wrapped[:3]:
            draw.text((20,y), line, fill="white", font=font)
            y += 40

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(tmp.name, "JPEG", quality=95)

        return tmp.name

    except Exception as e:
        print("Overlay error:", e)
        return image_path


# ─────────────────────────────────────────────
# MAIN IMAGE GENERATION (CLIP FIX APPLIED)
# ─────────────────────────────────────────────
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
        else "global news crisis war"
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

            # ─────────────────────────────────────
            # CLIP RANKING (FIXED CORE LOGIC)
            # ─────────────────────────────────────
            hits = data["hits"][:5]

            best_img = None
            best_score = -1

            for hit in hits:
                img_url = hit["largeImageURL"]
                img_data = requests.get(img_url, timeout=15).content

                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp.write(img_data)
                tmp.close()

                score = clip_score(keywords + " " + headline, tmp.name)

                print(f"  CLIP score: {score}")

                if score > best_score:
                    best_score = score
                    best_img = tmp.name

            # reject bad matches
            if best_score < 0.25:
                print("❌ No good image match found")
                continue

            return add_text_overlay(
                best_img,
                headline,
                source_type,
                is_breaking
            )

        except Exception as e:
            print("Image error:", e)
            continue

    return None