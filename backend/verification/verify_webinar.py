"""Verification for the webinar registration page, against a real Postgres.

WHY THE PAGE EXISTS, since it is what every check below is really about: the
Meta ad set optimises for the `CompleteRegistration` pixel event, and a pixel
cannot fire on a third-party domain. An ad pointing straight at StreamYard
would hand Meta no conversion signal at all. So the registration happens on
betterat.cricket, the conversion fires on confirmed success, and the viewing
link is handed over afterwards.

The checks that matter most are the ones about WHEN a conversion is claimed:
never before the lead is persisted, and never for a resubmission from an
address already on the list. A `CompleteRegistration` we invent is worse for
the ad set than one we miss.

Runs the SHIPPED route bodies and service — never a re-implementation.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_webinar.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Behind a guard so a CONTROL RUN against a build without the feature REPORTS
# it rather than dying on the first ImportError and saying nothing about the
# rest of the suite.
MISSING: list[str] = []
try:
    from app.services import webinar
except ImportError as exc:  # pragma: no cover - control run only
    webinar = None
    MISSING.append(f"services.webinar ({exc})")

try:
    from app.services.webinar_ddl import DOWNGRADE as WEBINAR_DOWNGRADE
    from app.services.webinar_ddl import STATEMENTS as WEBINAR_DDL
except ImportError as exc:  # pragma: no cover - control run only
    WEBINAR_DDL, WEBINAR_DOWNGRADE = [], []
    MISSING.append(f"services.webinar_ddl ({exc})")

try:
    from app.routers.public_webinar import RegisterIn, WebinarMeta
    from app.routers.public_webinar import calendar_file, register, webinar_details
except ImportError as exc:  # pragma: no cover - control run only
    register = webinar_details = calendar_file = RegisterIn = WebinarMeta = None
    MISSING.append(f"public_webinar route bodies ({exc})")

try:
    from app.services import platform_settings as ps
except ImportError as exc:  # pragma: no cover - control run only
    ps = None
    MISSING.append(f"services.platform_settings ({exc})")

HAVE = not MISSING

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


class FakeRequest:
    """The two headers the route body reads, and nothing else."""

    def __init__(self, ip: str = "203.0.113.9", ua: str = "verify-agent/1.0"):
        self.headers = {"user-agent": ua, "referer": "https://facebook.com/"}
        self.client = type("C", (), {"host": ip})()


class Background:
    """Captures what the route backgrounded instead of running it — the point of
    several checks is WHICH tasks were queued (a CAPI conversion, a confirmation
    email) and with what arguments, not what they then did."""

    def __init__(self):
        self.tasks: list[tuple] = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((getattr(fn, "__name__", str(fn)), args, kwargs))

    def named(self, name: str) -> list[dict]:
        return [kw for fn, _a, kw in self.tasks if name in fn]


# The first-touch attribution blob lib/visitor.js getAttribution() produces off
# a real ad click, verbatim in shape.
AD_ATTRIBUTION = {
    "has_signal": True,
    "utm_source": "fb",
    "utm_medium": "paid_social",
    "utm_campaign": "BC_AU_Trials_CBO_Aug2026",
    "utm_content": "demo_4x5_v1",
    "utm_term": "committee",
    "click_id": "IwAR0abcdef123",
    "click_source": "facebook",
    "landing_path": "/demo?utm_source=fb&fbclid=IwAR0abcdef123",
    "landing_referrer": "https://l.facebook.com/",
    # A key nothing allowlists — must not reach the stored blob.
    "injected_junk": "x" * 50,
}

# A valid phone, for the checks that are about something else. Written the way
# a person writes one, spaces and all — the stored value is what they typed.
PHONE = "0412 345 678"


async def apply_ddl(conn) -> None:
    for stmt in WEBINAR_DDL:
        await conn.execute(text(stmt))


async def platform_settings_table(conn) -> None:
    """`platform_settings` is a lifespan/migration-120 table, invisible to
    `create_all` — copied here column for column rather than approximated, per
    the house rule about a harness table that merely looks right."""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            id INT PRIMARY KEY DEFAULT 1,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    await conn.execute(text(
        "INSERT INTO platform_settings (id, settings) VALUES (1, '{}'::jsonb) "
        "ON CONFLICT (id) DO NOTHING"
    ))


async def row_for(session, email: str) -> dict | None:
    got = (await session.execute(text(
        "SELECT * FROM webinar_registrations WHERE lower(email) = lower(:e)"
    ), {"e": email})).mappings().first()
    return dict(got) if got else None


async def count_rows(session) -> int:
    return (await session.execute(text("SELECT count(*) FROM webinar_registrations"))).scalar_one()


async def main() -> None:
    print("=== webinar registration ===")
    if MISSING:
        for item in MISSING:
            check(f"the feature is present: {item}", False, "not importable")
        print("\nFeature absent — reporting rather than running the rest.")
        print(f"\n{PASS} passed, {FAIL} failed")
        await engine.dispose()
        sys.exit(1)

    print("\n-- migration 296 --")
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS webinar_registrations"))
        await conn.execute(text("DROP TABLE IF EXISTS platform_settings"))
        await platform_settings_table(conn)
        # Applied THREE times: alembic runs it once, and the main.py lifespan
        # mirror re-runs the same list on every boot, so every statement has to
        # be idempotent or a second deploy fails.
        for _ in range(3):
            await apply_ddl(conn)
        check("the DDL applies three times over", True)

        # Again over a POPULATED table — the case a real deploy is.
        await conn.execute(text("""
            INSERT INTO webinar_registrations (event_key, name, email, club)
            VALUES ('webinar-2026-09-21', 'Pre-existing', 'prior@example.com', 'Old CC')
        """))
        await apply_ddl(conn)
        kept = (await conn.execute(text(
            "SELECT count(*) FROM webinar_registrations WHERE email = 'prior@example.com'"
        ))).scalar_one()
        check("re-applying it over a populated table keeps the rows", kept == 1, str(kept))
        await conn.execute(text("DELETE FROM webinar_registrations"))

        cols = {r[0] for r in (await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'webinar_registrations'"
        ))).all()}
        for col in ("phone", "utm_source", "utm_medium", "utm_campaign", "utm_content",
                    "utm_term", "click_id", "click_source", "attribution",
                    "referrer", "landing_path", "visitor_id", "email_sent", "email_error"):
            check(f"the table carries {col}", col in cols)

        print("\n-- migration 297: the phone reaches a database already at 296 --")
        # The case a real deploy is, and the one the CREATE TABLE alone cannot
        # cover: the table already exists WITHOUT the column, with rows in it.
        # Rebuilt in raw SQL in its pre-297 shape rather than by dropping the
        # column from the current one, so this is genuinely the older schema.
        await conn.execute(text("DROP TABLE IF EXISTS webinar_registrations"))
        await conn.execute(text("""
            CREATE TABLE webinar_registrations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                event_key TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
                club TEXT NOT NULL, role TEXT,
                utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
                utm_content TEXT, utm_term TEXT, click_id TEXT, click_source TEXT,
                attribution JSONB, referrer TEXT, landing_path TEXT,
                visitor_id TEXT, user_agent TEXT,
                email_sent BOOLEAN NOT NULL DEFAULT FALSE, email_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            INSERT INTO webinar_registrations (event_key, name, email, club)
            VALUES ('webinar-2026-09-21', 'Registered At 296', 'at296@example.com', 'Early CC')
        """))
        for _ in range(3):
            await apply_ddl(conn)
        pre297 = {r[0] for r in (await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'webinar_registrations'"
        ))).all()}
        check("applying it over a pre-297 table adds the phone", "phone" in pre297)
        kept = (await conn.execute(text(
            "SELECT count(*) FROM webinar_registrations WHERE email = 'at296@example.com'"
        ))).scalar_one()
        check("and keeps the registrations already taken", kept == 1, str(kept))
        # Nobody typed one, so the honest answer for that row is nothing at all
        # — never an invented blank that reads as a number we hold. Read only
        # if the column is there, or a CONTROL RUN dies here on an
        # UndefinedColumnError and says nothing about the rest of the suite.
        if "phone" in pre297:
            earlier = (await conn.execute(text(
                "SELECT phone FROM webinar_registrations WHERE email = 'at296@example.com'"
            ))).scalar_one()
            check("a registration taken before the field existed reads as no phone",
                  earlier is None, repr(earlier))
        else:
            check("a registration taken before the field existed reads as no phone",
                  False, "no phone column to read")
        await conn.execute(text("DELETE FROM webinar_registrations"))

    print("\n-- the lifespan mirror runs the same list --")
    # Read out of main.py's real source rather than retyped, so the two can't
    # drift without this failing.
    main_src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    check("main.py's lifespan imports the shared DDL",
          "from app.services.webinar_ddl import STATEMENTS" in main_src)
    # Renumbered 295 -> 296 on merging origin/main, which had reached 295
    # (committee_rediscover) — two migrations sharing a revision id break
    # Alembic outright, which is exactly what this pair of checks is for.
    migration = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
                 / "296_webinar_registrations.py").read_text()
    check("migration 296 imports the same shared list",
          "from app.services.webinar_ddl import" in migration)
    check("and revises 295 (a shared revision id breaks alembic outright)",
          'down_revision = "295"' in migration)
    # Read defensively — a control run against a build without the migration
    # must REPORT it rather than dying on a FileNotFoundError.
    phone_path = (Path(__file__).resolve().parent.parent / "alembic" / "versions"
                  / "297_webinar_phone.py")
    phone_migration = phone_path.read_text() if phone_path.exists() else ""
    check("migration 297 runs the same shared list rather than its own ALTER",
          "from app.services.webinar_ddl import STATEMENTS" in phone_migration)
    check("and revises 296", 'down_revision = "296"' in phone_migration)
    # 296 owns the table. Undoing the column must not take every registration
    # with it, which a `DROP TABLE` downgrade copied from 296 would.
    check("its downgrade drops the column, never the table",
          "DROP COLUMN IF EXISTS phone" in phone_migration
          and "DROP TABLE" not in phone_migration)

    print("\n-- the event is declared once, and both copies agree --")
    event = webinar.EVENT
    check("the event starts 21 Sep 2026 09:30 UTC",
          event.starts_at == datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc),
          str(event.starts_at))
    # 17:30 Perth (UTC+8, no daylight saving) and 19:30 AEST (UTC+10, DST not
    # yet started in September) are the SAME instant. The labels on the page and
    # in the email have to be that instant, or half the audience arrives an hour
    # out.
    perth = event.starts_at + timedelta(hours=8)
    aest = event.starts_at + timedelta(hours=10)
    check("that is 5:30pm in Perth", (perth.hour, perth.minute) == (17, 30), str(perth))
    check("and 7:30pm on the east coast", (aest.hour, aest.minute) == (19, 30), str(aest))
    check("the labels say exactly that",
          event.date_label == "Monday 21 September"
          and event.time_label == "5:30pm AWST / 7:30pm AEST",
          f"{event.date_label} / {event.time_label}")
    check("21 September 2026 really is a Monday",
          event.starts_at.astimezone(timezone(timedelta(hours=8))).strftime("%A") == "Monday")

    # The frontend keeps a hand-mirrored copy so the headline paints without a
    # request (this traffic is paid and mobile). Two copies is a drift risk, so
    # it is asserted rather than trusted — the same arrangement billing_pricing.py
    # and pricing.js have.
    fe = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
          / "data" / "webinar.js").read_text()
    check("the frontend mirror carries the same start instant",
          "'2026-09-21T09:30:00Z'" in fe)
    check("the frontend mirror carries the same date label", event.date_label in fe)
    check("the frontend mirror carries the same time label", event.time_label in fe)
    check("the frontend mirror carries the same event key", event.key in fe)
    check("and the same duration",
          f"durationMinutes: {event.duration_minutes}" in fe)
    # The StreamYard link is the one field deliberately NOT mirrored: shipping
    # it in the bundle put it in front of every visitor and made the form
    # bypassable. It comes off the server now.
    check("the watch url is NOT in the frontend bundle's constant",
          event.watch_url not in fe, "still there")

    print("\n-- the page title follows the event, not a literal --")
    # Both copies were frozen in the post-event wording for one release, so
    # every share of the page advertised a recording of a demo that had not
    # happened yet. The server-rendered card is what a crawler actually reads.
    pm = getattr(webinar, "page_meta", None)
    if pm is None:
        check("services.webinar exposes page_meta", False, "missing")
    else:
        pre_title, pre_desc = pm(False)
        post_title, post_desc = pm(True)
        check("before the event the title does not say 'watch'",
              "watch" not in pre_title.lower(), pre_title)
        check("and reads as a live session", "live demo" in pre_title.lower(), pre_title)
        check("after the event it does", "watch" in post_title.lower(), post_title)
        check("the two titles differ", pre_title != post_title)
        check("the two descriptions differ", pre_desc != post_desc)
        check("the post-event description offers the recording",
              "recording" in post_desc.lower(), post_desc)
        check("the pre-event description does not",
              "recording" not in pre_desc.lower(), pre_desc)
        # Kept inside the meta-description window the rest of MARKETING_PAGES
        # observes, so neither state's card is truncated in a share preview.
        for label, desc in (("pre-event", pre_desc), ("post-event", post_desc)):
            check(f"the {label} description is a sane meta length",
                  50 <= len(desc) <= 200, str(len(desc)))
        # The mirror has to agree, or the tab and the share card disagree.
        check("the frontend mirror carries the same pre-event title", pre_title in fe)
        check("the frontend mirror carries the same post-event title", post_title in fe)
        check("called with no argument it reads the event's own clock",
              pm() == (pm(True) if event.is_past() else pm(False)))

    print("\n-- and the share card is built from it --")
    try:
        from app.routers import og_preview as ogp
        card = ogp._marketing_html("/demo", "https://betterat.cricket")
    except Exception as exc:  # pragma: no cover - reported, not raised
        card = ""
        check("the /demo share card renders", False, str(exc))
    if card:
        # An empty `want_*` would make the two `in card` checks below pass
        # against anything, so with page_meta absent they are REPORTED as
        # missing rather than silently going green — the control run is what
        # caught that.
        want_title, want_desc = pm(event.is_past()) if pm else ("", "")
        check("the /demo card's og:title is the state's own title",
              bool(want_title)
              and f'og:title" content="{want_title.replace("&", "&amp;")}"' in card,
              "no page_meta to compare against" if not want_title else "not found")
        check("the /demo card's description matches too",
              bool(want_desc) and want_desc.replace("&", "&amp;") in card,
              "no page_meta to compare against" if not want_desc else "not found")
        check("the retired literal is gone from the card",
              "Watch the BetterCricket demo | Live demo + Q&amp;A" not in card)
        check("the /demo entry is no longer frozen in MARKETING_PAGES",
              "/demo" not in ogp.MARKETING_PAGES)
        # Every other page still reads its own frozen copy.
        trial = ogp._marketing_html("/trial", "https://betterat.cricket")
        check("another marketing page is untouched",
              ogp.MARKETING_PAGES["/trial"][0].replace("&", "&amp;") in trial)

    print("\n-- the before/after switch is the event's END, not its start --")
    check("an hour before, it is not past", not event.is_past(event.starts_at - timedelta(hours=1)))
    # Somebody arriving halfway through should still be sent to the live stream.
    check("halfway through, it is STILL not past",
          not event.is_past(event.starts_at + timedelta(minutes=30)))
    check("a minute after it ends, it is past",
          event.is_past(event.ends_at + timedelta(minutes=1)))

    print("\n-- the calendar file --")
    ics = webinar.build_ics()
    check("it is a VCALENDAR", ics.startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in ics)
    # RFC 5545 requires CRLF. A file joined with bare newlines is accepted by
    # some calendar apps and silently rejected by others, which is the worst of
    # both.
    # Every LF must be preceded by a CR — a bare LF anywhere is the rejected
    # case. Tested by removing the CRLF pairs and looking for what's left,
    # rather than by inspecting split() output, which cannot see them.
    check("there is no bare LF anywhere in the file",
          "\n" not in ics.replace("\r\n", ""), repr(ics.replace("\r\n", "")[:40]))
    check("and no stray CR either",
          "\r" not in ics.replace("\r\n", ""), repr(ics.replace("\r\n", "")[:40]))
    check("it carries the start as a UTC instant", "DTSTART:20260921T093000Z" in ics)
    check("and the end an hour later", "DTEND:20260921T103000Z" in ics)
    check("the watch link is in the location", f"LOCATION:{event.watch_url}" in ics)
    check("it has a stable UID", f"UID:{event.key}@betterat.cricket" in ics)
    # A comma or semicolon in a TEXT field must be escaped or the line is
    # misparsed as multiple values.
    check("the title's own punctuation is escaped where present",
          ("," not in event.title) or ("\\," in ics))
    gcal = webinar.google_calendar_url()
    check("the Google Calendar link carries the same window",
          "20260921T093000Z%2F20260921T103000Z" in gcal, gcal)

    print("\n-- one registration --")
    async with Session() as session:
        bg = Background()
        result = await register(
            RegisterIn(
                name="Sam Committee", email="Sam@Example.com", club="Applecross CC",
                phone="0412 345 678", role="Secretary", attribution=AD_ATTRIBUTION, visitorId="v-1",
                meta=WebinarMeta(eventId="evt-1", eventSourceUrl="https://betterat.cricket/demo",
                                 fbp="fb.1.1.1", fbc="fb.1.2.IwAR0abcdef123"),
            ),
            FakeRequest(), bg, session,
        )
        check("it reports ok", result["ok"] is True)
        # This is what the page reads to decide whether to fire the conversion.
        check("and reports the registration as NEW", result["created"] is True)
        check("the response hands over the live watch link",
              result["watch_url"] == event.watch_url, str(result.get("watch_url")))
        check("and the date labels the success state prints",
              result["date_label"] == event.date_label)
        check("and the role options the form offers", "Secretary" in result["roles"])

        row = await row_for(session, "sam@example.com")
        check("the lead is persisted", row is not None)
        check("the email is stored folded", row and row["email"] == "sam@example.com", str(row and row["email"]))
        check("with the name", row and row["name"] == "Sam Committee")
        check("with the club", row and row["club"] == "Applecross CC")
        check("with the role", row and row["role"] == "Secretary")
        # Stored EXACTLY as typed, spaces and all. Normalising here would only
        # make it harder to read back to whoever rings them; the digits-only
        # form is derived once, at the Meta boundary.
        check("with the phone as they wrote it", row and row.get("phone") == "0412 345 678",
              str(row and row.get("phone")))

        print("\n-- every UTM tag and the click id are persisted --")
        for col, expected in (("utm_source", "fb"), ("utm_medium", "paid_social"),
                              ("utm_campaign", "BC_AU_Trials_CBO_Aug2026"),
                              ("utm_content", "demo_4x5_v1"), ("utm_term", "committee"),
                              ("click_id", "IwAR0abcdef123"), ("click_source", "facebook")):
            check(f"{col} is stored", row and row[col] == expected, str(row and row[col]))
        check("the referrer is stored", row and row["referrer"] == "https://l.facebook.com/")
        check("the landing path is stored", row and "/demo?utm_source=fb" in (row["landing_path"] or ""))
        check("the visitor id is stored", row and row["visitor_id"] == "v-1")
        check("and a timestamp", row and row["created_at"] is not None)
        stored_attr = row["attribution"] if row else None
        if isinstance(stored_attr, str):
            stored_attr = json.loads(stored_attr)
        check("the whole first-touch blob is kept alongside",
              isinstance(stored_attr, dict) and stored_attr.get("utm_campaign") == "BC_AU_Trials_CBO_Aug2026")
        # The blob arrives from a browser, so it is key-allowlisted.
        check("but a key nothing allowlists never reaches the blob",
              isinstance(stored_attr, dict) and "injected_junk" not in stored_attr,
              str(sorted(stored_attr or {})))

        print("\n-- the conversion is claimed once, for a real registration --")
        capi = bg.named("send_complete_registration_event")
        check("a server-side CompleteRegistration is queued", len(capi) == 1, str(len(capi)))
        # Meta counts the browser and server copies as ONE event only if both
        # carry the same event_id — otherwise one registration reads as two.
        check("sharing the browser pixel's own event_id",
              capi and capi[0].get("event_id") == "evt-1", str(capi and capi[0].get("event_id")))
        check("with the fbp/fbc match-quality pair",
              capi and capi[0].get("fbp") == "fb.1.1.1" and capi[0].get("fbc", "").endswith("IwAR0abcdef123"))
        check("and the registrant's email for matching",
              capi and capi[0].get("email") == "sam@example.com")
        # A second hashed identifier for the same person: a conversion carrying
        # an email AND a phone matches back to whoever saw the ad more often
        # than one carrying an email alone.
        check("and the phone, which is what improves the match quality",
              capi and capi[0].get("phone") == "0412 345 678",
              str(capi and capi[0].get("phone")))
        mail = bg.named("_send_confirmation_bg")
        check("the confirmation email is queued", len(mail) == 1, str(len(mail)))
        check("addressed to the registrant", mail and mail[0].get("email") == "sam@example.com")
        # Before the event there is no recording, so the email must not try to
        # send one.
        check("and carrying no recording link before the event",
              mail and mail[0].get("recording_url") is None)

    print("\n-- a resubmission is the same lead, not a second conversion --")
    async with Session() as session:
        before = await count_rows(session)
        bg = Background()
        again = await register(
            RegisterIn(name="Sam Committee-Smith", email="SAM@example.com",
                       club="Applecross Cricket Club", phone="(08) 9364 1234",
                       attribution={},
                       meta=WebinarMeta(eventId="evt-2")),
            FakeRequest(), bg, session,
        )
        check("it still reports ok", again["ok"] is True)
        # This is what stops the ad set optimising toward people who fill the
        # form in twice.
        check("but NOT as a new registration", again["created"] is False)
        check("no second CompleteRegistration is queued",
              len(bg.named("send_complete_registration_event")) == 0)
        check("no duplicate row is added", await count_rows(session) == before,
              f"{before} -> {await count_rows(session)}")
        row = await row_for(session, "sam@example.com")
        check("the corrected name lands on the row it already had",
              row and row["name"] == "Sam Committee-Smith")
        check("and the corrected club", row and row["club"] == "Applecross Cricket Club")
        # Same treatment as the name and the club: a resubmission is somebody
        # correcting what they typed, so the new number wins.
        check("and the corrected phone", row and row.get("phone") == "(08) 9364 1234",
              str(row and row.get("phone")))
        # A registration already credited to a campaign keeps that credit — the
        # second visit arrived with nothing, and overwriting would credit the
        # registration to whichever visit happened to be last.
        check("the original campaign credit survives an untagged resubmission",
              row and row["utm_campaign"] == "BC_AU_Trials_CBO_Aug2026", str(row and row["utm_campaign"]))
        check("and the role it already had is not blanked",
              row and row["role"] == "Secretary", str(row and row["role"]))
        # They still get the link — from their side nothing has gone wrong.
        check("they are still handed the watch link", again["watch_url"] == event.watch_url)

    print("\n-- a phone-less write never blanks a number already stored --")
    # The route requires a phone, so this is the service's own guard: a caller
    # that is not the form (a browser served an older bundle mid-deploy, an
    # internal call) must not be able to erase a number we already hold.
    async with Session() as session:
        try:
            await webinar.register(session, name="Sam Committee-Smith",
                                   email="sam@example.com", club="Applecross Cricket Club",
                                   phone=None)
        except TypeError as exc:  # pragma: no cover - control run only
            await session.rollback()
            check("the stored number survives a submission carrying none", False, str(exc))
        else:
            row = await row_for(session, "sam@example.com")
            check("the stored number survives a submission carrying none",
                  row and row.get("phone") == "(08) 9364 1234", str(row and row.get("phone")))

    print("\n-- what counts as a phone number --")
    # DELIBERATELY WIDER than admin_identity.mobile_valid, which refuses
    # anything that is not an Australian mobile. The clubroom landline a
    # secretary writes down is a perfectly good number to ring them on, and
    # refusing it would send a real registrant away.
    accepted = [
        ("an Australian mobile", "0412 345 678"),
        ("a landline with an area code", "(08) 9364 1234"),
        ("a landline with no area code", "9364 1234"),
        ("an international number", "+64 21 555 0100"),
        ("one written with dashes", "0412-345-678"),
    ]
    async with Session() as session:
        for label, value in accepted:
            email = f"ok{abs(hash(value)) % 10**8}@example.com"
            try:
                await register(RegisterIn(name="Phone Test", email=email,
                                          club="Phone CC", phone=value),
                               FakeRequest(), Background(), session)
            except Exception as exc:  # noqa: BLE001
                check(f"{label} is accepted", False, str(exc))
                continue
            row = await row_for(session, email)
            check(f"{label} is accepted", row is not None)
            check(f"and {label} is stored exactly as written",
                  row and row.get("phone") == value, str(row and row.get("phone")))
        await session.execute(text("DELETE FROM webinar_registrations WHERE club = 'Phone CC'"))
        await session.commit()

    print("\n-- the phone is OPTIONAL: skipping it registers you anyway --")
    # It shipped required for one release. On cold paid traffic a mandatory
    # phone number is the highest-friction field on the form, and it reads as a
    # promise to ring — which contradicts the "no sales call" line on /trial.
    async with Session() as session:
        for label, value in (("left blank", ""), ("typed as spaces", "   ")):
            email = f"nophone{len(label)}@example.com"
            bg = Background()
            try:
                res = await register(RegisterIn(name="No Phone Nora", email=email,
                                                club="Skip CC", phone=value),
                                     FakeRequest(), bg, session)
            except Exception as exc:  # noqa: BLE001
                check(f"a phone {label} still registers", False, str(exc))
                continue
            check(f"a phone {label} still registers", res.get("created") is True, str(res))
            row = await row_for(session, email)
            check(f"and {label} it is stored as nothing, not a blank string",
                  row is not None and not (row.get("phone") or ""),
                  repr(row and row.get("phone")))
            check(f"and {label} they are still handed the watch link",
                  bool(res.get("watch_url")), str(res.get("watch_url")))
            # The conversion still goes — just without the second identifier.
            capi = bg.named("send_complete_registration_event")
            check(f"and {label} the conversion is still queued", len(capi) == 1, str(len(capi)))
            check(f"and {label} it carries no phone to hash",
                  capi and not (capi[0].get("phone") or ""),
                  str(capi and capi[0].get("phone")))
        await session.execute(text("DELETE FROM webinar_registrations WHERE club = 'Skip CC'"))
        await session.commit()

    print("\n-- an untagged registration can be upgraded once a signal arrives --")
    async with Session() as session:
        bg = Background()
        await register(RegisterIn(name="Organic Olive", email="olive@example.com",
                                  club="Direct CC", phone="0400 000 000",
                                  attribution={"has_signal": False}),
                       FakeRequest(), bg, session)
        row = await row_for(session, "olive@example.com")
        check("it stores with no campaign", row and row["utm_campaign"] is None)
        await register(RegisterIn(name="Organic Olive", email="olive@example.com",
                                  club="Direct CC", phone="0400 000 000",
                                  attribution=AD_ATTRIBUTION),
                       FakeRequest(), Background(), session)
        row = await row_for(session, "olive@example.com")
        check("and a later tagged visit fills the gap",
              row and row["utm_campaign"] == "BC_AU_Trials_CBO_Aug2026", str(row and row["utm_campaign"]))

    print("\n-- every refusal --")
    async with Session() as session:
        for label, payload in (
            ("a blank name", RegisterIn(name="  ", email="a@b.com", club="X CC", phone=PHONE)),
            ("a blank club", RegisterIn(name="A", email="a@b.com", club="  ", phone=PHONE)),
            ("a blank email", RegisterIn(name="A", email="", club="X CC", phone=PHONE)),
            ("an email with no @", RegisterIn(name="A", email="notanemail", club="X CC", phone=PHONE)),
            ("an email with no domain dot", RegisterIn(name="A", email="a@b", club="X CC", phone=PHONE)),
            # A BLANK phone is deliberately absent from this list — it is
            # accepted, and is checked below. A number that IS typed still has
            # to look like one.
            ("a phone with too few digits", RegisterIn(name="A", email="a@b.com", club="X CC", phone="1234")),
            ("a phone that is not a number at all", RegisterIn(name="A", email="a@b.com", club="X CC", phone="ring me")),
            ("a phone with more digits than E.164 allows", RegisterIn(name="A", email="a@b.com", club="X CC", phone="0412345678901234")),
        ):
            before = await count_rows(session)
            try:
                await register(payload, FakeRequest(), Background(), session)
                check(f"{label} is refused", False, "accepted")
            except Exception as exc:
                check(f"{label} is refused", getattr(exc, "status_code", None) == 422, str(exc))
            check(f"{label} stores nobody", await count_rows(session) == before)

    print("\n-- the bot guards --")
    async with Session() as session:
        before = await count_rows(session)
        bg = Background()
        # Answered as though it worked: telling a bot otherwise only teaches
        # whoever wrote it to leave the field alone.
        honey = await register(
            RegisterIn(name="Bot", email="bot@example.com", club="Bot CC", website="http://spam"),
            FakeRequest(), bg, session,
        )
        check("a filled honeypot reads as success", honey["ok"] is True)
        check("but stores nobody", await count_rows(session) == before)
        check("and claims no conversion", honey["created"] is False)
        check("and queues no email", len(bg.named("_send_confirmation_bg")) == 0)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        try:
            await register(RegisterIn(name="Fast", email="fast@example.com", club="Fast CC",
                                      formStartedAt=now_ms),
                           FakeRequest(), Background(), session)
            check("a form filled in under 3 seconds is refused", False, "accepted")
        except Exception as exc:
            check("a form filled in under 3 seconds is refused",
                  getattr(exc, "status_code", None) == 422, str(exc))

        # Clock skew on the visitor's device produces a negative delta. That is
        # a person with a wrong clock, not a bot — refusing them would be the
        # guard costing a real registration.
        skew = await register(
            RegisterIn(name="Skewed Clock", email="skew@example.com", club="Skew CC", phone=PHONE,
                       formStartedAt=now_ms + 600_000),
            FakeRequest(), Background(), session,
        )
        check("a device with a clock running fast is NOT refused", skew["created"] is True)

        old = await register(
            RegisterIn(name="Real Person", email="real@example.com", club="Real CC", phone=PHONE,
                       formStartedAt=now_ms - 30_000),
            FakeRequest(), Background(), session,
        )
        check("a form filled in at human speed is accepted", old["created"] is True)

    print("\n-- after the event --")
    async with Session() as session:
        # The route reads is_past() live, so the switch is exercised by moving
        # the module's own constant rather than by faking a clock.
        real_event = webinar.EVENT
        try:
            past = webinar.WebinarEvent(
                key=real_event.key, title=real_event.title,
                starts_at=datetime.now(timezone.utc) - timedelta(days=2),
                duration_minutes=60, watch_url=real_event.watch_url,
                date_label=real_event.date_label, time_label=real_event.time_label,
            )
            webinar.EVENT = past
            import app.routers.public_webinar as pw
            pw.webinar.EVENT = past

            details = await webinar_details(session)
            check("the event reports itself as past", details["is_past"] is True)
            # Never the dead live link, and never a recording that doesn't exist.
            check("with no watch link while no recording is published",
                  details["watch_url"] is None, str(details["watch_url"]))
            check("and says the recording is unavailable",
                  details["recording_available"] is False)

            bg = Background()
            late = await register(
                RegisterIn(name="Late Larry", email="late@example.com", club="Late CC", phone=PHONE),
                FakeRequest(), bg, session,
            )
            check("somebody registering afterwards is still stored", late["created"] is True)
            check("and is offered no link yet", late["watch_url"] is None)

            await ps.update_settings(session, {"webinar_recording_url": "https://youtu.be/rec123"})
            check("a super admin's recording url is stored",
                  await ps.get_webinar_recording_url(session) == "https://youtu.be/rec123")
            details = await webinar_details(session)
            check("and the page starts serving it with no deploy",
                  details["watch_url"] == "https://youtu.be/rec123", str(details["watch_url"]))
            check("reporting the recording as available", details["recording_available"] is True)

            bg = Background()
            later = await register(
                RegisterIn(name="Later Lucy", email="later@example.com", club="Later CC", phone=PHONE),
                FakeRequest(), bg, session,
            )
            check("a registration now hands over the recording",
                  later["watch_url"] == "https://youtu.be/rec123")
            mail = bg.named("_send_confirmation_bg")
            check("and the email carries the recording rather than the live link",
                  mail and mail[0].get("recording_url") == "https://youtu.be/rec123",
                  str(mail and mail[0].get("recording_url")))
            # The pixel event is deliberately unchanged after the event, so the
            # conversion history stays continuous.
            check("the conversion is still claimed for a post-event signup",
                  len(bg.named("send_complete_registration_event")) == 1)

            ics_response = await calendar_file(session)
            body = ics_response.body.decode()
            check("the calendar file now points at the recording",
                  "https://youtu.be/rec123" in body)

            # Clearing it must mean "unset", not a stored empty string that
            # reads as a link which exists and is blank.
            await ps.update_settings(session, {"webinar_recording_url": "  "})
            check("clearing it unsets it rather than storing an empty string",
                  await ps.get_webinar_recording_url(session) is None)
            blob = (await session.execute(text(
                "SELECT settings FROM platform_settings WHERE id = 1"))).scalar_one()
            if isinstance(blob, str):
                blob = json.loads(blob)
            check("the key is gone from the blob entirely",
                  "webinar_recording_url" not in blob, str(sorted(blob)))

            try:
                await ps.update_settings(session, {"webinar_recording_url": "youtube.com/rec"})
                check("a url with no scheme is refused", False, "accepted")
            except ValueError as exc:
                check("a url with no scheme is refused", True, str(exc))
            check("and the refusal leaves it unset",
                  await ps.get_webinar_recording_url(session) is None)
        finally:
            webinar.EVENT = real_event
            import app.routers.public_webinar as pw
            pw.webinar.EVENT = real_event

    print("\n-- before the event, the details endpoint --")
    async with Session() as session:
        details = await webinar_details(session)
        check("reports the event as upcoming", details["is_past"] is False)
        check("and hands over the live link", details["watch_url"] == event.watch_url)
        ics_response = await calendar_file(session)
        check("the calendar endpoint serves a calendar",
              ics_response.media_type.startswith("text/calendar"), str(ics_response.media_type))
        check("as a download", "attachment" in ics_response.headers.get("content-disposition", ""))
        check("with the live link in it", event.watch_url in ics_response.body.decode())

    print("\n-- the confirmation email records its own outcome --")
    async with Session() as session:
        row = await row_for(session, "sam@example.com")
        check("a fresh row starts un-sent", row and row["email_sent"] is False)
        await webinar.mark_email_sent(session, row["id"], error=None)
        row = await row_for(session, "sam@example.com")
        check("acceptance is recorded on the row", row and row["email_sent"] is True)
        check("with no error", row and row["email_error"] is None)
        # A refusal recorded with its reason is what makes "they say they never
        # got it" answerable months later.
        await webinar.mark_email_sent(session, row["id"], error="provider said no")
        row = await row_for(session, "sam@example.com")
        check("a refusal is recorded with its reason",
              row and row["email_sent"] is False and row["email_error"] == "provider said no")

        # The whole send path, with the provider refusing — the page has
        # already handed over the link, so this must never raise.
        class Refusing:
            async def send(self, _msg):
                return type("R", (), {"ok": False, "message_id": None, "error": "smtp down"})()

        original = webinar.email_service.get_email_provider
        try:
            webinar.email_service.get_email_provider = lambda: Refusing()
            await webinar.send_confirmation(
                session, registration_id=row["id"], name="Sam", email="sam@example.com")
            check("a provider refusal does not raise", True)
            row = await row_for(session, "sam@example.com")
            check("and lands on the row with its reason",
                  row and row["email_sent"] is False and "smtp down" in (row["email_error"] or ""))

            class Throwing:
                async def send(self, _msg):
                    raise RuntimeError("connection reset")

            webinar.email_service.get_email_provider = lambda: Throwing()
            await webinar.send_confirmation(
                session, registration_id=row["id"], name="Sam", email="sam@example.com")
            check("a provider that throws does not raise either", True)
            row = await row_for(session, "sam@example.com")
            check("and is recorded too",
                  row and "connection reset" in (row["email_error"] or ""))

            captured: list = []

            class Accepting:
                async def send(self, msg):
                    captured.append(msg)
                    return type("R", (), {"ok": True, "message_id": "m-1", "error": None})()

            webinar.email_service.get_email_provider = lambda: Accepting()
            await webinar.send_confirmation(
                session, registration_id=row["id"], name="Sam Committee",
                email="sam@example.com")
            row = await row_for(session, "sam@example.com")
            check("acceptance clears the error", row and row["email_sent"] is True
                  and row["email_error"] is None)
            msg = captured[-1] if captured else None
            check("the email carries both timezones",
                  msg and "5:30pm AWST" in msg.html and "7:30pm AEST" in msg.html)
            check("and the date", msg and event.date_label in msg.html)
            check("and the watch link", msg and event.watch_url in msg.html)
            check("and a calendar link", msg and "calendar.google.com" in msg.html)
            check("and the .ics url", msg and "/public/webinar/calendar.ics" in msg.html)
            check("and one line pointing at the free trial",
                  msg and "/trial" in msg.html)
            # A text part matters for deliverability and for a client that
            # refuses HTML.
            check("the plain-text part carries the link too",
                  msg and event.watch_url in msg.text)
            check("and both timezones", msg and "AWST" in msg.text and "AEST" in msg.text)
        finally:
            webinar.email_service.get_email_provider = original

    print("\n-- the staff list --")
    async with Session() as session:
        from app.routers.club_admin import list_webinar_registrations
        rows = await list_webinar_registrations(None, session)
        check("it lists the registrations", len(rows) >= 4, str(len(rows)))
        check("newest first",
              all((rows[i]["created_at"] or "") >= (rows[i + 1]["created_at"] or "")
                  for i in range(len(rows) - 1)))
        sam = next((r for r in rows if r["email"] == "sam@example.com"), None)
        check("carrying the campaign each came from",
              sam and sam["utm_campaign"] == "BC_AU_Trials_CBO_Aug2026")
        check("and whether the confirmation email got out", sam and "email_sent" in sam)
        check("and the id as a string, not a raw UUID",
              sam and isinstance(sam["id"], str))
        # The whole reason the number is gathered: a lead somebody rings.
        # Without it on the staff list it may as well not be stored.
        check("and the phone, which is what the list is worked from",
              sam and sam.get("phone") == "(08) 9364 1234", str(sam and sam.get("phone")))

    print("\n-- the downgrade --")
    async with engine.begin() as conn:
        for stmt in WEBINAR_DOWNGRADE:
            await conn.execute(text(stmt))
        gone = (await conn.execute(text(
            "SELECT to_regclass('webinar_registrations') IS NULL"))).scalar_one()
        check("it removes the table", gone is True)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
