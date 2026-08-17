"""Which grade categories count towards a club's stats.

A club's grades already carry a category — Senior / Junior / Women's / Masters /
Mixed (``grades.category``, migration 123, guessed by
``grade_labels.suggest_category`` until an admin confirms it on /admin/grades).
Until now nothing in the stats layer read it: a 14-year-old's Under-14 runs and
a first-grade century landed in one career total, and there was no way to pull
them apart.

This module is the one place that turns "which categories should count" into
something SQL can use, and every stats surface routes through it.

**It works by EXCLUSION, and that is load-bearing.** The obvious shape is an
include-list — "give me the senior grade ids and filter to those" — and it is
wrong twice over:

- A manual game may legitimately have no grade at all (Grade is optional on
  Upload Scorecard, see the v8.76.1 note), and a career-scope import residual
  has no ``grade_id`` either. An include-list drops both; an exclude-list keeps
  them, because a row we cannot categorise is not a row we know to be junior.
- An empty exclusion set emits **no SQL clause at all**, so a club with no
  junior grades runs byte-for-byte the queries it ran before. That is what
  makes shipping a default that excludes junior safe for the ~50 senior-only
  clubs: nothing about their numbers can move, because their queries do not
  change.

The category is resolved per grade NAME, not per row: a category attaches to a
grade name club-wide across every season (the same rule
``admin.py::list_grades_with_stats`` and ``grade_labels.org_grade_categories``
already use), and it may be an unconfirmed suggestion rather than a stored
column — so it cannot go straight into a WHERE clause. We resolve names to
categories in Python and hand SQL a plain list of grade ids, which is the same
approach the public lineups endpoint takes for its own category filter.
"""
from typing import Iterable, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.grade_labels import (
    GRADE_CATEGORIES,
    MATCH_FORMATS,
    categories_for_name,
    formats_for_name,
    normalise_category,
    normalise_formats,
    org_grade_category_sets,
    org_grade_format_sets,
)

# What counts when nobody has said otherwise: everything except junior.
#
# Junior is the split clubs actually ask for — an Under-14 season sitting inside
# a senior career average is the reported problem. Women's, Masters and Mixed
# each get their own toggle, but they stay ON by default: a women's grade is
# senior cricket, and defaulting it off would empty out the stats of a club whose
# whole programme is women's.
DEFAULT_CATEGORIES: tuple[str, ...] = tuple(c for c in GRADE_CATEGORIES if c != "junior")

# The wire value meaning "no filter at all" — every category, including junior.
ALL = "all"


def normalise_categories(value) -> Optional[tuple[str, ...]]:
    """Coerce a category selection to a sorted tuple of valid keys.

    Accepts the comma-separated string the API takes on the wire, a list (what
    the club-default column stores), or None. Returns None for "not specified",
    which callers read as "use the club's default" — distinct from an empty
    selection, which is a real (if useless) choice and comes back as ().
    """
    if value is None:
        return None
    if isinstance(value, str):
        raw: Iterable = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        return None
    if ALL in {str(v).strip().lower() for v in raw}:
        return tuple(GRADE_CATEGORIES)
    return tuple(sorted({c for c in (normalise_category(v) for v in raw) if c}))


def primary_category(categories) -> str:
    """The one-answer view of a grade's categories.

    Same precedence ``grade_labels.suggest_category`` uses — junior first, so a
    girls' age-group side reads as a junior grade — and the same answer the
    single ``grades.category`` column holds, since that is written as the first
    entry in canonical order.
    """
    cats = set(categories or ())
    for key in ("junior", "womens", "masters", "mixed"):
        if key in cats:
            return key
    return "senior"


async def club_default_categories(session: AsyncSession, org_id) -> tuple[str, ...]:
    """The club's own default selection, else the platform default.

    ``organisations.stats_grade_categories`` is NULL for every club until an
    admin sets it, so upgrading changes nothing about where the default comes
    from — only what the default itself is.
    """
    if not org_id:
        return DEFAULT_CATEGORIES
    res = await session.execute(
        text("SELECT stats_grade_categories FROM organisations WHERE id = CAST(:org AS UUID)"),
        {"org": str(org_id)},
    )
    row = res.first()
    stored = normalise_categories(row[0]) if row else None
    # An empty stored list would hide every stat the club has. Treat it as unset
    # rather than honouring a selection nobody can have meant.
    return stored if stored else DEFAULT_CATEGORIES


