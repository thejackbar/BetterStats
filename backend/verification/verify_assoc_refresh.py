"""The crawl re-reads an existing club's associations.

Asked for as part of "start crawling should re-discover both new and existing
clubs and pick up changes in address, associations, officers". Two thirds of
that were already true and are asserted here rather than assumed:
``_upsert_club`` rewrites the club's name, website and whole address on every
pass, and newly listed officers are added.

The association was the real gap. The enrichment frontier was
``associations IS NULL`` and nothing else, so a club's associations were fetched
exactly once and then frozen for the life of the row — a club that moved
association kept the old one for ever and no crawl would ever correct it.
``associations_fetched_at`` (migration 298) is what makes "fetched, but a while
ago" expressible; ``last_crawled_at`` cannot, because the discovery pass bumps
it for every club it sees, so it records when the club was last SEEN rather than
when its associations were last READ.

What is checked here, through the SHIPPED service:

  · migration 298 applied three times to a populated pre-298 table, and the
    lifespan mirror landing on the same schema
  · the backfill stamping only clubs that already have associations, so the
    whole directory does not become refresh-due in one burst
  · a club whose associations are stale comes back onto the frontier
  · a club whose associations are recent does NOT
  · a never-fetched club is served FIRST, so refreshes cannot starve the backfill
  · a refresh that comes back empty clears the denormalised association name,
    rather than leaving one the club no longer plays in on screen
  · a failed fetch does not stamp the clock, so the club is retried
  · frontier_remaining still means never-fetched only — run_continuous reads it
    as "is the backfill finished" and would hot-loop for ever if refreshes
    were folded in
  · 0 days switches refreshing off and restores the pre-298 behaviour
  · the address and the committee really are refreshed on an ordinary pass

Run:  DATABASE_URL=... python -m verification.verify_assoc_refresh
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DB = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/betterstats_verify?host=/var/run/pgsock&port=5439",
)

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"  {extra}" if extra else ""))


def report(name, why):
    """A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN."""
    global FAIL
    FAIL += 1
    print(f"FAIL {name}  {why}")


# ── the shipped code, loaded so a control run reports rather than dying ────────
try:
    from app.services import club_directory as cd
except Exception as e:  # noqa: BLE001
    cd = None
    print(f"NOTE  app.services.club_directory did not import: {e}")

try:
    from app.services.assoc_refresh_ddl import STATEMENTS as ASSOC_DDL
except Exception as e:  # noqa: BLE001
    ASSOC_DDL = None
    print(f"NOTE  app.services.assoc_refresh_ddl did not import: {e}")

try:
    from app.config.settings import settings
except Exception as e:  # noqa: BLE001
    settings = None
    print(f"NOTE  app.config.settings did not import: {e}")


CRAWL_CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS marketing_crawl_control (
    id INTEGER PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT marketing_crawl_control_singleton CHECK (id = 1)
)
"""


class FakeAssoc:
    """Stands in for the main-graph association lookup, per routingCode."""

    def __init__(self, answers):
        self.answers = answers   # {routingCode: [ {...} ] | None}
        self.asked = []

    async def __call__(self, routing_code, **_kw):
        self.asked.append(routing_code)
        return self.answers.get(routing_code)


async def none_contact(*_a, **_kw):
    return None


async def seed(session, guid, *, name, assocs, fetched_at, assoc_name=None):
    """A directory row in a known state, written in RAW SQL.

    Deliberately not through the ORM: a pre-298 row is one whose
    associations_fetched_at was never set by anything, and inserting through a
    model that already carries the column could not produce that."""
    await session.execute(text(
        "INSERT INTO marketing_clubs "
        "  (id, grassroots_guid, playhq_id, name, kind, source, associations, "
        "   association_name, associations_fetched_at, first_seen_at, last_crawled_at) "
        "VALUES (gen_random_uuid(), :g, :g, :n, 'club', 'seed', "
        "        CAST(:a AS JSONB), :an, :f, NOW() - INTERVAL '400 days', "
        "        NOW() - INTERVAL '400 days') "
        "ON CONFLICT (grassroots_guid) DO UPDATE SET "
        "  associations = EXCLUDED.associations, name = EXCLUDED.name, "
        "  association_name = EXCLUDED.association_name, "
        "  associations_fetched_at = EXCLUDED.associations_fetched_at"),
        {"g": guid, "n": name, "a": assocs, "an": assoc_name, "f": fetched_at})
    await session.commit()


