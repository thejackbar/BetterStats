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
from app.services import fonts as font_service
from app.services import grade_scope
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
    # Typography — font_config comes straight off the row; the resolved
    # upload URL/format fields are computed by font_service.public_font_fields
    # and only populated by get_organisation (the list endpoint returns None).
    # Without these, a page that resolves its club through /organisations/{id}
    # (the player profile, the scorecard) themes the club's colours but
    # silently drops its fonts — the club-slug pages get them via /clubs/{slug}.
    font_config: dict | None = None
    font_display_url: str | None = None
    font_display_format: str | None = None
    font_body_url: str | None = None
    font_body_format: str | None = None
    font_mono_url: str | None = None
    font_mono_format: str | None = None

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
    auto_yearbooks: bool = False,
) -> tuple[Organisation, uuid.UUID, str]:
    """Create/upsert the club, kick off its first full sync, and best-effort
    link + push its Marketing Directory row — the part of onboarding that's
    identical regardless of who's attaching to it afterwards: an already-
    authenticated user (onboard_organisation, below) or a brand-new one
    created in the same breath (self-serve trial registration,
    routers/self_serve_trial.py). Deliberately does NOT touch club membership
    — callers attach the user themselves, since that part genuinely differs
    (an existing user vs. a new one; a super admin is never attached at all).

    `auto_yearbooks=True` (self-serve trial registration only — see that
    router) builds, narrates and publishes every past season's yearbook once
    this first sync succeeds; the ordinary authenticated-onboard path leaves
    yearbooks untouched, same as it always has.

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
    background_tasks.add_task(_sync_safe, org_id, run_id, "org_full", auto_yearbooks)

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
    payload = OrganisationOut.model_validate(org).model_dump()
    # Same resolver the public club payload (clubs.py) uses, so a club's fonts
    # read identically whether the frontend found it by slug or by id.
    payload.update(font_service.public_font_fields(org))
    return payload


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


@router.get("/{org_id}/grade-categories")
async def get_org_grade_categories(org_id: str, db: AsyncSession = Depends(get_db)):
    """Which grade categories this club actually runs, and what counts by default.

    Public and cheap: every stats page needs it to decide which category toggles
    to draw at all. A club with no junior programme gets an empty `available`
    and therefore no toggles, which is also the case where the filter itself is
    a no-op — the two answers agree by construction.
    """
    return {
        "available": await grade_scope.org_available_categories(db, org_id),
        "default": list(await grade_scope.club_default_categories(db, org_id)),
    }


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


@router.get("/{org_id}/lineups")
async def get_org_lineups(
    org_id: str,
    mode: str = Query("upcoming", pattern="^(upcoming|past)$"),
    season_id: str | None = None,
    grade_id: str | None = None,
    category: str | None = None,
    finals_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Published team lists, live from the Grassroots feed (public).

    Clubs publish their side on play.cricket.com.au ahead of the game and
    Grassroots serves it on the plain match record — see services/lineups.py.
    ``mode=upcoming`` reads the club's scheduled fixtures (falling back to its
    most recent games when nothing is scheduled, so the page is never blank in
    the off-season); ``mode=past`` walks back through played games, optionally
    filtered by season and grade, with ``offset``/``limit`` paging.

    ``category`` (one of `grade_labels.GRADE_CATEGORIES` — senior/junior/
    womens/masters/mixed) filters to grades classified that way — a club's
    actual Senior/Junior/Women's split, not a per-player attribute. ``finals_only``
    filters to games whose round name says so (the same `is_final` flag
    `sync.py` sets once a match is played).

    A side its club hasn't published yet comes back with an empty player list
    and ``published: false`` rather than being hidden — "not named yet" is the
    normal state early in the week and worth showing as such.

    Bounded on purpose: each match is a live upstream fetch (short-TTL cached),
    so a page asks for a handful at a time rather than a whole season.
    """
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    from app.services.lineups import org_lineups
    from app.services.grade_labels import (
        GRADE_CATEGORIES, category_for_name, category_label, org_grade_categories,
    )

    if category and category not in GRADE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")

    categories = await org_grade_categories(db, org.id)
    # Which categories actually occur among the org's grades — so the frontend
    # only ever offers a filter option that could return something.
    available_categories = [
        {"key": c, "label": category_label(c)}
        for c in ("senior", "junior", "womens", "masters", "mixed")
        if c in categories.values()
    ]

    # Grade rows whose effective category matches the request — resolved once
    # in Python (category may be an unconfirmed suggestion, not a DB column) so
    # the games query below can filter on a plain grade_id list.
    category_grade_ids: list[uuid.UUID] | None = None
    if category:
        gid_res = await db.execute(
            text(
                "SELECT gr.id, gr.name FROM grades gr "
                "JOIN seasons s ON s.id = gr.season_id WHERE s.organisation_id = :org"
            ),
            {"org": org.id},
        )
        category_grade_ids = [
            gid for gid, gname in gid_res.fetchall()
            if category_for_name(categories, gname) == category
        ]

    async def _played(off: int, lim: int) -> list[str]:
        """Synced games, newest first. Only 'api' games have a Grassroots match
        behind them — a manually-uploaded scorecard has no upstream team list."""
        where = ["g.organisation_id = :org", "g.source = 'api'", "g.played_at IS NOT NULL"]
        params: dict = {"org": org.id, "lim": lim, "off": off}
        if season_id:
            # Expand to the season's aliases so a merged-away season id still
            # matches its canonical games.
            season_ids = await resolve_season_filter(db, org.id, season_id)
            where.append("g.season_id = ANY(:season_ids)")
            params["season_ids"] = [uuid.UUID(s) for s in (season_ids or [season_id])]
        if grade_id:
            where.append("g.grade_id = :grade_id")
            params["grade_id"] = uuid.UUID(grade_id)
        if category_grade_ids is not None:
            where.append("g.grade_id = ANY(:category_grade_ids)")
            params["category_grade_ids"] = category_grade_ids
        if finals_only:
            where.append("g.is_final = TRUE")
        res = await db.execute(
            text(
                f"SELECT g.id::text FROM v_effective_games g WHERE {' AND '.join(where)} "
                "ORDER BY g.played_at DESC, g.id LIMIT :lim OFFSET :off"
            ),
            params,
        )
        return [r[0] for r in res.fetchall()]

    if mode == "past":
        # One extra row tells the page whether a "load more" is worth offering.
        ids = await _played(offset, limit + 1)
        has_more = len(ids) > limit
        match_ids, source = ids[:limit], "past"
    else:
        fixtures = await org_grassroots_fixtures(db, org)
        if category:
            fixtures = [fx for fx in fixtures if fx.get("category") == category]
        if finals_only:
            fixtures = [fx for fx in fixtures if fx.get("is_final")]
        by_id = {fx["id"]: fx for fx in fixtures if fx.get("id")}
        match_ids = list(by_id.keys())[:limit]
        has_more = False
        source = "fixtures"
        if not match_ids:
            ids = await _played(0, limit + 1)
            has_more = len(ids) > limit
            match_ids, source = ids[:limit], "recent"

    matches = await org_lineups(db, org, match_ids) if match_ids else []
    if source in ("past", "recent"):
        # Annotate each DB-sourced match with its own grade's category/is_final
        # — org_lineups() returns Grassroots' own payload shape, which knows
        # nothing about our category system.
        g_res = await db.execute(
            text(
                "SELECT g.id::text, gr.name, g.is_final FROM v_effective_games g "
                "LEFT JOIN grades gr ON gr.id = g.grade_id WHERE g.id::text = ANY(:ids)"
            ),
            {"ids": [m["match_id"] for m in matches]},
        )
        by_match = {mid: (gname, is_final) for mid, gname, is_final in g_res.fetchall()}
        for m in matches:
            gname, is_final = by_match.get(m["match_id"], (None, False))
            cat = category_for_name(categories, gname) if gname else None
            m["category"] = cat
            m["category_label"] = category_label(cat) if cat else None
            m["is_final"] = bool(is_final)
    else:
        # 'fixtures' source already carries category/is_final per fixture.
        for m in matches:
            fx = by_id.get(m["match_id"])
            m["category"] = fx.get("category") if fx else None
            m["category_label"] = category_label(fx["category"]) if fx and fx.get("category") else None
            m["is_final"] = bool(fx.get("is_final")) if fx else False

    return {
        "source": source,
        "offset": offset,
        "has_more": has_more,
        "categories": available_categories,
        "matches": matches,
    }


