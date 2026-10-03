"""stop_sync: stop a running sync and keep it stopped (app/scripts/stop_sync.py).

Real Postgres, the real `_check_sync_control` checkpoint polled by a stand-in
live loop, and the exact startup self-heal query from main.py run before
(control: it WOULD resume the club) and after (it finds nothing).

Run:  DATABASE_URL=... python -m verification.verify_stop_sync
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, uuid, io, contextlib
from sqlalchemy import text
from app.models.db import async_session_maker
from app.services.sync import _check_sync_control, SyncControlSignal
from app.scripts import stop_sync

RESUME_SQL = "SELECT id FROM sync_runs WHERE status='running' AND kind IN ('org_full','org_hard_refresh') AND org_id=:o"
P=F=0
def ck(n,c,x=""):
    global P,F
    if c: P+=1; print("PASS",n)
    else: F+=1; print("FAIL",n,x)

async def q(sql, **p):
    async with async_session_maker() as db:
        return (await db.execute(text(sql), p)).mappings().all()
async def ex(sql, **p):
    async with async_session_maker() as db:
        await db.execute(text(sql), p); await db.commit()

async def mk(org, kind, status):
    rid = uuid.uuid4()
    await ex("INSERT INTO sync_runs (id,org_id,kind,status,stats) VALUES (:i,:o,:k,:s,'{}'::json)", i=rid,o=org,k=kind,s=status)
    return rid

async def live_loop(rid, log):
    try:
        while True:
            await asyncio.sleep(0.5)
            await _check_sync_control(rid, {})
    except SyncControlSignal as s:
        log.append(s.action)

async def main():
    A, B = uuid.uuid4(), uuid.uuid4()
    for o,n in ((A,"Club A"),(B,"Club B")):
        await ex("INSERT INTO organisations (id,name,slug,is_active) VALUES (:i,:n,:s,true)", i=o,n=n,s=str(o)[:8])
    live = await mk(A,"org_full","running")           # a live loop is polling this one
    orphan = await mk(A,"org_hard_refresh","running") # process gone / stuck: nobody polls
    quick = await mk(A,"org_quick","running")         # non-full kind
    paused = await mk(A,"org_full","paused")
    other = await mk(B,"org_full","running")          # different club, must survive
    log=[]; t=asyncio.create_task(live_loop(live, log))
    ck("control: self-heal query WOULD resume club A before the stop", len(await q(RESUME_SQL,o=A))==2)

    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc=await stop_sync.run(str(A)[:8], False, 5)
    ck("dry run exits 0", rc==0)
    st=lambda r: q("SELECT status,control FROM sync_runs WHERE id=:i",i=r)
    dr=[(await st(r))[0] for r in (live,orphan,quick,paused)]
    ck("dry run changed nothing", all(x["status"] in("running","paused") and x["control"] is None for x in dr), dr)

    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc=await stop_sync.run(str(A), True, 4)   # orphan/quick are not polled -> forced after 4s
    out=buf.getvalue(); print(out)
    await asyncio.wait_for(t, 5)
    ck("exit 0", rc==0, rc)
    ck("live loop stopped itself via the real checkpoint", log==["cancel"], log)
    rows={r:(await st(r))[0] for r in (live,orphan,quick,paused,other)}
    ck("live run cancelled", rows[live]["status"]=="cancelled")
    ck("orphan Full Rebuild forced to cancelled", rows[orphan]["status"]=="cancelled")
    ck("non-full kind (org_quick) cancelled too", rows[quick]["status"]=="cancelled")
    ck("paused run cancelled", rows[paused]["status"]=="cancelled")
    ck("forced run keeps control=cancel so a live loop still unwinds", rows[orphan]["control"]=="cancel")
    ck("other club's run untouched", rows[other]["status"]=="running" and rows[other]["control"] is None)
    ck("completed_at stamped", all(r["completed_at"] for r in await q("SELECT completed_at FROM sync_runs WHERE id=ANY(:i)", i=[live,orphan,quick,paused])))
    ck("audit marker in stats", (await q("SELECT stats->>'cancelled_by_script' s, stats->>'cancel_forced' f FROM sync_runs WHERE id=:i",i=orphan))[0]["f"]=="true")
    ck("SELF-HEAL query finds nothing for club A after the stop", len(await q(RESUME_SQL,o=A))==0)
    ck("warns about the Full Rebuild", "WARNING" in out)
    ck("says it is safe to restart", "safe to restart" in out)
    ck("club B still resumable (scope respected)", len(await q(RESUME_SQL,o=B))==1)

    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc=await stop_sync.run(str(A), True, 1)
    ck("second run is a clean no-op", rc==0 and "Nothing to stop" in buf.getvalue())
    with contextlib.redirect_stdout(io.StringIO()):
        rc=await stop_sync.run("nope", True, 1)
    ck("unknown club exits 2", rc==2)
    with contextlib.redirect_stdout(io.StringIO()):
        rc=await stop_sync.run("all", True, 0)
    ck("'all' stops the remaining club", rc==0 and len(await q(RESUME_SQL,o=B))==0)
    await ex("DELETE FROM organisations WHERE id=ANY(:i)", i=[A,B])
    print(f"\n{P} passed, {F} failed")
asyncio.run(main())
