#!/usr/bin/env python3
"""Frame a raw app screenshot the way the marketing site images are framed.

The site's module and feature images are 1920x1080 JPGs: the app window with
rounded corners on a diagonal gradient in the module's accent colour. This
turns a raw capture into that.

    python3 tools/frame_marketing_shot.py raw.png out.jpg --accent select
    python3 tools/frame_marketing_shot.py raw.png out.jpg --accent admin \
        --crop 0,130,3200,1858          # x0,y0,x1,y1 in raw pixels

--crop is for cutting the club-site header off admin captures (it shows the
app version number, which stays off public pages).

Tall pages: the window is never narrower than --min-width, so a long page is
cut off at the bottom (top-aligned) instead of shrunk to a sliver.

Needs Pillow and numpy.
"""
import argparse
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# lib/moduleBrand.js
ACCENTS = {
    'stats': '#16C784',
    'select': '#3B82F6',
    'socials': '#EC4899',
    'admin': '#F59E0B',
    'iq': '#A855F7',
    'fantasy': '#06B6D4',
}
NAVY = (11, 16, 32)
CANVAS = (1920, 1080)
MAX_W, MAX_H = 1728, 900


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def gradient(accent_hex, size=CANVAS):
    w, h = size
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]
    t = np.clip((xs * 0.55 + ys * 0.45) * 1.3, 0, 1) ** 0.9
    a = np.array(hex_rgb(accent_hex), dtype=float)
    n = np.array(NAVY, dtype=float)
    arr = a[None, None, :] * (1 - t[..., None]) + n[None, None, :] * t[..., None]
    return Image.fromarray(arr.astype('uint8'), 'RGB')


def rounded(im, radius):
    im = im.convert('RGBA')
    mask = Image.new('L', im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    im.putalpha(mask)
    return im


def paste_window(canvas, win, x, y, radius=36):
    """Paste a rounded window with a soft shadow."""
    shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x, y + 14, x + win.width, y + win.height + 14), radius, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(rounded(win, radius), (x, y))


def window_for(raw, min_width=1300, max_w=MAX_W, max_h=MAX_H):
    """Scale a raw capture into the window box. Returns the window image."""
    w, h = raw.size
    s = min(max_w / w, max_h / h)
    ww, wh = round(w * s), round(h * s)
    if ww < min_width and min_width is not None:
        # tall page: hold the width, cut the bottom
        s = min_width / w
        ww = min_width
        wh = min(max_h, round(h * s))
        raw = raw.resize((ww, round(h * s)), Image.LANCZOS).crop((0, 0, ww, wh))
        return raw
    return raw.resize((ww, wh), Image.LANCZOS)


def frame(src, dst, accent, crop=None, min_width=1300, quality=84):
    raw = Image.open(src).convert('RGB')
    if crop:
        raw = raw.crop(crop)
    win = window_for(raw, min_width=min_width)
    canvas = gradient(ACCENTS.get(accent, accent)).convert('RGBA')
    paste_window(canvas, win, (CANVAS[0] - win.width) // 2, (CANVAS[1] - win.height) // 2)
    out = canvas.convert('RGB')
    # keep each image under ~700 KB
    for q in (quality, 80, 76, 72, 68):
        out.save(dst, 'JPEG', quality=q, optimize=True, progressive=True)
        import os
        if os.path.getsize(dst) <= 700 * 1024:
            break
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--accent', default='stats', help=f"one of {', '.join(ACCENTS)} or a #hex")
    ap.add_argument('--crop', help='x0,y0,x1,y1 in raw pixels')
    ap.add_argument('--min-width', type=int, default=1300)
    a = ap.parse_args()
    crop = tuple(int(v) for v in a.crop.split(',')) if a.crop else None
    frame(a.src, a.dst, a.accent, crop, a.min_width)
    print('wrote', a.dst)


if __name__ == '__main__':
    sys.exit(main())
