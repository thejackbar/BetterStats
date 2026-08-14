"""Fix fk_fee_members_player_same_org: SET NULL was nulling organisation_id too.

Migration 223 added a composite FK ``fee_members (organisation_id, player_id)
-> players (organisation_id, id) ON DELETE SET NULL`` so a member row could
never point at another club's player. For a MULTI-column foreign key,
Postgres's plain ``ON DELETE SET NULL`` nulls EVERY column in the FK on
delete — not just the one that's actually supposed to go nullable. So
deleting a linked player (merge_players' own ``DELETE FROM players``, the
same op undo-import and claim-fill-in also use) tried to null out
``organisation_id`` too, which is NOT NULL — the delete aborted with
``NotNullViolationError``, surfaced to the operator as "a data conflict
blocked it" on an otherwise ordinary merge.

Postgres 15 (this project's own DB image, see docker-compose.yml) added
per-column ``SET NULL (column_list)`` for exactly this composite-FK case:
``ON DELETE SET NULL (player_id)`` nulls only ``player_id``, leaving
``organisation_id`` — and the row's club membership — untouched.

Checks ``pg_constraint.confdelsetcols`` first so an already-corrected
constraint is left alone (cheap no-op on every app-restart re-run via
main.py's idempotent lifespan mirror). Recreated NOT VALID, same as 223 —
this only changes the ON DELETE behaviour, not whether existing rows satisfy
the FK, so there's nothing here for VALIDATE CONSTRAINT to newly check.

Revision ID: 253
Revises: 252
"""
from alembic import op

revision = "253"
down_revision = "252"
branch_labels = None
depends_on = None


FIX_SQL = r"""
DO $$
DECLARE
  player_id_attnum smallint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'fee_members' AND relkind = 'r') THEN
    RETURN;
  END IF;

  SELECT attnum INTO player_id_attnum
  FROM pg_attribute
  WHERE attrelid = 'fee_members'::regclass AND attname = 'player_id';

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_fee_members_player_same_org'
      AND conrelid = 'fee_members'::regclass
      AND confdelsetcols = ARRAY[player_id_attnum]
  ) THEN
    ALTER TABLE fee_members DROP CONSTRAINT IF EXISTS fk_fee_members_player_same_org;
    ALTER TABLE fee_members
      ADD CONSTRAINT fk_fee_members_player_same_org
      FOREIGN KEY (organisation_id, player_id)
      REFERENCES players (organisation_id, id)
      ON DELETE SET NULL (player_id)
      NOT VALID;
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(FIX_SQL)


def downgrade() -> None:
    # Not reversed — the old behaviour (nulling organisation_id, which
    # violates its own NOT NULL constraint the moment it fires) was a bug,
    # not a state worth restoring.
    pass
