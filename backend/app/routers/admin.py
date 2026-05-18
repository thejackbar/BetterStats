from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from pydantic import BaseModel
import uuid
import re
import json

from app.models.db import (
    Player, PlayerSeasonStats, BattingInnings, BowlingSpell,
    FieldingStat, FallOfWicket, Partnership, Milestone, User, get_db,
)
from app.routers.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalise(name: str) -> str:
    """Normalise 'Last, First' → 'first last' and strip extra spaces for comparison."""
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        name = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", name).lower()


async def _enrich_player(db: AsyncSession, p: Player) -> dict:
    stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == p.id))
    season_stats = stats_res.scalars().all()
    innings_res = await db.execute(select(BattingInnings).where(BattingInnings.player_id == p.id))
    game_innings = len(innings_res.scalars().all())
    return {
        "id": str(p.id),
        "name": p.display_name,
        "playhq_id": p.playhq_id,
        "claimed": p.claimed,
        "seasons_count": len(season_stats),
        "total_runs": sum((s.runs or 0) for s in season_stats),
        "total_wickets": sum((s.wickets or 0) for s in season_stats),
        "total_matches": sum((s.matches or 0) for s in season_stats),
        "game_level_innings": game_innings,
    }


@router.get("/player-info")
async def get_player_info(player_id: str, org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Return enriched stats for a single player (used by manual merge UI)."""
    p = await db.get(Player, uuid.UUID(player_id))
    if not p or str(p.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Player not found")
    return await _enrich_player(db, p)


@router.get("/merge-candidates")
async def get_merge_candidates(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Return pairs of players within an org that look like duplicates."""
    result = await db.execute(
        select(Player).where(Player.organisation_id == uuid.UUID(org_id))
    )
    players = result.scalars().all()

    # Load permanently ignored pairs for this org
    ignored_res = await db.execute(
        text("SELECT player_a_id::text, player_b_id::text FROM merge_pair_ignores WHERE org_id = :org_id"),
        {"org_id": org_id},
    )
    ignored = {(r.player_a_id, r.player_b_id) for r in ignored_res.mappings().all()}

    # Group by normalised name
    groups: dict[str, list[Player]] = {}
    for p in players:
        key = _normalise(p.name)
        groups.setdefault(key, []).append(p)

    candidate_pairs = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        enriched = [await _enrich_player(db, p) for p in group]

        for i in range(len(enriched)):
            for j in range(i + 1, len(enriched)):
                pair_key = tuple(sorted([enriched[i]["id"], enriched[j]["id"]]))
                if pair_key in ignored:
                    continue
                candidate_pairs.append({
                    "normalised_name": key,
                    "player_a": enriched[i],
                    "player_b": enriched[j],
                })

    return candidate_pairs


class IgnorePairRequest(BaseModel):
    player_a_id: str
    player_b_id: str
    org_id: str


@router.post("/ignore-pair")
async def ignore_pair(req: IgnorePairRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Permanently suppress a suggested duplicate pair."""
    a, b = sorted([req.player_a_id, req.player_b_id])
    await db.execute(
        text("""
            INSERT INTO merge_pair_ignores (org_id, player_a_id, player_b_id)
            VALUES (:org_id, :a, :b)
            ON CONFLICT (org_id, player_a_id, player_b_id) DO NOTHING
        """),
        {"org_id": req.org_id, "a": a, "b": b},
    )
    await db.commit()
    return {"status": "ignored"}


@router.get("/merge-history")
async def get_merge_history(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
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
async def merge_players(req: MergeRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
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


# ─── Grade merge ─────────────────────────────────────────

def _resolve_canonical_grade(canonical_chain: dict[str, str], name: str) -> str:
    seen = set()
    current = name
    while current in canonical_chain and current not in seen:
        seen.add(current)
        current = canonical_chain[current]
    return current


@router.get("/grades-with-stats")
async def list_grades_with_stats(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """List distinct grade names in an org with aggregate stats, applying active merges."""
    raw = await db.execute(
        text("""
            SELECT
                gr.name AS grade_name,
                COALESCE(MAX(gr.display_name_override), gr.name) AS display_name,
                COUNT(DISTINCT g.id) AS games,
                COUNT(DISTINCT bi.player_id) AS players,
                COALESCE(SUM(bi.runs), 0) AS runs
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN games g ON g.grade_id = gr.id
            LEFT JOIN batting_innings bi ON bi.game_id = g.id
            WHERE s.organisation_id = :org_id
            GROUP BY gr.name
            ORDER BY gr.name
        """),
        {"org_id": org_id},
    )
    raw_rows = [dict(r) for r in raw.mappings().all()]

    log_rows = await db.execute(
        text("""
            SELECT alias_name, canonical_name
            FROM grade_merge_logs
            WHERE org_id = :org_id AND undone_at IS NULL
        """),
        {"org_id": org_id},
    )
    alias_to_canonical = {r["alias_name"]: r["canonical_name"] for r in log_rows.mappings().all()}

    # Map original name -> display_name for lookup after merge resolution
    display_name_map = {row["grade_name"]: row["display_name"] for row in raw_rows}

    bucket: dict[str, dict] = {}
    aliases_by_canonical: dict[str, list[str]] = {}
    for row in raw_rows:
        name = row["grade_name"]
        canonical = _resolve_canonical_grade(alias_to_canonical, name)
        slot = bucket.setdefault(canonical, {
            "grade_name": canonical,
            "display_name": display_name_map.get(canonical, canonical),
            "games": 0,
            "players": 0,
            "runs": 0,
            "aliases": [],
        })
        slot["games"] += int(row["games"] or 0)
        slot["runs"] += int(row["runs"] or 0)
        slot["players"] = max(slot["players"], int(row["players"] or 0))
        if name != canonical:
            slot["aliases"].append(name)
            aliases_by_canonical.setdefault(canonical, []).append(name)

    out = list(bucket.values())
    out.sort(key=lambda r: r["display_name"].lower())
    return out


class MergeGradesRequest(BaseModel):
    org_id: str
    alias_name: str
    canonical_name: str


@router.post("/merge-grades")
async def merge_grades(req: MergeGradesRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Mark `alias_name` as a variant of `canonical_name` for the given org."""
    alias = req.alias_name.strip()
    canonical = req.canonical_name.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="Both grade names are required")
    if alias == canonical:
        raise HTTPException(status_code=400, detail="Alias and canonical grade are the same")

    existing = await db.execute(
        text("""
            SELECT alias_name, canonical_name
            FROM grade_merge_logs
            WHERE org_id = :org_id AND undone_at IS NULL
        """),
        {"org_id": req.org_id},
    )
    chain = {r["alias_name"]: r["canonical_name"] for r in existing.mappings().all()}

    resolved_canonical = _resolve_canonical_grade(chain, canonical)
    if resolved_canonical == alias:
        raise HTTPException(status_code=400, detail="That merge would create a cycle")

    # If alias is itself currently a canonical for other merges, redirect those to the new canonical
    await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET canonical_name = :new_canonical
            WHERE org_id = :org_id
              AND undone_at IS NULL
              AND canonical_name = :alias
        """),
        {"org_id": req.org_id, "new_canonical": resolved_canonical, "alias": alias},
    )

    # If this exact alias already maps, replace with the resolved canonical
    await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET undone_at = NOW()
            WHERE org_id = :org_id
              AND undone_at IS NULL
              AND alias_name = :alias
        """),
        {"org_id": req.org_id, "alias": alias},
    )

    await db.execute(
        text("""
            INSERT INTO grade_merge_logs (org_id, alias_name, canonical_name)
            VALUES (:org_id, :alias, :canonical)
        """),
        {"org_id": req.org_id, "alias": alias, "canonical": resolved_canonical},
    )
    await db.commit()
    return {"status": "merged", "alias": alias, "canonical": resolved_canonical}


