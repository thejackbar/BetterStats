"""Smaller copies of uploaded photos, made on request and kept in memory.

A player photo is stored exactly as it was uploaded (up to 8 MB) and a card draws it at about 360 pixels wide. Sending the original to
every card was the slowest thing on the Player Cards pages. `?w=` on a photo URL asks for a copy no wider than the next size up
(`SIZES`), so the cache holds a handful per photo and a caller cannot ask for an odd size to fill it.

* The bytes at a photo URL never change (the `?v=` changes on every upload), so a copy is keyed by the photo and that `v`.
* A photo that is already small enough, or an animated GIF, is sent as it is.
* A photo with transparency stays a PNG; anything else becomes a JPEG.
* EXIF rotation is applied before the copy is made, because the copy has no EXIF to tell the browser.
* Decoding runs off the event loop (`resized`), and a copy being made is shared by everyone asking for it at once.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from io import BytesIO
from typing import Optional

from starlette.concurrency import run_in_threadpool

SIZES = (240, 480, 800, 1200)
_MAX_ENTRIES = 600
_MAX_BYTES = 96 * 1024 * 1024

_cache: "OrderedDict[tuple, tuple[bytes, str]]" = OrderedDict()
_cache_bytes = 0
_inflight: dict[tuple, "asyncio.Future"] = {}


def bucket(width: Optional[int]) -> Optional[int]:
    """The size to serve for a requested width, or None for the original."""
    if not width or width <= 0:
        return None
    return next((s for s in SIZES if width <= s), SIZES[-1])


def make_copy(data: bytes, mime: str, width: int) -> tuple[bytes, str]:
    """A copy of the image no wider than `width`, or the original bytes when it cannot or need not be made smaller."""
    from PIL import Image, ImageOps

    try:
        with Image.open(BytesIO(data)) as im:
            if getattr(im, "is_animated", False) or im.format == "GIF":
                return data, mime
            im = ImageOps.exif_transpose(im)
            if im.width <= width:
                return data, mime
            alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            im = im.convert("RGBA" if alpha else "RGB")
            im.thumbnail((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
            out = BytesIO()
            if alpha:
                im.save(out, format="PNG", optimize=True)
                return out.getvalue(), "image/png"
            im.save(out, format="JPEG", quality=82, optimize=True, progressive=True)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mime   # an image Pillow cannot read is served as uploaded, as it always was


def _remember(key: tuple, value: tuple[bytes, str]) -> None:
    global _cache_bytes
    _cache[key] = value
    _cache.move_to_end(key)
    _cache_bytes += len(value[0])
    while _cache and (len(_cache) > _MAX_ENTRIES or _cache_bytes > _MAX_BYTES):
        _, old = _cache.popitem(last=False)
        _cache_bytes -= len(old[0])


async def resized(key: tuple, data: bytes, mime: str, width: int) -> tuple[bytes, str]:
    """The copy for `key` (photo, version, size), made once however many ask at the same moment."""
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    pending = _inflight.get(key)
    if pending is not None:
        return await asyncio.shield(pending)
    fut: "asyncio.Future" = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        value = await run_in_threadpool(make_copy, data, mime, width)
        _remember(key, value)
        fut.set_result(value)
        return value
    except BaseException as exc:
        if not fut.done():
            fut.set_exception(exc)
            fut.exception()   # read it, so a copy nobody else was waiting for does not log "never retrieved"
        raise
    finally:
        _inflight.pop(key, None)


def clear() -> None:
    global _cache_bytes
    _cache.clear()
    _cache_bytes = 0
