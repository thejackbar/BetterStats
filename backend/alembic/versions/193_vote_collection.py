"""BetterSelect — best-player vote collection (Brownlow-style 3-2-1).

Four tables:
  * vote_settings — one row per club: who votes (captain vs players), the
    ballot shape (descending values, default [3,2,1]), how weekly votes turn
    into season points (rank conversion vs raw tally), tie policy, self-vote
    and non-participant toggles, auto-close window, and the public voting
    link token (rotatable, same posture as the availability link).
  * vote_ballots — one voter's ballot for one fixture. A club player voter is
    voter_player_id (verified by last-4 PIN on the public page, or entered by
    an admin); a non-participant voter (coach / president / supporter) is a
    bare voter_name. Partial uniques keep one live ballot per voter per
    fixture in each identity space.
  * vote_ballot_picks — the ballot's ranked picks (position 1 = best).
    Values are derived from vote_settings at count time, not stored, so a
    config change recomputes the whole season on read.
  * vote_fixture_overrides — a manual lock/reopen on top of the auto-close
    window.

Revision ID: 193
Revises: 192
Create Date: 2026-07-29
"""
from alembic import op

revision = '193'
down_revision = '192'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_settings (
            organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT false,
            link_token TEXT,
            require_pin BOOLEAN NOT NULL DEFAULT true,
            voter_mode TEXT NOT NULL DEFAULT 'players',
            ballot_values JSONB NOT NULL DEFAULT '[3,2,1]'::jsonb,
            counting_method TEXT NOT NULL DEFAULT 'rank',
            tie_policy TEXT NOT NULL DEFAULT 'share',
            allow_self_vote BOOLEAN NOT NULL DEFAULT false,
            allow_non_participants BOOLEAN NOT NULL DEFAULT false,
            auto_close_days INTEGER NOT NULL DEFAULT 7,
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_settings_link_token "
        "ON vote_settings(link_token) WHERE link_token IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_ballots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
            voter_player_id UUID REFERENCES players(id) ON DELETE CASCADE,
            voter_name TEXT,
            voter_kind TEXT NOT NULL DEFAULT 'player',
            source TEXT NOT NULL DEFAULT 'self',
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_player "
        "ON vote_ballots(fixture_id, voter_player_id) WHERE voter_player_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_name "
        "ON vote_ballots(fixture_id, lower(voter_name)) WHERE voter_player_id IS NULL AND voter_name IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vote_ballots_org_fixture "
        "ON vote_ballots(organisation_id, fixture_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_ballot_picks (
            ballot_id UUID NOT NULL REFERENCES vote_ballots(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            PRIMARY KEY (ballot_id, position),
            UNIQUE (ballot_id, player_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vote_ballot_picks_player ON vote_ballot_picks(player_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vote_fixture_overrides (
            fixture_id UUID PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            set_by UUID REFERENCES users(id) ON DELETE SET NULL,
            set_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vote_fixture_overrides")
    op.execute("DROP TABLE IF EXISTS vote_ballot_picks")
    op.execute("DROP TABLE IF EXISTS vote_ballots")
    op.execute("DROP TABLE IF EXISTS vote_settings")
