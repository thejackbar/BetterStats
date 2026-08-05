"""Link an imported season row to a real grade, not just a free-text label.

Import Stats could match a sheet's grade label to a grade the club already had,
or file it under its own label — but it could never CREATE the grade. A club
importing decades of history from before it ever synced has no grades to match
against, so every historical grade lived only as text on
``imported_stats.grade_label``: invisible to the grade filter, to Merge Grades,
and to everything else that reads the grades table.

``imported_stats.grade_id`` is the link, mirroring what ``afl_imported_stats``
already carries. It stays nullable — a row whose season is still unresolved has
no season for a grade to hang off (``grades.season_id`` is required), so that
row keeps its label as text exactly as before. ON DELETE SET NULL so removing a
grade downgrades the row to its label rather than destroying the import.

Revision ID: 223
Revises: 222
"""
from alembic import op

revision = "223"
down_revision = "222"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE imported_stats ADD COLUMN IF NOT EXISTS grade_id UUID")
    # Guarded so a re-run on a database that already has the constraint (via the
    # idempotent lifespan mirror in main.py) is a no-op rather than an error.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'imported_stats_grade_id_fkey'
            ) THEN
                ALTER TABLE imported_stats
                    ADD CONSTRAINT imported_stats_grade_id_fkey
                    FOREIGN KEY (grade_id) REFERENCES grades (id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_imported_stats_grade_id ON imported_stats (grade_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_imported_stats_grade_id")
    op.execute("ALTER TABLE imported_stats DROP COLUMN IF EXISTS grade_id")
