from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import re as _re
from pydantic import BaseModel
import uuid
from datetime import date

from app.models.db import Organisation, Season, Grade, User, ClubMembership, get_db
from app.services import playhq_client
from app.services.sync import sync_organisation, upsert_organisation
from app.services.aggregations import get_upcoming_milestones_for_org, get_recently_achieved_milestones_for_org, get_club_summary
from app.services import playhq_partner_client
from app.routers.auth import get_current_user

router = APIRouter(prefix="/organisations", tags=["organisations"])

_org_sync_running: set = set()


def _filter_by_season(games: list, season_obj) -> list:
    name = (season_obj.name or "").strip().lower()
    by_name = [g for g in games if g.get("season", "").strip().lower() == name]
    if by_name:
        return by_name
    year = season_obj.year
    if year:
        return [g for g in games if g.get("played_at", "")[:4] in (str(year), str(year + 1))]
    return []


class OnboardRequest(BaseModel):
    org_id: str
    org_name: str = ""


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    slug: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    logo_url: str | None = None
    hero_image_url: str | None = None
    theme_mode: str | None = None
    theme_config: dict | None = None
    player_name_format: str | None = None

    class Config:
        from_attributes = True


@router.get("/search")
async def search_organisations(q: str = "", _: User = Depends(get_current_user)):
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    return results


@router.post("/onboard", status_code=202)
async def onboard_organisation(
    data: OnboardRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Determine the caller's single club membership / role.
    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = membership_res.scalar_one_or_none()
    is_super = membership is not None and membership.role == "super_admin"

    # A club admin gets one onboard. Once their linked club has data, they're
    # locked out — only a super admin can onboard further clubs.
    if not is_super and membership is not None:
        already = await db.execute(
            text("SELECT 1 FROM seasons WHERE organisation_id = :cid LIMIT 1"),
            {"cid": str(membership.club_id)},
        )
        if already.scalar():
            raise HTTPException(
                status_code=403,
                detail="Your account is already linked to a club. Contact a super admin to onboard another.",
            )

    org_data = await playhq_client.get_organisation(data.org_id)
    if not org_data:
        raise HTTPException(status_code=404, detail="Organisation not found")

    name = data.org_name.strip() or org_data.get("name") or data.org_id
    org_data["name"] = name

    from app.services.sync import start_sync_run
    org = await upsert_organisation(db, org_data)
    run_id = await start_sync_run(org.id, "org_full")
    background_tasks.add_task(_sync_safe, data.org_id, run_id, "org_full")

    # The onboarded club becomes the club admin's linked club.
    if not is_super:
        if membership is not None:
            membership.club_id = org.id
        else:
            db.add(ClubMembership(club_id=org.id, user_id=current_user.id, role="club_admin"))
        await db.commit()

    return {
        "status": "sync_started",
        "org_id": data.org_id,
        "name": name,
        "run_id": str(run_id),
    }


@router.get("", response_model=list[OrganisationOut])
async def list_organisations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organisation).order_by(Organisation.name))
    return result.scalars().all()


@router.get("/{org_id}", response_model=OrganisationOut)
async def get_organisation(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


def _season_sort_key(s):
    m = _re.search(r'[0-9]{4}', s.name or '')
    year = int(m.group()) if m else 0
    order = s.display_order if s.display_order is not None else 999999
    return (order, -year, s.name or '')


def _year_from_name(name):
    m = _re.search(r'[0-9]{4}', name or '')
    return int(m.group()) if m else 0


@router.get("/{org_id}/seasons")
async def get_org_seasons(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Season).where(Season.organisation_id == uuid.UUID(org_id))
    )
    seasons = sorted(result.scalars().all(), key=lambda s: (-_year_from_name(s.name), s.name or ''))
    return [
        {"id": str(s.id), "name": s.name, "year": s.year, "synced_at": s.synced_at}
        for s in seasons
    ]


@router.get("/{org_id}/grades")
async def get_org_grades(
    org_id: str,
    season_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params = {"org_id": org_id}
    season_clause = ""
    if season_id:
        season_clause = "AND g.season_id = CAST(:season_id AS UUID)"
        params["season_id"] = season_id
    result = await db.execute(
        text(f"""
            SELECT display_name FROM (
                SELECT DISTINCT COALESCE(g.display_name_override, g.name) AS display_name
                FROM grades g
                JOIN seasons s ON s.id = g.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {season_clause}
                  AND NOT EXISTS (
                      SELECT 1 FROM grade_merge_logs gml
                      WHERE gml.org_id = CAST(:org_id AS UUID)
                        AND gml.alias_name = g.name
                        AND gml.undone_at IS NULL
                  )
            ) sub
            ORDER BY
                NULLIF(regexp_replace(display_name, '[^0-9].*', ''), '')::int NULLS LAST,
                display_name
        """),
        params,
    )
    return [{"name": row.display_name} for row in result]


@router.get("/{org_id}/seasons/{season_id}/grades")
async def get_season_grades(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Grade)
        .where(Grade.season_id == uuid.UUID(season_id))
        .order_by(text("NULLIF(regexp_replace(grades.name, '[^0-9].*', ''), '')::int NULLS LAST"), Grade.name)
    )
    grades = result.scalars().all()
    if grades:
        seen: set[str] = set()
        out = []
        for g in grades:
            if g.name not in seen:
                seen.add(g.name)
                out.append({"id": str(g.id), "name": g.name})
        return out

    # No grades in DB — try the cheap per-season PlayHQ endpoint (single call per season)
    try:
        api_grades = await playhq_partner_client.get_season_grades(season_id)
        if api_grades:
            def _grade_sort_key(x):
                m = _re.match(r'^(\d+)', x["name"])
                return (int(m.group(1)) if m else float('inf'), x["name"])
            return sorted(
                [{"id": g["id"], "name": g.get("name", "")} for g in api_grades if g.get("id")],
                key=_grade_sort_key,
            )
    except Exception:
        pass
    return []


