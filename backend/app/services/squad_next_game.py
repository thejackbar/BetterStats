"""Which upcoming game a squad's availability is read and written against.

The Squads board used to answer every column with the club's first upcoming
date, whatever grade played on it. A club with a midweek T20 and a Saturday XI
squad therefore showed (and wrote) Saturday's players against the T20's date,
and kept doing so until the T20 was over.

A squad's next game is the earliest upcoming fixture that is its own:
  * the fixture names the squad (`team_id`), or
  * the fixture names no squad and sits in the squad's grade (`grade_id`).
A fixture that names a different squad is that squad's, even in the same grade.

Pure on purpose: it takes the entries `availability.upcoming_fixtures_by_date`
already builds (with `with_scope=True`) so the matrix and the check read one
definition.
"""
from __future__ import annotations

from typing import Iterable, Optional


def fixture_belongs_to_squad(f: dict, team_id: str, grade_id: Optional[str]) -> bool:
    """A fixture is a squad's own when it names the squad, or names no squad and
    sits in the squad's grade. One that names a different squad is that squad's,
    even in the same grade."""
    ft = f.get("team_id")
    if ft:
        return ft == team_id
    return bool(grade_id) and f.get("grade_id") == grade_id


def _next_entry(team_id: str, grade_id: Optional[str], fixtures: list[dict]) -> Optional[dict]:
    for f in fixtures:   # already in date order
        if fixture_belongs_to_squad(f, team_id, grade_id):
            return f
    return None


def _shape(f: dict, scope: str) -> dict:
    return {
        "date": f["date"],
        "fixture_id": f.get("id"),
        "opponent_name": f.get("opponent_name"),
        "label": f.get("label"),
        "home_away": f.get("home_away"),
        "scope": scope,
    }


def squad_next_games(by_date: dict[str, list[dict]], teams: Iterable[tuple[str, Optional[str]]]) -> dict[str, dict]:
    """{team_id: {date, fixture_id, opponent_name, label, home_away, scope}}.

    `teams` is (team_id, grade_id) pairs, ids as strings. `scope` says what the
    date means:
      'squad' - the squad's own next game
      'club'  - the squad has no grade and no fixture of its own, so there is
                nothing to tie it to: it reads the club's first date, as it
                always did, and the board says so
      'none'  - the squad has a grade and that grade has nothing upcoming:
                `date` is None and the board shows no availability for it
                rather than another grade's game
    """
    # One flat, date-ordered list; a two-day game counts once, on its first day.
    flat: list[dict] = []
    for d in sorted(by_date):
        for f in by_date[d]:
            if f.get("role") == "day2":
                continue
            flat.append({**f, "date": d})
    club_first = flat[0] if flat else None

    out: dict[str, dict] = {}
    for team_id, grade_id in teams:
        hit = _next_entry(team_id, grade_id, flat)
        if hit:
            out[team_id] = _shape(hit, "squad")
        elif not grade_id and club_first:
            out[team_id] = _shape(club_first, "club")
        else:
            out[team_id] = {
                "date": None, "fixture_id": None, "opponent_name": None,
                "label": None, "home_away": None, "scope": "none",
            }
    return out


def fixtures_for_player(
    by_date: dict[str, list[dict]],
    squads: Iterable[tuple[str, Optional[str]]],
    team_names: dict[str, str],
    grade_names: dict[str, str],
) -> dict[str, list[dict]]:
    """The self-service page's fixtures: what is on, where and when, and which
    games are the player's own.

    `by_date` entries are built with `with_scope=True, with_detail=True`;
    `squads` is the verified player's (team_id, grade_id) pairs. Each entry comes
    back without the internal `team_id` / `grade_id` (the page is unauthenticated)
    and with `team_name` (our side) and `mine`.
    A player in no squad gets `mine` False everywhere; the page then draws no
    emphasis rather than guessing one.
    """
    squads = list(squads)
    out: dict[str, list[dict]] = {}
    for d, entries in by_date.items():
        rows = []
        for f in entries:
            tid, gid = f.get("team_id"), f.get("grade_id")
            row = {k: v for k, v in f.items() if k not in ("team_id", "grade_id")}
            mine_squad = next((t for t, g in squads if fixture_belongs_to_squad(f, t, g)), None)
            # Our side: the team the fixture names, else the player's squad it
            # matched on (what they call it), else the grade.
            row["team_name"] = (
                (team_names.get(tid) if tid else None)
                or (team_names.get(mine_squad) if mine_squad else None)
                or (grade_names.get(gid) if gid else None)
            )
            row["mine"] = mine_squad is not None
            rows.append(row)
        out[d] = rows
    return out
