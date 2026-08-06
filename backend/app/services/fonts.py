"""Per-club custom typography — shared constants for club_admin.py (upload +
settings sanitisation) and images.py (serving).

Three independent roles: display (headings), body (paragraph text) and mono
(numbers/stats — maps onto the app's `font-mono` styling used throughout stat
figures and tabular data). Each is either left unset (app default), pointed
at a curated built-in preset (a Google Fonts family already loaded site-wide
via index.html — see frontend/src/lib/theme.js FONT_PRESETS, which this key
set mirrors), or an uploaded font file. Presets need no upload at all; an
uploaded file is validated by extension/size and stored as bytes on the
organisation row (font_{role}_data / font_{role}_mime — see models/db.py).
"""

FONT_ROLES = ("display", "body", "mono")

# Mirrors frontend/src/lib/theme.js DISPLAY_FONT_PRESETS / BODY_FONT_PRESETS /
# MONO_FONT_PRESETS — keep all three lists in sync by hand (no shared build
# step between the two).
DISPLAY_FONT_PRESET_KEYS = {
    "oswald", "anton", "bebas", "archivo_black", "teko", "big_shoulders",
    "antonio", "saira_condensed", "abril", "bungee", "playfair", "fredoka",
    "barlow_condensed",
}
BODY_FONT_PRESET_KEYS = {
    "inter", "geist", "hanken", "spectral", "cormorant", "archivo",
}
MONO_FONT_PRESET_KEYS = {
    "jetbrains_mono", "ibm_plex_mono", "space_mono", "roboto_mono",
}

FONT_PRESET_KEYS_BY_ROLE = {
    "display": DISPLAY_FONT_PRESET_KEYS,
    "body": BODY_FONT_PRESET_KEYS,
    "mono": MONO_FONT_PRESET_KEYS,
}

FONT_ALLOWED_EXTS = {".woff2", ".woff", ".ttf", ".otf"}
FONT_MAX_BYTES = 6 * 1024 * 1024  # 6 MB — variable multi-weight files can run a couple of MB

_FONT_MIME_BY_EXT = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}

# CSS @font-face `format()` hint, keyed the same way.
_FONT_FORMAT_BY_EXT = {
    ".woff2": "woff2",
    ".woff": "woff",
    ".ttf": "truetype",
    ".otf": "opentype",
}

_FONT_FORMAT_BY_MIME = {
    "font/woff2": "woff2",
    "font/woff": "woff",
    "font/ttf": "truetype",
    "font/otf": "opentype",
}


# Weights an admin can pick per role. 400 is Regular, 700 Bold; a club whose
# font ships one weight only should be left on whatever that weight is.
FONT_WEIGHT_CHOICES = (300, 400, 500, 600, 700, 800, 900)


def sanitize_weight(value) -> int | None:
    """A weight from the admin form, or None for 'use the app default'."""
    try:
        weight = int(value)
    except (TypeError, ValueError):
        return None
    return weight if weight in FONT_WEIGHT_CHOICES else None


def mime_for_ext(ext: str) -> str:
    return _FONT_MIME_BY_EXT.get(ext.lower(), "font/woff2")


def format_for_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    return _FONT_FORMAT_BY_MIME.get(mime.lower(), "woff2")


# ---------------------------------------------------------------------------
# Reading what weights an uploaded file actually carries
# ---------------------------------------------------------------------------
#
# This is what stops the browser faking a bold. A club uploads ONE file, so
# unless that file is a variable font with a `wght` axis it holds exactly one
# weight - and every `font-weight: 700` on the page is then synthesised by
# smearing the outlines, which reads as muddy and too dark (reported by a club
# running Patua One, a 400-only slab serif). buildThemeCss turns synthesis off
# for a single-weight face, so a bold request renders the real weight instead.
#
# Reported on the upload screen too, so an admin can see why their headings
# are not bold rather than assuming the upload failed.

_WOFF2_KNOWN_TAGS = (
    "cmap", "head", "hhea", "hmtx", "maxp", "name", "OS/2", "post", "cvt ",
    "fpgm", "glyf", "loca", "prep", "CFF ", "VORG", "EBDT", "EBLC", "gasp",
    "hdmx", "kern", "LTSH", "PCLT", "VDMX", "vhea", "vmtx", "BASE", "GDEF",
    "GPOS", "GSUB", "EBSC", "JSTF", "MATH", "CBDT", "CBLC", "COLR", "CPAL",
    "SVG ", "sbix", "acnt", "avar", "bdat", "bloc", "bsln", "cvar", "fdsc",
    "feat", "fmtx", "fvar", "gvar", "hsty", "just", "lcar", "mort", "morx",
    "opbd", "prop", "trak", "Zapf", "Silf", "Glat", "Gloc", "Feat", "Sill",
)


def _sfnt_tables(data: bytes) -> dict[str, bytes]:
    """Table tag -> bytes for a plain .ttf/.otf."""
    if len(data) < 12:
        return {}
    num = int.from_bytes(data[4:6], "big")
    out: dict[str, bytes] = {}
    for i in range(num):
        rec = 12 + 16 * i
        if rec + 16 > len(data):
            break
        tag = data[rec:rec + 4].decode("latin1")
        off = int.from_bytes(data[rec + 8:rec + 12], "big")
        length = int.from_bytes(data[rec + 12:rec + 16], "big")
        if off + length <= len(data):
            out[tag] = data[off:off + length]
    return out


