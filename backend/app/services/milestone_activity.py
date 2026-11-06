"""Who a grade milestone is still worth showing for, and what the Milestones filters read.

Asked for off a club whose Milestones page listed a player as one game short of
50 in 1st Grade when he had not played 1st Grade for twenty years. The grade
scan judged a player "active" on any season row at the club in the last three
years, which says nothing about WHICH grade he plays. So a 1st Grade tally from
2006 sat on the page for as long as he kept turning out in 3rd Grade.

Two rules, both applied to the UPCOMING list only (a reached milestone is
history and stays):

- **A GRADE THE PLAYER HAS GONE QUIET IN IS NOT IN REACH.** His last game in
  that grade must fall within :data:`ACTIVE_SEASON_YEARS` of this year, the same
  window "active at the club" already uses. A game with no date is not evidence
  of dormancy, so it keeps the row (rule 6: warn, do not refuse, where the data
  cannot answer).
- **A GRADE THE CLUB IS NOT FIELDING THIS SEASON IS NOT IN REACH.** There is no
  game coming up in a grade with no side, so "1 game to 50" in it is noise.
  "This season" is the club's newest season that holds any grade. A club with no
  season or no grades yet judges nothing, which keeps every row.

The same module carries the per-player facts the Milestones filter bar reads:
the season each player last played, and the kind of cricket they play (the
grade categories of the grades in that last season). Both are DERIVED ON READ,
never stored (rule 4).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql
from app.services.game_status import not_played_game_sql
from app.services.grade_labels import (
    categories_for_name, grade_alias_map, grade_key, org_grade_category_sets,
)
from app.services.season_resolve import season_start_year, season_year_for_date

# Current year and the two before it. Defined here (milestone_scan re-exports
# it) so the grade rules below and the career "active" rule cannot drift.
ACTIVE_SEASON_YEARS = 2

#: Age-group order for the filter, and the label each reads under on screen.
AGE_GROUP_ORDER = ("senior", "junior", "womens", "masters", "mixed")


def still_playing_from(today: datetime.date | None = None) -> datetime.date:
    """The earliest game date that still counts as "plays this grade"."""
    today = today or datetime.date.today()
    return datetime.date(today.year - ACTIVE_SEASON_YEARS, 1, 1)


def played_recently(last_played, today: datetime.date | None = None) -> bool:
    """Did the last game fall inside the active window? Unknown date: yes."""
    if last_played is None:
        return True
    d = last_played.date() if isinstance(last_played, datetime.datetime) else last_played
    return d >= still_playing_from(today)


def _start(name, year) -> int | None:
    """A season's starting year: its name first, then the year column."""
    return season_start_year(name or "") or year


@dataclass(frozen=True)
class GradeActivity:
    """Which grades the club has a side in this season."""

    #: The club's newest season (by starting year) that holds a grade, or None.
    season_start: int | None = None
    #: Canonical grade keys with a grade row in that season.
    fielded: frozenset = frozenset()
    aliases: dict = field(default_factory=dict)
    display_keys: dict = field(default_factory=dict)

    def key_of(self, name) -> str:
        """A grade's key: sponsor suffix off, merges folded, display name resolved."""
        k = grade_key(name)
        k = self.aliases.get(k, k)
        return self.display_keys.get(k, k)

    def is_fielded(self, name) -> bool:
        """Does the club have a side in this grade this season?

        True when it cannot be judged (no season, no grades, no name): showing a
        milestone nobody asked to hide is the smaller mistake.
        """
        if self.season_start is None or not self.fielded or not name:
            return True
        return self.key_of(name) in self.fielded


async def load_grade_activity(session: AsyncSession, org_id) -> GradeActivity:
    """The club's grades in its newest season. One read plus the merge map."""
    if not org_id:
        return GradeActivity()
    rows = (await session.execute(text(
        "SELECT s.name, s.year, gr.name, gr.display_name_override"
        " FROM seasons s JOIN grades gr ON gr.season_id = s.id"
        " WHERE s.organisation_id = CAST(:org AS uuid)"
    ), {"org": str(org_id)})).all()
    if not rows:
        return GradeActivity()
    aliases = await grade_alias_map(session, org_id)

    def canon(name):
        k = grade_key(name)
        return aliases.get(k, k)

    display_keys = {}
    for _sn, _sy, gname, shown in rows:
        if shown and str(shown).strip():
            display_keys.setdefault(grade_key(shown), canon(gname))
    dated = [(_start(sn, sy), gname) for sn, sy, gname, _shown in rows]
    dated = [(s, g) for s, g in dated if s is not None]
    if not dated:
        return GradeActivity(aliases=aliases, display_keys=display_keys)
    latest = max(s for s, _g in dated)
    fielded = frozenset(canon(g) for s, g in dated if s == latest and canon(g))
    return GradeActivity(season_start=latest, fielded=fielded,
                         aliases=aliases, display_keys=display_keys)


