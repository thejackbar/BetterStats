"""The rules a club's association imposes on selection, and what they say about
a given side.

One vocabulary, one evaluator. Every screen that shows a rule flag — the
selection board, the availability matrix, the BetterSelect roster, the team
sheet, BetterIQ's selection analysis — reads what this module decides, and the
save path re-checks it. Two copies of "may this player be picked" is how one
screen ends up disagreeing with another.

WHAT IS DELIBERATELY GENERIC
----------------------------
This is not one association's rulebook with the numbers left blank:

* **The date an age is measured on is a setting.** One competition counts a
  player's age as at 1 September of the year the season started, the next as at
  1 January, a third takes it on the day of the match. All three come out of
  ``age_basis`` — a month, a day, and which end of the season the year is taken
  from — so no association's convention is privileged in code.
* **A rule says which grades it covers by NAME, never by id.** Grades are
  per-season rows: next season's "1st Grade" is a different id, so a rule keyed
  on ids silently stops applying the day the new season's grades are created,
  mid-rollover, with nothing to see. Names are what makes a rule standing.
  An EMPTY grade list means EVERY grade, which is what a club's first rule
  means before anyone has thought about divisions.
* **A rule can be scoped by grade CATEGORY or FORMAT instead**, so "every
  junior grade" or "the T20 competition" is one rule rather than one per grade.
* **Severity is the club's call.** The same age limit is a hard bar at one
  association and a guideline at the next, so each rule carries ``warn`` (say
  so, still allow it) or ``block`` (refuse the save). Nothing is hardcoded as
  one or the other, bar the kinds that are purely informational.
* **Every rule has an escape hatch.** ``selection_rule_players`` records a
  permit, clearance or exemption for one player against one rule — because
  associations grant them, and a system that cannot express one gets switched
  off rather than corrected.

WHAT A RULE NEVER DOES
----------------------
Invent a number. There is no built-in bowling-workload ladder, no default
qualifying-game count, no assumed age. A club that has set no rules gets
exactly the board it had before this shipped: no badges, no filters, no extra
queries. Every screen asks this module what to draw rather than deciding for
itself, so switching a rule off takes its badge, its filter and its warning
with it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grade_labels, player_age

# ── Vocabulary ───────────────────────────────────────────────────────────────

SEVERITIES = ("info", "warn", "block")

# The bowling-workload rule is guidance a selector reads, never a breach: a
# fourteen year old is not ineligible, there is simply a limit on what may be
# asked of them once they are out there. Same for a free-text rule nobody has
# asked to be ticked off.
_INFO_ONLY = {"bowling_workload"}

BOWLING_APPLIES = ("pace", "all")
QUALIFY_COUNTS = ("club", "this_or_higher", "same_grade")
ABOVE_SCOPES = ("any", "immediate")
FINALS_SCOPES = ("any", "only", "exclude")
AGE_YEAR_ENDS = ("season_start", "season_end")
AGE_BASES = ("cutoff", "match_date", "fixed_date")

# How an age rule's two ends compare. A competition writes its limits either
# way round — "15 and over" and "over 15" are different rules, and so are
# "under 21" and "21 or under" — so the club picks rather than us assuming.
MIN_OPS = ("gte", "gt")
MAX_OPS = ("lt", "lte")

# Bowling types that count as pace or medium pace, which is the group every
# junior bowling-workload policy is written about. Mirrors the classifier
# BetterSelect's own Pace/Spin filter uses (selectionMeta.classifyBowl).
PACE_TYPES = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST"}

RULE_KINDS: dict[str, dict] = {
    "age": {
        "label": "Age limit",
        "blurb": "A minimum age, a maximum, or both, measured on whatever date "
                 "your association counts age from.",
        "needs": "A date of birth on each player's profile.",
    },
    "overseas": {
        "label": "Overseas players",
        "blurb": "How many overseas players may be named in one side.",
        "needs": "The overseas flag on a player's profile.",
    },
    "bowling_workload": {
        "label": "Bowling limits by age",
        "blurb": "Overs per day and per spell for younger bowlers. Shown "
                 "beside the player rather than blocking anything.",
        "needs": "A date of birth, and a bowling style on the profile.",
    },
    "finals_qualification": {
        "label": "Finals qualification",
        "blurb": "Games that have to be played before a player is eligible for "
                 "a final.",
        "needs": "Nothing — counted from matches played and sides named.",
    },
    "grade_cap": {
        "label": "Playing down after a higher grade",
        "blurb": "Stops a player dropping back once they have played a set "
                 "number of games in a higher grade.",
        "needs": "Your squads in order of seniority.",
    },
    "fees": {
        "label": "Fees paid",
        "blurb": "Players must be square with the club to be picked.",
        "needs": "BetterFees, or the financial tick on a player's profile.",
    },
    "training": {
        "label": "Training attendance",
        "blurb": "A minimum number of net sessions inside a recent window.",
        "needs": "Nets sessions, or the training tick on a player's profile.",
    },
    "registration": {
        "label": "Registration",
        "blurb": "Players must be registered for the season before they play.",
        "needs": "The registration tick on the Accounts screen.",
    },
    "rest": {
        "label": "Rest between matches",
        "blurb": "A cap on how many matches one player is named in across a "
                 "few days.",
        "needs": "Nothing — read from the sides you have named.",
    },
    "custom": {
        "label": "Your own rule",
        "blurb": "Anything the app can't work out for itself, with a tick per "
                 "player when you want one.",
        "needs": "Nothing.",
    },
}

# The platform default when a club has never opened the settings screen: age as
# at 1 September of the year the season started, which is both the Cricket
# Australia junior-policy convention and what a club is most likely to mean.
# It only ever applies once a club has written an age rule of its own.
DEFAULT_AGE_BASIS = {"basis": "cutoff", "month": 9, "day": 1, "year": "season_start"}
# The month a season is taken to start in when a fixture has no season on it to
# read. July for a southern-hemisphere summer; a club playing an April-to-
# September season sets 4 and every age lands in the right year.
DEFAULT_SEASON_START_MONTH = 7

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _int(value, lo: int, hi: int, fallback: int | None = None) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if lo <= n <= hi else fallback


def _str_list(value, limit: int = 60) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s and s not in out:
            out.append(s[:120])
        if len(out) >= limit:
            break
    return out


# ── The club's own defaults ──────────────────────────────────────────────────

def club_config(org) -> dict:
    """The club-wide rule settings, with the platform defaults filled in."""
    raw = getattr(org, "selection_rules_config", None) or {}
    return {
        "age_basis": clean_age_basis(raw.get("age_basis")),
        "season_start_month": _int(raw.get("season_start_month"), 1, 12,
                                   DEFAULT_SEASON_START_MONTH),
        # Which of the plain informational badges the board draws beside a
        # player. A club that doesn't collect fees through BetterFees, or
        # doesn't want its selectors seeing who owes, turns them off here.
        # A RULE about the same thing still shows — that one was asked for.
        "show_fees": raw.get("show_fees") is not False,
        "show_training": raw.get("show_training") is not False,
    }


def clean_age_basis(raw) -> dict:
    """How age is measured, normalised. Anything unreadable falls back to the
    platform default rather than saving a rule nobody could satisfy."""
    if not isinstance(raw, dict):
        return dict(DEFAULT_AGE_BASIS)
    basis = raw.get("basis")
    if basis == "match_date":
        return {"basis": "match_date"}
    if basis == "fixed_date":
        # One calendar date, the same every season — for a competition that
        # publishes its cutoff as an actual date rather than as a rule about
        # the season. Unreadable falls back to the platform default rather
        # than storing a date nobody could satisfy.
        try:
            day = date.fromisoformat(str(raw.get("date"))[:10])
        except (TypeError, ValueError):
            return dict(DEFAULT_AGE_BASIS)
        return {"basis": "fixed_date", "date": day.isoformat()}
    month = _int(raw.get("month"), 1, 12, DEFAULT_AGE_BASIS["month"])
    day = _int(raw.get("day"), 1, 31, DEFAULT_AGE_BASIS["day"])
    year = raw.get("year") if raw.get("year") in AGE_YEAR_ENDS else DEFAULT_AGE_BASIS["year"]
    return {"basis": "cutoff", "month": month, "day": day, "year": year}


def age_basis_label(basis: dict) -> str:
    if (basis or {}).get("basis") == "match_date":
        return "on the day of the match"
    b = clean_age_basis(basis)
    if b["basis"] == "fixed_date":
        try:
            d = date.fromisoformat(b["date"])
            return f"as at {d.day} {_MONTHS[d.month - 1]} {d.year}"
        except (TypeError, ValueError, KeyError):
            return "as at a set date"
    end = "the year the season started" if b["year"] == "season_start" else "the year the season ends"
    return f"as at {b['day']} {_MONTHS[b['month'] - 1]} of {end}"


def season_year_for(day: date, start_month: int) -> int:
    """The year a season starting in ``start_month`` is labelled by."""
    return day.year if day.month >= start_month else day.year - 1


def season_window(year: int, start_month: int) -> tuple[date, date]:
    """First and last day of a season labelled ``year``. A season starting in
    January is one calendar year; anything else straddles two."""
    start = date(year, start_month, 1)
    end = date(year + 1, start_month, 1) - timedelta(days=1) if start_month > 1 else date(year, 12, 31)
    return start, end


def age_as_at(basis: dict, match_date: date | None, season_year: int | None,
              start_month: int) -> date | None:
    """The date an age is measured on for this fixture, or None if we can't say.

    A cutoff resolves against the SEASON, not the calendar: "1 September of the
    year the season commenced" is September 2025 for every match of a 2025/26
    season, including the ones played in February. That is what makes a player
    the same age all season, which is the whole point of a cutoff.
    """
    b = clean_age_basis(basis)
    if b["basis"] == "match_date":
        return match_date
    if b["basis"] == "fixed_date":
        try:
            return date.fromisoformat(b["date"])
        except (TypeError, ValueError, KeyError):
            return None
    if season_year is None:
        if not match_date:
            return None
        season_year = season_year_for(match_date, start_month)
    year = season_year if b["year"] == "season_start" else season_year + 1
    try:
        return date(year, b["month"], b["day"])
    except ValueError:
        # 29 February in a non-leap year, or 31 of a 30-day month. The last day
        # of that month is what the association means.
        for day in (b["day"] - 1, b["day"] - 2, b["day"] - 3):
            try:
                return date(year, b["month"], day)
            except ValueError:
                continue
        return None


# ── Rule validation ──────────────────────────────────────────────────────────

def clean_severity(kind: str, value) -> str:
    if kind in _INFO_ONLY:
        return "info"
    return value if value in SEVERITIES else "warn"


def clean_scope(raw) -> dict:
    """Which fixtures a rule covers. An empty list anywhere means EVERY one —
    a club's first rule applies to the whole club until it says otherwise."""
    raw = raw if isinstance(raw, dict) else {}
    finals = raw.get("finals") if raw.get("finals") in FINALS_SCOPES else "any"
    return {
        "grade_names": _str_list(raw.get("grade_names")),
        "categories": [c for c in _str_list(raw.get("categories"))
                       if c in grade_labels.GRADE_CATEGORIES],
        "formats": [f for f in _str_list(raw.get("formats"))
                    if f in grade_labels.MATCH_FORMATS],
        "team_ids": [t for t in _str_list(raw.get("team_ids")) if _is_uuid(t)],
        "finals": finals,
    }


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def clean_config(kind: str, raw) -> dict:
    """A rule's own numbers, normalised. Raises ValueError when what's left
    could not be a rule — an age limit with neither end set says nothing."""
    raw = raw if isinstance(raw, dict) else {}
    if kind == "age":
        cfg: dict = {}
        lo = _int(raw.get("min_age"), player_age.MIN_AGE_LIMIT, player_age.MAX_AGE_LIMIT)
        hi = _int(raw.get("under_age"), player_age.MIN_AGE_LIMIT, player_age.MAX_AGE_LIMIT)
        if lo is None and hi is None:
            raise ValueError("Set a minimum age, a maximum, or both.")
        if lo is not None and hi is not None and hi < lo:
            raise ValueError("The maximum age has to be at or above the minimum.")
        if lo is not None:
            cfg["min_age"] = lo
            cfg["min_op"] = raw.get("min_op") if raw.get("min_op") in MIN_OPS else "gte"
        if hi is not None:
            cfg["under_age"] = hi
            cfg["max_op"] = raw.get("max_op") if raw.get("max_op") in MAX_OPS else "lt"
        # A rule may measure age its own way; without one it follows the club's.
        if raw.get("as_at"):
            cfg["as_at"] = clean_age_basis(raw.get("as_at"))
        return cfg
    if kind == "overseas":
        return {
            "max_in_xi": _int(raw.get("max_in_xi"), 0, 20, 1),
            "max_in_round": _int(raw.get("max_in_round"), 0, 40),
        }
    if kind == "bowling_workload":
        ladder = []
        for rung in (raw.get("ladder") or []):
            if not isinstance(rung, dict):
                continue
            under = _int(rung.get("under_age"), player_age.MIN_AGE_LIMIT, player_age.MAX_AGE_LIMIT)
            if under is None:
                continue
            ladder.append({
                "under_age": under,
                "max_overs": _int(rung.get("max_overs"), 1, 90),
                "max_spell": _int(rung.get("max_spell"), 1, 40),
                "rest_minutes": _int(rung.get("rest_minutes"), 0, 240),
            })
        if not ladder:
            raise ValueError("Add at least one age band.")
        ladder.sort(key=lambda r: r["under_age"])
        share = raw.get("max_share_of_overs")
        try:
            share = round(float(share), 3) if share not in (None, "") else None
        except (TypeError, ValueError):
            share = None
        if share is not None and not 0 < share <= 1:
            share = None
        return {
            "ladder": ladder,
            "applies_to": raw.get("applies_to") if raw.get("applies_to") in BOWLING_APPLIES else "pace",
            "max_share_of_overs": share,
        }
    if kind == "finals_qualification":
        return {
            "min_games": _int(raw.get("min_games"), 1, 60, 1),
            "counts": raw.get("counts") if raw.get("counts") in QUALIFY_COUNTS else "club",
        }
    if kind == "grade_cap":
        return {
            "max_games_above": _int(raw.get("max_games_above"), 1, 60, 2),
            "above": raw.get("above") if raw.get("above") in ABOVE_SCOPES else "any",
        }
    if kind == "fees":
        return {}
    if kind == "training":
        return {
            "min_sessions": _int(raw.get("min_sessions"), 1, 30, 1),
            "window_days": _int(raw.get("window_days"), 1, 365, 21),
        }
    if kind == "registration":
        return {}
    if kind == "rest":
        return {
            "max_games_in_window": _int(raw.get("max_games_in_window"), 1, 20, 1),
            "window_days": _int(raw.get("window_days"), 1, 60, 2),
        }
    if kind == "custom":
        note = str(raw.get("note") or "").strip()[:600]
        if not note:
            raise ValueError("Write down what the rule is.")
        return {"note": note, "require_tick": bool(raw.get("require_tick"))}
    raise ValueError("Unknown rule type.")


