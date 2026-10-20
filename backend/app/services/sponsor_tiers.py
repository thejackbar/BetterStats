"""Sponsor tiers and where each sponsor shows (migration 318).

Four fixed tiers. A club can rename them but not add or remove them, so the
placement rules and the post defaults can rely on the keys. A tier sets the
default spots a sponsor shows in; a sponsor can then switch any one spot on or
off by hand. Only those hand-set choices are stored (``org_sponsors.placements``),
so where a sponsor shows is derived on read and moves with its tier.

Spots:
  dashboard  the major-sponsor slot on the club dashboard
  bar        the sticky strip of logos at the bottom of every club page
  footer     the full sponsor list at the very bottom of every club page
  posts      the sponsor block BetterPosts puts on a new post by default

Unknown tiers and unknown spots fail closed: a bad value is refused on write
and ignored on read, never widened into "shows everywhere".
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

TIERS: tuple[str, ...] = ("major", "gold", "silver", "supporter")
DEFAULT_TIER = "silver"

DEFAULT_LABELS: dict[str, str] = {
    "major": "Major Partners",
    "gold": "Gold Partners",
    "silver": "Silver Partners",
    "supporter": "Supporters",
}

PLACEMENTS: tuple[str, ...] = ("dashboard", "bar", "footer", "posts")

PLACEMENT_LABELS: dict[str, str] = {
    "dashboard": "Dashboard slot",
    "bar": "Bottom bar",
    "footer": "Sponsor list",
    "posts": "Social posts",
}

TIER_DEFAULT_PLACEMENTS: dict[str, tuple[str, ...]] = {
    "major": ("dashboard", "bar", "footer", "posts"),
    "gold": ("bar", "footer", "posts"),
    "silver": ("bar", "footer"),
    "supporter": ("footer",),
}

LABEL_MAX_CHARS = 40


def tier_rank(tier: Optional[str]) -> int:
    """0 for major up to 3 for supporter. An unknown tier sorts last."""
    try:
        return TIERS.index(tier or "")
    except ValueError:
        return len(TIERS)


def clean_tier(value: Any) -> str:
    """The tier key, or ValueError when it is not one of the four."""
    key = str(value or "").strip().lower()
    if key not in TIERS:
        raise ValueError(f"Unknown sponsor tier: {value!r}")
    return key


def resolve_labels(stored: Any) -> dict[str, str]:
    """Tier key -> display name. A blank or missing entry is the stock name."""
    out = dict(DEFAULT_LABELS)
    if isinstance(stored, dict):
        for key in TIERS:
            raw = stored.get(key)
            if isinstance(raw, str) and raw.strip():
                out[key] = raw.strip()[:LABEL_MAX_CHARS]
    return out


def clean_labels(raw: Any) -> Optional[dict[str, str]]:
    """What to store for a labels save: only entries that differ from the stock
    name, clipped. None (stored as NULL) when nothing differs."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for key in TIERS:
        val = raw.get(key)
        if isinstance(val, str):
            val = val.strip()[:LABEL_MAX_CHARS]
            if val and val != DEFAULT_LABELS[key]:
                out[key] = val
    return out or None


def clean_overrides(raw: Any) -> Optional[dict[str, bool]]:
    """Keep only known spots with a real boolean. None when nothing is left, so
    the column reads NULL and the sponsor follows its tier."""
    if not isinstance(raw, dict):
        return None
    out = {k: v for k, v in raw.items() if k in PLACEMENTS and isinstance(v, bool)}
    return out or None


def resolve_placements(tier: Optional[str], overrides: Any) -> list[str]:
    """The spots a sponsor shows in: the tier's defaults with any hand-set
    switch applied on top. Returned in PLACEMENTS order."""
    base = set(TIER_DEFAULT_PLACEMENTS.get(tier or "", ()))
    if isinstance(overrides, dict):
        for spot in PLACEMENTS:
            val = overrides.get(spot)
            if isinstance(val, bool):
                if val:
                    base.add(spot)
                else:
                    base.discard(spot)
    return [spot for spot in PLACEMENTS if spot in base]


def sort_sponsors(sponsors: Iterable[Any]) -> list[Any]:
    """Tier first (major to supporter), then the club's own drag order."""
    return sorted(
        sponsors,
        key=lambda s: (tier_rank(getattr(s, "tier", None)), getattr(s, "display_order", 0) or 0),
    )


def tier_meta() -> dict:
    """The static description the admin screen renders its controls from, so the
    defaults live in one place and the screen never keeps a second copy."""
    return {
        "tiers": [
            {
                "key": key,
                "default_label": DEFAULT_LABELS[key],
                "default_placements": list(TIER_DEFAULT_PLACEMENTS[key]),
            }
            for key in TIERS
        ],
        "placements": [{"key": key, "label": PLACEMENT_LABELS[key]} for key in PLACEMENTS],
    }
