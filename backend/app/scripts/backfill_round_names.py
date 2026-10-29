"""Fill in ``games.round_name`` from Cricket Australia's own fixture list, then write the
premierships it makes visible. One club, or every club.

WHY THIS EXISTS
---------------
Automatic premierships (services/premierships.py) need to know which stored game was a GRAND final.
``games.is_final`` cannot say: it is true of any round whose label contains "final". The label is on
the match-list entry the sync already fetches, so a club's first sync, and every sync after it, stores
``round_name`` for the games it rediscovers (and writes the honours). An incremental run only scans the
seasons still in play, so a club that synced BEFORE this shipped keeps older grand finals unnamed until a
Full Rebuild. This is the cheap way to fill them: one CA call per grade, one small column.

HOW IT KEEPS THE CALL COUNT DOWN
--------------------------------
* Only grades holding a final the club played in with no round name are read.
* A CA grade is competition-wide: every club in it shares ONE match list. With ``all``, each distinct
  grade is fetched once and the answer is used for every club that has a game in it.
* ``--max-grades N`` stops the run before it would fetch more than N grades (default 400), finishing
  whole clubs only. ``--concurrency N`` (default 3, at most 6) reads that many grades at once and
  ``--pause SECONDS`` (default 0.5) is the gap each reader leaves between its own calls, so the call
  rate is about N / (latency + pause). All three bound a single run.
* It resumes by itself: a club whose finals are all named is no longer a candidate, so running it again
  carries on where the last run stopped. Ctrl-C is safe: every club is committed before the next starts.

WHAT IT TOUCHES
---------------
``games.round_name`` for games the club played in (``home_org_id`` / ``away_org_id``), and with
``--premierships`` the club's automatic premiership honours (services/premierships.reconcile), which
adds honours, links hand-typed ones to their scorecard and never removes a hand-typed row. The honours
step is database only. A club that hides its junior programme gets no junior honours.

A dry run still reads from CA (read only) but writes nothing, and cannot preview the honours, because
the names they depend on are not stored yet. Apply the names first, then preview with
``python -m app.scripts.sync_premierships <club>``.

USAGE
-----
    python -m app.scripts.backfill_round_names <org-id-or-slug>                       # dry run
    python -m app.scripts.backfill_round_names <org-id-or-slug> --apply --premierships
    python -m app.scripts.backfill_round_names all                                    # dry run, every club
    python -m app.scripts.backfill_round_names all --apply --premierships --max-grades 400 --concurrency 4
    (run the last one again until it says nothing is left; then `sync_premierships all --apply`)
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services import premierships

DEFAULT_MAX_GRADES = 400
DEFAULT_PAUSE = 0.5
DEFAULT_CONCURRENCY = 3
MAX_CONCURRENCY = 6   # the CA client itself never has more than six calls in flight


async def _clubs(db, org_ref: str) -> list[dict]:
    """The clubs to work on. For ``all``, only those holding a final with no round name yet."""
    if org_ref.lower() == "all":
        rows = (await db.execute(text("""
            SELECT o.id, o.name FROM organisations o
             WHERE o.archived_at IS NULL
               AND o.id IN (
                   SELECT home_org_id FROM games WHERE is_final = TRUE AND round_name IS NULL
                   UNION
                   SELECT away_org_id FROM games WHERE is_final = TRUE AND round_name IS NULL)
             ORDER BY o.name"""))).mappings().all()
        return [dict(r) for r in rows]
    try:
        where, param = "id = CAST(:ref AS UUID)", str(uuid.UUID(org_ref))
    except ValueError:
        where, param = "LOWER(slug) = LOWER(:ref)", org_ref
    row = (await db.execute(
        text(f"SELECT id, name FROM organisations WHERE {where}"), {"ref": param})).mappings().first()
    return [dict(row)] if row else []


async def _grades_needing_names(db, org_id) -> list[dict]:
    """Grades (by raw CA guid) holding a final the club played in with no round name yet."""
    rows = (await db.execute(text("""
        SELECT DISTINCT COALESCE(gr.grassroots_id, CAST(gr.id AS TEXT)) AS guid,
               gr.name AS grade_name, s.name AS season_name
          FROM games g
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
         WHERE g.is_final = TRUE AND g.round_name IS NULL
           AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID))
    """), {"org": str(org_id)})).mappings().all()
    return [dict(r) for r in rows]


class Fetcher:
    """One CA call per distinct grade for the whole run, spaced, with a budget."""

    def __init__(self, max_grades: int, pause: float, concurrency: int = 1):
        self.max_grades, self.pause = max_grades, pause
        self.names: dict[str, str] = {}      # match id -> round label, from every grade read so far
        self.seen: set[str] = set()          # grade guids already read this run
        self.failed: set[str] = set()        # grades CA returned nothing for (blip or empty): retried next run
        self._slots = asyncio.Semaphore(max(1, min(concurrency, MAX_CONCURRENCY)))
        self._tasks: dict[str, asyncio.Task] = {}   # grade guid -> its read, so two askers share one call

    def cost(self, guids) -> int:
        return len({g for g in guids if g not in self.seen})

    async def read(self, gd: dict) -> None:
        """Read one grade. A second asker for the same grade waits for the first read, never makes a call."""
        guid = gd["guid"]
        task = self._tasks.get(guid)
        if task is None:
            self.seen.add(guid)
            task = self._tasks[guid] = asyncio.ensure_future(self._fetch(gd))
        await task

    async def read_all(self, grades: list[dict]) -> None:
        await asyncio.gather(*(self.read(gd) for gd in grades))

    async def _fetch(self, gd: dict) -> None:
        guid = gd["guid"]
        async with self._slots:
            try:
                matches = await gr.get_grade_matches(guid)
            except Exception as e:  # a grade CA no longer serves is not fatal
                print(f"  ! {gd['season_name']} / {gd['grade_name']}: {e}")
                self.failed.add(guid)
                return
            if not matches:
                self.failed.add(guid)
            for m in matches:
                mid, rn = m.get("id"), ((m.get("round") or {}).get("name") or "").strip()
                if mid and rn:
                    self.names[mid] = rn
            await asyncio.sleep(self.pause)   # inside the slot: each worker leaves a gap between its calls


async def run_one(db, org: dict, fetcher: Fetcher, apply: bool, with_premierships: bool) -> dict:
    print(f"\nClub: {org['name']} ({org['id']})")
    grades = await _grades_needing_names(db, org["id"])
    fresh = fetcher.cost(g["guid"] for g in grades)
    print(f"  {len(grades)} grade(s) hold a final with no round name yet"
          f" ({fresh} not already read this run, one CA call each) …")
    await fetcher.read_all(grades)

    ids = []
    for mid in fetcher.names:
        try:
            ids.append(uuid.UUID(mid))
        except ValueError:
            pass
    ours = (await db.execute(text("""
        SELECT id, round_name FROM games
         WHERE id = ANY(:ids)
           AND (home_org_id = CAST(:org AS UUID) OR away_org_id = CAST(:org AS UUID))
    """), {"ids": ids, "org": str(org["id"])})).mappings().all()
    todo = [r["id"] for r in ours
            if fetcher.names.get(str(r["id"])) and r["round_name"] != fetcher.names[str(r["id"])]]
    gf = sum(1 for i in todo if premierships.is_grand_final_round(fetcher.names[str(i)]))
    print(f"  {'Updating' if apply else 'Would update'} {len(todo)} game(s); {gf} of them grand finals.")
    if apply:
        for i in todo:
            await db.execute(text("UPDATE games SET round_name = :rn WHERE id = :id"),
                             {"rn": fetcher.names[str(i)], "id": i})
        await db.commit()
    out = {"games": len(todo), "grand_finals": gf, "create": 0, "wins": 0}
    if with_premierships and apply:
        rep = await premierships.reconcile(db, org["id"], apply=True)
        out["create"], out["wins"] = rep.get("create", 0) or 0, rep.get("wins", 0) or 0
        print("  Premierships:", {k: v for k, v in rep.items() if k not in ("preview", "unresolved")})
    return out


async def run(org_ref: str, apply: bool, with_premierships: bool, max_grades: int, pause: float,
              concurrency: int = DEFAULT_CONCURRENCY) -> int:
    async with async_session_maker() as db:
        clubs = await _clubs(db, org_ref)
        if not clubs:
            if org_ref.lower() == "all":
                print("Every club's finals already have their round names. Nothing to do.")
                return 0
            print(f"No club found for {org_ref!r} (pass an organisation id, public slug, or 'all').")
            return 1

        fetcher = Fetcher(max_grades, pause, concurrency)
        totals = {"games": 0, "grand_finals": 0, "create": 0, "wins": 0}
        done = 0
        try:
            for org in clubs:
                # Whole clubs only: stop BEFORE a club that would take the run over its budget (the first
                # club always runs, so one big club cannot starve the rest forever).
                if done and fetcher.cost(g["guid"] for g in await _grades_needing_names(db, org["id"])) \
                        + len(fetcher.seen) > fetcher.max_grades:
                    break
                try:
                    r = await run_one(db, org, fetcher, apply, with_premierships)
                except Exception as e:  # one club's bad data must not stop the sweep
                    print(f"  ! {org['name']}: {e}")
                    await db.rollback()
                    continue
                done += 1
                for k in totals:
                    totals[k] += r[k]
        except KeyboardInterrupt:
            print("\nStopped. Every club finished so far is saved; run it again to carry on.")

        left = len(clubs) - done
        print(f"\n{'Wrote' if apply else 'Would write'} {totals['games']} round name(s) "
              f"({totals['grand_finals']} grand finals) across {done} of {len(clubs)} club(s); "
              f"{len(fetcher.seen)} grade(s) read from CA, {len(fetcher.failed)} returned nothing.")
        if with_premierships and apply:
            print(f"Premierships: {totals['wins']} grand finals won, {totals['create']} honours added.")
        if left and org_ref.lower() == "all":
            print(f"{left} club(s) not reached because of --max-grades {max_grades}: run it again to carry on.")
        elif fetcher.failed and apply:
            print("Grades CA returned nothing for are tried again next run.")
        if not apply:
            print("Dry run — re-run with --apply to write these.")
        return 0


def _opt(args: list[str], name: str, cast, default):
    if name not in args:
        return default
    i = args.index(name)
    try:
        val = cast(args[i + 1])
    except (IndexError, ValueError):
        print(f"{name} needs a number, e.g. {name} {default}")
        raise SystemExit(2)
    del args[i:i + 2]
    return val


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    with_prem = "--premierships" in args
    max_grades = _opt(args, "--max-grades", int, DEFAULT_MAX_GRADES)
    pause = _opt(args, "--pause", float, DEFAULT_PAUSE)
    concurrency = _opt(args, "--concurrency", int, DEFAULT_CONCURRENCY)
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(positional[0], apply, with_prem, max_grades, pause, concurrency)))


if __name__ == "__main__":
    main()
