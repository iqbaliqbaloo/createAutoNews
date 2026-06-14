import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

BRAND_NAME = "VisionaryMinds"
LOGO_PATH  = os.path.join(os.path.dirname(__file__), "logo.png")
DARK_NAVY  = (8, 12, 24)

# ── Intent badge colours ───────────────────────────────────────────────────
TAG_COLORS = {
    "WAR":              (204,  41,  54),
    "POLITICS":         ( 26,  86, 219),
    "ECONOMY":          (  5, 122,  85),
    "DISASTER":         (208,  56,   1),
    "HEALTH":           (  2, 132, 199),
    "SPORTS":           (108,  43, 217),
    "TECHNOLOGY":       (  0, 172, 193),
    "ENTERTAINMENT":    (156,  39, 176),
    "CRICKET":          (  0, 120,  70),
    "SPORTS_CRICKET":   (  0, 120,  70),
    "FOOTBALL":         (  5, 122,  85),
    "SPORTS_FOOTBALL":  (  5, 122,  85),
    "SPORTS_LIVE":      (204,  41,  54),
    "FIFA":             ( 53,  99, 233),
    "WORLD CUP":        ( 53,  99, 233),
    "TENNIS":           (190, 130,   0),
    "F1":               (225,   6,   0),
    "BOXING":           (170,  20,  20),
    "BASKETBALL":       (200,  85,   0),
    "PSL":              (  0,  99,  65),
    "IPL":              (  0,  75, 160),
    "UCL":              (  0,  29,  61),
    "EPL":              ( 56,   0,  60),
}

BADGE_LABELS = {
    "WAR":              "WAR & CONFLICT",
    "POLITICS":         "POLITICS",
    "ECONOMY":          "ECONOMY",
    "DISASTER":         "DISASTER ALERT",
    "HEALTH":           "HEALTH ALERT",
    "SPORTS":           "SPORTS",
    "TECHNOLOGY":       "TECHNOLOGY",
    "ENTERTAINMENT":    "ENTERTAINMENT",
    "CRICKET":          "CRICKET",
    "SPORTS_CRICKET":   "CRICKET",
    "FOOTBALL":         "FOOTBALL",
    "SPORTS_FOOTBALL":  "FOOTBALL",
    "SPORTS_LIVE":      "LIVE SPORTS",
    "FIFA":             "FIFA WORLD CUP",
    "WORLD CUP":        "FIFA WORLD CUP",
    "TENNIS":           "TENNIS",
    "F1":               "FORMULA 1",
    "BOXING":           "BOXING",
    "BASKETBALL":       "BASKETBALL",
    "PSL":              "PSL",
    "IPL":              "IPL",
    "UCL":              "CHAMPIONS LEAGUE",
    "EPL":              "PREMIER LEAGUE",
}

# ── Platform configs ───────────────────────────────────────────────────────
# Facebook and Instagram: 1080×1350 portrait (4:5)
# Telegram: 1280×720 landscape
PLATFORMS = {
    "facebook": {
        "canvas":        (1080, 1350),
        "overlay_start": 0.65,
        "gradient_h":    110,
        "badge_fs":      30,
        "headline_fs":   52,
        "subtext_fs":    30,
        "logo_fs":       22,
        "logo_pad_x":    16,
        "logo_pad_y":    10,
        "pad":           44,
        "line_gap":      16,
        "badge_y_frac":  0.68,
        "corner_r":      32,
        "border_w":      6,
    },
    "instagram": {
        "canvas":        (1080, 1350),
        "overlay_start": 0.65,
        "gradient_h":    110,
        "badge_fs":      30,
        "headline_fs":   52,
        "subtext_fs":    30,
        "logo_fs":       22,
        "logo_pad_x":    16,
        "logo_pad_y":    10,
        "pad":           44,
        "line_gap":      16,
        "badge_y_frac":  0.68,
        "corner_r":      32,
        "border_w":      6,
    },
    "telegram": {
        "canvas":        (1280, 720),
        "overlay_start": 0.58,
        "gradient_h":    80,
        "badge_fs":      24,
        "headline_fs":   40,
        "subtext_fs":    24,
        "logo_fs":       18,
        "logo_pad_x":    14,
        "logo_pad_y":    8,
        "pad":           38,
        "line_gap":      12,
        "badge_y_frac":  0.62,
        "corner_r":      20,
        "border_w":      4,
    },
}

# ── Font loader ────────────────────────────────────────────────────────────
_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_REGULAR_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/verdana.ttf",
]


def _load_font(size, bold=True):
    for p in (_BOLD_FONTS if bold else _REGULAR_FONTS):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Image helpers ──────────────────────────────────────────────────────────

