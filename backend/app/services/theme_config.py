"""Validation for a club's ``organisations.theme_config`` blob.

Shared by both sports' club-admin settings endpoints (cricket's
routers/club_admin.py and AFL's routers/afl/club_admin.py) rather than
copied, because these values are injected straight into a <style> tag by
frontend/src/lib/theme.js::buildThemeCss — a second copy of the allowlist
that drifted would mean one sport quietly accepting something the other
rejects.

The key set is deliberately sport-agnostic. AFL never sends chart_runs or
chart_wickets and cricket never sends anything AFL-only; an allowlist that
covers both is simpler than two lists to keep in step, and an unused key
costs nothing.
"""
import re

# Top-level colour keys, and the sub-keys allowed inside light/dark palettes.
THEME_COLOR_KEYS = {
    "accent", "accent2", "positive", "negative",
    "chart_runs", "chart_wickets", "chart_milestone",
    "cat_honour", "cat_role", "cat_award", "cat_milestone",
}
THEME_PALETTE_KEYS = {
    "bg", "surface", "surface2", "hairline", "hairline2",
    "text", "dim", "faint", "faintest",
}
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def valid_hex(value) -> bool:
    return isinstance(value, str) and bool(HEX_RE.match(value.strip()))


def sanitize_theme_config(raw: dict) -> dict:
    """Keep only recognised keys with valid hex colour values."""
    clean: dict = {}
    for key in THEME_COLOR_KEYS:
        val = raw.get(key)
        if valid_hex(val):
            clean[key] = val.strip()
    series = raw.get("chart_series")
    if isinstance(series, list):
        clean_series = [c.strip() for c in series if valid_hex(c)]
        if clean_series:
            clean["chart_series"] = clean_series[:12]
    for theme in ("light", "dark"):
        palette = raw.get(theme)
        if isinstance(palette, dict):
            clean_palette = {
                k: v.strip() for k, v in palette.items()
                if k in THEME_PALETTE_KEYS and valid_hex(v)
            }
            if clean_palette:
                clean[theme] = clean_palette
    return clean
