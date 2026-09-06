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
import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# A stable per-name id for an association we only know from the Club
# Directory, so two Directory-only clubs that name the same association land
# on one value even though neither has ever synced a real grade guid for it.
# Deterministic and namespaced so it can never collide with a real CA guid.
_DIRECTORY_ASSOC_NS = uuid.uuid5(uuid.NAMESPACE_URL,
                                  "bettercricket.com/directory-association")


def _directory_assoc_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip()).lower()

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


async def propagate_from_directory(db: AsyncSession) -> int:
    """Fill a whole club's gap from the Club Directory, where it can only mean
    one thing: a club that plays in EXACTLY one association, per the Directory's
    own ``marketing_clubs.associations``.

    THE TWO ID SPACES DO NOT MATCH, so this never writes the Directory's own
    id. `grades.association_id` is written from the GRASSROOTS proxy's
    ``owningOrganisation.id``; the Directory's comes from PlayHQ's main graph,
    a routing code. Checked against the live database before writing this, not
    assumed — the two overlap on NAME, not on id. So the match is by name:
    reuse whatever id we already hold for that name (a real one, once any club
    has synced it, or an earlier directory-minted one), and only mint a fresh
    deterministic id keyed on the normalised name when nothing anywhere has
    called it that yet. Two Directory-only clubs naming the same association
    land on one value for the same reason `propagate_by_grade_guid` does.

    Refuses exactly like the other two phases: a name that already means more
    than one distinct association_id somewhere is left alone rather than
    picking one, which is the shape of two real associations sharing a common
    word ("Metropolitan Cricket Association") rather than the same body.
    """
    rows = (await db.execute(text(
        """
        SELECT o.id AS org_id,
               BTRIM(mc.associations->0->>'name') AS assoc_name,
               (SELECT MIN(g2.association_id) FROM grades g2
                 WHERE g2.association_id IS NOT NULL
                   AND LOWER(BTRIM(g2.association_name)) =
                       LOWER(BTRIM(mc.associations->0->>'name'))) AS known_id,
               (SELECT MIN(g2.association_short_name) FROM grades g2
                 WHERE g2.association_id IS NOT NULL
                   AND LOWER(BTRIM(g2.association_name)) =
                       LOWER(BTRIM(mc.associations->0->>'name'))) AS known_short,
               (SELECT COUNT(DISTINCT g2.association_id) FROM grades g2
                 WHERE g2.association_id IS NOT NULL
                   AND LOWER(BTRIM(g2.association_name)) =
                       LOWER(BTRIM(mc.associations->0->>'name'))) AS distinct_ids
          FROM organisations o
          JOIN marketing_clubs mc ON mc.existing_org_id = o.id AND mc.kind = 'club'
         WHERE o.archived_at IS NULL
           AND jsonb_typeof(mc.associations) = 'array'
           AND jsonb_array_length(mc.associations) = 1
           AND COALESCE(BTRIM(mc.associations->0->>'name'), '') <> ''
           AND EXISTS (
               SELECT 1 FROM seasons s JOIN grades gr ON gr.season_id = s.id
                WHERE s.organisation_id = o.id AND gr.association_id IS NULL)
        """
    ))).mappings().all()

    org_ids, assoc_ids, assoc_names, assoc_shorts = [], [], [], []
    for r in rows:
        if r["distinct_ids"] and r["distinct_ids"] > 1:
            continue  # this name already means more than one thing — refuse
        if r["known_id"]:
            assoc_id, assoc_short = r["known_id"], r["known_short"]
        else:
            assoc_id = str(uuid.uuid5(
                _DIRECTORY_ASSOC_NS, _directory_assoc_key(r["assoc_name"])))
            assoc_short = None
        org_ids.append(str(r["org_id"]))
        assoc_ids.append(assoc_id)
        assoc_names.append(r["assoc_name"])
        assoc_shorts.append(assoc_short)

    if not org_ids:
        return 0

    res = await db.execute(text(
        """
        UPDATE grades gr
           SET association_id = v.assoc_id,
               association_name = COALESCE(gr.association_name, v.assoc_name),
               association_short_name =
                   COALESCE(gr.association_short_name, v.assoc_short)
          FROM unnest(CAST(:org_ids AS uuid[]), CAST(:assoc_ids AS text[]),
                      CAST(:assoc_names AS text[]), CAST(:assoc_shorts AS text[]))
               AS v(org_id, assoc_id, assoc_name, assoc_short)
          JOIN seasons s ON s.organisation_id = v.org_id
         WHERE gr.season_id = s.id
           AND gr.association_id IS NULL
        """
    ), {
        "org_ids": org_ids, "assoc_ids": assoc_ids,
        "assoc_names": assoc_names, "assoc_shorts": assoc_shorts,
    })
    return res.rowcount or 0


async def propagate_all(db: AsyncSession, commit: bool = True) -> dict:
    """All three SQL phases, run until none of them writes anything.

    They feed each other: a guid filled from another club unlocks that club's
    other seasons of the same name, which in turn carry a guid another club is
    waiting on; a whole club filled from the Directory can be the FIRST known
    row for a guid or a name that unlocks other clubs sharing it. Bounded at
    five passes so a pathological cycle cannot spin.

    ``commit=False`` leaves the writes in the caller's open transaction, which
    is how the batch script's dry run reports what WOULD be filled — including
    the residual gap, which can only be measured before the rollback — without
    keeping a second copy of this loop that could drift from it.
    """
    by_guid = by_name = by_directory = 0
    for _ in range(5):
        guid_rows = await propagate_by_grade_guid(db)
        name_rows = await propagate_by_club_grade_name(db)
        dir_rows = await propagate_from_directory(db)
        by_guid += guid_rows
        by_name += name_rows
        by_directory += dir_rows
        if not guid_rows and not name_rows and not dir_rows:
            break
    if commit:
        await db.commit()
    return {"filled_by_grade_guid": by_guid, "filled_by_club_grade_name": by_name,
            "filled_by_directory": by_directory}


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


