import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

BRAND_NAME = "VisionaryMinds"
TAG_RED    = (204, 41, 54)
PANEL_BASE = (8, 8, 18)

# ── Intent / league badge colours ─────────────────────────────────────────
TAG_COLORS = {
    "WAR":              (204,  41,  54),
    "POLITICS":         ( 26,  86, 219),
    "ECONOMY":          (  5, 122,  85),
    "DISASTER":         (208,  56,   1),
    "SPORTS":           (108,  43, 217),
    "CRICKET":          (  0, 120,  70),
    "SPORTS_CRICKET":   (  0, 120,  70),
    "FOOTBALL":         (  5, 122,  85),
    "SPORTS_FOOTBALL":  (  5, 122,  85),
    "SPORTS_LIVE":      (204,  41,  54),
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

_LOGO_SEARCH = [
    os.path.join(os.path.dirname(__file__), "assets", "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.jpg"),
    os.path.join(os.path.dirname(__file__), "vm_logo.png"),
]
_logo_cache = None

# ── Platform configs — Facebook and Instagram both 1080×1080 ──────────────
PLATFORMS = {
    "facebook": {
        "canvas":      (1080, 1080),
        "badge_fs":    30,
        "headline_fs": 60,
        "pad":         44,
        "logo_size":   66,
        "brand_fs":    24,
        "strip_h":     38,
        "strip_fs":    15,
        "line_gap":    16,
    },
    "instagram": {
        "canvas":      (1080, 1080),
        "badge_fs":    30,
        "headline_fs": 60,
        "pad":         44,
        "logo_size":   66,
        "brand_fs":    24,
        "strip_h":     38,
        "strip_fs":    15,
        "line_gap":    16,
    },
    "telegram": {
        "canvas":      (1280, 720),
        "badge_fs":    26,
        "headline_fs": 52,
        "pad":         42,
        "logo_size":   60,
        "brand_fs":    22,
        "strip_h":     32,
        "strip_fs":    14,
        "line_gap":    13,
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
    s   = min(img.width, img.height)
    img = img.crop(((img.width - s) // 2, (img.height - s) // 2,
                    (img.width - s) // 2 + s, (img.height - s) // 2 + s)).convert("RGBA")
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


def _top_vignette_overlay(width, height, vignette_h=140, opacity=0.65):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(min(vignette_h, height)):
        t = (1.0 - y / vignette_h) ** 1.6
        arr[y, :, 3] = int(opacity * 255 * t)
    return Image.fromarray(arr, "RGBA")


# ── Drawing helpers ────────────────────────────────────────────────────────

def _text_wh(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _draw_text_shadowed(draw, xy, text, font, fill=(255, 255, 255), shadow_offset=2):
    x, y = xy
    draw.text((x + shadow_offset + 1, y + shadow_offset + 1), text, font=font, fill=(0, 0, 0))
    draw.text((x + shadow_offset,     y + shadow_offset),     text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


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
    used = sum(len(l.split()) for l in lines)
    if used < len(words) and lines:
        last = lines[-1]
        while last and _text_wh(draw, last + "…", font)[0] > max_width:
            last = " ".join(last.split()[:-1])
        lines[-1] = (last + "…") if last else "…"
    return lines[:max_lines]


def _relative_time(published_at):
    if not published_at:
        return ""
    try:
        from datetime import datetime, timezone
        dt   = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1:    return "Just now"
        if mins < 60:   return f"{mins}m ago"
        if mins < 1440: return f"{mins // 60}h ago"
        return f"{mins // 1440}d ago"
    except Exception:
        return ""


# ── Badge drawing ──────────────────────────────────────────────────────────

def _draw_badge(draw, label, color, pad, badge_fs, badge_top, badge_left):
    font     = _load_font(badge_fs, bold=True)
    pad_x, pad_y = 22, 10
    tb = draw.textbbox((0, 0), label, font=font)
    bw = tb[2] - tb[0]
    bh = tb[3] - tb[1]
    badge_w = bw + pad_x * 2
    badge_h = bh + pad_y * 2

    sh_r = max(0, color[0] - 60)
    sh_g = max(0, color[1] - 60)
    sh_b = max(0, color[2] - 60)
    draw.rounded_rectangle(
        [badge_left + 2, badge_top + 3, badge_left + badge_w + 2, badge_top + badge_h + 3],
        radius=6, fill=(sh_r, sh_g, sh_b),
    )
    draw.rounded_rectangle(
        [badge_left, badge_top, badge_left + badge_w, badge_top + badge_h],
        radius=6, fill=color,
    )
    hl_color = tuple(min(255, c + 50) for c in color)
    draw.rounded_rectangle(
        [badge_left + 1, badge_top + 1, badge_left + badge_w - 1, badge_top + 3],
        radius=3, fill=hl_color,
    )
    draw.text(
        (badge_left + pad_x - tb[0], badge_top + pad_y - tb[1]),
        label, font=font, fill=(255, 255, 255),
    )
    return badge_w, badge_h


# ── Core composition — Al Jazeera style ───────────────────────────────────

def compose_image(image_url, platform, intent, headline, source_name,
                  published_at=None, image_path=None, tag_color=None):
    """
    Full-bleed photo with dark gradient overlay — professional news style.

      ┌──────────────────────────────────────┐
      │ ◉ VisionaryMinds    [vivid photo]    │ ← logo top-left, subtle vignette
      │                                      │
      │         [full-bleed HD photo]        │
      │                                      │
      │   ~ ~ ~ dark gradient fades in ~ ~ ~ │
      │                                      │
      │  ┌───────────────┐                   │
      │  │   CRICKET     │  ← coloured badge │
      │  └───────────────┘                   │
      │  Short punchy headline here          │ ← bold white, 2-3 lines
      │  second headline line                │
      │──────────────────────────────────────│
      │  VISIONARYMINDS              42m ago │ ← thin accent strip
      └──────────────────────────────────────┘
    """
    cfg    = PLATFORMS.get(platform, PLATFORMS["facebook"])
    W, H   = cfg["canvas"]
    pad    = cfg["pad"]
    accent = tag_color or TAG_COLORS.get(intent.upper(), TAG_RED)

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
        base = Image.new("RGBA", (W, H), (12, 12, 22, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        base = _enhance_photo(base)

    # 2. Dark gradient overlay from ~40% down (full-bleed Al Jazeera style) ─
    grad_start = int(H * 0.40)
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    for y in range(grad_start, H):
        t = (y - grad_start) / max(H - 1 - grad_start, 1)
        alpha = int(255 * min(1.0, t ** 0.52))
        arr[y, :, 0] = PANEL_BASE[0]
        arr[y, :, 1] = PANEL_BASE[1]
        arr[y, :, 2] = PANEL_BASE[2]
        arr[y, :, 3] = alpha
    gradient = Image.fromarray(arr, "RGBA")
    photo = Image.alpha_composite(base, gradient)

    # 3. Top vignette so logo stays readable on any bright photo ───────────
    top_vig = _top_vignette_overlay(W, H, vignette_h=130, opacity=0.65)
    photo = Image.alpha_composite(photo, top_vig)

    canvas = photo.convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # 4. Logo + brand name ─────────────────────────────────────────────────
    logo_size   = cfg["logo_size"]
    lx, ly      = 20, 20
    logo_placed = False
    _logo       = _load_logo()

    if _logo:
        backing_size = logo_size + 10
        backing = Image.new("RGBA", (backing_size, backing_size), (0, 0, 0, 0))
        ImageDraw.Draw(backing).ellipse(
            [0, 0, backing_size - 1, backing_size - 1], fill=(0, 0, 0, 130)
        )
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(backing, (lx - 5, ly - 5), backing)
        logo_r = _logo.resize((logo_size, logo_size), Image.LANCZOS)
        canvas_rgba.paste(logo_r, (lx, ly), logo_r)
        canvas      = canvas_rgba.convert("RGB")
        draw        = ImageDraw.Draw(canvas)
        logo_placed = True

    brand_font = _load_font(cfg["brand_fs"], bold=True)
    bx = lx + (logo_size + 10 if logo_placed else 0)
    by = ly + max(0, (logo_size - cfg["brand_fs"]) // 2)
    _draw_text_shadowed(draw, (bx, by), BRAND_NAME, brand_font, shadow_offset=1)

    # 5. Category badge (sits in the gradient zone) ────────────────────────
    badge_label = BADGE_LABELS.get(intent.upper(), intent.upper().replace("_", " "))
    badge_top   = int(H * 0.54)
    badge_w, badge_h = _draw_badge(
        draw, badge_label, accent, pad, cfg["badge_fs"], badge_top, pad
    )

    # 6. Headline text ─────────────────────────────────────────────────────
    headline_font = _load_font(cfg["headline_fs"], bold=True)
    max_text_w    = W - pad * 2
    lines         = _wrap_headline(draw, headline, headline_font, max_text_w, max_lines=3)
    line_step     = cfg["headline_fs"] + cfg["line_gap"]
    text_y        = badge_top + badge_h + 18

    for line in lines:
        _draw_text_shadowed(
            draw, (pad, text_y), line, headline_font,
            fill=(255, 255, 255), shadow_offset=2,
        )
        text_y += line_step

    # 7. Bottom watermark strip ────────────────────────────────────────────
    strip_h = cfg["strip_h"]
    strip_y = H - strip_h
    draw.rectangle([0, strip_y, W, H], fill=PANEL_BASE)
    draw.line([(0, strip_y), (W, strip_y)], fill=accent, width=2)

    strip_font = _load_font(cfg["strip_fs"], bold=False)
    draw.text(
        (pad, strip_y + (strip_h - cfg["strip_fs"]) // 2),
        BRAND_NAME.upper(), font=strip_font, fill=(140, 140, 170),
    )
    rel_time = _relative_time(published_at)
    if rel_time:
        tw, _ = _text_wh(draw, rel_time, strip_font)
        draw.text(
            (W - tw - pad, strip_y + (strip_h - cfg["strip_fs"]) // 2),
            rel_time, font=strip_font, fill=(140, 140, 170),
        )

    return canvas


# ── Public entry point ─────────────────────────────────────────────────────

def save_platform_images(image_url, intent, headline, source_name,
                         published_at=None, output_dir=None, image_path=None,
                         tag_color=None):
    """Generate a branded premium image for every active platform."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vm_images_")

    paths = {}
    for platform in PLATFORMS:
        try:
            img  = compose_image(image_url, platform, intent, headline,
                                 source_name, published_at,
                                 image_path=image_path, tag_color=tag_color)
            path = os.path.join(output_dir, f"{platform}.jpg")
            img.save(path, "JPEG", quality=96, optimize=True, subsampling=0)
            paths[platform] = path
            logger.info(f"Saved {platform} → {path}")
        except Exception as e:
            logger.error(f"compose_image failed [{platform}]: {e}")

    return paths
