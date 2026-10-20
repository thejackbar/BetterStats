"""A club's BetterComms sending limit follows its BetterAdmin subscription, a
capped send says how much is held back, and a capped club gets a batch EVERY day.

Reported: Applecross CC emailed 669 players on Thu 8 Oct. Their tier was Sandbox
(50 a day), so 50 went at once and the rest waited for the daily resume job. The
last player had the email on 18 Oct. Three faults sat behind that:

  1. Subscribing to BetterAdmin never touched ``organisations.comms_tier``, so a
     paying club stayed on the trial limit until a super admin approved a request
     that nobody told it to make.
  2. The club's daily window was a rolling 24 hours. The resume job (00:15 UTC)
     found the previous day's batch, stamped when it FINISHED a few seconds after
     00:15, still inside the window and sent nothing, so a capped club got a
     batch every OTHER day (300 sent in ten days is six batches of 50).
  3. Nothing on the send screen or the sent email said any of this was happening.

Runs the SHIPPED route bodies (``send_campaign``, ``resume_deferred_campaigns``),
the shipped subscription writers and the backfill script against a real
Postgres. A fake provider stands in for SES, and a controlled clock stands in
for the scheduler.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/verify_comms_tiers \
        python -m verification.verify_comms_tier_follows_subscription

Control: run it from a checkout of the commit before this change. Every new name
is read through a presence-safe accessor, so absence is REPORTED as a FAIL and
nothing crashes.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_comms_tiers",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.auth.modules import (  # noqa: E402
    MODULE_ADMIN, MODULE_COMMS, MODULE_FEES, STATUS_ACTIVE, STATUS_CANCELLED,
    STATUS_PAST_DUE, STATUS_PAUSED, STATUS_TRIAL,
)
from app.models.db import (  # noqa: E402
    Base, CommsCampaign, CommsContact, CommsRecipient, Organisation, User,
)
from app.routers import comms  # noqa: E402
from app.services import comms_limits  # noqa: E402
from app.services import module_subscriptions as mod_subs  # noqa: E402
from app.services.email_service import SendResult  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# ── The clock and the provider ──────────────────────────────────────────────

class Clock:
    """``start`` is when a job begins (what the allowance is measured at);
    ``finish`` is when its batch is stamped, a few seconds later, which is what
    made yesterday's batch still count at 00:15 today."""
    start = datetime(2026, 10, 8, 1, 44, 33, tzinfo=timezone.utc)
    finish = start + timedelta(seconds=5)

    @classmethod
    def set(cls, start: datetime, duration: int = 5) -> None:
        cls.start = start
        cls.finish = start + timedelta(seconds=duration)


class FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return Clock.finish


class FakeProvider:
    name = "ses"

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, msg):
        self.sent.append(msg.to_email)
        return SendResult(ok=True, message_id=f"m-{len(self.sent)}")


class NoLimit:
    async def acquire(self) -> None:
        return None


PROVIDER = FakeProvider()
comms.get_email_provider = lambda: PROVIDER
comms.send_limiter = NoLimit()
comms.datetime = FakeDatetime
comms_limits._now = lambda: Clock.start


async def _no_directory_reconcile(db, club):
    """The audience here is hand-added contacts. The Directory read that normally
    tops contacts up first needs lifespan-only tables (fee_members columns,
    member_membership_types, player_achievements) that create_all cannot see, and
    it has nothing to do with sending limits."""
    return None


comms.reconcile_contacts_from_directory = _no_directory_reconcile


# ── Helpers ─────────────────────────────────────────────────────────────────

def present(obj, name):
    """A presence-safe accessor: the control run has none of the new names."""
    return getattr(obj, name, None)


async def load(Session, org_id):
    """A fresh read, so a value is what was committed, not what a loaded object remembers."""
    async with Session() as s:
        return (await s.execute(select(Organisation).options(
            selectinload(Organisation.module_subscriptions)).where(Organisation.id == org_id))).scalar_one()


