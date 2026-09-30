"""BetterSocials saved templates, one row each (migration 313).

Saved templates used to ride inside `organisations.socials_style`, the blob the
post generator's Style choices are stored in. That blob is replaced whole on
every save, so two admins (or two tabs) overwrote each other's templates, a
club over the size cap lost every template at once, and a save needed the
Settings permission the social screens do not require.

`social_templates` is one row per template, keyed on the browser-minted
`tpl_…` key the editor already uses, so a template can be saved, updated and
deleted on its own. `data` holds the rest of what the editor saved (base
layout, Style, freeform blocks, layer order).

ONE copy of the DDL, per the vote_medal_ddl rule — alembic's 313 and main.py's
lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS social_templates (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_by UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_social_templates_org_key
        ON social_templates (organisation_id, key)
    """,
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS social_templates",
]
