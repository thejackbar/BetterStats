"""Season alias helpers.

Admins can merge seasons (e.g. Summer 2025/26 + Winter 2025/26) so they
display and aggregate as a single canonical season. The `season_aliases`
table is a soft mapping — no row rewrites — so callers expand a canonical
season_id at query time to include any active aliases.

Two consumers:
- Filter callers want: "user picked season X — include rows for X and
  any aliases of X". Use `resolve_season_filter`.
- List callers want: "show only canonical seasons in the dropdown, plus
  attach the alias info". Use `load_active_alias_map`.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def load_active_alias_map(session: AsyncSession, org_id) -> dict[str, list[str]]:
    """Return `{canonical_id: [alias_id, ...]}` for all active aliases in this org.

    Alias IDs are stringified so callers can compare against incoming
    string season_ids without re-stringifying every UUID.
    """
    result = await session.execute(
        text(
            "SELECT canonical_season_id, alias_season_id "
            "FROM season_aliases "
            "WHERE org_id = :org AND undone_at IS NULL"
        ),
        {"org": str(_as_uuid(org_id))},
    )
    out: dict[str, list[str]] = {}
    for canonical, alias in result.all():
        out.setdefault(str(canonical), []).append(str(alias))
    return out


async def load_reverse_alias_map(session: AsyncSession, org_id) -> dict[str, str]:
    """Return `{alias_id: canonical_id}` for all active aliases.

    Lets callers normalise an incoming season_id to its canonical before
    expanding (in case a URL bookmarks an alias_id directly).
    """
    result = await session.execute(
        text(
            "SELECT alias_season_id, canonical_season_id "
            "FROM season_aliases "
            "WHERE org_id = :org AND undone_at IS NULL"
        ),
        {"org": str(_as_uuid(org_id))},
    )
    return {str(alias): str(canonical) for alias, canonical in result.all()}


async def resolve_season_filter(
    session: AsyncSession,
    org_id,
    season_id: Optional[str],
    include_shared: bool = False,
) -> Optional[list[str]]:
    """Expand a season_id filter to canonical + aliases.

    ``include_shared`` also pulls in the season rows OTHER clubs hold for the
    same year. A fixture between two synced clubs is one `games` row whose
    season belongs to whichever club synced it first, so without this a club's
    own match drops out of its own season the moment a season is picked — the
    same match its all-time figures count. It is opt-in rather than the default
    because a query whose ONLY club guard is this list (a grade listing, a
    season dropdown) would then reach another club's rows: pass it only where
    the read is also guarded by the club's own players or by
    ``club_grades.club_game_clause``.

    Returns:
        None  — caller passed no season_id, no filter should be applied.
        [...] — list of season_ids (UUID strings) to use in `= ANY(:sids)`.
                Always has at least one element when not None.
    """
    if not season_id:
        return None
    rev = await load_reverse_alias_map(session, org_id)
    canonical = rev.get(str(season_id), str(season_id))
    aliases = await session.execute(
        text(
            "SELECT alias_season_id FROM season_aliases "
            "WHERE org_id = :org AND canonical_season_id = :c AND undone_at IS NULL"
        ),
        {"org": str(_as_uuid(org_id)), "c": canonical},
    )
    ids = {canonical, *(str(r[0]) for r in aliases.all())}

    # A club's real-world season can be split across several Season rows —
    # one per competition/grassroots season GUID (e.g. an Over 60s / masters
    # comp reports under a different CA season id than the mainline grades
    # even though it's "the same year"). Pull in sibling rows sharing the
    # canonical season's year so a year split across comps is fully counted
    # (same fix as iq_team.player_impact's year-based MVP scope).
    year_row = await session.execute(
        text("SELECT year FROM seasons WHERE id = CAST(:sid AS UUID)"),
        {"sid": canonical},
    )
    year = year_row.scalar()
    if year is not None:
        siblings = await session.execute(
            text("SELECT id FROM seasons WHERE organisation_id = CAST(:org AS UUID) AND year = :year"),
            {"org": str(_as_uuid(org_id)), "year": year},
        )
        ids |= {str(r[0]) for r in siblings.all()}

    if include_shared:
        # Every club's row for the same real-world season, three ways:
        #
        #   1. the same CA season GUID. Exact — a CA season id is global, not
        #      per club, so two clubs in one competition hold the same
        #      `grassroots_id` under their own per-club row ids. This is the
        #      key `iq_filters.season_ids_cross_club` already matches on.
        #   2. the same year, for two clubs whose competitions report under
        #      different CA season ids for the one summer.
        #   3. the same name, because `year` is nullable — it is only set when
        #      CA returns a start date (see the sync's season upsert), and a
        #      hand-created season row can have neither of the above.
        meta = await session.execute(
            text("SELECT name, grassroots_id FROM seasons"
                 " WHERE id = ANY(:ids)"),
            {"ids": list(ids)},
        )
        names, guids = set(), set()
        for nm, guid in meta.all():
            if nm:
                names.add(nm.lower())
            if guid:
                guids.add(guid)
        shared = await session.execute(
            text(
                "SELECT id FROM seasons"
                " WHERE (grassroots_id IS NOT NULL AND grassroots_id = ANY(:guids))"
                "    OR (CAST(:year AS INT) IS NOT NULL AND year = CAST(:year AS INT))"
                "    OR LOWER(name) = ANY(:names)"
            ),
            {"guids": list(guids), "year": year, "names": list(names)},
        )
        ids |= {str(r[0]) for r in shared.all()}
    return list(ids)


async def org_id_for_season(session: AsyncSession, season_id: str) -> Optional[str]:
    """Look up the org_id for a season — used when a query only has
    season_id and not org_id (e.g. player-scoped endpoints)."""
    if not season_id:
        return None
    result = await session.execute(
        text("SELECT organisation_id FROM seasons WHERE id = :sid"),
        {"sid": str(_as_uuid(season_id))},
    )
    row = result.first()
    return str(row[0]) if row else None


async def resolve_season_filter_no_org(
    session: AsyncSession,
    season_id: Optional[str],
    include_shared: bool = False,
) -> Optional[list[str]]:
    """Same as resolve_season_filter but for callers that only have
    season_id (no org_id). Looks up org_id from the season first."""
    if not season_id:
        return None
    org_id = await org_id_for_season(session, season_id)
    if not org_id:
        return [str(season_id)]
    return await resolve_season_filter(session, org_id, season_id, include_shared)
