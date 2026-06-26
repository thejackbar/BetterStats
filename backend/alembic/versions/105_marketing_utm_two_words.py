"""Marketing club directory — recompute UTM with the two-word rule

The UTM default now uses the first ONE or TWO words before 'Cricket Club'
(split on a space or hyphen), e.g. 'Mount Lawley Cricket Club' →
'mount-lawley-cricket-club'. Recompute existing clubs to match, but only rows
whose ``utm_code`` still equals the OLD first-word formula (so a hand-edited UTM
is never clobbered).

Revision ID: 105
Revises: 104
Create Date: 2026-06-25
"""
import re
from alembic import op
import sqlalchemy as sa


revision = '105'
down_revision = '104'
branch_labels = None
depends_on = None


def _old_utm(name: str) -> str:
    """The previous default: first space-delimited word, alphanumerics only."""
    raw = (name or "").strip()
    if not raw:
        return ""
    token = re.sub(r"[^a-z0-9]", "", raw.split(" ")[0].lower())
    return f"{token}-cricket-club" if token else ""


def _new_utm(name: str) -> str:
    """The new default: first one/two words before 'cricket club', hyphen-joined."""
    raw = (name or "").strip()
    if not raw:
        return ""
    prefix = re.split(r"(?i)\bcricket[\s-]+club\b", raw, maxsplit=1)[0]
    base = prefix if prefix.strip() else raw
    tokens = []
    for part in re.split(r"[\s-]+", base):
        tok = re.sub(r"[^a-z0-9]", "", part.lower())
        if tok and tok not in ("cricket", "club"):
            tokens.append(tok)
    return ("-".join(tokens[:2]) + "-cricket-club") if tokens else ""


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name, utm_code FROM marketing_clubs")).fetchall()
    for r in rows:
        new = _new_utm(r.name)
        # Only touch rows still on the old auto value (i.e. not hand-edited).
        if new and r.utm_code == _old_utm(r.name) and new != r.utm_code:
            conn.execute(
                sa.text("UPDATE marketing_clubs SET utm_code = :u, updated_at = NOW() WHERE id = :id"),
                {"u": new, "id": r.id})


def downgrade() -> None:
    # One-way data recompute; nothing to reverse.
    pass
