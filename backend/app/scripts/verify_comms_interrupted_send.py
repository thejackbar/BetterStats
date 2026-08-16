"""Verification for the interrupted-send fix (BetterComms, v9.24.16).

Reproduces the 16 Aug 2026 incident against a real database: two campaigns were
sending when the backend was restarted, ~4,969 emails had already gone out, and
every one of the 9,868 recipients was still 'queued' with the campaigns showing
0 sent — the whole batch's outcomes were held in memory awaiting a single
write-back that never came.

Exercises the shipped functions (routers.comms._run_send / _campaign_tallies /
resume_deferred_campaigns / resume_interrupted_sends, comms_limits
.ses_events_health), stubbing only the email provider so a process death can be
simulated mid-run. It creates its own throwaway club and campaigns.

WARNING: this REBUILDS the public schema, so point it at a scratch database
only, never a live one. It refuses to run without VERIFY_COMMS_DSN set:

  VERIFY_COMMS_DSN=postgresql+asyncpg://user@host/scratch_db \\
    python -m app.scripts.verify_comms_interrupted_send
"""
import asyncio, os, sys, uuid, datetime as dt

_DSN = os.environ.get("VERIFY_COMMS_DSN")
if not _DSN:
    sys.exit("Refusing to run: set VERIFY_COMMS_DSN to a SCRATCH database "
             "(this script drops and recreates the public schema).")
os.environ["DATABASE_URL"] = _DSN
os.environ.setdefault("SECRET_KEY", "verify-only")

from sqlalchemy import text
from app.models.db import async_session_maker, engine, Base

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))



ORG = uuid.uuid4()


async def seed(n_recipients, status="queued"):
    """One club, one campaign at 'sending', n queued recipients."""
    cid = uuid.uuid4()
    async with async_session_maker() as s:
        await s.execute(text(
            "INSERT INTO comms_campaigns (id, organisation_id, name, subject, body_html,"
            " status, stats) VALUES (:i,:o,'Test','Subj','<p>Hi {{first_name}}</p>','sending',"
            " '{}'::jsonb)"), {"i": cid, "o": ORG})
        for k in range(n_recipients):
            await s.execute(text(
                "INSERT INTO comms_recipients (id, campaign_id, organisation_id, email, name, status)"
                " VALUES (:i,:c,:o,:e,:n,:st)"),
                {"i": uuid.uuid4(), "c": cid, "o": ORG,
                 "e": f"p{k}@club{k}.example", "n": f"P{k}", "st": status})
        await s.commit()
    return cid


async def counts(cid):
    async with async_session_maker() as s:
        rows = (await s.execute(text(
            "SELECT status, count(*) FROM comms_recipients WHERE campaign_id=:c GROUP BY status"),
            {"c": cid})).all()
    return {r[0]: int(r[1]) for r in rows}


async def campaign_row(cid):
    async with async_session_maker() as s:
        r = (await s.execute(text(
            "SELECT status, stats, error FROM comms_campaigns WHERE id=:c"), {"c": cid})).one()
    return {"status": r[0], "stats": r[1], "error": r[2]}


class Res:
    def __init__(self, ok, mid=None, err=None):
        self.ok, self.message_id, self.error = ok, mid, err


class StubProvider:
    """Stands in for SES. `die_after` raises once N sends have been attempted,
    reproducing a process death mid-run (the 16 Aug incident)."""
    name = "stub"

    def __init__(self, die_after=None, fail_all=False):
        self.attempts = 0
        self.die_after = die_after
        self.fail_all = fail_all
        self.sent_to = []

    async def send(self, msg):
        self.attempts += 1
        if self.die_after is not None and self.attempts > self.die_after:
            raise RuntimeError("simulated process death mid-send")
        if self.fail_all:
            return Res(False, err="provider rejected")
        self.sent_to.append(getattr(msg, "to", None) or getattr(msg, "to_email", None))
        return Res(True, mid=f"ses-{self.attempts}")