async def main():
    engine = create_async_engine(DB, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    if cd is None or ASSOC_DDL is None or settings is None:
        report("the association refresh is present", "feature absent — reporting rather than crashing")
        await engine.dispose()
        print(f"\n{PASS} passed, {FAIL} failed")
        return 1

    from app.models.db import (
        Base, MarketingClub, MarketingClubContact, Organisation, User)

    # ── 1. MIGRATION 298 OVER A POPULATED PRE-298 TABLE ───────────────────────
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS marketing_club_contacts CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS marketing_clubs CASCADE"))
        await conn.execute(text(CRAWL_CONTROL_DDL))
        await conn.execute(text(
            "INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"))
        await conn.run_sync(Base.metadata.create_all, tables=[
            User.__table__, Organisation.__table__, MarketingClub.__table__,
            MarketingClubContact.__table__])
        # …then take the column away again, so what follows is genuinely a
        # pre-298 table with rows already in it.
        await conn.execute(text(
            "ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS associations_fetched_at"))
        await conn.execute(text(
            "INSERT INTO marketing_clubs "
            "  (id, grassroots_guid, name, kind, source, associations, last_crawled_at) "
            "VALUES (gen_random_uuid(), 'pre-a', 'Pre A', 'club', 'seed', "
            "        '[{\"id\":\"x\",\"name\":\"Old Assoc\"}]'::jsonb, "
            "        NOW() - INTERVAL '200 days'), "
            "       (gen_random_uuid(), 'pre-b', 'Pre B', 'club', 'seed', NULL, "
            "        NOW() - INTERVAL '10 days')"))

    for run in (1, 2, 3):
        async with engine.begin() as conn:
            for stmt in ASSOC_DDL:
                await conn.execute(text(stmt))
        async with Session() as s:
            stamped = await s.scalar(text(
                "SELECT associations_fetched_at FROM marketing_clubs "
                "WHERE grassroots_guid = 'pre-a'"))
            unstamped = await s.scalar(text(
                "SELECT associations_fetched_at FROM marketing_clubs "
                "WHERE grassroots_guid = 'pre-b'"))
        if run == 1:
            ck("migration 298 stamps a club that ALREADY has associations, so the "
               "whole directory does not become refresh-due in one burst",
               stamped is not None, str(stamped))
            ck("and leaves a never-fetched club NULL — it is still on the ordinary "
               "backfill frontier, which run_continuous reads as 'not finished'",
               unstamped is None, str(unstamped))
            ck("the stamp is the club's own last_crawled_at, so the "
               "longest-unseen clubs come due for a refresh first",
               abs((datetime.now(timezone.utc) - stamped).days - 200) <= 1,
               str(stamped))
            first_stamp = stamped
        else:
            ck(f"applying it again (run {run}) writes nothing — the backfill is "
               "guarded on the stamp still being NULL",
               stamped == first_stamp, f"{first_stamp} -> {stamped}")

    # ── 2. THE FRONTIER: NEVER-FETCHED, PLUS STALE ────────────────────────────
    now = datetime.now(timezone.utc)
    async with Session() as s:
        await s.execute(text("DELETE FROM marketing_clubs"))
        await s.commit()
        await seed(s, "never", name="Never Fetched CC", assocs=None,
                   fetched_at=None)
        await seed(s, "stale", name="Stale CC",
                   assocs='[{"id":"a1","name":"Old Assoc"}]',
                   assoc_name="Old Assoc", fetched_at=now - timedelta(days=200))
        await seed(s, "fresh", name="Fresh CC",
                   assocs='[{"id":"a2","name":"Current Assoc"}]',
                   assoc_name="Current Assoc", fetched_at=now - timedelta(days=3))

    fake = FakeAssoc({"never": [{"id": "n1", "name": "New Assoc"}],
                      "stale": [{"id": "a9", "name": "Moved Assoc"}],
                      "fresh": [{"id": "a2", "name": "Current Assoc"}]})
    real_assoc, real_contact = cd.phq.discover_associations, cd.phq.discover_org_contact
    cd.phq.discover_associations, cd.phq.discover_org_contact = fake, none_contact
    try:
        async with Session() as s:
            stats = await cd.enrich_associations(s, limit=10)

        ck("A STALE CLUB COMES BACK ONTO THE FRONTIER — the gap this closes: its "
           "associations used to be read once and frozen for ever",
           "stale" in fake.asked, str(fake.asked))
        ck("a never-fetched club is still enriched", "never" in fake.asked,
           str(fake.asked))
        ck("A RECENTLY-READ CLUB IS LEFT ALONE — re-asking a question whose answer "
           "has not changed would spend the crawl's whole daily budget",
           "fresh" not in fake.asked, str(fake.asked))
        ck("THE BACKFILL IS SERVED FIRST — a club nobody has ever enriched is "
           "worth more than a refresh, so refreshes cannot starve it",
           fake.asked and fake.asked[0] == "never", str(fake.asked))

        async with Session() as s:
            moved = await s.scalar(text(
                "SELECT association_name FROM marketing_clubs WHERE grassroots_guid='stale'"))
            stamp = await s.scalar(text(
                "SELECT associations_fetched_at FROM marketing_clubs "
                "WHERE grassroots_guid='stale'"))
        ck("the refreshed club's association is actually updated",
           moved == "Moved Assoc", str(moved))
        ck("and its clock is restamped, so it is not re-read on the next pass",
           stamp is not None and (datetime.now(timezone.utc) - stamp).days == 0,
           str(stamp))

        # frontier_remaining is what run_continuous reads to decide the backfill
        # is done. Folding refreshes into it would mean the runner never
        # considered itself finished and hot-looped for ever.
        ck("FRONTIER_REMAINING STILL MEANS NEVER-FETCHED ONLY — run_continuous "
           "reads it as 'is the backfill finished'",
           stats.get("frontier_remaining") == 0, str(stats.get("frontier_remaining")))
        ck("and refreshes are reported separately instead",
           "refresh_due" in stats, str(stats))

        # ── 3. A REFRESH THAT COMES BACK EMPTY ────────────────────────────────
        # Only reachable now that a club with associations is re-read at all: the
        # club has left every association it used to play in.
        async with Session() as s:
            await seed(s, "left", name="Left CC",
                       assocs='[{"id":"a3","name":"Departed Assoc"}]',
                       assoc_name="Departed Assoc",
                       fetched_at=now - timedelta(days=200))
        fake.answers["left"] = []
        async with Session() as s:
            await cd.enrich_associations(s, limit=10)
        async with Session() as s:
            row = (await s.execute(text(
                "SELECT associations, association_name, associations_fetched_at "
                "FROM marketing_clubs WHERE grassroots_guid='left'"))).first()
        ck("A REFRESH THAT COMES BACK EMPTY CLEARS THE DENORMALISED NAME — "
           "leaving it would show an association the club no longer plays in",
           row is not None and row[0] == [] and row[1] is None,
           str(row[:2] if row else None))
        ck("and it still counts as a real answer, so the club is not re-read "
           "immediately", row is not None and row[2] is not None)

        # ── 4. A FAILED FETCH DOES NOT STAMP THE CLOCK ────────────────────────
        async with Session() as s:
            await seed(s, "flaky", name="Flaky CC",
                       assocs='[{"id":"a4","name":"Some Assoc"}]',
                       assoc_name="Some Assoc", fetched_at=now - timedelta(days=200))
        fake.answers["flaky"] = None      # the client's "could not reach PlayHQ"
        async with Session() as s:
            await cd.enrich_associations(s, limit=10)
        async with Session() as s:
            stamp = await s.scalar(text(
                "SELECT associations_fetched_at FROM marketing_clubs "
                "WHERE grassroots_guid='flaky'"))
        ck("A FAILED FETCH DOES NOT RESTAMP THE CLOCK — the club stays due, so a "
           "PlayHQ wobble cannot silently buy it another 90 days of staleness",
           stamp is not None and (datetime.now(timezone.utc) - stamp).days >= 199,
           str(stamp))
        ck("and its stored associations are left standing rather than blanked",
           (await _assoc_name(Session, "flaky")) == "Some Assoc")

        # ── 5. REFRESHING CAN BE SWITCHED OFF ─────────────────────────────────
        original_days = settings.marketing_association_refresh_days
        try:
            settings.marketing_association_refresh_days = 0
            fake.asked.clear()
            async with Session() as s:
                off = await cd.enrich_associations(s, limit=10)
            ck("0 DAYS RESTORES THE PRE-298 BEHAVIOUR — no club with associations "
               "is re-read at all", not any(a in fake.asked for a in ("stale", "left")),
               str(fake.asked))
            ck("and nothing is reported as refresh-due",
               off.get("refresh_due") == 0, str(off.get("refresh_due")))
        finally:
            settings.marketing_association_refresh_days = original_days
    finally:
        cd.phq.discover_associations = real_assoc
        cd.phq.discover_org_contact = real_contact

    # ── 6. THE OTHER TWO THIRDS OF THE ASK, ASSERTED RATHER THAN ASSUMED ──────
    # "pick up changes in address … officers" was already true. Proving it is
    # what makes "nothing to build there" an answer rather than a claim.
    search = _FakeSearch({1: [{
        "id": "addr", "name": "Renamed CC", "routingCode": "addr",
        "tenant": {"name": "Cricket Australia"},
        "address": {"suburb": "New Suburb", "state": "WA", "postcode": "6000"},
        "websiteUrl": "https://new.example",
        "contacts": [{"firstName": "Fresh", "lastName": "Officer",
                      "position": "Treasurer", "email": "fresh@addr.test",
                      "phone": None, "visible": True}],
    }]})
    async with Session() as s:
        await seed(s, "addr", name="Old Name CC", assocs=None, fetched_at=None)
        await s.execute(text(
            "UPDATE marketing_clubs SET suburb='Old Suburb', postcode='1111' "
            "WHERE grassroots_guid='addr'"))
        await s.commit()

    real_search = cd.phq.search_organisations
    cd.phq.search_organisations = search
    try:
        async with Session() as s:
            await cd.discover_clubs(s)
        async with Session() as s:
            row = (await s.execute(text(
                "SELECT name, suburb, postcode, website_url FROM marketing_clubs "
                "WHERE grassroots_guid='addr'"))).first()
            officers = await s.scalar(text(
                "SELECT count(*) FROM marketing_club_contacts c "
                "JOIN marketing_clubs k ON k.id = c.marketing_club_id "
                "WHERE k.grassroots_guid='addr'"))
        ck("AN ORDINARY CRAWL ALREADY REFRESHES THE ADDRESS — name, suburb, "
           "postcode and website are rewritten on every pass",
           row is not None and row[0] == "Renamed CC" and row[1] == "New Suburb"
           and row[2] == "6000" and row[3] == "https://new.example", str(row))
        ck("AND IT ALREADY ADDS A NEWLY LISTED OFFICER — the additive half was "
           "never the gap", officers == 1, str(officers))
    finally:
        cd.phq.search_organisations = real_search

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


async def _assoc_name(Session, guid):
    async with Session() as s:
        return await s.scalar(text(
            "SELECT association_name FROM marketing_clubs WHERE grassroots_guid = :g"),
            {"g": guid})


class _FakeSearch:
    def __init__(self, pages, total=250):
        self.pages, self.total, self.asked = pages, total, []

    async def __call__(self, _kind, _q, page=1, limit=100, **_kw):
        self.asked.append(page)
        return self.pages.get(page, []), self.total


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
