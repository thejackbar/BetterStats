"""Migration 276's backfill and constraints, in ONE copy run by both alembic
and the lifespan mirror in ``main.py`` — the rule ``vote_medal_ddl`` and
``pillar_plan_ddl`` already set.

**A plan owns its themes; a theme owns its objectives.** 275 gave a theme its
plan; this makes the three-level tree an invariant the database enforces rather
than something the screens have to be careful about:

* ``club_strategic_pillars.plan_id``  NOT NULL
* ``club_objectives.plan_id``         NOT NULL, ON DELETE CASCADE
* ``club_objectives.pillar_id``       NOT NULL, ON DELETE CASCADE

The two FKs were ``ON DELETE SET NULL``, which cannot coexist with NOT NULL —
a plan delete would try to null a column that refuses it. So deleting a plan
now takes its themes and their objectives, and deleting a theme takes its
objectives, structurally. That is what "an objective belongs to its theme, with
its plan" means: there is nowhere for an orphan to go.

**Nothing the club wrote is deleted to get there.** Every statement below moves
rows into a home rather than removing them, and the ACTIONS and MOTIONS serving
an objective are untouched throughout — ``committee_tasks``/``meeting_motions``
→ ``club_objectives`` stays ON DELETE SET NULL, so they are kept and simply
stop being linked. The one exception is an empty theme with no plan, which
holds nothing but a word.

Every statement is idempotent: each one either matches nothing on a second run
or is an ``ADD CONSTRAINT``/``SET NOT NULL`` guarded against already being so.
"""

# 1. An objective takes the plan of its theme. This is the invariant
#    `upsert_objective` enforces on every write; applying it first means a
#    theme that 275 could attribute drags its objectives onto the same plan,
#    including any that never named one.
INHERIT_PLAN_FROM_THEME_SQL = """
UPDATE club_objectives o
SET plan_id = p.plan_id
FROM club_strategic_pillars p
WHERE o.pillar_id = p.id
  AND p.plan_id IS NOT NULL
  AND (o.plan_id IS NULL OR o.plan_id <> p.plan_id)
"""

# 2. A theme with no plan AND no objectives holds nothing but its name, so it
#    goes. Anything with work under it is carried instead, by step 3.
DROP_EMPTY_PLANLESS_THEMES_SQL = """
DELETE FROM club_strategic_pillars p
WHERE p.plan_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM club_objectives o WHERE o.pillar_id = p.id)
"""

# 3. Whatever is still unattributed — a theme with no plan but real objectives
#    under it, or an objective on no plan at all — is carried into ONE plan per
#    club rather than binned. It is named so a committee knows what it is
#    looking at and can move the work onto a real plan or delete it.
CARRIER_PLAN_SQL = """
DO $$
DECLARE
    r RECORD;
    carrier UUID;
BEGIN
    FOR r IN
        SELECT DISTINCT organisation_id FROM (
            SELECT organisation_id FROM club_strategic_pillars WHERE plan_id IS NULL
            UNION ALL
            SELECT organisation_id FROM club_objectives WHERE plan_id IS NULL
        ) AS needs
    LOOP
        SELECT id INTO carrier FROM club_strategic_plans
        WHERE organisation_id = r.organisation_id AND name = 'Unfiled work'
        LIMIT 1;

        IF carrier IS NULL THEN
            INSERT INTO club_strategic_plans (id, organisation_id, name, description)
            VALUES (gen_random_uuid(), r.organisation_id, 'Unfiled work',
                    'Themes and objectives that were not on a plan when plans '
                    'took ownership of their own themes. Move them onto a real '
                    'plan, or delete what no longer applies.')
            RETURNING id INTO carrier;
        END IF;

        UPDATE club_strategic_pillars SET plan_id = carrier
        WHERE organisation_id = r.organisation_id AND plan_id IS NULL;

        UPDATE club_objectives SET plan_id = carrier
        WHERE organisation_id = r.organisation_id AND plan_id IS NULL;
    END LOOP;
END $$;
"""