async def make_club(Session, name, tier="sandbox", comms_status=None, **kw):
    async with Session() as s:
        org = Organisation(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"),
                           comms_tier=tier, module_subscriptions=[], **kw)
        s.add(org)
        await s.flush()
        if comms_status == STATUS_TRIAL:
            mod_subs.start_trial_billing(org, MODULE_ADMIN, days=14)
        elif comms_status:
            for key in mod_subs.expand_billing_module(MODULE_ADMIN):
                mod_subs.upsert_subscription(org, key, status=comms_status)
            # A club that was handed these rows is not a "transition" test subject:
            # put its tier back where the case says it is.
            org.comms_tier = tier
        await s.commit()
        return org.id


async def with_org(Session, org_id, fn):
    """Load the club with its subscriptions, run a shipped writer, commit."""
    async with Session() as s:
        org = (await s.execute(select(Organisation).options(
            selectinload(Organisation.module_subscriptions)).where(Organisation.id == org_id))).scalar_one()
        fn(org)
        await s.commit()


async def tier_of(Session, org_id) -> str:
    return (await load(Session, org_id)).comms_tier


async def make_audience(Session, org_id, n, prefix):
    async with Session() as s:
        for i in range(n):
            s.add(CommsContact(id=uuid.uuid4(), organisation_id=org_id,
                               email=f"{prefix}{i}@example.com", name=f"{prefix}{i}",
                               source="manual", subscribed=True))
        await s.commit()


async def new_campaign(Session, org_id, subject):
    async with Session() as s:
        c = CommsCampaign(id=uuid.uuid4(), organisation_id=org_id, name=subject, subject=subject,
                          body_html="<p>Important reminder</p>", status="draft",
                          audience={"type": "all"})
        s.add(c)
        await s.commit()
        return c.id


async def press_send(Session, org_id, campaign_id, staff_id):
    """The shipped route body, then wait for its detached send task."""
    async with Session() as s:
        org = await s.get(Organisation, org_id)
        staff = await s.get(User, staff_id)
        res = await comms.send_campaign(campaign_id=str(campaign_id), user=staff, club=org, db=s)
    if comms._SEND_TASKS:
        await asyncio.gather(*list(comms._SEND_TASKS))
    return res


async def counts(Session, campaign_id):
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT status, count(*) FROM comms_recipients WHERE campaign_id = :c GROUP BY 1"),
            {"c": campaign_id})).all()
        status = (await s.execute(text("SELECT status FROM comms_campaigns WHERE id = :c"),
                                  {"c": campaign_id})).scalar_one()
    d = {k: int(v) for k, v in rows}
    return d.get("sent", 0), d.get("deferred", 0), status


def at_resume(day: datetime, jitter: int = 0) -> None:
    """The scheduler fires at 00:15 UTC; ``jitter`` is how late it actually starts."""
    Clock.set(day.replace(hour=0, minute=15, second=0, microsecond=0) + timedelta(seconds=jitter))


# ── 1. The rule, as a table ─────────────────────────────────────────────────

def check_rule_table() -> None:
    print("\n── The tier rule ───────────────────────────────────────────────")
    rule = present(comms_limits, "tier_after_comms_status")
    if rule is None:
        check("tier_after_comms_status exists", False, "absent")
        return
    cases = [
        # (tier, previous, new, expected, label)
        ("sandbox", STATUS_TRIAL, STATUS_ACTIVE, "production", "trial -> active lifts Sandbox to Production"),
        ("sandbox", None, STATUS_ACTIVE, "production", "a brand new active module lifts Sandbox"),
        ("sandbox", STATUS_PAST_DUE, STATUS_ACTIVE, "production", "past_due -> active lifts Sandbox"),
        ("sandbox", STATUS_ACTIVE, STATUS_ACTIVE, None, "a renewal (active -> active) changes nothing"),
        ("sandbox", None, STATUS_TRIAL, None, "starting a trial changes nothing"),
        ("sandbox", STATUS_ACTIVE, STATUS_PAST_DUE, None, "a late payment changes nothing"),
        ("production", STATUS_ACTIVE, STATUS_PAST_DUE, None, "past_due does not demote Production"),
        ("production", STATUS_ACTIVE, STATUS_CANCELLED, "sandbox", "cancelled returns Production to Sandbox"),
        ("production", STATUS_ACTIVE, STATUS_PAUSED, "sandbox", "paused returns Production to Sandbox"),
        ("production", STATUS_PAUSED, STATUS_CANCELLED, None, "paused -> cancelled is already lapsed"),
        ("suspended", STATUS_TRIAL, STATUS_ACTIVE, None, "a suspended club is NOT lifted by subscribing"),
        ("suspended", STATUS_ACTIVE, STATUS_CANCELLED, None, "a suspended club is left suspended on cancel"),
        ("production", STATUS_TRIAL, STATUS_ACTIVE, None, "an already-Production club is left alone"),
    ]
    for tier, prev, new, want, label in cases:
        got = rule(tier, prev, new)
        check(label, got == want, f"got {got!r}, wanted {want!r}")


