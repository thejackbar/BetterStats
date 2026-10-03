"""Stop a sync that is running right now, and make sure it stays stopped.

WHY THIS EXISTS
---------------
The All Clubs page can Pause or Cancel a club's Full Sync, but only for the two
full kinds and only from the browser. This works on ANY kind of run (Sync Now,
Quick Sync, the scheduled results sync, Full Rebuild, player deep sync) from the
server shell, which is what you want when a sync is hammering Cricket Australia
or the box and you would rather not wait for a page to load.

HOW IT STOPS A RUN
------------------
A sync runs inside the backend process; this script is a different process, so
it cannot cancel the coroutine directly. A live run polls ``sync_runs.control``
at its checkpoints (per season, per few dozen games: ``_check_sync_control``),
and on ``cancel`` finalises itself and unwinds. So:

  1. Every run that is ``running`` gets ``control = 'cancel'``.
  2. The script waits (``--wait``, default 90s) for each run to honour it.
  3. A run that has not stopped by then (stuck in one long upstream call, or an
     orphan whose process is already gone) is forced to ``cancelled`` in the
     database. ``control`` is left at ``cancel`` on a forced run, so a live
     loop that is still going stops at its next checkpoint instead of carrying
     on behind a row that says it has finished.
  4. A run that is ``paused`` has nothing alive to signal and is cancelled
     straight away.

WHY IT DOES NOT RESTART
-----------------------
The thing that restarts a sync is the startup self-heal in ``main.py``: on boot
it finds every ``org_full`` / ``org_hard_refresh`` row still ``status =
'running'``, marks it errored and starts a brand-new run for that club. So the
rule is simple: the row must be ``cancelled`` BEFORE the backend is restarted.
This script does not return success until no run for the club is left
``running``, and it prints a clear line when it is safe to restart.

WHAT IT DOES NOT DO
-------------------
  · It does not touch the schedule. The Sunday and Monday 01:00 Perth job will
    still sync this club next time round, which is usually what you want (a
    cancelled run never moves the watermark, so that run re-covers the gap).
    If a club must not sync at all, deactivate it, which is a separate decision.
  · With ``all`` while the weekly job is mid-loop, the job moves on to the next
    club once this one is cancelled. The final sweep reports anything that has
    started since; to stop the whole job, stop it at the source.
  · It never deletes a row. Cancelled runs stay in Sync History.

CANCELLING A FULL REBUILD
-------------------------
A Full Rebuild wipes the club's stored games BEFORE it re-pulls them. Cancelling
it part way leaves the club with a partial history, and the scheduled sync only
looks at recent fixtures, so it will not fill the rest. The script warns when it
is about to cancel one. Run Sync Now (or a new Full Rebuild) afterwards.

USAGE  (from /srv/docker, on the server)
-----
    docker compose exec betterstats-backend python -m app.scripts.stop_sync <org-id-or-slug|all>            # dry run
    docker compose exec betterstats-backend python -m app.scripts.stop_sync <org-id-or-slug|all> --apply
    docker compose exec betterstats-backend python -m app.scripts.stop_sync <org-id-or-slug|all> --apply --wait 20
    docker compose exec betterstats-backend python -m app.scripts.stop_sync <org-id-or-slug|all> --apply --wait 0   # force now
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.models.db import async_session_maker

POLL_SECONDS = 3

_FIND_SQL = """
    SELECT r.id, r.org_id, o.name AS org_name, r.kind, r.status, r.control,
           r.started_at, r.stats->>'progress_phase' AS phase
    FROM sync_runs r
    JOIN organisations o ON o.id = r.org_id
    WHERE r.status IN ('running', 'paused')
      {org_filter}
    ORDER BY o.name, r.started_at
