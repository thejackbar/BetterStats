"""Merge BetterComms Lists into Segments — a segment gains a static member set

"Lists" (a hand-picked roll call) and "Segments" (a live rule) were two audience
concepts a user had to learn separately. They are folded into one: a Segment now
also carries a frozen, hand-picked STATIC set (`comms_segment_members`), and the
audience it resolves to is the UNION of its rule matches and that static set.

Every existing list is migrated to a pure-static segment (carrying its
`source`/`origin` and a `legacy_list_id` back-link); the `comms_lists` /
`comms_list_members` tables are kept for history and `saved_list` campaign
back-compat. The auto-list producers (CRM Sales Pipeline, Wizard Clubs, Club
Admin Users) are repointed to create static segments, so `wizard_club_lists`
gains a `segment_id`.

The DDL is the ONE copy in services/comms_segment_ddl.py, run by both this
migration and main.py's lifespan mirror, every statement idempotent.

Numbered 304 after checking origin/main, which had reached 303
(import_overwrite_lock) — two migrations sharing a revision id break Alembic
outright.
"""

from alembic import op
from sqlalchemy import text

from app.services.comms_segment_ddl import STATEMENTS

revision = "304"
down_revision = "303"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    for stmt in STATEMENTS:
        conn.execute(text(stmt))


def downgrade():
    conn = op.get_bind()
    # Drop only what this migration added; comms_lists / comms_list_members are
    # untouched (this migration never dropped them), and a segment migrated from
    # a list is left in place — removing it would lose a club's own edits since.
    conn.execute(text("DROP TABLE IF EXISTS comms_segment_members"))
    conn.execute(text("DROP INDEX IF EXISTS uq_comms_segments_legacy_list"))
    conn.execute(text("DROP INDEX IF EXISTS uq_wizard_club_lists_segment_club"))
    conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS legacy_list_id"))
    conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS origin"))
    conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS source"))
    conn.execute(text("ALTER TABLE wizard_club_lists DROP COLUMN IF EXISTS segment_id"))
