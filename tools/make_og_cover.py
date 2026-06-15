#!/usr/bin/env python3
"""Generate the social-share cover image (og-cover.png).

This is the 1200x630 landscape card that Facebook, WhatsApp, iMessage,
LinkedIn and the rest show when someone shares a Better Cricket link. The
square logo (og-image.png) stays the favicon/app icon; this wider card is
purpose-built for link previews.

It reuses the real logo mark out of og-image.png (transparent background)
and renders the current "Better Cricket" wordmark + tagline beside it on the
brand navy. Re-run after a brand tweak:

    python3 tools/make_og_cover.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
SRC_LOGO = PUBLIC / "og-image.png"
OUT = PUBLIC / "og-cover.png"

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


def main():
    img = vertical_gradient((W, H), NAVY_TOP, NAVY_BOT).convert("RGBA")

    # --- logo mark (cropped out of the square logo, wordmark trimmed off) ---
    logo = Image.open(SRC_LOGO).convert("RGBA")
    lw, lh = logo.size
    mark = logo.crop((0, 0, lw, int(lh * 0.66)))  # drop the "BetterStats" wordmark
    bbox = mark.getbbox()
    if bbox:
        mark = mark.crop(bbox)
    target_h = 372
    scale = target_h / mark.height
    mark = mark.resize((int(mark.width * scale), target_h), Image.LANCZOS)

    # Anchor by the right edge so the arrow never clips off-canvas.
    right_margin = 76
    paste_x = W - right_margin - mark.width
    paste_y = (H - mark.height) // 2
    mark_cx = paste_x + mark.width // 2
    mark_cy = H // 2

    glow = radial_glow((W, H), (mark_cx, mark_cy), 240, ACCENT, 52)
    img = Image.alpha_composite(img, glow)
    img.alpha_composite(mark, (paste_x, paste_y))

    d = ImageDraw.Draw(img)

    # --- left-hand text block ---
    x = 80
    # accent rule
    d.rounded_rectangle([x, 150, x + 64, 158], radius=4, fill=ACCENT)

    f_word = font(F_BOLD, 104)
    d.text((x - 4, 178), "Better", font=f_word, fill=WHITE)
    d.text((x - 4, 292), "Cricket", font=f_word, fill=ACCENT)

    f_tag = font(F_REG, 31)
    d.text((x, 428), "The platform Australian", font=f_tag, fill=SLATE)
    d.text((x, 468), "cricket clubs run on", font=f_tag, fill=SLATE)

    # module line, letter-spaced uppercase
    f_mod = font(F_BOLD, 18)
    draw_spaced(
        d, (x, 540),
        "STATS  ·  SELECTION  ·  SOCIALS  ·  ADMIN  ·  ANALYTICS",
        f_mod, FAINT, tracking=1.5,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
