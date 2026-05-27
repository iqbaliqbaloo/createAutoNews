import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

BRAND_NAME = "VisionaryMinds"

# Intent pill colours
INTENT_COLORS = {
    "WAR":      {"bg": (204, 41,  54),  "fg": (255, 255, 255)},
    "POLITICS": {"bg": (26,  86,  219), "fg": (255, 255, 255)},
    "ECONOMY":  {"bg": (5,   122, 85),  "fg": (255, 255, 255)},
    "DISASTER": {"bg": (208, 56,  1),   "fg": (255, 255, 255)},
    "SPORTS":   {"bg": (108, 43,  217), "fg": (255, 255, 255)},
}

# Platform canvas + layout configs
PLATFORMS = {
    "facebook": {
        "canvas":          (1200, 630),
        "tag_pos":         (40, 30),
        "tag_font_size":   26,
        "headline_y":      420,
        "headline_size":   52,
        "headline_max_w":  1000,
        "source_pos":      (40, 575),
        "source_size":     22,
        "brand_right_x":   1160,
        "brand_y":         575,
        "brand_size":      24,
    },
    "instagram": {
        "canvas":          (1080, 1080),
        "tag_pos":         (40, 40),
        "tag_font_size":   28,
        "headline_y":      750,
        "headline_size":   60,
        "headline_max_w":  900,
        "source_pos":      (40, 1010),
        "source_size":     24,
        "brand_right_x":   1040,
        "brand_y":         1010,
        "brand_size":      28,
    },
    # ── Twitter — uncomment when Twitter API credentials are added ──────────
    # "twitter": {
    #     "canvas":          (1200, 675),
    #     "tag_pos":         (40, 30),
    #     "tag_font_size":   22,
    #     "headline_y":      460,
    #     "headline_size":   46,
    #     "headline_max_w":  980,
    #     "source_pos":      (40, 625),
    #     "source_size":     20,
    #     "brand_right_x":   1160,
    #     "brand_y":         625,
    #     "brand_size":      22,
    #     "source_omit_time": True,   # Twitter shows tweet time natively
    # },
    # ── Telegram — uncomment when Telegram bot token is added ───────────────
    # "telegram": {
    #     "canvas":          (1280, 720),
    #     "tag_pos":         (50, 35),
    #     "tag_font_size":   26,
    #     "headline_y":      540,
    #     "headline_size":   54,
    #     "headline_max_w":  1050,
    #     "source_pos":      (50, 678),
    #     "source_size":     22,
    #     "brand_right_x":   1230,
    #     "brand_y":         678,
    #     "brand_size":      26,
    # },
}

# Font search paths (Ubuntu GitHub Actions + Windows dev)
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


# ── Font helpers ───────────────────────────────────────────────────────────

def _load_font(size, bold=True):
    paths = _BOLD_FONTS if bold else _REGULAR_FONTS
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Image helpers ──────────────────────────────────────────────────────────

