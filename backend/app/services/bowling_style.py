"""Bowling action/type → human label + pace/spin class.

Python mirror of the frontend's ``BOWLING_OPTS``
(``frontend/src/lib/playerAttributes.js``) so BetterIQ's natural-language
answers can tell a seamer from a spinner instead of guessing — without it the
Ask tools only saw wicket counts and would happily call a spinner a "third
seamer" or describe them as "sharp".
"""
from __future__ import annotations

# Same split BetterIQ's team/selection analysis already uses.
PACE_TYPES = frozenset({"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST"})
SPIN_TYPES = frozenset({"FINGER_SPIN", "WRIST_SPIN"})

# (bowling_action, bowling_type) → label, mirroring BOWLING_OPTS.
_LABELS = {
    ("RIGHT_ARM", "FAST"): "Right-arm fast",
    ("RIGHT_ARM", "FAST_MEDIUM"): "Right-arm fast-medium",
    ("RIGHT_ARM", "MEDIUM"): "Right-arm medium",
    ("RIGHT_ARM", "MEDIUM_FAST"): "Right-arm medium-fast",
    ("RIGHT_ARM", "FINGER_SPIN"): "Off spin",
    ("RIGHT_ARM", "WRIST_SPIN"): "Leg spin",
    ("LEFT_ARM", "FAST"): "Left-arm fast",
    ("LEFT_ARM", "FAST_MEDIUM"): "Left-arm fast-medium",
    ("LEFT_ARM", "MEDIUM"): "Left-arm medium",
    ("LEFT_ARM", "MEDIUM_FAST"): "Left-arm medium-fast",
    ("LEFT_ARM", "FINGER_SPIN"): "Left-arm orthodox",
    ("LEFT_ARM", "WRIST_SPIN"): "Left-arm wrist spin",
}

# Legacy / CA-sourced rows often carry only the type (no action) — fall back to
# a plain type label so the model still learns pace vs spin.
_TYPE_ONLY = {
    "FAST": "fast",
    "FAST_MEDIUM": "fast-medium",
    "MEDIUM": "medium",
    "MEDIUM_FAST": "medium-fast",
    "FINGER_SPIN": "finger spin",
    "WRIST_SPIN": "wrist spin",
}


def bowling_class(bowling_type: str | None) -> str | None:
    """'pace' | 'spin' | None — the coarse split that stops a spinner reading as a quick."""
    if bowling_type in PACE_TYPES:
        return "pace"
    if bowling_type in SPIN_TYPES:
        return "spin"
    return None


def bowling_label(action: str | None, bowling_type: str | None) -> str | None:
    """Human bowling style, e.g. 'Off spin' or 'Right-arm fast-medium'. None when unknown."""
    if not bowling_type:
        return None
    return _LABELS.get((action, bowling_type)) or _TYPE_ONLY.get(bowling_type)
