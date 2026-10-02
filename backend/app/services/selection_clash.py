"""Which same-date selections actually clash.

A player used to be allowed in only ONE XI per date. That is wrong for clubs
that run games back to back: a Colts game in the morning and a T20 in the
evening are two different sessions, and so are a junior game and a senior game.
This module says, for two fixtures on the same date, whether picking one player
in both is a real clash (the pick is refused, or becomes a call-up) or a pair
that can be played, which the board allows and only flags.

Rules, in order:

1. A multi-day game (``end_on`` after ``played_on``, or a grade that only plays
   two-day) takes the whole date. Always a clash.
2. One junior grade and one non-junior grade: allowed. Juniors and seniors play
   in different sessions, whatever the clock says. The flag carries the start
   times so a selector can check them.
3. Both start times known: allowed when the games do not overlap, using an
   estimated length per format (``DURATION_MINUTES``). Overlapping is a clash.
4. A start time missing and no junior/senior split: cannot tell, so it stays a
   clash. Failing closed is the old behaviour, not a new refusal.

The estimate is only an estimate (no fixture carries an end time), so the flag
always shows the gap, and a gap under ``TIGHT_GAP_MINUTES`` is marked tight.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy import text

from app.services import grade_labels

# How long a game is assumed to run from its start time. T20 is a three and a
# half hour game; a one-day game is a full day. An unknown format uses the
# longer figure, so an unknown can only make a pair look MORE clashing.
DURATION_MINUTES = {"t20": 210, "one_day": 480}
DEFAULT_DURATION_MINUTES = 480
TIGHT_GAP_MINUTES = 60


def parse_minutes(value: Any) -> Optional[int]:
    """"HH:MM" (or "HH:MM:SS") to minutes after midnight. None for anything else."""
    if not value:
        return None
    parts = str(value).strip().split(":")
    try:
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def fmt_12h(minutes: Optional[int]) -> Optional[str]:
    if minutes is None:
        return None
    h, m = divmod(minutes % (24 * 60), 60)
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{suffix}"


def _is_multi_day(fx: dict) -> bool:
    end_on, played_on = fx.get("end_on"), fx.get("played_on")
    if end_on and played_on and end_on > played_on:
        return True
    formats = fx.get("formats") or frozenset()
    return bool(formats) and set(formats) == {"two_day"}


def _duration(fx: dict) -> int:
    lengths = [DURATION_MINUTES[f] for f in (fx.get("formats") or ()) if f in DURATION_MINUTES]
    return max(lengths) if lengths else DEFAULT_DURATION_MINUTES


def classify_pair(this_fx: dict, other_fx: dict) -> dict:
    """Judge two same-date fixtures. Each is a dict with ``start_time``,
    ``played_on``, ``end_on``, ``categories`` and ``formats``.

    Returns ``{"compatible": bool, "reason": str, ...}``. When compatible it
    also carries ``start_time`` (the other game's, 12 hour), ``gap_minutes``
    (None when it cannot be worked out) and ``tight``."""
    if _is_multi_day(this_fx) or _is_multi_day(other_fx):
        return {"compatible": False, "reason": "multi_day"}

    a_start = parse_minutes(this_fx.get("start_time"))
    b_start = parse_minutes(other_fx.get("start_time"))
    a_junior = "junior" in (this_fx.get("categories") or ())
    b_junior = "junior" in (other_fx.get("categories") or ())

    gap: Optional[int] = None
    if a_start is not None and b_start is not None:
        a_end = a_start + _duration(this_fx)
        b_end = b_start + _duration(other_fx)
        overlaps = a_start < b_end and b_start < a_end
        if overlaps and a_junior == b_junior:
            return {"compatible": False, "reason": "overlap"}
        # Gap between the earlier game's estimated finish and the later start.
        gap = (b_start - a_end) if a_start <= b_start else (a_start - b_end)
        if overlaps:
            gap = 0
    elif a_junior == b_junior:
        return {"compatible": False, "reason": "no_time"}

    split = a_junior != b_junior
    return {
        "compatible": True,
        "reason": "junior_senior" if split else "back_to_back",
        "start_time": fmt_12h(b_start),
        "gap_minutes": gap,
        # A junior/senior pair is allowed whatever the clock says, so the
        # flag is only "tight" when the estimates say the games run together.
        "tight": bool(gap is not None and gap < TIGHT_GAP_MINUTES),
    }


async def _fixture_facts(db, org_id, fixture_ids: Iterable) -> dict[str, dict]:
    ids = list(fixture_ids)
    if not ids:
        return {}
    res = await db.execute(
        text(
            "SELECT f.id, f.start_time, f.played_on, f.end_on, gr.name "
            "FROM fixtures f LEFT JOIN grades gr ON gr.id = f.grade_id "
            "WHERE f.id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": ids},
    )
    rows = res.fetchall()
    if not rows:
        return {}
    cats = await grade_labels.org_grade_category_sets(db, org_id)
    fmts = await grade_labels.org_grade_format_sets(db, org_id)
    out: dict[str, dict] = {}
    for fid, start_time, played_on, end_on, grade_name in rows:
        out[str(fid)] = {
            "start_time": start_time,
            "played_on": played_on,
            "end_on": end_on,
            "categories": (
                grade_labels.categories_for_name(cats, grade_name) if grade_name else frozenset()
            ),
            "formats": (
                grade_labels.formats_for_name(fmts, grade_name) if grade_name else frozenset()
            ),
        }
    return out


async def compatible_fixtures(db, org_id, fx, other_fixture_ids: Iterable) -> dict[str, dict]:
    """``{other fixture id: classify_pair result}`` for the other fixtures that
    can be played alongside ``fx`` (the compatible ones only).

    ``fx`` is the fixture being picked, an ORM row. Ids are the other
    same-date fixtures a player is already named in."""
    others = {str(i) for i in other_fixture_ids}
    if not others:
        return {}
    facts = await _fixture_facts(db, org_id, [fx.id, *others])
    mine = facts.get(str(fx.id))
    if not mine:
        return {}
    mine = {**mine, "played_on": fx.played_on, "end_on": fx.end_on}
    out: dict[str, dict] = {}
    for oid in others:
        theirs = facts.get(oid)
        if not theirs:
            continue
        verdict = classify_pair(mine, theirs)
        if verdict["compatible"]:
            out[oid] = verdict
    return out


def flag_text(team_name: str, verdict: dict) -> str:
    """One line for the board: "Colts 9:00am, finishes about 2 hours before"."""
    when = verdict.get("start_time")
    head = f"{team_name} {when}" if when else team_name
    gap = verdict.get("gap_minutes")
    if gap is None:
        return head
    if gap <= 0:
        return f"{head}, may run into this game"
    if verdict.get("reason") == "junior_senior":
        return head
    hours, mins = divmod(gap, 60)
    span = f"{hours}h {mins}m" if hours and mins else f"{hours}h" if hours else f"{mins}m"
    return f"{head}, about {span} between games"
