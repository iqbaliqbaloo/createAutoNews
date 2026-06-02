import os
import requests

token   = os.environ.get("FB_PAGE_TOKEN")
page_id = os.environ.get("FB_PAGE_ID")
dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


# ─── SAFE CHECKS ─────────────────────────────

if not token or not page_id:
    print("ERROR: Missing FB_PAGE_TOKEN or FB_PAGE_ID")
    exit()


print("Token loaded: YES")
print("Token preview:", token[:10] + "...")

if dry_run:
    print("DRY_RUN=true — skipping actual API call")
    exit(0)

# ─── REQUEST ────────────────────────────────

try:
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"

    r = requests.post(
        url,
        data={
            "message": "debug test delete",
            "access_token": token
        },
        timeout=20
    )

    # ─── SAFE RESPONSE HANDLING ─────────────

    try:
        data = r.json()
    except Exception:
        print("Invalid JSON response")
        print("Raw response:", r.text)
        exit()

    print("Status Code:", r.status_code)
    print("Response:", data)

    # ─── SUCCESS CHECK ───────────────────────

    if "id" in data:
        print("SUCCESS: Post created with ID:", data["id"])
    else:
        print("FAILED:", data.get("error", data))

except Exception as e:
    print("Request error:", str(e))