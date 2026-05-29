"""BetterSelect — fixtures (Phase 0).

Persisted upcoming / scheduled fixtures: the foundation availability and team
selection build on. BetterStats otherwise stores only completed games, so this
is net-new data. Two sources:

  - 'playhq': pulled from the partner API via POST /fixtures/sync. The fixture
    id is the CA/PlayHQ game GUID, so once played it maps 1:1 to games.id.
  - 'manual': created by hand (POST /fixtures) so admins can build lineups and
    social posts for friendlies / pre-season without an official PlayHQ game.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_FIXTURES, require_cap
from app.models.db import Fixture, Organisation, Season, User, get_db
from app.routers.auth import get_current_user
from app.services import playhq_partner_client

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def _serialize(f: Fixture) -> dict:
    return {
        "id": str(f.id),
        "organisation_id": str(f.organisation_id),
        "grade_id": str(f.grade_id) if f.grade_id else None,
        "source": f.source,
        "playhq_id": f.playhq_id,
        "label": f.label,
        "round": f.round,
        "played_on": f.played_on.isoformat() if f.played_on else None,
        "end_on": f.end_on.isoformat() if f.end_on else None,
        "start_time": f.start_time,
        "home_team": f.home_team,
        "away_team": f.away_team,
        "home_away": f.home_away,
        "opponent_name": f.opponent_name,
        "venue": f.venue,
        "status": f.status,
        "notes": f.notes,
    }


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _derive_sides(g: dict, org: Organisation) -> tuple[Optional[str], Optional[str]]:
    """Best-effort (home_away, opponent_name) from the club's perspective."""
    home = g.get("home_team") or ""
    away = g.get("away_team") or ""
    keys = []
    if org.short_name:
        keys.append(org.short_name.lower().strip())
    if org.name:
        keys.append(org.name.lower().strip())
        keys.append(org.name.split()[0].lower().strip())
    hl, al = home.lower(), away.lower()
    if any(k and k in hl for k in keys):
        return "HOME", away
    if any(k and k in al for k in keys):
        return "AWAY", home
    return None, None


class FixtureCreate(BaseModel):
    organisation_id: str
    label: Optional[str] = None
    opponent_name: Optional[str] = None
    home_away: Optional[str] = None  # HOME | AWAY | BYE
    grade_id: Optional[str] = None
    round: Optional[str] = None
    played_on: Optional[date] = None
    end_on: Optional[date] = None
    start_time: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = "UPCOMING"
    notes: Optional[str] = None


class FixtureUpdate(BaseModel):
    label: Optional[str] = None
    opponent_name: Optional[str] = None
    home_away: Optional[str] = None
    grade_id: Optional[str] = None
    round: Optional[str] = None
    played_on: Optional[date] = None
    end_on: Optional[date] = None
    start_time: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def list_fixtures(
    org_id: str,
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """List persisted fixtures for an org, soonest first."""
    stmt = select(Fixture).where(Fixture.organisation_id == uuid.UUID(org_id))
    if upcoming_only:
        stmt = stmt.where(Fixture.played_on >= date.today())
    stmt = stmt.order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    res = await db.execute(stmt)
    return [_serialize(f) for f in res.scalars().all()]


@router.post("", status_code=201)
async def create_fixture(
    body: FixtureCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    """Create a manual fixture (no PlayHQ game required)."""
    org = await db.get(Organisation, uuid.UUID(body.organisation_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    us = org.short_name or org.name
    home_team = away_team = None
    if body.home_away == "HOME":
        home_team, away_team = us, body.opponent_name
    elif body.home_away == "AWAY":
        home_team, away_team = body.opponent_name, us

    f = Fixture(
        id=uuid.uuid4(),
        organisation_id=org.id,
        source="manual",
        grade_id=uuid.UUID(body.grade_id) if body.grade_id else None,
        label=body.label,
        round=body.round,
        played_on=body.played_on,
        end_on=body.end_on,
        start_time=body.start_time,
        home_team=home_team,
        away_team=away_team,
        home_away=body.home_away,
        opponent_name=body.opponent_name,
        venue=body.venue,
        status=body.status or "UPCOMING",
        notes=body.notes,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _serialize(f)


@router.patch("/{fixture_id}")
async def update_fixture(
    fixture_id: str,
    body: FixtureUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f:
        raise HTTPException(status_code=404, detail="Fixture not found")
    data = body.model_dump(exclude_unset=True)
    if "grade_id" in data:
        data["grade_id"] = uuid.UUID(data["grade_id"]) if data["grade_id"] else None
    for key, value in data.items():
        setattr(f, key, value)
    f.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(f)
    return _serialize(f)


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f:
        raise HTTPException(status_code=404, detail="Fixture not found")
    await db.delete(f)
    await db.commit()


@router.post("/sync")
async def sync_fixtures(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    """Pull upcoming fixtures from the PlayHQ partner API and upsert them.

    Keyed on the PlayHQ game GUID, so re-running is idempotent and a fixture
    that later completes lines up with games.id. Only non-FINAL games dated
    today-or-later are stored.
    """
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if not org.playhq_id:
        return {"synced": 0, "detail": "Org has no playhq_id — manual fixtures only."}

    seasons_res = await db.execute(select(Season).where(Season.organisation_id == org.id))
    db_seasons = [{"id": str(s.id), "name": s.name} for s in seasons_res.scalars().all()]
    games = await playhq_partner_client.get_org_games(
        org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id)
    )

    today_iso = date.today().isoformat()
    synced = 0
    for g in games:
        gid = g.get("id")
        played = g.get("played_at")
        if not gid or g.get("status") == "FINAL" or not played or played < today_iso:
            continue
        try:
            fid = uuid.UUID(str(gid))
        except (ValueError, TypeError):
            continue
        home_away, opponent = _derive_sides(g, org)
        existing = await db.get(Fixture, fid)
        target = existing or Fixture(id=fid, organisation_id=org.id)
        target.source = "playhq"
        target.playhq_id = str(gid)
        target.round = g.get("round")
        target.played_on = _parse_date(played)
        target.start_time = g.get("time")
        target.home_team = g.get("home_team")
        target.away_team = g.get("away_team")
        target.home_away = home_away
        target.opponent_name = opponent
        target.venue = g.get("venue")
        target.status = g.get("status") or "UPCOMING"
        if existing:
            target.updated_at = datetime.now(timezone.utc)
        else:
            db.add(target)
        synced += 1

    await db.commit()
    return {"synced": synced}
