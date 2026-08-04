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


def mime_for_ext(ext: str) -> str:
    return _FONT_MIME_BY_EXT.get(ext.lower(), "font/woff2")


def format_for_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    return _FONT_FORMAT_BY_MIME.get(mime.lower(), "woff2")


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
