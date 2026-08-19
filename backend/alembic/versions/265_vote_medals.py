"""BetterSelect votes — a club runs several medals, each with its own settings.

``vote_settings`` had ``organisation_id`` as its PRIMARY KEY, so one club held
exactly one ballot shape, one voter mode, one counting method and one public
link. A club that runs a Senior Club Champion on 3-2-1 alongside a Colts medal
on 5-4-3-2-1 had no way to express it, and its two counts could only ever be
told apart by filtering the one leaderboard down to a grade after the fact.

``vote_medals`` is that record. Every setting that lived on ``vote_settings``
moves across UNCHANGED IN NAME, which is what lets ``votes.effective_config``
read a medal with no edit — plus:

  * ``name`` — what the club calls it ("Club Champion", "Colts Medal").
  * ``grade_ids`` — the grades it counts, as a JSONB list of uuid strings.
    EMPTY MEANS EVERY GRADE, deliberately: that is what a club's one medal
    means before anyone has thought about grades, and it is what the migrated
    row has to mean so an existing count doesn't narrow the day this ships.
    A JSONB list rather than a real uuid[] with an FK, matching
    ``organisations.module_overrides`` and ``stats_grade_categories`` — a
    grade later deleted or merged away just stops matching, instead of
    blocking the delete or silently taking the medal with it.
  * ``position`` — the club's own ordering of its medals.

``vote_ballots``, ``vote_fixture_overrides`` and ``vote_nudges`` each gain a
``medal_id``. A ballot belongs to ONE medal: a fixture counting towards two
medals collects a separate ballot for each, so a 3-2-1 medal and a 5-4-3-2-1
medal can genuinely disagree about who was best (per direct instruction).
That means the two "one live ballot per voter per fixture" partial uniques are
rebuilt with ``medal_id`` in front of them, and ``vote_fixture_overrides``
moves from a ``fixture_id`` primary key to ``(medal_id, fixture_id)`` — a lock
or a source override is a decision about one medal's count, not about the
fixture in the abstract.

MIGRATION OF AN EXISTING CLUB: its ``vote_settings`` row becomes its first
medal, carrying its settings AND ``link_token`` across, so every ballot already
cast still counts and the link already shared with players this season keeps
working. ``vote_settings`` itself is left in place as history and nothing reads
it after this — the same call migration 230 made for ``club_objectives.plan``.
A club with ballots or overrides but no settings row (an admin entering paper
votes never had to open the settings screen) gets a medal too, or the NOT NULL
below would have nothing to point those rows at.

Revision ID: 265
Revises: 264
Create Date: 2026-08-19
"""
from alembic import op

revision = '265'
down_revision = '264'
branch_labels = None
depends_on = None


from app.services.vote_medal_ddl import VOTE_MEDAL_STATEMENTS


def upgrade() -> None:
    for stmt in VOTE_MEDAL_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("ALTER TABLE vote_fixture_overrides DROP CONSTRAINT IF EXISTS vote_fixture_overrides_pkey")
    op.execute("ALTER TABLE vote_ballots DROP COLUMN IF EXISTS medal_id")
    op.execute("ALTER TABLE vote_fixture_overrides DROP COLUMN IF EXISTS medal_id")
    op.execute("ALTER TABLE vote_nudges DROP COLUMN IF EXISTS medal_id")
    op.execute("DROP TABLE IF EXISTS vote_medals")
