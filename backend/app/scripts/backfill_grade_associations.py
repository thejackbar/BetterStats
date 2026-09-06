"""Fill in ``grades.association_id`` from Cricket Australia's own team list.

WHY THIS EXISTS
---------------
Every grade CA returns carries ``grade.owningOrganisation`` — the association
that runs it — on ``/fixturesladders/organisations/{org}/teams?seasonId=``.
That is the payload the sync already fetches to seed its grades, and it has
been reading only the grade's id and name from it. So the association was
available all along and simply never stored, which is why nothing in the app
could tell a club's WASTCA cricket from its Perth Scorchers Women's League
cricket.

The sync writes it now (``sync._resolve_org_grade``), on new grades AND on
existing ones, so a plain Sync Now fills in the seasons a run still scans.
This script is the retroactive half, for the history an incremental run no
longer reaches — and it is cheap: ONE call per season, not per grade, because
the teams payload carries every grade the club played that year.

**A club admin can now run this themselves**, from the Competitions panel on
Manage Grades, and the work is the same function either way
(``services/competition_grouping.run_grouping``). This script stays as the
operator's way in: it takes ``all``, it has a dry run, and it needs nobody
logged in. Do not reimplement the walk here — a second copy is how the button
and the command line start disagreeing about what grouping means.

Verified live against Applecross's oldest season (Summer 1975/76), so a club's
whole history is reachable. A club onboarded after this shipped has nothing to
fix; its grades get the association at creation.

WHAT IT TOUCHES
---------------
``grades.association_id`` / ``.association_name`` / ``.association_short_name``
for the named club's own grades, and then (unless ``--no-group``) the club's
competition grouping, by running the same skip-don't-replace seeder the sync
runs. It never writes a game, a stat or a grade's name, and it never
overwrites an association already stored with a blank.

Dry run by default, per the house rule — the same posture
``purge_import_only_players`` and ``refile_manual_game_seasons`` take.

USAGE
-----
    python -m app.scripts.backfill_grade_associations <org-id-or-slug>
    python -m app.scripts.backfill_grade_associations <org-id-or-slug> --apply
    python -m app.scripts.backfill_grade_associations all --apply
    python -m app.scripts.backfill_grade_associations <org> --apply --no-group
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import competition_grouping as grouping


async def _orgs(db, org_ref: str) -> list[dict]:
    if org_ref.lower() == "all":
        rows = await db.execute(text(
            "SELECT id, name FROM organisations WHERE archived_at IS NULL ORDER BY name"
        ))
        return [dict(r) for r in rows.mappings().all()]
    try:
        where, param = "id = CAST(:ref AS UUID)", str(uuid.UUID(org_ref))
    except ValueError:
        where, param = "LOWER(slug) = LOWER(:ref)", org_ref
    row = (await db.execute(
        text(f"SELECT id, name FROM organisations WHERE {where}"), {"ref": param}
    )).mappings().first()
    return [dict(row)] if row else []


async def _backfill_org(db, org, apply: bool, group: bool) -> dict:
    org_id = str(org["id"])
    print(f"\nClub: {org['name']} ({org_id})")

    if not apply:
        # A dry run reports the same gap the admin screen reads, so the two
        # can never disagree about how much there is to do.
        gap = await grouping.grouping_gap(db, org["id"])
        print(f"  {gap['seasons_missing']} season(s) hold a grade with no association.")
        print(f"  {gap['grades_ungrouped']} grade name(s) are in no competition.")
        print("  DRY RUN — nothing written. Re-run with --apply.")
        return {"filled": 0}

    async def progress(done: int, total: int, phase: str) -> None:
        if total:
            print(f"  [{done:>3}/{total}] {phase}")

    result = await grouping.run_grouping(
        org["id"], progress=progress, apply=True, group=group,
    )
    print(
        f"  Applied: {result['grades_filled']} grade row(s) updated across "
        f"{result['seasons_checked']} season(s), "
        f"{result['associations_found']} association(s) found."
    )
    if result["seasons_failed"]:
        print(f"  {result['seasons_failed']} season(s) could not be read from CA.")
    if group:
        print(
            f"  Grouped: {result['competitions_created']} competition(s) created, "
            f"{result['grades_assigned']} grade(s) assigned."
        )
    else:
        print("  Grouping skipped (--no-group).")
    return {"filled": result["grades_filled"]}


async def run(org_ref: str, apply: bool, group: bool) -> int:
    async with async_session_maker() as db:
        orgs = await _orgs(db, org_ref)
        if not orgs:
            print(f"No club found for {org_ref!r} (pass an organisation id, slug, or 'all').")
            return 1
        total = 0
        for org in orgs:
            try:
                result = await _backfill_org(db, org, apply, group)
                total += result["filled"]
            except Exception as e:  # one club's CA hiccup must not end the sweep
                await db.rollback()
                print(f"  FAILED for {org['name']}: {e}")
        print(f"\nTotal grade rows {'updated' if apply else 'that would be updated'}: {total}")
        return 0


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    group = "--no-group" not in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(positional[0], apply, group)))


if __name__ == "__main__":
    main()
