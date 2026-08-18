"""Trial lifecycle notifications + onboarding nudges (Phase 16, see
docs/self-serve-trial-onboarding-plan.md).

Extends the daily-scan pattern already used for Twenty CRM Task-raising
(twenty_leads_tasks._scan_trials_and_renewals) into real outbound email to
the club's own primary admin. A trial club has nobody watching a CRM — these
are the reminders that actually reach them. Deliberately CRM-independent
(unlike the Twenty scan, this runs whether or not Twenty is configured) and
scoped to every club with a module trial, not just the ones exported to
Twenty.

Six nudge types, each checked against ``trial_lifecycle_nudges.dedupe_key``
before sending and recorded only after a successful send (mirrors
twenty_links' check/act/record shape) so the daily scan never re-sends the
same nudge twice, and a provider failure or crash mid-send gets retried on
the next scan instead of being silently marked done:

  - trial_started       first day or two of a module trial
  - trial_ending_soon    TRIAL_ENDING_SOON_DAYS before it lapses
  - trial_ended          just lapsed, not yet converted
  - trial_converted      trial -> active (a real subscription)
  - no_historical_data   Core trial running NUDGE_HISTORICAL_DATA_DAYS+, the
                         onboarding wizard's "import_stats" step not done
  - module_unopened      a non-Core module trial running
                         NUDGE_MODULE_UNOPENED_DAYS+ with no page_view under
                         that module's admin route from anyone at the club

BetterAdmin's three billing members (fees/comms/merch) are collapsed to one
nudge via billing_key_for — a club that started a BetterAdmin trial gets one
email, not three. Off by default (platform_settings.trial_nudges_enabled) —
see Phase 0's "nothing here touches prod until a super admin flips it on"
caution; there is no staging environment for this app.

THE WORDING IS NOT IN THIS FILE. Each nudge reads a real comms_templates row
on the BetterCricket outreach org, editable in Comms -> Templates like any
other email (see TEMPLATE_DB_NAMES / seed_nudge_templates). The _SEED_BODY
copy below is the seed AND the fallback for an environment with no outreach
org designated, so a nudge still has something to say before anyone has been
near the Templates screen.

These stay TRANSACTIONAL sends, not BetterComms campaigns: they go straight
to the club's own admin, are not built from an audience, carry no
unsubscribe token and are not counted against a club's send allowance. Only
the wording moved.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import BILLABLE_MODULE_NAMES, billing_key_for
from app.config.settings import settings
from app.services import email_pause, email_service

logger = logging.getLogger(__name__)

# Tunable windows (days) — mirrors the constants at the top of
# twenty_leads_tasks.py.
SCAN_LOOKBACK_DAYS = 2          # daily-job margin so a missed run doesn't drop an event
TRIAL_ENDING_SOON_DAYS = 3
NUDGE_HISTORICAL_DATA_DAYS = 5
NUDGE_MODULE_UNOPENED_DAYS = 5

# Frontend admin route each module's dashboard tile links to
# (frontend/src/lib/modules.js MODULE_INFO[].to / MODULE_GROUPS.admin.to) —
# used to spot a page_view under that module since the trial started.
_MODULE_ROUTE = {
    "select": "/admin/betterselect",
    "socials": "/admin/bettersocials",
    "admin": "/admin/betteradmin",
    "iq": "/admin/betteriq",
    "fantasy": "/admin/fantasy",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _module_name(module_key: str) -> str:
    return BILLABLE_MODULE_NAMES.get(billing_key_for(module_key), module_key)


async def _primary_admin(session: AsyncSession, org_id) -> dict | None:
    """The club's own admin to nudge — the primary admin if one is set
    (always true for a self-serve-registered club), else any admin on the
    club with a usable email."""
    row = (await session.execute(text("""
        SELECT u.email, u.first_name, u.display_name
        FROM club_memberships cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.club_id = :org_id AND u.email IS NOT NULL AND u.email != ''
        ORDER BY cm.is_primary_admin DESC
        LIMIT 1
    """), {"org_id": org_id})).first()
    if row is None:
        return None
    return {"email": row.email, "first_name": row.first_name, "display_name": row.display_name}


def _greeting(admin: dict) -> str:
    return (admin.get("first_name") or admin.get("display_name") or "there").split(" ")[0]


async def _already_sent(session: AsyncSession, dedupe_key: str) -> bool:
    row = (await session.execute(
        text("SELECT 1 FROM trial_lifecycle_nudges WHERE dedupe_key = :k"), {"k": dedupe_key}
    )).first()
    return row is not None


async def _record_sent(session: AsyncSession, *, dedupe_key: str, organisation_id,
                       module_key: str | None, nudge_type: str) -> None:
    """Record a nudge AFTER it has actually been sent (never before) — a
    provider failure or crash mid-send must be retried next scan, not
    silently marked done. ON CONFLICT DO NOTHING since a single-process
    scheduler is the only writer here (no concurrent scan can race this)."""
    await session.execute(text("""
        INSERT INTO trial_lifecycle_nudges (id, organisation_id, module_key, nudge_type, dedupe_key)
        VALUES (:id, :org_id, :module_key, :nudge_type, :dedupe_key)
        ON CONFLICT (dedupe_key) DO NOTHING
    """), {
        "id": str(uuid.uuid4()), "org_id": organisation_id, "module_key": module_key,
        "nudge_type": nudge_type, "dedupe_key": dedupe_key,
    })
    await session.commit()


async def _send(admin: dict, subject: str, html: str, text_body: str) -> bool:
    msg = email_service.EmailMessage(
        to_email=admin["email"],
        to_name=admin.get("first_name") or admin.get("display_name"),
        subject=subject,
        html=html,
        text=text_body,
        from_email=settings.email_from_address,
        from_name=settings.email_from_name,
        reply_to=settings.email_reply_to,
        configuration_set=(settings.ses_configuration_set_transactional or "").strip() or None,
        # A daily scan sent this, not a person — held while automated email is
        # paused (services/email_pause).
        category=email_pause.CATEGORY_AUTOMATED,
    )
    result = await email_service.get_email_provider().send(msg)
    if not result.ok:
        logger.warning("trial_lifecycle: send failed for %s: %s", admin["email"], result.error)
    return result.ok


def _admin_url(path: str = "/admin") -> str:
    return f"{settings.public_base_url.rstrip('/')}{path}"


# ─── Editable templates (BetterClubhouse → Comms → Templates) ────────────────
#
# Every nudge's wording lives in a real ``comms_templates`` row on the
# BetterCricket outreach org, so a super admin edits these in Comms →
# Templates like any other email rather than needing a code change. Same
# shape sales_email.py already uses for the rep-facing templates: seed once
# (ON CONFLICT DO NOTHING, so an edited row is never overwritten), read at
# send time, and fall back to the hardcoded composer below when the outreach
# org isn't configured or the row is missing/empty.
#
# These stay TRANSACTIONAL sends, not BetterComms campaigns: no audience, no
# unsubscribe token, no send throttle. The template is the wording only.

# nudge_type -> the Comms → Templates row it reads from.
TEMPLATE_DB_NAMES = {
    "trial_started": "Trial started",
    "trial_ending_soon": "Trial ending soon",
    "trial_ended": "Trial ended",
    "trial_converted": "Trial converted to a subscription",
    "no_historical_data": "Trial nudge — import historical stats",
    "module_unopened": "Trial nudge — module never opened",
}

# Merge tokens every template may use. {{module}}, {{trial_end_date}} and
# {{module_url}} are empty for a nudge that has no module or no end date
# behind it (no_historical_data), so a template that references one still
# renders rather than leaking a raw token.
MERGE_TOKENS = (
    "first_name", "name", "club", "module", "trial_end_date",
    "dashboard_url", "pricing_url", "import_url", "module_url",
)

_BUTTON = (
    '<p style="margin:24px 0"><a href="{url}" style="display:inline-block;background:#16c784;'
    'color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;font-size:14px;'
    'font-weight:bold">{label}</a></p>'
)

_SEED_SUBJECT = {
    "trial_started": "Your {{module}} trial is live",
    "trial_ending_soon": "{{module}} trial ends {{trial_end_date}}",
    "trial_ended": "{{module}} trial has ended",
    "trial_converted": "Welcome aboard, {{module}} is now live",
    "no_historical_data": "Got older stats for {{club}}?",
    "module_unopened": "Haven't tried {{module}} yet?",
}

_SEED_BODY = {
    "trial_started": (
        "<p>Hi {{first_name}},</p>"
        "<p>{{club}}'s {{module}} trial just started, running until {{trial_end_date}}.</p>"
        "<p>Jump in and have a look around. Everything's already switched on, so there's "
        "nothing to set up.</p>"
        + _BUTTON.format(url="{{dashboard_url}}", label="Open your dashboard")
    ),
    "trial_ending_soon": (
        "<p>Hi {{first_name}},</p>"
        "<p>{{club}}'s {{module}} trial ends on {{trial_end_date}}.</p>"
        "<p>If it's been useful, get in touch and we'll set the club up on a proper "
        "subscription before access lapses. Have a look at what's included and what it "
        "costs on the pricing page.</p>"
        + _BUTTON.format(url="{{pricing_url}}", label="See pricing")
    ),
    "trial_ended": (
        "<p>Hi {{first_name}},</p>"
        "<p>{{club}}'s {{module}} trial has come to an end, so that module's back to "
        "read-only for now.</p>"
        "<p>Keen to keep using it? Reply to this email or subscribe from the pricing page "
        "and we'll turn it back on.</p>"
        + _BUTTON.format(url="{{pricing_url}}", label="Subscribe")
    ),
    "trial_converted": (
        "<p>Hi {{first_name}},</p>"
        "<p>{{club}} is now subscribed to {{module}}. Thanks for backing the club with it.</p>"
        "<p>Nothing changes day to day, the trial just doesn't run out any more.</p>"
        + _BUTTON.format(url="{{dashboard_url}}", label="Open your dashboard")
    ),
    "no_historical_data": (
        "<p>Hi {{first_name}},</p>"
        "<p>BetterCricket pulls in everything Cricket Australia has on {{club}}, but if the "
        "club's got older scorebooks, spreadsheets or a stats system from before that, you "
        "can bring that history across too.</p>"
        "<p>It's a CSV upload from the Import page. Takes a few minutes and fills in the "
        "gaps PlayHQ doesn't cover.</p>"
        + _BUTTON.format(url="{{import_url}}", label="Import historical stats")
    ),
    "module_unopened": (
        "<p>Hi {{first_name}},</p>"
        "<p>{{club}} picked up a {{module}} trial, but nobody's opened it yet.</p>"
        "<p>It's already set up and ready to go, worth a look before the trial runs out.</p>"
        + _BUTTON.format(url="{{module_url}}", label="Open {{module}}")
    ),
}


async def seed_nudge_templates(session: AsyncSession) -> int:
    """Insert every nudge's template into the outreach org's Comms library,
    once. ON CONFLICT DO NOTHING, so a row a super admin has since reworded
    is never clobbered — unlike comms.py's own starter-template seed there's
    no empty-row self-heal here, since none of these are ever auto-created
    empty. No-op (returns 0) when no outreach org is designated. Returns the
    count inserted."""
    from app.services.marketing_org import get_outreach_org

    org = await get_outreach_org(session)
    if org is None:
        return 0
    total = 0
    for nudge_type, name in TEMPLATE_DB_NAMES.items():
        result = await session.execute(text("""
            INSERT INTO comms_templates (id, organisation_id, name, subject, html)
            VALUES (gen_random_uuid(), :org_id, :name, :subject, :html)
            ON CONFLICT (organisation_id, name) DO NOTHING
        """), {
            "org_id": org.id, "name": name,
            "subject": _SEED_SUBJECT[nudge_type],
            # Plain string, never str.format() — the body holds {{token}}
            # placeholders and .format() reads "{{" as an escaped brace,
            # silently collapsing every {{club}} to {club} before it is even
            # stored (the trap sales_email.py's own seed documents).
            "html": _SEED_BODY[nudge_type],
        })
        total += result.rowcount or 0
    if total:
        await session.commit()
    return total


async def _load_template_row(session: AsyncSession, nudge_type: str):
    from sqlalchemy import select as _select

    from app.models.db import CommsTemplate
    from app.services.marketing_org import get_outreach_org

    org = await get_outreach_org(session)
    if org is None:
        return None
    return await session.scalar(_select(CommsTemplate).where(
        CommsTemplate.organisation_id == org.id,
        CommsTemplate.name == TEMPLATE_DB_NAMES[nudge_type],
    ))


def _build_context(*, admin: dict, org_name: str, module_name: str = "",
                   trial_ends_at: datetime | None = None, route: str | None = None) -> dict:
    """Every merge token, resolved. A token with nothing behind it resolves
    to an empty string rather than being left in the body as a raw
    {{placeholder}} for the club to read."""
    full_name = (admin.get("display_name") or admin.get("first_name") or "").strip()
    return {
        "first_name": _greeting(admin),
        "name": full_name or "there",
        "club": org_name,
        "module": module_name,
        "trial_end_date": trial_ends_at.strftime("%-d %B %Y") if trial_ends_at else "",
        "dashboard_url": _admin_url(),
        "pricing_url": _admin_url("/pricing"),
        "import_url": _admin_url("/admin/import"),
        "module_url": _admin_url(route) if route else _admin_url(),
    }


async def render_nudge(session: AsyncSession, nudge_type: str, ctx: dict) -> tuple[str, str, str]:
    """(subject, html, text) for one nudge — from its editable Comms template
    when the outreach org holds one with real content, else the hardcoded
    composer. A template pasted in as a full HTML document renders as-is; a
    fragment gets the BetterCricket shell wrapped around it."""
    row = await _load_template_row(session, nudge_type)
    if row is None or not (row.html or "").strip():
        return _compose_hardcoded(nudge_type, ctx)

    from app.routers.comms import _html_to_text, _is_full_doc, _merge

    subject = _merge(row.subject or _SEED_SUBJECT[nudge_type], ctx)
    body = _merge(row.html, ctx)
    html = body if _is_full_doc(body) else _wrap(body)
    return subject, html, _html_to_text(html)


# ─── Hardcoded fallback ──────────────────────────────────────────────────────
#
# Used when no outreach org is designated (so there is nowhere for the
# templates to live) or its row for this nudge is missing/blank. Kept in step
# with _SEED_BODY above by hand — an edit to one is worth making to the
# other, or the two say different things depending on how the environment is
# set up.

def _wrap(inner_html: str) -> str:
    """The BetterCricket shell. Deliberately NOT comms.py's club-branded
    campaign shell — this is a platform-level transactional send with no
    unsubscribe footer (see the module docstring), so it carries its own
    plain "you're getting this because" line instead."""
    # Written on one line per element, not indented — _html_to_text keeps
    # whatever whitespace it finds, and an indented shell leaves the plain
    # text part of every nudge ragged.
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;'
        'padding:24px;color:#1a1a1a">'
        '<p style="font-size:14px;color:#555">BetterCricket</p>'
        f"{inner_html}"
        '<p style="font-size:12px;color:#888;margin-top:24px">'
        "You're getting this because your club has an active trial on BetterCricket.</p>"
        "</div>"
    )


def _compose_hardcoded(nudge_type: str, ctx: dict) -> tuple[str, str, str]:
    from app.routers.comms import _html_to_text, _merge

    subject = _merge(_SEED_SUBJECT[nudge_type], ctx)
    html = _wrap(_merge(_SEED_BODY[nudge_type], ctx))
    return subject, html, _html_to_text(html)


# ─── Scan ───────────────────────────────────────────────────────────────────

async def _run_lifecycle_events(session: AsyncSession) -> dict:
    """trial_started / trial_ending_soon / trial_ended / trial_converted,
    scanned straight off org_module_subscriptions. BetterAdmin's three
    billing members collapse to one event via the dedupe key alone —
    whichever of fees/comms/merch is processed first sends and records the
    email, the other two then see it already recorded and no-op."""
    now = _now()
    lookback = now - timedelta(days=SCAN_LOOKBACK_DAYS)
    soon_horizon = now + timedelta(days=TRIAL_ENDING_SOON_DAYS)
    stats = {"trial_started": 0, "trial_ending_soon": 0, "trial_ended": 0, "trial_converted": 0}

    events = [
        ("trial_started", """
            SELECT s.organisation_id, s.module_key, s.trial_started_at, s.trial_ends_at, o.name
            FROM org_module_subscriptions s JOIN organisations o ON o.id = s.organisation_id
            WHERE s.status = 'trial' AND s.trial_started_at IS NOT NULL
              AND s.trial_started_at BETWEEN :lookback AND :now AND o.archived_at IS NULL
        """, {"lookback": lookback, "now": now}, "trial_started_at"),
        ("trial_ending_soon", """
            SELECT s.organisation_id, s.module_key, s.trial_started_at, s.trial_ends_at, o.name
            FROM org_module_subscriptions s JOIN organisations o ON o.id = s.organisation_id
            WHERE s.status = 'trial' AND s.trial_ends_at IS NOT NULL
              AND s.trial_ends_at BETWEEN :now AND :soon_horizon AND o.archived_at IS NULL
        """, {"now": now, "soon_horizon": soon_horizon}, "trial_ends_at"),
        ("trial_ended", """
            SELECT s.organisation_id, s.module_key, s.trial_started_at, s.trial_ends_at, o.name
            FROM org_module_subscriptions s JOIN organisations o ON o.id = s.organisation_id
            WHERE s.status = 'trial' AND s.trial_ends_at IS NOT NULL
              AND s.trial_ends_at < :now AND s.trial_ends_at >= :lookback AND o.archived_at IS NULL
        """, {"now": now, "lookback": lookback}, "trial_ends_at"),
        ("trial_converted", """
            SELECT s.organisation_id, s.module_key, s.trial_started_at, s.trial_ends_at, o.name
            FROM org_module_subscriptions s JOIN organisations o ON o.id = s.organisation_id
            WHERE s.status = 'active' AND s.trial_started_at IS NOT NULL
              AND s.updated_at BETWEEN :lookback AND :now AND o.archived_at IS NULL
        """, {"lookback": lookback, "now": now}, None),
    ]

    for nudge_type, query, params, date_field in events:
        rows = (await session.execute(text(query), params)).all()
        for row in rows:
            billing_key = billing_key_for(row.module_key)
            module_name = _module_name(row.module_key)
            date_value = getattr(row, date_field, None) if date_field else None
            date_part = date_value.date().isoformat() if date_value else ""
            dedupe_key = f"{nudge_type}:{billing_key}:{row.organisation_id}:{date_part}"
            try:
                if await _already_sent(session, dedupe_key):
                    continue
                admin = await _primary_admin(session, row.organisation_id)
                if admin is None:
                    logger.info("trial_lifecycle: no admin to nudge for org %s (%s)", row.organisation_id, nudge_type)
                    continue
                ctx = _build_context(admin=admin, org_name=row.name, module_name=module_name,
                                     trial_ends_at=row.trial_ends_at)
                subject, html, text_body = await render_nudge(session, nudge_type, ctx)
                if await _send(admin, subject, html, text_body):
                    await _record_sent(session, dedupe_key=dedupe_key, organisation_id=row.organisation_id,
                                       module_key=billing_key, nudge_type=nudge_type)
                    stats[nudge_type] += 1
            except Exception as e:  # noqa: BLE001
                await session.rollback()
                logger.error("trial_lifecycle: %s failed for org %s: %s", nudge_type, row.organisation_id, e)
    return stats


async def _run_no_historical_data(session: AsyncSession) -> int:
    now = _now()
    cutoff = now - timedelta(days=NUDGE_HISTORICAL_DATA_DAYS)
    rows = (await session.execute(text("""
        SELECT o.id AS organisation_id, o.name
        FROM organisations o
        JOIN org_module_subscriptions s ON s.organisation_id = o.id
            AND s.module_key = 'core' AND s.status = 'trial'
        LEFT JOIN onboarding_wizard_state ws ON ws.organisation_id = o.id
        WHERE s.trial_started_at IS NOT NULL AND s.trial_started_at <= :cutoff
          AND (s.trial_ends_at IS NULL OR s.trial_ends_at > :now)
          AND o.archived_at IS NULL
          AND (ws.completed_steps IS NULL OR NOT jsonb_exists(ws.completed_steps::jsonb, 'import_stats'))
    """), {"cutoff": cutoff, "now": now})).all()

    sent = 0
    for row in rows:
        dedupe_key = f"no_historical_data:core:{row.organisation_id}"
        try:
            if await _already_sent(session, dedupe_key):
                continue
            admin = await _primary_admin(session, row.organisation_id)
            if admin is None:
                continue
            ctx = _build_context(admin=admin, org_name=row.name)
            subject, html, text_body = await render_nudge(session, "no_historical_data", ctx)
            if await _send(admin, subject, html, text_body):
                await _record_sent(session, dedupe_key=dedupe_key, organisation_id=row.organisation_id,
                                   module_key="core", nudge_type="no_historical_data")
                sent += 1
        except Exception as e:  # noqa: BLE001
            await session.rollback()
            logger.error("trial_lifecycle: no_historical_data failed for org %s: %s", row.organisation_id, e)
    return sent


async def _run_module_unopened(session: AsyncSession) -> int:
    now = _now()
    cutoff = now - timedelta(days=NUDGE_MODULE_UNOPENED_DAYS)
    rows = (await session.execute(text("""
        SELECT s.organisation_id, s.module_key, s.trial_started_at, o.name
        FROM org_module_subscriptions s JOIN organisations o ON o.id = s.organisation_id
        WHERE s.status = 'trial' AND s.module_key != 'core'
          AND s.trial_started_at IS NOT NULL AND s.trial_started_at <= :cutoff
          AND (s.trial_ends_at IS NULL OR s.trial_ends_at > :now)
          AND o.archived_at IS NULL
    """), {"cutoff": cutoff, "now": now})).all()

    # Collapse BetterAdmin's fees/comms/merch to one check per club — they
    # share the one admin route, so any one member row stands for the group.
    seen_groups: set[tuple] = set()
    sent = 0
    for row in rows:
        billing_key = billing_key_for(row.module_key)
        group_key = (row.organisation_id, billing_key)
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        route = _MODULE_ROUTE.get(billing_key)
        if route is None:
            continue
        dedupe_key = f"module_unopened:{billing_key}:{row.organisation_id}"
        try:
            if await _already_sent(session, dedupe_key):
                continue
            opened = (await session.execute(text("""
                SELECT 1 FROM usage_events ue
                JOIN club_memberships cm ON cm.user_id = ue.user_id
                WHERE cm.club_id = :org_id AND ue.event_type = 'page_view'
                  AND ue.path LIKE :route_prefix AND ue.created_at >= :trial_started_at
                LIMIT 1
            """), {"org_id": row.organisation_id, "route_prefix": f"{route}%",
                   "trial_started_at": row.trial_started_at})).first()
            if opened is not None:
                continue
            admin = await _primary_admin(session, row.organisation_id)
            if admin is None:
                continue
            module_name = _module_name(row.module_key)
            ctx = _build_context(admin=admin, org_name=row.name, module_name=module_name, route=route)
            subject, html, text_body = await render_nudge(session, "module_unopened", ctx)
            if await _send(admin, subject, html, text_body):
                await _record_sent(session, dedupe_key=dedupe_key, organisation_id=row.organisation_id,
                                   module_key=billing_key, nudge_type="module_unopened")
                sent += 1
        except Exception as e:  # noqa: BLE001
            await session.rollback()
            logger.error("trial_lifecycle: module_unopened failed for org %s/%s: %s",
                        row.organisation_id, billing_key, e)
    return sent


async def scan_and_send(session: AsyncSession) -> dict:
    """Entry point for the daily scheduler job. Returns a stats dict for the
    log line. Every sub-scan isolates its own per-row failures — one bad club
    never stops the rest running."""
    # Self-heal: make sure the editable templates exist before anything is
    # rendered, so the first run of a freshly-configured environment already
    # reads from Comms -> Templates rather than the hardcoded fallback.
    try:
        await seed_nudge_templates(session)
    except Exception:  # noqa: BLE001 - never let seeding stop the scan
        await session.rollback()
        logger.exception("trial_lifecycle: template seed failed, falling back to built-in wording")

    stats = await _run_lifecycle_events(session)
    stats["no_historical_data"] = await _run_no_historical_data(session)
    stats["module_unopened"] = await _run_module_unopened(session)
    return stats
