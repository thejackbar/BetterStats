"""Shared helper for recognising a club's own teams in upstream payloads.

Both the fixtures home/away derivation and the ladder "is this us?" highlight
need the same set of lowercased match keys for an organisation. Keeping the key
construction in one place stops the two copies from drifting.
"""
from __future__ import annotations


def club_match_keys(club) -> list[str]:
    """Lowercased/stripped keys for matching the club in opponent/ladder names.

    Returns the short name, the full name, and the first word of the name
    (e.g. ``"applecross"`` from ``"Applecross Cricket Club"``). Empty/missing
    values are dropped. Callers decide how to test (substring vs equality).
    """
    name = (club.name or "").strip()
    first_word = name.split()[0] if name else ""
    candidates = [club.short_name, club.name, first_word]
    return [k.lower().strip() for k in candidates if k and k.strip()]
