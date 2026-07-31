"""Meta Ads HQ — seed the initial "counting since" cutoff

A super admin asked to reset the Meta Ads HQ dashboard's on-site funnel/
table numbers (Club selected, the registration-wizard step funnel, Clubs
selected/searched, Meta's own campaign insights) to only count from
2026-07-28 06:00 Australia/Perth onward — the campaign's noisy early/test
period skewed the funnel (e.g. a later step reading MORE visitors than the
step before it). services/platform_settings.py's get_meta_ads_since /
set_meta_ads_since read/write `platform_settings.settings->>
'meta_ads_counting_since'`; this seeds that value once.

Deliberately does NOT reset get_registration_count() (the "Free trial
registrations" / "Completed registrations" KPI) — a genuine completed
registration always counts however long ago it happened, per direct
instruction to keep the real Meta-attributed registrations on the books.

Guarded by a separate `meta_ads_counting_since_seeded` marker (not by
whether `meta_ads_counting_since` itself is already set) so this is safe to
run only ONCE, ever: if a super admin later clears the cutoff from the UI
(to go back to unfiltered lifetime numbers), a later app restart re-running
this idempotent mirror must NOT silently reinstate it — the marker records
"this default was seeded", not "a value happens to be present right now".

Revision ID: 201
Revises: 200
Create Date: 2026-07-31
"""
from alembic import op


revision = "201"
down_revision = "200"
branch_labels = None
depends_on = None

_SINCE = "2026-07-28T06:00:00+08:00"


def upgrade() -> None:
    op.execute(f"""
        UPDATE platform_settings
        SET settings = settings || jsonb_build_object(
                'meta_ads_counting_since', '{_SINCE}',
                'meta_ads_counting_since_seeded', true
            ),
            updated_at = NOW()
        WHERE id = 1 AND NOT (settings ? 'meta_ads_counting_since_seeded')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE platform_settings
        SET settings = settings - 'meta_ads_counting_since' - 'meta_ads_counting_since_seeded'
        WHERE id = 1
    """)
