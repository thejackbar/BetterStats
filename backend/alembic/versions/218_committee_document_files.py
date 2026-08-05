"""Uploaded committee documents, who may open them, and the link that lets a
BetterStats Office Bearer award live on BetterClubhouse's role catalogue.

Three additive changes:

1. ``committee_documents`` learns to hold a FILE, not just a link to one. The
   registry stays link-first — a constitution already living in the club's
   Drive should stay there — but a quote emailed to the treasurer has nowhere
   to live, and asking a volunteer to upload it to Drive first is how it ends
   up not recorded at all. Bytes go in Postgres for the same reason player
   photos do: the container's upload volume is not guaranteed to persist.

2. ``organisations.committee_docs_office_bearer_only`` decides who may open an
   uploaded file. It governs UPLOADS ONLY — a link-based row is a URL we do
   not host and cannot gate, so pretending otherwise would be false assurance.
   Defaults to TRUE (the tighter rule): an uploaded governance document is new
   ground with no existing behaviour to preserve, and a leaked one cannot be
   un-leaked.

3. ``player_achievements.club_role_id`` points an Office Bearer award at the
   ``club_roles`` row it names. BetterStats is the core module and may be all a
   club ever buys, so its Office Bearer records are written against
   BetterClubhouse's role catalogue from the outset — a club adopting
   BetterClubhouse later finds its roles and role types already there instead
   of needing a migration out of the awards table.

Revision ID: 218
Revises: 217
"""
from alembic import op

revision = "218"
down_revision = "217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── A document can now BE the file, not just point at it ─────────────────
    for col, ddl in [
        ("file_data", "BYTEA"),
        ("file_name", "TEXT"),
        ("file_mime", "TEXT"),
        ("file_size", "INTEGER"),
        ("uploaded_by_user_id", "UUID REFERENCES users(id) ON DELETE SET NULL"),
    ]:
        op.execute(f"ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS {col} {ddl}")

    # `url` is NOT NULL and an uploaded document has no external URL. Relax it
    # rather than storing a fake one — a row now carries a url or a file.
    op.execute("ALTER TABLE committee_documents ALTER COLUMN url DROP NOT NULL")

    # ── Who may open an uploaded file ────────────────────────────────────────
    op.execute("""
        ALTER TABLE organisations
        ADD COLUMN IF NOT EXISTS committee_docs_office_bearer_only
        BOOLEAN NOT NULL DEFAULT TRUE
    """)

    # ── An Office Bearer award names a club_roles row ────────────────────────
    op.execute("""
        ALTER TABLE player_achievements
        ADD COLUMN IF NOT EXISTS club_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_player_achievements_club_role
        ON player_achievements(club_role_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_player_achievements_club_role")
    op.execute("ALTER TABLE player_achievements DROP COLUMN IF EXISTS club_role_id")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS committee_docs_office_bearer_only")
    for col in ("file_data", "file_name", "file_mime", "file_size", "uploaded_by_user_id"):
        op.execute(f"ALTER TABLE committee_documents DROP COLUMN IF EXISTS {col}")