def _min_phrase(age: int, op: str | None) -> str:
    return f"over {age}" if op == "gt" else f"{age} and over"


def _max_phrase(age: int, op: str | None) -> str:
    return f"{age} or under" if op == "lte" else f"under {age}"


def rule_summary(kind: str, config: dict, basis: dict | None = None) -> str:
    """One plain line saying what the rule asks for. Read on the settings
    screen, on the board's rule list and in the warning itself, so it is
    written once here."""
    c = config or {}
    if kind == "age":
        bits = []
        if c.get("min_age") is not None:
            bits.append(_min_phrase(c["min_age"], c.get("min_op")))
        if c.get("under_age") is not None:
            bits.append(_max_phrase(c["under_age"], c.get("max_op")))
        return " · ".join(bits) + f" ({age_basis_label(c.get('as_at') or basis)})"
    if kind == "overseas":
        n = c.get("max_in_xi", 1)
        line = "No overseas players" if n == 0 else f"At most {n} overseas player{'s' if n != 1 else ''} in a side"
        if c.get("max_in_round"):
            line += f", {c['max_in_round']} across the club on a match day"
        return line
    if kind == "bowling_workload":
        who = "pace and medium pace" if c.get("applies_to") == "pace" else "all bowlers"
        rungs = ", ".join(
            f"under {r['under_age']}: {r['max_overs']} overs" if r.get("max_overs") else f"under {r['under_age']}"
            for r in (c.get("ladder") or [])
        )
        return f"{who.capitalize()} — {rungs}"
    if kind == "finals_qualification":
        where = {"club": "for the club", "this_or_higher": "in this grade or higher",
                 "same_grade": "in this grade"}.get(c.get("counts", "club"), "for the club")
        n = c.get("min_games", 1)
        return f"{n} game{'s' if n != 1 else ''} {where} before a final"
    if kind == "grade_cap":
        n = c.get("max_games_above", 2)
        where = "any higher grade" if c.get("above") == "any" else "the grade immediately above"
        return f"Can't play here after {n} game{'s' if n != 1 else ''} in {where}"
    if kind == "fees":
        return "Fees have to be square"
    if kind == "training":
        n, d = c.get("min_sessions", 1), c.get("window_days", 21)
        return f"{n} net session{'s' if n != 1 else ''} in the last {d} days"
    if kind == "registration":
        return "Registered for the season"
    if kind == "rest":
        n, d = c.get("max_games_in_window", 1), c.get("window_days", 2)
        return f"At most {n} match{'es' if n != 1 else ''} in any {d} days"
    if kind == "custom":
        return c.get("note", "")
    return ""


