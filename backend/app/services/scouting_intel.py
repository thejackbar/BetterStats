"""BetterIQ — manual scouting intel (batting & bowling "scouting card").

Cricket Australia's community data is scorecard-level — runs, wickets, dismissal
type — with NO ball-by-ball detail: no shot direction, no delivery length/line,
no record of which bowler *type* dismissed a batter. So the rich "how does he get
out / how does he bowl" read a selector keeps in their head is necessarily MANUAL
intel, the same posture as the existing scout-entered scoring-zones wagon wheel.

This module is the validation layer for that intel, shared by the opponent path
(``iq.upsert_opponent_tag`` → ``opponent_player_tags.batting_intel/bowling_intel``)
and our own players (``iq_trends`` → ``player_scouting_cards``). It only
normalises/clips the two JSONB blobs to a known shape; the read-side synthesis
(the "DNA" insights) is done on the frontend, where the held dismissal stats it
blends with are already loaded.

Shape (both stored as one JSONB blob each):

    batting_intel = {
        "vuln_bowling": [code, …],   # bowler types/kinds that trouble him (BOWLING_KINDS)
        "fav_bowling":  [code, …],   # bowler types/kinds he handles comfortably (BOWLING_KINDS)
        "zones":        [int×20],    # 4 lengths × 5 lines, intensity 0–3 (where he's vulnerable)
        "fav_shots":    [code, …],   # shots he favours (BAT_SHOTS)
        "risky_shots":  [code, …],   # shots he plays that are risky / can get him out (BAT_SHOTS)
        "strengths":    str,
        "weaknesses":   str,
        "plan":         str,         # one-line "how to get him out"
    }

    A legacy blob may still carry a single combined "shots" key (pre-split
    favoured/risky) — read sites (frontend scoutDna.js) fall back to it as
    risky_shots when both new keys are empty; a fresh save always writes the
    split shape, so "shots" naturally drops out of storage over time.
    bowling_intel = {
        "stock":        code|None,   # stock delivery kind (BOWLING_KINDS)
        "variations":   [code, …],   # BOWL_VARIATIONS
        "zones":        [int×20],    # where he attacks
        "danger":       [code, …],   # when he's most dangerous (BOWL_DANGER)
        "strengths":    str,
        "weaknesses":   str,
        "plan":         str,         # one-line "how to play him"
    }
"""
from __future__ import annotations

# ── Controlled vocab (code → human label). The frontend mirrors these labels. ──
# Bowler kinds — used for a batter's vulnerability and a bowler's stock type. Kept
# coarse-but-useful (a scout thinks "struggles vs spin / vs genuine pace"), with
# the common finer kinds available.
BOWLING_KINDS = {
    "PACE": "Genuine pace",
    "FAST_MEDIUM": "Fast-medium",
    "SWING": "Swing",
    "SEAM": "Seam",
    "OFF_SPIN": "Off spin",
    "LEG_SPIN": "Leg spin",
    "LEFT_ARM_ORTHODOX": "Left-arm orthodox",
    "LEFT_ARM_WRIST": "Left-arm wrist",
    "LEFT_ARM_PACE": "Left-arm pace",
}

BAT_SHOTS = {
    "PULL": "Pull",
    "HOOK": "Hook",
    "CUT": "Cut",
    "DRIVE": "Straight drive",
    "COVER_DRIVE": "Cover drive",
    "ON_DRIVE": "On drive",
    "SWEEP": "Sweep",
    "REVERSE_SWEEP": "Reverse sweep",
    "LOFT": "Loft / slog",
    "FLICK": "Flick",
    "GLANCE": "Glance",
    "DEFENCE": "Defence",
    "LEAVE": "Leave",
}

