"""Which sponsor a player card shows (migration 367).

Two surfaces draw a sponsor on a card:

  share_card     the public share page, /players/{id}/share
  player_cards   the collectable Player Cards (the card book, packs, swaps)

A club picks one sponsor for each in the Sponsors screen. Only the pick is
stored (``organisations.card_sponsors``). A surface with no pick, or whose
sponsor was deleted or lost its logo, falls back to the club's top sponsor that
has a logo, which is what every card showed before a club could choose. The
fallback itself lives in the frontend (``cardSponsor``), so this module only
decides what is a valid pick.

A sponsor with no logo cannot be drawn on a card, so it cannot be picked.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

SURFACES: tuple[str, ...] = ("share_card", "player_cards")

SURFACE_LABELS: dict[str, str] = {
    "share_card": "Player share card",
    "player_cards": "Player Cards",
}


def _usable_ids(sponsors: Iterable[Any]) -> set[str]:
    return {str(s.id) for s in sponsors if getattr(s, "logo_url", None)}


def clean(raw: Any, sponsors: Iterable[Any]) -> Optional[dict[str, str]]:
    """What to store for a save. Keeps known surfaces whose sponsor is this
    club's and has a logo; anything else is dropped. None when nothing is left,
    so the column reads NULL. ValueError for a surface that does not exist, so
    a typo is a 422."""
    if not isinstance(raw, dict):
        return None
    usable = _usable_ids(sponsors)
    out: dict[str, str] = {}
    for surface, sponsor_id in raw.items():
        if surface not in SURFACES:
            raise ValueError(f"Unknown card surface: {surface}")
        if sponsor_id is not None and str(sponsor_id) in usable:
            out[surface] = str(sponsor_id)
    return out or None


def view(stored: Any, sponsors: Iterable[Any]) -> dict[str, Optional[str]]:
    """{"share_card": id or None, "player_cards": id or None}, with a pick whose
    sponsor is gone or has no logo shown as not picked."""
    usable = _usable_ids(sponsors)
    stored = stored if isinstance(stored, dict) else {}
    out: dict[str, Optional[str]] = {}
    for surface in SURFACES:
        val = stored.get(surface)
        out[surface] = str(val) if val is not None and str(val) in usable else None
    return out