def scope_summary(scope: dict, team_names: dict[str, str] | None = None) -> str:
    """Who the rule covers, in words. "Every grade" is the honest reading of an
    empty scope and is what a club's first rule means."""
    s = clean_scope(scope)
    bits: list[str] = []
    if s["grade_names"]:
        bits.append(", ".join(s["grade_names"]))
    if s["categories"]:
        bits.append(", ".join(grade_labels.category_label(c) for c in s["categories"]))
    if s["formats"]:
        bits.append(", ".join(grade_labels.format_label(f) for f in s["formats"]))
    if s["team_ids"] and team_names:
        named = [team_names[t] for t in s["team_ids"] if t in team_names]
        if named:
            bits.append(", ".join(named))
    line = " · ".join(bits) if bits else "Every grade"
    if s["finals"] == "only":
        line += " · finals only"
    elif s["finals"] == "exclude":
        line += " · not in finals"
    return line


# ── The grades a rule can name ───────────────────────────────────────────────

async def club_grades(db: AsyncSession, org_id) -> list[dict]:
    """Every grade the club runs, exactly as Manage Grades reads them.

    That screen is where a club names, merges and ORDERS its grades, so the
    rule scope picker has to agree with it: merged grades are one entry under
    the name that was kept, a renamed grade reads under the club's own name for
    it, and the list comes back in the club's reading order rather than
    alphabetically. Anything else offers a selector a list they don't
    recognise, in an order nobody chose.

    ``recent`` marks the grades from the club's two most recent seasons — what
    it actually runs now, as opposed to a decade of history the picker would
    otherwise bury them in.
    """
    rows = (await db.execute(
        text(
            "SELECT gr.name, MAX(gr.display_name_override) AS display_name, "
            "MIN(gr.display_order) AS display_order, MAX(s.year) AS latest_year "
            "FROM grades gr JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = :org GROUP BY gr.name"
        ),
        {"org": org_id},
    )).mappings().all()
    if not rows:
        return []

    aliases = {
        r["alias_name"]: r["canonical_name"]
        for r in (await db.execute(
            text("SELECT alias_name, canonical_name FROM grade_merge_logs "
                 "WHERE org_id = :org AND undone_at IS NULL"),
            {"org": org_id},
        )).mappings().all()
    }
    display_by_raw = {r["name"]: (r["display_name"] or r["name"]) for r in rows}

    # The two most recent seasons the club holds any grade in. Two rather than
    # one because a club mid-rollover has next season's grades half-created,
    # and a rule written now has to be able to name last season's.
    years = sorted({r["latest_year"] for r in rows if r["latest_year"] is not None}, reverse=True)
    recent_years = set(years[:2])

    folded: dict[str, dict] = {}
    for r in rows:
        canonical = resolve_canonical_grade(aliases, r["name"])
        label = display_by_raw.get(canonical) or canonical
        slot = folded.setdefault(label, {
            "name": label, "display_order": None, "recent": False, "aliases": set(),
        })
        slot["aliases"].add(r["name"])
        if r["display_order"] is not None and (
                slot["display_order"] is None or r["display_order"] < slot["display_order"]):
            slot["display_order"] = r["display_order"]
        if r["latest_year"] is not None and r["latest_year"] in recent_years:
            slot["recent"] = True

    out = [{k: v for k, v in g.items() if k != "aliases"} for g in folded.values()]
    # The club's own reading order first; a grade nobody has placed sorts after
    # every placed one. Same rule as Manage Grades and everywhere else.
    out.sort(key=lambda g: (g["display_order"] is None, g["display_order"] or 0, g["name"].lower()))
    return out


