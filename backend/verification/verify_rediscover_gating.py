"""What the crawler's Stop switch governs, and what it deliberately does not.

Reported first as "rediscover committee is disabled on club directory", then,
once the button explained itself: if they are two different jobs, why must the
crawler be restarted to run one of them?

The gate turned out to be protecting nothing. The prune is per club, scoped to
the ids seen in that club's OWN payload, so a half-finished run leaves the clubs
it never reached untouched rather than emptied. And the platform already
disagreed with itself: the single-club ``rediscover_club`` bypasses
``discover_clubs`` entirely and has always run while stopped, same prune, same
retick, no gate at all. The all-clubs gate was inherited from the code it is
built on, not a safety rule.

So Stop now means "stop the UNATTENDED crawler" and a rediscover carries its own
cancel — which is what keeps "halt every bit of PlayHQ traffic" reachable.

What is checked here, through the SHIPPED route bodies and services:

  · the two meanings of "paused" are kept apart — ``state == 'paused'`` is the
    runner merely on a break and must NOT read as the operator's Stop
  · a REDISCOVER runs while the crawler is stopped, and reconciles for real
  · every BACKGROUND path still honours the Stop, so the switch still stops all
    unattended traffic — the half of the old behaviour that must not regress
  · a rediscover stops on its OWN cancel, and reports itself stopped rather than
    as a finished run that happened to read fewer clubs
  · the clubs a stopped run never reached are left exactly as they were
  · the server's own staleness answer rides on the status, so the screen cannot
    disagree with it about whether a new run would be allowed
  · a run this process has lost track of is reported stale; one legitimately
    running for hours is not

Run:  DATABASE_URL=... python -m verification.verify_rediscover_gating
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
    """A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN — a missing part is
    reported by name rather than raising on the first attribute read."""
    global FAIL
    FAIL += 1
    print(f"FAIL {name}  {why}")


# ── the shipped code, loaded so a control run reports rather than dying ────────
try:
    from app.routers import marketing as mkt
except Exception as e:  # noqa: BLE001
    mkt = None
    print(f"NOTE  app.routers.marketing did not import: {e}")

try:
    from app.services import club_directory as cd
except Exception as e:  # noqa: BLE001
    cd = None
    print(f"NOTE  app.services.club_directory did not import: {e}")


CRAWL_CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS marketing_crawl_control (
    id          INTEGER PRIMARY KEY,
    paused      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT marketing_crawl_control_singleton CHECK (id = 1)
)
"""


class _NullBackground:
    """Stands in for FastAPI's BackgroundTasks — the POST's bookkeeping is what
    is being checked, not the hours-long run it would queue."""

    def add_task(self, *_a, **_kw):
        pass


def au_club(guid, name, contacts):
    """One AU club in the shape PlayHQ's search actually returns."""
    return {"id": guid, "name": name, "routingCode": guid[:8],
            "tenant": {"name": "Cricket Australia"},
            "address": {"suburb": "Somewhere", "state": "WA"},
            "contacts": contacts}


def officer(name, position, email):
    first, _, last = name.partition(" ")
    return {"firstName": first, "lastName": last, "position": position,
            "email": email, "phone": None, "visible": True}


class FakeSearch:
    """Stands in for the PlayHQ club search. Records how many pages were asked
    for, which is what tells a run that stopped from one that finished.

    ``total`` matters more than it looks: ``discover_clubs`` stops once
    ``(pages_done * 100) >= totalRecords``, so a fake reporting its own tiny row
    count is 'finished' after page one and a cancel could never be reached. It
    defaults high so paging continues, and the caller sets it low only when
    running out of pages IS the thing being checked."""

    def __init__(self, pages, total=250):
        self.pages = pages           # {page_no: [club, …]}
        self.total = total
        self.asked = []

    async def __call__(self, _kind, _q, page=1, limit=100, **_kw):
        self.asked.append(page)
        return self.pages.get(page, []), self.total


