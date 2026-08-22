"""The one copy of migration 275's backfill, run by BOTH alembic and the
lifespan mirror in ``main.py``.

Same discipline ``services/vote_medal_ddl.py`` keeps: two hand-copied versions
of a data-moving statement drift the first time one is edited, and this one
SPLITS rows, so a drift would leave a club's plan tree half-converted.

Both statements are idempotent. The split only matches a pillar whose
objectives still span several plans, and the claim only fills a NULL plan_id,
so re-running the pair once every pillar carries its plan does nothing.
"""

# A pillar used by several plans is copied once per extra plan, and that plan's
# objectives are re-pointed at its own copy. The FIRST plan (by id) keeps the
# original row; CLAIM_SQL below then attributes it.
#
# This has to run BEFORE the claim: if a single plan claimed the original
# first, the other plans' objectives would be left pointing at a theme that
# now belongs to somebody else's plan.
PILLAR_PLAN_SPLIT_SQL = """
DO $$
DECLARE
    r RECORD;
    new_id UUID;
BEGIN
    FOR r IN
        SELECT p.id AS pillar_id, o.plan_id AS plan_id, p.organisation_id,
               p.name, p.description, p.sort_order, p.is_active
        FROM club_strategic_pillars p
        JOIN club_objectives o
          ON o.pillar_id = p.id AND o.plan_id IS NOT NULL
        WHERE p.plan_id IS NULL
          AND o.plan_id <> (
            SELECT o2.plan_id FROM club_objectives o2
            WHERE o2.pillar_id = p.id AND o2.plan_id IS NOT NULL
            ORDER BY o2.plan_id
            LIMIT 1
          )
        GROUP BY p.id, o.plan_id, p.organisation_id, p.name, p.description,
                 p.sort_order, p.is_active
    LOOP
        INSERT INTO club_strategic_pillars
            (id, organisation_id, name, description, sort_order, is_active, plan_id)
        VALUES (gen_random_uuid(), r.organisation_id, r.name, r.description,
                r.sort_order, r.is_active, r.plan_id)
        RETURNING id INTO new_id;

        UPDATE club_objectives
        SET pillar_id = new_id
        WHERE pillar_id = r.pillar_id AND plan_id = r.plan_id;
    END LOOP;
END $$;
"""

# What is left of each original pillar now belongs to at most one plan. A
# pillar with no objectives anywhere cannot be attributed and keeps a NULL
# plan_id — it reads as a theme no plan has claimed.
PILLAR_PLAN_CLAIM_SQL = """
UPDATE club_strategic_pillars p
SET plan_id = sub.plan_id
FROM (
    SELECT pillar_id, MIN(plan_id::text)::uuid AS plan_id
    FROM club_objectives
    WHERE pillar_id IS NOT NULL AND plan_id IS NOT NULL
    GROUP BY pillar_id
    HAVING COUNT(DISTINCT plan_id) = 1
) AS sub
WHERE p.id = sub.pillar_id AND p.plan_id IS NULL
"""
