"""Shared SQL fragments for the BetterIQ global Season + Team filter.

The filter sends ONE representative season-row id, but a single real cricket
season ("2024/25") is frequently stored as several ``seasons`` rows: the
MyCricket and PlayHQ feeds give the same year different season ids, and separate
competitions get their own rows. Scoping on one row shows only a slice of the
year, so we expand a picked season to every row in the same org that shares its
year (falling back to the one row when the year is unknown, so an undated row is
never widened to the whole table). Grades are matched by NAME because the
per-club / per-season grade ids all collapse to one competition grade.

Both builders read the already-bound parameter ``:season`` (a season-row id) and,
for the grade variant, ``:grade`` (a grade NAME — or several names joined with
``||``, the multi-grade filter's wire format; a name never contains ``||``, so a
single name and a multi-select read through the same parameter). Callers bind
these today.
"""
from __future__ import annotations

import contextvars
import re
import uuid as _uuid
from typing import Optional

# ── The Grade Type / Match Type scope ────────────────────────────────────────
# BetterIQ was the last stats surface with no ``GradeScope`` (migration 259):
# no way to ask it for the T20s or the women's grades, and its figures counted
# every grade whatever the club had set, so a club that leaves juniors out saw
# BetterIQ disagree with its own Leaderboard.
#
# The scope rides in a ContextVar rather than being threaded through ~30 query
# builders and every one of their ``execute`` calls. Two reasons, and the
# second is the load-bearing one:
#
#  * IQ has no shared context dict to hang it on the way StatLab does, and
#    ``iq_team`` already carries its cross-season filter exactly this way
#    (``_RANGE_SEASONS``), so this is the file's own established pattern
#    rather than a new one.
#  * ``GradeScope.clause()`` emits ``:param`` references that every caller
#    then has to bind. Threading a bind through thirty-odd execute sites is
#    how one of them quietly ends up without it and the filter reads as
#    working while doing nothing there. Rendering the clause with its values
#    INLINED instead means every existing execute call keeps working
#    untouched — the same trade ``_RANGE_SEASONS`` already makes when it
#    inlines season ids as ``'…'::uuid`` literals.
#
# Inlining is safe here because none of the values come from a browser: the
# excluded grade ids are UUIDs read out of our own ``grades`` table and the
# formats are members of a fixed vocabulary. Both are re-validated below
# anyway, and anything that doesn't parse is dropped rather than interpolated.
_SCOPE: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "iq_grade_scope", default=None
)
# Where the format half should read each fixture's own ``match_format`` from.
# Per-query, because a query's games alias is its own business (``g``, ``gsf``,
# ``ge`` …) and format is a per-FIXTURE fact — a grade that plays both a
# one-day and a two-day season would otherwise file every game under one.
_GAME_ALIAS: contextvars.ContextVar[str] = contextvars.ContextVar(
    "iq_scope_game_alias", default="g"
)

_FORMAT_TOKEN = re.compile(r"^[a-z0-9_]+$")


def set_scope(scope):
    """Make ``scope`` the active Grade Type / Match Type filter. Returns a
    token for :func:`reset_scope`."""
    return _SCOPE.set(scope)


def reset_scope(token) -> None:
    _SCOPE.reset(token)


def active_scope():
    """The scope in force, or None when no filter is applied."""
    scope = _SCOPE.get()
    return scope if scope is not None and getattr(scope, "active", False) else None


def _sql_literal(value) -> Optional[str]:
    """A bound value as an inlinable SQL literal, or None if it can't be.

    Only two shapes ever reach here — a list of grade UUIDs and a list of
    format tokens — and anything else returns None so the caller drops the
    clause rather than interpolating something it doesn't understand.
    """
    if not isinstance(value, (list, tuple)):
        return None
    if not value:
        # An empty ANY(...) is legal but pointless; the caller drops it.
        return None
    parts = []
    for item in value:
        try:
            parts.append(f"'{_uuid.UUID(str(item))}'::uuid")
            continue
        except (ValueError, TypeError, AttributeError):
            pass
        token = str(item).strip().lower()
        if not _FORMAT_TOKEN.match(token):
            return None
        parts.append(f"'{token}'")
    return "ARRAY[" + ", ".join(parts) + "]"


def _inline(sql: str, params: dict) -> Optional[str]:
    """``sql`` with each ``:param`` replaced by its literal value.

    ``GradeScope`` stays the single definition of what the filter MEANS —
    this only changes how its clause is delivered. Longest parameter name
    first, so ``:x_formats`` isn't half-eaten by a substitution for ``:x``.
    """
    for key in sorted(params, key=len, reverse=True):
        literal = _sql_literal(params[key])
        if literal is None:
            return None
        sql = sql.replace(f":{key}", literal)
    # A leftover ``:name`` means a parameter we were never given a value for,
    # and an unbound parameter in an inlined fragment fails at execute time.
    if re.search(r"(?<![:\w]):[a-z_][a-z0-9_]*", sql):
        return None
    return sql


