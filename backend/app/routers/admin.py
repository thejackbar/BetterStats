from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from pydantic import BaseModel
import uuid
import re
import json

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

    candidate_pairs = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
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

        for i in range(len(enriched)):
            for j in range(i + 1, len(enriched)):
                candidate_pairs.append({
                    "normalised_name": key,
                    "player_a": enriched[i],
                    "player_b": enriched[j],
                })

    return candidate_pairs


@router.get("/merge-history")
async def get_merge_history(org_id: str, db: AsyncSession = Depends(get_db)):
    """Return recent merges for an org that can be undone."""
    rows = await db.execute(
        text("""
            SELECT id, merged_at, keep_player_id, keep_player_name,
                   removed_player_id, removed_player_name, undone_at
            FROM merge_logs
            WHERE org_id = :org_id
            ORDER BY merged_at DESC
            LIMIT 50
        """),
        {"org_id": org_id},
    )
    return [
        {
            "id": r.id,
            "merged_at": r.merged_at.isoformat() if r.merged_at else None,
            "keep_player_id": str(r.keep_player_id),
            "keep_player_name": r.keep_player_name,
            "removed_player_id": str(r.removed_player_id),
            "removed_player_name": r.removed_player_name,
            "undone": r.undone_at is not None,
        }
        for r in rows.mappings().all()
    ]


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

    # --- Collect IDs before making changes (for undo log) ---
    def _ids(rows) -> list:
        return [r.id for r in rows]

    batting_rows = (await db.execute(select(BattingInnings).where(BattingInnings.player_id == remove_id))).scalars().all()
    bowling_rows = (await db.execute(select(BowlingSpell).where(BowlingSpell.player_id == remove_id))).scalars().all()
    fielding_rows = (await db.execute(select(FieldingStat).where(FieldingStat.player_id == remove_id))).scalars().all()
    fow_rows = (await db.execute(select(FallOfWicket).where(FallOfWicket.player_id == remove_id))).scalars().all()
    batter1_rows = (await db.execute(select(Partnership).where(Partnership.batter1_id == remove_id))).scalars().all()
    batter2_rows = (await db.execute(select(Partnership).where(Partnership.batter2_id == remove_id))).scalars().all()
    milestone_rows = (await db.execute(select(Milestone).where(Milestone.player_id == remove_id))).scalars().all()

    remove_stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == remove_id))
    remove_stats = remove_stats_res.scalars().all()
    keep_stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == keep_id))
    keep_season_ids = {s.season_id for s in keep_stats_res.scalars().all()}

    moved_pss_ids = [s.id for s in remove_stats if s.season_id not in keep_season_ids]

    # --- Reassign game-level records ---
    await db.execute(update(BattingInnings).where(BattingInnings.player_id == remove_id).values(player_id=keep_id))
    await db.execute(update(BowlingSpell).where(BowlingSpell.player_id == remove_id).values(player_id=keep_id))
    await db.execute(update(FieldingStat).where(FieldingStat.player_id == remove_id).values(player_id=keep_id))
    await db.execute(update(FallOfWicket).where(FallOfWicket.player_id == remove_id).values(player_id=keep_id))
    await db.execute(update(Partnership).where(Partnership.batter1_id == remove_id).values(batter1_id=keep_id))
    await db.execute(update(Partnership).where(Partnership.batter2_id == remove_id).values(batter2_id=keep_id))
    await db.execute(update(Milestone).where(Milestone.player_id == remove_id).values(player_id=keep_id))

    # --- Handle PlayerSeasonStats ---
    for stat in remove_stats:
        if stat.season_id not in keep_season_ids:
            await db.execute(
                update(PlayerSeasonStats).where(PlayerSeasonStats.id == stat.id).values(player_id=keep_id)
            )
        else:
            await db.execute(delete(PlayerSeasonStats).where(PlayerSeasonStats.id == stat.id))

    # Save data needed for undo log before player is deleted
    keep_original_playhq_id = keep.playhq_id
    removed_playhq_id = remove.playhq_id
    removed_name = remove.name

    # --- Delete remove player FIRST (avoids unique constraint violation on playhq_id) ---
    await db.execute(delete(Player).where(Player.id == remove_id))

    # --- Now safe to copy playhq_id to keep (remove is deleted in this transaction) ---
    if not keep.playhq_id and removed_playhq_id:
        keep.playhq_id = removed_playhq_id

    # --- Write merge log ---
    await db.execute(
        text("""
            INSERT INTO merge_logs (
                org_id, keep_player_id, keep_player_name,
                removed_player_id, removed_player_name, removed_player_playhq_id,
                keep_original_playhq_id,
                moved_season_stat_ids, batting_innings_ids, bowling_spell_ids,
                fielding_stat_ids, fall_of_wicket_ids,
                batter1_partnership_ids, batter2_partnership_ids, milestone_ids
            ) VALUES (
                :org_id, :keep_id, :keep_name,
                :remove_id, :remove_name, :remove_playhq_id,
                :keep_orig_playhq_id,
                :pss_ids, :bat_ids, :bowl_ids,
                :field_ids, :fow_ids,
                :b1_ids, :b2_ids, :mil_ids
            )
        """),
        {
            "org_id": str(org_id),
            "keep_id": str(keep_id),
            "keep_name": keep.name,
            "remove_id": str(remove_id),
            "remove_name": removed_name,
            "remove_playhq_id": removed_playhq_id,
            "keep_orig_playhq_id": keep_original_playhq_id,
            "pss_ids": json.dumps(moved_pss_ids),
            "bat_ids": json.dumps(_ids(batting_rows)),
            "bowl_ids": json.dumps(_ids(bowling_rows)),
            "field_ids": json.dumps(_ids(fielding_rows)),
            "fow_ids": json.dumps(_ids(fow_rows)),
            "b1_ids": json.dumps(_ids(batter1_rows)),
            "b2_ids": json.dumps(_ids(batter2_rows)),
            "mil_ids": json.dumps(_ids(milestone_rows)),
        },
    )

    await db.commit()

    return {"status": "merged", "kept_player_id": str(keep_id), "removed_player_id": str(remove_id)}


