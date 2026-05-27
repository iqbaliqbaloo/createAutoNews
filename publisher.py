import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────────
# IMAGE UPLOAD (IMGBB SAFE VERSION)
# ─────────────────────────────────────────────

def upload_to_imgbb(image_path, retries=3):

    try:
        for attempt in range(retries):
            try:
                print(f"  imgbb upload attempt {attempt+1}...")

                with open(image_path, "rb") as f:
                    files = {"image": f.read()}

                r = requests.post(
                    "https://api.imgbb.com/1/upload",
                    data={
                        "key": os.getenv("IMGBB_API_KEY"),
                        "expiration": 3600
                    },
                    files=files,
                    timeout=30
                )

                try:
                    data = r.json()
                except:
                    print("  imgbb invalid response")
                    continue

                if data.get("success"):
                    url = data["data"]["url"]
                    print(f"  imgbb uploaded successfully")
                    return url

                print(f"  imgbb failed: {data}")

            except Exception as e:
                print(f"  imgbb attempt {attempt+1} error: {e}")
                time.sleep(2)

        return None

    except Exception as e:
        print(f"  imgbb critical error: {e}")
        return None


# ─────────────────────────────────────────────
# FACEBOOK POSTING (ROBUST VERSION)
# ─────────────────────────────────────────────

def post_to_facebook(text, image_path=None):

    FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
    FB_PAGE_ID    = os.getenv("FB_PAGE_ID")

    if not FB_PAGE_TOKEN or not FB_PAGE_ID:
        print("ERROR: Missing FB credentials")
        return False

    print(f"Posting to Facebook: {FB_PAGE_ID}")

    def safe_json(r):
        try:
            return r.json()
        except:
            return {}

    try:
        img_url = None

        # STEP 1: Upload image (optional)
        if image_path and os.path.exists(image_path):
            img_url = upload_to_imgbb(image_path)

        # STEP 2: Try photo post (URL method)
        if img_url:
            try:
                r = requests.post(
                    f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                    data={
                        "caption": text,
                        "url": img_url,
                        "access_token": FB_PAGE_TOKEN
                    },
                    timeout=30
                )

                result = safe_json(r)

                if "id" in result:
                    print("  Facebook posted (URL method)")
                    return True

            except Exception as e:
                print(f"  FB URL upload failed: {e}")

        # STEP 3: File upload fallback
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as img:
                    r = requests.post(
                        f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                        data={
                            "caption": text,
                            "access_token": FB_PAGE_TOKEN
                        },
                        files={"source": img},
                        timeout=30
                    )

                result = safe_json(r)

                if "id" in result:
                    print("  Facebook posted (file method)")
                    return True

            except Exception as e:
                print(f"  FB file upload error: {e}")

        # STEP 4: TEXT ONLY fallback
        print("  Posting text only...")

        r = requests.post(
            f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed",
            data={
                "message": text,
                "access_token": FB_PAGE_TOKEN
            },
            timeout=30
        )

        result = safe_json(r)

        if "id" in result:
            print("  Facebook text posted successfully")
            return True

        print(f"  Facebook failed: {result}")
        return False

    except Exception as e:
        print(f"  Facebook exception: {e}")
        return False


# ─────────────────────────────────────────────
# INSTAGRAM POSTING (STABLE VERSION)
# ─────────────────────────────────────────────

def post_to_instagram(text, image_path=None):
    FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
    IG_USER_ID    = os.getenv("IG_USER_ID")

    if not FB_PAGE_TOKEN or not IG_USER_ID:
        print("Missing Instagram credentials")
        return False

    img_url = upload_to_imgbb(image_path)
    if not img_url:
        return False

    # 1. Create media container
    r = requests.post(
        f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
        data={
            "image_url": img_url,
            "caption": text,
            "access_token": FB_PAGE_TOKEN
        }
    )

    container = r.json()

    if "id" not in container:
        print("Container failed:", container)
        return False

    creation_id = container["id"]

    # 🔥 IMPORTANT FIX: wait before publish
    time.sleep(10)

    # 2. Retry publish (important)
    for i in range(5):
        r2 = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": FB_PAGE_TOKEN
            }
        )

        result = r2.json()

        if "id" in result:
            print("Instagram posted ✔")
            return True

        print(f"Retry {i+1}: {result}")
        time.sleep(5)

    print("Instagram failed after retries")
    return False