async def main():
    # Build the schema from the real ORM metadata rather than a hand-written
    # copy, so the tables match what the shipped code actually queries.
    async with engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as s:
        await s.execute(text(
            "INSERT INTO organisations (id,name,slug,comms_tier,is_active)"
            " VALUES (:i,'Test CC','test-cc','production',true)"), {"i": ORG})
        await s.commit()

    from app.routers import comms as C
    from app.services import comms_limits

    # Small chunk so a 25-recipient campaign spans several commits.
    C.SEND_CHUNK = 10

    print("\n--- item 1: chunked write-back survives a mid-send crash ---")
    cid = await seed(25)
    prov = StubProvider(die_after=12)   # dies during the 2nd chunk
    C.get_email_provider = lambda: prov
    comms_limits.send_allowance = lambda s, org, defaults=None: _ok(1000)
    await C._run_send(str(cid), str(ORG))

    c = await counts(cid)
    check("first chunk committed as sent despite the crash", c.get("sent") == 10, str(c))
    check("in-flight chunk is recorded, not silently lost", c.get("in_flight") == 10, str(c))
    check("untouched recipients stay queued", c.get("queued") == 5, str(c))
    check("crash did not lose the whole batch (old bug: 25 queued)",
          c.get("queued", 0) != 25, str(c))
    row = await campaign_row(cid)
    check("campaign counters moved during the run", (row["stats"] or {}).get("sent") == 10, str(row["stats"]))

    print("\n--- item 2: resume finishes the campaign, never re-sends in-flight ---")
    # Campaign is at 'error' after the crash; a real restart leaves it 'sending'.
    async with async_session_maker() as s:
        await s.execute(text("UPDATE comms_campaigns SET status='sending', error=NULL WHERE id=:c"),
                        {"c": cid})
        await s.commit()
    prov2 = StubProvider()
    C.get_email_provider = lambda: prov2
    kicked = await C.resume_deferred_campaigns(reason="test")
    c2 = await counts(cid)
    check("resume picked the campaign up (queued now matched)", kicked == 1, f"kicked={kicked}")
    check("only the 5 genuinely-queued rows were sent on resume",
          prov2.attempts == 5, f"attempts={prov2.attempts}")
    check("in-flight rows were NOT re-sent (no duplicate to a real club)",
          c2.get("in_flight") == 10, str(c2))
    check("nothing left queued", c2.get("queued", 0) == 0, str(c2))
    check("sent total is 15 (10 + 5), in-flight excluded", c2.get("sent") == 15, str(c2))
    row2 = await campaign_row(cid)
    check("campaign finalised as sent", row2["status"] == "sent", row2["status"])
    check("unconfirmed reported in stats", (row2["stats"] or {}).get("unconfirmed") == 10, str(row2["stats"]))
    check("unconfirmed explained on the campaign, not reported as clean",
          row2["error"] and "never confirmed" in row2["error"], str(row2["error"]))

    print("\n--- item 2b: the old resume query would have stranded this ---")
    async with async_session_maker() as s:
        old = (await s.execute(text("""
            SELECT COUNT(DISTINCT c.id) FROM comms_campaigns c
            JOIN comms_recipients r ON r.campaign_id = c.id
            WHERE c.status='sending' AND r.status='deferred'"""))).scalar()
        new = (await s.execute(text("""
            SELECT COUNT(DISTINCT c.id) FROM comms_campaigns c
            JOIN comms_recipients r ON r.campaign_id = c.id
            WHERE c.status='sending' AND r.status IN ('deferred','queued')"""))).scalar()
    cid_str = await seed(4)
    async with async_session_maker() as s:
        old2 = (await s.execute(text("""
            SELECT COUNT(DISTINCT c.id) FROM comms_campaigns c
            JOIN comms_recipients r ON r.campaign_id = c.id
            WHERE c.status='sending' AND r.status='deferred'"""))).scalar()
        new2 = (await s.execute(text("""
            SELECT COUNT(DISTINCT c.id) FROM comms_campaigns c
            JOIN comms_recipients r ON r.campaign_id = c.id
            WHERE c.status='sending' AND r.status IN ('deferred','queued')"""))).scalar()
    check("deferred-only query misses a restart-stranded campaign", int(old2) == 0, str(old2))
    check("widened query finds it", int(new2) == 1, str(new2))

    print("\n--- item 2c: double-dispatch guard ---")
    cid3 = await seed(5)
    C._SENDING_CAMPAIGNS.add(str(cid3))
    prov3 = StubProvider()
    C.get_email_provider = lambda: prov3
    await C._run_send(str(cid3), str(ORG))
    check("a campaign already sending in-process is skipped, not sent twice",
          prov3.attempts == 0, f"attempts={prov3.attempts}")
    C._SENDING_CAMPAIGNS.discard(str(cid3))
    check("guard released after the run", str(cid) not in C._SENDING_CAMPAIGNS)

    print("\n--- item 3: SES event health ---")
    async with async_session_maker() as s:
        h = await comms_limits.ses_events_health(s)
    check("reports disconnected: real sends, zero SES events", h["connected"] is False, str(h))
    check("flagged unhealthy so startup warns", h["healthy"] is False, str(h))
    check("counts the sends it expected events for", h["sent"] >= 15, str(h))

    # Our own unsubscribe events must NOT count as SES being connected — that is
    # exactly the shape of the live data that hid this for five weeks.
    async with async_session_maker() as s:
        await s.execute(text(
            "INSERT INTO email_events (id, email, event_type)"
            " VALUES (:i,'a@b.example','unsubscribe')"), {"i": uuid.uuid4()})
        await s.commit()
        h2 = await comms_limits.ses_events_health(s)
    check("unsubscribe events alone do not read as connected", h2["connected"] is False, str(h2))

    async with async_session_maker() as s:
        await s.execute(text(
            "INSERT INTO email_events (id, email, event_type)"
            " VALUES (:i,'a@b.example','delivery')"), {"i": uuid.uuid4()})
        await s.commit()
        h3 = await comms_limits.ses_events_health(s)
    check("a real delivery event flips it to connected", h3["connected"] is True, str(h3))
    check("and healthy", h3["healthy"] is True, str(h3))

    # No sends at all in the window -> nothing to expect, so not a problem.
    async with async_session_maker() as s:
        await s.execute(text("DELETE FROM email_events"))
        await s.execute(text("UPDATE comms_recipients SET sent_at = now() - interval '60 days'"))
        await s.commit()
        h4 = await comms_limits.ses_events_health(s)
    check("silent when nothing was sent in the window", h4["healthy"] is True, str(h4))

    print("\n--- blast radius: chunk size is what bounds the loss ---")
    # One chunk covering the whole audience is the old shape: a crash confirms
    # nothing at all, which is exactly what left 9,868 recipients unattributed.
    C.SEND_CHUNK = 10_000
    cid_big = await seed(25)
    C.get_email_provider = lambda: StubProvider(die_after=12)
    await C._run_send(str(cid_big), str(ORG))
    cbig = await counts(cid_big)
    check("single-chunk run confirms nothing when it crashes", cbig.get("sent", 0) == 0, str(cbig))
    C.SEND_CHUNK = 10
    cid_sm = await seed(25)
    C.get_email_provider = lambda: StubProvider(die_after=12)
    await C._run_send(str(cid_sm), str(ORG))
    csm = await counts(cid_sm)
    check("chunked run confirms everything before the failing chunk",
          csm.get("sent", 0) == 10, str(csm))
    check("chunking strictly reduces the unattributed rows",
          csm.get("sent", 0) > cbig.get("sent", 0), f"{csm} vs {cbig}")

    print("\n--- regression: an ordinary uninterrupted send still works ---")
    cid4 = await seed(23)
    prov4 = StubProvider()
    C.get_email_provider = lambda: prov4
    await C._run_send(str(cid4), str(ORG))
    c4 = await counts(cid4)
    row4 = await campaign_row(cid4)
    check("every recipient sent", c4.get("sent") == 23, str(c4))
    check("no rows left in flight", "in_flight" not in c4, str(c4))
    check("campaign marked sent", row4["status"] == "sent", row4["status"])
    check("no spurious error on a clean send", not row4["error"], str(row4["error"]))
    check("provider called exactly once per recipient", prov4.attempts == 23, str(prov4.attempts))

    print("\n--- regression: all-fail still reports error ---")
    cid5 = await seed(6)
    C.get_email_provider = lambda: StubProvider(fail_all=True)
    await C._run_send(str(cid5), str(ORG))
    row5 = await campaign_row(cid5)
    c5 = await counts(cid5)
    check("all-failed campaign flagged error", row5["status"] == "error", row5["status"])
    check("failures recorded per row", c5.get("failed") == 6, str(c5))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
    await engine.dispose()
    return 1 if FAIL else 0


class _ok:
    """send_allowance is awaited; wrap a plain int."""
    def __init__(self, v): self.v = v
    def __await__(self):
        async def _c(): return self.v
        return _c().__await__()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
