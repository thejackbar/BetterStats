"""Where notifications come from, and how they leave the building.

Two halves, run once a day per club:

  * ``scan_org`` asks each source what it can see and hands every answer to
    ``notifications.emit``. **A source reports everything it can see, every
    time** — it never tries to work out what is new, because the unique dedupe
    key already does that far more reliably than a "since last run" window
    could. A missed day therefore catches up on its own, and a source that runs
    twice in an hour costs one rejected insert per fact.

  * ``dispatch_emails`` turns the pending email deliveries into ONE digest per
    recipient. Three milestones and a lapsing Working With Children check are
    one email, not four — the same call ``trial_lifecycle`` makes, and the
    difference between a system people read and one they filter.

**EVERY DEDUPE KEY NAMES THE FACT, NOT THE RUN.** ``milestone:<player>:runs:5000``
is true forever; a certificate's key carries its expiry DATE, so renewing it
creates a genuinely new fact to warn about next time and an unchanged one is
only ever raised once. The one exception is low stock, which is a standing state
rather than an event — its key carries the ISO week, so a club is reminded
weekly while it lasts rather than once ever (which would go unnoticed) or daily
(which would be nagging).

**A FIRST RUN IS CAPPED.** An established club switching this on has a decade of
history in reach of the sources, so each event is capped at ``MAX_PER_EVENT``
per run: the club hears about the most pressing ones and the rest arrive
tomorrow, instead of one club's backlog filling a table and an inbox.

Never raises. A source that throws is logged and skipped, and the club's other
sources still run — one bad row must not cost a club its whole notification run.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import org_entitled_modules
from app.config.settings import settings as app_settings
from app.models.db import Organisation, async_session_maker
from app.services import email_service, milestone_scan
from app.services import notification_events as ev
from app.services import notifications as notif
from app.services.milestone_rules import is_displayable

logger = logging.getLogger(__name__)

#: How far back a source looks for something that has already happened. Wide
#: enough that a few missed runs catch up by themselves, and harmless because
#: the dedupe key stops anything being announced twice.
LOOKBACK_DAYS = 21

#: Most notifications one event may raise for one club in one run. See the
#: first-run note above.
MAX_PER_EVENT = 40

#: Most items spelled out in one digest email before it says "and N more".
DIGEST_ITEM_CAP = 25

_MILESTONE_STAT_LABELS = {
    "runs": "career runs",
    "wickets": "career wickets",
    "matches": "career matches",
    "catches": "career catches",
}


# ─── Sources ─────────────────────────────────────────────────────────────────
# Each returns a list of dicts ready for notifications.emit. They query, they
# never write, and they know nothing about channels or recipients.

async def _src_milestone_achieved(session: AsyncSession, org_id, config: dict) -> list[dict]:
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows = (await session.execute(text("""
        SELECT m.player_id, m.milestone_type, m.milestone_value, m.achieved_at,
               COALESCE(p.display_name_override, p.name) AS player_name
        FROM milestones m
        JOIN players p ON p.id = m.player_id
        WHERE p.organisation_id = :org
          AND m.achieved_at IS NOT NULL AND m.achieved_at >= :cutoff
        ORDER BY m.achieved_at DESC, m.milestone_value DESC
        LIMIT :cap
    """), {"org": str(org_id), "cutoff": cutoff, "cap": MAX_PER_EVENT * 3})).mappings().all()

    out = []
    for r in rows:
        # The stored table keeps smaller, retired thresholds (10 matches, 100
        # runs) that no screen draws any more. Announcing one would be telling a
        # club about a milestone its own Records page does not recognise.
        if not is_displayable(r["milestone_type"], r["milestone_value"]):
            continue
        stat = _MILESTONE_STAT_LABELS.get(r["milestone_type"], r["milestone_type"])
        out.append({
            "dedupe_key": f"milestone:{r['player_id']}:{r['milestone_type']}:{r['milestone_value']}",
            "title": f"{r['player_name']} reached {r['milestone_value']:,} {stat}",
            "body": f"Passed on {r['achieved_at'].strftime('%-d %b %Y')}.",
            "link": f"/admin/players?player={r['player_id']}",
            "payload": {
                "player_id": str(r["player_id"]),
                "player_name": r["player_name"],
                "milestone_type": r["milestone_type"],
                "milestone_value": r["milestone_value"],
            },
            "occurred_at": datetime.combine(r["achieved_at"], datetime.min.time(), tzinfo=timezone.utc),
        })
        if len(out) >= MAX_PER_EVENT:
            break
    return out


async def _src_milestone_upcoming(session: AsyncSession, org_id, config: dict) -> list[dict]:
    # The one definition of "who is close to something" — the same helper the
    # dashboard, the Records page and the admin report read, so the notification
    # cannot name a player those screens do not list.
    rows = await milestone_scan.upcoming_career_milestones(session, str(org_id))
    rows.sort(key=lambda r: (r["needed"], -r["target"]))
    out = []
    for r in rows[:MAX_PER_EVENT]:
        stat = _MILESTONE_STAT_LABELS.get(r["type"], r["type"])
        out.append({
            # The target is in the key, so the same player reaching the NEXT
            # threshold is a new fact and this one is announced exactly once.
            "dedupe_key": f"milestone_upcoming:{r['player_id']}:{r['type']}:{r['target']}",
            "title": f"{r['player_name']} is {r['needed']} from {r['target']:,} {stat}",
            "body": f"Currently on {r['current']:,}.",
            "link": f"/admin/milestones",
            "payload": r,
        })
    return out


async def _src_qualification_expiring(session: AsyncSession, org_id, config: dict) -> list[dict]:
    """Volunteer and official certifications approaching their expiry date.

    The notice period is the club's own (``lead_days``), because how long a
    renewal takes is not the same everywhere: a Working With Children check can
    take weeks to come back, a first aid refresher is a weekend.

    An ALREADY EXPIRED certificate is included, not filtered out — it is the
    most urgent case there is, and a club that has just switched notifications
    on should hear about the ones already lapsed rather than only the ones about
    to.
    """
    lead_days = int(config.get("lead_days", 60))
    today = date.today()
    horizon = today + timedelta(days=lead_days)
    rows = (await session.execute(text("""
        SELECT mq.id, mq.expires_at, qt.name AS qualification_name,
               fm.id AS member_id, fm.full_name
        FROM member_qualifications mq
        JOIN qualification_types qt ON qt.id = mq.qualification_type_id
        JOIN fee_members fm ON fm.id = mq.member_id
        WHERE mq.organisation_id = :org
          AND mq.expires_at IS NOT NULL
          AND mq.expires_at <= :horizon
        ORDER BY mq.expires_at ASC
        LIMIT :cap
    """), {"org": str(org_id), "horizon": horizon, "cap": MAX_PER_EVENT})).mappings().all()

    out = []
    for r in rows:
        expires = r["expires_at"]
        days = (expires - today).days
        if days < 0:
            when = f"expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
            body = f"Lapsed on {expires.strftime('%-d %b %Y')}. They should not be rostered until it is renewed."
        elif days == 0:
            when = "expires today"
            body = "Today is the last day it is valid."
        else:
            when = f"expires in {days} day{'s' if days != 1 else ''}"
            body = f"Due to expire on {expires.strftime('%-d %b %Y')}."
        out.append({
            # The expiry DATE is in the key, so a renewal creates a new fact to
            # warn about next time round and an unchanged one is raised once.
            "dedupe_key": f"qualification:{r['id']}:{expires.isoformat()}",
            "title": f"{r['full_name']}'s {r['qualification_name']} {when}",
            "body": body,
            "link": "/admin/clubhouse/qualifications",
            "payload": {
                "member_id": str(r["member_id"]),
                "member_name": r["full_name"],
                "qualification": r["qualification_name"],
                "expires_at": expires.isoformat(),
                "days_remaining": days,
            },
        })
    return out


async def _src_asset_service_due(session: AsyncSession, org_id, config: dict) -> list[dict]:
    from app.services.assets import asset_alerts
    lead_days = int(config.get("lead_days", 30))
    alerts = await asset_alerts(session, org_id, horizon_days=lead_days)
    out = []
    for a in alerts.get("service_due", [])[:MAX_PER_EVENT]:
        # Two genuinely different jobs, so two notifications rather than one
        # that means either — a club servicing the mower has not replaced it.
        for kind, due_key, label in (
            ("service", "service_due_date", "service"),
            ("replace", "replace_due_date", "replacement"),
        ):
            if not a.get(f"{kind}_due") or not a.get(due_key):
                continue
            overdue = a.get(f"{kind}_overdue")
            out.append({
                "dedupe_key": f"asset:{a['asset_id']}:{kind}:{a[due_key]}",
                "title": f"{a['name']} — {label} {'overdue' if overdue else 'due'}",
                "body": f"{'Was due' if overdue else 'Due'} {a[due_key]}.",
                "link": "/admin/assets",
                "payload": {"asset_id": a["asset_id"], "name": a["name"], "kind": kind,
                            "due_date": a[due_key], "overdue": bool(overdue)},
            })
    return out[:MAX_PER_EVENT]


async def _src_merch_low_stock(session: AsyncSession, org_id, config: dict) -> list[dict]:
    from app.services.merch import merch_alerts
    alerts = await merch_alerts(session, org_id)
    # Low stock is a STANDING STATE, not an event — it stays true until somebody
    # restocks. Keying on the ISO week is what makes it a weekly reminder while
    # it lasts: keying on the variant alone would mention it once ever and then
    # never again, keying on the day would nag.
    iso_year, iso_week, _ = date.today().isocalendar()
    out = []
    for v in alerts.get("low_stock", [])[:MAX_PER_EVENT]:
        name = f"{v['product_name']}" + (f" ({v['variant_label']})" if v.get("variant_label") else "")
        out.append({
            "dedupe_key": f"merch_low:{v['variant_id']}:{iso_year}W{iso_week:02d}",
            "title": f"{name} is down to {v['quantity']}",
            "body": f"At or below the low-stock level of {v['threshold']}.",
            "link": "/admin/merch/stock",
            "payload": v,
        })
    return out


async def _src_report_pending(session: AsyncSession, org_id, config: dict) -> list[dict]:
    rows = (await session.execute(text("""
        SELECT id, title, created_at FROM saved_reports
        WHERE org_id = :org AND visibility = 'club' AND status = 'pending'
        ORDER BY created_at ASC LIMIT :cap
    """), {"org": str(org_id), "cap": MAX_PER_EVENT})).mappings().all()
    return [
        {
            "dedupe_key": f"report_pending:{r['id']}",
            "title": f"“{r['title']}” is waiting for approval",
            "body": "A member has shared a StatLab report with the club.",
            "link": "/admin/reports",
            "payload": {"report_id": str(r["id"]), "title": r["title"]},
            "occurred_at": r["created_at"],
        }
        for r in rows
    ]


async def _src_player_request_pending(session: AsyncSession, org_id, config: dict) -> list[dict]:
    rows = (await session.execute(text("""
        SELECT r.id, r.requester_note, r.created_at,
               COALESCE(p.display_name_override, p.name) AS player_name
        FROM player_sync_requests r
        JOIN players p ON p.id = r.player_id
        WHERE r.org_id = :org AND r.status = 'pending'
        ORDER BY r.created_at ASC LIMIT :cap
    """), {"org": str(org_id), "cap": MAX_PER_EVENT})).mappings().all()
    return [
        {
            "dedupe_key": f"player_request:{r['id']}",
            "title": f"{r['player_name']} has asked for their stats to be checked",
            "body": (r["requester_note"] or "").strip()[:200] or "No note was left.",
            "link": "/admin/players",
            "payload": {"request_id": r["id"], "player_name": r["player_name"]},
            "occurred_at": r["created_at"],
        }
        for r in rows
    ]


async def _src_sync_failed(session: AsyncSession, org_id, config: dict) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    rows = (await session.execute(text("""
        SELECT id, kind, error, completed_at FROM sync_runs
        WHERE org_id = :org AND status = 'error' AND player_id IS NULL
          AND completed_at IS NOT NULL AND completed_at >= :since
        ORDER BY completed_at DESC LIMIT :cap
    """), {"org": str(org_id), "since": since, "cap": MAX_PER_EVENT})).mappings().all()
    return [
        {
            "dedupe_key": f"sync_failed:{r['id']}",
            "title": "A data sync did not finish",
            "body": ((r["error"] or "").strip()[:280] or "No error was recorded.")
                    + " Results will stop updating until it runs cleanly.",
            "link": "/admin/sync",
            "payload": {"run_id": str(r["id"]), "kind": r["kind"]},
            "occurred_at": r["completed_at"],
        }
        for r in rows
    ]


async def _src_sync_completed(session: AsyncSession, org_id, config: dict) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    rows = (await session.execute(text("""
        SELECT id, kind, stats, completed_at FROM sync_runs
        WHERE org_id = :org AND status = 'success' AND player_id IS NULL
          AND completed_at IS NOT NULL AND completed_at >= :since
        ORDER BY completed_at DESC LIMIT :cap
    """), {"org": str(org_id), "since": since, "cap": MAX_PER_EVENT})).mappings().all()
    out = []
    for r in rows:
        new_games = int((r["stats"] or {}).get("gr_games_new") or 0)
        # A sync that brought nothing in is not news. The club's results did not
        # move, and saying so every day is exactly the noise that makes people
        # stop reading the bell.
        if new_games <= 0:
            continue
        out.append({
            "dedupe_key": f"sync_completed:{r['id']}",
            "title": f"{new_games} new match{'es' if new_games != 1 else ''} synced",
            "body": "Stats, records and leaderboards are up to date.",
            "link": "/admin/matches",
            "payload": {"run_id": str(r["id"]), "new_games": new_games},
            "occurred_at": r["completed_at"],
        })
    return out


SOURCES = {
    "milestone_achieved": _src_milestone_achieved,
    "milestone_upcoming": _src_milestone_upcoming,
    "qualification_expiring": _src_qualification_expiring,
    "asset_service_due": _src_asset_service_due,
    "merch_low_stock": _src_merch_low_stock,
    "report_pending": _src_report_pending,
    "player_request_pending": _src_player_request_pending,
    "sync_failed": _src_sync_failed,
    "sync_completed": _src_sync_completed,
}


# ─── The scan ────────────────────────────────────────────────────────────────

async def scan_org(session: AsyncSession, org: Organisation) -> dict:
    """Ask every enabled source what it can see, and record what is new."""
    stats = {"emitted": 0, "events_run": 0, "sources_failed": 0}
    club_settings = await notif.club_settings(session, org.id)
    if not club_settings.get("enabled", True):
        return stats
    rules = await notif.club_rules(session, org.id)
    entitled = org_entitled_modules(org)

    # Resolved once for the whole club rather than per notification — a club
    # with fifty milestones would otherwise re-read the same handful of
    # preference rows fifty times.
    people = {}
    prefs_by_user: dict[str, dict] = {}

    for event in ev.EVENT_TYPES:
        rule = rules.get(event.key, {})
        if not rule.get("enabled", True):
            continue
        if not notif.event_available(event, entitled):
            continue
        # Nothing is going anywhere, so do not spend the query finding it.
        if not any(rule.get("channels", {}).get(c) for c in ev.CHANNELS):
            continue
        source = SOURCES.get(event.key)
        if source is None:
            continue

        try:
            items = await source(session, org.id, rule.get("config", {}))
        except Exception:
            # One source is never the whole run. A statement timeout on a big
            # club's milestone scan must not cost it the lapsing WWCC notice.
            logger.exception("notification scan: source %s failed for org %s", event.key, org.id)
            await session.rollback()
            stats["sources_failed"] += 1
            continue

        if event.key not in people:
            people[event.key] = await notif.recipients_for(session, org.id, event)
            for p in people[event.key]:
                uid = str(p["user_id"])
                if uid not in prefs_by_user:
                    prefs_by_user[uid] = await notif.user_preferences(session, p["user_id"], org.id)

        stats["events_run"] += 1
        for item in items[:MAX_PER_EVENT]:
            created = await notif.emit(
                session, org.id, event_key=event.key,
                settings=club_settings, rules=rules,
                entitled_modules=entitled, prefs_by_user=prefs_by_user,
                recipients=people[event.key],
                **item,
            )
            if created:
                stats["emitted"] += 1
    return stats


# ─── Email digest ────────────────────────────────────────────────────────────

def _should_email_today(club_settings: dict, today: date) -> bool:
    if not club_settings.get("email_enabled", True):
        return False
    if club_settings.get("email_frequency") == "weekly":
        return today.weekday() == int(club_settings.get("email_weekday") or 0)
    return True


def _digest_html(club_name: str, greeting: str, groups: list[dict], link: str,
                 settings_link: str) -> tuple[str, str]:
    """Plain inline-styled HTML — a system transactional send, not a BetterComms
    campaign, so no club shell and no marketing unsubscribe wrapper. The footer
    still points at the settings screen, because a person told something they
    did not ask for must always be one click from turning it off."""
    blocks = []
    text_blocks = []
    for g in groups:
        rows = "".join(
            f'<li style="margin:0 0 6px"><strong>{_esc(i["title"])}</strong>'
            + (f'<br><span style="color:#555">{_esc(i["body"])}</span>' if i.get("body") else "")
            + "</li>"
            for i in g["items"][:DIGEST_ITEM_CAP]
        )
        more = len(g["items"]) - DIGEST_ITEM_CAP
        if more > 0:
            rows += f'<li style="margin:0 0 6px;color:#555">and {more} more</li>'
        blocks.append(
            f'<p style="font-size:13px;font-weight:bold;margin:20px 0 8px">{_esc(g["label"])}</p>'
            f'<ul style="font-size:14px;line-height:1.5;margin:0;padding-left:18px">{rows}</ul>'
        )
        text_lines = [f"- {i['title']}" + (f" — {i['body']}" if i.get("body") else "")
                      for i in g["items"][:DIGEST_ITEM_CAP]]
        if more > 0:
            text_lines.append(f"- and {more} more")
        text_blocks.append(g["label"] + "\n" + "\n".join(text_lines))

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1a1a1a">
      <p style="font-size:13px;color:#555;margin:0 0 16px">{_esc(club_name)} · BetterCricket</p>
      <p style="font-size:14px;line-height:1.5;margin:0 0 4px">Hi {_esc(greeting)},</p>
      <p style="font-size:14px;line-height:1.5;margin:0">Here is what has come up at the club.</p>
      {''.join(blocks)}
      <p style="margin:24px 0">
        <a href="{link}" style="display:inline-block;background:#16c784;color:#fff;text-decoration:none;
           padding:10px 20px;border-radius:6px;font-size:14px;font-weight:bold">Open BetterCricket</a>
      </p>
      <p style="font-size:12px;color:#888;margin-top:24px">
        You are getting this because you administer {_esc(club_name)} on BetterCricket.
        <a href="{settings_link}" style="color:#888">Choose what you are told about</a>.
      </p>
    </div>
    """
    text_body = "\n\n".join([f"Hi {greeting},", "Here is what has come up at the club.",
                             *text_blocks, f"Open BetterCricket: {link}",
                             f"Choose what you are told about: {settings_link}"])
    return html, text_body