def scope_clause(grade_column: str = "gr.id", kind: str = "game",
                 game_alias: Optional[str] = None) -> str:
    """The active scope as a self-contained ``AND …`` fragment, or ''.

    ``kind`` carries ``GradeScope``'s own meaning:

    - ``'game'``   the row is a fixture, so format is read per fixture off
                   ``<game_alias>.match_format``.
    - ``'aggregate'`` a ``player_season_stats`` row, which has no game behind
                   it and so no format at all — under a Match Type filter it
                   drops out rather than being counted as whichever format is
                   being asked for.
    - ``'grade'``  a grade listing with no game in the query.
    """
    scope = active_scope()
    if scope is None:
        return ""
    params: dict = {}
    scope.bind(params)
    sql = scope.clause(grade_column, kind, game_alias=game_alias or _GAME_ALIAS.get())
    return _inline(sql, params) or ""


def scope_meta() -> dict:
    """What the active scope covers, for a page that has to label a filtered
    figure. Inactive reads as an empty scope rather than nothing at all, so a
    caller can render the same shape either way."""
    scope = _SCOPE.get()
    if scope is None:
        return {"categories": [], "excluded_categories": [], "formats": None,
                "active": False, "category_active": False, "format_active": False}
    return scope.as_meta()


# Every sibling row of :season for the same org/year (or just :season when the
# year is NULL). s0 is the picked row; s2 ranges over the org's season rows.
_SEASON_YEAR_SET = (
    "(SELECT s2.id FROM seasons s2 "
    "JOIN seasons s0 ON s0.id = CAST(:season AS UUID) "
    "WHERE s2.organisation_id = s0.organisation_id "
    "AND (s2.year = s0.year OR (s0.year IS NULL AND s2.id = s0.id)))"
)


def season_member_clause(column: str, season_id) -> str:
    """``AND <column> IN (<rows of :season's year>)`` — or '' when no season set.

    For a non-grade season column, e.g. ``pss.season_id``."""
    return f"AND {column} IN {_SEASON_YEAR_SET}" if season_id else ""


# The year set PLUS every OTHER club's sibling row of the same CA season —
# per-club season rows minted for a cross-club collision share `grassroots_id`
# (the raw CA season GUID), so this is how a shared game the OPPONENT synced
# first (whose `season_id` resolves to THEIR season row, migration 167's note)
# still matches OUR season filter. Mirrors aggregations._club_results.
_SEASON_YEAR_SET_CROSS = (
    "(SELECT s5.id FROM seasons s5 "
    f"WHERE s5.id IN {_SEASON_YEAR_SET} "
    "OR (s5.grassroots_id IS NOT NULL AND s5.grassroots_id IN "
    f"(SELECT s6.grassroots_id FROM seasons s6 WHERE s6.id IN {_SEASON_YEAR_SET} "
    "AND s6.grassroots_id IS NOT NULL)))"
)


def season_member_clause_cross_club(column: str, season_id) -> str:
    """``season_member_clause`` for a GAME's season column: also matches another
    club's sibling row of the same CA season, so an opponent-first-synced shared
    game isn't dropped by our season filter."""
    return f"AND {column} IN {_SEASON_YEAR_SET_CROSS}" if season_id else ""


def season_ids_cross_club(in_list: str, column: str = "g.season_id") -> str:
    """Compare-mode variant: ``column`` matches an explicit inlined id list OR a
    cross-club sibling (shared ``grassroots_id``) of any id in it."""
    return (
        f"AND ({column} IN ({in_list}) OR {column} IN "
        f"(SELECT s5.id FROM seasons s5 WHERE s5.grassroots_id IS NOT NULL "
        f"AND s5.grassroots_id IN (SELECT s6.grassroots_id FROM seasons s6 "
        f"WHERE s6.id IN ({in_list}) AND s6.grassroots_id IS NOT NULL)))"
    )


def grade_base(col: str) -> str:
    """SQL expression: a grade name with a trailing sponsor parenthetical
    stripped, so "B Grade (DXC Technology)" and "B Grade" read as the SAME
    competition grade (CA decorates the grade name with the season's sponsor, so
    the same grade gets a different name year to year).

    Only a parenthetical with NO digit is stripped — sponsors are alphabetic
    ("(Solo Energy)", "(Raikot Group)"), whereas a genuine sub-grade usually
    carries a number ("(Div 1)", "(Section 2)"), so numbered grades stay
    distinct. The filter both lists and matches grades on this base, so picking
    "B Grade" scopes every sponsor variant of it."""
    return f"regexp_replace({col}, '\\s*\\([^)0-9]*\\)\\s*$', '')"


