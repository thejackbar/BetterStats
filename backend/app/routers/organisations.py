import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
import re as _re
from pydantic import BaseModel
import uuid

from app.models.db import Organisation, Season, Grade, User, ClubMembership, MarketingClub, get_db
from app.services import playhq_client
from app.services.sync import sync_organisation, upsert_organisation
from app.services.aggregations import get_upcoming_milestones_for_org, get_recently_achieved_milestones_for_org, get_club_summary
from app.services.fixtures_source import org_grassroots_fixtures
from app.services.season_aliases import resolve_season_filter
from app.routers.auth import get_current_user, get_optional_user, user_can_view_org_private
from app.auth.capabilities import require_cap, RUN_SYNC

router = APIRouter(prefix="/organisations", tags=["organisations"])

_org_sync_running: set = set()
_background_tasks: set = set()
logger = logging.getLogger(__name__)


def _push_club_to_twenty(org_id) -> None:
    """Fire-and-forget: push one club's Company fields to Twenty. No-op when
    Twenty isn't configured; never raises into the request (mirrors
    club_admin.py's identical helper — kept local since routers don't share
    request-scoped helpers)."""
    async def _run():
        try:
            from app.services import twenty_sync
            await twenty_sync.push_org_company(org_id)
        except Exception:
            logger.exception("twenty push failed")
    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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


async def _onboard_club_core(
    db: AsyncSession, background_tasks: BackgroundTasks, org_id: str, org_name: str = "",
) -> tuple[Organisation, uuid.UUID, str]:
    """Create/upsert the club, kick off its first full sync, and best-effort
    link + push its Marketing Directory row — the part of onboarding that's
    identical regardless of who's attaching to it afterwards: an already-
    authenticated user (onboard_organisation, below) or a brand-new one
    created in the same breath (self-serve trial registration,
    routers/self_serve_trial.py). Deliberately does NOT touch club membership
    — callers attach the user themselves, since that part genuinely differs
    (an existing user vs. a new one; a super admin is never attached at all).

    NOTE on atomicity: upsert_organisation commits internally (pre-existing
    behaviour, out of scope to change here — it's used elsewhere too). That
    commit durably commits the *whole* session, including anything the caller
    added earlier but hasn't committed yet. Callers that need "nothing exists
    until everything succeeds" should do their own pre-org-creation writes
    (e.g. a new User row) as flush-only before calling this, and treat
    anything after this call's return as no longer cleanly rollback-able."""
    org_data = await playhq_client.get_organisation(org_id)
    if not org_data:
        raise HTTPException(status_code=404, detail="Organisation not found")

    name = org_name.strip() or org_data.get("name") or org_id
    org_data["name"] = name

    from app.services.sync import start_sync_run
    org = await upsert_organisation(db, org_data)
    run_id = await start_sync_run(org.id, "org_full")
    # Same in-memory guard trigger_sync uses, so an admin who clicks "Sync
    # Now" on this club while its own first sync is still running gets
    # "already_running" instead of a second sync racing the first.
    _org_sync_running.add(org_id)
    background_tasks.add_task(_sync_safe, org_id, run_id, "org_full")

    # Link this now-synced org back to its Marketing Directory row immediately —
    # otherwise the link only happens the next time the directory crawler
    # revisits this club (club_directory._link_existing_org), which could be
    # days away. Same matching priority (PlayHQ id, then name), reversed to look
    # up FROM the org. Best-effort: a club that isn't in the directory at all is
    # a normal no-op. Pushing to Twenty now (rather than waiting for the nightly
    # refresh) is what makes "we synced the club" show up in the CRM lifecycle/
    # engagement score right away.
    mc = await db.scalar(
        select(MarketingClub).where(MarketingClub.existing_org_id.is_(None),
                                    MarketingClub.playhq_id == org_id))
    if mc is None:
        mc = await db.scalar(
            select(MarketingClub).where(MarketingClub.existing_org_id.is_(None),
                                        func.lower(MarketingClub.name) == name.lower()))
    if mc is not None:
        mc.existing_org_id = org.id
        await db.commit()
        _push_club_to_twenty(org.id)

    return org, run_id, name


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

    org, run_id, name = await _onboard_club_core(db, background_tasks, data.org_id, data.org_name)

    # The onboarded club becomes the club admin's linked club.
    if not is_super:
        if membership is not None:
            membership.club_id = org.id
        else:
            db.add(ClubMembership(club_id=org.id, user_id=current_user.id, role="club_admin"))
        await db.flush()
        # The first admin of a club is its primary/owner admin.
        from app.services.memberships import ensure_primary_admin
        await ensure_primary_admin(db, org.id)
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
    from app.services.season_aliases import load_active_alias_map, load_reverse_alias_map

    result = await db.execute(
        select(Season).where(Season.organisation_id == uuid.UUID(org_id))
    )
    all_seasons = list(result.scalars().all())
    alias_map = await load_active_alias_map(db, org_id)
    reverse_map = await load_reverse_alias_map(db, org_id)
    name_by_id = {str(s.id): s.name for s in all_seasons}

    # Hide rows that are currently merged into another season.
    canonical_seasons = [s for s in all_seasons if str(s.id) not in reverse_map]
    canonical_seasons.sort(key=lambda s: (-_year_from_name(s.name), s.name or ''))

    out = []
    for s in canonical_seasons:
        aliases = [
            {"id": aid, "name": name_by_id.get(aid, "")}
            for aid in alias_map.get(str(s.id), [])
        ]
        out.append({
            "id": str(s.id),
            "name": s.name,
            "year": s.year,
            "synced_at": s.synced_at,
            "aliases": aliases,
        })
    return out


