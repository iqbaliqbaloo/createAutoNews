import os
import logging
import tempfile
from io import BytesIO

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

BRAND_NAME  = "VisionaryMinds"
TAG_RED     = (204,  41,  54)
PANEL_BASE  = (8,    8,   16)   # deep dark blue-black for panel

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

# ── Human-readable badge labels ────────────────────────────────────────────
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

# ── Logo search paths ──────────────────────────────────────────────────────
_LOGO_SEARCH = [
    os.path.join(os.path.dirname(__file__), "assets", "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.png"),
    os.path.join(os.path.dirname(__file__), "logo.jpg"),
    os.path.join(os.path.dirname(__file__), "vm_logo.png"),
]
_logo_cache = None

# ── Platform configs ───────────────────────────────────────────────────────
PLATFORMS = {
    "facebook": {
        "canvas":        (1200, 630),
        "panel_ratio":   0.43,       # fraction of canvas height
        "blend_h":       90,         # gradient blend zone height (px)
        "badge_fs":      25,
        "headline_fs":   50,
        "pad":           38,         # left/right content padding
        "logo_size":     56,
        "brand_fs":      21,
        "strip_h":       30,         # bottom watermark strip
        "strip_fs":      13,
        "accent_w":      5,          # left accent bar width
        "line_gap":      12,         # headline line gap
    },
    "instagram": {
        "canvas":        (1080, 1080),
        "panel_ratio":   0.40,
        "blend_h":       100,
        "badge_fs":      28,
        "headline_fs":   58,
        "pad":           40,
        "logo_size":     62,
        "brand_fs":      23,
        "strip_h":       34,
        "strip_fs":      14,
        "accent_w":      5,
        "line_gap":      14,
    },
    "telegram": {
        "canvas":        (1280, 720),
        "panel_ratio":   0.43,
        "blend_h":       90,
        "badge_fs":      25,
        "headline_fs":   50,
        "pad":           38,
        "logo_size":     56,
        "brand_fs":      21,
        "strip_h":       30,
        "strip_fs":      13,
        "accent_w":      5,
        "line_gap":      12,
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
    img  = img.crop(((img.width - s)//2, (img.height - s)//2,
                     (img.width - s)//2 + s, (img.height - s)//2 + s)).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, s-1, s-1], fill=255)
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
        nw = int(ih * w / h)
        img = img.crop(((iw - nw)//2, 0, (iw - nw)//2 + nw, ih))
    else:
        nh = int(iw * h / w)
        img = img.crop((0, (ih - nh)//2, iw, (ih - nh)//2 + nh))
    return img.resize((w, h), Image.LANCZOS)


def _enhance_photo(img):
    """Vivid, contrasty — premium news feel (not washed out)."""
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(1.18)      # +18 % saturation
    rgb = ImageEnhance.Contrast(rgb).enhance(1.10)   # +10 % contrast
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.12)  # slight sharpening
    return rgb.convert("RGBA")


def _top_vignette_overlay(width, height, vignette_h=140, opacity=0.72):
    """
    Gradient dark overlay at the very top so the logo stays readable
    against any bright sky or light photo area.
    """
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    for y in range(min(vignette_h, height)):
        t = (1.0 - y / vignette_h) ** 1.6   # steep easing
        arr[y, :, 3] = int(opacity * 255 * t)
    return Image.fromarray(arr, "RGBA")


def _blend_zone_overlay(width, blend_h, panel_color):
    """
    Gradient that smoothly dissolves the photo into the dark panel over
    blend_h pixels above the hard panel edge. Creates cinematic depth.
    """
    r, g, b = panel_color
    arr      = np.zeros((blend_h, width, 4), dtype=np.uint8)
    arr[:, :, 0] = r
    arr[:, :, 1] = g
    arr[:, :, 2] = b
    for y in range(blend_h):
        t = (y / (blend_h - 1)) ** 1.8   # slow start, fast finish
        arr[y, :, 3] = int(255 * t)
    return Image.fromarray(arr, "RGBA")


def _panel_gradient(width, panel_h, panel_color, accent_color):
    """
    Dark panel with subtle depth gradient: slightly lighter at top,
    deepest at bottom. Very slight accent tint in top 30px.
    """
    r, g, b = panel_color
    ar, ag, ab = accent_color
    arr = np.zeros((panel_h, width, 3), dtype=np.uint8)
    for y in range(panel_h):
        t = y / max(panel_h - 1, 1)     # 0.0 at panel top → 1.0 at bottom
        base_v = int(r + (2 - 2*t))
        # top 30px: faint accent tint
        if y < 30:
            blend = (30 - y) / 30 * 0.08
            rv = int(base_v * (1 - blend) + ar * blend)
            gv = int(base_v * (1 - blend) + ag * blend)
            bv = int(base_v * (1 - blend) + ab * blend)
        else:
            rv = gv = bv = max(0, base_v)
        arr[y, :] = [rv, gv, bv]
    return Image.fromarray(arr, "RGB")


# ── Drawing helpers ────────────────────────────────────────────────────────

def _text_wh(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def _draw_text_shadowed(draw, xy, text, font, fill=(255, 255, 255),
                        shadow_offset=2, shadow_opacity=200):
    x, y = xy
    # Multi-layer shadow for premium depth
    draw.text((x+shadow_offset+1, y+shadow_offset+1), text, font=font,
              fill=(0, 0, 0))
    draw.text((x+shadow_offset,   y+shadow_offset),   text, font=font,
              fill=(0, 0, 0))
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
    # Truncate last line with ellipsis if content overflows
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
        if mins < 1440: return f"{mins//60}h ago"
        return f"{mins//1440}d ago"
    except Exception:
        return ""


# ── Badge drawing ──────────────────────────────────────────────────────────

def _draw_badge(draw, label, color, pad, badge_fs, badge_top, badge_left):
    """
    Premium pill badge with a subtle dark shadow offset beneath it.
    Returns (badge_w, badge_h) so the caller knows where to start the headline.
    """
    font      = _load_font(badge_fs, bold=True)
    pad_x, pad_y = 20, 10
    tb = draw.textbbox((0, 0), label, font=font)
    bw = tb[2] - tb[0]
    bh = tb[3] - tb[1]
    badge_w = bw + pad_x * 2
    badge_h = bh + pad_y * 2

    # Shadow layer (2px offset, darkened colour)
    sh_r = max(0, color[0] - 60)
    sh_g = max(0, color[1] - 60)
    sh_b = max(0, color[2] - 60)
    draw.rounded_rectangle(
        [badge_left + 2, badge_top + 3,
         badge_left + badge_w + 2, badge_top + badge_h + 3],
        radius=6, fill=(sh_r, sh_g, sh_b),
    )
    # Main badge
    draw.rounded_rectangle(
        [badge_left, badge_top, badge_left + badge_w, badge_top + badge_h],
        radius=6, fill=color,
    )
    # Subtle inner highlight — thin lighter line at top of badge
    hl_color = tuple(min(255, c + 50) for c in color)
    draw.rounded_rectangle(
        [badge_left + 1, badge_top + 1,
         badge_left + badge_w - 1, badge_top + 3],
        radius=3, fill=hl_color,
    )
    # Text
    draw.text(
        (badge_left + pad_x - tb[0], badge_top + pad_y - tb[1]),
        label, font=font, fill=(255, 255, 255),
    )
    return badge_w, badge_h


# ── Core composition ───────────────────────────────────────────────────────

def compose_image(image_url, platform, intent, headline, source_name,
                  published_at=None, image_path=None, tag_color=None):
    """
    Premium news-style composition:

      ┌──────────────────────────────────────┐
      │ ◉ VisionaryMinds      [vivid photo]  │ ← logo + brand (top-left vignette)
      │                                      │
      │           [full-bleed photo]         │
      │                                      │
      │~~~ cinematic gradient blend zone ~~~~│ ← smooth photo → panel dissolve
      │▌ ┌─────────────────┐                 │ ← accent bar + badge (overlaps)
      │▌ │  BREAKING NEWS  │                 │
      │▌ └─────────────────┘                 │
      │▌  Large bold headline text here      │
      │▌  second line of headline            │
      │──────────────────────────────────────│
      │  VisionaryMinds                42m   │ ← watermark strip
      └──────────────────────────────────────┘
    """
    cfg   = PLATFORMS.get(platform, PLATFORMS["facebook"])
    W, H  = cfg["canvas"]

    panel_h    = int(H * cfg["panel_ratio"])
    strip_h    = cfg["strip_h"]
    panel_y    = H - panel_h               # where the panel starts
    blend_h    = cfg["blend_h"]
    blend_y    = panel_y - blend_h         # where blend zone starts
    pad        = cfg["pad"]
    accent_w   = cfg["accent_w"]

    accent  = tag_color or TAG_COLORS.get(intent.upper(), TAG_RED)

    # ── 1. Load and enhance photo ──────────────────────────────────────────
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
        base = Image.new("RGBA", (W, H), (15, 15, 25, 255))
    else:
        base = _crop_to_canvas(base, W, H)
        base = _enhance_photo(base)

    # ── 2. Top vignette (logo readability) ────────────────────────────────
    top_vig = _top_vignette_overlay(W, H, vignette_h=150, opacity=0.70)
    photo   = Image.alpha_composite(base, top_vig)

    # ── 3. Blend zone (photo → panel) ─────────────────────────────────────
    if blend_y >= 0:
        blend_ov = _blend_zone_overlay(W, blend_h, PANEL_BASE)
        blend_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        blend_canvas.paste(blend_ov, (0, blend_y))
        photo = Image.alpha_composite(photo, blend_canvas)

    canvas = photo.convert("RGB")

    # ── 4. Dark panel with depth gradient ─────────────────────────────────
    panel_img = _panel_gradient(W, panel_h, PANEL_BASE, accent)
    canvas.paste(panel_img, (0, panel_y))

    draw = ImageDraw.Draw(canvas)

    # ── 5. Bottom watermark strip ──────────────────────────────────────────
    strip_y = H - strip_h
    strip_color = tuple(max(0, c - 4) for c in PANEL_BASE)   # slightly darker
    draw.rectangle([0, strip_y, W, H], fill=strip_color)
    # Thin separator line
    draw.line([(0, strip_y), (W, strip_y)], fill=(40, 40, 60), width=1)

    strip_font = _load_font(cfg["strip_fs"], bold=False)
    draw.text((pad, strip_y + (strip_h - cfg["strip_fs"]) // 2),
              BRAND_NAME.upper(), font=strip_font, fill=(120, 120, 150))

    rel_time = _relative_time(published_at)
    if rel_time:
        tw, _ = _text_wh(draw, rel_time, strip_font)
        draw.text((W - tw - pad, strip_y + (strip_h - cfg["strip_fs"]) // 2),
                  rel_time, font=strip_font, fill=(120, 120, 150))

    # ── 6. Left accent bar (full panel height, excl. strip) ───────────────
    draw.rectangle([0, panel_y, accent_w, strip_y], fill=accent)

    # ── 7. Thin accent separator line at top of panel ─────────────────────
    draw.line([(accent_w, panel_y), (W, panel_y)], fill=accent, width=2)

    # ── 8. Logo + brand name — top-left ───────────────────────────────────
    logo_size = cfg["logo_size"]
    lx, ly    = 18, 14
    logo_placed = False
    _logo = _load_logo()

    if _logo:
        # Subtle dark circle backing for logo
        backing_size = logo_size + 10
        backing      = Image.new("RGBA", (backing_size, backing_size), (0, 0, 0, 0))
        bd           = ImageDraw.Draw(backing)
        bd.ellipse([0, 0, backing_size - 1, backing_size - 1], fill=(0, 0, 0, 130))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(backing, (lx - 5, ly - 5), backing)
        # Logo
        logo_r = _logo.resize((logo_size, logo_size), Image.LANCZOS)
        canvas_rgba.paste(logo_r, (lx, ly), logo_r)
        canvas      = canvas_rgba.convert("RGB")
        draw        = ImageDraw.Draw(canvas)
        logo_placed = True

    brand_font = _load_font(cfg["brand_fs"], bold=True)
    bx = lx + (logo_size + 10 if logo_placed else 0)
    by = ly + max(0, (logo_size - cfg["brand_fs"]) // 2)
    _draw_text_shadowed(draw, (bx, by), BRAND_NAME, brand_font, shadow_offset=1)

    # ── 9. Badge — overlapping the accent line ─────────────────────────────
    badge_label = BADGE_LABELS.get(intent.upper(), intent.upper().replace("_", " "))
    badge_left  = pad + accent_w + 4

    # Badge sits with bottom ~12px inside the panel (overlaps accent line)
    badge_top_provisional = panel_y - 10
    badge_fs = cfg["badge_fs"]

    # Draw badge and get its dimensions
    font_b    = _load_font(badge_fs, bold=True)
    tb_b      = draw.textbbox((0, 0), badge_label, font=font_b)
    badge_h_px = (tb_b[3] - tb_b[1]) + 20    # text + padding
    badge_top  = panel_y - badge_h_px + 14    # badge mostly in panel, top peeks into photo

    badge_w, badge_h = _draw_badge(
        draw, badge_label, accent,
        pad, badge_fs, badge_top, badge_left,
    )

    # ── 10. Headline — large, left-aligned, inside panel ─────────────────
    headline_font = _load_font(cfg["headline_fs"], bold=True)
    max_text_w    = W - pad * 2 - accent_w - 8
    lines         = _wrap_headline(draw, headline, headline_font, max_text_w, max_lines=3)
    line_step     = cfg["headline_fs"] + cfg["line_gap"]
    text_y        = badge_top + badge_h + 16

    for line in lines:
        _draw_text_shadowed(
            draw, (badge_left, text_y), line,
            headline_font, fill=(255, 255, 255), shadow_offset=2,
        )
        text_y += line_step

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
            img.save(path, "JPEG", quality=94, optimize=True)
            paths[platform] = path
            logger.info(f"Saved {platform} → {path}")
        except Exception as e:
            logger.error(f"compose_image failed [{platform}]: {e}")

    return paths
