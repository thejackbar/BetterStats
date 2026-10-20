"""A club's milestone increments, one grade at a time.

``services/milestone_rules`` holds the ladder maths and the club-wide
``Scheme``. This module adds the one thing it cannot: a club that wants smaller
increments for A Grade and larger ones for everyone else.

**What a grade's increments cover.** The milestones that belong to a grade:
"100 games in A Grade", "1,000 runs in A Grade", the Records page with a grade
picked, and the grade notices. A player's CAREER milestones (the stored
``milestones`` rows, the dashboard, the profile's career list) have no grade
and keep the club's own scheme. A career is not one grade's, and a player who
moves between grades must not change ladder halfway up it.

**A grade is its name key.** Grades are per-season rows, so a setting keyed on
a grade id would restart every season. The key is
``grade_labels.grade_key`` of the name, folded through the club's active grade
merges, which is the same key ``club_grades`` and the Records grade filter use.
A merged-away spelling therefore reads as the grade it was merged into.

**Nothing set is nothing changed.** A club with no rows gets a book whose
``for_grade`` is the club scheme for every name, and loading it costs one cheap
read.

Every step in a row is optional: NULL follows the club's setting for that stat,
so "A Grade: runs every 250" leaves wickets, matches and catches on the club's.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text

from app.services.grade_labels import grade_alias_map, grade_key, strip_sponsor_suffix
from app.services.milestone_rules import (
    STATS, Scheme, is_valid_step, load_scheme,
)

#: Seasons back from this year that still count as a grade "in play" on the
#: settings screen. Older grades stay settable, behind a toggle.
ACTIVE_GRADE_YEARS = 2


@dataclass(frozen=True)
class SchemeBook:
    """The club's scheme plus the grades that have increments of their own."""

    club: Scheme
    #: grade key -> that grade's effective scheme (club's, with its own steps over).
    by_grade: dict = field(default_factory=dict)
    #: display name key -> grade key, for names the club typed over a raw one.
    display_keys: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)

    def for_grade(self, name) -> Scheme:
        """The scheme for a grade-level milestone in the grade called ``name``.

        Takes the raw feed name, the club's display name, or either with a
        sponsor suffix; a name the club never customised is the club's scheme.
        """
        if not self.by_grade or not name:
            return self.club
        key = grade_key(name)
        key = self.aliases.get(key, key)
        hit = self.by_grade.get(key)
        if hit is not None:
            return hit
        shown = self.display_keys.get(key)
        if shown is not None:
            return self.by_grade.get(shown, self.club)
        return self.club

    def smallest_step(self, stat: str) -> int:
        """The smallest step any grade (or the club) uses for ``stat``.

        For a query that pre-filters on "has at least one rung" before it knows
        which grade a row is in.
        """
        steps = [self.club.step_for(stat)]
        steps.extend(s.step_for(stat) for s in self.by_grade.values())
        return min(steps)


def _override_scheme(club: Scheme, row) -> Scheme:
    """The club's scheme with a row's own steps over it. An invalid step is ignored."""
    steps = {}
    for stat, value in zip(STATS, row):
        if value is not None and is_valid_step(stat, value):
            steps[stat] = value
    return club.with_steps(**steps)


async def load_book(db, org_id) -> SchemeBook:
    """The club's scheme and every grade override, for one request.

    Two reads when the club has no overrides (the scheme and the table), four
    when it has. Never raises on an unset club: a missing org is the default.
    """
    club = await load_scheme(db, org_id)
    if not org_id:
        return SchemeBook(club=club)
    rows = (await db.execute(
        text("SELECT grade_key, runs_step, wickets_step, matches_step, catches_step"
             " FROM milestone_grade_schemes WHERE organisation_id = CAST(:org AS uuid)"),
        {"org": str(org_id)},
    )).all()
    if not rows:
        return SchemeBook(club=club)

    aliases = await grade_alias_map(db, org_id)
    by_grade: dict[str, Scheme] = {}
    # A key saved under a spelling that has since been merged away reads as the
    # grade it was merged into; where both have a row, the survivor's wins.
    for r in sorted(rows, key=lambda r: aliases.get(r[0], r[0]) != r[0]):
        key = aliases.get(r[0], r[0])
        by_grade.setdefault(key, _override_scheme(club, r[1:]))

    display_keys: dict[str, str] = {}
    for name, shown in (await db.execute(
        text("SELECT gr.name, gr.display_name_override FROM grades gr"
             " JOIN seasons s ON s.id = gr.season_id"
             " WHERE s.organisation_id = CAST(:org AS uuid)"
             " AND gr.display_name_override IS NOT NULL"),
        {"org": str(org_id)},
    )).all():
        raw_key = aliases.get(grade_key(name), grade_key(name))
        display_keys.setdefault(grade_key(shown), raw_key)
    return SchemeBook(club=club, by_grade=by_grade, display_keys=display_keys,
                      aliases=aliases)


