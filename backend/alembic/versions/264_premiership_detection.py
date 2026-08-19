"""Detect a premiership from the game that won it, and let an admin approve it.

``games.round_name``
    The association's own round label for the match ("Grand Final", "Semi
    Final", "Round 7"). The sync has always READ this — ``services/sync.py``
    takes it off the grade match list and immediately reduces it to
    ``"final" in round_name.lower()`` for ``is_final`` — and then thrown it
    away. One bit cannot tell a flag from a straight-sets exit, which is why
    nothing could ever award a premiership off it. Storing the string costs no
    extra API call: it is already in hand on a request the sync makes anyway.

    Backfilled here from ``fixtures.round``, which is the one place a round
    name was already persisted (``fixtures.playhq_id`` holds the match GUID,
    so it joins to ``games.id``). That only covers fixtures a club has synced,
    so the rest fills in on the next sync.

``premiership_detections``
    The admin's DECISION about a detected premiership, and nothing else. The
    candidates themselves are derived on read from the games — same posture as
    BetterFees' match-day allocation and the Votes leaderboard — so a corrected
    round name or a re-synced result restates the list rather than leaving a
    stale detection row behind. Absence of a row means pending.

    ``created_achievement_ids`` records exactly which ``player_achievements``
    rows an approval wrote, so undoing one hands back those rows and no
    others. Without it an undo would have to re-derive the XI and could remove
    an award somebody added by hand.

Revision ID: 264
Revises: 263
"""
from alembic import op

revision = "264"
down_revision = "263"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS round_name TEXT")

    # No foreign keys, matching the neighbouring player_achievements table:
    # this is created both here and idempotently in main.py's lifespan, and a
    # raw-SQL table that FKs into the ORM ones becomes order-dependent on a
    # fresh database. An orphaned row simply never matches a candidate.
    op.execute("""
        CREATE TABLE IF NOT EXISTS premiership_detections (
            id                      UUID PRIMARY KEY,
            organisation_id         UUID NOT NULL,
            game_id                 UUID NOT NULL,
            status                  TEXT NOT NULL,
            decided_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_by_user_id      UUID,
            created_achievement_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_premiership_detections_org_game
            ON premiership_detections (organisation_id, game_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_premiership_detections_org
            ON premiership_detections (organisation_id)
    """)

    # Seed the round name from the fixtures the club has already synced.
    op.execute("""
        UPDATE games g
           SET round_name = f.round
          FROM fixtures f
         WHERE f.playhq_id = g.id::text
           AND f.round IS NOT NULL
           AND g.round_name IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS premiership_detections")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS round_name")