def resolve_canonical_grade(aliases: dict[str, str], name: str) -> str:
    """Follow a merge chain to the grade that was kept. Mirrors admin.py's own
    resolver, cycle guard included."""
    seen: set[str] = set()
    current = name
    while current in aliases and current not in seen:
        seen.add(current)
        current = aliases[current]
    return current


async def grade_alias_map(db: AsyncSession, org_id) -> dict[str, str]:
    """Raw grade name → the canonical DISPLAY name a rule would have stored.

    Keyed sponsor-suffix-stripped and case-folded, so a fixture arriving with
    "A Grade (Gatorade)" resolves the same as our stored "A Grade".
    """
    rows = (await db.execute(
        text("SELECT DISTINCT gr.name, gr.display_name_override FROM grades gr "
             "JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :org"),
        {"org": org_id},
    )).fetchall()
    aliases = {
        a: c for a, c in (await db.execute(
            text("SELECT alias_name, canonical_name FROM grade_merge_logs "
                 "WHERE org_id = :org AND undone_at IS NULL"),
            {"org": org_id},
        )).fetchall()
    }
    display_by_raw = {name: (override or name) for name, override in rows}
    out: dict[str, str] = {}
    for name, override in rows:
        canonical = resolve_canonical_grade(aliases, name)
        label = display_by_raw.get(canonical) or canonical
        for spelling in {name, override or name}:
            out[grade_labels.strip_sponsor_suffix(spelling).lower()] = label
    return out


# ── Reading and writing rules ────────────────────────────────────────────────

def rule_out(row, basis: dict, team_names: dict[str, str] | None = None) -> dict:
    kind = row["kind"]
    config = row["config"] or {}
    scope = clean_scope(row["scope"])
    return {
        "id": str(row["id"]),
        "kind": kind,
        "label": RULE_KINDS.get(kind, {}).get("label", kind),
        "name": row["name"] or RULE_KINDS.get(kind, {}).get("label", kind),
        "enabled": bool(row["enabled"]),
        "severity": clean_severity(kind, row["severity"]),
        "scope": scope,
        "config": config,
        "position": row["position"],
        "summary": rule_summary(kind, config, basis),
        "scope_summary": scope_summary(scope, team_names),
    }