def _woff_tables(data: bytes) -> dict[str, bytes]:
    """Table tag -> bytes for a .woff, whose tables are individually zlib'd."""
    import zlib

    if len(data) < 44:
        return {}
    num = int.from_bytes(data[12:14], "big")
    out: dict[str, bytes] = {}
    for i in range(num):
        rec = 44 + 20 * i
        if rec + 20 > len(data):
            break
        tag = data[rec:rec + 4].decode("latin1")
        off = int.from_bytes(data[rec + 4:rec + 8], "big")
        comp = int.from_bytes(data[rec + 8:rec + 12], "big")
        orig = int.from_bytes(data[rec + 12:rec + 16], "big")
        if off + comp > len(data):
            continue
        raw = data[off:off + comp]
        if comp < orig:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        out[tag] = raw
    return out


def _woff2_tags(data: bytes) -> set[str]:
    """Just the table tags in a .woff2.

    The table directory is uncompressed, but the table DATA is one brotli
    stream and this project has no brotli dependency - so we can see whether
    the file carries an `fvar` (making it variable, and therefore genuinely
    multi-weight) without being able to read its OS/2 weight. That is the only
    distinction that changes what CSS we emit, so it is enough.
    """
    if len(data) < 48:
        return set()
    num = int.from_bytes(data[12:14], "big")
    pos = 48
    tags: set[str] = set()
    for _ in range(num):
        if pos >= len(data):
            break
        flags = data[pos]
        pos += 1
        index = flags & 0x3F
        if index == 0x3F:
            if pos + 4 > len(data):
                break
            tags.add(data[pos:pos + 4].decode("latin1"))
            pos += 4
        else:
            tags.add(_WOFF2_KNOWN_TAGS[index] if index < len(_WOFF2_KNOWN_TAGS) else "")
        # origLength, then transformLength when a transform is applied. Both
        # are UIntBase128: 7 bits per byte, high bit continues.
        reads = 1
        if (flags >> 6) & 0x3:
            reads = 2
        elif index < len(_WOFF2_KNOWN_TAGS) and _WOFF2_KNOWN_TAGS[index] in ("glyf", "loca"):
            reads = 2
        for _ in range(reads):
            for _ in range(5):
                if pos >= len(data):
                    return tags
                byte = data[pos]
                pos += 1
                if not byte & 0x80:
                    break
    return tags


def describe_font(data: bytes, ext: str) -> dict:
    """What weights an uploaded font file carries.

    Returns ``{"weight": 400, "variable": False, "min_weight": 400,
    "max_weight": 400, "italic": False}``. A file we cannot parse is reported
    as a single static weight, which is the safe read: a static font file holds
    exactly one weight by definition, and only a variable font can hold more.
    """
    out = {"weight": 400, "variable": False, "min_weight": 400, "max_weight": 400, "italic": False}
    ext = (ext or "").lower()
    try:
        if ext == ".woff2":
            if "fvar" in _woff2_tags(data):
                # No brotli, so the axis range is unreadable. Claim the full
                # scale and let the browser clamp to the font's real axis.
                out.update(variable=True, min_weight=1, max_weight=1000)
            return out
        tables = _woff_tables(data) if ext == ".woff" else _sfnt_tables(data)
        os2 = tables.get("OS/2")
        if os2 and len(os2) >= 64:
            weight = int.from_bytes(os2[4:6], "big")
            if 1 <= weight <= 1000:
                out["weight"] = weight
                out["min_weight"] = weight
                out["max_weight"] = weight
            out["italic"] = bool(int.from_bytes(os2[62:64], "big") & 0x01)
        fvar = tables.get("fvar")
        if fvar and len(fvar) >= 16:
            axis_off = int.from_bytes(fvar[4:6], "big")
            axis_count = int.from_bytes(fvar[8:10], "big")
            axis_size = int.from_bytes(fvar[10:12], "big") or 20
            for i in range(axis_count):
                rec = axis_off + axis_size * i
                if rec + 12 > len(fvar):
                    break
                if fvar[rec:rec + 4] != b"wght":
                    continue
                lo = int.from_bytes(fvar[rec + 4:rec + 8], "big") >> 16
                hi = int.from_bytes(fvar[rec + 12:rec + 16], "big") >> 16 if rec + 16 <= len(fvar) else lo
                if 1 <= lo <= hi <= 1000 and lo != hi:
                    out.update(variable=True, min_weight=lo, max_weight=hi)
    except Exception:  # noqa: BLE001 - a malformed upload must not 500 the save
        return out
    return out


def public_font_fields(org) -> dict:
    """Resolve an org's font_config + the cache-busted URL/format for each
    uploaded role. Shared by the public club payload (clubs.py) and the admin
    settings response (club_admin.py) so the two can't drift."""
    cfg = org.font_config or {}
    out = {"font_config": cfg}
    for role in FONT_ROLES:
        entry = cfg.get(role) or {}
        data = getattr(org, f"font_{role}_data", None)
        if entry.get("source") == "upload" and data:
            v = entry.get("v") or "0"
            out[f"font_{role}_url"] = f"/api/images/organisations/{org.id}/font/{role}?v={v}"
            out[f"font_{role}_format"] = format_for_mime(getattr(org, f"font_{role}_mime", None))
        else:
            out[f"font_{role}_url"] = None
            out[f"font_{role}_format"] = None
    return out
