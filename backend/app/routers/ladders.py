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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Team, get_db
from app.routers.auth import get_current_club
from app.routers.teams import ensure_team_grades, _grade_name_map
from app.services import grassroots_scores_client

router = APIRouter(prefix="/ladders", tags=["ladders"])

INACTIVE_DETAIL = "This club page is currently not available."


# ── Defensive normalisation of the upstream ladder JSON ──────────────────────

def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def _to_num(v):
    if v is None:
        return 0
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 3)
    except (TypeError, ValueError):
        return 0


def _to_int(v):
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _extract_rows(data) -> list:
    """Pull the list of standing rows out of whatever envelope the proxy uses."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("ladder", "ladders", "standings", "rows", "items", "table", "entries"):
        v = data.get(key)
        if isinstance(v, list):
            # Some shapes nest rows inside each ladder object.
            if v and isinstance(v[0], dict) and any(rk in v[0] for rk in ("rows", "ladder", "standings", "entries")):
                out: list = []
                for grp in v:
                    for rk in ("rows", "ladder", "standings", "entries"):
                        if isinstance(grp.get(rk), list):
                            out.extend(grp[rk])
                return out
            return v
        if isinstance(v, dict):
            for rk in ("rows", "ladder", "standings", "items", "entries"):
                if isinstance(v.get(rk), list):
                    return v[rk]
    return []


def _norm_row(row: dict, club_keys: list) -> dict:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    comp = row.get("competitor") if isinstance(row.get("competitor"), dict) else {}
    name = (
        _first(row, "teamName", "name", "displayName")
        or _first(team, "name", "displayName", "shortName")
        or _first(comp, "name", "displayName")
        or "—"
    )
    tid = _first(row, "teamId", "id") or _first(team, "id") or _first(comp, "id")
    nlow = str(name).lower()
    return {
        "rank": _to_int(_first(row, "rank", "position", "pos", "order")),
        "team_id": str(tid) if tid else None,
        "team_name": name,
        "played": _to_num(_first(row, "played", "matchesPlayed", "games", "p", "P")),
        "won": _to_num(_first(row, "won", "wins", "w", "W")),
        "lost": _to_num(_first(row, "lost", "losses", "l", "L")),
        "drawn": _to_num(_first(row, "drawn", "draws", "d", "D")),
        "tied": _to_num(_first(row, "tied", "ties", "t", "T")),
        "no_result": _to_num(_first(row, "noResult", "noResults", "nr", "NR", "abandoned")),
        "byes": _to_num(_first(row, "byes", "bye", "b", "B")),
        "points": _to_num(_first(row, "points", "pts", "competitionPoints", "totalPoints")),
        "quotient": _first(row, "quotient", "netRunRate", "nrr", "percentage", "runRate"),
        "is_club": any(k and k in nlow for k in club_keys),
    }


def _normalize(raw, club_keys: list) -> list:
    rows = [_norm_row(r, club_keys) for r in _extract_rows(raw) if isinstance(r, dict)]
    if any(r["rank"] is not None for r in rows):
        rows.sort(key=lambda r: r["rank"] if r["rank"] is not None else 9999)
    else:
        rows.sort(key=lambda r: r["points"], reverse=True)
    return rows


async def _compute_team_ladders(db: AsyncSession, org: Organisation) -> dict:
    await ensure_team_grades(db, org.id)  # self-link any teams missing a grade
    teams = (await db.execute(
        select(Team)
        .where(Team.organisation_id == org.id, Team.is_active.is_(True))
        .order_by(Team.sequence.asc(), Team.name.asc())
    )).scalars().all()
    grade_names = await _grade_name_map(db, org.id)
    club_keys = [k.lower().strip() for k in [org.short_name, org.name, (org.name or "").split(" ")[0]] if k]

    linked = [t for t in teams if t.grade_id]
    unlinked = [{"team_id": str(t.id), "team_name": t.name} for t in teams if not t.grade_id]

    async def one(t: Team) -> dict:
        raw = await grassroots_scores_client.get_grade_ladder(str(t.grade_id))
        rows = _normalize(raw, club_keys)
        return {
            "team_id": str(t.id),
            "team_name": t.name,
            "grade_id": str(t.grade_id),
            "grade_name": grade_names.get(str(t.grade_id)),
            "available": bool(rows),
            "rows": rows,
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
    data = await _compute_team_ladders(db, org)
    # Public view: drop the admin-only "unlinked teams" hint.
    return {"teams": data["teams"]}
