"""The DDL behind vote medals (migration 265), in ONE place.

Every schema change in this codebase is applied twice: once by alembic, and
once idempotently by ``main.py``'s lifespan so the API boots against a database
alembic hasn't reached yet. Those two copies are normally hand-kept in step,
which is exactly how they drift. This one is a single list both sides run, in
the same order, so they cannot.

Every statement must therefore stay idempotent — the lifespan re-runs the whole
list on every boot. The backfill statements below are no-ops once a club
already has a medal, which is what makes that safe.
"""

VOTE_MEDAL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS vote_medals (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        link_token TEXT,
        enabled BOOLEAN NOT NULL DEFAULT false,
        require_pin BOOLEAN NOT NULL DEFAULT true,
        voter_mode TEXT NOT NULL DEFAULT 'players',
        ballot_values JSONB NOT NULL DEFAULT '[3,2,1]'::jsonb,
        counting_method TEXT NOT NULL DEFAULT 'rank',
        tie_policy TEXT NOT NULL DEFAULT 'share',
        allow_self_vote BOOLEAN NOT NULL DEFAULT false,
        allow_non_participants BOOLEAN NOT NULL DEFAULT false,
        auto_close_days INTEGER NOT NULL DEFAULT 7,
        eligibility_source TEXT NOT NULL DEFAULT 'scorecard',
        grade_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_medals_link_token "
    "ON vote_medals(link_token) WHERE link_token IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_vote_medals_org "
    "ON vote_medals(organisation_id, position)",

    "ALTER TABLE vote_ballots ADD COLUMN IF NOT EXISTS medal_id UUID "
    "REFERENCES vote_medals(id) ON DELETE CASCADE",
    "ALTER TABLE vote_fixture_overrides ADD COLUMN IF NOT EXISTS medal_id UUID "
    "REFERENCES vote_medals(id) ON DELETE CASCADE",
    "ALTER TABLE vote_nudges ADD COLUMN IF NOT EXISTS medal_id UUID "
    "REFERENCES vote_medals(id) ON DELETE CASCADE",

    # ── Backfill: one medal per club that already votes ─────────────────────
    # Named for the trophy most clubs running a 3-2-1 count call it. Every
    # setting rides across, link_token included, so the season in progress and
    # the link already in players' hands both survive.
    """
    INSERT INTO vote_medals (
        organisation_id, name, link_token, enabled, require_pin, voter_mode,
        ballot_values, counting_method, tie_policy, allow_self_vote,
        allow_non_participants, auto_close_days, eligibility_source
    )
    SELECT s.organisation_id, 'Club Champion', s.link_token, s.enabled,
           s.require_pin, s.voter_mode, s.ballot_values, s.counting_method,
           s.tie_policy, s.allow_self_vote, s.allow_non_participants,
           s.auto_close_days, s.eligibility_source
    FROM vote_settings s
    WHERE NOT EXISTS (
        SELECT 1 FROM vote_medals m WHERE m.organisation_id = s.organisation_id
    )
    """,
    # A club with ballots or overrides but no settings row — an admin typing in
    # paper votes never had to open the settings screen. Without this its rows
    # would have no medal to point at and the NOT NULL below would fail.
    """
    INSERT INTO vote_medals (organisation_id, name)
    SELECT DISTINCT o.organisation_id, 'Club Champion'
    FROM (
        SELECT organisation_id FROM vote_ballots
        UNION SELECT organisation_id FROM vote_fixture_overrides
        UNION SELECT organisation_id FROM vote_nudges
    ) o
    WHERE NOT EXISTS (
        SELECT 1 FROM vote_medals m WHERE m.organisation_id = o.organisation_id
    )
    """,
    # Each club has exactly one medal at this point, so the club is enough to
    # find it. DISTINCT ON keeps this correct on a re-run once a club has since
    # added a second medal — the first by position wins, which is the migrated
    # one. Only ever fills a NULL, so a ballot already cast against a specific
    # medal is never moved.
    """
    UPDATE vote_ballots b SET medal_id = m.id
    FROM (
        SELECT DISTINCT ON (organisation_id) organisation_id, id
        FROM vote_medals ORDER BY organisation_id, position, created_at
    ) m
    WHERE b.medal_id IS NULL AND m.organisation_id = b.organisation_id
    """,
    """
    UPDATE vote_fixture_overrides v SET medal_id = m.id
    FROM (
        SELECT DISTINCT ON (organisation_id) organisation_id, id
        FROM vote_medals ORDER BY organisation_id, position, created_at
    ) m
    WHERE v.medal_id IS NULL AND m.organisation_id = v.organisation_id
    """,
    """
    UPDATE vote_nudges n SET medal_id = m.id
    FROM (
        SELECT DISTINCT ON (organisation_id) organisation_id, id
        FROM vote_medals ORDER BY organisation_id, position, created_at
    ) m
    WHERE n.medal_id IS NULL AND m.organisation_id = n.organisation_id
    """,

    # ── Now the column can be required ──────────────────────────────────────
    "ALTER TABLE vote_ballots ALTER COLUMN medal_id SET NOT NULL",
    "ALTER TABLE vote_nudges ALTER COLUMN medal_id SET NOT NULL",
    "ALTER TABLE vote_fixture_overrides ALTER COLUMN medal_id SET NOT NULL",

    # ── One ballot per voter per fixture PER MEDAL ──────────────────────────
    "DROP INDEX IF EXISTS uq_vote_ballot_player",
    "DROP INDEX IF EXISTS uq_vote_ballot_name",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_medal_player "
    "ON vote_ballots(medal_id, fixture_id, voter_player_id) "
    "WHERE voter_player_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vote_ballot_medal_name "
    "ON vote_ballots(medal_id, fixture_id, lower(voter_name)) "
    "WHERE voter_player_id IS NULL AND voter_name IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_vote_ballots_medal_fixture "
    "ON vote_ballots(medal_id, fixture_id)",

    # ── A lock/source override belongs to one medal's count ─────────────────
    # DROP-then-ADD unconditionally: the DROP IF EXISTS is what makes the ADD
    # safe to re-run, whether it is removing the original fixture_id key or the
    # composite one a previous run of this list already built.
    "ALTER TABLE vote_fixture_overrides DROP CONSTRAINT IF EXISTS vote_fixture_overrides_pkey",
    "ALTER TABLE vote_fixture_overrides "
    "ADD CONSTRAINT vote_fixture_overrides_pkey PRIMARY KEY (medal_id, fixture_id)",

    "CREATE INDEX IF NOT EXISTS ix_vote_nudges_medal_fixture_player "
    "ON vote_nudges(medal_id, fixture_id, player_id, sent_at)",
]
