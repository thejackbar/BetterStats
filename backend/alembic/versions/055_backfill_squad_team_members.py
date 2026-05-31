"""backfill team_members from players.squad_team_id

Decision (build-plan task "Filters on BetterSelect Screens"): the assigned
squad (players.squad_team_id) is mirrored into team_members so the "Squad"
filter resolves to the same set on every BetterSelect screen. The app keeps the
two in step going forward (services/squad_membership.sync_squad_membership);
this one-off backfill brings EXISTING assignments across so the unify is
effective immediately, not just for future re-assignments.

Revision ID: 055
Revises: 054
Create Date: 2026-05-31

"""
from alembic import op


revision = '055'
down_revision = '054'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO team_members (team_id, player_id, organisation_id)
        SELECT p.squad_team_id, p.id, p.organisation_id
        FROM players p
        WHERE p.squad_team_id IS NOT NULL
        ON CONFLICT (team_id, player_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Data backfill only — the inserted rows are indistinguishable from manual
    # squad memberships, so there's nothing safe to reverse.
    pass