async def list_rules(db: AsyncSession, org_id, *, enabled_only: bool = False) -> list[dict]:
    """Every rule the club has written, as raw rows (dicts)."""
    sql = ("SELECT id, kind, name, enabled, severity, scope, config, position "
           "FROM selection_rules WHERE organisation_id = :org")
    if enabled_only:
        sql += " AND enabled"
    sql += " ORDER BY position, created_at"
    rows = (await db.execute(text(sql), {"org": org_id})).mappings().all()
    return [dict(r) for r in rows]


async def clearances_for(db: AsyncSession, org_id) -> dict[tuple[str, str], dict]:
    """Every per-player exception, keyed (rule_id, player_id)."""
    rows = (await db.execute(
        text("SELECT rule_id, player_id, state, note FROM selection_rule_players "
             "WHERE organisation_id = :org"),
        {"org": org_id},
    )).fetchall()
    return {
        (str(rid), str(pid)): {"state": state, "note": note}
        for rid, pid, state, note in rows
    }


# ── Which rules apply to a fixture ───────────────────────────────────────────

def fixture_is_final(fx) -> bool:
    """Whether this fixture is a final. The club's own answer wins; otherwise
    read the round name, the same heuristic the fixture sync and `games.is_final`
    already use."""
    override = getattr(fx, "is_final", None)
    if override is not None:
        return bool(override)
    return "final" in (getattr(fx, "round", None) or "").lower()


def _scope_matches(scope: dict, *, grade_name: str | None, categories: frozenset,
                   formats: frozenset, team_id: str | None, is_final: bool) -> bool:
    s = clean_scope(scope)
    if s["finals"] == "only" and not is_final:
        return False
    if s["finals"] == "exclude" and is_final:
        return False
    if s["grade_names"]:
        if not grade_name:
            return False
        want = {grade_labels.strip_sponsor_suffix(n).lower() for n in s["grade_names"]}
        if grade_labels.strip_sponsor_suffix(grade_name).lower() not in want:
            return False
    if s["categories"] and not (categories & set(s["categories"])):
        return False
    if s["formats"] and not (formats & set(s["formats"])):
        return False
    if s["team_ids"] and (not team_id or team_id not in s["team_ids"]):
        return False
    return True


@dataclass
class RuleContext:
    """Everything the screens need to draw a fixture's rules, and the save path
    needs to enforce them."""
    rules: list[dict] = field(default_factory=list)          # applying to this fixture
    player_flags: dict[str, list[dict]] = field(default_factory=dict)
    player_notes: dict[str, list[dict]] = field(default_factory=dict)
    team_rules: list[dict] = field(default_factory=list)     # judged against the whole XI
    age_as_at: date | None = None
    age_basis: dict = field(default_factory=dict)
    is_final: bool = False

    @property
    def active(self) -> bool:
        return bool(self.rules)

    def blocking_for(self, player_ids: list[str]) -> list[str]:
        """Reasons the given XI cannot be saved. Team rules are re-counted here
        rather than trusted from the browser — the board evaluates them live so
        a selector sees the cap fill up, but this is the copy that decides."""
        out: list[str] = []
        picked = set(player_ids)
        for pid in player_ids:
            for f in self.player_flags.get(pid, []):
                if f["severity"] == "block":
                    out.append(f"{f['player_name']}: {f['detail']}")
        for rule in self.team_rules:
            if rule["severity"] != "block":
                continue
            if rule["kind"] == "overseas":
                n = sum(1 for pid in picked if pid in rule["player_ids"])
                cap = rule["config"].get("max_in_xi", 1)
                if n > cap:
                    out.append(f"{rule['name']}: {n} overseas players named, {cap} allowed")
        return out


def _flag(rule: dict, code: str, detail: str, player_name: str, *,
          severity: str | None = None) -> dict:
    return {
        "rule_id": str(rule["id"]),
        "kind": rule["kind"],
        "name": rule["name"] or RULE_KINDS.get(rule["kind"], {}).get("label", rule["kind"]),
        "code": code,
        "severity": severity or clean_severity(rule["kind"], rule["severity"]),
        "detail": detail,
        "player_name": player_name,
    }


# ── Evaluation ───────────────────────────────────────────────────────────────