async def plan_api_phase(db: AsyncSession, org_id=None) -> dict:
    """How many Cricket Australia calls the API phase would actually make.

    THE CALL COUNT IS NOT THE OUTSTANDING SEASON COUNT, and the gap between
    them is the whole reason this exists. One fetched season resolves grade
    guids that other clubs share, and each answer then propagates backwards
    across every season of that club's own grade names — so seasons drop off
    the list before they are ever called.

    This works it out from data we already hold, with no request made. Grades
    are unioned into components by the two things the propagation phases
    spread along: a shared CA grade guid, and one club's own grade name. A
    fetched season resolves every component it touches, so walking the seasons
    in the order the API phase walks them gives the real number.

    It is an ESTIMATE of the call count in one direction only: it assumes CA
    answers every season it is asked, so a season CA has no association for is
    counted as a call that resolves something. That makes the projected calls a
    LOWER bound and the projected residual optimistic; the real run reports
    both exactly.
    """
    clause = " AND s.organisation_id = CAST(:org AS UUID)" if org_id else ""
    rows = (await db.execute(text(
        f"""
        SELECT gr.id, s.organisation_id AS org_id,
               COALESCE(s.grassroots_id, CAST(s.id AS TEXT)) AS season_guid,
               gr.grassroots_id AS guid,
               {_GRADE_KEY} AS gkey,
               gr.association_id IS NOT NULL AS known,
               s.year
          FROM grades gr
          JOIN seasons s ON s.id = gr.season_id
          LEFT JOIN grade_merge_logs gml
                 ON gml.org_id = s.organisation_id
                AND gml.undone_at IS NULL
                AND LOWER(gml.alias_name) = LOWER(gr.name)
         WHERE TRUE{clause}
        """), {"org": str(org_id)} if org_id else {})).mappings().all()

    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # A grade is linked to every other grade it can be resolved from.
    for r in rows:
        gid = ("g", r["id"])
        find(gid)
        if r["guid"]:
            union(gid, ("guid", r["guid"]))
        if r["gkey"]:
            union(gid, ("name", str(r["org_id"]), r["gkey"]))

    resolved = {find(("g", r["id"])) for r in rows if r["known"]}

    # The seasons still holding an unresolved grade, newest first — the order
    # `outstanding_seasons` itself returns them in.
    seasons: dict = {}
    for r in rows:
        if r["known"]:
            continue
        seasons.setdefault((r["org_id"], r["season_guid"]), {"year": r["year"], "comps": set()})
        seasons[(r["org_id"], r["season_guid"])]["comps"].add(find(("g", r["id"])))

    order = sorted(seasons.items(),
                   key=lambda kv: (kv[1]["year"] is None, -(kv[1]["year"] or 0)))

    calls = skipped = 0
    for _key, info in order:
        if info["comps"] <= resolved:
            skipped += 1      # another club's answer got there first
            continue
        calls += 1
        resolved |= info["comps"]

    unresolved_rows = sum(
        1 for r in rows if not r["known"] and find(("g", r["id"])) not in resolved)
    return {
        "seasons_outstanding": len(seasons),
        "projected_calls": calls,
        "resolved_by_another_club": skipped,
        "projected_rows_left": unresolved_rows,
    }


async def apply_associations(db: AsyncSession, found: dict) -> int:
    """Write ``{grade guid: owningOrganisation}`` across EVERY club at once.

    Not just the club whose call returned it — the guid is competition-wide, so
    one answer resolves every club's row for that grade. This is what makes the
    API phase collapse as it goes.

    ONE STATEMENT, not a loop of one UPDATE per guid. Found running the real
    API phase at concurrency: several workers each writing their own batch of
    guids in whatever order a dict happened to iterate produced a Postgres
    deadlock — two transactions locking the same two rows in opposite orders.
    A single UPDATE takes every row lock it needs in ONE scan of the table,
    which cannot deadlock against itself, and removes the per-caller ordering
    that could still cross another concurrent call's.
    """
    items = [(g, o) for g, o in (found or {}).items() if g and (o or {}).get("id")]
    if not items:
        return 0
    guids = [g for g, _ in items]
    aids = [o["id"] for _, o in items]
    anames = [(o.get("name") or "").strip() or None for _, o in items]
    ashorts = [(o.get("shortName") or "").strip() or None for _, o in items]
    res = await db.execute(text(
        """
        UPDATE grades gr
           SET association_id = v.aid,
               association_name = COALESCE(gr.association_name, v.aname),
               association_short_name = COALESCE(gr.association_short_name, v.ashort)
          FROM unnest(CAST(:guids AS text[]), CAST(:aids AS text[]),
                      CAST(:anames AS text[]), CAST(:ashorts AS text[]))
               AS v(guid, aid, aname, ashort)
         WHERE gr.grassroots_id = v.guid
           AND gr.association_id IS NULL
        """
    ), {"guids": guids, "aids": aids, "anames": anames, "ashorts": ashorts})
    return res.rowcount or 0