@router.get("/{org_id}/grades")
async def get_org_grades(
    org_id: str,
    season_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    params = {"org_id": org_id}
    season_clause = ""
    if season_id:
        # A club's real-world season can be split across several Season rows
        # (one per competition/grassroots season GUID — e.g. an Over 60s comp
        # reports under a different season id than the mainline grades even
        # though it's "the same year"), so scope to every season row sharing
        # the picked season's year/aliases, not just its exact id.
        season_ids = await resolve_season_filter(db, org_id, season_id)
        season_clause = "AND g.season_id = ANY(:season_ids)"
        params["season_ids"] = season_ids
    # Public callers only see grades the club shares; its own admins see all.
    public_clause = ""
    if not await user_can_view_org_private(db, viewer, org_id):
        public_clause = "AND g.is_public IS NOT FALSE"
    result = await db.execute(
        text(f"""
            SELECT display_name FROM (
                SELECT DISTINCT COALESCE(gdn.display_name_override, am.canonical_name, g.name) AS display_name
                FROM grades g
                JOIN seasons s ON s.id = g.season_id
                LEFT JOIN LATERAL (
                    -- A grade merge renames an alias (e.g. CA's newer "Men's
                    -- First Grade") to a canonical name (e.g. "1st Grade") for
                    -- continuity of records. Map aliased rows to their
                    -- canonical name rather than dropping them, or a season
                    -- whose grade row only exists under the alias name (like
                    -- the current one, post CA rename) loses the grade
                    -- entirely instead of showing it under its canonical name.
                    SELECT canonical_name FROM grade_merge_logs gml
                    WHERE gml.org_id = CAST(:org_id AS UUID)
                      AND gml.alias_name = g.name
                      AND gml.undone_at IS NULL
                    LIMIT 1
                ) am ON TRUE
                LEFT JOIN LATERAL (
                    SELECT g2.display_name_override FROM grades g2
                    JOIN seasons s2 ON s2.id = g2.season_id
                    WHERE s2.organisation_id = CAST(:org_id AS UUID)
                      AND g2.name = COALESCE(am.canonical_name, g.name)
                      AND g2.display_name_override IS NOT NULL
                    LIMIT 1
                ) gdn ON TRUE
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {season_clause}
                  {public_clause}
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

    # Grades are seeded into the DB during sync; no live API fallback needed.
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
    # W/L/D/total_games/win_rate are computed from our own synced games inside
    # get_club_summary (DB-first) — the old PlayHQ Partner override is retired.
    return await get_club_summary(db, org_id, season_id, grade_id)


@router.get("/{org_id}/fixtures")
async def get_org_fixtures(org_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch upcoming fixtures from the Grassroots /scores API (DB grades → live
    per-grade match list). Replaces the retired PlayHQ Partner path."""
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        return []
    fixtures = await org_grassroots_fixtures(db, org)
    upcoming = [
        {
            "id": fx["id"],
            "home_team": fx["home_team"],
            "away_team": fx["away_team"],
            "date": fx["played_at"],
            "time": fx.get("time"),
            "grade": fx.get("grade_name") or "",
            "season": fx.get("season_name") or "",
            "round": fx.get("round"),
            "venue": fx.get("venue"),
        }
        for fx in fixtures
    ]
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
async def trigger_sync(org_id: str, background_tasks: BackgroundTasks, _user: User = Depends(require_cap(RUN_SYNC))):
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
    finals_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Return all synced game results for the org from the DB, grouped-friendly flat list."""
    # A game is 'ours' when one of the org's own players has a recorded
    # appearance in it (a manual game is always ours). ID-based rather than
    # matching the org's name against the free-text home_team/away_team CA
    # supplies — a shared grade holds every club's games, and text matching
    # silently zeroed every result for a club whose CA-recorded team text
    # doesn't literally contain the org's first name-token (e.g. a hyphenated
    # name like "Bayswater-Postels" spelled differently by CA). Mirrors
    # ``_club_results`` so the headline matches this list.
    query = """
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.winning_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name,
               gr.id AS grade_id,
               s.id AS season_id, s.name AS season_name
        FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id
          AND (
              g.source = 'manual'
              OR EXISTS (
                  SELECT 1 FROM game_appearances ga
                  JOIN players p ON p.id = ga.player_id
                  WHERE ga.game_id = g.id AND p.organisation_id = :org_id
              )
          )
    """
    params: dict = {"org_id": org_id}

    if season_id:
        query += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        query += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    if finals_only:
        query += " AND g.is_final = TRUE"
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


@router.get("/{org_id}/grades/{grade_id}/info")
async def get_grade_info(org_id: str, grade_id: str, db: AsyncSession = Depends(get_db)):
    grade = await db.get(Grade, uuid.UUID(grade_id))
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    season = await db.get(Season, grade.season_id)
    return {
        "id": str(grade.id),
        "name": grade.display_name_override or grade.name,
        "season_id": str(grade.season_id),
        "season_name": season.name if season else None,
    }


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