def _esc(value) -> str:
    from html import escape
    return escape(str(value or ""))


async def dispatch_emails(session: AsyncSession, org: Organisation) -> dict:
    """Send each recipient one digest of everything still pending for them.

    A delivery is only marked sent once the provider has accepted the message,
    so a provider outage retries the whole digest tomorrow rather than silently
    dropping a lapsing certificate. A permanent refusal is recorded as failed
    with the reason, which is what makes "they say they never got it" answerable
    months later.
    """
    stats = {"emails_sent": 0, "deliveries_sent": 0, "failed": 0}
    club_settings = await notif.club_settings(session, org.id)
    if not club_settings.get("enabled", True):
        return stats
    if not _should_email_today(club_settings, date.today()):
        return stats

    rows = (await session.execute(text("""
        SELECT d.id AS delivery_id, d.user_id, n.event_key, n.title, n.body, n.severity,
               u.email, u.display_name, u.first_name
        FROM notification_deliveries d
        JOIN notifications n ON n.id = d.notification_id
        JOIN users u ON u.id = d.user_id
        WHERE n.organisation_id = :org AND d.channel = :channel
          AND d.status IN ('pending', 'failed')
        ORDER BY d.user_id, n.created_at ASC
    """), {"org": str(org.id), "channel": ev.CHANNEL_EMAIL})).mappings().all()
    if not rows:
        return stats

    by_user: dict[str, list] = {}
    for r in rows:
        by_user.setdefault(str(r["user_id"]), []).append(r)

    base = app_settings.public_base_url.rstrip("/")
    for _uid, items in by_user.items():
        address = (items[0]["email"] or "").strip()
        if not address:
            continue
        greeting = ((items[0]["first_name"] or items[0]["display_name"] or "there")
                    .strip().split(" ")[0] or "there")

        # Grouped under the event's own label so a digest reads as sections
        # rather than a flat list of unrelated sentences.
        grouped: dict[str, list] = {}
        for r in items:
            grouped.setdefault(r["event_key"], []).append({"title": r["title"], "body": r["body"]})
        groups = [
            {"label": ev.EVENTS_BY_KEY[k].label, "items": v}
            for k, v in grouped.items() if k in ev.EVENTS_BY_KEY
        ]
        if not groups:
            continue

        total = sum(len(g["items"]) for g in groups)
        subject = (f"{org.name}: {groups[0]['items'][0]['title']}" if total == 1
                   else f"{org.name}: {total} things to know")
        html, text_body = _digest_html(
            org.name or "Your club", greeting, groups,
            f"{base}/admin", f"{base}/admin/notifications")

        result = await email_service.get_email_provider().send(email_service.EmailMessage(
            to_email=address,
            to_name=items[0]["display_name"] or None,
            subject=subject, html=html, text=text_body,
            from_email=app_settings.email_from_address,
            from_name=org.name or app_settings.email_from_name,
            reply_to=app_settings.email_reply_to,
            configuration_set=(app_settings.ses_configuration_set_transactional or "").strip() or None,
        ))

        ids = [str(r["delivery_id"]) for r in items]
        if result.ok:
            await session.execute(text("""
                UPDATE notification_deliveries
                SET status = 'sent', sent_at = NOW(), error = NULL
                WHERE id = ANY(CAST(:ids AS uuid[]))
            """), {"ids": ids})
            stats["emails_sent"] += 1
            stats["deliveries_sent"] += len(ids)
        else:
            # Recorded, not dropped: the next run picks a failed row up again,
            # and the reason is on the row rather than only in a log line.
            await session.execute(text("""
                UPDATE notification_deliveries
                SET status = 'failed', error = :err
                WHERE id = ANY(CAST(:ids AS uuid[]))
            """), {"ids": ids, "err": (result.error or "send failed")[:500]})
            stats["failed"] += len(ids)
    return stats


async def run_all() -> dict:
    """Daily pass across every live club. Never raises — a club that throws is
    logged and the next one still runs, the rule every scan in this codebase
    keeps."""
    from app.services import auto_sync

    totals = {"orgs_scanned": 0, "emitted": 0, "emails_sent": 0,
              "deliveries_sent": 0, "failed": 0, "sources_failed": 0}
    async with async_session_maker() as session:
        # The same eligibility the scheduled sync uses: a live, unarchived club
        # whose Core subscription has not lapsed. A club that has left the
        # platform should not still be emailing its admins.
        orgs, _skipped = await auto_sync.eligible_clubs(session)

    for org in orgs:
        async with async_session_maker() as session:
            try:
                fresh = await session.get(Organisation, org.id)
                if fresh is None:
                    continue
                totals["orgs_scanned"] += 1
                scanned = await scan_org(session, fresh)
                await session.commit()
                sent = await dispatch_emails(session, fresh)
                await session.commit()
                for key, value in {**scanned, **sent}.items():
                    if key in totals:
                        totals[key] += value
            except Exception:
                logger.exception("notification scan failed for org %s", org.id)
                await session.rollback()
    logger.info("Notification scan: %s", totals)
    return totals
