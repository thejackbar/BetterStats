"""Trial Summary (Better HQ, Reporting): every club that signed up or went on a trial.

One row per club: when it signed up and how, what it is trialling or paying for, when its
trial ends, and what its own people have done in the platform since. Read only, derived on
read (CLAUDE.md rule 4): nothing here is stored, so a corrected trial date or a late sync
shows the next time the page loads.

Who is listed: a club with a self-serve registration (``organisations.signup_source``) or any
module trial ever started (``org_module_subscriptions.trial_started_at``). That covers the
public /trial sign-ups and the clubs we put on a trial ourselves.

Rules this module keeps:

* Module status comes from ``auth.modules.account_plan_status``, the function the club's own
  Account page reads, so the two can never disagree about a trial or a subscription.
* Organisations carry no created_at. The sign-up date is the registration's own timestamp
  (the earliest ``self_serve_idempotency_keys`` row), else the first trial start, else the first
  module row, and the row says which one it used. None of those: no date, never a guess.
* Activity counts only the club's own people: page views signed in by a member of that club
  who is not one of our super admins. A super admin looking at a club is not the club using it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import modules as mods
from app.models.db import Organisation
from app.services import meta_ads
from app.services.trial_lifecycle import TRIAL_ENDING_SOON_DAYS as ENDING_SOON_DAYS

# "Ending soon" is the window the trial emails, the All Clubs "Ending soon" tab and the
# trials-ending-soon CSV already use, so every surface reads the same clubs.
# The recent-activity window.
RECENT_DAYS = 7
# Dates are counted as days in the clubs' own part of the world.
LOCAL_TZ = "Australia/Melbourne"

SIGNUP_CHANNELS = {
    "self_serve_ad": "Self-serve, from a tracked link",
    "self_serve_organic": "Self-serve",
}


def club_status(org, plan: list[dict], now: datetime) -> dict:
    """The one headline status of a club, from its plan rows (account_plan_status).

    archived > paused > paying > on trial > trial ended > no modules. A club paying for one
    module and trialling another is paying; its running trial still shows in `trial_ends_at`."""
    trials = [p for p in plan if p["status"] == mods.STATUS_TRIAL]
    paid = [p for p in plan if p["status"] == mods.STATUS_SUBSCRIBED]
    ended = [p for p in plan if p["status"] == mods.STATUS_TRIAL_EXPIRED]
    ends = sorted(p["trial_ends_at"] for p in trials if p["trial_ends_at"])
    trial_ends_at = ends[0] if ends else None
    open_ended = bool(trials) and not ends
    ended_dates = sorted(p["trial_ends_at"] for p in ended if p["trial_ends_at"])

    if getattr(org, "archived_at", None):
        key = "archived"
    elif not getattr(org, "is_active", True) or (org.subscription_status or "") in (mods.STATUS_PAUSED, mods.STATUS_CANCELLED):
        key = "paused"
    elif paid or getattr(org, "stripe_subscription_id", None):
        key = "paying"
    elif trials:
        key = "on_trial"
    elif ended:
        key = "trial_ended"
    else:
        key = "no_modules"

    days_left = None
    left = None
    if trial_ends_at:
        left = (datetime.fromisoformat(trial_ends_at) - now).total_seconds() / 86400
        days_left = int(left)
    return {
        "status": key,
        "trial_ends_at": trial_ends_at,
        "trial_open_ended": open_ended,
        "days_left": days_left,
        "ending_soon": key == "on_trial" and left is not None and 0 <= left <= ENDING_SOON_DAYS,
        "trial_ended_at": ended_dates[-1] if (key == "trial_ended" and ended_dates) else None,
    }


async def _signup_dates(db: AsyncSession, ids: list) -> dict:
    rows = (await db.execute(text("""
        SELECT o.id::text AS org_id,
               (SELECT MIN(k.created_at) FROM self_serve_idempotency_keys k WHERE k.org_id = o.id) AS registered_at,
               (SELECT MIN(s.trial_started_at) FROM org_module_subscriptions s WHERE s.organisation_id = o.id) AS trial_at,
               (SELECT MIN(s.created_at) FROM org_module_subscriptions s WHERE s.organisation_id = o.id) AS module_at
        FROM organisations o WHERE o.id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).mappings().all()
    out = {}
    for r in rows:
        for field, src in (("registered_at", "registration"), ("trial_at", "trial_start"), ("module_at", "first_module")):
            if r[field]:
                out[r["org_id"]] = (r[field], src)
                break
    return out


