import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

BRAND_NAME  = "VisionaryMinds"
TAG_RED     = (204, 41, 54)      # all category tags use this red (#CC2936)
TAG_RED_DK  = (160, 20, 35)      # subtle darker shadow edge for depth

# Optional logo file — place logo.png in the project root to use it.
_LOGO_SEARCH = [
    os.path.join(os.path.dirname(__file__), "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.jpg"),
    os.path.join(os.path.dirname(__file__), "vm_logo.png"),
]
_logo_cache = None   # False = checked, no file found; PIL Image = found

# ── Platform canvas + layout ───────────────────────────────────────────────

PLATFORMS = {
    "facebook": {
        "canvas":         (1200, 630),
        "top_bar_h":      80,
        "brand_x":        30,
        "brand_y":        20,
        "brand_size":     26,
        "tag_right":      1170,
        "tag_y":          20,
        "tag_size":       22,
        "headline_y":     430,
        "headline_size":  52,
        "headline_max_w": 1100,
    },
    "instagram": {
        "canvas":         (1080, 1080),
        "top_bar_h":      90,
        "brand_x":        30,
        "brand_y":        24,
        "brand_size":     28,
        "tag_right":      1050,
        "tag_y":          24,
        "tag_size":       24,
        "headline_y":     760,
        "headline_size":  60,
        "headline_max_w": 1000,
    },
    # ── Twitter — uncomment + add credentials to post.yml to enable ─────────
    # "twitter": {
    #     "canvas":         (1200, 675),
    #     "top_bar_h":      75,
    #     "brand_x":        30,
    #     "brand_y":        18,
    #     "brand_size":     22,
    #     "tag_right":      1170,
    #     "tag_y":          18,
    #     "tag_size":       20,
    #     "headline_y":     460,
    #     "headline_size":  46,
    #     "headline_max_w": 1100,
    #     "source_y":       643,
    #     "source_size":    17,
    #     "source_omit_time": True,
    # },
    # ── Telegram — uncomment + add bot token env var to post.yml to enable ──
    # "telegram": {
    #     "canvas":         (1280, 720),
    #     "top_bar_h":      82,
    #     "brand_x":        36,
    #     "brand_y":        22,
    #     "brand_size":     26,
    #     "tag_right":      1245,
    #     "tag_y":          22,
    #     "tag_size":       22,
    #     "headline_y":     520,
    #     "headline_size":  54,
    #     "headline_max_w": 1200,
    #     "source_y":       690,
    #     "source_size":    19,
    # },
}

# ── Font paths ─────────────────────────────────────────────────────────────

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


# ── Logo loader ────────────────────────────────────────────────────────────

def _make_circular(img):
    """
    Crop the image to a square, then apply a circular alpha mask so the logo
    composites cleanly over any dark background with no white corners.
    Works for logos that have a circular design with a white rectangular frame.
    """
    s    = min(img.width, img.height)
    left = (img.width  - s) // 2
    top  = (img.height - s) // 2
    img  = img.crop((left, top, left + s, top + s)).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, s - 1, s - 1], fill=255)
    img.putalpha(mask)
    return img


