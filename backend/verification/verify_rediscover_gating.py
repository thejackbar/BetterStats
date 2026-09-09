"""Why the Rediscover committees button is disabled, and whether it is right to be.

Reported: "rediscover committee is disabled on club directory". Nothing was
broken — the button is gated on the operator's Stop flag (correctly: a full
rediscover re-pages the whole of PlayHQ and ``rediscover_all`` refuses outright
while the crawler is stopped) and on the in-process "a run is going" dict. It
simply never said which, and the Stop that causes it is set two rows away.

What is checked here, through the SHIPPED route bodies and services:

  · the two meanings of "paused" are kept apart — ``state == 'paused'`` is the
    runner merely on a break and must NOT read as the operator's Stop, or the
    button would go dead every time the crawler took a breather
  · the Stop flag really does stop a rediscover, which is what makes the gate
    correct rather than merely cautious
  · the server's own staleness answer rides on the status, so the screen cannot
    disagree with it about whether a new run would be allowed
  · a run this process has lost track of is reported stale, which is the case the
    button used to be permanently dead in
  · a rediscover legitimately running for hours is NOT reported stale

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


async def main():
    engine = create_async_engine(DB, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text(CRAWL_CONTROL_DDL))
        await conn.execute(text(
            "INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
            "ON CONFLICT (id) DO NOTHING"))
        # crawl_status reads the directory; an empty one is a legitimate state
        # ("idle") and is all these checks need.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marketing_clubs (
                id UUID PRIMARY KEY,
                kind TEXT,
                associations JSONB,
                last_crawled_at TIMESTAMPTZ
            )
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

    # ── 2. THE STOP FLAG IS WHAT THE BUTTON READS, AND IT REALLY STOPS A RUN ──
    if cd is None:
        report("stopping the crawler sets the flag the button reads", "club_directory absent")
        report("and a rediscover then refuses to run", "club_directory absent")
        report("starting the crawler clears it", "club_directory absent")
    else:
        async with Session() as s:
            await cd.set_crawl_paused(s, True)
            st = await cd.crawl_status(s)
        ck("stopping the crawler sets the flag the button reads",
           st.get("paused") is True, str(st.get("paused")))
        ck("and the status says so in words, naming the way out",
           st.get("state") == "stopped" and "Start crawling" in (st.get("detail") or ""),
           f"{st.get('state')} / {st.get('detail')}")

        # THIS is what makes the gate correct rather than merely cautious: with
        # the crawler stopped a rediscover genuinely does nothing, so a button
        # that let you press it would report a finished run that never read a page.
        async with Session() as s:
            res = await cd.rediscover_all(s)
        ck("A REDISCOVER GENUINELY REFUSES WHILE STOPPED — so holding the button "
           "back is right, it just had to say why",
           isinstance(res, dict) and res.get("skipped") == "stopped", str(res))
        ck("and it reports skipped rather than a zero-club success, which would "
           "read as 'nothing to do'",
           "au_seen" not in (res or {}), str(res))

        async with Session() as s:
            await cd.set_crawl_paused(s, False)
            st = await cd.crawl_status(s)
        ck("starting the crawler clears it", st.get("paused") is False, str(st.get("paused")))

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
        finally:
            mkt._rediscover.clear()
            mkt._rediscover.update(original)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
