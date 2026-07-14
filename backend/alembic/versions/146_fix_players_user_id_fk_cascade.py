"""Fix FK cascade drift on players.user_id -> users(id).

Deleting a user (DELETE /club-admin/super/users/{id}) does a plain
db.delete(user), on the documented assumption that club_memberships cascades
(it does — confdeltype 'c') and every other FK to users(id) is SET NULL. Live
production confirmed players_user_id_fkey was actually NO ACTION
(confdeltype 'a'): any user with a linked players row hit an unhandled
ForeignKeyViolationError and the whole delete silently rolled back — same
"looks like nothing happened" symptom as the migration 142 club-delete
incident, and the same root cause (a pre-Alembic legacy constraint whose
live definition was never reconciled with intent).

players.user_id itself is a retained-but-unused legacy column (see
app/models/db.py's Player model comment — "claimed / user_id retained as
columns but no longer used in business logic", and it isn't even declared as
a ForeignKey in the ORM). SET NULL is the correct behaviour: deleting a user
account should never be blocked by this dead column, matching every other
non-cascade FK to users(id) (see the live confdeltype audit that found this).

Safe on a live, populated table: builds the corrected constraint NOT VALID
(near-instant, brief lock) then VALIDATE CONSTRAINT separately (a background
scan under a SHARE UPDATE EXCLUSIVE lock, doesn't block concurrent reads/
writes). Checks pg_constraint.confdeltype first so an already-correct
constraint is left alone (cheap no-op on every app-restart re-run via
main.py's idempotent mirror) — same pattern as migration 142.

Revision ID: 146
Revises: 145
Create Date: 2026-07-14
"""
from alembic import op


revision = '146'
down_revision = '145'
branch_labels = None
depends_on = None


FIX_PLAYERS_USER_ID_FK_SQL = r"""
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'players' AND c.conname = 'players_user_id_fkey' AND c.confdeltype = 'n'
  ) THEN
    ALTER TABLE players DROP CONSTRAINT IF EXISTS players_user_id_fkey;
    ALTER TABLE players ADD CONSTRAINT players_user_id_fkey
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL NOT VALID;
    ALTER TABLE players VALIDATE CONSTRAINT players_user_id_fkey;
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(FIX_PLAYERS_USER_ID_FK_SQL)


def downgrade() -> None:
    # Not reversed — NO ACTION was never the intended behaviour; there's no
    # correct "undo" back to a broken state.
    pass
