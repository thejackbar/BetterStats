"""
DDL for configurable club notifications (migration 288).

THE ONE COPY. Both alembic (versions/288_configurable_notifications.py) and the
lifespan mirror in main.py run this same list, in this order, per the
vote_medal_ddl rule. Every statement is idempotent, because the lifespan re-runs
the whole list on every boot.

WHY FOUR TABLES AND NOT ONE:

  - **`club_notification_settings` is the club's master switch**, and it is
    ABSENT for every club until somebody changes something. A missing row means
    the defaults in ``services/notification_events.py``, resolved in Python — so
    the platform default lives in exactly one place and no backfill is needed to
    change it. That is the same call ``organisations.stats_min_rate_innings``
    makes with NULL.

  - **`club_notification_rules` is per club per event.** Absent again means the
    registry's default for that event, so a club that has never opened the
    screen behaves exactly as the catalogue says. `config` carries whatever that
    event needs — the notice period before a Working With Children check lapses,
    the horizon on an asset service date — because those are per-event numbers,
    not one club-wide setting that would have to mean different things at once.

  - **`user_notification_preferences` is the opt-out, and it is per CLUB as well
    as per user.** A person who administers two clubs may want one club's
    milestones and not the other's. `event_key = '*'` (``ALL_EVENTS``) is the
    whole-club opt-out; a specific key narrows it to one event.

  - **`notifications` + `notification_deliveries` are the record.** A
    notification is the thing that happened, once per club; a delivery is one
    recipient on one channel. Splitting them is what lets the in-app feed, the
    email digest and any later channel read the SAME event rather than each
    re-deriving it from the source data and disagreeing about what happened.

THE DEDUPE KEY IS THE WHOLE RELIABILITY STORY. Every source builds a key that
identifies the real-world fact ("this player reached 5,000 runs", "this WWCC
expires on this date"), never the run that noticed it — so a daily scan can run
every day, a missed day catches up, and nothing is ever announced twice. It is
UNIQUE per organisation, so the insert itself is the guard rather than a
read-then-write race.

Nothing here removes a notification. A delivery that failed is recorded as
failed and retried on the next scan; a notification nobody read is simply old.
Pruning is a decision for a person, not something a nightly job should do to a
club's own record of what it was told.
"""

STATEMENTS: list[str] = [
    # ── The club's master switches ───────────────────────────────────────────
    # Absent row = the platform defaults. `enabled` is the kill switch a club
    # asked for: off means nothing is emitted at all, on any channel, and the
    # scan skips the club before it does any work.
    """
    CREATE TABLE IF NOT EXISTS club_notification_settings (
        organisation_id     UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        enabled             BOOLEAN NOT NULL DEFAULT true,
        email_enabled       BOOLEAN NOT NULL DEFAULT true,
        in_app_enabled      BOOLEAN NOT NULL DEFAULT true,
        -- 'daily' | 'weekly'. How often the email digest goes out; the in-app
        -- feed is always live, since there is nothing to batch about a list.
        email_frequency     TEXT NOT NULL DEFAULT 'daily',
        -- 0-6, Monday=0. Which day a weekly digest is sent. Ignored on daily.
        email_weekday       INTEGER NOT NULL DEFAULT 0,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by_user_id  UUID REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    # ── Per club, per event ──────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS club_notification_rules (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id  UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        event_key        TEXT NOT NULL,
        enabled          BOOLEAN NOT NULL DEFAULT true,
        -- {"email": true, "in_app": true} — absent channel falls back to the
        -- registry default, so adding a channel later needs no backfill.
        channels         JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- Per-event settings the registry declares (e.g. {"lead_days": 30}).
        config           JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_club_notification_rules_org_event
        ON club_notification_rules (organisation_id, event_key)
    """,
    # ── Per user, per club, per event — the opt-out ──────────────────────────
    """
    CREATE TABLE IF NOT EXISTS user_notification_preferences (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        organisation_id  UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        -- '*' (notification_events.ALL_EVENTS) opts the person out of the whole
        -- club; a real event key narrows it to that one event.
        event_key        TEXT NOT NULL,
        channels         JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_notification_prefs
        ON user_notification_preferences (user_id, organisation_id, event_key)
    """,
    # ── What happened ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id  UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        event_key        TEXT NOT NULL,
        -- Identifies the REAL-WORLD FACT, never the run that noticed it.
        dedupe_key       TEXT NOT NULL,
        severity         TEXT NOT NULL DEFAULT 'info',
        title            TEXT NOT NULL,
        body             TEXT,
        -- Where in the app to go and act on it. Relative, so it works on
        -- whatever host the club reaches us on.
        link             TEXT,
        payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- When the thing happened, which is not always when we noticed it.
        occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # The insert IS the guard against a double announcement — a read-then-write
    # check would race a manual scan against the nightly one.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_org_dedupe
        ON notifications (organisation_id, dedupe_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_notifications_org_created
        ON notifications (organisation_id, created_at DESC)
    """,
    # ── Who was told, on which channel ───────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        notification_id  UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
        user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        -- 'email' | 'in_app', and whatever a later channel is called. Kept as
        -- text rather than an enum so adding one is a code change, not a
        -- migration on a live table.
        channel          TEXT NOT NULL,
        -- 'pending' | 'sent' | 'failed'. A failed row is retried by the next
        -- scan; nothing is marked sent before the provider has accepted it.
        status           TEXT NOT NULL DEFAULT 'pending',
        sent_at          TIMESTAMPTZ,
        read_at          TIMESTAMPTZ,
        error            TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_deliveries
        ON notification_deliveries (notification_id, user_id, channel)
    """,
    # The two reads: this person's unread in-app feed, and the email digest's
    # "what is still pending for this recipient".
    """
    CREATE INDEX IF NOT EXISTS ix_notification_deliveries_user
        ON notification_deliveries (user_id, channel, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_notification_deliveries_unread
        ON notification_deliveries (user_id, channel) WHERE read_at IS NULL
    """,
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS notification_deliveries",
    "DROP TABLE IF EXISTS notifications",
    "DROP TABLE IF EXISTS user_notification_preferences",
    "DROP TABLE IF EXISTS club_notification_rules",
    "DROP TABLE IF EXISTS club_notification_settings",
]