def _fetch_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or len(r.content) < 8000:
            return None
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Image fetch failed ({url}): {e}")
        return None


def _crop_to_canvas(img, w, h):
    iw, ih = img.size
    if (iw / ih) > (w / h):
        nw  = int(ih * w / h)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh  = int(iw * h / w)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    return img.resize((w, h), Image.LANCZOS)


def _enhance_photo(img):
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.20)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.12)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.15)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.04)
    return rgb.convert("RGBA")


# ── Drawing helpers ────────────────────────────────────────────────────────

def _text_wh(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _wrap_headline(draw, text, font, max_width, max_lines=3):
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if _text_wh(draw, test, font)[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    # truncate last line with ellipsis if text was cut
    used = sum(len(l.split()) for l in lines)
    if used < len(words) and lines:
        last = lines[-1]
        while last and _text_wh(draw, last + "…", font)[0] > max_width:
            last = " ".join(last.split()[:-1])
        lines[-1] = (last + "…") if last else "…"
    return lines[:max_lines]


# ── Core composition ───────────────────────────────────────────────────────

def compose_image(image_url, platform, intent, headline, source_name,
                  published_at=None, image_path=None, tag_color=None,
                  image_subtext=None):
    """
    Portrait breaking-news broadcast graphic — Al Jazeera style.

      ┌──────────────────────────────────────┐
      │ ┌──────────────────┐                 │
      │ │  VisionaryMinds  │  ← white box   │
      │ └──────────────────┘                 │
      │                                      │
      │        [full-bleed HD photo]         │
      │                                      │
      │   ~ ~ ~ gradient fade ~ ~ ~          │
      │  ████████████████████████████████    │ ← dark navy overlay
      │  ┌──────────────┐                   │
      │  │  POLITICS    │  ← coloured badge │
      │  └──────────────┘                   │
      │  Bold white headline text here       │
      │  second line of headline             │
      │──────────────────────────────────────│ ← thin accent line
    """
    cfg    = PLATFORMS.get(platform, PLATFORMS["facebook"])
    W, H   = cfg["canvas"]
    pad    = cfg["pad"]
    accent = tag_color or TAG_COLORS.get(intent.upper(), (204, 41, 54))

    # 1. Load and enhance photo ────────────────────────────────────────────
    base = None
    if image_path and os.path.exists(image_path):
        try:
            base = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"Image open failed {image_path}: {e}")
    if base is None and image_url:
        base = _fetch_image(image_url)
    if base is None:
        logger.warning("No image — dark placeholder")
        base = Image.new("RGBA", (W, H), (12, 16, 30, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        base = _enhance_photo(base)

    # 2. Gradient overlay — tinted with accent colour, reduced opacity so
    #    the background photo stays clearly visible
    overlay_y  = int(H * cfg["overlay_start"])
    gradient_h = cfg["gradient_h"]

    # Tint: 60% dark navy + 40% accent colour — vibrant but readable
    r_a, g_a, b_a = accent
    tint = (
        int(DARK_NAVY[0] * 0.60 + r_a * 0.40),
        int(DARK_NAVY[1] * 0.60 + g_a * 0.40),
        int(DARK_NAVY[2] * 0.60 + b_a * 0.40),
    )

    arr = np.zeros((H, W, 4), dtype=np.uint8)
    # Short fast gradient fade (transparent → tinted)
    fade_start = max(0, overlay_y - gradient_h)
    for y in range(fade_start, overlay_y):
        t     = (y - fade_start) / gradient_h
        alpha = int(185 * (t ** 2.0))   # steeper curve = faster fade
        arr[y, :, :3] = tint
        arr[y, :, 3]  = alpha
    # Text band — 73% opacity, top 65% of photo is untouched
    arr[overlay_y:, :, :3] = tint
    arr[overlay_y:, :, 3]  = 185

    overlay = Image.fromarray(arr, "RGBA")
    photo   = Image.alpha_composite(base, overlay).convert("RGB")
    draw    = ImageDraw.Draw(photo)

    # 3. Logo — top-left, full size, pasted directly ─────────────────────
    # Logo is circular with its own background so no backdrop needed.
    logo_target_h = int(H * 0.10)   # 10% of canvas height — clearly visible
    lx, ly = 18, 18

    try:
        logo   = Image.open(LOGO_PATH).convert("RGBA")
        ratio  = logo_target_h / logo.height
        logo_w = int(logo.width * ratio)
        logo   = logo.resize((logo_w, logo_target_h), Image.LANCZOS)
        photo.paste(logo, (lx, ly), logo)   # alpha channel = circular mask

    except Exception as e:
        logger.warning(f"Logo load failed: {e} — text fallback")
        logo_font = _load_font(cfg["logo_fs"], bold=True)
        ltb       = draw.textbbox((0, 0), BRAND_NAME, font=logo_font)
        ltext_w, ltext_h = ltb[2] - ltb[0], ltb[3] - ltb[1]
        bpx, bpy  = 14, 8
        draw.rounded_rectangle(
            [lx, ly, lx + ltext_w + bpx * 2, ly + ltext_h + bpy * 2],
            radius=10, fill=tint,
        )
        draw.text(
            (lx + bpx - ltb[0], ly + bpy - ltb[1]),
            BRAND_NAME, font=logo_font, fill=(255, 255, 255),
        )

    # 4. Coloured badge (category label) ─────────────────────────────────
    badge_label = BADGE_LABELS.get(intent.upper(), intent.upper().replace("_", " "))
    badge_font  = _load_font(cfg["badge_fs"], bold=True)
    btb         = draw.textbbox((0, 0), badge_label, font=badge_font)
    btext_w     = btb[2] - btb[0]
    btext_h     = btb[3] - btb[1]
    bpx, bpy    = 22, 10
    badge_w     = btext_w + bpx * 2
    badge_h     = btext_h + bpy * 2
    badge_top   = int(H * cfg["badge_y_frac"])
    badge_left  = pad

    draw.rounded_rectangle(
        [badge_left, badge_top, badge_left + badge_w, badge_top + badge_h],
        radius=5, fill=accent,
    )
    draw.text(
        (badge_left + bpx - btb[0], badge_top + bpy - btb[1]),
        badge_label, font=badge_font, fill=(255, 255, 255),
    )

    # 5. Bold white headline ───────────────────────────────────────────────
    headline_font = _load_font(cfg["headline_fs"], bold=True)
    max_text_w    = W - pad * 2
    lines         = _wrap_headline(draw, headline, headline_font, max_text_w, max_lines=2)
    line_step     = cfg["headline_fs"] + cfg["line_gap"]
    text_y        = badge_top + badge_h + 22

    for line in lines:
        # soft shadow (1px offset, dark tint — not pure black)
        draw.text((pad + 1, text_y + 1), line, font=headline_font, fill=(5, 5, 20))
        draw.text((pad,     text_y),     line, font=headline_font, fill=(255, 255, 255))
        text_y += line_step

    # 6. Subtext below headline (smaller font, light grey) ────────────────
    if image_subtext:
        subtext_font = _load_font(cfg["subtext_fs"], bold=False)
        subtext_step = cfg["subtext_fs"] + 10
        text_y      += 6   # small gap between headline and subtext
        for sline in image_subtext.strip().split("\n")[:2]:
            sline = sline.strip()
            if not sline:
                continue
            # Truncate if too wide
            while sline and _text_wh(draw, sline, subtext_font)[0] > max_text_w:
                sline = " ".join(sline.split()[:-1])
            if not sline:
                continue
            draw.text((pad + 1, text_y + 1), sline, font=subtext_font, fill=(5, 5, 20))
            draw.text((pad,     text_y),     sline, font=subtext_font, fill=(220, 220, 230))
            text_y += subtext_step

    # 7. Accent border (sharp corners) ───────────────────────────────────
    bw = cfg.get("border_w", 5)
    draw.rectangle(
        [bw // 2, bw // 2, W - bw // 2 - 1, H - bw // 2 - 1],
        outline=accent,
        width=bw,
    )

    # 9. Thin accent stripe at the very bottom (inside border) ────────────
    draw.rectangle([bw + 1, H - 8, W - bw - 1, H - bw - 1], fill=accent)

    return photo


# ── Public entry point ─────────────────────────────────────────────────────

def save_platform_images(image_url, intent, headline, source_name,
                         published_at=None, output_dir=None, image_path=None,
                         tag_color=None, image_subtext=None):
    """Generate a branded portrait news image for every active platform."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vm_images_")

    paths = {}
    for platform in PLATFORMS:
        try:
            img  = compose_image(image_url, platform, intent, headline,
                                 source_name, published_at,
                                 image_path=image_path, tag_color=tag_color,
                                 image_subtext=image_subtext)
            path = os.path.join(output_dir, f"{platform}.jpg")
            img.save(path, "JPEG", quality=96, optimize=True, subsampling=0)
            paths[platform] = path
            logger.info(f"Saved {platform} → {path}")
        except Exception as e:
            logger.error(f"compose_image failed [{platform}]: {e}")

    return paths