async def main():
    engine = create_async_engine(DB, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(CRAWL_CONTROL_DDL))
        await conn.execute(text(
            "INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"))
        # THE HARNESS TABLES ARE BUILT FROM THE ORM MODELS, never by hand — a
        # table that merely LOOKS right is worse than none, and _upsert_club
        # writes a good deal more than the four columns crawl_status reads.
        if cd is not None:
            from app.models.db import (   # noqa: PLC0415 — optional, see the NOTE above
                Base, MarketingClub, MarketingClubContact, Organisation, User)
            # `users` comes along because organisations carries an FK to it
            # (password_protected_by); create_all sorts the circular pair out.
            await conn.run_sync(Base.metadata.create_all, tables=[
                User.__table__, Organisation.__table__, MarketingClub.__table__,
                MarketingClubContact.__table__])
        else:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS marketing_clubs (
                    id UUID PRIMARY KEY, kind TEXT, associations JSONB,
                    last_crawled_at TIMESTAMPTZ)
            """))

    # ── 1. THE TWO MEANINGS OF "PAUSED" ARE NOT THE SAME FLAG ─────────────────
    # `state` can read "paused" for a runner merely on a break, while the
    # operator's Stop is the separate `paused` BOOLEAN. The button gates on the
    # boolean; gating on the word would kill it every time the crawler breathed.
    if cd is None:
        report("the operator's Stop is a different thing from a stalled runner",
               "club_directory absent")
    else:
        async with Session() as s:
            await cd.set_crawl_paused(s, False)
            st = await cd.crawl_status(s)
        ck("with nothing stopped, the operator flag is false",
           st.get("paused") is False, str(st.get("paused")))
        ck("and the button's own condition is therefore not met",
           not st.get("paused"))
        ck("THE DERIVED 'paused' STATE IS NOT THE OPERATOR'S STOP — a runner on "
           "a break must never disable the button",
           st.get("state") != "stopped", st.get("state"))

    # ── 2. THE STOP FLAG STOPS THE UNATTENDED CRAWLER ─────────────────────────
    if cd is None:
        report("stopping the crawler sets the flag", "club_directory absent")
        report("an ordinary discovery pass honours the Stop", "club_directory absent")
        report("association enrichment honours the Stop", "club_directory absent")
        report("a crawl batch honours the Stop", "club_directory absent")
        report("starting the crawler clears it", "club_directory absent")
    else:
        async with Session() as s:
            await cd.set_crawl_paused(s, True)
            st = await cd.crawl_status(s)
        ck("stopping the crawler sets the flag", st.get("paused") is True,
           str(st.get("paused")))
        ck("and the status says so in words, naming the way out",
           st.get("state") == "stopped" and "Start crawling" in (st.get("detail") or ""),
           f"{st.get('state')} / {st.get('detail')}")

        # THE HALF THAT MUST NOT REGRESS. Letting a rediscover through is only
        # defensible while Stop still stops everything unattended, so each
        # background path is pressed with the flag set and must read nothing.
        search = FakeSearch({1: [au_club("g-bg", "Background CC",
                                         [officer("A B", "President", "a@b.test")])]})
        real_search = cd.phq.search_organisations
        cd.phq.search_organisations = search
        try:
            async with Session() as s:
                bg = await cd.discover_clubs(s)
            ck("AN ORDINARY DISCOVERY PASS STILL HONOURS THE STOP — this is the "
               "unattended crawler the switch is for",
               bg.get("au_seen") == 0 and bg.get("stopped") is True, str(bg))
            ck("and it asked PlayHQ for nothing at all", search.asked == [],
               str(search.asked))

            async with Session() as s:
                batch = await cd.crawl_batch(s)
            ck("a crawl batch still refuses outright while stopped",
               batch.get("skipped") == "stopped", str(batch))

            async with Session() as s:
                enr = await cd.enrich_associations(s, limit=5)
            ck("association enrichment still honours the Stop",
               enr.get("enriched") == 0, str(enr.get("enriched")))
        finally:
            cd.phq.search_organisations = real_search

        async with Session() as s:
            await cd.set_crawl_paused(s, False)
            st = await cd.crawl_status(s)
        ck("starting the crawler clears it", st.get("paused") is False,
           str(st.get("paused")))

    # ── 2b. A REDISCOVER IS NOT THE UNATTENDED CRAWLER ────────────────────────
    # The reported case: two different jobs, one switch. A super admin pressing
    # Rediscover is explicit intent, and the per-club Rediscover has always run
    # while stopped — so refusing here was the platform disagreeing with itself.
    if cd is None:
        report("a rediscover runs while the crawler is stopped", "club_directory absent")
        report("and it reconciles for real", "club_directory absent")
    else:
        search = FakeSearch({1: [au_club(
            "g-red", "Rediscover CC",
            [officer("Current Sec", "Secretary", "sec@redis.test")])]})
        real_search = cd.phq.search_organisations
        cd.phq.search_organisations = search
        try:
            async with Session() as s:
                await cd.set_crawl_paused(s, True)
            async with Session() as s:
                res = await cd.rediscover_all(s)
            ck("A REDISCOVER RUNS WHILE THE CRAWLER IS STOPPED — the reported "
               "case, and what the single-club Rediscover has always done",
               res.get("au_seen") == 1 and not res.get("stopped"), str(res))
            ck("and it really read PlayHQ rather than short-circuiting",
               search.asked and search.asked[0] == 1, str(search.asked))
            ck("it no longer reports a skip, so nothing formats a refusal as a "
               "zero-club success", "skipped" not in res, str(res))

            async with Session() as s:
                got = await s.scalar(text(
                    "SELECT count(*) FROM marketing_club_contacts c "
                    "JOIN marketing_clubs k ON k.id = c.marketing_club_id "
                    "WHERE k.grassroots_guid = 'g-red'"))
            ck("and the committee it read is actually stored", got == 1, str(got))
        finally:
            cd.phq.search_organisations = real_search
            async with Session() as s:
                await cd.set_crawl_paused(s, False)

    # ── 2c. A REDISCOVER STOPS ON ITS OWN CANCEL ──────────────────────────────
    # Without this, letting it ignore the crawler's Stop would take away the
    # ability to halt all PlayHQ traffic once one was running.
    if cd is None:
        report("a rediscover stops on its own cancel", "club_directory absent")
        report("a halted run reports itself stopped", "club_directory absent")
        report("clubs a halted run never reached are untouched", "club_directory absent")
    else:
        # Page 1 reconciles; the cancel is raised before page 2, so the club on
        # page 2 must be left exactly as it was.
        untouched_guid = "g-page2"
        async with Session() as s:
            await s.execute(text(
                "INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, source) "
                "VALUES (gen_random_uuid(), :g, 'Untouched CC', 'club', 'seed') "
                "ON CONFLICT (grassroots_guid) DO NOTHING"), {"g": untouched_guid})
            await s.commit()

        search = FakeSearch({
            1: [au_club("g-p1", "Page One CC",
                        [officer("P One", "President", "p1@stop.test")])],
            2: [au_club(untouched_guid, "Untouched CC RENAMED",
                        [officer("P Two", "President", "p2@stop.test")])],
        })
        cancelled = {"v": False}

        async def cancel_after_first_page():
            if search.asked:          # page 1 has been fetched — stop before page 2
                cancelled["v"] = True
            return cancelled["v"]

        real_search = cd.phq.search_organisations
        cd.phq.search_organisations = search
        try:
            try:
                async with Session() as s:
                    res = await cd.rediscover_all(s, should_stop=cancel_after_first_page)
            except TypeError as e:   # a build with no cancel at all
                res = {}
                report("a rediscover takes a cancel of its own", str(e))
            ck("A REDISCOVER STOPS ON ITS OWN CANCEL — so halting every bit of "
               "PlayHQ traffic is still reachable",
               res.get("stopped") is True, str(res))
            ck("A HALTED RUN IS NOT A FINISHED ONE — it says so rather than "
               "printing the same line over a partial pass",
               res.get("au_seen") == 1 and res.get("stopped") is True, str(res))
            ck("and it never asked for the page it was stopped before",
               2 not in search.asked, str(search.asked))

            async with Session() as s:
                name = await s.scalar(text(
                    "SELECT name FROM marketing_clubs WHERE grassroots_guid = :g"),
                    {"g": untouched_guid})
                kept = await s.scalar(text(
                    "SELECT count(*) FROM marketing_club_contacts c "
                    "JOIN marketing_clubs k ON k.id = c.marketing_club_id "
                    "WHERE k.grassroots_guid = :g"), {"g": untouched_guid})
            ck("A CLUB THE HALTED RUN NEVER REACHED IS LEFT EXACTLY AS IT WAS — "
               "the prune is per club, so a partial pass cannot empty it",
               name == "Untouched CC" and kept == 0, f"{name} / {kept} contact(s)")
        finally:
            cd.phq.search_organisations = real_search

    # ── 3. THE SERVER'S STALENESS ANSWER RIDES ON THE STATUS ──────────────────
    # The screen must not keep a second copy of the window: the POST decides
    # whether a new run is allowed, so the status has to report the same answer.
    if mkt is None or not hasattr(mkt, "rediscover_status"):
        report("the status reports whether a new run would be allowed", "route absent")
        report("a run this process has lost track of is reported stale", "route absent")
        report("a rediscover running for hours is NOT reported stale", "route absent")
        report("the status and the POST cannot disagree", "route absent")
        report("the rest of the payload survives", "route absent")
    else:
        original = dict(mkt._rediscover)
        try:
            def set_state(**kw):
                mkt._rediscover.update(kw)

            # nothing running — nothing to be stale about
            set_state(running=False, started_at=None, finished_at=None,
                      result=None, error=None, progress={})
            out = await mkt.rediscover_status(_=None)
            ck("with no run at all, the status is not stale",
               out.get("stale") is False, str(out.get("stale")))
            ck("and reports not running", out.get("running") is False)

            # just started — the ordinary case
            set_state(running=True, started_at=datetime.now(timezone.utc).isoformat(),
                      progress={"clubs_seen": 12})
            out = await mkt.rediscover_status(_=None)
            ck("a run that has just started is not stale",
               out.get("stale") is False, str(out.get("stale")))

            # 45 minutes in — a rediscover legitimately runs for HOURS, so the
            # shared 30-minute default must not apply to it.
            set_state(running=True, started_at=(
                datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat())
            out = await mkt.rediscover_status(_=None)
            ck("A REDISCOVER 45 MINUTES IN IS NOT STALE — it re-pages the whole of "
               "PlayHQ at 15-40s a page and legitimately runs for hours",
               out.get("stale") is False, str(out.get("stale")))

            # a day in — this process has lost track of it
            set_state(running=True, started_at=(
                datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
            out = await mkt.rediscover_status(_=None)
            ck("A RUN THIS PROCESS HAS LOST TRACK OF IS REPORTED STALE — the case "
               "the button used to be permanently dead in",
               out.get("stale") is True, str(out.get("stale")))
            ck("while still reporting running, so the screen can tell the two apart",
               out.get("running") is True)

            # THE STATUS AND THE POST CANNOT DISAGREE. The whole reason `stale`
            # is exposed is that the browser's disable and the server's own
            # decision have to be the same decision.
            for label, started, expect_stale in (
                ("a fresh run", datetime.now(timezone.utc), False),
                ("a day-old run", datetime.now(timezone.utc) - timedelta(hours=24), True),
            ):
                set_state(running=True, started_at=started.isoformat())
                out = await mkt.rediscover_status(_=None)
                allowed = not (mkt._rediscover["running"] and not mkt._bg_stale(
                    mkt._rediscover, mkt._REDISCOVER_STALE_SECS))
                ck(f"the status and the POST agree about {label}",
                   out.get("stale") is expect_stale and allowed is expect_stale,
                   f"stale={out.get('stale')} allowed={allowed}")

            # the rest of the payload is untouched by the added key
            set_state(running=True, started_at="2026-09-09T01:00:00+00:00",
                      finished_at=None, result=None, error=None,
                      progress={"clubs_seen": 41, "pruned": 3})
            out = await mkt.rediscover_status(_=None)
            ck("the rest of the payload survives — progress, started_at, result, error",
               out.get("progress") == {"clubs_seen": 41, "pruned": 3}
               and out.get("started_at") == "2026-09-09T01:00:00+00:00"
               and "result" in out and "error" in out,
               str(out))
            ck("and the status is a copy, so a reader cannot mutate the live state",
               out is not mkt._rediscover)

            # a malformed started_at reads as stale rather than raising, so a
            # corrupt dict frees the button instead of wedging it for ever
            set_state(running=True, started_at="not a timestamp")
            out = await mkt.rediscover_status(_=None)
            ck("a malformed start time reads as stale rather than raising — a "
               "corrupt dict frees the button instead of wedging it",
               out.get("stale") is True, str(out.get("stale")))

            # ── the stop endpoint ─────────────────────────────────────────────
            if not hasattr(mkt, "rediscover_stop"):
                report("stopping a rediscover raises its cancel", "route absent")
                report("stopping when nothing runs says so", "route absent")
                report("the cancel is asked by the run itself", "route absent")
                report("a new run clears a cancel left by the last one", "route absent")
            else:
                set_state(running=True, started_at=datetime.now(timezone.utc).isoformat(),
                          cancel=False)
                out = await mkt.rediscover_stop(_=None)
                ck("stopping a rediscover raises its cancel",
                   out.get("status") == "stopping"
                   and mkt._rediscover.get("cancel") is True, str(out))
                ck("and the status carries it, so the button can say 'Stopping...'",
                   (await mkt.rediscover_status(_=None)).get("cancel") is True)

                # THE CANCEL IS WHAT THE RUN ITSELF ASKS. A flag nothing reads
                # would leave the Stop button drawing a control that does nothing.
                ck("THE CANCEL IS THE CHECK THE RUN ASKS — not a flag nothing reads",
                   await mkt._rediscover_cancelled() is True)

                set_state(running=False, cancel=False)
                out = await mkt.rediscover_stop(_=None)
                ck("stopping when nothing is running says so rather than arming a "
                   "cancel the next run would trip over",
                   out.get("status") == "not_running"
                   and mkt._rediscover.get("cancel") is False, str(out))

                # A stale cancel must not kill the NEXT run before it starts.
                set_state(running=False, cancel=True, started_at=None)
                await mkt.rediscover(background=_NullBackground(), _=None)
                ck("STARTING A RUN CLEARS A CANCEL LEFT BY THE LAST ONE — or the "
                   "next rediscover would stop before its first page",
                   mkt._rediscover.get("cancel") is False
                   and mkt._rediscover.get("running") is True,
                   str({k: mkt._rediscover.get(k) for k in ("cancel", "running")}))
        finally:
            mkt._rediscover.clear()
            mkt._rediscover.update(original)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