@router.get("/{org_id}/lineups/{match_id}")
async def get_org_lineup_one(org_id: str, match_id: str, db: AsyncSession = Depends(get_db)):
    """One match's published lineup — for deep-linking straight from a
    Fixtures-page row instead of making a supporter hunt through the Lineups
    list for it. Same payload shape as one entry of the list endpoint's
    ``matches`` array, so the frontend renders it with the same component."""
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    from app.services.lineups import match_lineups
    data = await match_lineups(db, org, match_id)
    if not data:
        raise HTTPException(status_code=404, detail="No lineup found for that match")
    return data


async def _sync_safe(org_id: str, run_id: uuid.UUID, kind: str = "org_full", auto_yearbooks: bool = False):
    from app.services.sync import finish_sync_run, pause_sync_run, cancel_sync_run, SyncControlSignal
    import logging
    try:
        stats = await sync_organisation(org_id, run_id=run_id, kind=kind)
        await finish_sync_run(run_id, stats if isinstance(stats, dict) else {})

        # Self-serve registration's first full sync: build, narrate and publish
        # every past season's yearbook once the club's data is actually in, so
        # a brand-new club gets a full yearbook archive with no admin action
        # needed. Isolated try/except with its own session — a yearbook
        # failure must never look like a sync failure (finish_sync_run has
        # already recorded success above).
        if auto_yearbooks:
            try:
                from app.models.db import async_session_maker
                from app.routers.yearbooks import auto_generate_and_publish_all_yearbooks
                async with async_session_maker() as s:
                    yb_result = await auto_generate_and_publish_all_yearbooks(s, org_id)
                logging.getLogger(__name__).info(f"Self-serve yearbook auto-generate for {org_id}: {yb_result}")
            except Exception as ye:
                logging.getLogger(__name__).warning(f"Self-serve yearbook auto-generate failed for {org_id}: {ye}")
    except SyncControlSignal as sig:
        # Pause/Cancel from the Super Admin All Clubs page — not a crash.
        if sig.action == "pause":
            await pause_sync_run(run_id, {})
        else:
            await cancel_sync_run(run_id, {})
        logging.getLogger(__name__).info(f"Sync {sig.action} for {org_id}")
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
    run_id = await start_sync_run(org_uuid, "org_full", triggered_by_user_id=_user.id)
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
    # A game is 'ours' if any of: (a) we're recorded as home_org_id/away_org_id
    # on the row itself — the reliable per-club signal set at sync time (see
    # migration 167) for a shared games.id row between two both-synced clubs,
    # (b) the game's own grade belongs to our org (the ordinary, non-shared
    # case), (c) one of our players has a recorded appearance in it
    # (belt-and-suspenders for a shared row synced before its home/away org id
    # was backfilled), or (d) it's a manual game we created (checked via the
    # view's own `organisation_id` — see migration 169; a bare `g.source =
    # 'manual'` here used to mean ANY club's manual game read as "ours" on
    # every other club's results, a cross-club leak). NOT purely
    # grade-ownership — a shared grade's game.grade_id belongs to whichever
    # club's sync created the row first, so a club that synced second would
    # otherwise never see its own wins at all (the historical bug: an INNER
    # JOIN through grade->season->org silently excluded these before the
    # WHERE clause's appearance check was even reached). Matching the org's
    # name against the free-text home_team/away_team CA supplies is
    # deliberately avoided — silently zeroes every result for a club whose
    # CA-recorded team text doesn't literally contain the org's first
    # name-token (e.g. a hyphenated name like "Bayswater-Postels" spelled
    # differently by CA). Mirrors ``_club_results`` so the headline matches
    # this list.
    #
    # grade_id is LEFT JOINed (not INNER) so a shared game whose grade_id
    # belongs to the OTHER club still returns a row — grade_name then
    # describes whichever club's grade row is actually attached, which is
    # fine since it's just descriptive text for the same real competition.
    # season is now joined off the view's own `season_id` (migration 169),
    # not via grade->season — a manual game always has `season_id` set even
    # when it has no grade (the upload form allows "— none —" for Grade), so
    # this is what actually fixed those games disappearing from this page. A
    # grade_id/season_id filter still needs to match a shared game under a
    # foreign grade row, so it compares via grassroots_id (the raw CA guid,
    # shared across every club's per-club grade/season rows for the same
    # real grade/season — see migration 067) rather than requiring the
    # literal id to match.
    # g.result is ALSO relative to whichever club's sync wrote it first
    # (classify_match_result computes it against that syncing org's own
    # team) — the exact same single-column-can't-hold-two-perspectives issue
    # opp_org_id had. Now that shared games are visible to the OTHER club
    # too, its stored result can read backwards for them. g.winning_team is
    # the actual winning team's name (neutral, not org-relative), so it's
    # re-derived here against OUR home/away side instead of trusted as
    # stored — falling back to the raw g.result when winning_team is NULL
    # (a symmetric draw/tie/no-result, or a row where home_org_id/
    # away_org_id can't place either side, e.g. not yet backfilled).
    query = """
        SELECT g.id, g.played_at, g.home_team, g.away_team,
               CASE
                   WHEN g.winning_team IS NULL THEN g.result
                   WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
                   WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
                   WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
                   WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
                   ELSE g.result
               END AS result,
               g.winning_team,
               COALESCE(gr.display_name_override, gr.name) AS grade_name,
               gr.id AS grade_id,
               s.id AS season_id, s.name AS season_name
        FROM v_effective_games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN seasons s ON s.id = g.season_id
        WHERE (
            g.organisation_id = CAST(:org_id AS UUID)
            OR g.home_org_id = CAST(:org_id AS UUID)
            OR g.away_org_id = CAST(:org_id AS UUID)
            OR s.organisation_id = CAST(:org_id AS UUID)
            OR EXISTS (
                SELECT 1 FROM game_appearances ga
                JOIN players p ON p.id = ga.player_id
                WHERE ga.game_id = g.id AND p.organisation_id = CAST(:org_id AS UUID)
            )
        )
    """
    params: dict = {"org_id": org_id}

    if season_id:
        query += """ AND (
            s.id = CAST(:season_id AS UUID)
            OR (s.grassroots_id IS NOT NULL AND s.grassroots_id = (
                SELECT grassroots_id FROM seasons WHERE id = CAST(:season_id AS UUID)
            ))
        )"""
        params["season_id"] = season_id
    if grade_id:
        query += """ AND (
            gr.id = CAST(:grade_id AS UUID)
            OR (gr.grassroots_id IS NOT NULL AND gr.grassroots_id = (
                SELECT grassroots_id FROM grades WHERE id = CAST(:grade_id AS UUID)
            ))
        )"""
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
            "grade_id": str(r.grade_id) if r.grade_id else None,
            "season_id": str(r.season_id) if r.season_id else None,
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
