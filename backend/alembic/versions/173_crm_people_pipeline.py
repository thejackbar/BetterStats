"""BetterCRM — People/Contacts + the internal & club-facing Deal pipeline.

Adds the generic ``crm_people``/``crm_person_roles`` contact layer (a Person
can hold several roles — parent, coach, committee, volunteer, sponsor
contact… — without a new table per role; ``player_id`` is a nullable bridge
to the existing per-club ``players`` row for future unification, additive
only, no change to the Player identity scheme) and the Deal/pipeline engine
(``crm_pipelines``/``crm_stages``/``crm_deals``/``crm_deal_contacts``/
``crm_activities``) that replaces Twenty's Opportunity board for BetterCricket's
own sales pipeline (``scope='platform'``, ``organisation_id`` NULL, deals
usually linked to a ``marketing_clubs`` prospect row) and doubles as a
club-facing CRM module (``scope='club'``, org-scoped, gated by the new
``crm`` entitlement key under the BetterAdmin umbrella + MANAGE_CRM
capability). One schema, two scopes — see ``services/crm.py``.

Revision ID: 173
Revises: 172
Create Date: 2026-07-22
"""
from alembic import op


revision = '173'
down_revision = '172'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_people (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
            marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
            player_id UUID REFERENCES players(id) ON DELETE SET NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_people_org ON crm_people(organisation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_people_marketing_club ON crm_people(marketing_club_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_people_email ON crm_people(lower(email))")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_person_roles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            person_id UUID NOT NULL REFERENCES crm_people(id) ON DELETE CASCADE,
            organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            title TEXT,
            started_at DATE,
            ended_at DATE,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_person_roles_person ON crm_person_roles(person_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_person_roles_org_role ON crm_person_roles(organisation_id, role)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_pipelines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope TEXT NOT NULL DEFAULT 'club',
            organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            is_default BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_pipelines_scope_org ON crm_pipelines(scope, organisation_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_stages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pipeline_id UUID NOT NULL REFERENCES crm_pipelines(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            default_probability INTEGER NOT NULL DEFAULT 0,
            is_won BOOLEAN NOT NULL DEFAULT false,
            is_lost BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_crm_stages_pipeline_key UNIQUE (pipeline_id, key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_stages_pipeline_position ON crm_stages(pipeline_id, position)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_deals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope TEXT NOT NULL DEFAULT 'club',
            organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
            marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
            pipeline_id UUID NOT NULL REFERENCES crm_pipelines(id) ON DELETE CASCADE,
            stage_id UUID NOT NULL REFERENCES crm_stages(id) ON DELETE RESTRICT,
            title TEXT NOT NULL,
            value_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'AUD',
            probability INTEGER,
            module_keys JSONB NOT NULL DEFAULT '[]',
            expected_close_date DATE,
            status TEXT NOT NULL DEFAULT 'open',
            lost_reason TEXT,
            owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            source TEXT,
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_deals_scope_org ON crm_deals(scope, organisation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_deals_marketing_club ON crm_deals(marketing_club_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_deals_pipeline_stage ON crm_deals(pipeline_id, stage_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_deals_status ON crm_deals(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_deal_contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deal_id UUID NOT NULL REFERENCES crm_deals(id) ON DELETE CASCADE,
            person_id UUID NOT NULL REFERENCES crm_people(id) ON DELETE CASCADE,
            role_on_deal TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_crm_deal_contacts UNIQUE (deal_id, person_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_deal_contacts_person ON crm_deal_contacts(person_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_activities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deal_id UUID REFERENCES crm_deals(id) ON DELETE CASCADE,
            person_id UUID REFERENCES crm_people(id) ON DELETE CASCADE,
            organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
            type TEXT NOT NULL DEFAULT 'note',
            body TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            meta JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_activities_deal ON crm_activities(deal_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_activities_person ON crm_activities(person_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_activities_org ON crm_activities(organisation_id, occurred_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crm_activities")
    op.execute("DROP TABLE IF EXISTS crm_deal_contacts")
    op.execute("DROP TABLE IF EXISTS crm_deals")
    op.execute("DROP TABLE IF EXISTS crm_stages")
    op.execute("DROP TABLE IF EXISTS crm_pipelines")
    op.execute("DROP TABLE IF EXISTS crm_person_roles")
    op.execute("DROP TABLE IF EXISTS crm_people")
