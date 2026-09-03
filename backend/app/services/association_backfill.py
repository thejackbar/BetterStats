"""Filling in every club's grade associations from what we already hold.

A grade can only be put in a competition once we know which ASSOCIATION ran
it. The sync writes that as it goes (migration 283), but only for the seasons
it scans, so every club onboarded before that carries a history of grades with
no association and therefore no competition — Applecross opened Manage Grades
and found 53 seasons outside every competition.

Fetching them one club at a time is one Cricket Australia call per club per
season, which is where "this will take a fortnight" came from. Two facts about
our OWN data make almost all of those calls unnecessary:

1. **A CA GRADE GUID IS COMPETITION-WIDE.** One grade GUID is shared by every
   club in that grade (verified against ten clubs sharing High Wycombe's "1st
   Grade", see the migration 067 note). So an association ANY club holds for a
   guid is the association for EVERY club's row carrying it. That is exact,
   free, and it is what makes the API phase collapse: the first club processed
   in an association resolves the grade guids for all the others.

2. **A CLUB'S OWN GRADE NAME IS ITS OWN COMPETITION.** Applecross's "1st Grade"
   in 2011/12 is the same competition as its "1st Grade" today. So one recent
   sync propagates backwards across every season of that name — with the guard
   that the rows we DO know must all agree on one association. Where a club has
   moved between associations under one grade name, they disagree, and nothing
   is written rather than a guess.

Both phases are plain SQL over our own database and fill NULLs only: an
association we already hold is never overwritten, which is what makes them safe
to run repeatedly and safe to run before the API phase.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# The sponsor-suffix strip, as SQL. Mirrors `grade_labels.strip_sponsor_suffix`
# and `iq_filters.grade_base`: CA decorates a grade's name with the season's
# sponsor, so "B Grade (DXC Technology)" and "B Grade" are one grade.
_GRADE_KEY = (
    r"LOWER(BTRIM(regexp_replace(COALESCE(gml.canonical_name, gr.name),"
    r" '\s*\([^)0-9]*\)\s*$', '')))"
)


async def propagate_by_grade_guid(db: AsyncSession) -> int:
    """Fill a grade's association from another club's row for the same guid.

    Exact: the guid IS the competition-wide grade. The HAVING guard means a
    guid two clubs disagree about is left alone rather than resolved by
    whichever row sorted first.
    """
    res = await db.execute(text(
        """
        WITH known AS (
            SELECT grassroots_id,
                   MIN(association_id)         AS association_id,
                   MIN(association_name)       AS association_name,
                   MIN(association_short_name) AS association_short_name
              FROM grades
             WHERE grassroots_id IS NOT NULL AND association_id IS NOT NULL
             GROUP BY grassroots_id
            HAVING COUNT(DISTINCT association_id) = 1
        )
        UPDATE grades gr
           SET association_id = k.association_id,
               association_name = COALESCE(gr.association_name, k.association_name),
               association_short_name =
                   COALESCE(gr.association_short_name, k.association_short_name)
          FROM known k
         WHERE gr.grassroots_id = k.grassroots_id
           AND gr.association_id IS NULL
        """
    ))
    return res.rowcount or 0


async def propagate_by_club_grade_name(db: AsyncSession) -> int:
    """Fill a grade's association from the same club's other rows of that name.

    Folded through the club's own grade merges, so CA's older spelling inherits
    the answer given to the name that was kept. Only where every row of that
    name we already know agrees — a club that has moved associations under one
    name is left for the API phase rather than guessed at.
    """
    res = await db.execute(text(
        f"""
        WITH folded AS (
            SELECT gr.id,
                   s.organisation_id AS org,
                   {_GRADE_KEY} AS key,
                   gr.association_id,
                   gr.association_name,
                   gr.association_short_name
              FROM grades gr
              JOIN seasons s ON s.id = gr.season_id
              LEFT JOIN LATERAL (
                  SELECT canonical_name FROM grade_merge_logs g2
                   WHERE g2.org_id = s.organisation_id
                     AND g2.alias_name = gr.name
                     AND g2.undone_at IS NULL
                   LIMIT 1
              ) gml ON TRUE
        ), known AS (
            SELECT org, key,
                   MIN(association_id)         AS association_id,
                   MIN(association_name)       AS association_name,
                   MIN(association_short_name) AS association_short_name
              FROM folded
             WHERE association_id IS NOT NULL
             GROUP BY org, key
            HAVING COUNT(DISTINCT association_id) = 1
        )
        UPDATE grades gr
           SET association_id = k.association_id,
               association_name = COALESCE(gr.association_name, k.association_name),
               association_short_name =
                   COALESCE(gr.association_short_name, k.association_short_name)
          FROM folded f
          JOIN known k ON k.org = f.org AND k.key = f.key
         WHERE gr.id = f.id
           AND gr.association_id IS NULL
        """
    ))
    return res.rowcount or 0


async def propagate_all(db: AsyncSession, commit: bool = True) -> dict:
    """Both SQL phases, run until neither writes anything.

    They feed each other: a guid filled from another club unlocks that club's
    other seasons of the same name, which in turn carry a guid another club is
    waiting on. Two or three passes settle it; the loop is bounded so a
    pathological cycle cannot spin.

    ``commit=False`` leaves the writes in the caller's open transaction, which
    is how the batch script's dry run reports what WOULD be filled — including
    the residual gap, which can only be measured before the rollback — without
    keeping a second copy of this loop that could drift from it.
    """
    by_guid = by_name = 0
    for _ in range(5):
        guid_rows = await propagate_by_grade_guid(db)
        name_rows = await propagate_by_club_grade_name(db)
        by_guid += guid_rows
        by_name += name_rows
        if not guid_rows and not name_rows:
            break
    if commit:
        await db.commit()
    return {"filled_by_grade_guid": by_guid, "filled_by_club_grade_name": by_name}


async def outstanding_seasons(db: AsyncSession, org_id=None) -> list[dict]:
    """The (club, season) pairs still holding a grade with no association.

    This is exactly the list the API phase has to work through, and it is
    re-read between calls: each answer is applied across every club by guid, so
    a season that was outstanding a moment ago may already be resolved.
    """
    clause = " AND s.organisation_id = CAST(:org AS UUID)" if org_id else ""
    res = await db.execute(text(
        f"""
        SELECT s.organisation_id AS org_id,
               COALESCE(s.grassroots_id, CAST(s.id AS TEXT)) AS season_guid,
               s.name AS season_name,
               COUNT(*) AS grades
          FROM seasons s
          JOIN grades gr ON gr.season_id = s.id
         WHERE gr.association_id IS NULL{clause}
         GROUP BY s.organisation_id, season_guid, s.name, s.year
         ORDER BY s.year DESC NULLS LAST
        """
    ), ({"org": str(org_id)} if org_id else {}))
    return [dict(r) for r in res.mappings()]


async def apply_associations(db: AsyncSession, found: dict) -> int:
    """Write ``{grade guid: owningOrganisation}`` across EVERY club at once.

    Not just the club whose call returned it — the guid is competition-wide, so
    one answer resolves every club's row for that grade. This is what makes the
    API phase collapse as it goes.
    """
    filled = 0
    for guid, owner in (found or {}).items():
        if not guid or not (owner or {}).get("id"):
            continue
        res = await db.execute(text(
            """
            UPDATE grades
               SET association_id = :aid,
                   association_name = COALESCE(association_name, :aname),
                   association_short_name = COALESCE(association_short_name, :ashort)
             WHERE grassroots_id = :guid AND association_id IS NULL
            """
        ), {
            "aid": owner["id"],
            "aname": (owner.get("name") or "").strip() or None,
            "ashort": (owner.get("shortName") or "").strip() or None,
            "guid": guid,
        })
        filled += res.rowcount or 0
    return filled
