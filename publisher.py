import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_URL = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────
# IMGBB UPLOAD (FIXED)
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
                    files={
                        "image": f
                    },
                    timeout=30
                )

            data = r.json()

            if data.get("success"):
                print("  imgbb upload success")
                return data["data"]["url"]

            print(f"  imgbb failed: {data}")

        except Exception as e:
            print(f"  imgbb error: {e}")
            time.sleep(2)

    return None


# ─────────────────────────────────────────────
# FACEBOOK POST (STABLE)
# ─────────────────────────────────────────────

def post_to_facebook(text, image_path=None):
    """
    Instead of calling FB Graph API directly (blocked),
    we send the post data to a Make.com webhook.
    Make.com then posts to your Facebook Page using
    their own approved Meta app — no developer review needed.
    """
 
    webhook_url = os.getenv("MAKE_WEBHOOK_URL")
 
    if not webhook_url:
        print("❌ Missing MAKE_WEBHOOK_URL in environment")
        return False
 
    try:
        # Upload image to ImgBB first so Make.com can fetch it via URL
        img_url = upload_to_imgbb(image_path) if image_path else None
 
        payload = {
            "message": text,
            "image_url": img_url or ""   # empty string if no image
        }
 
        print(f"  Sending to Make.com webhook... (image={'yes' if img_url else 'no'})")
 
        r = requests.post(
            webhook_url,
            json=payload,
            timeout=30
        )
 
        # Make.com returns "Accepted" (200) when it receives the webhook
        if r.status_code == 200:
            print("✅ FB posted via Make.com")
            return True
 
        print(f"❌ Make.com webhook failed: {r.status_code} {r.text}")
        return False
 
    except Exception as e:
        print(f"❌ Make.com exception: {e}")
        return False

# ─────────────────────────────────────────────
# INSTAGRAM (FIXED + CLEAN)
# ─────────────────────────────────────────────

def wait_for_media_ready(media_id, token, retries=10):

    for i in range(retries):
        try:
            r = requests.get(
                f"{GRAPH_URL}/{media_id}",
                params={
                    "fields": "status_code",
                    "access_token": token
                },
                timeout=15
            )

            data = r.json()
            status = data.get("status_code")

            print(f"  IG status check {i+1}: {status}")

            if status == "FINISHED":
                return True

            if status == "ERROR":
                return False

        except Exception as e:
            print(f"  IG status error: {e}")

        time.sleep(5)

    return False


def post_to_instagram(text, image_path=None):

    token   = os.getenv("FB_PAGE_TOKEN")
    ig_user = os.getenv("IG_USER_ID")

    if not token or not ig_user:
        print("❌ Missing Instagram credentials")
        return False

    try:
        img_url = upload_to_imgbb(image_path)

        if not img_url:
            print("❌ Image upload failed")
            return False

        # STEP 1 — create media
        r = requests.post(
            f"{GRAPH_URL}/{ig_user}/media",
            data={
                "image_url": img_url,
                "caption": text,
                "access_token": token
            },
            timeout=30
        )

        container = r.json()

        if "id" not in container:
            print("❌ Container failed:", container)
            return False

        media_id = container["id"]

        print(f"  Media created: {media_id}")

        # STEP 2 — wait processing
        if not wait_for_media_ready(media_id, token):
            print("❌ Media not ready")
            return False

        # STEP 3 — publish with retry
        for i in range(5):

            r = requests.post(
                f"{GRAPH_URL}/{ig_user}/media_publish",
                data={
                    "creation_id": media_id,
                    "access_token": token
                },
                timeout=30
            )

            result = r.json()

            if "id" in result:
                print("✅ Instagram posted")
                return True

            print(f"  retry {i+1}: {result}")
            time.sleep(5)

        return False

    except Exception as e:
        print("❌ IG exception:", e)
        return False


# ─────────────────────────────────────────────
# TELEGRAM (BOT API)
# ─────────────────────────────────────────────

def post_to_telegram(text, image_path=None):

    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    channel = os.getenv("TELEGRAM_CHANNEL_ID")

    if not token or not channel:
        print("❌ Missing Telegram credentials")
        return False

    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            with open(image_path, "rb") as f:
                r = requests.post(
                    url,
                    data={"chat_id": channel, "caption": text[:1024]},
                    files={"photo": f},
                    timeout=30,
                )
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            r = requests.post(
                url,
                data={"chat_id": channel, "text": text[:4096]},
                timeout=30,
            )

        result = r.json()
        if result.get("ok"):
            print("✅ Telegram posted")
            return True

        print("❌ Telegram failed:", result)
        return False

    except Exception as e:
        print("❌ Telegram exception:", e)
        return False