"""Marketing — association short code (acronym) for shortcode search

PlayHQ has no association abbreviation, so derive one from the name (first letter
of each alphabetic word), e.g. 'West Australian Suburban Turf Cricket Association'
→ 'WASTCA'. Stored on the registry so the 'Association contains' filter and the
multi-select can be searched by shortcode.

Revision ID: 108
Revises: 107
Create Date: 2026-06-25
"""
import re
from alembic import op
import sqlalchemy as sa


revision = '108'
down_revision = '107'
branch_labels = None
depends_on = None


def _acronym(name: str) -> str:
    return "".join(w[0] for w in re.findall(r"[A-Za-z]+", name or "")).upper()


def upgrade() -> None:
    op.add_column('marketing_associations', sa.Column('short_code', sa.Text(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM marketing_associations")).fetchall()
    for r in rows:
        code = _acronym(r.name)
        if code:
            conn.execute(sa.text("UPDATE marketing_associations SET short_code = :c WHERE id = :id"),
                         {"c": code, "id": r.id})


def downgrade() -> None:
    op.drop_column('marketing_associations', 'short_code')