async def _people(db: AsyncSession, ids: list) -> dict:
    """Members who are not super admins, their latest sign-in, and the contact: the primary
    admin first, then any member with an email (as the trials-ending-soon CSV picks)."""
    rows = (await db.execute(text("""
        SELECT cm.club_id::text AS org_id,
               COUNT(DISTINCT cm.user_id) AS members,
               MAX(u.last_login_at) AS last_login_at,
               (array_agg(COALESCE(NULLIF(u.display_name, ''), NULLIF(TRIM(CONCAT(u.first_name, ' ', u.last_name)), ''), u.username)
                          ORDER BY cm.is_primary_admin DESC, cm.created_at)
                  FILTER (WHERE NULLIF(u.email, '') IS NOT NULL))[1] AS admin_name,
               (array_agg(u.email ORDER BY cm.is_primary_admin DESC, cm.created_at)
                  FILTER (WHERE NULLIF(u.email, '') IS NOT NULL))[1] AS admin_email
        FROM club_memberships cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.club_id = ANY(CAST(:ids AS uuid[]))
          AND cm.role <> 'super_admin'
          AND NOT EXISTS (SELECT 1 FROM club_memberships sa WHERE sa.user_id = cm.user_id AND sa.role = 'super_admin')
        GROUP BY cm.club_id
    """), {"ids": ids})).mappings().all()
    return {r["org_id"]: r for r in rows}


async def _directory_contacts(db: AsyncSession, ids: list) -> dict:
    """The top-ranked Club Directory contact, for a club with no member who has an email."""
    rows = (await db.execute(text("""
        SELECT DISTINCT ON (mc.existing_org_id) mc.existing_org_id::text AS org_id, c.full_name, c.email
        FROM marketing_clubs mc JOIN marketing_club_contacts c ON c.marketing_club_id = mc.id
        WHERE mc.existing_org_id = ANY(CAST(:ids AS uuid[])) AND NULLIF(c.email, '') IS NOT NULL
        ORDER BY mc.existing_org_id, c.role_rank ASC
    """), {"ids": ids})).mappings().all()
    return {r["org_id"]: r for r in rows}


async def _activity(db: AsyncSession, ids: list, since_recent: datetime) -> dict:
    """Signed-in page views by each club's own people. A page view carries the user, not the
    club, so it is attributed through that user's membership of the club."""
    base = f"""
        FROM club_memberships cm
        JOIN usage_events ue ON ue.user_id = cm.user_id AND ue.event_type = 'page_view'
        WHERE cm.club_id = ANY(CAST(:ids AS uuid[]))
          AND cm.role <> 'super_admin'
          AND NOT EXISTS (SELECT 1 FROM club_memberships sa WHERE sa.user_id = cm.user_id AND sa.role = 'super_admin')
    """
    rows = (await db.execute(text(f"""
        SELECT cm.club_id::text AS org_id,
               COUNT(*) AS views,
               COUNT(*) FILTER (WHERE ue.created_at >= :recent) AS views_recent,
               COUNT(DISTINCT (ue.created_at AT TIME ZONE '{LOCAL_TZ}')::date) AS active_days,
               COUNT(DISTINCT (ue.created_at AT TIME ZONE '{LOCAL_TZ}')::date) FILTER (WHERE ue.created_at >= :recent) AS active_days_recent,
               COUNT(DISTINCT ue.user_id) AS active_people,
               MAX(ue.created_at) AS last_active_at
        {base}
        GROUP BY cm.club_id
    """), {"ids": ids, "recent": since_recent})).mappings().all()
    out = {r["org_id"]: dict(r) for r in rows}
    # The parts of the admin they used most: the first path segment after /admin.
    areas = (await db.execute(text(f"""
        SELECT org_id, area, n FROM (
            SELECT cm.club_id::text AS org_id,
                   NULLIF(split_part(split_part(ue.path, '?', 1), '/', 3), '') AS area,
                   COUNT(*) AS n,
                   ROW_NUMBER() OVER (PARTITION BY cm.club_id ORDER BY COUNT(*) DESC) AS rk
            {base}
              AND split_part(ue.path, '?', 1) ~* '^/admin/[^/]+'
            GROUP BY cm.club_id, area
        ) t WHERE rk <= 3 AND area IS NOT NULL ORDER BY org_id, n DESC
    """), {"ids": ids})).mappings().all()
    for a in areas:
        out.setdefault(a["org_id"], {}).setdefault("top_areas", []).append({"area": a["area"], "views": int(a["n"])})
    return out


