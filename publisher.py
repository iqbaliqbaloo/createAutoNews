import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Make.com webhook pool (primary → MAKE_WEBHOOK_URL_1 fallback) ──────────
_WEBHOOK_POOL = None


def _get_webhook_pool():
    """Build ordered list of active Make.com webhook URLs (lazy, once per process)."""
    global _WEBHOOK_POOL
    if _WEBHOOK_POOL is None:
        _WEBHOOK_POOL = [
            u for u in (
                os.getenv("MAKE_WEBHOOK_URL"),
                os.getenv("MAKE_WEBHOOK_URL_1"),
            )
            if u
        ]
    return _WEBHOOK_POOL


# ── ImgBB image host (provides a public URL for Make.com to fetch) ─────────

def upload_to_imgbb(image_path, retries=3):
    """Upload a local image to ImgBB. Returns permanent public URL or None."""
    if not image_path or not os.path.exists(image_path):
        return None

    api_key = os.getenv("IMGBB_API_KEY")
    if not api_key:
        print("❌ IMGBB_API_KEY missing")
        return None

    for attempt in range(retries):
        try:
            print(f"  imgbb upload attempt {attempt + 1}...")
            with open(image_path, "rb") as f:
                r = requests.post(
                    "https://api.imgbb.com/1/upload",
                    data={"key": api_key},                           # no expiration → permanent
                    files={"image": ("image.jpg", f, "image/jpeg")},
                    timeout=30,
                )
            data = r.json()
            if data.get("success"):
                print("  imgbb ✔")
                return data["data"]["url"]
            print(f"  imgbb rejected: {data.get('error', data)}")
        except Exception as e:
            print(f"  imgbb error: {e}")
        if attempt < retries - 1:
            time.sleep(2)

    return None


# ── Webhook dispatcher ─────────────────────────────────────────────────────

def _send_webhook(payload, per_webhook_retries=2):
    """
    POST payload to each Make.com webhook in order (primary → fallback).
    Returns True on first 200 response; False if all URLs fail.
    Make.com reads the 'platform' field to route to Facebook or Instagram.
    """
    pool = _get_webhook_pool()
    if not pool:
        print("❌ No Make.com webhook URL configured (MAKE_WEBHOOK_URL / MAKE_WEBHOOK_URL_1)")
        return False

    for idx, url in enumerate(pool):
        label = "primary" if idx == 0 else f"fallback-{idx}"
        for attempt in range(per_webhook_retries):
            try:
                print(f"  → {label} webhook attempt {attempt + 1}")
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    return True
                print(f"  {label} rejected: {r.status_code} {r.text[:120]}")
            except Exception as e:
                print(f"  {label} error: {e}")
            if attempt < per_webhook_retries - 1:
                time.sleep(3)

    return False


# ── Platform post functions ────────────────────────────────────────────────

def post_to_facebook(text, image_path=None):
    """Send Facebook post data to Make.com; Make.com publishes to the Page."""
    img_url = upload_to_imgbb(image_path) if image_path else None
    payload = {
        "platform":  "facebook",
        "message":   text,
        "image_url": img_url or "",
    }
    print(f"  Posting Facebook via Make.com (image={'yes' if img_url else 'no'})...")
    ok = _send_webhook(payload)
    print("✅ FB posted via Make.com" if ok else "❌ FB post failed")
    return ok


def post_to_instagram(text, image_path=None):
    """Send Instagram post data to Make.com; Make.com publishes to the account."""
    img_url = upload_to_imgbb(image_path) if image_path else None
    if not img_url:
        reason = "no image provided" if not image_path else "upload failed"
        print(f"❌ Instagram: image required but {reason} — skipping")
        return False
    payload = {
        "platform":  "instagram",
        "message":   text,
        "image_url": img_url,
    }
    print("  Posting Instagram via Make.com...")
    ok = _send_webhook(payload)
    print("✅ Instagram posted via Make.com" if ok else "❌ Instagram post failed")
    return ok



def post_to_telegram(text, image_path=None):
    """Post directly to Telegram via Bot API (no Make.com intermediary)."""
    # Strip **markdown** markers — Telegram plain-text mode, no parse_mode
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

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
