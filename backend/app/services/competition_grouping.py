"""Grouping a club's older seasons into the competitions it has named.

WHAT THIS IS FOR
----------------
A competition is a named group of a club's grades (see ``competitions.py`` for
why it cannot be synced). Grades are grouped automatically by the ASSOCIATION
Cricket Australia names on each one, which the sync writes as it goes.

That leaves a real gap on every established club. An incremental sync only
scans the seasons that could still have been in play, so a club's older
seasons carry grades with no association at all, and a grade with no
association cannot be put in a competition. The club then does its own work on
Manage Grades, renaming a group or splitting one association into the
competitions it actually runs, and the seasons before that window stay
outside all of it.

Nothing is wrong with those matches. They still count in every unfiltered
figure and they show under "Other grades". They simply cannot be found under a
competition, which is exactly what an admin has just finished setting up. So
the club is told, and offered the one job that closes it.

THE JOB IS THE SCRIPT, AND THE SCRIPT IS THIS
---------------------------------------------
``app/scripts/backfill_grade_associations.py`` and the admin button both call
:func:`run_grouping`. One implementation, per the house rule: two copies of
"fill in the associations and re-seed" is how the button and the script start
disagreeing about what grouping means.

It is ONE Cricket Australia call per season, not per grade, because the teams
payload carries every grade the club played that year. An established club with
fifty seasons is fifty calls, which is why this is a background job with a
progress bar rather than something that happens inside a request.

IT IS SAFE TO RUN TWICE, AND THAT IS LOAD-BEARING
--------------------------------------------------
Only a grade with NO association is written, an association CA omits never
erases one we hold, and the seeder is skip-don't-replace, so a competition the
club has renamed or split keeps its own naming. A second run over a finished
club writes nothing. That is what lets the button be offered without a warning
attached to it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import async_session_maker
from app.services import playhq_client
from app.services.competitions import seed_competitions_for_org

logger = logging.getLogger(__name__)

# The sync_runs kind this job writes. Deliberately NOT one of the two kinds
# main.py's restart self-heal resumes: this job is cheap, idempotent and
# re-runnable from a button, so a run cut off by a deploy is better finalised
# as errored and started again than silently resumed behind the admin's back.
# It is also not in club_admin._FULL_SYNC_KINDS, so it can never read as the
# full historical sync the Setup Wizard waits on.
RUN_KIND = "competition_grouping"


async def grouping_gap(db: AsyncSession, org_id) -> dict:
    """What is still outside the club's competitions, and is it worth saying.

    ``seasons_missing`` is the count this job can actually act on: seasons
    holding a grade Cricket Australia has never told us the association for.
    ``grades_ungrouped`` is the wider count of grade names in no competition,
    which includes grades an admin has deliberately left out, so it is
    reported for context and never used as the trigger on its own.
    """
    row = (await db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(DISTINCT s.id)
                 FROM seasons s
                 JOIN grades gr ON gr.season_id = s.id
                WHERE s.organisation_id = CAST(:org AS UUID)
                  AND gr.association_id IS NULL)                AS seasons_missing,
              (SELECT COUNT(DISTINCT gr.name)
                 FROM grades gr
                 JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org AS UUID)
                  AND gr.competition_id IS NULL)                AS grades_ungrouped,
              (SELECT COUNT(*)
                 FROM club_competitions
                WHERE organisation_id = CAST(:org AS UUID))     AS competitions,
              (SELECT COUNT(*)
                 FROM club_competitions
                WHERE organisation_id = CAST(:org AS UUID)
                  AND is_seeded = false)                        AS competitions_edited
            """
        ),
        {"org": str(org_id)},
    )).mappings().first()

    seasons_missing = int(row["seasons_missing"] or 0)
    competitions = int(row["competitions"] or 0)
    return {
        "seasons_missing": seasons_missing,
        "grades_ungrouped": int(row["grades_ungrouped"] or 0),
        "competitions": competitions,
        # True where the club has named or split a competition itself. It is
        # what makes the prompt worth showing: an admin who has just set their
        # competitions up is the one who cares that older seasons are outside
        # them.
        "competitions_edited": int(row["competitions_edited"] or 0) > 0,
        # The one field a screen needs. Nothing to fetch means nothing to
        # offer, whatever else is true — a button that would write nothing is
        # worse than no button.
        "needs_grouping": seasons_missing > 0,
    }


async def running_run_id(db: AsyncSession, org_id) -> Optional[str]:
    """The club's in-flight grouping run, if it has one.

    One at a time per club: two runs would fetch the same seasons twice and
    race each other's writes for no benefit. A screen reconnecting after a
    reload picks the live run back up from here rather than starting another.
    """
    row = (await db.execute(
        text(
            "SELECT id FROM sync_runs WHERE org_id = CAST(:org AS UUID)"
            " AND kind = :kind AND status = 'running'"
            " ORDER BY started_at DESC LIMIT 1"
        ),
        {"org": str(org_id), "kind": RUN_KIND},
    )).first()
    return str(row[0]) if row else None