"""


async def _resolve_org(db, org_ref: str):
    try:
        org_id = str(uuid.UUID(org_ref))
        where, param = "id = CAST(:ref AS UUID)", org_id
    except ValueError:
        where, param = "LOWER(slug) = LOWER(:ref)", org_ref
    return (await db.execute(
        text(f"SELECT id, name FROM organisations WHERE {where}"), {"ref": param},
    )).mappings().first()


async def _find_runs(org_id) -> list[dict]:
    flt = "AND r.org_id = CAST(:org AS UUID)" if org_id else ""
    async with async_session_maker() as db:
        rows = (await db.execute(
            text(_FIND_SQL.format(org_filter=flt)), {"org": str(org_id)} if org_id else {},
        )).mappings().all()
    return [dict(r) for r in rows]


def _describe(r: dict) -> str:
    since = r["started_at"].strftime("%Y-%m-%d %H:%M UTC") if r["started_at"] else "?"
    extra = f", {r['phase']}" if r.get("phase") else ""
    pending = f", control={r['control']}" if r.get("control") else ""
    return f"{r['org_name']}: {r['kind']} [{r['status']}] since {since}{extra}{pending}  (run {r['id']})"


def _patch(forced: bool) -> str:
    return json.dumps({
        "cancelled_by_script": "stop_sync",
        "cancelled_at": datetime.now(timezone.utc).isoformat(),
        **({"cancel_forced": True} if forced else {}),
    })


async def _signal_cancel(run_id) -> None:
    async with async_session_maker() as db:
        await db.execute(text(
            "UPDATE sync_runs SET control = 'cancel', updated_at = now() "
            "WHERE id = :id AND status = 'running'"), {"id": run_id})
        await db.commit()


async def _cancel_now(run_id, statuses: tuple[str, ...], forced: bool) -> int:
    """Flip a run to the terminal 'cancelled' state in the database.

    ``control`` is deliberately left alone: on a forced run it stays 'cancel'
    so a live loop that is still going notices at its next checkpoint and
    unwinds; on a paused run it is already NULL."""
    async with async_session_maker() as db:
        res = await db.execute(text(
            "UPDATE sync_runs SET status = 'cancelled', completed_at = now(), updated_at = now(), "
            "stats = (COALESCE(stats::jsonb, '{}'::jsonb) || CAST(:patch AS jsonb))::json "
            "WHERE id = :id AND status = ANY(:statuses)"),
            {"id": run_id, "patch": _patch(forced), "statuses": list(statuses)})
        await db.commit()
        return res.rowcount or 0


async def _still_running(ids: list) -> list:
    if not ids:
        return []
    async with async_session_maker() as db:
        rows = (await db.execute(
            text("SELECT id FROM sync_runs WHERE id = ANY(:ids) AND status = 'running'"),
            {"ids": ids})).all()
    return [r[0] for r in rows]


async def run(org_ref: str, apply: bool, wait: int) -> int:
    org_id = None
    if org_ref.lower() != "all":
        async with async_session_maker() as db:
            org = await _resolve_org(db, org_ref)
        if not org:
            print(f"No club matches {org_ref!r}.")
            return 2
        org_id = org["id"]
        print(f"Club: {org['name']} ({org['id']})")
    else:
        print("Scope: every club")

    runs = await _find_runs(org_id)
    if not runs:
        print("No running or paused sync found. Nothing to stop.")
        return 0

    print(f"\n{len(runs)} sync run(s) to stop:")
    for r in runs:
        print("  - " + _describe(r))
    rebuilds = [r for r in runs if r["kind"] == "org_hard_refresh"]
    if rebuilds:
        print("\nWARNING: cancelling a Full Rebuild part way leaves the club with a partial history "
              "(it wipes stored games before re-pulling). Run Sync Now or a new Full Rebuild afterwards:")
        for r in rebuilds:
            print(f"  - {r['org_name']}")

    if not apply:
        print("\nDry run. Nothing changed. Re-run with --apply to stop them.")
        return 0

    running = [r for r in runs if r["status"] == "running"]
    paused = [r for r in runs if r["status"] == "paused"]

    for r in paused:
        await _cancel_now(r["id"], ("paused",), forced=False)
        print(f"Cancelled paused run for {r['org_name']}.")
    for r in running:
        await _signal_cancel(r["id"])
    if running:
        print(f"\nCancel requested for {len(running)} running run(s). "
              f"Waiting up to {wait}s for them to stop at their next checkpoint...")

    pending = [r["id"] for r in running]
    waited = 0
    while pending and waited < wait:
        await asyncio.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        pending = await _still_running(pending)
    stopped_cleanly = len(running) - len(pending)
    if running:
        print(f"{stopped_cleanly} run(s) stopped by themselves.")

    for rid in pending:
        n = await _cancel_now(rid, ("running",), forced=True)
        if n:
            print(f"Forced run {rid} to cancelled (it had not reached a checkpoint). "
                  "If it is still alive it will stop at its next one.")

    # Final sweep: nothing may be left 'running', or the startup self-heal
    # would resume it on the next boot. Anything new here started while we
    # were working (for example the weekly job moving on to the next club).
    left = await _find_runs(org_id)
    left_running = [r for r in left if r["status"] == "running"]
    if left_running:
        print("\nStill running after the sweep (started since, or not stopped):")
        for r in left_running:
            print("  - " + _describe(r))
        print("Run the script again. Do NOT restart the backend until this list is empty: "
              "startup resumes any run still marked running.")
        return 1

    print("\nDone. No sync is running" + (f" for this club" if org_id else "") +
          ". It is safe to restart the backend now: startup only resumes runs still marked "
          "'running', and these are 'cancelled'.")
    print("The scheduled sync (Sun and Mon 01:00 Perth) is untouched and will pick this club up as normal.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Stop a running sync and keep it stopped.")
    ap.add_argument("org", help="club id, club slug, or 'all'")
    ap.add_argument("--apply", action="store_true", help="actually stop the runs (default is a dry run)")
    ap.add_argument("--wait", type=int, default=90,
                    help="seconds to let a live run stop itself before forcing it (default 90, 0 = force now)")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.org, args.apply, max(0, args.wait))))


if __name__ == "__main__":
    main()