async def club_grade_choices(db, org_id, *, this_year: int) -> list[dict]:
    """The grades a club can give increments to, newest first.

    One entry per grade key. ``name`` is what the club reads: its own display
    name when it set one, else the newest season's name without the sponsor
    suffix. ``active`` is a season row in the last ``ACTIVE_GRADE_YEARS`` years
    (a row with no year counts, as everywhere else); the screen hides the
    rest behind a toggle. A grade with saved increments that no longer has a
    season row is still listed, so the club can see and clear it.
    """
    aliases = await grade_alias_map(db, org_id)
    rows = (await db.execute(
        text("SELECT gr.name, gr.display_name_override, s.year"
             " FROM grades gr JOIN seasons s ON s.id = gr.season_id"
             " WHERE s.organisation_id = CAST(:org AS uuid)"),
        {"org": str(org_id)},
    )).all()
    cutoff = this_year - ACTIVE_GRADE_YEARS
    grades: dict[str, dict] = {}
    for name, shown, year in rows:
        raw_key = grade_key(name)
        key = aliases.get(raw_key, raw_key)
        if not key:
            continue
        g = grades.setdefault(key, {"key": key, "name": None, "last_year": None,
                                    "active": False, "_rank": None})
        rank = (year if year is not None else 9999, raw_key == key)
        if g["_rank"] is None or rank > g["_rank"]:
            g["_rank"] = rank
            g["name"] = (shown or "").strip() or strip_sponsor_suffix(name)
        if year is not None and (g["last_year"] is None or year > g["last_year"]):
            g["last_year"] = year
        if year is None or year >= cutoff:
            g["active"] = True
    saved = (await db.execute(
        text("SELECT grade_key, grade_name, runs_step, wickets_step, matches_step, catches_step"
             " FROM milestone_grade_schemes WHERE organisation_id = CAST(:org AS uuid)"),
        {"org": str(org_id)},
    )).all()
    for r in saved:
        key = aliases.get(r[0], r[0])
        g = grades.setdefault(key, {"key": key, "name": r[1] or key, "last_year": None,
                                    "active": False, "_rank": None})
        # Survivor's row wins over a merged-away spelling's, as in load_book.
        if "steps" in g and r[0] != key:
            continue
        g["steps"] = dict(zip(STATS, r[2:]))
    out = []
    for g in grades.values():
        g.pop("_rank", None)
        g.setdefault("steps", {s: None for s in STATS})
        out.append(g)
    out.sort(key=lambda g: (-(g["last_year"] or 0), (g["name"] or "").lower()))
    return out


async def resolve_grade(db, org_id, name, *, this_year: int) -> dict | None:
    """The grade choice whose key, name or display name is ``name``, else None."""
    if not name or not str(name).strip():
        return None
    wanted = grade_key(name)
    aliases = await grade_alias_map(db, org_id)
    wanted = aliases.get(wanted, wanted)
    choices = await club_grade_choices(db, org_id, this_year=this_year)
    for c in choices:
        if c["key"] == wanted:
            return c
    for c in choices:
        if grade_key(c["name"]) == grade_key(name):
            return c
    return None


async def save_grade_steps(db, org_id, choice: dict, steps: dict) -> dict:
    """Write the given steps for one grade; a stat not in ``steps`` is left alone.

    ``steps`` maps stat -> int, or None to follow the club again. The caller has
    validated every value. The row is kept even when every step is None: an
    empty row reads exactly like no row.
    """
    current = dict(choice.get("steps") or {s: None for s in STATS})
    current.update(steps)
    await db.execute(
        text("""
            INSERT INTO milestone_grade_schemes
                (organisation_id, grade_key, grade_name,
                 runs_step, wickets_step, matches_step, catches_step, updated_at)
            VALUES (CAST(:org AS uuid), :key, :name, :r, :w, :m, :c, NOW())
            ON CONFLICT (organisation_id, grade_key) DO UPDATE SET
                grade_name = EXCLUDED.grade_name,
                runs_step = EXCLUDED.runs_step, wickets_step = EXCLUDED.wickets_step,
                matches_step = EXCLUDED.matches_step, catches_step = EXCLUDED.catches_step,
                updated_at = NOW()
        """),
        {"org": str(org_id), "key": choice["key"], "name": choice["name"],
         "r": current["runs"], "w": current["wickets"],
         "m": current["matches"], "c": current["catches"]},
    )
    return current
