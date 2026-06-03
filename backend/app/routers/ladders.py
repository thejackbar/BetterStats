"""BetterSelect — Ladders / standings.

Live grade ladders from Cricket Australia's unauthenticated fixturesladders
endpoint, presented per team (each team is linked to the grade it most recently
played in — see teams.ensure_team_grades).

The upstream JSON shape is not contractually known here, so _extract_rows and
_norm_row are deliberately defensive: they try several plausible key names and
bail to sensible defaults rather than raising. One live run will confirm the
real field names if any need tweaking.

Two surfaces:
  GET /ladders/teams          — admin, behind get_current_club
  GET /ladders/public/{slug}  — public, club resolved by slug
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Grade, Organisation, Season, Team, get_db
from app.routers.auth import get_current_club
from app.routers.teams import ensure_team_grades, _grade_name_map
from app.services import grassroots_scores_client
from app.services.club_match import club_match_keys

router = APIRouter(prefix="/ladders", tags=["ladders"])

INACTIVE_DETAIL = "This club page is currently not available."


# ── Ladder JSON parsing ──────────────────────────────────────────────────────
# Confirmed shape (live, May 2026):
#   { "grade": {...}, "ladders": [ { "name": "Overall" | "2 Day+" | "One Day",
#       "columns": [ {"id","heading","description"} ],
#       "pools":   [ { "teams": [ {
#           "id", "displayName", "rank", "owningOrganisation": {...},
#           "ladderData": [ {"id": "competitionPoints", "val": 82}, ... ] } ] } ] } ] }
# A grade can carry multiple ladder *views* (Overall / 2 Day+ / One Day) — the
# same switcher the official site exposes via ?ladder=N.

# Stats we surface, in display order. (id, fallback heading) — the API's own
# column heading is preferred when present.
LADDER_STATS = [
    ("played", "P"), ("won", "W"), ("lost", "L"), ("ties", "T"),
    ("noResults", "NR"), ("byes", "BYE"),
    ("competitionPoints", "PTS"), ("quotient", "Q"), ("netRunRate", "NRR"),
]


def _row_stats(ladder_data) -> dict:
    """ladderData: [{id, val}] -> {id: val}."""
    return {d.get("id"): d.get("val") for d in (ladder_data or []) if isinstance(d, dict)}


def _parse_ladder_payload(raw, club_keys: list) -> list:
    """Turn the upstream payload into display-ready views:
    [ {name, columns: [{id, heading}], rows: [{rank, team_name, logo_url,
       is_club, stats: {stat_id: val}}]} ].
    """
    if not isinstance(raw, dict):
        return []
    views = []
    for ladder in raw.get("ladders", []) or []:
        if not isinstance(ladder, dict):
            continue
        headings = {c.get("id"): c.get("heading") for c in (ladder.get("columns") or []) if isinstance(c, dict)}
        columns = [{"id": sid, "heading": headings.get(sid) or fb} for sid, fb in LADDER_STATS if sid in headings]
        rows = []
        for pool in (ladder.get("pools") or []):
            for t in (pool.get("teams") or []):
                if not isinstance(t, dict):
                    continue
                stats = _row_stats(t.get("ladderData"))
                name = t.get("displayName") or "—"
                org = t.get("owningOrganisation") or {}
                hay = " ".join(str(x).lower() for x in [name, org.get("name"), org.get("shortName")] if x)
                rows.append({
                    "rank": t.get("rank"),
                    "team_id": t.get("id"),
                    "team_name": name,
                    "logo_url": org.get("logoUrl"),
                    "is_club": any(k and k in hay for k in club_keys),
                    "stats": {sid: stats.get(sid) for sid, _ in LADDER_STATS},
                })
        rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 9999))
        views.append({"name": ladder.get("name") or "Ladder", "columns": columns, "rows": rows})
    return views


async def _compute_team_ladders(db: AsyncSession, org: Organisation, auto_link: bool = True) -> dict:
    if auto_link:
        await ensure_team_grades(db, org.id)  # self-link any teams missing a grade (admin only)
    teams = (await db.execute(
        select(Team)
        .where(Team.organisation_id == org.id, Team.is_active.is_(True))
        .order_by(Team.sequence.asc(), Team.name.asc())
    )).scalars().all()
    grade_names = await _grade_name_map(db, org.id)
    # grade_id -> raw CA grade GUID. The ladder API is keyed on the shared GUID,
    # while Team.grade_id may be a per-club uuid5 (grassroots_id == id for legacy).
    grade_gr = {
        str(gid): (gg or str(gid))
        for gid, gg in (await db.execute(
            select(Grade.id, Grade.grassroots_id)
            .join(Season, Grade.season_id == Season.id)
            .where(Season.organisation_id == org.id)
        )).all()
    }
    club_keys = club_match_keys(org)

    linked = [t for t in teams if t.grade_id]
    unlinked = [{"team_id": str(t.id), "team_name": t.name} for t in teams if not t.grade_id]

    async def one(t: Team) -> dict:
        raw = await grassroots_scores_client.get_grade_ladder(grade_gr.get(str(t.grade_id), str(t.grade_id)))
        views = _parse_ladder_payload(raw, club_keys)
        return {
            "team_id": str(t.id),
            "team_name": t.name,
            "grade_id": str(t.grade_id),
            "grade_name": grade_names.get(str(t.grade_id)),
            "available": bool(views and any(v["rows"] for v in views)),
            "views": views,
        }

    results = list(await asyncio.gather(*[one(t) for t in linked])) if linked else []
    return {"teams": results, "unlinked": unlinked}


@router.get("/teams")
async def team_ladders(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Per-team ladders for the signed-in club (includes unlinked teams)."""
    return await _compute_team_ladders(db, club)


@router.get("/public/{slug}")
async def public_team_ladders(slug: str, db: AsyncSession = Depends(get_db)):
    """Per-team ladders for a public club page (resolved by slug)."""
    org = (await db.execute(
        select(Organisation).where(Organisation.slug == slug.lower())
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Club not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail=INACTIVE_DETAIL)
    # Read-only on public GETs — linking happens on the admin side.
    data = await _compute_team_ladders(db, org, auto_link=False)
    # Public view: drop the admin-only "unlinked teams" hint.
    return {"teams": data["teams"]}


@router.get("/grade/{grade_id}")
async def grade_ladder(grade_id: str, db: AsyncSession = Depends(get_db)):
    """Public ladder for a single grade — powers historical browsing (any
    season). Standings are public, so no auth; the grade just has to belong to
    an active club. Club rows are flagged via the owning org's name."""
    try:
        gid = uuid.UUID(grade_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Grade not found")
    grade = await db.get(Grade, gid)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    season = await db.get(Season, grade.season_id) if grade.season_id else None
    org = await db.get(Organisation, season.organisation_id) if season else None
    if not org or not org.is_active:
        raise HTTPException(status_code=404, detail="Grade not found")
    club_keys = club_match_keys(org)
    # Ladder API wants the shared raw CA grade GUID, not our (possibly per-club) PK.
    raw = await grassroots_scores_client.get_grade_ladder(grade.grassroots_id or str(gid))
    views = _parse_ladder_payload(raw, club_keys)
    return {
        "grade_id": str(gid),
        "grade_name": grade.display_name,
        "season_name": season.name if season else None,
        "available": bool(views and any(v["rows"] for v in views)),
        "views": views,
    }