BOWL_VARIATIONS = {
    "YORKER": "Yorker",
    "BOUNCER": "Bouncer",
    "SLOWER_BALL": "Slower ball",
    "OFF_CUTTER": "Off-cutter",
    "LEG_CUTTER": "Leg-cutter",
    "INSWING": "Inswinger",
    "OUTSWING": "Outswinger",
    "DOOSRA": "Doosra",
    "GOOGLY": "Googly",
    "ARM_BALL": "Arm ball",
    "TOP_SPINNER": "Top-spinner",
    "CARROM": "Carrom ball",
    "KNUCKLE": "Knuckle ball",
}

BOWL_DANGER = {
    "NEW_BALL": "With the new ball",
    "FIRST_CHANGE": "First change",
    "MIDDLE": "Through the middle",
    "DEATH": "At the death",
    "VS_LHB": "vs left-handers",
    "VS_RHB": "vs right-handers",
    "VS_SET": "Once batters are set",
}

# The length × line grid that the zone heatmap draws. Rows = length, cols = line;
# row-major flat array of 20 cells, each an intensity 0–3.
ZONE_LENGTHS = ["Full toss", "Full", "Good", "Short"]
ZONE_LINES = ["Wide off", "Off stump", "Stumps", "Leg stump", "Down leg"]
ZONE_CELLS = len(ZONE_LENGTHS) * len(ZONE_LINES)  # 20
ZONE_MAX = 3

# Free-text caps — generous but bounded (these are scouting notes, not essays).
_TEXT_CAP = 600


def _codes(value, allowed: dict) -> list[str]:
    """Keep only known codes, de-duplicated, order preserved."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for v in value:
        code = str(v or "").strip().upper()
        if code in allowed and code not in out:
            out.append(code)
    return out


def _one_code(value, allowed: dict) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in allowed else None


def _zones(value) -> list[int]:
    """A flat 20-cell grid of intensities 0..ZONE_MAX. Anything off-shape clears
    to all-zero. Returns [] when nothing is marked (so an empty grid stores NULL)."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[int] = []
    for i in range(ZONE_CELLS):
        try:
            n = int(value[i]) if i < len(value) else 0
        except (TypeError, ValueError):
            n = 0
        out.append(max(0, min(ZONE_MAX, n)))
    return out if any(out) else []


def _text(value) -> str | None:
    s = (value or "")
    if not isinstance(s, str):
        return None
    s = s.strip()
    return s[:_TEXT_CAP] or None


def clean_batting_intel(d: dict | None) -> dict | None:
    """Normalise an incoming batting-intel blob; ``None`` when it's empty so the
    column stores NULL rather than an all-default shell."""
    if not isinstance(d, dict):
        return None
    out = {
        "vuln_bowling": _codes(d.get("vuln_bowling"), BOWLING_KINDS),
        "fav_bowling": _codes(d.get("fav_bowling"), BOWLING_KINDS),
        "zones": _zones(d.get("zones")),
        "fav_shots": _codes(d.get("fav_shots"), BAT_SHOTS),
        "risky_shots": _codes(d.get("risky_shots"), BAT_SHOTS),
        "strengths": _text(d.get("strengths")),
        "weaknesses": _text(d.get("weaknesses")),
        "plan": _text(d.get("plan")),
    }
    return out if _has_content(out) else None


def clean_bowling_intel(d: dict | None) -> dict | None:
    if not isinstance(d, dict):
        return None
    out = {
        "stock": _one_code(d.get("stock"), BOWLING_KINDS),
        "variations": _codes(d.get("variations"), BOWL_VARIATIONS),
        "zones": _zones(d.get("zones")),
        "danger": _codes(d.get("danger"), BOWL_DANGER),
        "strengths": _text(d.get("strengths")),
        "weaknesses": _text(d.get("weaknesses")),
        "plan": _text(d.get("plan")),
    }
    return out if _has_content(out) else None


def _has_content(d: dict) -> bool:
    """True when at least one field carries real intel."""
    for v in d.values():
        if isinstance(v, list):
            if v:
                return True
        elif v:
            return True
    return False
