import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

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
                    data={"key": api_key},
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


# ── Per-platform webhook sender ────────────────────────────────────────────

def _send_to_url(url, payload, label, retries=2):
    """POST payload to a single Make.com webhook URL. Returns True on 200."""
    if not url:
        print(f"❌ {label} webhook URL not configured")
        return False

    for attempt in range(retries):
        try:
            print(f"  → {label} webhook attempt {attempt + 1}")
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return True
            # Make.com acknowledged — a non-200 means it rejected the request.
            # Do NOT retry with the same URL; it would double-post.
            print(f"  {label} rejected: {r.status_code} {r.text[:120]}")
            return False
        except Exception as e:
            print(f"  {label} error: {e}")
        if attempt < retries - 1:
            time.sleep(3)

    return False


# ── Platform post functions ────────────────────────────────────────────────

def post_to_facebook(text, image_path=None):
    """Send Facebook post to Make.com via MAKE_WEBHOOK_URL (never MAKE_WEBHOOK_URL_1)."""
    img_url = upload_to_imgbb(image_path) if image_path else None
    payload = {
        "platform":  "facebook",
        "message":   text,
        "image_url": img_url or "",
    }
    print(f"  Posting Facebook via Make.com (image={'yes' if img_url else 'no'})...")
    url = os.getenv("MAKE_WEBHOOK_URL")
    ok  = _send_to_url(url, payload, "Facebook(MAKE_WEBHOOK_URL)")
    print("✅ FB posted via Make.com" if ok else "❌ FB post failed")
    return ok


def post_to_instagram(text, image_path=None):
    """Send Instagram post to Make.com via MAKE_WEBHOOK_URL_1 (never MAKE_WEBHOOK_URL)."""
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
    url = os.getenv("MAKE_WEBHOOK_URL_1")
    ok  = _send_to_url(url, payload, "Instagram(MAKE_WEBHOOK_URL_1)")
    print("✅ Instagram posted via Make.com" if ok else "❌ Instagram post failed")
    return ok


def send_error_email(subject, body):
    """
    Send an error notification email via Gmail SMTP.
    Requires secrets: GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_EMAIL.
    Returns True if sent, False otherwise (never raises).
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import pytz
    from datetime import datetime

    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    to_email   = os.getenv("NOTIFY_EMAIL") or gmail_user

    if not gmail_user or not gmail_pass:
        print("⚠️  Email skipped: GMAIL_USER / GMAIL_APP_PASSWORD not configured")
        return False

    try:
        pkt      = pytz.timezone("Asia/Karachi")
        now_pkt  = datetime.now(pkt).strftime("%d %b %Y %I:%M %p PKT")
        full_body = f"{body}\n\n🕒 Time: {now_pkt}\n📌 VisionaryMinds Autoposter"

        msg            = MIMEMultipart()
        msg["From"]    = gmail_user
        msg["To"]      = to_email
        msg["Subject"] = f"[VisionaryMinds] {subject}"
        msg.attach(MIMEText(full_body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())

        print(f"📧 Error email sent → {to_email}")
        return True
    except Exception as e:
        print(f"⚠️  Error email failed: {e}")
        return False


def post_to_telegram(text, image_path=None):
    """Post directly to Telegram via Bot API (no Make.com intermediary)."""
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