async def evaluate(db: AsyncSession, club, fx, players, *,
                   financial: dict[str, bool | None] | None = None,
                   trained: dict[str, bool | None] | None = None,
                   exclude_kinds: set[str] | None = None) -> RuleContext:
    """Judge a fixture's whole pool against the club's rules.

    ``financial`` and ``trained`` are the answers the selection pool has
    already worked out (BetterFees' balance, Net Manager's attendance, each
    overridden per player), passed in rather than recomputed so the badge and
    the rule can never disagree about the same player.

    A club with no rules costs one small query and returns an empty context —
    no extra work, and every screen then draws exactly what it drew before.
    """
    cfg = club_config(club)
    ctx = RuleContext(age_basis=cfg["age_basis"], is_final=fixture_is_final(fx))

    rows = await list_rules(db, club.id, enabled_only=True)
    if not rows:
        return ctx

    # What this fixture IS, so a rule can say whether it covers it.
    grade_name: str | None = None
    season_id = None
    season_year: int | None = None
    if fx.grade_id:
        got = (await db.execute(
            text("SELECT COALESCE(gr.display_name_override, gr.name), gr.season_id, s.year "
                 "FROM grades gr JOIN seasons s ON s.id = gr.season_id WHERE gr.id = :gid"),
            {"gid": fx.grade_id},
        )).first()
        if got:
            grade_name, season_id, season_year = got[0], got[1], got[2]
    if season_id is None:
        got = (await db.execute(
            text("SELECT id, year FROM seasons WHERE organisation_id = :org "
                 "ORDER BY year DESC NULLS LAST, name DESC LIMIT 1"),
            {"org": club.id},
        )).first()
        if got:
            season_id, season_year = got[0], got[1]
    if season_year is None and fx.played_on:
        season_year = season_year_for(fx.played_on, cfg["season_start_month"])

    # Fold the fixture's grade onto the name Manage Grades reads it under, so a
    # rule naming the grade that was KEPT in a merge still covers a fixture
    # arriving under one of the names merged into it. Only fetched when some
    # rule actually names a grade.
    if grade_name and any(clean_scope(r["scope"])["grade_names"] for r in rows):
        folded = (await grade_alias_map(db, club.id)).get(
            grade_labels.strip_sponsor_suffix(grade_name).lower())
        if folded:
            grade_name = folded

    categories: frozenset = frozenset()
    formats: frozenset = frozenset()
    if grade_name:
        categories = grade_labels.categories_for_name(
            await grade_labels.org_grade_category_sets(db, club.id), grade_name)
        formats = grade_labels.formats_for_name(
            await grade_labels.org_grade_format_sets(db, club.id), grade_name)

    team_id = str(fx.team_id) if fx.team_id else None
    applying = [
        r for r in rows
        if r["kind"] not in (exclude_kinds or ())
        and _scope_matches(r["scope"], grade_name=grade_name, categories=categories,
                           formats=formats, team_id=team_id, is_final=ctx.is_final)
    ]
    if not applying:
        return ctx

    kinds = {r["kind"] for r in applying}
    clearances = await clearances_for(db, club.id)
    by_id = {str(p.id): p for p in players}
    names = {pid: p.display_name for pid, p in by_id.items()}

    # The date ages are measured on for THIS fixture. One answer for the whole
    # board, so two players born a day apart can't be judged on two dates.
    age_basis = cfg["age_basis"]
    for r in applying:
        if r["kind"] in ("age", "bowling_workload") and (r["config"] or {}).get("as_at"):
            age_basis = clean_age_basis(r["config"]["as_at"])
            break
    ctx.age_basis = age_basis
    ctx.age_as_at = age_as_at(age_basis, fx.played_on, season_year, cfg["season_start_month"])

    # Facts each rule kind needs, fetched only when a rule of that kind is on.
    played: dict[str, list[dict]] = {}
    if kinds & {"finals_qualification", "grade_cap"}:
        played = await _appearances(db, club, season_id, season_year,
                                    cfg["season_start_month"], fx)
    sessions: dict[str, int] = {}
    session_count = 0
    if "training" in kinds:
        window = max((r["config"] or {}).get("window_days", 21)
                     for r in applying if r["kind"] == "training")
        sessions, session_count = await _net_sessions(db, club.id, fx.played_on or date.today(), window)
    registered: dict[str, bool] = {}
    if "registration" in kinds and season_id:
        registered = await _registrations(db, club.id, season_id)
    other_games: dict[str, int] = {}
    if "rest" in kinds and fx.played_on:
        window = max((r["config"] or {}).get("window_days", 2)
                     for r in applying if r["kind"] == "rest")
        other_games = await _nearby_commitments(db, club.id, fx, window)
    team_seqs: dict[str, int] = {}
    fixture_seq: int | None = None
    if kinds & {"grade_cap", "finals_qualification"}:
        team_seqs, fixture_seq = await _team_sequences(db, club.id, fx)

    for rule in applying:
        kind = rule["kind"]
        config = rule["config"] or {}
        severity = clean_severity(kind, rule["severity"])
        rule["severity"] = severity
        rule["summary"] = rule_summary(kind, config, age_basis)

        if kind == "overseas":
            ctx.team_rules.append({
                "id": str(rule["id"]),
                "kind": kind,
                "name": rule["name"] or RULE_KINDS[kind]["label"],
                "severity": severity,
                "config": config,
                "summary": rule["summary"],
                "player_ids": [pid for pid, p in by_id.items() if p.is_overseas],
            })
            continue

        for pid, p in by_id.items():
            cleared = clearances.get((str(rule["id"]), pid))
            if cleared and cleared["state"] == "cleared":
                if kind not in _INFO_ONLY:
                    ctx.player_notes.setdefault(pid, []).append({
                        "kind": kind, "rule_id": str(rule["id"]),
                        "detail": cleared["note"] or f"Cleared for {rule['summary'].lower()}",
                    })
                continue
            forced = bool(cleared and cleared["state"] == "blocked")

            finding = _judge(
                kind, config, p, pid,
                age_at=ctx.age_as_at, played=played.get(pid, []),
                sessions=sessions.get(pid, 0), session_count=session_count,
                registered=registered.get(pid), other_games=other_games.get(pid, 0),
                financial=(financial or {}).get(pid), trained=(trained or {}).get(pid),
                team_seqs=team_seqs, fixture_seq=fixture_seq, grade_name=grade_name,
                forced=forced, note=(cleared or {}).get("note"),
            )
            if not finding:
                continue
            detail, is_note = finding
            if is_note:
                ctx.player_notes.setdefault(pid, []).append(
                    {"kind": kind, "rule_id": str(rule["id"]), "detail": detail})
            else:
                ctx.player_flags.setdefault(pid, []).append(
                    _flag(rule, kind, detail, names.get(pid, "")))

    ctx.rules = [
        {
            "id": str(r["id"]),
            "kind": r["kind"],
            "name": r["name"] or RULE_KINDS.get(r["kind"], {}).get("label", r["kind"]),
            "severity": r["severity"],
            "summary": r["summary"],
        }
        for r in applying
    ]
    return ctx