# 4. Every objective needs a theme, and one per plan is enough to hold the ones
#    that never had one. Created inside the objective's OWN plan, so carrying
#    it cannot move it between plans.
GENERAL_THEME_SQL = """
DO $$
DECLARE
    r RECORD;
    theme UUID;
BEGIN
    FOR r IN
        SELECT DISTINCT organisation_id, plan_id
        FROM club_objectives
        WHERE pillar_id IS NULL AND plan_id IS NOT NULL
    LOOP
        SELECT id INTO theme FROM club_strategic_pillars
        WHERE organisation_id = r.organisation_id AND plan_id = r.plan_id
          AND name = 'General'
        LIMIT 1;

        IF theme IS NULL THEN
            INSERT INTO club_strategic_pillars
                (id, organisation_id, name, description, sort_order, plan_id)
            VALUES (gen_random_uuid(), r.organisation_id, 'General',
                    'Objectives in this plan that were not filed under a theme.',
                    999, r.plan_id)
            RETURNING id INTO theme;
        END IF;

        UPDATE club_objectives SET pillar_id = theme
        WHERE plan_id = r.plan_id AND pillar_id IS NULL;
    END LOOP;
END $$;
"""

# 5. The FKs. SET NULL cannot coexist with NOT NULL, so both become CASCADE —
#    which is the tree: delete a plan and its themes and objectives go with it.
#    Dropped by name and rebuilt, since Postgres has no ALTER CONSTRAINT for
#    a referential action.
FK_CASCADE_SQL = [
    """
    DO $$
    DECLARE fk TEXT;
    BEGIN
        SELECT conname INTO fk FROM pg_constraint
        WHERE conrelid = 'club_objectives'::regclass AND contype = 'f'
          AND confrelid = 'club_strategic_plans'::regclass;
        IF fk IS NOT NULL AND (
            SELECT confdeltype FROM pg_constraint WHERE conname = fk
              AND conrelid = 'club_objectives'::regclass) <> 'c' THEN
            EXECUTE format('ALTER TABLE club_objectives DROP CONSTRAINT %I', fk);
            fk := NULL;
        END IF;
        IF fk IS NULL THEN
            ALTER TABLE club_objectives
                ADD CONSTRAINT club_objectives_plan_id_fkey
                FOREIGN KEY (plan_id) REFERENCES club_strategic_plans(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
    """
    DO $$
    DECLARE fk TEXT;
    BEGIN
        SELECT conname INTO fk FROM pg_constraint
        WHERE conrelid = 'club_objectives'::regclass AND contype = 'f'
          AND confrelid = 'club_strategic_pillars'::regclass;
        IF fk IS NOT NULL AND (
            SELECT confdeltype FROM pg_constraint WHERE conname = fk
              AND conrelid = 'club_objectives'::regclass) <> 'c' THEN
            EXECUTE format('ALTER TABLE club_objectives DROP CONSTRAINT %I', fk);
            fk := NULL;
        END IF;
        IF fk IS NULL THEN
            ALTER TABLE club_objectives
                ADD CONSTRAINT club_objectives_pillar_id_fkey
                FOREIGN KEY (pillar_id) REFERENCES club_strategic_pillars(id) ON DELETE CASCADE;
        END IF;
    END $$;
    """,
]

# 6. And finally the constraints themselves. SET NOT NULL is a no-op when the
#    column already is.
NOT_NULL_SQL = [
    "ALTER TABLE club_strategic_pillars ALTER COLUMN plan_id SET NOT NULL",
    "ALTER TABLE club_objectives ALTER COLUMN plan_id SET NOT NULL",
    "ALTER TABLE club_objectives ALTER COLUMN pillar_id SET NOT NULL",
]

# The whole conversion, in the order it has to run.
PLAN_TREE_SQL = [
    INHERIT_PLAN_FROM_THEME_SQL,
    DROP_EMPTY_PLANLESS_THEMES_SQL,
    CARRIER_PLAN_SQL,
    GENERAL_THEME_SQL,
    *FK_CASCADE_SQL,
    *NOT_NULL_SQL,
]