def grade_match_clause(col_expr: str) -> str:
    """``<base name> = ANY(...)`` against the ``:grade`` parameter — a single
    grade name, or several joined with ``||`` (multi-select), matched
    INCLUDE-style. For a single name ``string_to_array`` yields a one-element
    array, so behaviour is identical to the old ``= :grade`` equality.

    A value prefixed with ``!`` instead means EXCLUDE those names — and,
    unlike include mode, is NULL-tolerant: a row whose grade can't resolve to
    a name at all (a grade-less manual game, a career-scope import residual)
    is KEPT rather than silently dropped. This mirrors ``grade_scope.clause()``
    's rule for BetterStats' junior/senior split — "a row we cannot categorise
    is not a row we know to exclude" — applied here because the IQ grade
    filter matches by NAME across per-club/per-season grade-id variations, not
    a stored grade_id set, so it can't reuse that helper directly. Include
    mode is deliberately NOT NULL-tolerant: an explicit pick means exactly
    those grades, and a grade-less row is correctly outside an explicit pick.

    Powers the "Seniors only" preset (``Context.jsx``'s ``TeamPicker``), which
    sends the EXCLUDED (non-senior) names rather than the included ones —
    the include form of "every senior grade" used to drop every grade-less
    manual game and import residual from a "seniors only" view, the exact
    anti-pattern ``grade_scope.py`` was built to avoid. Every existing caller
    of this function needs no change: the mode is carried entirely in the
    runtime VALUE bound to ``:grade``, which every call site already forwards
    verbatim from the ``grade``/``grade_id``/``grade_filter`` parameter it
    receives. A grade name is assumed to never start with ``!`` or contain
    ``||`` (the existing multi-select delimiter convention)."""
    return (
        "(CASE WHEN :grade LIKE '!%' THEN "
        f"({col_expr} IS NULL OR NOT ({col_expr} = ANY(string_to_array(substring(:grade FROM 2), '||')))) "
        f"ELSE {col_expr} = ANY(string_to_array(:grade, '||')) END)"
    )


def grade_canonical_label(alias: str = "gr", org_param: str = "org") -> str:
    """SQL expression: a grade row's merge- and sponsor-aware grouping label.

    An admin can merge two genuinely different-looking raw grade names (e.g.
    "PSWL South" and "PSWL: South") into one competition via the merge-grades
    admin screen (``grade_merge_logs``: org-scoped active rows ``alias_name ->
    canonical_name``, at most one active row per alias, mirrored idempotently at
    startup in ``main.py``) — ``aggregations._GRADE_MATCH`` already honours this
    for leaderboards. BetterIQ's grade filter didn't, so a club with a merged
    grade saw both raw names as separate options that each only matched their
    own literal games. Resolves an active alias to its canonical raw name
    (single-hop, matching ``_GRADE_MATCH`` — merges are re-targeted onto the
    final root at merge time, not chased through a chain here), then strips the
    trailing sponsor parenthetical (``grade_base``) from whichever name applies,
    so team_grades()'s listing and season_grade_clause's matching agree."""
    own = grade_base(f"COALESCE({alias}.display_name_override, {alias}.name)")
    return (
        f"COALESCE("
        f"(SELECT {grade_base('gml.canonical_name')} FROM grade_merge_logs gml"
        f" WHERE gml.org_id = CAST(:{org_param} AS UUID)"
        f" AND gml.alias_name = {alias}.name AND gml.undone_at IS NULL LIMIT 1), "
        f"{own})"
    )


def season_grade_clause(season_id, grade_id, *, grade_alias: str = "gr", org_param: str = "org",
                        kind: str = "game", game_alias: Optional[str] = None) -> str:
    """Combined season (year-expanded) + grade (by merged, sponsor-stripped
    name) filter for the per-game IQ queries, where the grades table is
    aliased ``gr`` by default. ``org_param`` is the already-bound org-id
    parameter name the caller's query uses (``org`` everywhere except iq.py's
    ``org_id`` — see ``grade_canonical_label``).

    The Grade Type / Match Type scope is appended here too, so a caller that
    already asks for the season + grade filter gets the new one for free. A
    picked GRADE beats the category half but never the format half
    (``formats_only``) — someone who chose "Under 14s" plainly wants the
    juniors, whereas a grade plus a format is the single most useful thing
    the pair does, since a grade routinely plays both inside one season.
    """
    parts = []
    if season_id:
        parts.append(season_member_clause(f"{grade_alias}.season_id", season_id))
    if grade_id:
        parts.append(f"AND {grade_match_clause(grade_canonical_label(grade_alias, org_param))}")
    parts.append(grade_scope_fragment(f"{grade_alias}.id", grade_id, kind=kind, game_alias=game_alias))
    return " ".join(p for p in parts if p)


def grade_scope_fragment(grade_column: str, grade_id=None, *, kind: str = "game",
                         game_alias: Optional[str] = None) -> str:
    """:func:`scope_clause`, with the picked-grade rule applied.

    Kept separate from ``scope_clause`` so a caller that has no grade filter
    of its own doesn't have to pass ``None`` to say so, and so the rule lives
    in exactly one place rather than at each of the call sites that has to
    apply it."""
    scope = active_scope()
    if scope is None:
        return ""
    if grade_id:
        token = _SCOPE.set(scope.formats_only())
        try:
            return scope_clause(grade_column, kind, game_alias)
        finally:
            _SCOPE.reset(token)
    return scope_clause(grade_column, kind, game_alias)
