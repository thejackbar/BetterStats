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
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import playhq_client
from app.services.competitions import seed_competitions_for_org


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

    seasons = (await db.execute(
        text(
            """
            SELECT s.id, s.name, COALESCE(s.grassroots_id, CAST(s.id AS TEXT)) AS guid,
                   COUNT(gr.id) FILTER (WHERE gr.association_id IS NULL) AS unfilled
              FROM seasons s
              LEFT JOIN grades gr ON gr.season_id = s.id
             WHERE s.organisation_id = CAST(:org AS UUID)
             GROUP BY s.id
            HAVING COUNT(gr.id) FILTER (WHERE gr.association_id IS NULL) > 0
             ORDER BY s.year DESC NULLS LAST
            """
        ),
        {"org": org_id},
    )).mappings().all()

    if not seasons:
        print("  Every grade already carries its association. Nothing to do.")
        filled = 0
    else:
        print(f"  {len(seasons)} season(s) hold a grade with no association.")
        # The CA organisation GUID the API is keyed on. A club's own row id IS
        # that GUID (organisations.id is the CA org id), so no lookup is needed.
        filled = 0
        by_assoc: Counter = Counter()
        for season in seasons:
            teams = await playhq_client.get_teams(org_id, season["guid"])
            # grade GUID -> owningOrganisation, from every grade shape the
            # payload uses (a team carries `grade` and/or `grades`).
            found: dict[str, dict] = {}
            for team in teams:
                candidates = list(team.get("grades") or [])
                if team.get("grade"):
                    candidates.append(team["grade"])
                for grade in candidates:
                    guid = ((grade or {}).get("id") or "").strip()
                    owner = (grade or {}).get("owningOrganisation") or {}
                    if guid and owner.get("id"):
                        found[guid] = owner
            if not found:
                print(f"    {season['name']}: CA reported no association. Left alone.")
                continue
            for guid, owner in found.items():
                by_assoc[owner.get("name") or owner["id"]] += 1
                if not apply:
                    continue
                res = await db.execute(
                    text(
                        """
                        UPDATE grades gr
                           SET association_id = :aid,
                               association_name = COALESCE(:aname, gr.association_name),
                               association_short_name = COALESCE(:ashort, gr.association_short_name)
                          FROM seasons s
                         WHERE s.id = gr.season_id
                           AND s.organisation_id = CAST(:org AS UUID)
                           AND gr.grassroots_id = :guid
                           AND gr.association_id IS DISTINCT FROM :aid
                        """
                    ),
                    {
                        "aid": owner["id"],
                        "aname": (owner.get("name") or "").strip() or None,
                        "ashort": (owner.get("shortName") or "").strip() or None,
                        "org": org_id,
                        "guid": guid,
                    },
                )
                filled += res.rowcount or 0
        for name, count in by_assoc.most_common():
            print(f"    {count:4d} grade(s)  {name}")

    grouped = {}
    if apply:
        await db.commit()
        if group:
            grouped = await seed_competitions_for_org(db, org["id"])
            await db.commit()
            print(
                f"  Grouped: {grouped.get('competitions_created', 0)} competition(s) created, "
                f"{grouped.get('grades_assigned', 0)} grade(s) assigned."
            )
        print(f"  Applied: {filled} grade row(s) updated.")
    else:
        print("  DRY RUN — nothing written. Re-run with --apply.")
    return {"filled": filled, **grouped}


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
