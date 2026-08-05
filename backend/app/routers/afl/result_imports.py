"""Import Results — historical match results from a spreadsheet.

The sibling of Import Stats (routers/afl/imports.py): that one brings in
season TOTALS per player, this one brings in the MATCHES themselves — one row
per game, with both sides' goals/behinds/score, the venue, the round and what
the club recorded as the outcome. Clubs keep exactly this sheet: a
decades-long results register that predates PlayHQ entirely (the reference
sheet behind this feature runs 1947–2023).

Flow mirrors the Upload Scorecard reader in Core (cricket): read what the
sheet says, faithfully; cross-check it against itself; flag where it doesn't
add up; let the admin fix or keep before anything is written. Two warning
kinds, same split the scorecard reader uses:
  * ``sheet_error`` — the sheet's OWN figures disagree (goals x6 + behinds
    doesn't equal the total; the recorded outcome contradicts the scores).
    Usually a decades-old typo: fix it or import it as written.
  * ``check``      — something worth a look but not contradictory (a result
    we worked out from the scores because the outcome column was blank; a
    0-0 game).
A row that genuinely can't be imported (no date, no season) is ``blocked``,
never silently dropped.

Unlike Import Stats, imported results are REAL games — they land in the
shared ``games`` table with an ``afl_game_details`` row alongside, so they
show up on the public results list, the dashboard W/L/D and the records the
same way a synced game does. Three guards make that safe:
  * a game the PlayHQ sync already holds is never touched (matched on date +
    opponent + team, reported as ``synced`` and skipped — sync always wins);
  * every imported row carries ``source='import'`` and its batch id, so the
    whole upload is undoable in one click;
  * the game id is derived from the row's own identity
    (uuid5(org, season|grade|date|opponent|round)), so re-uploading a
    corrected sheet UPDATES the same rows instead of duplicating them.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.afl import AflGameDetails
from app.models.db import Game, Grade, ImportBatch, Organisation, Season, User, get_db
from app.routers.auth import get_current_club
from app.services import import_ingest as ingest
from app.services.afl.grade_labels import suggest_category
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/result-imports", tags=["afl-result-imports"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# How many rows come back with per-row detail for the review table (the
# counts and the import itself always cover every row — see _resolve).
ROW_DETAIL_LIMIT = 5000

KEY_FIELDS = ("season_label", "grade_label", "played_on", "opponent")
CONTEXT_FIELDS = ("round_label", "series_label", "home_away", "venue", "start_time", "external_ref")
SCORE_FIELDS = ("our_goals", "our_behinds", "our_score",
                "opp_goals", "opp_behinds", "opp_score", "margin")
RESULT_FIELDS = ("outcome",)
ALL_FIELDS = KEY_FIELDS + CONTEXT_FIELDS + SCORE_FIELDS + RESULT_FIELDS

# Header synonyms. The "opp" variants deliberately spell the prefix out — a
# club sheet almost always labels its own columns with the club's own name
# ("HamGoal", "HamTotalScore") and the opposition's with an opp/opposition
# prefix, so the prefixed synonyms are what tells the two halves apart.
SYNONYMS = {
    "season_label": ["season", "year", "yr", "season year"],
    "grade_label": ["club team", "team", "grade", "division", "age group", "level", "squad", "comp"],
    "played_on": ["date", "match date", "game date", "played", "played on", "date played"],
    "opponent": ["opposition club", "opposition", "opponent", "against", "versus", "vs", "opp club"],
    "round_label": ["rnd", "round", "rd", "round number"],
    "series_label": ["series", "fixture type", "competition type", "match type", "stage"],
    "home_away": ["home away", "home or away", "h a", "venue type", "home/away", "ground type"],
    "venue": ["venue", "ground", "location", "oval", "field"],
    "start_time": ["game time", "gametime", "time", "start time", "bounce time"],
    "external_ref": ["game id", "gameid", "match id", "id", "game ref", "game no", "game number"],
    "our_goals": ["goals", "goals for", "our goals", "club goals", "team goals"],
    "our_behinds": ["behinds", "points", "behinds for", "our behinds", "club behinds", "our points"],
    "our_score": ["total score", "score", "our score", "club score", "score for", "total", "points scored"],
    "opp_goals": ["opp goals", "opposition goals", "goals against", "their goals"],
    "opp_behinds": ["opp points", "opp behinds", "opposition behinds", "opposition points",
                    "behinds against", "points against", "their behinds"],
    "opp_score": ["opp total score", "opp score", "opposition score", "score against", "their score"],
    "margin": ["margin", "diff", "difference", "points margin"],
    "outcome": ["result", "outcome", "win loss", "w l", "win/loss", "verdict"],
}

# Values a column has to be mostly made of before it can be sniffed as that
# field by CONTENT — the fallback for a header that says nothing useful
# ("Column1", "Unnamed: 17"), which is exactly how an outcome column tends to
# arrive out of a real club's spreadsheet.
VALUE_HINTS = {
    "outcome": {"won", "win", "w", "wins", "loss", "lost", "l", "lose", "defeat", "draw", "drawn",
                "drawn game", "tie", "tied", "bye", "cancel", "cancelled", "canceled", "washout",
                "abandoned", "forfeit", "forfiet", "won on forfeit", "won on forfiet",
                "loss on forfeit", "loss on forfiet", "missing score", "no score", "no game"},
    "home_away": {"home", "away", "h", "a", "bye", "neutral", "home game", "away game"},
    "series_label": {"home & away", "home and away", "finals", "final", "regular", "home&away",
                     "practice", "pre season", "pre-season"},
}


# ── column auto-mapping ──────────────────────────────────────────────────────

def _norm(h) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(h).lower())).strip()


def _field_score(nh: str, syns: list) -> float:
    if nh in syns:
        return 1.0
    return max((SequenceMatcher(None, nh, syn).ratio() for syn in syns), default=0.0)


def _suggest_column_mapping(headers: list, rows: list) -> dict:
    """Best (header -> field) assignment, then a content sniff for the leftovers.

    Assignment is GLOBAL rather than per-field: "HamPoints" and "OppPoints"
    both score 0.8 against the plain synonym "points", so picking each field's
    own best header independently is a coin flip between them. Taking the
    strongest pair in the whole matrix first (OppPoints -> opp_behinds at
    0.95, since it also matches the prefixed synonym) leaves HamPoints with
    only our_behinds to land on, which is the right answer for both.
    """
    normed = {h: _norm(h) for h in headers if _norm(h)}
    syns = {f: [_norm(x) for x in s] for f, s in SYNONYMS.items()}

    pairs = []
    for h, nh in normed.items():
        for field, s in syns.items():
            score = _field_score(nh, s)
            if score >= 0.6:
                pairs.append((score, h, field))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))

    mapping: dict = {}
    used_headers: set = set()
    for score, h, field in pairs:
        if field in mapping or h in used_headers:
            continue
        mapping[field] = {"column": h, "confidence": round(score, 2)}
        used_headers.add(h)

    # Content sniff: a header that matched nothing, whose VALUES are mostly a
    # known vocabulary, is that field.
    sample = rows[:400]
    for field, vocab in VALUE_HINTS.items():
        if field in mapping:
            continue
        best_h, best_hit = None, 0.0
        for h in normed:
            if h in used_headers:
                continue
            vals = [_norm(r.get(h)) for r in sample]
            vals = [v for v in vals if v]
            if len(vals) < 5:
                continue
            hit = sum(1 for v in vals if v in vocab) / len(vals)
            if hit > best_hit:
                best_h, best_hit = h, hit
        if best_h and best_hit >= 0.6:
            mapping[field] = {"column": best_h, "confidence": round(best_hit, 2), "matched_on": "values"}
            used_headers.add(best_h)
    return mapping


def _col(mapping: dict, field: str) -> Optional[str]:
    v = mapping.get(field)
    if isinstance(v, dict):
        return v.get("column")
    return v or None


def _cell(row: dict, mapping: dict, field: str) -> str:
    c = _col(mapping, field)
    return str(row.get(c, "") or "").strip() if c else ""


# ── value parsing ────────────────────────────────────────────────────────────

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y",
    "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y", "%d-%b-%y",
)


def parse_date(raw: str) -> Optional[date]:
    """A spreadsheet date, however it survived the trip through the parser.

    parse_upload stringifies every cell, so a real Excel date arrives as
    "1947-04-19 00:00:00" while a text column can hold anything a club typed.
    Day-first is preferred for the ambiguous slash forms — this is Australian
    club football, where 4/5/1968 is the 4th of May.
    """
    s = (raw or "").strip()
    if not s:
        return None
    s = re.sub(r"\s+", " ", s)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # An Excel serial that came through as a bare number (1900 date system).
    if re.fullmatch(r"\d{4,5}(\.\d+)?", s):
        try:
            serial = int(float(s))
            if 1 <= serial <= 80000:
                from datetime import timedelta
                return date(1899, 12, 30) + timedelta(days=serial)
        except (ValueError, OverflowError):
            pass
    return None


def parse_time(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?$", s, re.I)
    if not m:
        return None
    hh, mm, ss, ap = int(m.group(1)), m.group(2), m.group(3) or "00", (m.group(4) or "").lower()
    if ap == "pm" and hh < 12:
        hh += 12
    if ap == "am" and hh == 12:
        hh = 0
    if hh > 23:
        return None
    return f"{hh:02d}:{mm}:{ss}"


def _int(raw: str) -> Optional[int]:
    v = ingest.to_int(raw)
    return v


# ── outcome classification ───────────────────────────────────────────────────

# category -> what it means for the import.
#   result   — a played game with a real outcome
#   forfeit  — a result awarded without a game being played
#   bye      — no opponent, no game
#   cancelled/no_score — nothing to record (the sheet's own "Cancel" /
#                        "Missing Score"), always skipped
CATEGORY_LABELS = {
    "result": "Result",
    "forfeit": "Forfeit",
    "bye": "Bye",
    "cancelled": "Cancelled",
    "no_score": "No score recorded",
    "unknown": "Unrecognised",
}


def classify_outcome(raw: str) -> tuple:
    """(category, result letter or None) from whatever the club wrote.

    Spelling is taken as it comes — the reference sheet writes "Forfiet"
    throughout, and a register that's been hand-kept since 1947 will have
    others. Matching is on the substring, so "Won on Forfiet", "won by
    forfeit" and "W - forfeit" all land in the same place.
    """
    s = _norm(raw)
    if not s:
        return ("unknown", None)
    forfeit = "forfeit" in s or "forfiet" in s
    if "bye" in s:
        return ("bye", None)
    if any(w in s for w in ("cancel", "washout", "wash out", "abandon", "no game", "not played", "postpon")):
        return ("cancelled", None)
    if any(w in s for w in ("missing", "no score", "unknown score", "no result recorded")):
        return ("no_score", None)
    if any(w in s for w in ("draw", "drawn", "tie", "tied")):
        return ("forfeit" if forfeit else "result", "D")
    if re.search(r"\b(won|win|wins|w)\b", s):
        return ("forfeit" if forfeit else "result", "W")
    if re.search(r"\b(loss|lost|lose|l|defeat|defeated)\b", s):
        return ("forfeit" if forfeit else "result", "L")
    if forfeit:
        return ("forfeit", None)
    return ("unknown", None)


def _result_from_scores(ours: Optional[int], theirs: Optional[int]) -> Optional[str]:
    if ours is None or theirs is None:
        return None
    return "W" if ours > theirs else "L" if ours < theirs else "D"


def _side_from_home_away(raw: str) -> tuple:
    """(our_side, is_bye). A blank reads as neutral, not as an error.

    Finals are routinely played at a third club's ground and the sheet just
    leaves home/away empty for them — 103 rows in the reference sheet. Those
    are real results and must import; they're stored with our club as the
    nominal home side, which is arbitrary but affects nothing except which
    column the name is printed in.
    """
    s = _norm(raw)
    if not s:
        return (None, False)
    if "bye" in s:
        return (None, True)
    if s.startswith("h"):
        return ("HOME", False)
    if s.startswith("a"):
        return ("AWAY", False)
    if s.startswith("n"):          # neutral
        return (None, False)
    return (None, False)


_FINAL_RE = re.compile(r"\b(final|finals|gf|pf|sf|ef|qf|semi|prelim|elimination|qualifying|grand)\b")


def _is_final(series_raw: str, round_raw: str) -> bool:
    return bool(_FINAL_RE.search(_norm(series_raw)) or _FINAL_RE.search(_norm(round_raw)))


def _round_name(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    return f"Round {s}" if re.fullmatch(r"\d+", s) else s


def _opp_key(name: str) -> str:
    """Opponent name reduced to something two spellings of the same club
    share — used only to spot a game the sync already holds."""
    s = _norm(name)
    s = re.sub(r"\b(football|fc|afc|club|the|inc|reserves|seniors|colts)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ── row building ─────────────────────────────────────────────────────────────

def _build_row(idx: int, raw: dict, mapping: dict) -> dict:
    get = lambda f: _cell(raw, mapping, f)  # noqa: E731

    played_on = parse_date(get("played_on"))
    our_goals, our_behinds = _int(get("our_goals")), _int(get("our_behinds"))
    our_score = _int(get("our_score"))
    opp_goals, opp_behinds = _int(get("opp_goals")), _int(get("opp_behinds"))
    opp_score = _int(get("opp_score"))
    # A sheet that records goals and behinds but no total (or the other way
    # round) is normal — fill whichever half is missing rather than treating
    # the row as incomplete. 6 points a goal, 1 a behind.
    if our_score is None and our_goals is not None and our_behinds is not None:
        our_score = our_goals * 6 + our_behinds
    if opp_score is None and opp_goals is not None and opp_behinds is not None:
        opp_score = opp_goals * 6 + opp_behinds

    outcome_raw = get("outcome")
    category, result = classify_outcome(outcome_raw)
    our_side, bye_flag = _side_from_home_away(get("home_away"))
    if bye_flag and category in ("unknown", "result"):
        category = "bye"

    warnings: list = []
    result_inferred = False
    if category in ("result", "forfeit") and result is None:
        # The one place we go beyond transcribing: a blank or unreadable
        # outcome against two real scores has exactly one honest reading.
        result = _result_from_scores(our_score, opp_score)
        if result:
            result_inferred = True
            warnings.append({"kind": "check", "text": (
                f"No result recorded — worked out from the scores as a "
                f"{'win' if result == 'W' else 'loss' if result == 'L' else 'draw'}.")})
        if category == "unknown" and result:
            category = "result"

    # Cross-checks against the sheet's own figures.
    for who, g, b, sc in (("Our", our_goals, our_behinds, our_score),
                          ("Opposition", opp_goals, opp_behinds, opp_score)):
        if g is not None and b is not None and sc is not None and g * 6 + b != sc:
            warnings.append({"kind": "sheet_error", "text": (
                f"{who} score doesn't add up: {g}.{b} is {g * 6 + b}, the sheet says {sc}.")})
    if category == "result" and result and not result_inferred:
        from_scores = _result_from_scores(our_score, opp_score)
        if from_scores and from_scores != result and (our_score or opp_score):
            warnings.append({"kind": "sheet_error", "text": (
                f"Recorded as a {'win' if result == 'W' else 'loss' if result == 'L' else 'draw'} "
                f"but the scores read {our_score}-{opp_score}.")})
    margin = _int(get("margin"))
    if margin is not None and our_score is not None and opp_score is not None \
            and margin != our_score - opp_score:
        warnings.append({"kind": "sheet_error", "text": (
            f"Margin says {margin}, the scores give {our_score - opp_score}.")})
    if category == "result" and not our_score and not opp_score:
        warnings.append({"kind": "check", "text": "No score recorded — imports as 0-0."})

    return {
        "index": idx,
        "external_ref": get("external_ref") or None,
        "season_label": get("season_label") or None,
        "grade_label": get("grade_label") or None,
        "played_on": played_on.isoformat() if played_on else None,
        "start_time": parse_time(get("start_time")),
        "round_label": get("round_label") or None,
        "round_name": _round_name(get("round_label")),
        "is_final": _is_final(get("series_label"), get("round_label")),
        "series_label": get("series_label") or None,
        "our_side": our_side,
        "venue": get("venue") or None,
        "opponent": get("opponent") or None,
        "our_goals": our_goals, "our_behinds": our_behinds, "our_score": our_score,
        "opp_goals": opp_goals, "opp_behinds": opp_behinds, "opp_score": opp_score,
        "outcome_raw": outcome_raw or None,
        "category": category,
        "result": result,
        "result_inferred": result_inferred,
        "warnings": warnings,
    }


def _identity_key(r: dict) -> str:
    """What makes this row a distinct game. Round is in the key because a
    club that plays the same opponent twice in a season on the same recorded
    date (a re-scheduled fixture carried at its original date) is otherwise
    indistinguishable."""
    return "|".join([
        (r.get("season_label") or "").strip().lower(),
        (r.get("grade_label") or "").strip().lower(),
        r.get("played_on") or "",
        _opp_key(r.get("opponent") or ""),
        (r.get("round_label") or "").strip().lower(),
    ])


# ── db lookups ───────────────────────────────────────────────────────────────

async def _org_seasons(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(
        select(Season).where(Season.organisation_id == org_id)
        .order_by(Season.year.desc().nulls_last(), Season.name.desc())
    )).scalars().all()
    return [(str(s.id), s.name or "", s.year) for s in rows]


async def _org_grade_names(db: AsyncSession, org_id) -> list:
    rows = await db.execute(text("""
        SELECT DISTINCT gr.name FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org ORDER BY gr.name
    """), {"org": str(org_id)})
    return [r[0] for r in rows.all()]


async def _existing_games(db: AsyncSession, org_id) -> dict:
    """(played_at, opponent key) -> [{grade, source}] for games we already hold.

    One query for the whole batch rather than a lookup per row.

    The GRADE has to be part of the comparison, not just the date and the
    opponent: a club's Seniors, Reserves and Under 17s all play the same
    opposition on the same afternoon, so a date+opponent match alone would
    read the whole day's card as one already-synced game and silently drop
    the other teams' results. Kept as a list per (date, opponent) so a game
    under a DIFFERENT grade can still be surfaced as something to look at
    rather than either skipped or ignored.
    """
    rows = await db.execute(text("""
        SELECT g.played_at, g.opp_club_name, g.home_team, g.away_team, gr.name AS grade_name,
               COALESCE(d.source, 'playhq') AS source
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org AND g.played_at IS NOT NULL
    """), {"org": str(org_id)})
    out: dict = {}
    for r in rows:
        entry = {"grade": _norm(r.grade_name), "grade_name": r.grade_name,
                 "source": "synced" if r.source != "import" else "import"}
        for nm in {_opp_key(x or "") for x in (r.opp_club_name, r.home_team, r.away_team)}:
            if nm:
                out.setdefault((r.played_at.isoformat(), nm), []).append(entry)
    return out


# ── request models ───────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    rows: list[dict] = []
    mapping: dict = {}
    season_overrides: dict = {}
    grade_overrides: dict = {}
    include_byes: bool = False
    include_forfeits: bool = True


class CommitRequest(ResolveRequest):
    filename: Optional[str] = None


def _apply_season_overrides(matches: dict, overrides: dict) -> None:
    for label, choice in (overrides or {}).items():
        if label not in matches:
            matches[label] = {"candidates": []}
        if choice == "__unassigned__":
            matches[label].update(season_id=None, is_prior=True, status="unassigned")
        elif choice:
            matches[label].update(season_id=str(choice), is_prior=False, status="manual")


def _apply_grade_overrides(matches: dict, overrides: dict) -> None:
    for label, choice in (overrides or {}).items():
        if label not in matches:
            matches[label] = {"candidates": []}
        if choice == "__own__":
            matches[label].update(grade_name=label, status="own")
        elif choice:
            matches[label].update(grade_name=str(choice), status="manual")


# ── the reconciler ───────────────────────────────────────────────────────────

async def _resolve(db: AsyncSession, org_id, club_name: str, req: ResolveRequest) -> dict:
    if not _col(req.mapping, "played_on"):
        raise HTTPException(422, "No column is mapped to the match date.")

    built = [_build_row(i, r, req.mapping) for i, r in enumerate(req.rows)]

    season_labels, grade_labels = [], []
    for r in built:
        if r["season_label"] and r["season_label"] not in season_labels:
            season_labels.append(r["season_label"])
        if r["grade_label"] and r["grade_label"] not in grade_labels:
            grade_labels.append(r["grade_label"])

    seasons = await _org_seasons(db, org_id)
    grade_names = await _org_grade_names(db, org_id)
    smatch = ingest.match_seasons(season_labels, seasons) if season_labels else {}
    _apply_season_overrides(smatch, req.season_overrides)
    gmatch = ingest.match_grades(grade_labels, grade_names) if grade_labels else {}
    _apply_grade_overrides(gmatch, req.grade_overrides)

    existing = await _existing_games(db, org_id)

    seen_keys: dict = {}
    counts: dict = {}
    for r in built:
        sm = smatch.get(r["season_label"]) if r["season_label"] else None
        r["season_id"] = (sm or {}).get("season_id")
        gm = gmatch.get(r["grade_label"]) if r["grade_label"] else None
        r["grade_name"] = (gm or {}).get("grade_name") or r["grade_label"]

        cat = r["category"]
        counts[cat] = counts.get(cat, 0) + 1

        if cat in ("cancelled", "no_score"):
            r["status"], r["status_note"] = "skipped", f"{CATEGORY_LABELS[cat]} — nothing to import."
        elif cat == "bye" and not req.include_byes:
            r["status"], r["status_note"] = "skipped", "Bye — not included."
        elif cat == "forfeit" and not req.include_forfeits:
            r["status"], r["status_note"] = "skipped", "Forfeit — not included."
        elif cat == "unknown":
            r["status"], r["status_note"] = "blocked", (
                f"Can't tell what '{r['outcome_raw']}' means, and there are no scores to work it out from."
                if r["outcome_raw"] else "No result and no scores — nothing to import.")
        elif not r["played_on"]:
            r["status"], r["status_note"] = "blocked", "No readable match date."
        elif not r["season_id"]:
            r["status"], r["status_note"] = "blocked", "No season — match or create one on the Seasons step."
        elif not r["grade_name"]:
            r["status"], r["status_note"] = "blocked", "No team or grade on this row."
        elif cat != "bye" and not r["opponent"]:
            r["status"], r["status_note"] = "blocked", "No opposition club."
        else:
            key = _identity_key(r)
            if key in seen_keys:
                r["status"] = "duplicate"
                r["status_note"] = f"Same game as row {seen_keys[key] + 1} — imported once."
            else:
                seen_keys[key] = r["index"]
                prior = existing.get((r["played_on"], _opp_key(r["opponent"] or ""))) or []
                mine = [p for p in prior if p["grade"] == _norm(r["grade_name"])]
                others = [p for p in prior if p["grade"] != _norm(r["grade_name"])]
                if any(p["source"] == "synced" for p in mine):
                    r["status"] = "synced"
                    r["status_note"] = "Already synced from PlayHQ — left alone."
                elif mine:
                    r["status"], r["status_note"] = "update", "Already imported — will be updated."
                else:
                    r["status"], r["status_note"] = "ready", None
                    if any(p["source"] == "synced" for p in others):
                        # The same club on the same day under a different
                        # team — normally exactly right (the Seniors and the
                        # Reserves both played them), but worth naming in
                        # case the two are the one match under two labels.
                        r["warnings"].append({"kind": "check", "text": (
                            "Already have a game against this club on this date under "
                            + ", ".join(sorted({p["grade_name"] for p in others if p["source"] == "synced"}))
                            + " — a different team's game, unless your sheet names this one differently.")})

    importable = [r for r in built if r["status"] in ("ready", "update")]

    warnings = []
    blocked = [r for r in built if r["status"] == "blocked"]
    if blocked:
        reasons: dict = {}
        for r in blocked:
            reasons[r["status_note"]] = reasons.get(r["status_note"], 0) + 1
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        warnings.append({"kind": "check", "text":
                         f"{len(blocked)} row(s) can't be imported yet — "
                         + "; ".join(f"{n}× {why}" for why, n in top)})
    sheet_errors = sum(1 for r in importable for w in r["warnings"] if w["kind"] == "sheet_error")
    if sheet_errors:
        warnings.append({"kind": "sheet_error", "text":
                         f"{sheet_errors} row(s) don't add up in the sheet itself. Fix them in your "
                         "spreadsheet and upload again, or import as written to keep the club's own figures."})
    inferred = sum(1 for r in importable if r["result_inferred"])
    if inferred:
        warnings.append({"kind": "check", "text":
                         f"{inferred} row(s) had no recorded result — worked out from the scores."})
    no_side = sum(1 for r in importable if r["our_side"] is None and r["category"] != "bye")
    if no_side:
        warnings.append({"kind": "check", "text":
                         f"{no_side} row(s) don't say home or away (finals at a neutral ground, usually) — "
                         f"{club_name} is stored as the home side on those."})
    synced = sum(1 for r in built if r["status"] == "synced")
    if synced:
        warnings.append({"kind": "check", "text":
                         f"{synced} row(s) match a game already synced from PlayHQ — those are left alone, "
                         "the synced game wins."})

    by_season: dict = {}
    for r in importable:
        k = r["season_label"] or "—"
        s = by_season.setdefault(k, {"season_label": k, "games": 0, "wins": 0, "losses": 0,
                                     "draws": 0, "byes": 0, "grades": set()})
        s["games"] += 1
        if r["category"] == "bye":
            s["byes"] += 1
        elif r["result"] == "W":
            s["wins"] += 1
        elif r["result"] == "L":
            s["losses"] += 1
        elif r["result"] == "D":
            s["draws"] += 1
        if r["grade_name"]:
            s["grades"].add(r["grade_name"])
    season_summary = sorted(
        ({**s, "grades": sorted(s["grades"])} for s in by_season.values()),
        key=lambda s: s["season_label"])

    # Every count above is over the WHOLE sheet; only the per-row detail the
    # review table renders is capped, so a club that uploads something far
    # bigger than a century of results can't turn each keystroke into a
    # multi-megabyte response. The commit reads the rows again from the
    # request itself, so nothing is ever imported on a truncated view.
    detail = built[:ROW_DETAIL_LIMIT]

    return {
        "seasons": [{"raw_label": lb, **m} for lb, m in smatch.items()],
        "grades": [{"raw_label": lb, **m} for lb, m in gmatch.items()],
        "grade_options": grade_names,
        "rows": detail,
        "rows_truncated": len(built) - len(detail),
        "season_summary": season_summary,
        "warnings": warnings,
        "totals": {
            "rows": len(built),
            "importable": len(importable),
            "skipped": sum(1 for r in built if r["status"] == "skipped"),
            "blocked": len(blocked),
            "duplicates": sum(1 for r in built if r["status"] == "duplicate"),
            "already_synced": synced,
            "updates": sum(1 for r in built if r["status"] == "update"),
            "sheet_errors": sheet_errors,
            "by_category": counts,
        },
        "_importable": importable,
    }


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/template.csv")
async def template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Year", "Round", "Series", "Team", "Home/Away", "Venue",
                     "Goals", "Behinds", "Score", "Opposition",
                     "Opp Goals", "Opp Behinds", "Opp Score", "Result"])
    writer.writerow(["12/04/1975", "1975", "1", "Home & Away", "Seniors", "Home", "Simpson Reserve",
                     "14", "11", "95", "Ascot Vale", "8", "9", "57", "Won"])
    writer.writerow(["13/09/1975", "1975", "GF", "Finals", "Seniors", "", "Princes Park",
                     "10", "8", "68", "Moreland", "11", "9", "75", "Loss"])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afl_results_import_template.csv"},
    )


@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    parsed = ingest.parse_upload(file.filename or "", content)
    if not parsed["rows"]:
        raise HTTPException(400, "No data found in file")
    mapping = _suggest_column_mapping(parsed["headers"], parsed["rows"])
    return {"headers": parsed["headers"], "rows": parsed["rows"], "mapping": mapping,
            "row_count": len(parsed["rows"])}


@router.post("/resolve")
async def resolve(
    req: ResolveRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    resolved = await _resolve(db, club.id, club.name or "Our club", req)
    resolved.pop("_importable")
    return resolved


@router.post("/commit")
async def commit(
    req: CommitRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    resolved = await _resolve(db, club.id, club.name or "Our club", req)
    importable = resolved["_importable"]
    if not importable:
        raise HTTPException(422, "Nothing to import — no rows are ready. "
                                 "Check the season and team matches and try again.")

    batch = ImportBatch(
        id=uuid.uuid4(), organisation_id=club.id, filename=req.filename, status="committed",
        granularity="game",
        column_mapping={f: _col(req.mapping, f) for f in ALL_FIELDS if _col(req.mapping, f)},
        row_count=len(req.rows), created_by_user_id=current_user.id,
        committed_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    await db.flush()

    # A (season, team label) pair becomes a real Grade row — a game has to
    # hang off one (games.grade_id), and it's also what puts these results
    # behind the grade filter and inside Merge Grades like any synced game.
    grade_cache: dict = {}

    async def _grade_id(season_id, label):
        key = (str(season_id), label.strip().lower())
        if key in grade_cache:
            return grade_cache[key]
        found = await db.execute(select(Grade).where(
            Grade.season_id == uuid.UUID(str(season_id)),
            func.lower(Grade.name) == label.strip().lower(),
        ))
        row = found.scalar_one_or_none()
        if row is None:
            row = Grade(id=uuid.uuid4(), season_id=uuid.UUID(str(season_id)), grassroots_id=None,
                        name=label.strip(), category=suggest_category(label))
            db.add(row)
            await db.flush()
        grade_cache[key] = row.id
        return row.id

    our_name = club.name or "Our club"
    created, updated, grades_created = 0, 0, len(grade_cache)

    for r in importable:
        grade_id = await _grade_id(r["season_id"], r["grade_name"])
        game_id = uuid.uuid5(club.id, f"import-game:{_identity_key(r)}")
        is_bye = r["category"] == "bye"
        # A blank home/away reads as neutral; our club takes the home slot so
        # the row still renders as a match-up (see _side_from_home_away).
        side = r["our_side"] or ("HOME" if not is_bye else None)
        opponent = r["opponent"] if not is_bye else None

        game = await db.get(Game, game_id)
        if game is None:
            game = Game(id=game_id)
            db.add(game)
            created += 1
        else:
            updated += 1
        game.grade_id = grade_id
        game.played_at = date.fromisoformat(r["played_on"])
        game.is_final = bool(r["is_final"])
        game.venue = r["venue"]
        game.result = None if is_bye else r["result"]
        if is_bye:
            game.home_team = game.away_team = None
            game.home_club = game.away_club = None
            game.opp_club_name = None
            game.winning_team = None
            game.home_org_id = game.away_org_id = None
        else:
            home_is_us = side == "HOME"
            game.home_team = our_name if home_is_us else opponent
            game.away_team = opponent if home_is_us else our_name
            game.home_club, game.away_club = game.home_team, game.away_team
            game.opp_club_name = opponent
            game.home_org_id = club.id if home_is_us else None
            game.away_org_id = None if home_is_us else club.id
            game.winning_team = (
                our_name if r["result"] == "W" else opponent if r["result"] == "L" else None)

        details = await db.get(AflGameDetails, game_id)
        if details is None:
            details = AflGameDetails(game_id=game_id, playhq_id=None)
            db.add(details)
        details.round_name = r["round_name"]
        details.round_abbrev = r["round_label"]
        # A bye is on the record but was never played — keeping it out of
        # 'FINAL' is what stops it counting as a game in the club's played
        # tally and on the results list.
        details.status = "BYE" if is_bye else "FINAL"
        details.start_time = r["start_time"]
        details.our_side = side
        details.venue_name = r["venue"]
        if is_bye:
            details.home_goals = details.home_behinds = details.home_score = None
            details.away_goals = details.away_behinds = details.away_score = None
        elif side == "HOME":
            details.home_goals, details.home_behinds, details.home_score = (
                r["our_goals"], r["our_behinds"], r["our_score"])
            details.away_goals, details.away_behinds, details.away_score = (
                r["opp_goals"], r["opp_behinds"], r["opp_score"])
        else:
            details.away_goals, details.away_behinds, details.away_score = (
                r["our_goals"], r["our_behinds"], r["our_score"])
            details.home_goals, details.home_behinds, details.home_score = (
                r["opp_goals"], r["opp_behinds"], r["opp_score"])
        details.source = "import"
        details.import_batch_id = batch.id
        details.import_ref = r["external_ref"]
        details.is_bye = is_bye
        details.is_forfeit = r["category"] == "forfeit"
        details.result_note = r["outcome_raw"]
        # synced_at is the sync's "still needs a stats pull" signal; an
        # imported result has no PlayHQ game behind it to pull, so stamping it
        # keeps the incremental sync from ever queueing one.
        details.synced_at = datetime.now(timezone.utc)

    grades_created = len(grade_cache) - grades_created

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="afl_import_results",
        target_type="import_batch", target_id=str(batch.id),
        details={"games_created": created, "games_updated": updated,
                 "rows": len(req.rows), "grades_touched": len(grade_cache)},
    )
    await db.commit()

    return {
        "batch_id": str(batch.id),
        "games_created": created,
        "games_updated": updated,
        "grades_touched": len(grade_cache),
        "rows_skipped": resolved["totals"]["skipped"],
        "rows_blocked": resolved["totals"]["blocked"],
        "already_synced": resolved["totals"]["already_synced"],
        "season_summary": resolved["season_summary"],
    }


@router.get("")
async def list_imports(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Only this tool's own batches. Import Stats writes to the same shared
    import_batches table with granularity='season', so the two logs would
    otherwise show each other's uploads and offer an Undo that does nothing."""
    rows = (await db.execute(
        select(ImportBatch).where(
            ImportBatch.organisation_id == club.id, ImportBatch.granularity == "game")
        .order_by(ImportBatch.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(b.id), "filename": b.filename, "status": b.status,
            "row_count": b.row_count,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "committed_at": b.committed_at.isoformat() if b.committed_at else None,
            "undone_at": b.undone_at.isoformat() if b.undone_at else None,
        }
        for b in rows
    ]


@router.get("/{batch_id}/games")
async def list_batch_games(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.is_final,
               g.venue, gr.name AS grade_name, s.name AS season_name, s.year,
               d.round_name, d.is_bye, d.is_forfeit, d.result_note,
               d.home_goals, d.home_behinds, d.home_score,
               d.away_goals, d.away_behinds, d.away_score, d.our_side
        FROM afl_game_details d
        JOIN games g ON g.id = d.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE d.import_batch_id = :batch AND s.organisation_id = :org
        ORDER BY g.played_at DESC NULLS LAST
    """), {"batch": batch_id, "org": str(club.id)})
    return [dict(r._mapping) for r in rows]


@router.post("/{batch_id}/undo")
async def undo_import(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    batch = await db.get(ImportBatch, uuid.UUID(batch_id))
    if not batch or batch.organisation_id != club.id:
        raise HTTPException(404, "Import batch not found")
    if batch.undone_at is not None:
        raise HTTPException(400, "This import was already undone")

    # Deleting the game takes its details/periods/lines/events with it (all
    # ON DELETE CASCADE). Scoped to source='import' so a game the sync has
    # since taken over can never be removed by undoing the upload that
    # first created it.
    #
    # Note on re-uploads: because a game's id is derived from the row's own
    # identity, uploading a corrected sheet rewrites the same rows and stamps
    # them with the NEW batch. Undo therefore removes whatever that batch
    # last wrote, which is the honest reading of "undo this upload" — the
    # older batch's log entry stays, but its rows now belong to the newer
    # one.
    result = await db.execute(text("""
        DELETE FROM games WHERE id IN (
            SELECT d.game_id FROM afl_game_details d
            JOIN games g ON g.id = d.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE d.import_batch_id = :batch AND d.source = 'import'
              AND s.organisation_id = :org
        )
    """), {"batch": batch_id, "org": str(club.id)})
    batch.status = "undone"
    batch.undone_at = datetime.now(timezone.utc)

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="undo_afl_import_results",
        target_type="import_batch", target_id=batch_id,
    )
    await db.commit()
    return {"status": "undone", "games_removed": result.rowcount}
