"""
Weekly script — downloads 10 images per intent keyword from Pixabay
and stores them in image_library/{INTENT}/.
Runs inside image_library_refresh.yml (Sunday midnight UTC).
"""

import os
import requests

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

LIBRARY_ROOT = os.path.join(os.path.dirname(__file__), "..", "image_library")

INTENT_KEYWORDS = {
    "WAR":            ["battlefield military", "soldiers troops", "war conflict"],
    "POLITICS":       ["parliament building", "press conference podium", "government summit"],
    "ECONOMY":        ["stock market trading", "financial charts", "banking finance"],
    "DISASTER":       ["flood emergency rescue", "earthquake destruction", "natural disaster"],
    "SPORTS":         ["stadium crowd match", "sports competition athlete", "trophy ceremony"],
    "SPORTS_CRICKET": ["cricket match stadium", "cricket bat ball", "cricket players"],
    "SPORTS_FOOTBALL":["football match crowd", "soccer goal celebration", "football stadium"],
}


def download_image(url, dest_path):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and len(r.content) > 8000:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"  download error: {e}")
    return False


def refresh_intent(intent, keywords):
    folder = os.path.join(LIBRARY_ROOT, intent)
    os.makedirs(folder, exist_ok=True)

    count = 0
    for keyword in keywords:
        if count >= 10:
            break
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key":         PIXABAY_API_KEY,
                    "q":           keyword,
                    "image_type":  "photo",
                    "per_page":    5,
                    "safesearch":  "true",
                    "orientation": "horizontal",
                    "min_width":   1000,
                },
                timeout=15,
            )
            for hit in r.json().get("hits", []):
                if count >= 10:
                    break
                img_url = hit.get("largeImageURL")
                if not img_url:
                    continue
                img_id   = hit.get("id", count)
                dest     = os.path.join(folder, f"{intent.lower()}_{img_id}.jpg")
                if os.path.exists(dest):
                    count += 1
                    continue
                if download_image(img_url, dest):
                    count += 1
                    print(f"  [{intent}] saved {dest}")
        except Exception as e:
            print(f"  [{intent}] keyword '{keyword}' error: {e}")

    print(f"[{intent}] {count} images in library")


if __name__ == "__main__":
    if not PIXABAY_API_KEY:
        print("PIXABAY_API_KEY not set — aborting")
        raise SystemExit(1)

    for intent, keywords in INTENT_KEYWORDS.items():
        refresh_intent(intent, keywords)

    print("Image library refresh complete.")
