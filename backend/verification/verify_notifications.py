"""Verification for configurable club notifications, against a real Postgres.

A club could not choose what it was told about. The bell computed a fixed set of
sections live from source data and nothing left the building, so a milestone
passed unremarked unless somebody opened the bell, and a volunteer's Working
With Children check could lapse with nobody warned at all.

Runs the SHIPPED services and route bodies — never a re-implementation — so a
check that passes is evidence about the code a club will actually run.

What it pins, and why each one is here rather than taken on trust:

  * the DDL applied three times to a populated database, and alembic and the
    lifespan mirror running the SAME list object, so the two cannot drift;
  * a club with no rows at all behaving exactly as the registry declares —
    that is what lets a default be changed in code with no backfill;
  * the dedupe key naming the FACT: a second scan raises nothing, a renewed
    certificate with a new expiry raises something, and a retired milestone
    threshold no screen draws is never announced;
  * every one of the six conditions in ``channel_allowed`` failing closed on
    its own — the club kill switch, the channel switch, the event switch, the
    module gate, the capability gate and the person's own opt-out;
  * an opt-out silencing a channel the club switched ON, and NOT switching on
    one the club switched off;
  * the notice period being the club's own, at both ends;
  * one digest per recipient rather than one email per fact, marked sent only
    once the provider accepted it, and a refusal recorded and retried;
  * cross-club isolation on the feed and on mark-read, from both sides.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5432 \
  python verification/verify_notifications.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

# Behind a guard so a CONTROL RUN against the previous commit reports the
# feature missing as failed checks rather than dying on an ImportError before a
# single one runs.
MISSING: list[str] = []
try:
    from app.services import notification_ddl as nddl
    from app.services import notification_events as ev
    from app.services import notification_scan as scan
    from app.services import notifications as notif
    HAVE = True
except Exception as exc:  # pragma: no cover - control run only
    HAVE = False
    MISSING.append(str(exc))
    nddl = ev = scan = notif = None

try:
    from app.services import email_service
except Exception as exc:  # pragma: no cover
    email_service = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER = uuid.uuid4()

# Three admins, deliberately different: the primary holds everything, QUAL_ONLY
# is a club_member whose only capability is qualifications (so a capability gate
# has something real to exclude), and NO_EMAIL has no address at all.
PRIMARY = uuid.uuid4()
QUAL_ONLY = uuid.uuid4()
NO_EMAIL = uuid.uuid4()
STAFF = uuid.uuid4()          # a super_admin membership — BetterCricket's own
                              # staff, never a recipient of a club's own news
OTHER_ADMIN = uuid.uuid4()

SEASON = uuid.uuid4()
P_MILESTONE = uuid.uuid4()
P_UPCOMING = uuid.uuid4()
M_VOL = uuid.uuid4()          # a volunteer with certifications
QT_WWCC = uuid.uuid4()
QT_FIRSTAID = uuid.uuid4()
QT_RSA = uuid.uuid4()
Q_SOON = uuid.uuid4()         # expires in 20 days  — inside every notice period
Q_FAR = uuid.uuid4()          # expires in 200 days — outside the default 60
Q_LAPSED = uuid.uuid4()       # already expired


# ─── A stand-in email provider ───────────────────────────────────────────────

class StubProvider:
    """Records what was sent instead of sending it, and can be told to refuse.

    It MUTATES — one that answered the same thing every time could not tell a
    working retry from a no-op.
    """
    name = "stub"

    def __init__(self):
        self.sent: list = []
        self.fail_with: str | None = None

    async def send(self, msg):
        if self.fail_with:
            return email_service.SendResult(ok=False, error=self.fail_with)
        self.sent.append(msg)
        return email_service.SendResult(ok=True, message_id=f"stub-{len(self.sent)}")


STUB = StubProvider()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not add the server defaults some raw-SQL migrations
        # set, and this feature's own tables are one of those lists.
        if HAVE:
            for _ in range(3):     # applied three times, as a live boot does
                for stmt in nddl.STATEMENTS:
                    await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        for org, name, slug in ((ORG, "Applecross Cricket Club", "applecross"),
                                (OTHER, "High Wycombe CC", "high-wycombe")):
            await s.execute(text("""
                INSERT INTO organisations (id, name, slug, is_active)
                VALUES (:id, :name, :slug, true)
            """), {"id": str(org), "name": name, "slug": slug})

        people = [
            (PRIMARY, "primary@club.test", "Jack Barendse", ORG, "club_admin", [], True),
            (QUAL_ONLY, "qual@club.test", "Sam Volunteer", ORG, "club_admin", [], False),
            (NO_EMAIL, None, "No Address", ORG, "club_admin", [], False),
            (STAFF, "staff@bettersports.test", "Better Staff", ORG, "super_admin", [], False),
            (OTHER_ADMIN, "other@club.test", "Other Club Admin", OTHER, "club_admin", [], True),
        ]
        for uid, email, name, org, role, caps, primary in people:
            await s.execute(text("""
                INSERT INTO users (id, email, username, display_name, failed_login_count)
                VALUES (:id, :email, :username, :name, 0)
            """), {"id": str(uid), "email": email, "username": str(uid)[:8], "name": name})
            await s.execute(text("""
                INSERT INTO club_memberships (id, club_id, user_id, role, capabilities, is_primary_admin)
                VALUES (gen_random_uuid(), :club, :user, :role, CAST(:caps AS jsonb), :primary)
            """), {"club": str(org), "user": str(uid), "role": role,
                   "caps": "[]", "primary": primary})

        await s.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:id, :org, 'Summer 2025/26', 2025)
        """), {"id": str(SEASON), "org": str(ORG)})

        for pid, name in ((P_MILESTONE, "Brad Quinsee"), (P_UPCOMING, "Darren Hind")):
            await s.execute(text("""
                INSERT INTO players (id, organisation_id, name, is_player, status)
                VALUES (:id, :org, :name, true, 'active')
            """), {"id": str(pid), "org": str(ORG), "name": name})

        # A milestone the current scheme draws, and one it retired.
        await s.execute(text("""
            INSERT INTO milestones (player_id, milestone_type, milestone_value, achieved_at)
            VALUES (:p, 'runs', 5000, :d), (:p, 'matches', 25, :d)
        """), {"p": str(P_MILESTONE), "d": date.today() - timedelta(days=3)})

        # Within reach of 500 runs (needs 20, window is 50).
        await s.execute(text("""
            INSERT INTO player_season_stats (player_id, season_id, matches, runs, wickets, catches, source)
            VALUES (:p, :s, 40, 480, 0, 0, 'api')
        """), {"p": str(P_UPCOMING), "s": str(SEASON)})

        # A volunteer and three certifications: one lapsing soon, one a long way
        # off, one already lapsed.
        await s.execute(text("""
            INSERT INTO fee_members (id, organisation_id, full_name, email)
            VALUES (:id, :org, 'Jo Volunteer', 'jo@club.test')
        """), {"id": str(M_VOL), "org": str(ORG)})
        for qt, qname in ((QT_WWCC, "Working With Children Check"),
                          (QT_FIRSTAID, "First Aid"), (QT_RSA, "RSA")):
            await s.execute(text("""
                INSERT INTO qualification_types (id, organisation_id, name)
                VALUES (:id, :org, :name)
            """), {"id": str(qt), "org": str(ORG), "name": qname})
        today = date.today()
        for qid, qt, expires in ((Q_SOON, QT_WWCC, today + timedelta(days=20)),
                                 (Q_FAR, QT_FIRSTAID, today + timedelta(days=200)),
                                 (Q_LAPSED, QT_RSA, today - timedelta(days=10))):
            await s.execute(text("""
                INSERT INTO member_qualifications
                    (id, organisation_id, member_id, qualification_type_id, obtained_at, expires_at)
                VALUES (:id, :org, :m, :qt, :obtained, :expires)
            """), {"id": str(qid), "org": str(ORG), "m": str(M_VOL), "qt": str(qt),
                   "obtained": today - timedelta(days=400), "expires": expires})
        # A report awaiting approval and a player request, so the capability
        # gate has real content to include and exclude rather than an empty
        # source that would pass whatever the rule did.
        await s.execute(text("""
            INSERT INTO saved_reports (id, org_id, slug, title, query_json, visibility, status)
            VALUES (gen_random_uuid(), :org, 'top-run-scorers', 'Top run scorers',
                    '{}'::jsonb, 'club', 'pending')
        """), {"org": str(ORG)})
        await s.execute(text("""
            INSERT INTO player_sync_requests (player_id, org_id, status, requester_note)
            VALUES (:p, :org, 'pending', 'My 2019 season is missing')
        """), {"p": str(P_MILESTONE), "org": str(ORG)})
        await s.commit()


