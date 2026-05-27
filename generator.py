import os
import re
import requests
import tempfile
import textwrap
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from sentence_transformers import SentenceTransformer, util

load_dotenv()

# ─────────────────────────────────────────────
# CLIP MODEL (GLOBAL)
# ─────────────────────────────────────────────
clip_model = SentenceTransformer("clip-ViT-B-32")

GRAPH_URL = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────
# CLIP SCORE (FIXED + STABLE)
# ─────────────────────────────────────────────
def clip_score(text, image_path):
    try:
        image = Image.open(image_path).convert("RGB")

        text_emb = clip_model.encode(text, convert_to_tensor=True)
        img_emb  = clip_model.encode(image, convert_to_tensor=True)

        score = util.cos_sim(text_emb, img_emb).item()

        return float(score)

    except Exception as e:
        print("CLIP error:", e)
        return 0.0


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
# IMAGE GENERATION (CLIP MATCHED + FIXED)
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

    best_img = None
    best_score = -1

    # ─────────────────────────────────────
    # SEARCH MULTIPLE PIXABAY TERMS
    # ─────────────────────────────────────
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

            hits = data["hits"][:5]

            temp_files = []

            # ─────────────────────────────────────
            # CLIP RANKING (CORE FIX)
            # ─────────────────────────────────────
            for hit in hits:

                try:
                    img_url = hit["largeImageURL"]
                    img_data = requests.get(img_url, timeout=15).content

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tmp.write(img_data)
                    tmp.close()

                    temp_files.append(tmp.name)

                    # IMPORTANT: use headline ONLY for CLIP stability
                    score = clip_score(headline, tmp.name)

                    print(f"  CLIP score: {score:.3f}")

                    if score > best_score:
                        best_score = score
                        best_img = tmp.name

                except Exception as e:
                    print("Image download error:", e)
                    continue

            # cleanup weaker images
            for path in temp_files:
                if path != best_img:
                    try:
                        os.unlink(path)
                    except:
                        pass

            # strong threshold (FIXED)
            if best_score >= 0.32 and best_img:
                return add_text_overlay(
                    best_img,
                    headline,
                    source_type,
                    is_breaking
                )

        except Exception as e:
            print("Pixabay error:", e)
            continue

    return None