def _load_logo():
    """Return RGBA PIL Image of logo (circular-masked), or None if no logo file found."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache if _logo_cache is not False else None
    for path in _LOGO_SEARCH:
        if os.path.exists(path):
            try:
                raw         = Image.open(path).convert("RGBA")
                _logo_cache = _make_circular(raw)
                logger.info(f"Logo loaded from {path}")
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
        if r.status_code != 200 or len(r.content) < 5000:
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


def _desaturate(img, amount=0.12):
    return ImageEnhance.Color(img.convert("RGB")).enhance(1.0 - amount).convert("RGBA")


def _bottom_gradient(width, height):
    """Dark gradient rising from the bottom — covers the headline area."""
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    alpha_top    = int(0.08 * 255)
    alpha_bottom = int(0.88 * 255)
    for y in range(height):
        t = y / max(height - 1, 1)
        arr[y, :, 3] = int(alpha_top + (alpha_bottom - alpha_top) * t)
    return Image.fromarray(arr, "RGBA")


def _top_bar_overlay(width, height, bar_h):
    """Dark gradient falling from the top — covers the brand + tag area."""
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(min(bar_h, height)):
        # Strongest at top (y=0), fades to zero at y=bar_h
        t = 1.0 - (y / bar_h)
        arr[y, :, 3] = int(210 * t)
    return Image.fromarray(arr, "RGBA")


# ── Drawing helpers ────────────────────────────────────────────────────────

def _text_wh(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _draw_text(draw, xy, text, font, color=(255, 255, 255), shadow=True):
    x, y = xy
    if shadow:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


def _wrap_headline(draw, text, font, max_width):
    """
    Word-wrap to at most 2 lines. Truncates last line with "…" when the full
    headline doesn't fit, so the reader always knows more is implied.
    """
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
            if len(lines) == 2:
                break
    if current and len(lines) < 2:
        lines.append(" ".join(current))

    used = sum(len(l.split()) for l in lines)
    if used < len(words) and lines:
        last = lines[-1]
        ellipsis = "…"
        while last and _text_wh(draw, last + ellipsis, font)[0] > max_width:
            last = " ".join(last.split()[:-1])
        lines[-1] = (last + ellipsis) if last else ellipsis

    return lines[:2]


# ── Brand element (top-left) ───────────────────────────────────────────────

def _draw_brand(draw, canvas_img, cfg):
    """
    Render VisionaryMinds brand at top-left.
    Uses logo.png if present in the project root, otherwise falls back to
    a white "VM" badge so the layout is never empty.
    """
    bx   = cfg["brand_x"]
    by   = cfg["brand_y"]
    size = cfg["brand_size"]
    font = _load_font(size, bold=True)
    cx   = bx

    logo = _load_logo()

    if logo:
        # Logo is circular (square after _make_circular), scale to brand height + generous padding
        logo_h = size + 18   # slightly taller than the text for visual weight
        logo_r = logo.resize((logo_h, logo_h), Image.LANCZOS)
        # Vertically centre the circle relative to brand text
        logo_y = by - (logo_h - size) // 2
        canvas_img.paste(logo_r, (cx, max(0, logo_y)), logo_r)
        cx += logo_h + 10
    else:
        # Fallback: white rounded "VM" badge
        mark_font = _load_font(max(size - 8, 12), bold=True)
        mb = draw.textbbox((0, 0), "VM", font=mark_font)
        mw, mh = mb[2] - mb[0], mb[3] - mb[1]
        box_w, box_h = mw + 14, mh + 10
        # Align badge vertically to the brand text cap-height
        badge_y = by + max(0, (size - box_h) // 2)
        draw.rounded_rectangle(
            [cx, badge_y, cx + box_w, badge_y + box_h],
            radius=5, fill=(255, 255, 255),
        )
        draw.text(
            (cx + 7 - mb[0], badge_y + 5 - mb[1]),
            "VM", font=mark_font, fill=(20, 20, 30),
        )
        cx += box_w + 10

    # Brand name text
    tb = draw.textbbox((0, 0), BRAND_NAME, font=font)
    text_y = by + max(0, ((size + 8) - (tb[3] - tb[1])) // 2) - tb[1]
    draw.text((cx, text_y), BRAND_NAME, font=font, fill=(255, 255, 255))


# ── Category tag (top-right, always red) ──────────────────────────────────

def _draw_category_tag(draw, label, cfg):
    """
    Render the category tag at top-right as a RED rectangular box with
    white bold text. All intents use the same red — brand consistency.
    """
    rx   = cfg["tag_right"]
    ry   = cfg["tag_y"]
    size = cfg["tag_size"]
    font = _load_font(size, bold=True)

    pad_x, pad_y = 16, 8
    tb = draw.textbbox((0, 0), label, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    tag_w  = tw + pad_x * 2
    tag_h  = th + pad_y * 2
    tag_x  = rx - tag_w     # right-align

    draw.rounded_rectangle(
        [tag_x, ry, tag_x + tag_w, ry + tag_h],
        radius=4, fill=TAG_RED,
    )
    draw.text(
        (tag_x + pad_x - tb[0], ry + pad_y - tb[1]),
        label, font=font, fill=(255, 255, 255),
    )


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

def compose_image(image_url, platform, intent, headline, source_name,
                  published_at=None, image_path=None):
    """
    Compose a single branded image for the given platform.

    Layout:
      TOP LEFT  → VisionaryMinds logo + name
      TOP RIGHT → Category tag (RED box, white text)
      BOTTOM    → Large bold headline (max 2 lines, centred)

    image_path: pre-downloaded temp file from pixabay_searcher (preferred).
                Falls back to downloading image_url if path is absent/invalid.
                Both being None produces a dark fallback background.
    """
    cfg = PLATFORMS[platform]
    W, H = cfg["canvas"]

    # ── Base image ─────────────────────────────────────────────────────────
    # Priority 1: use the already-downloaded, CLIP-validated file (no network risk)
    base = None
    if image_path and os.path.exists(image_path):
        try:
            base = Image.open(image_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"Failed to open pre-downloaded image {image_path}: {e}")

    # Priority 2: download from URL (fallback if path not provided or failed)
    if base is None and image_url:
        base = _fetch_image(image_url)

    # Priority 3: dark placeholder (should never be reached in normal operation)
    if base is None:
        logger.warning("No image available — using dark placeholder")
        base = Image.new("RGBA", (W, H), (18, 18, 28, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        base = _desaturate(base, amount=0.12)

    # ── Gradient overlays (composited before drawing) ─────────────────────
    base = Image.alpha_composite(base, _bottom_gradient(W, H))
    base = Image.alpha_composite(base, _top_bar_overlay(W, H, cfg["top_bar_h"]))

    canvas = base.convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    # ── TOP LEFT: brand ───────────────────────────────────────────────────
    _draw_brand(draw, canvas, cfg)

    # ── TOP RIGHT: category tag ───────────────────────────────────────────
    _draw_category_tag(draw, intent, cfg)

    # ── BOTTOM: headline (large, bold, white, max 2 lines, centred) ───────
    headline_font = _load_font(cfg["headline_size"], bold=True)
    lines     = _wrap_headline(draw, headline, headline_font, cfg["headline_max_w"])
    line_step = cfg["headline_size"] + 12
    start_y   = cfg["headline_y"]

    for i, line in enumerate(lines):
        lw, _ = _text_wh(draw, line, headline_font)
        lx    = (W - lw) // 2
        ly    = start_y + i * line_step
        _draw_text(draw, (lx, ly), line, headline_font, shadow=True)

    return canvas


# ── Public entry point ─────────────────────────────────────────────────────

def save_platform_images(image_url, intent, headline, source_name,
                         published_at=None, output_dir=None, image_path=None):
    """
    Generate and save a separate image for every active platform.
    image_path: pre-downloaded temp file from pixabay_searcher (used instead of
                re-downloading from image_url, eliminating network-failure blanks).
    Returns dict mapping platform name → file path.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="vm_images_")

    paths = {}
    for platform in PLATFORMS:
        try:
            img  = compose_image(image_url, platform, intent, headline,
                                 source_name, published_at, image_path=image_path)
            path = os.path.join(output_dir, f"{platform}.jpg")
            img.save(path, "JPEG", quality=92, optimize=True)
            paths[platform] = path
            logger.info(f"Saved {platform} image → {path}")
        except Exception as e:
            logger.error(f"compose_image failed for {platform}: {e}")

    return paths
