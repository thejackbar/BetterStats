"""Club merger — audit log for bulk org-to-org data reassignment

New capability (services/org_merge.py, routers/club_admin.py) for a real-world
club merger — e.g. Hilton Palmyra + Bicton Attadale merging into Hilton
Bicton, where Hilton Bicton's BetterCricket org only carries one of the two
predecessor clubs' PlayHQ/CA identity and the other club's rich historical
data sits under its own, still-separately-synced CA organisation. The flow:
sync the second club as its own temporary BetterCricket org (ordinary
onboarding — no new code needed for that half), then bulk-reassign every
player/season/grade/game/leaf-stat row from that temp org onto the target
club's real org, and archive the temp org.

`org_merge_logs` is an audit trail (source/target org, who ran it, counts per
entity type) — NOT a full per-row backup. Reversibility is partial: players
that collided with an existing target-org player were merged through the
existing `admin.merge_players` machinery and so get its real per-player
`undo_merge`; seasons/grades/games that were moved or redirected have no
built-in undo in this first cut (un-archiving the source org does not
reverse the reassignment).

Revision ID: 168
Revises: 167
Create Date: 2026-07-21
"""
from alembic import op


revision = '168'
down_revision = '167'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_merge_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
            source_org_name TEXT NOT NULL,
            target_org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            performed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            seasons_moved INTEGER NOT NULL DEFAULT 0,
            seasons_merged INTEGER NOT NULL DEFAULT 0,
            grades_moved INTEGER NOT NULL DEFAULT 0,
            grades_merged INTEGER NOT NULL DEFAULT 0,
            games_repointed INTEGER NOT NULL DEFAULT 0,
            players_moved INTEGER NOT NULL DEFAULT 0,
            players_merged INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_org_merge_logs_target "
        "ON org_merge_logs(target_org_id, performed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_org_merge_logs_target")
    op.execute("DROP TABLE IF EXISTS org_merge_logs")
