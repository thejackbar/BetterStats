"""Gender on the person spine, and a detail line on the life-membership honour.

`fee_members.gender` — the Directory can filter on gender, so it has to be able
to record one. It could not: gender lived ONLY on `players`, so a social member,
a parent or a sponsor's contact had nowhere to carry it.

Read precedence is the same one email and mobile already use in
`directory.list_people`: the member's own value, falling back to the linked
player's. So a synced player's gender shows through without being copied, and
anything recorded here is the club's own answer for that person. Writing always
goes to the spine — Stats owns `players.gender` and the Directory does not
reach across to it.

`fee_members.life_member_detail` — free text beside the life-membership date,
for whatever the club records against the honour. A life member NUMBER is the
usual one. Deliberately not parsed or validated: clubs number these however
they always have, and a format guess would reject a real one.

Revision ID: 249
Revises: 248
"""
from alembic import op

revision = "249"
down_revision = "248"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS gender TEXT")
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS life_member_detail TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS life_member_detail")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS gender")
