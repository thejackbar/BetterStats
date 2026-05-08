from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from pydantic import BaseModel
import uuid
import re

from app.models.db import (
    Player, PlayerSeasonStats, BattingInnings, BowlingSpell,
    FieldingStat, FallOfWicket, Partnership, Milestone, get_db,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalise(name: str) -> str:
    """Normalise 'Last, First' → 'first last' and strip extra spaces for comparison."""
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", name).lower()


@router.get("/merge-candidates")
async def get_merge_candidates(org_id: str, db: AsyncSession = Depends(get_db)):
    """Return pairs of players within an org that look like duplicates."""
    result = await db.execute(
        select(Player).where(Player.organisation_id == uuid.UUID(org_id))
    )
    players = result.scalars().all()

    # Group by normalised name
    groups: dict[str, list[Player]] = {}
    for p in players:
        key = _normalise(p.name)
        groups.setdefault(key, []).append(p)

    # Fetch season stats counts for all players in duplicate groups
    candidate_pairs = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        # Build enriched player info with season-stat counts
        enriched = []
        for p in group:
            stats_res = await db.execute(
                select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == p.id)
            )
            season_stats = stats_res.scalars().all()
            total_runs = sum((s.runs or 0) for s in season_stats)
            total_wickets = sum((s.wickets or 0) for s in season_stats)
            total_matches = sum((s.matches or 0) for s in season_stats)
            seasons_count = len(season_stats)

            innings_res = await db.execute(
                select(BattingInnings).where(BattingInnings.player_id == p.id)
            )
            game_innings = len(innings_res.scalars().all())

            enriched.append({
                "id": str(p.id),
                "name": p.name,
                "playhq_id": p.playhq_id,
                "claimed": p.claimed,
                "seasons_count": seasons_count,
                "total_runs": total_runs,
                "total_wickets": total_wickets,
                "total_matches": total_matches,
                "game_level_innings": game_innings,
            })

        # Emit all unique pairs from the group
        for i in range(len(enriched)):
            for j in range(i + 1, len(enriched)):
                candidate_pairs.append({
                    "normalised_name": key,
                    "player_a": enriched[i],
                    "player_b": enriched[j],
                })

    return candidate_pairs


class MergeRequest(BaseModel):
    keep_player_id: str
    remove_player_id: str
    org_id: str


@router.post("/merge-players")
async def merge_players(req: MergeRequest, db: AsyncSession = Depends(get_db)):
    """Merge remove_player into keep_player, reassigning all records."""
    keep_id = uuid.UUID(req.keep_player_id)
    remove_id = uuid.UUID(req.remove_player_id)
    org_id = uuid.UUID(req.org_id)

    keep = await db.get(Player, keep_id)
    remove = await db.get(Player, remove_id)

    if not keep or not remove:
        raise HTTPException(status_code=404, detail="Player not found")
    if keep.organisation_id != org_id or remove.organisation_id != org_id:
        raise HTTPException(status_code=400, detail="Players must belong to the specified organisation")
    if keep_id == remove_id:
        raise HTTPException(status_code=400, detail="Cannot merge a player with itself")

    # Reassign game-level records
    await db.execute(
        update(BattingInnings)
        .where(BattingInnings.player_id == remove_id)
        .values(player_id=keep_id)
    )
    await db.execute(
        update(BowlingSpell)
        .where(BowlingSpell.player_id == remove_id)
        .values(player_id=keep_id)
    )
    await db.execute(
        update(FieldingStat)
        .where(FieldingStat.player_id == remove_id)
        .values(player_id=keep_id)
    )
    await db.execute(
        update(FallOfWicket)
        .where(FallOfWicket.player_id == remove_id)
        .values(player_id=keep_id)
    )
    await db.execute(
        update(Partnership)
        .where(Partnership.batter1_id == remove_id)
        .values(batter1_id=keep_id)
    )
    await db.execute(
        update(Partnership)
        .where(Partnership.batter2_id == remove_id)
        .values(batter2_id=keep_id)
    )
    await db.execute(
        update(Milestone)
        .where(Milestone.player_id == remove_id)
        .values(player_id=keep_id)
    )

    # Handle PlayerSeasonStats: reassign seasons keep doesn't have, drop duplicates
    remove_stats_res = await db.execute(
        select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == remove_id)
    )
    remove_stats = remove_stats_res.scalars().all()

    keep_stats_res = await db.execute(
        select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == keep_id)
    )
    keep_season_ids = {s.season_id for s in keep_stats_res.scalars().all()}

    for stat in remove_stats:
        if stat.season_id not in keep_season_ids:
            # Keep player has no stats for this season — reassign
            await db.execute(
                update(PlayerSeasonStats)
                .where(PlayerSeasonStats.id == stat.id)
                .values(player_id=keep_id)
            )
        else:
            # Keep player already has stats for this season (Grassroots data is authoritative)
            await db.execute(
                delete(PlayerSeasonStats).where(PlayerSeasonStats.id == stat.id)
            )

    # Copy playhq_id from remove to keep if keep has none
    if not keep.playhq_id and remove.playhq_id:
        keep.playhq_id = remove.playhq_id

    await db.flush()
    await db.execute(delete(Player).where(Player.id == remove_id))
    await db.commit()

    return {"status": "merged", "kept_player_id": str(keep_id), "removed_player_id": str(remove_id)}
