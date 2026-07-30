"""Votes redesign — nudge audit trail.

The Games hub's "Nudge non-voters" (bulk, per-fixture) sends an email
reminder to every eligible player who hasn't voted yet. vote_nudges is the
send log: it backs the "one nudge per player per fixture per 24h" rate limit
(BetterComms usage policy) and makes the count auditable.

Note: the design brief assumed SMS/WhatsApp push nudges, but this codebase
has no SMS/WhatsApp sending integration (BetterComms is email-only, via
services/email_service.py) — so a nudge is a plain reminder email to the
player's stored address; a player with no email on file simply can't be
nudged automatically (channel reads "none").

Revision ID: 196
Revises: 195
Create Date: 2026-07-30
"""
from alembic import op

revision = '196'
down_revision = '195'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_nudges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
            player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vote_nudges_fixture_player "
        "ON vote_nudges(fixture_id, player_id, sent_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vote_nudges")
