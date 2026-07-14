"""Fix FK cascade drift on legacy per-game/per-player stat tables.

Deleting a club (DELETE /club-admin/super/clubs/{id}) cascades
organisations -> seasons -> grades -> games/players -> {per-game stat
tables}. Live production hit a real ForeignKeyViolationError deleting a
club with real data: "partnerships_game_id_fkey" was NOT ON DELETE CASCADE
in the actual database, even though app/models/db.py's ORM column has
always declared `ondelete="CASCADE"` — the model's declared intent was
never applied to the live schema (these are pre-dating-Alembic tables;
`grep`ing every migration file confirms no migration has ever touched
these constraints by name). Reconciling every FK on the same lineage of
legacy tables here, not just the one that happened to be hit first —
these were plausibly all created in the same original batch and share
the same risk.

Safe on a live, populated table: builds the corrected constraint
`NOT VALID` (near-instant, brief lock) then `VALIDATE CONSTRAINT`
separately (a background scan under a SHARE UPDATE EXCLUSIVE lock, doesn't
block concurrent reads/writes) — the standard safe pattern for adding a FK
to an already-populated table. Checks `pg_constraint.confdeltype` first so
a constraint already correct is left untouched (cheap no-op on every
app-restart re-run of this same block via main.py's lifespan mirror).

Revision ID: 142
Revises: 141
Create Date: 2026-07-14
"""
from alembic import op


revision = '142'
down_revision = '141'
branch_labels = None
depends_on = None


FIX_FK_CASCADES_SQL = r"""
DO $$
DECLARE
  spec RECORD;
  cname TEXT;
BEGIN
  FOR spec IN SELECT * FROM (VALUES
    ('batting_innings',  'game_id',    'games',   'c'),
    ('batting_innings',  'player_id',  'players', 'c'),
    ('bowling_spells',   'game_id',    'games',   'c'),
    ('bowling_spells',   'player_id',  'players', 'c'),
    ('fielding_stats',   'game_id',    'games',   'c'),
    ('fielding_stats',   'player_id',  'players', 'c'),
    ('bowler_wickets',   'game_id',    'games',   'c'),
    ('bowler_wickets',   'bowler_id',  'players', 'c'),
    ('bowler_wickets',   'fielder_id', 'players', 'n'),
    ('game_appearances', 'game_id',    'games',   'c'),
    ('game_appearances', 'player_id',  'players', 'c'),
    ('fall_of_wickets',  'game_id',    'games',   'c'),
    ('fall_of_wickets',  'player_id',  'players', 'n'),
    ('partnerships',     'game_id',    'games',   'c'),
    ('partnerships',     'batter1_id', 'players', 'n'),
    ('partnerships',     'batter2_id', 'players', 'n'),
    ('milestones',       'player_id',  'players', 'c'),
    ('milestones',       'game_id',    'games',   'n'),
    ('fee_match_days',   'game_id',    'games',   'c')
  ) AS t(tbl, col, target, mode)
  LOOP
    -- Skip cleanly if the table doesn't exist on this deploy yet (e.g. BetterFees not migrated).
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = spec.tbl AND relkind = 'r') THEN
      CONTINUE;
    END IF;
    cname := spec.tbl || '_' || spec.col || '_fkey';
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      WHERE t.relname = spec.tbl AND c.conname = cname AND c.confdeltype = spec.mode
    ) THEN
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', spec.tbl, cname);
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(id) ON DELETE %s NOT VALID',
        spec.tbl, cname, spec.col, spec.target,
        CASE spec.mode WHEN 'c' THEN 'CASCADE' ELSE 'SET NULL' END
      );
      EXECUTE format('ALTER TABLE %I VALIDATE CONSTRAINT %I', spec.tbl, cname);
    END IF;
  END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(FIX_FK_CASCADES_SQL)


def downgrade() -> None:
    # Not reversed — these constraints should always have been CASCADE/SET
    # NULL per the ORM model; there's no correct "undo" back to a broken state.
    pass
