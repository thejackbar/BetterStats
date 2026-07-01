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
) -> Optional[list[str]]:
    """Expand a season_id filter to canonical + aliases.

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
) -> Optional[list[str]]:
    """Same as resolve_season_filter but for callers that only have
    season_id (no org_id). Looks up org_id from the season first."""
    if not season_id:
        return None
    org_id = await org_id_for_season(session, season_id)
    if not org_id:
        return [str(season_id)]
    return await resolve_season_filter(session, org_id, season_id)
