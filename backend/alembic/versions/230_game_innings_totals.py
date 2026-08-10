"""Games — the TRUE per-innings total, straight from Grassroots, not just SUM(batting_innings.runs)

BetterIQ's Team Analysis "par score" (and score-bands/chase-stats) card
computes "our runs" for a game as ``SUM(batting_innings.runs)`` — batter runs
only, excluding extras (byes, leg-byes, wides, no-balls). That's a documented
"close-but-not-exact" approximation that understates every team total by
roughly 10-25 runs.

Cricket Australia's Grassroots API scorecard payload (``/scores/matches/{id}
?responseModifier=includeScorecard``) carries the real figure on each
``innings[]`` entry — confirmed against the live-merge already reading it in
``routers/games.py::get_scorecard`` (``inn.get("runsScored")`` /
``inn.get("numberOfWicketsFallen")`` / ``inn.get("totalExtras")``) — but sync
has never persisted it; only the per-batter rows it derives from are stored.

``games.innings_totals`` (JSONB, nullable) holds one entry per innings:
``[{"innings_number": 1, "runs_scored": 162, "wickets": 7, "extras": 14}, …]``.
A JSONB array rather than fixed scalar columns because a game can carry 1-4
innings (a two-day match bats each side twice) with no fixed shape to pin
scalar columns to. There is no clean byes/leg-byes/wides/no-balls breakdown
at the innings level in this payload (only the single combined
``totalExtras``) — the ball-by-ball ``/balls`` endpoint carries that
breakdown but is live-scored-matches-only, so ``extras`` here is the combined
total, not a further breakdown.

Prospective-only, by explicit decision: this migration only adds the column.
Nothing here (or in the accompanying sync.py change) forces a re-sync or
backfills an already-synced game — that would mean an hour+ Full Rebuild per
club across 50+ production databases, out of scope here. A game synced (or
re-synced) after this ships gets the real figure; an older, not-yet-revisited
game keeps NULL, and every reader falls back to the existing bat-only sum for
exactly that case (see services/iq_team.py's `_per_game`).

Revision ID: 230
Revises: 229
"""
from alembic import op

revision = "230"
down_revision = "229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE games DROP COLUMN IF EXISTS innings_totals"
    )