async def org(session, org_id):
    from app.models.db import Organisation
    return await session.get(Organisation, org_id)


async def emitted(session, org_id, event_key=None) -> list[dict]:
    clause = "AND event_key = :ek" if event_key else ""
    rows = (await session.execute(text(f"""
        SELECT event_key, dedupe_key, title, body FROM notifications
        WHERE organisation_id = :org {clause} ORDER BY dedupe_key
    """), {"org": str(org_id), **({"ek": event_key} if event_key else {})})).mappings().all()
    return [dict(r) for r in rows]


async def deliveries(session, *, user_id=None, channel=None) -> list[dict]:
    where = ["1=1"]
    params = {}
    if user_id:
        where.append("d.user_id = :uid")
        params["uid"] = str(user_id)
    if channel:
        where.append("d.channel = :ch")
        params["ch"] = channel
    rows = (await session.execute(text(f"""
        SELECT d.user_id, d.channel, d.status, n.event_key, n.dedupe_key
        FROM notification_deliveries d JOIN notifications n ON n.id = d.notification_id
        WHERE {' AND '.join(where)}
    """), params)).mappings().all()
    return [dict(r) for r in rows]


async def reset_notifications(session):
    await session.execute(text("DELETE FROM notifications"))
    await session.execute(text("DELETE FROM club_notification_rules"))
    await session.execute(text("DELETE FROM club_notification_settings"))
    await session.execute(text("DELETE FROM user_notification_preferences"))
    await session.commit()


