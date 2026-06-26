"""Marketing club directory — recompute UTM with the three-word rule

The UTM default now uses up to the first THREE words before 'Cricket Club'
(split on a space or hyphen), e.g. 'Swan Athletic Caversham CC' →
'swan-athletic-caversham-cricket-club'. Recompute existing clubs to match, but
only rows whose ``utm_code`` still equals a previous AUTO value (the old
first-word formula OR the two-word formula), so a hand-edited UTM is never
clobbered.

Revision ID: 106
Revises: 105
Create Date: 2026-06-25
"""
import re
from alembic import op
import sqlalchemy as sa


revision = '106'
down_revision = '105'
branch_labels = None
depends_on = None


def _tokens(name: str) -> list:
    """Cleaned words before 'cricket club', split on space or hyphen."""
    raw = (name or "").strip()
    if not raw:
        return []
    prefix = re.split(r"(?i)\bcricket[\s-]+club\b", raw, maxsplit=1)[0]
    base = prefix if prefix.strip() else raw
    out = []
    for part in re.split(r"[\s-]+", base):
        tok = re.sub(r"[^a-z0-9]", "", part.lower())
        if tok and tok not in ("cricket", "club"):
            out.append(tok)
    return out


def _old1_utm(name: str) -> str:
    """Original default: first space-delimited word only, alphanumerics."""
    raw = (name or "").strip()
    if not raw:
        return ""
    token = re.sub(r"[^a-z0-9]", "", raw.split(" ")[0].lower())
    return f"{token}-cricket-club" if token else ""


def _join(tokens: list, n: int) -> str:
    return ("-".join(tokens[:n]) + "-cricket-club") if tokens else ""


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name, utm_code FROM marketing_clubs")).fetchall()
    for r in rows:
        toks = _tokens(r.name)
        new = _join(toks, 3)
        prior_auto = {_old1_utm(r.name), _join(toks, 2)}   # 1-word and 2-word autos
        if new and r.utm_code in prior_auto and new != r.utm_code:
            conn.execute(
                sa.text("UPDATE marketing_clubs SET utm_code = :u, updated_at = NOW() WHERE id = :id"),
                {"u": new, "id": r.id})


def downgrade() -> None:
    pass