def _judge(kind, config, p, pid, *, age_at, played, sessions, session_count,
           registered, other_games, financial, trained, team_seqs, fixture_seq,
           grade_name, forced, note) -> tuple[str, bool] | None:
    """One player against one rule. Returns (detail, is_note) or None.

    Silence is the answer whenever the club's own data cannot answer the
    question — no date of birth, no fees module and no tick, no registration
    row. A rule that flags everyone because nobody filled a field in gets
    switched off, and then it flags nothing at all.
    """
    if forced:
        return (note or "Marked ineligible for this rule", False)

    if kind == "age":
        age = player_age.age_on(p.date_of_birth, age_at)
        if age is None:
            return None
        lo, hi = config.get("min_age"), config.get("under_age")
        if lo is not None:
            ok = age > lo if config.get("min_op") == "gt" else age >= lo
            if not ok:
                return (f"{age} — the grade is {_min_phrase(lo, config.get('min_op'))}", False)
        if hi is not None:
            ok = age <= hi if config.get("max_op") == "lte" else age < hi
            if not ok:
                return (f"{age} — the grade is {_max_phrase(hi, config.get('max_op'))}", False)
        return None

    if kind == "bowling_workload":
        age = player_age.age_on(p.date_of_birth, age_at)
        if age is None:
            return None
        if config.get("applies_to") == "pace":
            if (p.bowling_type or "").upper() not in PACE_TYPES:
                return None
        elif not (p.bowling_type or p.bowling_action):
            return None
        rung = next((r for r in config.get("ladder", []) if age < r["under_age"]), None)
        if not rung:
            return None
        bits = []
        if rung.get("max_overs"):
            bits.append(f"{rung['max_overs']} overs")
        if rung.get("max_spell"):
            bits.append(f"{rung['max_spell']} per spell")
        if rung.get("rest_minutes"):
            bits.append(f"{rung['rest_minutes']} min rest")
        if config.get("max_share_of_overs"):
            share = int(round(config["max_share_of_overs"] * 100))
            bits.append(f"max {share}% of the innings")
        return (f"Under {rung['under_age']} — {', '.join(bits)}" if bits else
                f"Under {rung['under_age']}", True)

    if kind == "finals_qualification":
        counts = config.get("counts", "club")
        need = config.get("min_games", 1)
        if counts == "same_grade" and grade_name:
            key = grade_labels.strip_sponsor_suffix(grade_name).lower()
            got = sum(1 for g in played
                      if grade_labels.strip_sponsor_suffix(g["grade"] or "").lower() == key)
        elif counts == "this_or_higher" and fixture_seq is not None:
            # A game we can't rank counts. Telling a club its own captain hasn't
            # qualified because one appearance carried an unrecognised team name
            # is the worse error of the two.
            got = sum(1 for g in played
                      if (team_seqs.get((g["team"] or "").lower()) or fixture_seq) <= fixture_seq)
        else:
            got = len(played)
        if got >= need:
            return None
        return (f"{got} of {need} qualifying game{'s' if need != 1 else ''}", False)

    if kind == "grade_cap":
        if fixture_seq is None:
            return None
        limit = config.get("max_games_above", 2)
        above = config.get("above", "any")
        n = 0
        for g in played:
            seq = team_seqs.get((g["team"] or "").lower())
            if seq is None or seq >= fixture_seq:
                continue
            if above == "immediate" and seq != fixture_seq - 1:
                continue
            n += 1
        if n < limit:
            return None
        return (f"{n} games in a higher grade this season", False)

    if kind == "fees":
        if financial is False:
            return ("Owes the club money", False)
        return None

    if kind == "training":
        # The player's own override wins outright, exactly as it does for the
        # board's training badge. Then the real count for THIS rule's window —
        # which is not necessarily the badge's window. A club that ran no
        # sessions in the window can't answer, and says nothing.
        if p.trained_override is True:
            return None
        if p.trained_override is False:
            return ("Marked as not at training", False)
        if not session_count:
            return None
        need = config.get("min_sessions", 1)
        if sessions >= need:
            return None
        return (f"{sessions} of {need} net session{'s' if need != 1 else ''}", False)

    if kind == "registration":
        if registered is False:
            return ("Not registered for the season", False)
        return None

    if kind == "rest":
        allowed = config.get("max_games_in_window", 1)
        if 1 + other_games <= allowed:
            return None
        return (f"Named in {1 + other_games} matches inside "
                f"{config.get('window_days', 2)} days", False)

    if kind == "custom":
        if not config.get("require_tick"):
            return None
        return (config.get("note", "Not ticked off"), False)

    return None


# ── The club-wide view, for screens with no fixture in front of them ─────────

# A rule that only means something against a particular match. Left out of the
# roster and availability screens rather than answered badly there: "has this
# player qualified for a final" has no answer until you say which final.
_FIXTURE_ONLY_KINDS = {"finals_qualification", "grade_cap", "rest", "overseas"}


class _AnyFixture:
    """Stands in for "no particular match" on the roster and availability
    screens. Only the rules that hold whatever the fixture is — fees,
    registration, training, an age limit written across the whole club — can
    match it, because a rule scoped to a grade has no grade to compare with."""

    def __init__(self):
        self.id = uuid.uuid4()
        self.grade_id = None
        self.team_id = None
        self.played_on = date.today()
        self.round = None
        self.is_final = False


async def evaluate_club_wide(db: AsyncSession, club, players, *,
                             financial: dict[str, bool | None] | None = None,
                             trained: dict[str, bool | None] | None = None) -> RuleContext:
    """The club's rules as they stand for a player, with no match in mind."""
    return await evaluate(db, club, _AnyFixture(), players,
                          financial=financial, trained=trained,
                          exclude_kinds=_FIXTURE_ONLY_KINDS)


# ── The facts the rules are judged against ───────────────────────────────────