def upcoming_grade_ok(activity: GradeActivity, grade_name, last_played,
                      today: datetime.date | None = None) -> bool:
    """May an UPCOMING grade milestone be shown for this player and grade?"""
    return activity.is_fielded(grade_name) and played_recently(last_played, today)


def last_season_in_grade(season_rows, grade_name, activity: GradeActivity) -> int | None:
    """The newest season year a player has matches in ``grade_name``, from the
    profile's season grid (``get_player_team_breakdown['season_rows']``)."""
    want = activity.key_of(grade_name)
    best = None
    for sr in season_rows or ():
        y = sr.get("year")
        if y is None:
            continue
        for gname, n in (sr.get("grades") or {}).items():
            if n and activity.key_of(gname) == want and (best is None or y > best):
                best = y
    return best


def profile_grade_ok(activity: GradeActivity, season_rows, grade_name,
                     today: datetime.date | None = None) -> bool:
    """The profile's version of :func:`upcoming_grade_ok`. It has seasons, not dates."""
    if not activity.is_fielded(grade_name):
        return False
    y = last_season_in_grade(season_rows, grade_name, activity)
    if y is None:
        return True
    return y >= (today or datetime.date.today()).year - ACTIVE_SEASON_YEARS


async def annotate_players(session: AsyncSession, org_id, items: list[dict],
                           activity: GradeActivity | None = None) -> dict:
    """Add ``last_played_season`` and ``age_groups`` to each item, in place.

    ``last_played_season`` is the starting year of the newest season the player
    has any record in at THIS club: a scorecard they were named in, or a season
    row (an import or hand-entered season has no scorecard). ``age_groups`` are
    the grade categories of the grades they played in that season. A player with
    no scorecard to read reads as ``senior``, as an unclassified grade does
    everywhere else. Returns what the page needs to draw the filters:
    ``{"current_season", "age_groups"}`` where ``age_groups`` are those present.
    """
    pids = sorted({str(i["player_id"]) for i in items if i.get("player_id")})
    last: dict[str, int] = {}
    groups: dict[str, set] = {}
    if pids:
        for pid, sname, syear in (await session.execute(text("""
            SELECT pss.player_id::text, s.name, s.year
            FROM v_effective_player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = ANY(CAST(:pids AS uuid[]))
              AND s.organisation_id = CAST(:org AS uuid)
        """), {"pids": pids, "org": str(org_id)})).all():
            y = _start(sname, syear)
            if y is not None and y > last.get(pid, -1):
                last[pid] = y

        played = (await session.execute(text(f"""
            SELECT ga.player_id::text AS pid, gr.name AS grade_name,
                   MAX(g.played_at) AS last_played
            FROM game_appearances ga
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN games ag ON ag.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE ga.player_id = ANY(CAST(:pids AS uuid[]))
              AND {club_game_sql('g', 'org')}
              AND NOT {not_played_game_sql('ag')}
            GROUP BY ga.player_id, gr.name
        """), {"pids": pids, "org": str(org_id)})).mappings().all()
        by_player: dict[str, list] = {}
        for r in played:
            d = r["last_played"]
            if d is None:
                continue
            y = season_year_for_date(d.date() if isinstance(d, datetime.datetime) else d)
            by_player.setdefault(r["pid"], []).append((y, r["grade_name"]))
            if y is not None and y > last.get(r["pid"], -1):
                last[r["pid"]] = y
        if by_player:
            name_cats = await org_grade_category_sets(session, org_id)
            for pid, entries in by_player.items():
                newest = max(y for y, _n in entries)
                cats: set = set()
                for y, gname in entries:
                    if y == newest:
                        cats |= set(categories_for_name(name_cats, gname))
                groups[pid] = cats

    present: set = set()
    for i in items:
        pid = str(i.get("player_id") or "")
        i["last_played_season"] = last.get(pid)
        cats = groups.get(pid) or {"senior"}
        ordered = [c for c in AGE_GROUP_ORDER if c in cats]
        i["age_groups"] = ordered
        present.update(ordered)
    current = max(last.values()) if last else None
    club_now = (activity or await load_grade_activity(session, org_id)).season_start
    return {
        "current_season": club_now if club_now is not None else current,
        "age_groups": [c for c in AGE_GROUP_ORDER if c in present],
    }
