"""Grade-scoped BetterImport reconciliation.

The reconciler (``services/import_reconcile.py``) previously compared a club's
uploaded totals against the player's Grassroots (GR) coverage **across every
grade**, even when the upload itself was explicitly scoped to one grade (the
CSV's ``Grade`` column, stored as ``imported_stats.grade_label``). For a club
that keeps detailed stats for one grade only (very common in Premier
cricket — a "1st Grade" honour board with no equivalent for the lower grades),
this produced two compounding bugs:

  * the residual amount itself was wrong — it was diluted by subtracting the
    player's *other*-grade GR history, which the uploaded sheet never claimed
    to cover;
  * grade-filtered leaderboards (``aggregations.py``'s ``grade_id``/
    ``grade_name`` branches) never read the import residual at all, since
    every delta was written with no grade attribution, so a club's
    grade-scoped historical total never appeared once a grade filter was
    applied — only on the ungraded "All Seasons" profile total.

``import_effective_deltas.grade_label`` closes this: a season-scope delta
already has an exact ``grade_id`` (one real ``grades`` row for that season),
but a career-scope residual spans many seasons' worth of same-named grades
(a new "1st Grade" ``grades`` row is minted every season — see the "Cross-Club
Grade Collision Fix" era notes), so it's tagged by grade *name* instead,
matched the same fuzzy/merge-aware way ``aggregations._GRADE_MATCH`` already
matches a grade filter against a grade row.

Non-breaking: NULL for every existing delta (ungraded imports keep reading
exactly as before); reconciler and leaderboard changes populate/consume it
going forward, with no destructive rewrite of already-committed data — a
re-run of ``reconcile_imported_totals`` (self-healing, wipe-and-rebuild by
design) picks up the fix for existing orgs.

Revision ID: 152
Revises: 151
Create Date: 2026-07-16
"""
from alembic import op


revision = '152'
down_revision = '151'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE import_effective_deltas ADD COLUMN IF NOT EXISTS grade_label TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE import_effective_deltas DROP COLUMN IF EXISTS grade_label")