class UndoMergeRequest(BaseModel):
    merge_log_id: int
    org_id: str


@router.post("/undo-merge")
async def undo_merge(req: UndoMergeRequest, db: AsyncSession = Depends(get_db)):
    """Reverse a previous merge: re-create removed player and reassign records back."""
    log_row = await db.execute(
        text("SELECT * FROM merge_logs WHERE id = :id AND org_id = :org_id"),
        {"id": req.merge_log_id, "org_id": req.org_id},
    )
    log = log_row.mappings().first()
    if not log:
        raise HTTPException(status_code=404, detail="Merge log not found")
    if log["undone_at"] is not None:
        raise HTTPException(status_code=400, detail="This merge has already been undone")

    keep_id = log["keep_player_id"]
    remove_id = log["removed_player_id"]

    keep = await db.get(Player, keep_id)
    if not keep:
        raise HTTPException(status_code=404, detail="Keep player no longer exists")

    # Re-create removed player
    await db.execute(
        text("""
            INSERT INTO players (id, name, organisation_id, playhq_id, claimed)
            VALUES (:id, :name, :org_id, :playhq_id, false)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": str(remove_id),
            "name": log["removed_player_name"],
            "org_id": req.org_id,
            "playhq_id": log["removed_player_playhq_id"],
        },
    )

    # Reverse playhq_id copy on keep player if we were the ones who set it
    if log["keep_original_playhq_id"] is None and log["removed_player_playhq_id"]:
        keep.playhq_id = None

    # Reassign game-level records back
    bat_ids = json.loads(log["batting_innings_ids"] or "[]")
    if bat_ids:
        await db.execute(
            text("UPDATE batting_innings SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bat_ids},
        )
    bowl_ids = json.loads(log["bowling_spell_ids"] or "[]")
    if bowl_ids:
        await db.execute(
            text("UPDATE bowling_spells SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bowl_ids},
        )
    field_ids = json.loads(log["fielding_stat_ids"] or "[]")
    if field_ids:
        await db.execute(
            text("UPDATE fielding_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": field_ids},
        )
    fow_ids = json.loads(log["fall_of_wicket_ids"] or "[]")
    if fow_ids:
        await db.execute(
            text("UPDATE fall_of_wickets SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": fow_ids},
        )
    b1_ids = json.loads(log["batter1_partnership_ids"] or "[]")
    if b1_ids:
        await db.execute(
            text("UPDATE partnerships SET batter1_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b1_ids},
        )
    b2_ids = json.loads(log["batter2_partnership_ids"] or "[]")
    if b2_ids:
        await db.execute(
            text("UPDATE partnerships SET batter2_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b2_ids},
        )
    mil_ids = json.loads(log["milestone_ids"] or "[]")
    if mil_ids:
        await db.execute(
            text("UPDATE milestones SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": mil_ids},
        )

    # Reassign season stats back (only the ones we moved, not the deleted duplicates)
    pss_ids = json.loads(log["moved_season_stat_ids"] or "[]")
    if pss_ids:
        await db.execute(
            text("UPDATE player_season_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": pss_ids},
        )

    # Mark merge log as undone
    await db.execute(
        text("UPDATE merge_logs SET undone_at = NOW() WHERE id = :id"),
        {"id": req.merge_log_id},
    )

    await db.commit()

    return {"status": "undone", "restored_player_id": str(remove_id)}
