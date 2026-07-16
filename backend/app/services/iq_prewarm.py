"""BetterIQ — bulk pre-warm of opposition dossiers (the Setup Wizard's IQ step).

Dossiers normally build one at a time, on demand, the first time a scout opens
an opponent (10–40s each, cached 7 days — see iq_opponent.py). This service
lets a club build every known opponent's dossier for a chosen set of grades up
front, so Opposition Scout feels instant from the first visit.

Politeness first: opponents are built strictly ONE AT A TIME (each build
already fans out its own bounded scorecard fetches through the shared
grassroots client semaphore), the opponent list is capped, and there's at most
one prewarm running per club. Progress lives in an in-process dict — same
posture as the sync governor / hard-refresh locks; a restart simply forgets an
in-flight prewarm, and re-running is cheap because already-fresh dossiers
return as cache hits instantly.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import OppositionDossier, async_session_maker
from app.services import iq_opponent

logger = logging.getLogger(__name__)

MAX_OPPONENTS = 40          # hard cap per prewarm run (CA-proxy politeness)
BUILD_TIMEOUT_SEC = 300     # give up waiting on one dossier after 5 minutes
POLL_INTERVAL_SEC = 5

# org_id (str) → progress dict. In-process only (single backend container).
_STATE: dict[str, dict] = {}
_TASKS: set = set()

# The latest season year's grades, with how many distinct opponents each holds.
_GRADES_SQL = text("""
    SELECT gr.id::text AS id, gr.name AS name, s.name AS season_name,
           COUNT(DISTINCT COALESCE(g.opp_org_id, NULLIF(g.opp_club_name, ''))) AS opponents
    FROM grades gr
    JOIN seasons s ON s.id = gr.season_id
    LEFT JOIN v_effective_games g ON g.grade_id = gr.id
    WHERE s.organisation_id = CAST(:org_id AS UUID)
      AND s.year = (SELECT MAX(year) FROM seasons
                    WHERE organisation_id = CAST(:org_id AS UUID) AND year IS NOT NULL)
    GROUP BY gr.id, gr.name, s.name
    ORDER BY COUNT(DISTINCT COALESCE(g.opp_org_id, NULLIF(g.opp_club_name, ''))) DESC, gr.name
""")

# Distinct opponents across the chosen grades, most recently met first.
_OPPONENTS_SQL = text("""
    SELECT COALESCE(g.opp_org_id, g.opp_club_name) AS opp_key,
           mode() WITHIN GROUP (ORDER BY g.opp_club_name) AS name,
           MAX(g.played_at) AS last_played
    FROM v_effective_games g
    JOIN grades gr ON gr.id = g.grade_id
    JOIN seasons s ON s.id = gr.season_id
    WHERE s.organisation_id = CAST(:org_id AS UUID)
      AND gr.id IN :grade_ids
      AND g.opp_club_name IS NOT NULL AND g.opp_club_name <> ''
    GROUP BY COALESCE(g.opp_org_id, g.opp_club_name)
    ORDER BY MAX(g.played_at) DESC NULLS LAST
""").bindparams(bindparam("grade_ids", expanding=True))


async def options(session: AsyncSession, org_id: str) -> dict:
    """Grade picker data for the wizard step: the latest season's grades with
    opponent counts, plus whether a prewarm is already running."""
    rows = (await session.execute(_GRADES_SQL, {"org_id": org_id})).mappings().all()
    grades = [dict(r) for r in rows]
    # "Top 3" default: the three grades with the most opponents (i.e. the most
    # active competitions) — the admin can tick differently.
    suggested = [g["id"] for g in grades if g["opponents"] > 0][:3]
    return {"grades": grades, "suggested": suggested, **status(org_id)}


def status(org_id: str) -> dict:
    st = _STATE.get(str(org_id))
    return dict(st) if st else {"status": "idle"}


async def start(session: AsyncSession, org_id: str, grade_ids: list[str]) -> dict:
    """Kick off a background prewarm over the chosen grades. No-op (returns the
    live progress) if one is already running for this club."""
    org_id = str(org_id)
    st = _STATE.get(org_id)
    if st and st.get("status") == "running":
        return dict(st)

    gids = []
    for g in grade_ids or []:
        try:
            gids.append(uuid.UUID(str(g)))
        except (ValueError, TypeError):
            continue
    grade_ids = gids[:20]
    if not grade_ids:
        return {"status": "idle", "detail": "Pick at least one grade."}

    rows = (await session.execute(
        _OPPONENTS_SQL, {"org_id": org_id, "grade_ids": grade_ids}
    )).mappings().all()
    opponents = [{"opp_key": r["opp_key"], "name": r["name"]} for r in rows][:MAX_OPPONENTS]
    if not opponents:
        return {"status": "idle", "detail": "No opponents found in those grades yet — run this after your first sync."}

    _STATE[org_id] = {
        "status": "running", "total": len(opponents), "done": 0,
        "current": opponents[0]["name"], "results": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    task = asyncio.create_task(_run(org_id, opponents))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return dict(_STATE[org_id])


async def _dossier_status(org_id: str, opp_key: str) -> str | None:
    async with async_session_maker() as session:
        row = (await session.execute(
            select(OppositionDossier.status).where(
                OppositionDossier.organisation_id == org_id,
                OppositionDossier.opp_key == opp_key,
            ).limit(1)
        )).scalar_one_or_none()
        return row


async def _run(org_id: str, opponents: list[dict]) -> None:
    """Sequentially build (or cache-hit) each opponent's dossier."""
    st = _STATE[org_id]
    try:
        for opp in opponents:
            st["current"] = opp["name"]
            outcome = "error"
            try:
                async with async_session_maker() as session:
                    res = await iq_opponent.get_or_start_dossier(
                        session, org_id, opp["opp_key"], opp_name=opp["name"]
                    )
                if res.get("status") == "ready":
                    outcome = "ready"
                else:
                    # Poll the cache row until the detached build lands.
                    waited = 0
                    while waited < BUILD_TIMEOUT_SEC:
                        await asyncio.sleep(POLL_INTERVAL_SEC)
                        waited += POLL_INTERVAL_SEC
                        dstatus = await _dossier_status(org_id, opp["opp_key"])
                        if dstatus in ("ready", "error"):
                            outcome = dstatus
                            break
                    else:
                        outcome = "timeout"
            except Exception as e:  # one bad opponent never stops the run
                logger.exception(f"IQ prewarm: build failed for org={org_id} opp={opp['opp_key']}: {e}")
            st["results"].append({"name": opp["name"], "status": outcome})
            st["done"] += 1
        st["status"] = "done"
        st["current"] = None
    except Exception as e:
        logger.exception(f"IQ prewarm: run failed for org={org_id}: {e}")
        st["status"] = "error"
        st["error"] = str(e)[:300]
