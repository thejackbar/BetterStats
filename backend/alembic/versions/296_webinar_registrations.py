"""Registrations for a dated BetterCricket webinar

The Meta ad campaign optimises for the `CompleteRegistration` pixel event,
which cannot fire on a third-party domain — so the registration has to happen
on betterat.cricket and hand the viewing link over afterwards, rather than the
ad pointing straight at StreamYard.

This is the lead behind each one. Deliberately NOT `club_onboarding_requests`:
that table is the queue of clubs asking to be onboarded, and somebody who has
signed up to watch a demo has not asked for that. Mixing them would put a
hundred curious registrants in front of the staff who work the onboarding list.

Revision ID: 296
Revises: 295
"""
from alembic import op

from app.services.webinar_ddl import DOWNGRADE, STATEMENTS

revision = "296"
down_revision = "295"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
