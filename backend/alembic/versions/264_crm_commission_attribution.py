"""Commission attribution on a CRM deal — who earned the club, not who holds it

Assignment (crm_deals.owner_user_id) says who is WORKING a club and a super
admin may move it at will. Commission attribution is a separate, stickier
fact: the first sales rep to do real sales work on the club EARNED it, and
reassigning the club afterwards does not take that away.

The qualifying actions are deliberately narrow — logging a call outcome that
is not a General Note, or sending an email to one of the club's contacts.
A note, or a General Note outcome, is someone writing something down; it
claims nothing about the club and must not attribute it.

Backfilled from the activity rows already recorded, so a rep who has been
working clubs for weeks is attributed on deploy rather than only from the
next call onwards.

Revision ID: 264
Revises: 263
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = '264'
down_revision = '263'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_rep_user_id UUID "
        "REFERENCES users(id) ON DELETE SET NULL"
    ))
    conn.execute(sa.text(
        "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_attributed_at TIMESTAMPTZ"
    ))
    # 'call' | 'email' — which action earned it. The activity row itself is
    # the full audit trail; this is enough to read the reason without going
    # looking for it.
    conn.execute(sa.text(
        "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_attributed_via TEXT"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_crm_deals_commission_rep "
        "ON crm_deals (commission_rep_user_id) WHERE commission_rep_user_id IS NOT NULL"
    ))

    # Backfill: the EARLIEST qualifying activity by a sales-role user wins,
    # matching the live rule (first action attributes, and nothing later
    # moves it). Only deals with nothing attributed yet are touched, so
    # re-running this is a no-op.
    conn.execute(sa.text("""
        WITH qualifying AS (
            SELECT DISTINCT ON (a.deal_id)
                   a.deal_id,
                   a.created_by_user_id,
                   a.occurred_at,
                   CASE WHEN a.type = 'email' THEN 'email' ELSE 'call' END AS via
            FROM crm_activities a
            JOIN club_memberships cm ON cm.user_id = a.created_by_user_id AND cm.role = 'sales'
            WHERE a.deal_id IS NOT NULL
              AND a.created_by_user_id IS NOT NULL
              AND (
                    a.type = 'email'
                 OR (a.type = 'call' AND (a.outcome IS NULL OR a.outcome <> 'general_note'))
              )
            ORDER BY a.deal_id, a.occurred_at ASC
        )
        UPDATE crm_deals d
           SET commission_rep_user_id = q.created_by_user_id,
               commission_attributed_at = q.occurred_at,
               commission_attributed_via = q.via
          FROM qualifying q
         WHERE q.deal_id = d.id
           AND d.commission_rep_user_id IS NULL
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_crm_deals_commission_rep"))
    for col in ("commission_rep_user_id", "commission_attributed_at", "commission_attributed_via"):
        conn.execute(sa.text(f"ALTER TABLE crm_deals DROP COLUMN IF EXISTS {col}"))