@router.get("/grade-merge-history")
async def grade_merge_history(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await db.execute(
        text("""
            SELECT id, merged_at, alias_name, canonical_name, undone_at
            FROM grade_merge_logs
            WHERE org_id = :org_id
            ORDER BY merged_at DESC
            LIMIT 100
        """),
        {"org_id": org_id},
    )
    return [
        {
            "id": r["id"],
            "merged_at": r["merged_at"].isoformat() if r["merged_at"] else None,
            "alias_name": r["alias_name"],
            "canonical_name": r["canonical_name"],
            "undone": r["undone_at"] is not None,
        }
        for r in rows.mappings().all()
    ]


class UndoGradeMergeRequest(BaseModel):
    merge_log_id: int
    org_id: str


@router.post("/undo-grade-merge")
async def undo_grade_merge(req: UndoGradeMergeRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET undone_at = NOW()
            WHERE id = :id AND org_id = :org_id AND undone_at IS NULL
            RETURNING id
        """),
        {"id": req.merge_log_id, "org_id": req.org_id},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Merge log not found or already undone")
    await db.commit()
    return {"status": "undone"}


@router.post("/undo-merge")
async def undo_merge(req: UndoMergeRequest, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
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

    # Reverse playhq_id copy on keep player FIRST, before re-creating the removed player,
    # to avoid unique constraint violation (organisation_id, playhq_id).
    if log["keep_original_playhq_id"] is None and log["removed_player_playhq_id"]:
        keep.playhq_id = None
        await db.flush()

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

    # asyncpg returns JSONB columns as Python lists already; guard against
    # legacy string-encoded rows just in case.
    def _jlist(val):
        if isinstance(val, list):
            return val
        return json.loads(val or "[]")

    # Reassign game-level records back
    bat_ids = _jlist(log["batting_innings_ids"])
    if bat_ids:
        await db.execute(
            text("UPDATE batting_innings SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bat_ids},
        )
    bowl_ids = _jlist(log["bowling_spell_ids"])
    if bowl_ids:
        await db.execute(
            text("UPDATE bowling_spells SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bowl_ids},
        )
    field_ids = _jlist(log["fielding_stat_ids"])
    if field_ids:
        await db.execute(
            text("UPDATE fielding_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": field_ids},
        )
    fow_ids = _jlist(log["fall_of_wicket_ids"])
    if fow_ids:
        await db.execute(
            text("UPDATE fall_of_wickets SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": fow_ids},
        )
    b1_ids = _jlist(log["batter1_partnership_ids"])
    if b1_ids:
        await db.execute(
            text("UPDATE partnerships SET batter1_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b1_ids},
        )
    b2_ids = _jlist(log["batter2_partnership_ids"])
    if b2_ids:
        await db.execute(
            text("UPDATE partnerships SET batter2_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b2_ids},
        )
    mil_ids = _jlist(log["milestone_ids"])
    if mil_ids:
        await db.execute(
            text("UPDATE milestones SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": mil_ids},
        )

    pss_ids = _jlist(log["moved_season_stat_ids"])
    if pss_ids:
        await db.execute(
            text("UPDATE player_season_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": pss_ids},
        )

    await db.execute(
        text("UPDATE merge_logs SET undone_at = NOW() WHERE id = :id"),
        {"id": req.merge_log_id},
    )

    await db.commit()

    return {"status": "undone", "restored_player_id": str(remove_id)}
