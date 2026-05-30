import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

BRAND_NAME = "VisionaryMinds"
TAG_RED    = (204, 41, 54)

# Intent / league → badge colour
TAG_COLORS = {
    "WAR":              (204,  41,  54),   # red
    "POLITICS":         ( 26,  86, 219),   # blue
    "ECONOMY":          (  5, 122,  85),   # green
    "DISASTER":         (208,  56,   1),   # orange
    "SPORTS":           (108,  43, 217),   # purple
    "CRICKET":          (  0,  99,  65),   # cricket green
    "SPORTS_CRICKET":   (  0,  99,  65),
    "FOOTBALL":         (  5, 122,  85),
    "SPORTS_FOOTBALL":  (  5, 122,  85),
    "SPORTS_LIVE":      (204,  41,  54),
    "TENNIS":           (200, 140,   0),   # golden
    "F1":               (225,   6,   0),   # F1 red
    "BOXING":           (180,  20,  20),
    "BASKETBALL":       (210,  90,   0),   # orange
    "PSL":              (  0,  99,  65),
    "IPL":              (  0,  75, 160),
    "UCL":              (  0,  29,  61),
    "EPL":              ( 56,   0,  60),
}

# Human-readable badge labels (what's printed on the red pill)
BADGE_LABELS = {
    "WAR":              "WAR & CONFLICT",
    "POLITICS":         "POLITICS",
    "ECONOMY":          "ECONOMY",
    "DISASTER":         "DISASTER",
    "SPORTS":           "SPORTS",
    "CRICKET":          "CRICKET",
    "SPORTS_CRICKET":   "CRICKET",
    "FOOTBALL":         "FOOTBALL",
    "SPORTS_FOOTBALL":  "FOOTBALL",
    "SPORTS_LIVE":      "LIVE SPORTS",
    "TENNIS":           "TENNIS",
    "F1":               "FORMULA 1",
    "BOXING":           "BOXING",
    "BASKETBALL":       "BASKETBALL",
    "PSL":              "PSL",
    "IPL":              "IPL",
    "UCL":              "CHAMPIONS LEAGUE",
    "EPL":              "PREMIER LEAGUE",
}

# Optional logo file — checked in order; first match wins.
_LOGO_SEARCH = [
    os.path.join(os.path.dirname(__file__), "assets", "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.jpg"),
    os.path.join(os.path.dirname(__file__), "vm_logo.png"),
]
_logo_cache = None


# ── Platform layout config ─────────────────────────────────────────────────
# panel_ratio  : fraction of canvas height the bottom dark panel occupies
# badge_fs     : badge font size
# headline_fs  : headline font size
# headline_pad : left/right padding for headline text
# logo_size    : logo circle diameter
# brand_fs     : brand name font size

PLATFORMS = {
    "facebook": {
        "canvas":       (1200, 630),
        "panel_ratio":  0.42,
        "badge_fs":     26,
        "headline_fs":  52,
        "headline_pad": 36,
        "logo_size":    56,
        "brand_fs":     22,
    },
    "instagram": {
        "canvas":       (1080, 1080),
        "panel_ratio":  0.40,
        "badge_fs":     30,
        "headline_fs":  60,
        "headline_pad": 36,
        "logo_size":    60,
        "brand_fs":     24,
    },
    "telegram": {
        "canvas":       (1280, 720),
        "panel_ratio":  0.42,
        "badge_fs":     26,
        "headline_fs":  52,
        "headline_pad": 36,
        "logo_size":    56,
        "brand_fs":     22,
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


# ── Logo helpers ───────────────────────────────────────────────────────────

def _make_circular(img):
    s    = min(img.width, img.height)
    left = (img.width  - s) // 2
    top  = (img.height - s) // 2
    img  = img.crop((left, top, left + s, top + s)).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, s - 1, s - 1], fill=255)
    img.putalpha(mask)
    return img


