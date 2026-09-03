"""What can the Club Directory tell us about which association ran a grade?

READ ONLY. Writes nothing, calls nothing upstream.

`marketing_clubs.associations` holds every association a club plays in, which
looks like exactly the seed the grade backfill needs. Two things have to be
true before it can be used, and both are facts about the live data rather than
about the code:

1. **THE IDS HAVE TO BE THE SAME NAMESPACE.** `grades.association_id` is
   written from the GRASSROOTS proxy (`grade.owningOrganisation.id`), while the
   Directory's comes from PlayHQ's main graph (`discoverCompetitions` →
   `organisation.id`, which is a routing code). This repo has been caught by a
   PlayHQ-vs-Grassroots id mismatch before, so it is checked, not assumed.

2. **THE CLUB HAS TO PLAY IN EXACTLY ONE.** The Directory records associations
   per CLUB, not per grade, so a club in three of them says nothing about which
   one ran a given grade. One association is an exact answer; several is a
   guess, and a wrong association files a club's matches under a competition it
   never played in.

Usage
-----
    python -m app.scripts.inspect_association_sources
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.models.db import async_session_maker


async def main() -> None:
    async with async_session_maker() as db:
        async def one(sql, **kw):
            return (await db.execute(text(sql), kw)).scalar()

        print("— what the grades hold —")
        total = await one("SELECT COUNT(*) FROM grades")
        known = await one("SELECT COUNT(*) FROM grades WHERE association_id IS NOT NULL")
        distinct = await one(
            "SELECT COUNT(DISTINCT association_id) FROM grades"
            " WHERE association_id IS NOT NULL")
        print(f"  {known} of {total} grade rows carry an association"
              f" ({distinct} distinct)")

        print("\n— what the Club Directory holds for OUR clubs —")
        linked = await one("""
            SELECT COUNT(*) FROM marketing_clubs mc
             JOIN organisations o ON o.id = mc.existing_org_id
             WHERE o.archived_at IS NULL""")
        with_assoc = await one("""
            SELECT COUNT(*) FROM marketing_clubs mc
             JOIN organisations o ON o.id = mc.existing_org_id
             WHERE o.archived_at IS NULL
               AND jsonb_typeof(mc.associations) = 'array'
               AND jsonb_array_length(mc.associations) > 0""")
        exactly_one = await one("""
            SELECT COUNT(*) FROM marketing_clubs mc
             JOIN organisations o ON o.id = mc.existing_org_id
             WHERE o.archived_at IS NULL
               AND jsonb_typeof(mc.associations) = 'array'
               AND jsonb_array_length(mc.associations) = 1""")
        print(f"  {linked} of our clubs are linked to a Directory row")
        print(f"  {with_assoc} have at least one association recorded")
        print(f"  {exactly_one} play in EXACTLY one — an exact answer for every"
              " grade they hold")

        print("\n— do the two id namespaces match? —")
        overlap = await one("""
            SELECT COUNT(DISTINCT gr.association_id)
              FROM grades gr
             WHERE gr.association_id IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM marketing_clubs mc,
                        LATERAL jsonb_array_elements(mc.associations) a
                    WHERE jsonb_typeof(mc.associations) = 'array'
                      AND a->>'id' = gr.association_id)""")
        name_overlap = await one("""
            SELECT COUNT(DISTINCT LOWER(BTRIM(gr.association_name)))
              FROM grades gr
             WHERE gr.association_name IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM marketing_clubs mc,
                        LATERAL jsonb_array_elements(mc.associations) a
                    WHERE jsonb_typeof(mc.associations) = 'array'
                      AND LOWER(BTRIM(a->>'name')) = LOWER(BTRIM(gr.association_name)))""")
        print(f"  ids that appear in both: {overlap} of {distinct}")
        print(f"  names that appear in both: {name_overlap}")
        if distinct and not overlap and name_overlap:
            print("  → DIFFERENT namespaces, but the NAMES agree: match on name.")
        elif overlap:
            print("  → the ids agree: the Directory's association id can be used"
                  " directly.")
        else:
            print("  → no overlap on either. Too little synced data to tell yet,"
                  " or genuinely unrelated.")

        print("\n— how much a single-association club would fill —")
        fillable = await one("""
            SELECT COUNT(*)
              FROM grades gr
              JOIN seasons s ON s.id = gr.season_id
              JOIN organisations o ON o.id = s.organisation_id
              JOIN marketing_clubs mc ON mc.existing_org_id = o.id
             WHERE gr.association_id IS NULL
               AND o.archived_at IS NULL
               AND jsonb_typeof(mc.associations) = 'array'
               AND jsonb_array_length(mc.associations) = 1""")
        gap = await one("SELECT COUNT(*) FROM grades WHERE association_id IS NULL")
        pct = (fillable / gap * 100) if gap else 0
        print(f"  {fillable} of the {gap} grade rows with no association belong"
              f" to a club that plays in exactly one ({pct:.1f}%)")

        rows = (await db.execute(text("""
            SELECT o.name, jsonb_array_length(mc.associations) AS n,
                   COUNT(*) FILTER (WHERE gr.association_id IS NULL) AS missing
              FROM organisations o
              JOIN marketing_clubs mc ON mc.existing_org_id = o.id
              JOIN seasons s ON s.organisation_id = o.id
              JOIN grades gr ON gr.season_id = s.id
             WHERE o.archived_at IS NULL
               AND jsonb_typeof(mc.associations) = 'array'
             GROUP BY o.name, n
             HAVING COUNT(*) FILTER (WHERE gr.association_id IS NULL) > 0
             ORDER BY missing DESC LIMIT 12"""))).all()
        if rows:
            print("\n  biggest gaps, and how many associations each club plays in:")
            for name, n, missing in rows:
                print(f"    {missing:6d} grades  {n} assoc  {name}")


asyncio.run(main())
