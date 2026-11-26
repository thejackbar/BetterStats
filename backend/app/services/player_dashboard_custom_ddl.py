"""The DDL behind a club's own Player Dashboard modules (migration 400), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``player_dashboard_custom_modules``
    A card the club writes itself for the Player Dashboard: a link button (tickets, the
    merch store, a form), an announcement, an event with a countdown, or an image banner.
    ``kind`` is one of ``services/player_dashboard_custom.KINDS``. ``show_from`` and
    ``show_until`` are optional dates (blank is always); an event with no ``show_until``
    drops off the day after ``event_date``. ``event_date`` and ``event_time`` are the
    club's wall clock, so no timezone is stored. The image is kept in the row, like a
    club logo, and served by ``routers/images``; ``image_version`` busts the cache on a
    new upload. ``click_count`` is a plain tally of taps, with no record of who tapped.
    The club adds, edits and removes these itself; no code removes one.

``organisations.player_dashboard_layout``
    The order of the cards on the Player Dashboard grid: built-in section ids
    (``availability``, ``selection``, ``cards`` ...) and ``custom:<id>`` for the club's
    own. NULL is the standard order with the club's own cards after it.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS player_dashboard_custom_modules (
        id UUID PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT,
        url TEXT,
        button_label TEXT,
        emoji TEXT,
        event_date DATE,
        event_time TIME,
        location TEXT,
        show_from DATE,
        show_until DATE,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        image_data BYTEA,
        image_mime TEXT,
        image_version TEXT,
        click_count INTEGER NOT NULL DEFAULT 0,
        last_clicked_at TIMESTAMPTZ,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_player_dashboard_custom_modules_org ON player_dashboard_custom_modules (organisation_id, created_at)",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS player_dashboard_layout JSONB",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS fees_payment_details JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS fees_payment_details",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS player_dashboard_layout",
    "DROP TABLE IF EXISTS player_dashboard_custom_modules",
]