@router.get("/{org_id}/upcoming-milestones")
async def get_upcoming_milestones(
    org_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    rows = await get_upcoming_milestones_for_org(db, org_id, limit)
    return rows


@router.get("/{org_id}/recently-achieved-milestones")
async def get_recently_achieved_milestones(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    rows = await get_recently_achieved_milestones_for_org(db, org_id)
    return rows


@router.get("/{org_id}/summary")
async def get_org_summary(
    org_id: str,
    season_id: str | None = None,
    grade_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    summary = await get_club_summary(db, org_id, season_id, grade_id)
    org = await db.get(Organisation, uuid.UUID(org_id))
    if org and org.playhq_id:
        db_seasons_res = await db.execute(
            select(Season).where(Season.organisation_id == uuid.UUID(org_id))
        )
        db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
        final = [g for g in all_games if g.get("status") == "FINAL" and g.get("result")]
        if season_id:
            season_obj = await db.get(Season, uuid.UUID(season_id))
            if season_obj:
                final = _filter_by_season(final, season_obj)
        if grade_id:
            grade_obj = await db.get(Grade, uuid.UUID(grade_id))
            if grade_obj:
                final = [g for g in final if (g.get("grade") or {}).get("name", "").strip().lower() == grade_obj.name.strip().lower()]
        wins = sum(1 for g in final if g.get("result") == "WIN")
        losses = sum(1 for g in final if g.get("result") == "LOSS")
        draws = sum(1 for g in final if g.get("result") in ("DRAW", "TIE"))
        total = len(final)
        summary["total_games"] = total
        summary["wins"] = wins
        summary["losses"] = losses
        summary["draws"] = draws
        summary["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0
    return summary


@router.get("/{org_id}/fixtures")
async def get_org_fixtures(org_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch upcoming fixtures from the PlayHQ partner API."""
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        return []

    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == uuid.UUID(org_id))
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    today = date.today()

    upcoming = [
        {
            "id": g["id"],
            "home_team": g["home_team"],
            "away_team": g["away_team"],
            "date": g["played_at"],
            "time": g.get("time"),
            "grade": (g.get("grade") or {}).get("name", ""),
            "season": g.get("season", ""),
            "round": g.get("round"),
            "venue": g.get("venue"),
        }
        for g in all_games
        if g.get("status") != "FINAL" and g.get("played_at") and g["played_at"] >= today.isoformat()
    ]
    upcoming.sort(key=lambda x: (x["date"], x.get("time") or ""))
    return upcoming[:20]


async def _sync_safe(org_id: str, run_id: uuid.UUID, kind: str = "org_full"):
    from app.services.sync import finish_sync_run
    import logging
    try:
        stats = await sync_organisation(org_id, run_id=run_id, kind=kind)
        await finish_sync_run(run_id, stats if isinstance(stats, dict) else {})
    except Exception as exc:
        import traceback
        logging.getLogger(__name__).error(f"Sync crashed for {org_id}: {exc}\n{traceback.format_exc()}")
        await finish_sync_run(run_id, {}, f"Unexpected error: {exc}")
    finally:
        _org_sync_running.discard(org_id)


@router.post("/{org_id}/sync", status_code=202)
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks):
    from app.services.sync import start_sync_run
    if org_id in _org_sync_running:
        return {"status": "already_running", "org_id": org_id}
    org_uuid = uuid.UUID(org_id)
    run_id = await start_sync_run(org_uuid, "org_full")
    _org_sync_running.add(org_id)
    background_tasks.add_task(_sync_safe, org_id, run_id, "org_full")
    return {"status": "sync_started", "org_id": org_id, "run_id": str(run_id)}


@router.get("/{org_id}/results")
async def get_org_results(
    org_id: str,
    season_id: str | None = None,
    grade_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return all synced game results for the org from the DB, grouped-friendly flat list."""
    # Use org name (first word) to filter to games where our club is one of the teams.
    # Old syncs stored all games in a grade (including non-org games); this removes those.
    org = await db.get(Organisation, uuid.UUID(org_id))
    org_word = (org.name or "").split()[0] if org and org.name else ""

    query = """
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.winning_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name,
               gr.id AS grade_id,
               s.id AS season_id, s.name AS season_name
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id}

    if org_word:
        query += " AND (g.home_team ILIKE :org_pat OR g.away_team ILIKE :org_pat)"
        params["org_pat"] = f"%{org_word}%"
    if season_id:
        query += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        query += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    query += " ORDER BY g.played_at DESC"
    rows = await db.execute(text(query), params)
    return [
        {
            "id": str(r.id),
            "played_at": r.played_at.isoformat() if r.played_at else None,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "result": r.result,
            "winning_team": r.winning_team,
            "grade_name": r.grade_name,
            "grade_id": str(r.grade_id),
            "season_id": str(r.season_id),
            "season_name": r.season_name,
        }
        for r in rows
    ]


@router.get("/{org_id}/sync-logs")
async def get_sync_logs(org_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.db import SyncRun
    org_uuid = uuid.UUID(org_id)
    res = await db.execute(
        select(SyncRun)
        .where(SyncRun.org_id == org_uuid)
        .order_by(SyncRun.started_at.desc())
        .limit(30)
    )
    runs = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "stats": r.stats or {},
            "error": r.error,
        }
        for r in runs
    ]
