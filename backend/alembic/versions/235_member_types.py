"""Membership is MULTI-valued and scoped; roles and honours are separate axes.

Three independent things had been collapsed into one single-valued
`fee_members.member_category`, whose vocabulary also mixed them:

  1. What KIND of member someone is. Several at once — a dad who plays and
     whose kid plays is a Senior Player AND a Parent — and split internal
     (Senior Player, Junior Player, Parent, Social Member) vs external
     (Sponsor Contact, External Contact), because an external contact is not
     someone the club counts as a member.
  2. What they DO: Volunteer, Committee member, Official. Already multi-valued
     through volunteer_roles / committee_terms, and needing NO change here. An
     Official in particular need not be a member at all — a panel umpire is a
     person the club records, not someone who joined it.
  3. HONOURS. Life Membership is bestowed on a member of any type, so it is
     neither a type nor a role. It stays on the person spine as
     `is_life_member` (+ the new `life_member_since`) rather than moving to
     `player_achievements`, which keys on player_id and so could not hold a
     life member who never played.

So: `membership_types` (the club's own catalogue, migration 175) gains a
`scope`, and `member_membership_types` makes holding it multi-valued.
`fee_members.membership_type_id` STAYS as the PRIMARY type — BetterFees has to
bill one tier, and a Senior Player who is also a Parent pays senior subs. Same
shape as committee_task_assignees keeping assigned_to_member_id (migration 220).

`member_category` is NOT dropped. It is left alone as history and still read as
a fallback, so a club tagged before this never loses a filter.

Revision ID: 235
Revises: 234
"""
from alembic import op

revision = "235"
down_revision = "234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE membership_types ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'internal'"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS member_membership_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            membership_type_id UUID NOT NULL REFERENCES membership_types(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (member_id, membership_type_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_member_membership_types_org "
        "ON member_membership_types(organisation_id, membership_type_id)"
    )
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS life_member_since DATE")
    op.execute(EXTERNAL_SCOPE)
    op.execute(BACKFILL_PRIMARY)


# A club that already has these by name gets them scoped without touching the
# ones it named itself. Matched on the name because scope is new and nothing
# else distinguishes them yet.
EXTERNAL_SCOPE = """
    UPDATE membership_types SET scope = 'external'
    WHERE lower(name) IN ('sponsor contact', 'external contact', 'third party', 'contractor')
      AND scope <> 'external'
"""

# Every member already carrying a primary type holds it in the set too, so the
# join table is the one place the full answer lives from here on. Guarded on the
# member having no rows yet, NOT on the pair: this is mirrored into main.py's
# lifespan and re-runs on every boot, and a per-pair guard would re-add a type
# the club has since unticked.
BACKFILL_PRIMARY = """
    INSERT INTO member_membership_types (organisation_id, member_id, membership_type_id)
    SELECT fm.organisation_id, fm.id, fm.membership_type_id
    FROM fee_members fm
    WHERE fm.membership_type_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM member_membership_types a WHERE a.member_id = fm.id
      )
    ON CONFLICT (member_id, membership_type_id) DO NOTHING
"""


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS member_membership_types")
    op.execute("ALTER TABLE membership_types DROP COLUMN IF EXISTS scope")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS life_member_since")
