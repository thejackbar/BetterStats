"""
DDL for competitions and the association a grade is played under (migration 282).

THE ONE COPY. Both alembic (versions/282_stats_by_competition.py) and the
lifespan mirror in main.py run this same list, in this order, per the
vote_medal_ddl rule. Every statement is idempotent, because the lifespan
re-runs the whole list on every boot.

WHY THERE ARE TWO DIFFERENT THINGS HERE, AND NOT ONE:

  - **The ASSOCIATION is synced and exact.** Every grade Cricket Australia
    returns carries `grade.owningOrganisation` — the association that runs it
    — on `/fixturesladders/organisations/{org}/teams?seasonId=`, which is the
    payload sync ALREADY fetches to seed its grades and has been discarding.
    Verified live back to Summer 1975/76, so it costs no extra API call now
    and no extra call to backfill a club's whole history. Applecross's
    2025/26 grades resolve to three associations (WASTCA, Perth Scorchers
    Women's League, WA Integrated Cricket League) with no guessing at all.

  - **The COMPETITION is the club's own, because CA does not publish one.**
    PlayHQ's public site groups a season's grades under a competition
    ("Border Cup", "VCV Over 60s Competition", "WASTCA Seniors"), and that
    level is NOT in the Grassroots feed: it is absent from the seasons list,
    the teams list, the grade record, the grade's match list and the full
    match record, and every plausible competition endpoint on the proxy
    answers 403. PlayHQ's own API, where the name lives, is behind a
    CloudFront WAF that this app is documented never to build a club-facing
    button on. So a competition here is a NAMED GROUP OF GRADES the club
    owns, seeded from the association so most clubs need do nothing, and
    editable for the club the association alone cannot separate — Veterans
    Cricket Victoria runs Border Cup, the Over 60s competition and the Echuca
    divisions, and one bucket for all three is the reported bug.

`grades.competition_id` is ON DELETE SET NULL: deleting a competition
un-groups its grades, it never deletes a grade or a game. A grade on no
competition is not filtered out of anything unfiltered — it simply has no
competition to be found under, the same way an uncategorised grade behaves.
"""

STATEMENTS: list[str] = [
    # The association that runs the grade, straight from CA. Three columns
    # rather than a lookup table: an association has no rows of its own here,
    # it is a label plus the CA org GUID that identifies it across clubs, and
    # a table would be a join for nothing. The GUID is what makes two clubs'
    # spellings of one association resolve to the same thing.
    "ALTER TABLE grades ADD COLUMN IF NOT EXISTS association_id TEXT",
    "ALTER TABLE grades ADD COLUMN IF NOT EXISTS association_name TEXT",
    "ALTER TABLE grades ADD COLUMN IF NOT EXISTS association_short_name TEXT",
    """
    CREATE TABLE IF NOT EXISTS club_competitions (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id  UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name             TEXT NOT NULL,
        -- The association this competition sits under, where it has one. Kept
        -- so a seeded competition can be recognised on a later sync (and so a
        -- club running two competitions under one association still reads as
        -- that association's). NULL for a competition a club invented that
        -- spans associations.
        association_id   TEXT,
        association_name TEXT,
        -- The order the club reads its own competitions in. NULL sorts after
        -- every ordered row, the same rule grades.display_order follows.
        display_order    INTEGER,
        -- Set on a row this app seeded, cleared the moment a person edits it,
        -- so re-seeding can never overwrite a club's own naming.
        is_seeded        BOOLEAN NOT NULL DEFAULT false,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # A club may not hold two competitions under one name — the name is what a
    # person picks from a filter, so two identical entries are unreadable.
    # Case-folded, because "Border Cup" and "border cup" are one competition.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_club_competitions_org_name
        ON club_competitions (organisation_id, lower(name))
    """,
    """
    ALTER TABLE grades ADD COLUMN IF NOT EXISTS competition_id UUID
        REFERENCES club_competitions(id) ON DELETE SET NULL
    """,
    # The two reads this feature makes of `grades`: resolve a club's grade rows
    # to their competition, and list the associations it plays under.
    """
    CREATE INDEX IF NOT EXISTS ix_grades_competition
        ON grades (competition_id) WHERE competition_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_grades_association
        ON grades (association_id) WHERE association_id IS NOT NULL
    """,
]

DOWNGRADE: list[str] = [
    "DROP INDEX IF EXISTS ix_grades_association",
    "DROP INDEX IF EXISTS ix_grades_competition",
    "ALTER TABLE grades DROP COLUMN IF EXISTS competition_id",
    "DROP TABLE IF EXISTS club_competitions",
    "ALTER TABLE grades DROP COLUMN IF EXISTS association_short_name",
    "ALTER TABLE grades DROP COLUMN IF EXISTS association_name",
    "ALTER TABLE grades DROP COLUMN IF EXISTS association_id",
]