async def _data(db: AsyncSession, ids: list) -> dict:
    """What the club has in the platform: players, games on record, and its last sync."""
    rows = (await db.execute(text("""
        SELECT o::text AS org_id,
               (SELECT COUNT(*) FROM players p WHERE p.organisation_id = o) AS players,
               (SELECT COUNT(*) FROM games g WHERE g.home_org_id = o OR g.away_org_id = o) AS games,
               (SELECT MAX(r.completed_at) FROM sync_runs r WHERE r.org_id = o AND r.status = 'success') AS last_sync_at,
               (SELECT r.status FROM sync_runs r WHERE r.org_id = o ORDER BY r.started_at DESC LIMIT 1) AS last_sync_status
        FROM unnest(CAST(:ids AS uuid[])) AS o
    """), {"ids": ids})).mappings().all()
    return {r["org_id"]: r for r in rows}


def _contact(member: dict, directory: dict | None, org) -> dict:
    if member.get("admin_email"):
        return {"admin_name": member.get("admin_name"), "admin_email": member["admin_email"], "contact_source": "club_admin"}
    if directory:
        return {"admin_name": directory["full_name"], "admin_email": directory["email"], "contact_source": "club_directory"}
    if getattr(org, "contact_email", None):
        return {"admin_name": None, "admin_email": org.contact_email, "contact_source": "club_settings"}
    return {"admin_name": None, "admin_email": None, "contact_source": None}


def _iso(v):
    return v.isoformat() if v else None


async def build_summary(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    orgs = (await db.execute(
        select(Organisation)
        .options(selectinload(Organisation.module_subscriptions))
        .where(text("""(organisations.signup_source IS NOT NULL OR EXISTS (
            SELECT 1 FROM org_module_subscriptions s
            WHERE s.organisation_id = organisations.id AND s.trial_started_at IS NOT NULL))"""))
    )).scalars().all()
    ids = [str(o.id) for o in orgs]
    if not ids:
        return {"clubs": [], "generated_at": now.isoformat(), "recent_days": RECENT_DAYS,
                "ending_soon_days": ENDING_SOON_DAYS}

    signups = await _signup_dates(db, ids)
    people = await _people(db, ids)
    activity = await _activity(db, ids, now - timedelta(days=RECENT_DAYS))
    data = await _data(db, ids)
    directory = await _directory_contacts(db, ids)

    clubs = []
    for o in orgs:
        oid = str(o.id)
        plan = mods.account_plan_status(o, now)
        status = club_status(o, plan, now)
        signed_up = signups.get(oid)
        p = people.get(oid) or {}
        a = activity.get(oid) or {}
        d = data.get(oid) or {}
        attribution = o.signup_attribution if isinstance(o.signup_attribution, dict) else None
        clubs.append({
            "org_id": oid,
            "name": o.name,
            "slug": o.slug,
            **status,
            "signed_up_at": _iso(signed_up[0]) if signed_up else None,
            "signed_up_from": signed_up[1] if signed_up else None,
            "signup_channel": SIGNUP_CHANNELS.get(o.signup_source or "", "Set up by us"),
            "origin": meta_ads.origin_from_attribution(attribution) if o.signup_source else None,
            "modules": [
                {"module": m["module"], "name": m["name"], "status": m["status"], "trial_ends_at": m["trial_ends_at"]}
                for m in plan if m["status"] in (mods.STATUS_TRIAL, mods.STATUS_SUBSCRIBED, mods.STATUS_TRIAL_EXPIRED)
            ],
            **_contact(p, directory.get(oid), o),
            "members": int(p.get("members") or 0),
            "last_login_at": _iso(p.get("last_login_at")),
            "activity": {
                "views": int(a.get("views") or 0),
                "views_recent": int(a.get("views_recent") or 0),
                "active_days": int(a.get("active_days") or 0),
                "active_days_recent": int(a.get("active_days_recent") or 0),
                "active_people": int(a.get("active_people") or 0),
                "last_active_at": _iso(a.get("last_active_at")),
                "top_areas": a.get("top_areas") or [],
            },
            "data": {
                "players": int(d.get("players") or 0),
                "games": int(d.get("games") or 0),
                "last_sync_at": _iso(d.get("last_sync_at")),
                "last_sync_status": d.get("last_sync_status"),
            },
        })

    _floor = ""
    clubs.sort(key=lambda c: c["signed_up_at"] or _floor, reverse=True)
    return {"clubs": clubs, "generated_at": now.isoformat(), "recent_days": RECENT_DAYS,
            "ending_soon_days": ENDING_SOON_DAYS}
