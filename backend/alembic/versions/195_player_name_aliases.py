"""Player name aliases — a former/alternate name that still resolves to the
right player.

A live feed (Play.Cricket team list, Grassroots scorecard) identifies a
participant by name as well as GUID, and a club sometimes renames a player in
BetterCricket (a preferred name, a marriage-name change) after they've already
appeared under their old name in matches. The old name no longer textually
matches anything on the player's record, so the existing GUID-first /
surname-and-initial-fallback matching in services/lineups.py and
routers/games.py's live scorecard merge can both miss them.

`player_name_aliases` is an explicit, org-scoped `alias_key -> player_id`
map. Auto-seeded with the OLD name whenever a rename happens (source
'rename'); an admin can also add one by hand (source 'manual') for a rename
that predates this table, or any other name variant CA's feed happens to use.

Revision ID: 195
Revises: 194
Create Date: 2026-07-30
"""
from alembic import op

revision = '195'
down_revision = '194'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS player_name_aliases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            alias_name TEXT NOT NULL,
            alias_key TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_player_name_alias_key "
        "ON player_name_aliases(organisation_id, alias_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_player_name_aliases_player "
        "ON player_name_aliases(player_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS player_name_aliases")