def _associations_from_teams(teams: list) -> dict:
    """``{grade guid: owningOrganisation}`` from a season's teams payload.

    A team carries its grade as ``grade`` and/or ``grades``, so both shapes are
    read. A grade CA reports without an owning organisation is skipped rather
    than stored blank.
    """
    found: dict[str, dict] = {}
    for team in teams or []:
        candidates = list(team.get("grades") or [])
        if team.get("grade"):
            candidates.append(team["grade"])
        for grade in candidates:
            guid = ((grade or {}).get("id") or "").strip()
            owner = (grade or {}).get("owningOrganisation") or {}
            if guid and owner.get("id"):
                found[guid] = owner
    return found


async def run_grouping(
    org_id,
    run_id: Optional[uuid.UUID] = None,
    *,
    progress=None,
    apply: bool = True,
    group: bool = True,
) -> dict:
    """Fill in the missing associations, then group what that unlocks.

    Runs on its OWN session, because the caller is a background task whose
    request session is long gone by the time this starts. ``progress`` is an
    optional ``(done, total, phase)`` callback so the admin button can draw a
    bar and the command-line script can print; neither is required.

    ``group=False`` fills the associations in and stops, for an operator who
    wants the raw data without touching a club's own competition naming. The
    button never passes it — an association nothing is grouped by leaves the
    club exactly where it started.

    Returns the counts a screen reports back. Never raises for one season's CA
    hiccup: that season is counted as failed and the rest of the club is still
    grouped, which is a better outcome than an all-or-nothing job that a flaky
    upstream can stop halfway.
    """
    org_id_str = str(org_id)
    filled = 0
    failed = 0
    seen_associations: set[str] = set()

    async with async_session_maker() as db:
        seasons = (await db.execute(
            text(
                """
                SELECT s.id, s.name,
                       COALESCE(s.grassroots_id, CAST(s.id AS TEXT)) AS guid
                  FROM seasons s
                  JOIN grades gr ON gr.season_id = s.id
                 WHERE s.organisation_id = CAST(:org AS UUID)
                   AND gr.association_id IS NULL
                 GROUP BY s.id
                 ORDER BY s.year DESC NULLS LAST
                """
            ),
            {"org": org_id_str},
        )).mappings().all()

        total = len(seasons)
        if progress:
            await progress(0, total, "Reading seasons")

        for index, season in enumerate(seasons, start=1):
            try:
                teams = await playhq_client.get_teams(org_id_str, season["guid"])
                found = _associations_from_teams(teams)
                if apply:
                    for guid, owner in found.items():
                        seen_associations.add(owner["id"])
                        res = await db.execute(
                            text(
                                """
                                UPDATE grades gr
                                   SET association_id = :aid,
                                       association_name = COALESCE(:aname, gr.association_name),
                                       association_short_name =
                                           COALESCE(:ashort, gr.association_short_name)
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
                                "org": org_id_str,
                                "guid": guid,
                            },
                        )
                        filled += res.rowcount or 0
                    await db.commit()
            except Exception as e:  # one season's upstream hiccup is not the job
                await db.rollback()
                failed += 1
                logger.warning(
                    "Competition grouping: season %s failed for %s: %s",
                    season["name"], org_id_str, e,
                )
            if progress:
                await progress(index, total, f"Season {season['name']}")

        grouped = {"competitions_created": 0, "grades_assigned": 0}
        if apply and group:
            if progress:
                await progress(total, total, "Grouping grades")
            grouped = await seed_competitions_for_org(db, org_id)
            await db.commit()

    return {
        "seasons_checked": total,
        "seasons_failed": failed,
        "grades_filled": filled,
        "associations_found": len(seen_associations),
        **grouped,
    }


async def run_grouping_job(org_id, run_id: uuid.UUID) -> None:
    """The background task behind the admin button.

    Owns the sync_run row end to end: progress while it works, a final status
    either way. A failure is recorded on the run rather than raised into a
    task nobody is awaiting, which is what lets the screen say what went wrong
    instead of spinning.
    """
    from app.services.sync import finish_sync_run, update_sync_run

    async def progress(done: int, total: int, phase: str) -> None:
        await update_sync_run(run_id, {
            "progress_phase": phase,
            # A club with nothing to fetch still reaches 100 rather than
            # dividing by zero and drawing an empty bar forever.
            "progress_pct": 100 if not total else round(done * 100 / total),
            "progress_done": done,
            "progress_total": total,
        })

    try:
        stats = await run_grouping(org_id, run_id, progress=progress)
        await finish_sync_run(run_id, stats)
    except Exception as e:
        logger.exception("Competition grouping failed for %s", org_id)
        await finish_sync_run(run_id, {}, error=str(e)[:500])
