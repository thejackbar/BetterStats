"""Linked clubs (migration 322).

A Super Admin can link two or more clubs. Each club is in at most one link
group, so `organisation_id` is the primary key and `group_id` is what the
members of one group share. Once linked, a Club Admin of any club in the group
can choose which of the group's clubs they are working in, from the admin app.

A group always has two or more members: unlinking down to one club removes the
last row too (services/club_links.py), so a lone row never means anything.

ONE copy of the DDL, per the vote_medal_ddl rule: alembic's 322, main.py's
lifespan mirror and the football schema mirror
(services/afl/cricket_schema_mirror.SHARED_DDL_MODULES) all run STATEMENTS. The
football database needs the table because the shared `/auth/me` reads it for a
Club Admin. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS club_links (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        group_id UUID NOT NULL,
        linked_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_club_links_group ON club_links (group_id)",
]

# Drops only the table this migration added.
DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_club_links_group",
    "DROP TABLE IF EXISTS club_links",
]
