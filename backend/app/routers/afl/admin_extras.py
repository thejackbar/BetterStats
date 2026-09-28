"""BetterStats admin tools football was missing: Activity Log, Milestones and a
Matches list.

Each is the football counterpart of a cricket Core admin screen, built on data
the football silo already holds:

* **Activity Log** reads ``audit_logs``, which every AFL admin router has been
  writing to (merges, imports, user changes, season edits) with nothing that
  showed it. Same shape and capability as cricket's ``/club-admin/activity-log``.
* **Milestones** reads the same career figure the profile and the public
  dashboard use (synced + imported + manual), so the three never disagree about
  who is close to what. Games and goals only — football's own ladders.
* **Matches** lists every game the club holds, synced or imported, with what
  the sync has and hasn't pulled for it, so an admin can see a game waiting on
  its stats rather than wondering why a player's total looks short.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_PLAYERS, MANAGE_USERS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services.afl import aggregations
from app.services.afl.season_groups import season_group

router = APIRouter(prefix="/club-admin", tags=["afl-admin-extras"])


@router.get("/activity-log")
async def list_activity_log(
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_cap(MANAGE_USERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Recent admin actions for this club, newest first."""
    rows = await db.execute(text("""
        SELECT al.id, al.created_at, al.action, al.target_type, al.target_id,
               al.details, u.email AS user_email,
               COALESCE(u.display_name, u.username) AS user_name
        FROM audit_logs al
        LEFT JOIN users u ON u.id = al.user_id
        WHERE al.org_id = :org
        ORDER BY al.created_at DESC
        LIMIT :lim
    """), {"org": str(club.id), "lim": limit})
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "action": r["action"],
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "user_email": r["user_email"],
            "user_name": r["user_name"],
            "details": r["details"] or {},
        }
        for r in rows.mappings().all()
    ]


@router.get("/milestones")
async def list_milestones(
    days: int = Query(60, ge=1, le=730),
    _: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """What is coming up (within each ladder's reach window) and what was
    reached by games played in the last ``days`` days."""
    upcoming = await aggregations.upcoming_milestones(db, club.id, limit=500)
    reached = await aggregations.recently_reached_milestones(db, club.id, days=days)
    return {"upcoming": upcoming, "reached": reached, "days": days}


@router.get("/games")
async def list_games(
    season_id: Optional[uuid.UUID] = None,
    source: Optional[str] = Query(None, pattern="^(playhq|import)$"),
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = 0,
    _: User = Depends(require_cap(MANAGE_PLAYERS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Every game the club holds, newest first, with how far the sync got."""
    clauses = ["s.organisation_id = :org"]
    params: dict = {"org": str(club.id), "lim": limit, "off": offset}
    if season_id:
        clauses.append("s.id = ANY(:season)")
        params["season"] = await season_group(db, club.id, season_id)
    if source:
        clauses.append("COALESCE(d.source, 'playhq') = :source")
        params["source"] = source
    if q and q.strip():
        clauses.append("(g.home_team ILIKE :q OR g.away_team ILIKE :q OR gr.name ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    where = " AND ".join(clauses)
    base = f"""
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE {where}
    """
    res = await db.execute(text(f"""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result, g.is_final,
               gr.name AS grade_name, s.id AS season_id, s.name AS season_name,
               d.round_name, d.status, d.our_side, d.home_score, d.away_score,
               COALESCE(d.source, 'playhq') AS source, d.is_bye, d.is_forfeit,
               d.result_note, d.synced_at, d.publish_lineup,
               (SELECT COUNT(*) FROM afl_player_game_lines l
                 WHERE l.game_id = g.id AND l.side = d.our_side) AS our_lines
        {base}
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), params)
    games = []
    for r in res.mappings().all():
        row = dict(r)
        row["id"] = str(row["id"])
        row["season_id"] = str(row["season_id"])
        row["played_at"] = row["played_at"].isoformat() if row["played_at"] else None
        row["synced_at"] = row["synced_at"].isoformat() if row["synced_at"] else None
        # An imported game carries only a result; a synced FINAL game with no
        # stats pull yet is the one worth flagging.
        row["stats_pending"] = (row["source"] == "playhq" and row["status"] == "FINAL"
                                and row["synced_at"] is None)
        games.append(row)
    count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
    total = int((await db.execute(text(f"SELECT COUNT(*) {base}"), count_params)).scalar() or 0)
    return {"games": games, "total": total}