# ── 2. The rule, through the shipped writers, committed and re-read ─────────

async def check_subscription_flows(Session) -> None:
    print("\n── Subscribing and lapsing, through the shipped writers ───────")
    # Trial: the self-serve starting point. Stays Sandbox, and cannot request more.
    a = await make_club(Session, "Trial Club", comms_status=STATUS_TRIAL)
    check("a club on a BetterAdmin trial is on Sandbox", await tier_of(Session, a) == "sandbox")

    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    check("converting the trial to active lifts the club to Production",
          await tier_of(Session, a) == "production", await tier_of(Session, a))

    # A renewal re-sets active. A super admin who put the club back on Sandbox by
    # hand (not suspended) must not be overridden on every renewal.
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET comms_tier='sandbox' WHERE id=:i"), {"i": a})
        await s.commit()
    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    check("a renewal does not undo a hand-set Sandbox",
          await tier_of(Session, a) == "sandbox", await tier_of(Session, a))

    # Pair: the same flow from a genuine transition DOES lift, so the check above
    # is not passing because the hook never runs.
    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_PAUSED))
    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    check("pausing then reactivating lifts again (the hook is live)",
          await tier_of(Session, a) == "production", await tier_of(Session, a))

    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_PAST_DUE))
    check("a failed payment (past_due) does not drop the club to Sandbox",
          await tier_of(Session, a) == "production", await tier_of(Session, a))

    await with_org(Session, a, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_CANCELLED))
    check("cancelling BetterAdmin returns the club to Sandbox",
          await tier_of(Session, a) == "sandbox", await tier_of(Session, a))

    # Removing the module outright (a super admin toggling it off) is a lapse too.
    b = await make_club(Session, "Toggled Club", comms_status=STATUS_ACTIVE, tier="production")
    await with_org(Session, b, lambda o: mod_subs.remove_billing(o, MODULE_ADMIN))
    check("removing the BetterComms module returns the club to Sandbox",
          await tier_of(Session, b) == "sandbox", await tier_of(Session, b))

    # The super admin module toggle (reconcile_held_modules) grants active rows.
    c = await make_club(Session, "Granted Club")
    await with_org(Session, c, lambda o: mod_subs.reconcile_held_modules(o, [MODULE_COMMS]))
    check("a super admin granting BetterComms lifts the club to Production",
          await tier_of(Session, c) == "production", await tier_of(Session, c))

    # Only the comms key moves the tier: the other BetterAdmin keys must not.
    d = await make_club(Session, "Fees Only Club")
    await with_org(Session, d, lambda o: mod_subs.upsert_subscription(o, MODULE_FEES, status=STATUS_ACTIVE))
    check("an active Fees module on its own does not change the sending tier",
          await tier_of(Session, d) == "sandbox", await tier_of(Session, d))

    # A suspended club is not lifted by paying; only a super admin reinstates.
    e = await make_club(Session, "Suspended Club", tier="suspended", comms_status=STATUS_TRIAL)
    await with_org(Session, e, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    check("a suspended club stays suspended when it subscribes",
          await tier_of(Session, e) == "suspended", await tier_of(Session, e))

    # The outreach org is uncapped whatever its tier and is not touched.
    f = await make_club(Session, "Outreach Org", is_marketing_outreach=True, comms_status=STATUS_TRIAL)
    await with_org(Session, f, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    check("the marketing outreach org's tier is never rewritten",
          await tier_of(Session, f) == "sandbox", await tier_of(Session, f))


# ── 3. A capped club gets a batch every day ─────────────────────────────────

async def check_daily_batches(Session, staff_id) -> None:
    print("\n── A Sandbox club's 120-recipient send, day by day ────────────")
    club = await make_club(Session, "Capped Club")
    await make_audience(Session, club, 120, "cap")
    camp = await new_campaign(Session, club, "Important Reminder")

    Clock.set(datetime(2026, 10, 8, 1, 44, 33, tzinfo=timezone.utc))
    res = await press_send(Session, club, camp, staff_id)
    sent, deferred, status = await counts(Session, camp)
    check("day 0: the first 50 go out at once", sent == 50, f"sent {sent}")
    check("the send says how many go now", res.get("sending_now") == 50, f"sending_now={res.get('sending_now')!r}")
    check("the send says how many are held back", res.get("deferred") == 70, f"deferred={res.get('deferred')!r}")
    nxt = res.get("next_batch_at")
    check("the send says when the next batch is (00:15 UTC the next day)",
          bool(nxt) and datetime.fromisoformat(nxt) == datetime(2026, 10, 9, 0, 15, tzinfo=timezone.utc),
          f"next_batch_at={nxt!r}")
    check("the campaign stays sending while recipients wait", status == "sending", status)

    # The cap is still a cap: another pass on the same day sends nothing more.
    Clock.set(datetime(2026, 10, 8, 6, 0, 0, tzinfo=timezone.utc))
    await comms.resume_deferred_campaigns()
    sent, deferred, _ = await counts(Session, camp)
    check("a second pass the same day respects the cap", sent == 50, f"sent {sent}")

    # Day 1: the resume job starts a little late, as it does. Yesterday's batch
    # was stamped after it finished (00:15:05 or later). It must NOT count today.
    at_resume(datetime(2026, 10, 9), jitter=2)
    await comms.resume_deferred_campaigns()
    sent, deferred, status = await counts(Session, camp)
    check("day 1: the resume job sends the next 50 (not skipped)", sent == 100, f"sent {sent}")

    at_resume(datetime(2026, 10, 10), jitter=0)
    await comms.resume_deferred_campaigns()
    sent, deferred, status = await counts(Session, camp)
    check("day 2: the last 20 go out and the campaign is sent",
          sent == 120 and deferred == 0 and status == "sent", f"sent {sent} deferred {deferred} {status}")

    # The window is a fixed UTC day, so jitter either way cannot move a batch.
    print("\n── The resume job's start time cannot skip a day ──────────────")
    for jitter in (0, 1, 4, 30):
        club2 = await make_club(Session, f"Jitter Club {jitter}")
        await make_audience(Session, club2, 150, f"j{jitter}_")
        camp2 = await new_campaign(Session, club2, f"Reminder {jitter}")
        Clock.set(datetime(2026, 10, 8, 1, 44, 33, tzinfo=timezone.utc))
        await press_send(Session, club2, camp2, staff_id)
        got = []
        for day in (9, 10):
            at_resume(datetime(2026, 10, day), jitter=jitter)
            await comms.resume_deferred_campaigns()
            got.append((await counts(Session, camp2))[0])
        check(f"start {jitter}s late: 50, 100, 150 across three days", got == [100, 150],
              f"cumulative after days 1 and 2: {got}")


# ── 4. Subscribing mid-send frees the rest ──────────────────────────────────

async def check_subscribe_mid_send(Session, staff_id) -> None:
    print("\n── A club that subscribes while its email is held back ────────")
    club = await make_club(Session, "Subscribes Mid Send", comms_status=STATUS_TRIAL)
    await make_audience(Session, club, 120, "sub")
    camp = await new_campaign(Session, club, "Availability")
    Clock.set(datetime(2026, 10, 8, 1, 44, 33, tzinfo=timezone.utc))
    await press_send(Session, club, camp, staff_id)
    check("on trial, only 50 of 120 go out", (await counts(Session, camp))[0] == 50)

    await with_org(Session, club, lambda o: mod_subs.set_status_billing(o, MODULE_ADMIN, STATUS_ACTIVE))
    at_resume(datetime(2026, 10, 9))
    await comms.resume_deferred_campaigns()
    sent, deferred, status = await counts(Session, camp)
    check("after subscribing, the next resume sends everything left",
          sent == 120 and status == "sent", f"sent {sent}, {status}")

    prod = await make_club(Session, "Already Production", tier="production")
    await make_audience(Session, prod, 120, "prod")
    camp2 = await new_campaign(Session, prod, "Production send")
    Clock.set(datetime(2026, 10, 8, 1, 44, 33, tzinfo=timezone.utc))
    res = await press_send(Session, prod, camp2, staff_id)
    sent, deferred, status = await counts(Session, camp2)
    check("a Production club sends all 120 at once with nothing held back",
          sent == 120 and deferred == 0 and res.get("deferred") == 0,
          f"sent {sent}, deferred {deferred}, route deferred={res.get('deferred')!r}")


# ── 5. The backfill ─────────────────────────────────────────────────────────

async def check_backfill(Session) -> None:
    print("\n── sync_comms_tiers: clubs that were already subscribed ───────")
    try:
        from app.scripts import sync_comms_tiers
    except ImportError:
        check("app.scripts.sync_comms_tiers exists", False, "absent")
        return

    # Clear the earlier cases so the run reports on exactly the clubs built here.
    async with Session() as s:
        await s.execute(text("DELETE FROM org_module_subscriptions"))
        await s.execute(text("UPDATE organisations SET comms_tier='sandbox'"))
        await s.commit()

    paying = await make_club(Session, "Paying On Sandbox", comms_status=STATUS_ACTIVE, tier="sandbox")
    trial = await make_club(Session, "Still On Trial", comms_status=STATUS_TRIAL)
    cancelled = await make_club(Session, "Cancelled", comms_status=STATUS_CANCELLED, tier="sandbox")
    hand_lifted = await make_club(Session, "Hand Lifted", tier="production")
    suspended = await make_club(Session, "Breaker Tripped", comms_status=STATUS_ACTIVE, tier="suspended")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await sync_comms_tiers.run("all", apply=False)
    out = buf.getvalue()
    check("dry run exits cleanly", rc == 0, f"rc={rc}")
    check("dry run writes nothing", await tier_of(Session, paying) == "sandbox")
    check("dry run names the paying club it would lift", "Paying On Sandbox" in out, out[:300])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await sync_comms_tiers.run("all", apply=True)
    check("--apply lifts the paying Sandbox club", await tier_of(Session, paying) == "production")
    check("--apply leaves a trial club alone", await tier_of(Session, trial) == "sandbox")
    check("--apply leaves a cancelled club alone", await tier_of(Session, cancelled) == "sandbox")
    check("--apply never demotes a hand-lifted Production club", await tier_of(Session, hand_lifted) == "production")
    check("--apply lists the hand-lifted club for a person to decide", "Hand Lifted" in buf.getvalue())
    check("--apply leaves a suspended club suspended", await tier_of(Session, suspended) == "suspended")


# ── Main ────────────────────────────────────────────────────────────────────

async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py, migration 120). The tier defaults and the account
        # daily limit are read from it; a missing table is swallowed by
        # _tier_defaults but aborts the transaction under it.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{\"default_trial_days\": 14}') "
            "ON CONFLICT (id) DO NOTHING"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        staff = User(id=uuid.uuid4(), username="staff", email="staff@example.com")
        s.add(staff)
        await s.commit()
        staff_id = staff.id

    check_rule_table()
    await check_subscription_flows(Session)
    await check_daily_batches(Session, staff_id)
    await check_subscribe_mid_send(Session, staff_id)
    await check_backfill(Session)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
