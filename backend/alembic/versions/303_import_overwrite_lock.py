"""An overwrite import can supersede a wrong Cricket Australia match, locked

A club whose PlayHQ (Cricket Australia) records are wrong for some seasons can
import its own correct records and, in the CSV import's overwrite mode, have
each imported match take over the incorrect synced one:

* manual_games.pairing_locked — a human set this pairing, so
  match_pairing.reconcile_org never re-derives or flips it and a future sync
  cannot bring the incorrect synced copy back;
* seasons.import_authoritative — the club has re-sourced this whole season from
  its import, so v_effective_player_season_stats counts the import's own
  matches for it and steps CA's season summary aside, correcting the totals.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290, 292 and 293 also
run. Every statement is idempotent.

Revision ID: 303
Revises: 302
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "303"
down_revision = "302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # 287 owns the columns and the views; undoing it (superseded_ddl.DOWNGRADE)
    # removes these too.
    pass
