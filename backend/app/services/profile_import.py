"""BetterImport (profiles) — parse an uploaded sheet of player contact + profile
data, auto-map its columns, and normalise each value to our canonical codes.

This is the *profile* sibling of ``import_ingest`` (which handles historical
stats). It deliberately reuses that module's sheet parser and, crucially, its
name matcher (``match_players``) — so a player-profile CSV matches names the same
way the stats importer, award importer and KlubPro migration do: an exact name
is a straight match, a close one is offered as a suggestion, and a missing one
can be created new or pointed at an existing player.

Everything here is DB-free (plain data in, plain data out) so the wizard's
preview can call it repeatedly and it stays unit-testable. The value normalisers
mirror ``frontend/src/lib/playerAttributes.js`` (the editor's source of truth),
the same posture ``services/klubpro_migration.py`` takes for its imports.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

from app.services.import_ingest import _norm  # shared header normaliser


# ── importable profile fields ────────────────────────────────────────────────
# player_name is the only key; every other field is an optional attribute. An
# empty cell never updates a player (leave-as-is), so a club can upload just
# emails and phones, or fill in as many of the others as they have.
NAME_FIELD = "player_name"
VALUE_FIELDS = (
    "email", "phone", "squad", "player_role", "batting_hand", "bowling", "gender",
)
ALL_FIELDS = (NAME_FIELD,) + VALUE_FIELDS

# The canonical player columns each value field writes to (squad is resolved to
# squad_team_id in the router; bowling expands to action + type).
PLAYER_FIELDS = ("email", "phone", "gender", "player_role", "batting_hand",
                 "bowling_action", "bowling_type")

FIELD_LABELS = {
    "player_name": "Player name",
    "email": "Email",
    "phone": "Phone / mobile",
    "squad": "Squad (selection pool)",
    "player_role": "Role",
    "batting_hand": "Batting hand",
    "bowling": "Bowling",
    "gender": "Gender",
}

# Lower-cased, punctuation-normalised header synonyms for auto-mapping. The
# wizard always lets the user confirm/override, so a near miss is cheap.
SYNONYMS = {
    "player_name": ["player", "name", "player name", "full name", "member", "members", "first last", "surname"],
    "email": ["email", "email address", "e mail", "mail", "contact email", "emails"],
    "phone": ["phone", "mobile", "mobile number", "phone number", "contact number", "contact",
              "cell", "cell phone", "ph", "telephone", "tel", "mob", "mobile phone"],
    "squad": ["squad", "selection pool", "pool", "team", "side", "squad team", "grade", "selection squad"],
    "player_role": ["role", "player role", "position", "player type", "type", "playing role"],
    "batting_hand": ["batting", "batting hand", "bat", "bats", "bat hand", "batting style", "handedness", "bat arm"],
    "bowling": ["bowling", "bowling type", "bowls", "bowl", "bowling style", "bowler type",
                "bowling action", "bowling arm", "bowler"],
    "gender": ["gender", "sex", "m f"],
}


# ── column auto-mapping ──────────────────────────────────────────────────────

def suggest_column_mapping(headers: list) -> dict:
    """{field: {"column": header, "confidence": float}} — best column per field.

    Threshold sits a touch higher than the stats importer's: these field names
    are short and distinctive (email / phone / gender), so a loose match would
    do more harm than a missed one the user can map by hand.
    """
    per_header = {}
    for h in headers:
        nh = _norm(h)
        if not nh:
            continue
        best_field, best_score = None, 0.0
        for field, syns in SYNONYMS.items():
            if nh in syns:
                s = 1.0
            else:
                s = max((SequenceMatcher(None, nh, syn).ratio() for syn in syns), default=0.0)
            if s > best_score:
                best_field, best_score = field, s
        if best_field and best_score >= 0.72:
            per_header[h] = (best_field, best_score)
    mapping: dict = {}
    for h, (field, score) in per_header.items():
        if field not in mapping or score > mapping[field]["confidence"]:
            mapping[field] = {"column": h, "confidence": round(score, 2)}
    return mapping


# ── value normalisers (mirror frontend/src/lib/playerAttributes.js) ──────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def norm_email(v) -> tuple[Optional[str], Optional[str]]:
    """(clean_email | None, error | None). A blank cell is (None, None)."""
    s = str(v or "").strip()
    if not s:
        return (None, None)
    if not _EMAIL_RE.match(s):
        return (None, "invalid")
    return (s, None)


def norm_phone(v) -> Optional[str]:
    """Trim + collapse whitespace; keep the number roughly as typed (digits,
    +, spaces, brackets, dashes). Anything with no digit at all is dropped."""
    s = re.sub(r"\s+", " ", str(v or "").strip())
    if not s or not any(c.isdigit() for c in s):
        return None
    return s


def norm_gender(v) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("m", "male", "man", "boy"):
        return "male"
    if s in ("f", "female", "woman", "girl"):
        return "female"
    return None


def norm_batting_hand(v) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("right", "right handed", "right-handed", "right hand", "rhb", "rh", "r"):
        return "RIGHT"
    if s in ("left", "left handed", "left-handed", "left hand", "lhb", "lh", "l"):
        return "LEFT"
    return None


# label → (bowling_action, bowling_type). Keys lower-cased for tolerant matching;
# mirrors BOWLING_OPTS in playerAttributes.js plus the medium-fast/chinaman rows
# the KlubPro normaliser already carries.
_BOWLING_LABELS = {
    "right-arm fast": ("RIGHT_ARM", "FAST"),
    "right-arm fast-medium": ("RIGHT_ARM", "FAST_MEDIUM"),
    "right-arm medium-fast": ("RIGHT_ARM", "MEDIUM_FAST"),
    "right-arm medium": ("RIGHT_ARM", "MEDIUM"),
    "off spin": ("RIGHT_ARM", "FINGER_SPIN"),
    "right-arm off spin": ("RIGHT_ARM", "FINGER_SPIN"),
    "leg spin": ("RIGHT_ARM", "WRIST_SPIN"),
    "right-arm leg spin": ("RIGHT_ARM", "WRIST_SPIN"),
    "left-arm fast": ("LEFT_ARM", "FAST"),
    "left-arm fast-medium": ("LEFT_ARM", "FAST_MEDIUM"),
    "left-arm medium-fast": ("LEFT_ARM", "MEDIUM_FAST"),
    "left-arm medium": ("LEFT_ARM", "MEDIUM"),
    "left-arm orthodox": ("LEFT_ARM", "FINGER_SPIN"),
    "left-arm wrist spin": ("LEFT_ARM", "WRIST_SPIN"),
    "left-arm chinaman": ("LEFT_ARM", "WRIST_SPIN"),
}
# Short forms / common spellings → a canonical label key above.
_BOWLING_ALIASES = {
    "offspin": "off spin", "off-spin": "off spin", "offie": "off spin",
    "legspin": "leg spin", "leg-spin": "leg spin", "leggie": "leg spin",
    "right arm fast": "right-arm fast", "right arm fast medium": "right-arm fast-medium",
    "right arm medium": "right-arm medium", "right arm medium fast": "right-arm medium-fast",
    "left arm fast": "left-arm fast", "left arm medium": "left-arm medium",
    "left arm orthodox": "left-arm orthodox", "slow left arm": "left-arm orthodox",
    "sla": "left-arm orthodox", "slow left-arm orthodox": "left-arm orthodox",
    "rf": "right-arm fast", "rfm": "right-arm fast-medium", "rm": "right-arm medium",
    "lf": "left-arm fast", "lfm": "left-arm fast-medium", "lm": "left-arm medium",
}
_BOWLING_TYPES = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST", "FINGER_SPIN", "WRIST_SPIN"}


def norm_bowling(v) -> tuple[Optional[str], Optional[str]]:
    """A bowling label/shorthand → (bowling_action, bowling_type). Either part
    may be None when the cell only pins one of them (e.g. a bare 'FAST')."""
    if v is None:
        return (None, None)
    s = str(v).strip().lower()
    if not s:
        return (None, None)
    if s in _BOWLING_ALIASES:
        s = _BOWLING_ALIASES[s]
    if s in _BOWLING_LABELS:
        return _BOWLING_LABELS[s]
    up = str(v).strip().upper().replace("-", "_").replace(" ", "_")
    if up in _BOWLING_TYPES:
        return (None, up)
    return (None, None)


_ROLE_LABELS = {
    "batter": "Batter", "batsman": "Batter", "bat": "Batter", "batting": "Batter",
    "bowler": "Bowler", "bowl": "Bowler", "bowling": "Bowler",
    "all rounder": "All Rounder", "all-rounder": "All Rounder", "allrounder": "All Rounder",
    "all round": "All Rounder", "ar": "All Rounder",
    "wicketkeeper": "Wicketkeeper", "wicket keeper": "Wicketkeeper", "keeper": "Wicketkeeper",
    "wk": "Wicketkeeper", "gk": "Wicketkeeper",
    "wicketkeeper-batter": "Wicketkeeper-Batter", "wicketkeeper batter": "Wicketkeeper-Batter",
    "wicket keeper batter": "Wicketkeeper-Batter", "wk-batter": "Wicketkeeper-Batter",
    "wk batter": "Wicketkeeper-Batter", "keeper batter": "Wicketkeeper-Batter",
}


def norm_role(v) -> Optional[str]:
    """A role label → one of the canonical ROLE_OPTS, or None when unrecognised
    (unknown free text is dropped rather than stored, so the editor dropdown
    always resolves)."""
    if v is None or str(v).strip() == "":
        return None
    return _ROLE_LABELS.get(str(v).strip().lower())


# ── per-row profile patch ────────────────────────────────────────────────────

def row_profile(values: dict) -> tuple[dict, list]:
    """Map one row's {field: raw_cell} (mapped value fields only) to a canonical
    player patch. Returns (patch, notes).

    Only fields with a usable value land in ``patch`` — a blank or unrecognised
    cell is omitted so it never clobbers existing data. ``notes`` carries any
    "couldn't read this" flag for the review screen (invalid email, unrecognised
    gender/role/bowling). ``squad`` is handled by the router (needs the team
    list) and is not touched here.
    """
    patch: dict = {}
    notes: list = []

    def raw(f):
        x = values.get(f)
        return str(x).strip() if (x is not None and str(x).strip() != "") else None

    if raw("email") is not None:
        val, err = norm_email(values["email"])
        if val:
            patch["email"] = val
        elif err:
            notes.append(f"email “{raw('email')}” looks invalid — left unchanged")

    if raw("phone") is not None:
        ph = norm_phone(values["phone"])
        if ph:
            patch["phone"] = ph

    if raw("gender") is not None:
        g = norm_gender(values["gender"])
        if g:
            patch["gender"] = g
        else:
            notes.append(f"gender “{raw('gender')}” not recognised — left unchanged")

    if raw("player_role") is not None:
        role = norm_role(values["player_role"])
        if role:
            patch["player_role"] = role
        else:
            notes.append(f"role “{raw('player_role')}” not recognised — left unchanged")

    if raw("batting_hand") is not None:
        bh = norm_batting_hand(values["batting_hand"])
        if bh:
            patch["batting_hand"] = bh
        else:
            notes.append(f"batting hand “{raw('batting_hand')}” not recognised — left unchanged")

    if raw("bowling") is not None:
        action, btype = norm_bowling(values["bowling"])
        # Only a full arm + type label is applied — a bare "Fast" with no arm
        # can't be shown in the editor's dropdown, so it's flagged, not stored.
        if action and btype:
            patch["bowling_action"] = action
            patch["bowling_type"] = btype
        else:
            notes.append(f"bowling “{raw('bowling')}” not recognised — left unchanged")

    return patch, notes


# ── squad (selection-pool team) matching ─────────────────────────────────────

def _norm_squad(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(s or "").lower())).strip()


def match_squads(labels: list, teams: list, threshold: float = 0.82) -> dict:
    """labels → match info. ``teams`` = list of (id, name).

    status: 'exact' (auto-assign), 'fuzzy' (a close team — surfaced to confirm),
    'none' (no team like this — pick, create, or skip). Mirrors the player
    matcher's shape so the wizard renders both with the same picker.
    """
    name_map: dict = {}
    for tid, nm in teams:
        name_map.setdefault(_norm_squad(nm), []).append((tid, nm))

    out: dict = {}
    for label in labels:
        if label in out:
            continue
        ln = _norm_squad(label)
        if not ln:
            continue
        exact = name_map.get(ln, [])
        if exact:
            tid, nm = exact[0]
            out[label] = {"team_id": str(tid), "matched_name": nm, "status": "exact",
                          "auto_status": "exact", "confidence": 1.0, "candidates": []}
            continue
        scored = sorted(
            ((SequenceMatcher(None, ln, _norm_squad(nm)).ratio(), tid, nm) for tid, nm in teams),
            key=lambda t: t[0], reverse=True,
        )[:5]
        cands = [{"team_id": str(tid), "name": nm, "confidence": round(sc, 2)} for sc, tid, nm in scored if sc >= 0.5]
        top = scored[0][0] if scored else 0.0
        st = "fuzzy" if top >= threshold else "none"
        out[label] = {"team_id": None, "status": st, "auto_status": st,
                      "confidence": round(top, 2), "candidates": cands}
    return out
