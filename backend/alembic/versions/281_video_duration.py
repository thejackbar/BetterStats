"""How long an instructional video runs

The length was being typed into the title by hand ("Merge Players (2m 45s)"),
which puts it in the wrong place: it is a property of the video, not part of
its name, and a title carrying it cannot be shown separately or read by a
search engine.

Stored in seconds. The display format is then decided in one place, and the
VideoObject on the video's page can carry a real ISO-8601 duration.

Its own migration rather than an edit to 280, which is already applied in
production.

Revision ID: 281
Revises: 280
Create Date: 2026-08-28
"""
from alembic import op

from app.services.instructional_video_ddl import (  # noqa: E402
    DURATION_DOWNGRADE,
    DURATION_STATEMENTS,
)

revision = "281"
down_revision = "280"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in DURATION_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DURATION_DOWNGRADE:
        op.execute(stmt)
