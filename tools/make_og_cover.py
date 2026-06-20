#!/usr/bin/env python3
"""Generate the BetterCricket social images.

Produces both share assets from the one canonical brand mark:
  * og-cover.png  — the 1200x630 landscape card Facebook, WhatsApp, iMessage,
    LinkedIn and the rest show on a shared link (eyebrow, tagline, mark).
  * og-image.png  — the 1200x1200 square brand logo used as the schema.org
    Organization logo in structured data.

The mark is read straight out of the canonical logo (the green "B" + growth
bars), the same artwork BrandLogo renders in the nav, footer and admin header,
so the social images can never drift from the in-app brand. Re-run after a
brand tweak:

    python3 tools/make_og_cover.py
"""
import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
# Canonical brand mark — white bars variant, for the navy social backgrounds.
SRC_SVG = ROOT / "frontend" / "src" / "assets" / "bettercricket-white.svg"
OUT = PUBLIC / "og-cover.png"
OUT_SQUARE = PUBLIC / "og-image.png"

W, H = 1200, 630

# Brand palette (matches the app's navy/accent theme).
NAVY_TOP = (13, 23, 48)      # #0d1730
NAVY_BOT = (6, 10, 18)       # #060a12
ACCENT = (22, 199, 132)      # #16c784
WHITE = (241, 245, 249)      # #f1f5f9
SLATE = (148, 163, 184)      # #94a3b8
FAINT = (100, 116, 139)      # #64748b

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
F_BOLD = f"{FONT_DIR}/DejaVuSans-Bold.ttf"
F_REG = f"{FONT_DIR}/DejaVuSans.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def vertical_gradient(size, top, bot):
    w, h = size
    base = Image.new("RGB", size, top)
    top_arr = top
    grad = Image.new("L", (1, h))
    for y in range(h):
        grad.putpixel((0, y), int(255 * y / max(1, h - 1)))
    grad = grad.resize(size)
    bot_img = Image.new("RGB", size, bot)
    return Image.composite(bot_img, base, grad)


def radial_glow(size, centre, radius, colour, max_alpha):
    """A soft circular glow used behind the logo mark."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = centre
    d.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=colour + (max_alpha,),
    )
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.55))


def draw_spaced(draw, xy, text, fnt, fill, tracking):
    """Draw text with manual letter-spacing (Pillow has none)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def load_mark():
    """The canonical brand mark, tight-cropped, from the embedded PNG in the SVG.

    The bettercricket-*.svg files are a square canvas wrapping one base64 PNG of
    the green-B-plus-bars artwork. Decode it directly (no SVG rasteriser needed)
    and trim the transparent margins so callers can scale it cleanly.
    """
    svg = SRC_SVG.read_text()
    m = re.search(r'href="data:image/png;base64,([^"]+)"', svg)
    if not m:
        raise SystemExit(f"no embedded PNG found in {SRC_SVG}")
    mark = Image.open(BytesIO(base64.b64decode(m.group(1)))).convert("RGBA")
    bbox = mark.getbbox()
    return mark.crop(bbox) if bbox else mark


def scaled_to_height(mark, target_h):
    scale = target_h / mark.height
    return mark.resize((int(mark.width * scale), target_h), Image.LANCZOS)


def render_cover(mark):
    """The 1200x630 landscape share card."""
    img = vertical_gradient((W, H), NAVY_TOP, NAVY_BOT).convert("RGBA")

    m = scaled_to_height(mark, 300)

    # Anchor by the right edge so the mark never clips off-canvas.
    right_margin = 80
    paste_x = W - right_margin - m.width
    paste_y = (H - m.height) // 2
    mark_cx = paste_x + m.width // 2

    glow = radial_glow((W, H), (mark_cx, H // 2), 230, ACCENT, 52)
    img = Image.alpha_composite(img, glow)
    img.alpha_composite(m, (paste_x, paste_y))

    d = ImageDraw.Draw(img)

    # --- left-hand text block: brand eyebrow + tagline hero + module strip ---
    x = 80
    text_limit = paste_x - 36  # keep a gutter between the copy and the mark

    # accent rule
    d.rounded_rectangle([x, 96, x + 64, 104], radius=4, fill=ACCENT)

    # brand eyebrow (one word, the canonical BetterCricket name)
    f_eye = font(F_BOLD, 22)
    draw_spaced(d, (x, 122), "BETTERCRICKET", f_eye, SLATE, tracking=3)

    # tagline hero ("better." in accent, the brand pun). Size to fit the column.
    hero_lines = [("Making your", WHITE), ("cricket club", WHITE), ("better.", ACCENT)]
    hero_size = 76
    while hero_size > 40:
        f_hero = font(F_BOLD, hero_size)
        if max(d.textlength(t, font=f_hero) for t, _ in hero_lines) <= text_limit - x:
            break
        hero_size -= 2
    step = hero_size + 12
    y0 = 176
    for i, (text, colour) in enumerate(hero_lines):
        d.text((x - 4, y0 + i * step), text, font=f_hero, fill=colour)

    # module strip, letter-spaced uppercase
    f_mod = font(F_BOLD, 18)
    draw_spaced(
        d, (x, 500),
        "STATS  ·  SELECTION  ·  SOCIALS  ·  ADMIN  ·  ANALYTICS",
        f_mod, FAINT, tracking=1.5,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({img.size[0]}x{img.size[1]})")


def render_square(mark, size=1200):
    """The square brand logo (schema.org Organization logo)."""
    img = vertical_gradient((size, size), NAVY_TOP, NAVY_BOT).convert("RGBA")
    m = scaled_to_height(mark, int(size * 0.40))
    if m.width > size * 0.66:  # keep wide marks inside a comfortable margin
        m = m.resize((int(size * 0.66), int(m.height * (size * 0.66) / m.width)), Image.LANCZOS)
    cx, cy = size // 2, size // 2
    glow = radial_glow((size, size), (cx, cy), int(size * 0.34), ACCENT, 60)
    img = Image.alpha_composite(img, glow)
    img.alpha_composite(m, (cx - m.width // 2, cy - m.height // 2))
    img.convert("RGB").save(OUT_SQUARE, "PNG", optimize=True)
    print(f"wrote {OUT_SQUARE} ({img.size[0]}x{img.size[1]})")


def main():
    mark = load_mark()
    render_square(mark)
    render_cover(mark)


if __name__ == "__main__":
    main()