class GradeScope:
    """The resolved answer: which grade ids to leave out, and of what.

    ``excluded_ids`` empty means "nothing to do" — every caller checks
    :attr:`active` and skips emitting SQL entirely, which is what keeps a
    senior-only club's queries identical to what they were before this shipped.

    Both axes — the grade TYPE (men's / juniors / women's / masters) and the
    FORMAT played (two day / one day / T20) — resolve into this one object and
    one exclusion list, so adding the second filter changed no query. A grade
    failing either test is simply out of scope.
    """

    __slots__ = (
        "categories", "formats", "excluded_ids",
        "excluded_categories", "excluded_formats", "param",
    )

    def __init__(
        self,
        categories: Sequence[str],
        excluded_ids: Sequence,
        excluded_categories: Sequence[str],
        param: str = "gs_excluded_grade_ids",
        formats: Optional[Sequence[str]] = None,
        excluded_formats: Sequence[str] = (),
    ):
        self.categories = tuple(categories)
        self.formats = tuple(formats) if formats is not None else None
        self.excluded_ids = list(excluded_ids)
        self.excluded_categories = tuple(excluded_categories)
        self.excluded_formats = tuple(excluded_formats)
        self.param = param

    @property
    def active(self) -> bool:
        return bool(self.excluded_ids)

    def clause(self, column: str = "g.grade_id") -> str:
        """A WHERE fragment (leading AND) excluding the out-of-scope grades.

        ``column IS NULL OR NOT (...)`` rather than a bare ``NOT (...)``: with a
        NULL grade_id the ANY(...) comparison is NULL and NOT NULL is NULL, so a
        grade-less manual game would be dropped by a filter that has no opinion
        about it.
        """
        if not self.active:
            return ""
        return f" AND ({column} IS NULL OR NOT ({column} = ANY(:{self.param})))"

    def bind(self, params: dict) -> dict:
        """Add this scope's bind parameter to a params dict, in place."""
        if self.active:
            params[self.param] = self.excluded_ids
        return params

    def as_meta(self) -> dict:
        """What the API reports back so a page can label a filtered figure."""
        return {
            "categories": list(self.categories),
            "excluded_categories": list(self.excluded_categories),
            "formats": list(self.formats) if self.formats is not None else None,
            "excluded_formats": list(self.excluded_formats),
            "active": self.active,
        }


async def resolve_scope(
    session: AsyncSession,
    org_id,
    categories=None,
    *,
    formats=None,
    param: str = "gs_excluded_grade_ids",
) -> GradeScope:
    """Turn a category and/or format selection into the grade ids it leaves out.

    ``categories`` None falls back to the club's default. A selection covering
    every category (or an org with no grades outside it) yields an inactive
    scope, and therefore no SQL change at all.

    ``formats`` None means no format filter at all, which is the default — a
    format is something someone asks for, never something applied on their
    behalf. The two axes are independent: a grade has to pass both to stay in.

    **The two axes fail differently on an unclassified grade, deliberately.** A
    grade always has a category (the name suggestion falls back to men's
    senior), so the category test always has something to judge. A grade's
    format is frequently unknowable — most names say nothing and older games
    carry no ``match_format`` — so a grade we cannot place is left OUT of an
    explicit format filter rather than swept in. Asking for T20 and being shown
    every grade the club has ever run is worse than being shown the ones we can
    actually vouch for, and the Grades screen is where a club fills the gap.
    """
    # An explicit selection is an INCLUSION ("show me the women's grades") and
    # matches on any of a grade's categories. The club default is an EXCLUSION
    # ("don't count juniors") and matches on the grade's primary category only,
    # which is exactly what it did before grades could carry more than one — so
    # a Girls Under 16 grade stays out of a default that leaves junior out,
    # rather than sneaking back in on its women's half, while someone asking for
    # women's still finds it.
    explicit = normalise_categories(categories) is not None
    wanted = normalise_categories(categories)
    if wanted is None:
        wanted = await club_default_categories(session, org_id)
    wanted_formats = normalise_formats(formats)
    if wanted_formats is not None and set(wanted_formats) >= set(MATCH_FORMATS):
        # "every format" is the same question as "no format filter", and asking
        # it as a filter would needlessly drop the grades we can't classify.
        wanted_formats = None

    category_filter = set(wanted) < set(GRADE_CATEGORIES)
    if not org_id or (not category_filter and wanted_formats is None):
        return GradeScope(wanted, [], [], param, formats=wanted_formats)

    name_categories = await org_grade_category_sets(session, org_id)
    name_formats = (
        await org_grade_format_sets(session, org_id)
        if wanted_formats is not None else {}
    )
    res = await session.execute(
        text(
            "SELECT gr.id, gr.name FROM grades gr "
            "JOIN seasons s ON s.id = gr.season_id "
            "WHERE s.organisation_id = CAST(:org AS UUID)"
        ),
        {"org": str(org_id)},
    )
    excluded_ids = []
    excluded_categories = set()
    excluded_formats = set()
    for grade_id, name in res.fetchall():
        cats = categories_for_name(name_categories, name)
        # A grade carrying several categories is in scope if ANY of them is
        # wanted: a Girls Under 14 grade belongs to a club's juniors AND to its
        # women's cricket, and asking for either should find it. Under the
        # default that collapses to the primary category — see `explicit` above.
        judged = cats if explicit else {primary_category(cats)}
        if category_filter and not (judged & set(wanted)):
            excluded_ids.append(grade_id)
            excluded_categories.update(cats)
            continue
        if wanted_formats is not None:
            fmts = formats_for_name(name_formats, name)
            if not (fmts & set(wanted_formats)):
                excluded_ids.append(grade_id)
                excluded_formats.update(fmts)
    return GradeScope(
        wanted,
        excluded_ids,
        tuple(c for c in GRADE_CATEGORIES if c in excluded_categories),
        param,
        formats=wanted_formats,
        excluded_formats=tuple(f for f in MATCH_FORMATS if f in excluded_formats),
    )