def _fetch_image(url):
    """Download image from URL; returns RGBA PIL Image or None."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200 or len(r.content) < 5000:
            return None
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Image fetch failed ({url}): {e}")
        return None


def _crop_to_canvas(img, w, h):
    """Centre-crop + resize image to exact target dimensions."""
    iw, ih = img.size
    target_ratio = w / h
    img_ratio    = iw / ih

    if img_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        left  = (iw - new_w) // 2
        img   = img.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        top   = (ih - new_h) // 2
        img   = img.crop((0, top, iw, top + new_h))

    return img.resize((w, h), Image.LANCZOS)


def _desaturate(img, amount=0.12):
    """Reduce colour saturation by `amount` (0.12 = 12% desaturation)."""
    rgb = img.convert("RGB")
    enhanced = ImageEnhance.Color(rgb).enhance(1.0 - amount)
    return enhanced.convert("RGBA")


def _gradient_overlay(width, height):
    """
    Black gradient: bottom rgba(0,0,0,0.85) → top rgba(0,0,0,0.10).
    Built with numpy for smooth per-pixel alpha.
    """
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    alpha_top    = int(0.10 * 255)   # 26
    alpha_bottom = int(0.85 * 255)   # 217
    for y in range(height):
        t = y / max(height - 1, 1)   # 0 at top → 1 at bottom
        arr[y, :, 3] = int(alpha_top + (alpha_bottom - alpha_top) * t)
    return Image.fromarray(arr, "RGBA")


# ── Drawing helpers ────────────────────────────────────────────────────────

def _text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_pill(draw, text, pos, font, bg_color, fg_color, pad_x=20, pad_y=8):
    """Draw a pill-shaped badge with text centred inside."""
    x, y = pos
    tw, th = _text_size(draw, text, font)
    pw, ph = tw + pad_x * 2, th + pad_y * 2
    radius = ph // 2
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=radius, fill=bg_color)
    # Adjust for glyph bearing so text sits visually centred
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((x + pad_x - bbox[0], y + pad_y - bbox[1]), text, font=font, fill=fg_color)
    return pw, ph


def _wrap_headline(draw, text, font, max_width):
    """
    Word-wrap text to max_width pixels; returns at most 2 lines.
    If the full text doesn't fit in 2 lines the second line is trimmed
    and suffixed with "…" so readers know the headline continues.
    """
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if _text_size(draw, test, font)[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
            if len(lines) == 2:
                break   # hard stop at 2 lines
    if current and len(lines) < 2:
        lines.append(" ".join(current))

    # If text was truncated, suffix the last line with "…"
    used_words = sum(len(l.split()) for l in lines)
    if used_words < len(words) and lines:
        last = lines[-1]
        ellipsis = "…"
        # Trim words from the end until "last… " fits within max_width
        while last and _text_size(draw, last + ellipsis, font)[0] > max_width:
            last = " ".join(last.split()[:-1])
        lines[-1] = last + ellipsis

    return lines[:2]


def _draw_text_shadow(draw, pos, text, font, color=(255, 255, 255), shadow=(0, 0, 0)):
    x, y = pos
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x,     y    ), text, font=font, fill=color)


def _draw_text_right(draw, right_x, y, text, font, color=(255, 255, 255)):
    tw, _ = _text_size(draw, text, font)
    draw.text((right_x - tw, y), text, font=font, fill=color)


# ── Relative time ──────────────────────────────────────────────────────────

def _relative_time(published_at):
    if not published_at:
        return "Just now"
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


# ── Core composition ───────────────────────────────────────────────────────

def compose_image(image_url, platform, intent, headline, source_name, published_at=None):
    """
    Compose a single branded image for the given platform.
    Returns a PIL Image in RGB mode.
    """
    cfg = PLATFORMS[platform]
    W, H = cfg["canvas"]
    colors = INTENT_COLORS.get(intent, INTENT_COLORS["POLITICS"])

    # ── Layer 1: base image ──────────────────────────────────────────────
    base = _fetch_image(image_url)
    if base is None:
        base = Image.new("RGBA", (W, H), (20, 20, 30, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        base = _desaturate(base, amount=0.12)

    # ── Layer 2: gradient overlay ────────────────────────────────────────
    base = Image.alpha_composite(base, _gradient_overlay(W, H))

    # Convert to RGB for drawing (no transparency needed after compositing)
    canvas = base.convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # ── Fonts ────────────────────────────────────────────────────────────
    tag_font      = _load_font(cfg["tag_font_size"],  bold=True)
    headline_font = _load_font(cfg["headline_size"],  bold=True)
    source_font   = _load_font(cfg["source_size"],    bold=False)
    brand_font    = _load_font(cfg["brand_size"],     bold=True)

    # ── Intent tag pill ──────────────────────────────────────────────────
    _draw_pill(draw, intent, cfg["tag_pos"], tag_font, colors["bg"], colors["fg"])

    # ── Headline (centred, max 2 lines) ──────────────────────────────────
    lines      = _wrap_headline(draw, headline, headline_font, cfg["headline_max_w"])
    line_step  = cfg["headline_size"] + 10
    total_h    = len(lines) * line_step - 10
    start_y    = cfg["headline_y"]

    for i, line in enumerate(lines):
        lw, _   = _text_size(draw, line, headline_font)
        line_x  = (W - lw) // 2
        line_y  = start_y + i * line_step
        _draw_text_shadow(draw, (line_x, line_y), line, headline_font)

    # ── Source line ──────────────────────────────────────────────────────
    omit_time   = cfg.get("source_omit_time", False)
    rel_time    = _relative_time(published_at)
    source_text = (
        f"Source: {source_name}"
        if omit_time or not rel_time
        else f"Source: {source_name} | {rel_time}"
    )
    draw.text(cfg["source_pos"], source_text, font=source_font, fill=(200, 200, 200))

    # ── Brand name (right-aligned) ───────────────────────────────────────
    _draw_text_right(draw, cfg["brand_right_x"], cfg["brand_y"], BRAND_NAME, brand_font)

    return canvas


# ── Public entry point ─────────────────────────────────────────────────────

def save_platform_images(image_url, intent, headline, source_name,
                         published_at=None, output_dir=None):
    """
    Generate and save a separate image for every active platform.
    Returns dict mapping platform name → file path.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vm_images_")

    paths = {}
    for platform in PLATFORMS:
        try:
            img  = compose_image(image_url, platform, intent, headline, source_name, published_at)
            path = os.path.join(output_dir, f"{platform}.jpg")
            img.save(path, "JPEG", quality=92, optimize=True)
            paths[platform] = path
            logger.info(f"Saved {platform} image → {path}")
        except Exception as e:
            logger.error(f"compose_image failed for {platform}: {e}")

    return paths