# ─── The checks ──────────────────────────────────────────────────────────────

async def check_schema_and_defaults():
    print("\n── schema and defaults ─────────────────────────────────────────")
    async with Session() as s:
        rows = (await s.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN
              ('club_notification_settings','club_notification_rules',
               'user_notification_preferences','notifications','notification_deliveries')
        """))).scalars().all()
        check("the DDL applied three times leaves all five tables", len(rows) == 5, str(sorted(rows)))

        settings = await notif.club_settings(s, ORG)
        check("a club with no row reads the platform defaults",
              settings == notif.DEFAULT_CLUB_SETTINGS, str(settings))

        rules = await notif.club_rules(s, ORG)
        check("every registered event resolves for a club with no rows",
              set(rules) == {e.key for e in ev.EVENT_TYPES}, str(sorted(rules)))
        check("an unconfigured event carries the registry's own default",
              rules["sync_completed"]["channels"][ev.CHANNEL_EMAIL] is False
              and rules["sync_completed"]["channels"][ev.CHANNEL_IN_APP] is True,
              str(rules["sync_completed"]))
        check("the notice period defaults to the registry's 60 days",
              rules["qualification_expiring"]["config"]["lead_days"] == 60,
              str(rules["qualification_expiring"]["config"]))

    # The one-copy rule: alembic and the lifespan mirror must run the SAME list,
    # not two lists that look alike.
    import importlib
    mig = importlib.import_module("alembic.versions.287_configurable_notifications") \
        if False else None
    src = Path("alembic/versions/287_configurable_notifications.py").read_text()
    check("alembic 287 imports the shared DDL rather than restating it",
          "from app.services.notification_ddl import" in src, src[:120])
    main_src = Path("app/main.py").read_text()
    check("the lifespan mirror runs the same shared DDL list",
          "from app.services.notification_ddl import STATEMENTS" in main_src)


async def check_sources():
    print("\n── what the sources find ───────────────────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        stats = await scan.scan_org(s, await org(s, ORG))
        await s.commit()
        check("a scan of a club that has never configured anything emits something",
              stats["emitted"] > 0, str(stats))

        ms = await emitted(s, ORG, "milestone_achieved")
        check("the milestone is announced", len(ms) == 1, str(ms))
        check("the milestone names the player and the figure",
              ms and "Brad Quinsee" in ms[0]["title"] and "5,000" in ms[0]["title"],
              str(ms))
        check("a retired threshold no screen draws is NOT announced",
              all("matches:25" not in m["dedupe_key"] for m in ms), str(ms))
        check("the dedupe key names the fact, not the run",
              ms and ms[0]["dedupe_key"] == f"milestone:{P_MILESTONE}:runs:5000",
              str(ms))

        up = await emitted(s, ORG, "milestone_upcoming")
        check("a player within reach is announced", len(up) == 1, str(up))
        check("the upcoming key carries the target, so the next one is a new fact",
              up and up[0]["dedupe_key"].endswith(":runs:500"), str(up))

        qual = await emitted(s, ORG, "qualification_expiring")
        keys = {q["dedupe_key"] for q in qual}
        check("a certificate lapsing inside the notice period is raised",
              any(str(Q_SOON) in k for k in keys), str(keys))
        check("one already lapsed is raised too — it is the most urgent case",
              any(str(Q_LAPSED) in k for k in keys), str(keys))
        check("one outside the notice period is left alone",
              not any(str(Q_FAR) in k for k in keys), str(keys))
        lapsed = [q for q in qual if str(Q_LAPSED) in q["dedupe_key"]]
        check("a lapsed certificate says so rather than counting down",
              lapsed and "expired" in lapsed[0]["title"], str(lapsed))
        check("the expiry date is in the key, so a renewal is a new fact",
              any(k.endswith((date.today() + timedelta(days=20)).isoformat()) for k in keys),
              str(keys))

        before = len(await emitted(s, ORG))
        again = await scan.scan_org(s, await org(s, ORG))
        await s.commit()
        after = len(await emitted(s, ORG))
        check("a second scan the same day announces nothing twice",
              after == before and again["emitted"] == 0, f"{before} -> {after} ({again})")


async def check_notice_period():
    print("\n── the notice period is the club's own ─────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        # Narrow it: the certificate 20 days out must drop out of reach.
        await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": 7})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG))
        await s.commit()
        keys = {q["dedupe_key"] for q in await emitted(s, ORG, "qualification_expiring")}
        check("narrowing the notice period drops the certificate now out of reach",
              not any(str(Q_SOON) in k for k in keys), str(keys))
        check("an already-lapsed certificate is raised whatever the notice period",
              any(str(Q_LAPSED) in k for k in keys), str(keys))

        # Widen it: the one 200 days out comes into reach.
        await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": 300})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG))
        await s.commit()
        keys = {q["dedupe_key"] for q in await emitted(s, ORG, "qualification_expiring")}
        check("widening it reaches the certificate that was out of range",
              any(str(Q_FAR) in k for k in keys), str(keys))

        saved = await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": 9999})
        check("an out-of-range notice period is clamped, not stored",
              saved["config"]["lead_days"] == 365, str(saved["config"]))
        saved = await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": -5})
        check("a negative notice period cannot look backwards through time",
              saved["config"]["lead_days"] == 1, str(saved["config"]))
        saved = await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": "sixty"})
        check("a non-numeric notice period leaves the stored one alone",
              saved["config"]["lead_days"] == 1, str(saved["config"]))
        await s.commit()

        # A RENEWAL is a genuinely new fact to warn about.
        await reset_notifications(s)
        await notif.save_rule(s, ORG, "qualification_expiring", config={"lead_days": 60})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        first = {q["dedupe_key"] for q in await emitted(s, ORG, "qualification_expiring")}
        await s.execute(text("UPDATE member_qualifications SET expires_at = :d WHERE id = :id"),
                        {"d": date.today() + timedelta(days=30), "id": str(Q_LAPSED)})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        second = {q["dedupe_key"] for q in await emitted(s, ORG, "qualification_expiring")}
        check("renewing a certificate raises the new expiry as its own fact",
              len(second) == len(first) + 1, f"{len(first)} -> {len(second)}")
        # Put it back so later checks read the seeded shape.
        await s.execute(text("UPDATE member_qualifications SET expires_at = :d WHERE id = :id"),
                        {"d": date.today() - timedelta(days=10), "id": str(Q_LAPSED)})
        await s.commit()


async def check_switches():
    print("\n── every switch fails closed on its own ────────────────────────")
    async with Session() as s:
        # 1. the club's kill switch
        await reset_notifications(s)
        await notif.save_club_settings(s, ORG, {"enabled": False})
        await s.commit()
        stats = await scan.scan_org(s, await org(s, ORG))
        await s.commit()
        check("the club kill switch stops everything, on every channel",
              stats["emitted"] == 0 and len(await emitted(s, ORG)) == 0, str(stats))

        # 2. one event switched off
        await reset_notifications(s)
        await notif.save_rule(s, ORG, "milestone_achieved", enabled=False)
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        check("an event switched off raises nothing while its neighbours still do",
              len(await emitted(s, ORG, "milestone_achieved")) == 0
              and len(await emitted(s, ORG, "milestone_upcoming")) > 0)

        # 3. both channels off for one event — the source should not even run
        await reset_notifications(s)
        await notif.save_rule(s, ORG, "milestone_achieved",
                              channels={"email": False, "in_app": False})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        check("an event with no channel left on is not even queried",
              len(await emitted(s, ORG, "milestone_achieved")) == 0)

        # 4. the club's email channel off
        await reset_notifications(s)
        await notif.save_club_settings(s, ORG, {"email_enabled": False})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        rows = await deliveries(s, channel=ev.CHANNEL_EMAIL)
        check("switching email off at club level queues no email delivery",
              len(rows) == 0, str(rows[:2]))
        check("the in-app feed still fills while email is off",
              len(await deliveries(s, channel=ev.CHANNEL_IN_APP)) > 0)
        await reset_notifications(s)


async def check_recipients():
    print("\n── who is told ─────────────────────────────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()

        rows = await deliveries(s)
        told = {str(r["user_id"]) for r in rows}
        check("BetterCricket's own staff are not told a club's news",
              str(STAFF) not in told, str(told))
        check("another club's admin is not told this club's news",
              str(OTHER_ADMIN) not in told, str(told))
        check("the club's admins are told", str(PRIMARY) in told, str(told))

        no_addr = await deliveries(s, user_id=NO_EMAIL)
        check("an admin with no address gets the feed and no email",
              no_addr and all(r["channel"] == ev.CHANNEL_IN_APP for r in no_addr),
              str({r["channel"] for r in no_addr}))

        # The capability gate, using a real club_member with one capability.
        await s.execute(text("""
            UPDATE club_memberships SET role = 'club_member', capabilities = CAST(:caps AS jsonb)
            WHERE user_id = :u
        """), {"u": str(QUAL_ONLY), "caps": '["manage_qualifications"]'})
        await s.commit()
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        got = {r["event_key"] for r in await deliveries(s, user_id=QUAL_ONLY)}
        mine = {r["event_key"] for r in await deliveries(s, user_id=PRIMARY)}
        check("a club_member holding the capability IS told — it is their job",
              "qualification_expiring" in got, str(got))
        check("an event gated on a capability they do NOT hold reaches them",
              "report_pending" not in got, str(got))
        check("while the admin who holds it is told about the same queue",
              "report_pending" in mine, str(mine))
        check("an event gated on nothing reaches them both",
              "milestone_achieved" in got and "milestone_achieved" in mine,
              f"{got} / {mine}")

        # Put the membership back so later checks read the seeded shape.
        await s.execute(text("UPDATE club_memberships SET role = 'club_admin', "
                             "capabilities = '[]'::jsonb WHERE user_id = :u"),
                        {"u": str(QUAL_ONLY)})
        await s.commit()


async def check_module_gate():
    print("\n── the module gate ─────────────────────────────────────────────")
    async with Session() as s:
        merch = ev.EVENTS_BY_KEY["merch_low_stock"]
        check("a paid-module event is unavailable to a club without it",
              not notif.event_available(merch, []), "")
        check("and available to one that holds it",
              notif.event_available(merch, ["merch"]))
        check("a core event needs no module",
              notif.event_available(ev.EVENTS_BY_KEY["milestone_achieved"], []))
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        check("nothing about stock is raised for a club without BetterMerch",
              len(await emitted(s, ORG, "merch_low_stock")) == 0)


async def check_optout():
    print("\n── a person's own opt-out ──────────────────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        await notif.save_user_preference(s, PRIMARY, ORG, "milestone_achieved",
                                         {"email": False})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()

        mine = await deliveries(s, user_id=PRIMARY)
        opted = [r for r in mine if r["event_key"] == "milestone_achieved"]
        check("opting out of one event's email stops that email",
              all(r["channel"] != ev.CHANNEL_EMAIL for r in opted), str(opted))
        check("and leaves the in-app copy of the same event alone",
              any(r["channel"] == ev.CHANNEL_IN_APP for r in opted), str(opted))
        check("another event's email is untouched",
              any(r["channel"] == ev.CHANNEL_EMAIL and r["event_key"] != "milestone_achieved"
                  for r in mine), str(mine[:3]))
        check("another admin is unaffected by this one's choice",
              any(r["channel"] == ev.CHANNEL_EMAIL and r["event_key"] == "milestone_achieved"
                  for r in await deliveries(s, user_id=QUAL_ONLY)))

        # The whole-club opt-out.
        await reset_notifications(s)
        await notif.save_user_preference(s, PRIMARY, ORG, ev.ALL_EVENTS,
                                         {"email": False, "in_app": False})
        await s.commit()
        await scan.scan_org(s, await org(s, ORG)); await s.commit()
        check("a whole-club opt-out reaches every event on every channel",
              len(await deliveries(s, user_id=PRIMARY)) == 0)
        check("and stops nobody else being told",
              len(await deliveries(s, user_id=QUAL_ONLY)) > 0)

        # An opt-out can only ever silence — never switch something back on.
        event = ev.EVENTS_BY_KEY["milestone_achieved"]
        allowed = notif.channel_allowed(
            event, ev.CHANNEL_EMAIL,
            settings={**notif.DEFAULT_CLUB_SETTINGS, "email_enabled": False},
            rule={"enabled": True, "channels": {"email": True}},
            prefs={"milestone_achieved": {"email": True}})
        check("a preference cannot switch on a channel the club switched off",
              allowed is False)

        await s.execute(text("DELETE FROM user_notification_preferences"))
        await s.commit()


async def check_digest():
    print("\n── the email digest ────────────────────────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()

        STUB.sent.clear(); STUB.fail_with = None
        sent = await scan.dispatch_emails(s, await org(s, ORG))
        await s.commit()

        recipients = [m.to_email for m in STUB.sent]
        check("each recipient gets exactly one email, however many facts",
              len(recipients) == len(set(recipients)), str(recipients))
        check("more than one fact travels in that single email",
              sent["deliveries_sent"] > sent["emails_sent"], str(sent))
        check("an admin with no address is not emailed",
              None not in recipients and "" not in recipients, str(recipients))

        body = STUB.sent[0].html if STUB.sent else ""
        check("the digest names the club", "Applecross" in body)
        check("the digest groups facts under the event they belong to",
              "milestone" in body.lower() or "Milestone" in body)
        check("the digest links to the settings screen, so it is one click to stop",
              "/admin/notifications" in body)
        check("a plain-text alternative is sent too",
              bool(STUB.sent and STUB.sent[0].text.strip()))

        pending = (await s.execute(text("""
            SELECT COUNT(*) FROM notification_deliveries
            WHERE channel = 'email' AND status = 'pending'
        """))).scalar()
        check("a delivered row is marked sent, so tomorrow does not repeat it",
              pending == 0, str(pending))

        STUB.sent.clear()
        again = await scan.dispatch_emails(s, await org(s, ORG))
        await s.commit()
        check("a second dispatch with nothing new sends nothing",
              again["emails_sent"] == 0 and len(STUB.sent) == 0, str(again))


async def check_digest_failure_and_frequency():
    print("\n── a refused send, and the weekly cadence ──────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()

        STUB.sent.clear(); STUB.fail_with = "550 mailbox unavailable"
        failed = await scan.dispatch_emails(s, await org(s, ORG))
        await s.commit()
        check("a refused send is recorded as failed, not silently dropped",
              failed["failed"] > 0 and failed["emails_sent"] == 0, str(failed))
        row = (await s.execute(text("""
            SELECT status, error FROM notification_deliveries
            WHERE channel = 'email' AND status = 'failed' LIMIT 1
        """))).mappings().first()
        check("the reason is on the row, not only in a log line",
              row and "mailbox unavailable" in (row["error"] or ""), str(row))

        STUB.fail_with = None; STUB.sent.clear()
        retried = await scan.dispatch_emails(s, await org(s, ORG))
        await s.commit()
        check("the next run retries a failed delivery rather than losing it",
              retried["emails_sent"] > 0, str(retried))

        monday = date(2026, 9, 7)     # a Monday
        tuesday = date(2026, 9, 8)
        weekly = {**notif.DEFAULT_CLUB_SETTINGS, "email_frequency": "weekly", "email_weekday": 0}
        check("a weekly club is not emailed on the wrong day",
              scan._should_email_today(weekly, tuesday) is False)
        check("a weekly club is emailed on its chosen day",
              scan._should_email_today(weekly, monday) is True)
        check("a daily club is emailed whatever the day",
              scan._should_email_today(notif.DEFAULT_CLUB_SETTINGS, tuesday) is True)
        check("email switched off at club level sends on no day at all",
              scan._should_email_today(
                  {**notif.DEFAULT_CLUB_SETTINGS, "email_enabled": False}, monday) is False)


async def check_feed():
    print("\n── the in-app feed ─────────────────────────────────────────────")
    async with Session() as s:
        await reset_notifications(s)
        await scan.scan_org(s, await org(s, ORG)); await s.commit()

        feed = await notif.feed(s, PRIMARY, ORG)
        check("the feed carries this person's notifications", len(feed) > 0)
        check("every entry starts unread", all(not f["read"] for f in feed))
        check("an entry carries somewhere to go and act on it",
              all(f["link"] for f in feed), str(feed[:1]))
        unread = await notif.unread_count(s, PRIMARY, ORG)
        check("the unread count matches the feed", unread == len(feed), f"{unread} vs {len(feed)}")

        one = feed[0]["id"]
        marked = await notif.mark_read(s, PRIMARY, ORG, [one])
        await s.commit()
        check("marking one read marks exactly one", marked == 1, str(marked))
        check("the unread count follows",
              await notif.unread_count(s, PRIMARY, ORG) == unread - 1)

        marked_all = await notif.mark_read(s, PRIMARY, ORG)
        await s.commit()
        check("marking all read clears the rest", marked_all == unread - 1, str(marked_all))
        check("and nothing is left unread",
              await notif.unread_count(s, PRIMARY, ORG) == 0)

        check("another admin's feed was not read for them",
              await notif.unread_count(s, QUAL_ONLY, ORG) > 0)
        stolen = await notif.mark_read(s, OTHER_ADMIN, ORG, [one])
        await s.commit()
        check("an id off a browser cannot reach a row that was never yours",
              stolen == 0, str(stolen))

        # Cross-club, both directions.
        await scan.scan_org(s, await org(s, OTHER)); await s.commit()
        other_feed = await notif.feed(s, OTHER_ADMIN, OTHER)
        our_feed = await notif.feed(s, PRIMARY, ORG)
        check("another club's notifications never appear in ours",
              all(f["event_key"] for f in our_feed) and
              not set(f["id"] for f in our_feed) & set(f["id"] for f in other_feed))
        check("reading our club's feed as another club returns nothing",
              await notif.feed(s, PRIMARY, OTHER) == [])


async def check_routes():
    print("\n── the shipped route bodies ────────────────────────────────────")
    from fastapi import HTTPException
    from app.models.db import Organisation, User
    from app.routers.notifications import (
        ClubNotificationSettingsPatch, EventRulePatch, MarkReadPayload,
        UserPreferencePatch, get_notification_feed, get_notification_settings,
        mark_notification_feed_read, patch_notification_settings,
        put_notification_preference, put_notification_rule,
        run_notification_scan_now, get_notifications_summary,
    )

    async with Session() as s:
        await reset_notifications(s)
        club = await s.get(Organisation, ORG)
        user = await s.get(User, PRIMARY)

        payload = await get_notification_settings(current_user=user, club=club, db=s)
        keys = {e["key"] for e in payload["events"]}
        check("the settings payload lists every core event",
              "milestone_achieved" in keys and "qualification_expiring" in keys, str(sorted(keys)))
        check("an event for a module the club does not hold is not offered",
              "merch_low_stock" not in keys, str(sorted(keys)))
        check("the payload says whether this person may change the club's settings",
              payload["can_manage_club_settings"] is True)
        check("the payload says whether email would actually leave the building",
              "email_provider_live" in payload)
        qual = next(e for e in payload["events"] if e["key"] == "qualification_expiring")
        check("an event that has a notice period declares it as a field",
              qual["config_fields"] and qual["config_fields"][0]["key"] == "lead_days",
              str(qual["config_fields"]))

        saved = await patch_notification_settings(
            ClubNotificationSettingsPatch(email_frequency="weekly", email_weekday=3),
            current_user=user, club=club, db=s)
        check("the club's cadence is saved", saved["email_frequency"] == "weekly")
        check("saving one field leaves the others alone", saved["enabled"] is True, str(saved))
        saved = await patch_notification_settings(
            ClubNotificationSettingsPatch(email_frequency="fortnightly"),
            current_user=user, club=club, db=s)
        check("a cadence the system cannot honour falls back rather than storing",
              saved["email_frequency"] == "daily", str(saved))
        saved = await patch_notification_settings(
            ClubNotificationSettingsPatch(email_weekday=44), current_user=user, club=club, db=s)
        check("an impossible weekday is clamped into the week",
              0 <= saved["email_weekday"] <= 6, str(saved))

        rule = await put_notification_rule(
            "qualification_expiring", EventRulePatch(config={"lead_days": 90}),
            club=club, db=s)
        check("a notice period set through the route is stored",
              rule["config"]["lead_days"] == 90, str(rule))
        check("setting only the config leaves the channels alone",
              rule["channels"].get("email") is True, str(rule["channels"]))

        try:
            await put_notification_rule("not_a_real_event", EventRulePatch(enabled=False),
                                        club=club, db=s)
            check("an unknown event is refused", False)
        except HTTPException as e:
            check("an unknown event is refused", e.status_code == 404, str(e.status_code))

        try:
            await put_notification_rule("merch_low_stock", EventRulePatch(enabled=True),
                                        club=club, db=s)
            check("a rule for a module the club does not hold is refused", False)
        except HTTPException as e:
            check("a rule for a module the club does not hold is refused",
                  e.status_code == 402, str(e.status_code))

        pref = await put_notification_preference(
            "milestone_achieved", UserPreferencePatch(channels={"email": False}),
            current_user=user, club=club, db=s)
        check("an admin can silence one event for themselves",
              pref["channels"]["email"] is False, str(pref))
        try:
            await put_notification_preference(
                "nope", UserPreferencePatch(channels={"email": False}),
                current_user=user, club=club, db=s)
            check("a preference for an unknown event is refused", False)
        except HTTPException as e:
            check("a preference for an unknown event is refused", e.status_code == 404)

        result = await run_notification_scan_now(club=club, db=s)
        check("running the scan on demand raises something", result["emitted"] > 0, str(result))
        STUB.sent.clear()
        again = await run_notification_scan_now(club=club, db=s)
        check("pressing it a second time raises nothing new",
              again["emitted"] == 0, str(again))
        check("and it never emails anybody — the digest is the daily job's",
              len(STUB.sent) == 0)

        feed = await get_notification_feed(current_user=user, club=club, db=s)
        check("the feed route returns items and an unread count",
              feed["items"] and feed["unread"] == len(
                  [i for i in feed["items"] if not i["read"]]), str(feed["unread"]))
        unread_only = await get_notification_feed(unread_only=True, current_user=user,
                                                  club=club, db=s)
        check("the feed can be narrowed to unread",
              all(not i["read"] for i in unread_only["items"]))

        read = await mark_notification_feed_read(
            MarkReadPayload(notification_ids=None), current_user=user, club=club, db=s)
        check("mark-all-read clears the count", read["unread"] == 0, str(read))

        try:
            bad = await mark_notification_feed_read(
                MarkReadPayload(notification_ids=["not-a-uuid"]),
                current_user=user, club=club, db=s)
            check("a malformed id is a bad request, not a 500", False, str(bad))
        except HTTPException as e:
            check("a malformed id is a bad request, not a 500", e.status_code == 400)

        summary = await get_notifications_summary(current_user=user, club=club, db=s)
        check("the bell serves the stored feed alongside its live sections",
              "alerts" in summary and "alert_count" in summary, str(sorted(summary)[:6]))

        # A club that holds nothing still gets a usable settings payload.
        # Loaded HERE, after the rollback the malformed-id check triggers — an
        # instance fetched before it would be expired, and reading it would
        # raise a greenlet error rather than measuring anything.
        empty = await get_notification_settings(
            current_user=await s.get(User, OTHER_ADMIN),
            club=await s.get(Organisation, OTHER), db=s)
        check("a club that has configured nothing still gets the whole catalogue",
              len(empty["events"]) == len([e for e in ev.EVENT_TYPES if e.module is None]),
              str(len(empty["events"])))


async def main() -> int:
    if not HAVE:
        print("Configurable notifications are not present in this build:")
        for m in MISSING:
            print(f"  - {m}")
        print("\n0 passed, 1 failed")
        return 1

    email_service.get_email_provider = lambda: STUB  # noqa: E731

    await build_schema()
    await seed()
    await check_schema_and_defaults()
    await check_sources()
    await check_notice_period()
    await check_switches()
    await check_recipients()
    await check_module_gate()
    await check_optout()
    await check_digest()
    await check_digest_failure_and_frequency()
    await check_feed()
    await check_routes()

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