async def _appearances(db: AsyncSession, club, season_id, season_year,
                       start_month: int, fx) -> dict[str, list[dict]]:
    """Matches each player has played this season, from the scorecards AND the
    sides the club named.

    Both, because a final is picked the week after the last round and that
    round's scorecards may not have synced yet — counting only what has synced
    would tell a club its own captain hasn't qualified. Deduped on the DATE,
    which is what a synced game and the fixture it came from share, so a match
    counted from both sources counts once.

    Scoped through ``players.organisation_id``, not only the game's grade: a
    fixture between two synced clubs is ONE games row carrying both sides'
    appearances.
    """
    out: dict[str, dict[str, dict]] = {}
    as_of = fx.played_on or date.today()

    if season_id:
        rows = (await db.execute(
            text(
                "SELECT ga.player_id, g.played_at, gr.name, ga.team_name "
                "FROM game_appearances ga "
                "JOIN games g ON g.id = ga.game_id "
                "JOIN players p ON p.id = ga.player_id "
                "JOIN grades gr ON gr.id = g.grade_id "
                "WHERE p.organisation_id = :org AND gr.season_id = :season "
                "AND g.played_at IS NOT NULL AND g.played_at <= :as_of"
            ),
            {"org": club.id, "season": season_id, "as_of": as_of},
        )).fetchall()
        for pid, day, grade, team in rows:
            out.setdefault(str(pid), {})[day.isoformat()] = {
                "grade": grade, "team": team, "seq": None, "date": day,
            }

    if season_year is not None:
        lo, hi = season_window(season_year, start_month)
        rows = (await db.execute(
            text(
                "SELECT fl.player_id, f.played_on, "
                "COALESCE(gr.display_name_override, gr.name), COALESCE(t.name, f.label) "
                "FROM fixture_lineups fl "
                "JOIN fixtures f ON f.id = fl.fixture_id "
                "LEFT JOIN grades gr ON gr.id = f.grade_id "
                "LEFT JOIN teams t ON t.id = f.team_id "
                "WHERE fl.organisation_id = :org AND f.id <> :fid "
                "AND f.played_on BETWEEN :lo AND :hi AND f.played_on <= :as_of"
            ),
            {"org": club.id, "fid": fx.id, "lo": lo, "hi": min(hi, as_of), "as_of": as_of},
        )).fetchall()
        for pid, day, grade, team in rows:
            if not day:
                continue
            out.setdefault(str(pid), {}).setdefault(day.isoformat(), {
                "grade": grade, "team": team, "seq": None, "date": day,
            })

    return {pid: list(days.values()) for pid, days in out.items()}


async def _team_sequences(db: AsyncSession, org_id, fx) -> tuple[dict[str, int], int | None]:
    """Every team name (and short name) mapped to its seniority, plus this
    fixture's own. Seniority is what makes "a higher grade" answerable at all;
    a club that hasn't ordered its squads gets no answer, and the rule stays
    quiet rather than guessing."""
    rows = (await db.execute(
        text("SELECT id, name, short_name, sequence FROM teams WHERE organisation_id = :org"),
        {"org": org_id},
    )).fetchall()
    seqs: dict[str, int] = {}
    mine: int | None = None
    for tid, name, short, seq in rows:
        if not seq or seq <= 0:
            continue
        for label in (name, short):
            if label:
                seqs[label.strip().lower()] = seq
        if fx.team_id and str(tid) == str(fx.team_id):
            mine = seq
    return seqs, mine


async def _net_sessions(db: AsyncSession, org_id, as_of: date, window_days: int) -> tuple[dict[str, int], int]:
    """Sessions attended per player inside the window, and how many the club
    ran at all — the second is what separates "missed training" from "there was
    no training"."""
    since = as_of - timedelta(days=window_days)
    rows = (await db.execute(
        text("SELECT na.player_id, COUNT(DISTINCT ns.id) FROM net_attendance na "
             "JOIN net_sessions ns ON ns.id = na.session_id "
             "WHERE na.organisation_id = :org AND na.player_id IS NOT NULL "
             "AND ns.session_date BETWEEN :since AND :as_of GROUP BY na.player_id"),
        {"org": org_id, "since": since, "as_of": as_of},
    )).fetchall()
    total = (await db.execute(
        text("SELECT COUNT(*) FROM net_sessions WHERE organisation_id = :org "
             "AND session_date BETWEEN :since AND :as_of"),
        {"org": org_id, "since": since, "as_of": as_of},
    )).scalar() or 0
    return {str(pid): int(n) for pid, n in rows}, int(total)


async def _registrations(db: AsyncSession, org_id, season_id) -> dict[str, bool]:
    """Who the club has ticked as registered for the season. A player with no
    member row at all is absent, not False — we have not been told either way."""
    rows = (await db.execute(
        text("SELECT fm.player_id, fms.playhq_registered FROM fee_member_seasons fms "
             "JOIN fee_members fm ON fm.id = fms.member_id "
             "WHERE fm.organisation_id = :org AND fms.season_id = :season "
             "AND fm.player_id IS NOT NULL"),
        {"org": org_id, "season": season_id},
    )).fetchall()
    return {str(pid): bool(reg) for pid, reg in rows}


async def _nearby_commitments(db: AsyncSession, org_id, fx, window_days: int) -> dict[str, int]:
    """Other sides each player is already named in, within the window either
    side of this fixture. Read from named XIs, which is where a club's own
    intentions live — the same-day clash rule already covers the rest."""
    lo = fx.played_on - timedelta(days=window_days - 1)
    hi = fx.played_on + timedelta(days=window_days - 1)
    rows = (await db.execute(
        text("SELECT fl.player_id, COUNT(DISTINCT f.played_on) FROM fixture_lineups fl "
             "JOIN fixtures f ON f.id = fl.fixture_id "
             "WHERE fl.organisation_id = :org AND f.id <> :fid "
             "AND f.played_on BETWEEN :lo AND :hi GROUP BY fl.player_id"),
        {"org": org_id, "fid": fx.id, "lo": lo, "hi": hi},
    )).fetchall()
    return {str(pid): int(n) for pid, n in rows}
