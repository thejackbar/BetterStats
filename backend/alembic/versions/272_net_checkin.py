"""A player checks themselves in to nets, from a QR code or an NFC tag.

The Net Manager's check-in was an admin action: someone holding the club
account tapped each name on the iPad. This is the same check-in done by the
player, on their own phone, by scanning a QR code or tapping an NFC tag on the
way into the nets.

``organisations.net_checkin_token`` / ``.net_checkin_enabled``
    / ``.net_checkin_require_pin`` / ``.net_checkin_allow_registration``
    The club-wide link, mirroring ``availability_link_token`` exactly —
    lazily minted on first enable, rotatable, partial-unique so a NULL
    doesn't collide. **A QR code on the fence and an NFC tag under it hold
    the same URL**: a tag stores a URL and nothing else, so there is one
    link and one token behind both, not two.

    ``net_checkin_require_pin`` gates the EXISTING-PLAYER path on last-4-of
    -phone, the same proof the availability link asks for. It cannot gate
    the registration path below — someone the club has never met has no
    phone number on file to check against — which is the honest reason
    ``net_checkin_allow_registration`` is a separate switch a club can turn
    off on its own.

``net_attendance.source``
    'admin' (someone tapped the name on the iPad) or 'self' (the player
    scanned in). Mirrors ``player_availability.source``, and exists for the
    same reason: ``recorded_by`` is NULL for a self check-in, so it cannot
    tell the two apart. It is what lets the live screen raise a pop-up for
    somebody arriving on their own and stay quiet for a row the manager
    just added themselves.

``net_checkin_registrations``
    Someone who is not on the list yet fills in their details and is checked
    in **as a guest**, not as a player. ``net_attendance`` has carried guest
    rows (``player_id`` NULL + ``guest_name``) since it was written, for
    exactly this person — the trialist or newcomer not yet in the system —
    so a stranger who scans a QR code lands in tonight's session without
    writing an unvetted row into the club's player table. Their details sit
    here instead, flagged for an admin, who turns the registration into a
    real player or points it at someone already on the roster.

    ``previous_club`` has no home on ``players`` (there is no such column,
    and one row of free text from a self-registration is not a good enough
    reason to add one), so it lives here as what it is: something the person
    typed about themselves, kept with the rest of what they typed.

Revision ID: 272
Revises: 271
"""
from alembic import op

revision = "272"
down_revision = "271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── The club's link ───────────────────────────────────────────────────────
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_token TEXT")
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "net_checkin_enabled BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "net_checkin_require_pin BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "net_checkin_allow_registration BOOLEAN NOT NULL DEFAULT true"
    )
    # Partial, so every club that has never enabled it keeps a NULL without
    # colliding with the next one — the same shape every *_link_token uses.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_organisations_net_checkin_token "
        "ON organisations (net_checkin_token) WHERE net_checkin_token IS NOT NULL"
    )

    # ── Who put this row here ─────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS "
        "source TEXT NOT NULL DEFAULT 'admin'"
    )

    # ── A newcomer's own account of themselves ────────────────────────────────
    # session_id / attendance_id are SET NULL: a deleted session must not take
    # the registration with it. The person still turned up and the club still
    # has to decide about them.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS net_checkin_registrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            session_id UUID REFERENCES net_sessions(id) ON DELETE SET NULL,
            attendance_id UUID REFERENCES net_attendance(id) ON DELETE SET NULL,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            date_of_birth DATE,
            previous_club TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            player_id UUID REFERENCES players(id) ON DELETE SET NULL,
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    # The review queue is the only read: this club's pending ones, newest first.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_net_checkin_registrations_org_status "
        "ON net_checkin_registrations (organisation_id, status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS net_checkin_registrations")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS source")
    op.execute("DROP INDEX IF EXISTS ix_organisations_net_checkin_token")
    op.execute(
        "ALTER TABLE organisations "
        "DROP COLUMN IF EXISTS net_checkin_allow_registration, "
        "DROP COLUMN IF EXISTS net_checkin_require_pin, "
        "DROP COLUMN IF EXISTS net_checkin_enabled, "
        "DROP COLUMN IF EXISTS net_checkin_token"
    )