async def player_categories(session: AsyncSession, player_id, org_id) -> set[str]:
    """The grade categories a player has actually turned out in.

    Reads the grades behind their per-game rows and any grade-attributable
    aggregate residual. A career-level residual carries no grade and so says
    nothing about categories — it is left out here rather than counted as
    senior, since it is equally likely to be junior.
    """
    if not player_id or not org_id:
        return set()
    res = await session.execute(
        text(
            """
            SELECT DISTINCT gr.name
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = CAST(:org AS UUID)
              AND (
                EXISTS (
                    SELECT 1 FROM v_effective_games g
                    WHERE g.grade_id = gr.id AND (
                        EXISTS (SELECT 1 FROM v_effective_batting_innings bi
                                WHERE bi.game_id = g.id AND bi.player_id = CAST(:pid AS UUID))
                     OR EXISTS (SELECT 1 FROM v_effective_bowling_spells bs
                                WHERE bs.game_id = g.id AND bs.player_id = CAST(:pid AS UUID))
                     OR EXISTS (SELECT 1 FROM v_effective_fielding_stats fs
                                WHERE fs.game_id = g.id AND fs.player_id = CAST(:pid AS UUID))
                     OR EXISTS (SELECT 1 FROM game_appearances ga
                                WHERE ga.game_id = g.id AND ga.player_id = CAST(:pid AS UUID))
                    )
                )
                OR EXISTS (
                    SELECT 1 FROM v_effective_player_season_stats pss
                    WHERE pss.player_id = CAST(:pid AS UUID) AND pss.grade_id = gr.id
                )
              )
            """
        ),
        {"pid": str(player_id), "org": str(org_id)},
    )
    names = await org_grade_category_sets(session, org_id)
    played: set[str] = set()
    for row in res.fetchall():
        played |= categories_for_name(names, row[0])
    return played


async def resolve_scope_for_player(
    session: AsyncSession,
    org_id,
    player_id,
    categories=None,
    *,
    auto_widen: bool = True,
    param: str = "gs_excluded_grade_ids",
) -> tuple[GradeScope, bool]:
    """A scope for one player's own page, widened if the default would empty it.

    A junior who has never played a senior game would otherwise open on a page of
    zeroes, which reads as broken rather than as a filter doing its job. When the
    club's default leaves out every category this player has actually played, the
    categories they DID play are added back and the caller is told, so the page
    can say why it is showing junior figures.

    Only ever applies to the default. An explicit `categories` selection is a
    choice someone made and is honoured even when it comes back empty — otherwise
    switching juniors off for a junior-only player would silently switch them on
    again, and the toggle would look broken instead.
    """
    explicit = normalise_categories(categories) is not None
    scope = await resolve_scope(session, org_id, categories, param=param)
    if explicit or not auto_widen or not scope.active:
        return scope, False
    played = await player_categories(session, player_id, org_id)
    if not played or played & set(scope.categories):
        return scope, False
    widened = await resolve_scope(
        session, org_id, sorted(set(scope.categories) | played), param=param
    )
    return widened, True


async def org_available_categories(session: AsyncSession, org_id) -> list[str]:
    """The categories this club's grades actually fall into, in canonical order.

    A club with no Masters grade should not be offered a Masters toggle — the
    same rule the lineups endpoint's own `categories` field follows.
    """
    if not org_id:
        return []
    name_categories = await org_grade_category_sets(session, org_id)
    present: set[str] = set()
    for cats in name_categories.values():
        present |= cats
    return [c for c in GRADE_CATEGORIES if c in present]


async def org_available_formats(session: AsyncSession, org_id) -> list[str]:
    """The formats this club's grades actually play, in canonical order.

    Same rule as :func:`org_available_categories` — a club that has never played
    a two-day game should not be offered a Two Day filter. Empty when nothing
    can be classified at all, which is the honest answer for a club whose games
    predate ``games.match_format`` being written and whose grade names say
    nothing; the filter then simply doesn't render.
    """
    if not org_id:
        return []
    name_formats = await org_grade_format_sets(session, org_id)
    present: set[str] = set()
    for fmts in name_formats.values():
        present |= fmts
    return [f for f in MATCH_FORMATS if f in present]
