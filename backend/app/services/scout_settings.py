"""BetterScout — org settings (Settings screen's Organisation / Data &
refresh / Sharing defaults / Milestone alerts cards).

Wired to other screens: stale_after_weeks -> Overview's "going stale" panel,
default_window -> Discover/Profile's initial window, refresh_cadence -> the
scheduled refresh job, share_* -> share payloads (see
scout_watchlist.get_shared_card), digest_enabled/alert_scope -> the weekly
digest.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.scout import ScoutOrg

ORG_TYPES = {"", "agency", "club", "selector"}
REFRESH_CADENCES = {"daily", "weekly", "manual"}
DEFAULT_WINDOWS = {"1", "2", "5", "full"}
ALERT_SCOPES = {"all_tracked", "watchlisted_only"}

_SETTINGS_FIELDS = {
    "org_type", "home_region", "refresh_cadence", "stale_after_weeks", "default_window",
    "share_include_notes", "share_include_tags", "share_expiry_days",
    "digest_enabled", "alert_scope",
}


def settings_out(org: ScoutOrg) -> dict:
    return {
        "org_name": org.name,
        "logo_url": org.logo_url,
        "org_type": org.org_type or "",
        "home_region": org.home_region or "",
        "refresh_cadence": org.refresh_cadence,
        "stale_after_weeks": org.stale_after_weeks,
        "default_window": org.default_window,
        "share_include_notes": org.share_include_notes,
        "share_include_tags": org.share_include_tags,
        "share_expiry_days": org.share_expiry_days,
        "digest_enabled": org.digest_enabled,
        "alert_scope": org.alert_scope,
        "tier": org.tier,
    }


def _validate(fields: dict) -> None:
    if "org_type" in fields and (fields["org_type"] or "") not in ORG_TYPES:
        raise ValueError("Unknown org type.")
    if "refresh_cadence" in fields and fields["refresh_cadence"] not in REFRESH_CADENCES:
        raise ValueError("Unknown refresh cadence.")
    if "default_window" in fields and fields["default_window"] not in DEFAULT_WINDOWS:
        raise ValueError("Unknown default window.")
    if "alert_scope" in fields and fields["alert_scope"] not in ALERT_SCOPES:
        raise ValueError("Unknown alert scope.")
    if "stale_after_weeks" in fields and (fields["stale_after_weeks"] is None or fields["stale_after_weeks"] < 1):
        raise ValueError("Stale-after must be at least 1 week.")
    if "share_expiry_days" in fields and fields["share_expiry_days"] is not None and fields["share_expiry_days"] < 1:
        raise ValueError("Share expiry must be at least 1 day, or blank for never.")


async def update_settings(session, org: ScoutOrg, **fields) -> dict:
    fields = {k: v for k, v in fields.items() if k in _SETTINGS_FIELDS}
    _validate(fields)
    for k, v in fields.items():
        if k in ("org_type", "home_region") and v == "":
            v = None
        setattr(org, k, v)
    await session.commit()
    return settings_out(org)


def share_link_expired(org: ScoutOrg, share_token_created_at) -> bool:
    """org.share_expiry_days is None -> never expires. A share token minted
    before this column existed (share_token_created_at NULL) is treated as
    not expiring — it predates the feature, so a link someone already holds
    doesn't suddenly die the moment this ships."""
    if org.share_expiry_days is None or share_token_created_at is None:
        return False
    return datetime.now(timezone.utc) > share_token_created_at + timedelta(days=org.share_expiry_days)