def _load_logo():
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache if _logo_cache is not False else None
    for path in _LOGO_SEARCH:
        if os.path.exists(path):
            try:
                _logo_cache = _make_circular(Image.open(path).convert("RGBA"))
                logger.info(f"Logo loaded: {path}")
                return _logo_cache
            except Exception:
                continue
    _logo_cache = False
    return None


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
        new_w = int(ih * w / h)
        img = img.crop(((iw - new_w) // 2, 0, (iw - new_w) // 2 + new_w, ih))
    else:
        new_h = int(iw * h / w)
        img = img.crop((0, (ih - new_h) // 2, iw, (ih - new_h) // 2 + new_h))
    return img.resize((w, h), Image.LANCZOS)


def _top_vignette(width, panel_y, vignette_h=130, opacity=0.70):
    """
    Subtle dark gradient at the very top so the white logo and brand name
    are always readable against any photo background.
    """
    arr = np.zeros((panel_y, width, 4), dtype=np.uint8)
    for y in range(min(vignette_h, panel_y)):
        t = 1.0 - (y / vignette_h)          # 1.0 at top → 0.0 at vignette_h
        arr[y, :, 3] = int(opacity * 255 * t)
    return Image.fromarray(arr, "RGBA")


def _text_wh(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _shadow_text(draw, xy, text, font, fill=(255, 255, 255)):
    x, y = xy
    # Drop shadow
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x,     y    ), text, font=font, fill=fill)


def _wrap_headline(draw, text, font, max_width, max_lines=3):
    """Word-wrap, max max_lines lines, truncate last with '…' if needed."""
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

    used = sum(len(l.split()) for l in lines)
    if used < len(words) and lines:
        last = lines[-1]
        while last and _text_wh(draw, last + "…", font)[0] > max_width:
            last = " ".join(last.split()[:-1])
        lines[-1] = (last + "…") if last else "…"

    return lines[:max_lines]


# ── Core composition ───────────────────────────────────────────────────────

def compose_image(image_url, platform, intent, headline, source_name,
                  published_at=None, image_path=None, tag_color=None):
    """
    Al-Jazeera-style layout:
      • Full photo background (top 60 %)
      • Solid dark panel (bottom 40 %)
      • Coloured "BREAKING NEWS / POLITICS / CRICKET …" badge at junction
      • Large bold left-aligned headline inside the panel
      • VisionaryMinds logo + brand name, top-left
    """
    cfg   = PLATFORMS.get(platform, PLATFORMS["facebook"])
    W, H  = cfg["canvas"]

    panel_h = int(H * cfg["panel_ratio"])
    panel_y = H - panel_h          # y where the dark panel starts

    # ── 1. Base photo ──────────────────────────────────────────────────────
    base = None
    if image_path and os.path.exists(image_path):
        try:
            base = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"Image open failed {image_path}: {e}")
    if base is None and image_url:
        base = _fetch_image(image_url)
    if base is None:
        logger.warning("No image — using dark placeholder")
        base = Image.new("RGBA", (W, H), (18, 18, 28, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        # Slight desaturation so text pops
        base = ImageEnhance.Color(base.convert("RGB")).enhance(0.88).convert("RGBA")

    # ── 2. Top vignette — keeps logo readable on bright photos ────────────
    vignette = _top_vignette(W, panel_y, vignette_h=140, opacity=0.68)
    photo    = Image.alpha_composite(base, vignette).convert("RGB")

    # ── 3. Solid dark panel at bottom ─────────────────────────────────────
    draw = ImageDraw.Draw(photo)
    panel_color = (10, 10, 18)                  # near-black, slightly blue
    draw.rectangle([0, panel_y, W, H], fill=panel_color)

    # ── 4. Thin accent line at panel top (1 px, intent colour) ────────────
    accent = tag_color or TAG_COLORS.get(intent.upper(), TAG_RED)
    draw.line([(0, panel_y), (W, panel_y)], fill=accent, width=3)

    # ── 5. Logo + brand name — top-left ───────────────────────────────────
    logo_size = cfg["logo_size"]
    logo_x, logo_y = 20, 16
    logo_placed = False
    _logo = _load_logo()
    if _logo:
        _logo_r = _logo.resize((logo_size, logo_size), Image.LANCZOS)
        photo_rgba = photo.convert("RGBA")
        photo_rgba.paste(_logo_r, (logo_x, logo_y), _logo_r)
        photo = photo_rgba.convert("RGB")
        draw  = ImageDraw.Draw(photo)
        logo_placed = True

    brand_font = _load_font(cfg["brand_fs"], bold=True)
    brand_x = logo_x + (logo_size + 10 if logo_placed else 0)
    brand_y = logo_y + max(0, (logo_size - cfg["brand_fs"]) // 2)
    _shadow_text(draw, (brand_x, brand_y), BRAND_NAME, brand_font)

    # ── 6. Badge — coloured pill overlapping photo/panel junction ─────────
    badge_label = BADGE_LABELS.get(intent.upper(), intent.upper().replace("_", " "))
    badge_color = accent
    badge_font  = _load_font(cfg["badge_fs"], bold=True)
    badge_pad_x, badge_pad_y = 18, 9

    tb  = draw.textbbox((0, 0), badge_label, font=badge_font)
    bw  = tb[2] - tb[0]
    bh  = tb[3] - tb[1]
    badge_w = bw + badge_pad_x * 2
    badge_h = bh + badge_pad_y * 2

    badge_x = cfg["headline_pad"]
    # Badge sits with its bottom edge ~10px inside the panel (overlaps the accent line)
    badge_top = panel_y - badge_h + 14
    badge_bot = badge_top + badge_h

    draw.rounded_rectangle(
        [badge_x, badge_top, badge_x + badge_w, badge_bot],
        radius=5, fill=badge_color,
    )
    draw.text(
        (badge_x + badge_pad_x - tb[0], badge_top + badge_pad_y - tb[1]),
        badge_label, font=badge_font, fill=(255, 255, 255),
    )

    # ── 7. Headline — large, bold, left-aligned, inside panel ─────────────
    headline_font = _load_font(cfg["headline_fs"], bold=True)
    max_w   = W - cfg["headline_pad"] * 2
    lines   = _wrap_headline(draw, headline, headline_font, max_w, max_lines=3)
    line_h  = cfg["headline_fs"] + 10
    text_y  = badge_bot + 18               # start just below the badge

    for line in lines:
        _shadow_text(draw, (cfg["headline_pad"], text_y), line, headline_font)
        text_y += line_h

    return photo


# ── Public entry point ─────────────────────────────────────────────────────

def save_platform_images(image_url, intent, headline, source_name,
                         published_at=None, output_dir=None, image_path=None,
                         tag_color=None):
    """
    Generate a branded image for every active platform.
    Returns dict: platform → file path.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vm_images_")

    paths = {}
    for platform in PLATFORMS:
        try:
            img  = compose_image(image_url, platform, intent, headline,
                                 source_name, published_at,
                                 image_path=image_path, tag_color=tag_color)
            path = os.path.join(output_dir, f"{platform}.jpg")
            img.save(path, "JPEG", quality=93, optimize=True)
            paths[platform] = path
            logger.info(f"Saved {platform} → {path}")
        except Exception as e:
            logger.error(f"compose_image failed [{platform}]: {e}")

    return paths
