"""DDL for `webinar_registrations` (migration 295).

The ONE copy alembic and the `main.py` lifespan mirror both run, per the
`vote_medal_ddl` rule — two hand-kept copies is how the migration and the
boot-time mirror start disagreeing about the schema. Every statement is
idempotent because the lifespan re-runs the whole list on every boot.
"""
from __future__ import annotations

STATEMENTS: list[str] = [
    # A registration for one dated BetterCricket event. `event_key` is here from
    # the start so the second webinar reuses the table rather than needing a
    # migration — the registrations for two events must never merge into one
    # list, and keying on the event is what keeps them apart.
    """
    CREATE TABLE IF NOT EXISTS webinar_registrations (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_key       TEXT NOT NULL,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL,
        club            TEXT NOT NULL,
        -- Stored as typed, not normalised to a canonical form. A club officer
        -- writes their number however they write it — "0412 345 678", a
        -- landline with an area code, an international one — and rewriting it
        -- would only make it harder to read back to whoever rings them.
        -- Digits-only normalisation happens once, at the Meta CAPI boundary,
        -- where the hash requires it.
        phone           TEXT,
        role            TEXT,
        -- The five UTM tags and the ad click id get their own columns because a
        -- staff report groups by campaign; the whole first-touch blob is kept
        -- alongside in `attribution` so nothing the browser captured is lost.
        -- Same split organisations.signup_source / .signup_attribution uses.
        utm_source      TEXT,
        utm_medium      TEXT,
        utm_campaign    TEXT,
        utm_content     TEXT,
        utm_term        TEXT,
        click_id        TEXT,
        click_source    TEXT,
        attribution     JSONB,
        referrer        TEXT,
        landing_path    TEXT,
        visitor_id      TEXT,
        user_agent      TEXT,
        -- Whether the confirmation email was accepted by the provider, and its
        -- reason if not. On the row rather than in a log, so "they say they
        -- never got it" is answerable months later.
        email_sent      BOOLEAN NOT NULL DEFAULT FALSE,
        email_error     TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # The CREATE above covers a fresh database; a database that already has the
    # table from migration 296 needs the column added to it. Both live in this
    # one list so alembic and the lifespan mirror can never disagree about
    # which of the two a given database needed — see migration 297.
    """
    ALTER TABLE webinar_registrations ADD COLUMN IF NOT EXISTS phone TEXT
    """,
    # One row per person per event. Folded, because an address typed with a
    # capital is the same person — a second registration corrects the row it
    # already has rather than adding a duplicate to the follow-up list.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_webinar_reg_event_email
        ON webinar_registrations (event_key, lower(email))
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_webinar_reg_created
        ON webinar_registrations (event_key, created_at DESC)
    """,
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS webinar_registrations",
]
