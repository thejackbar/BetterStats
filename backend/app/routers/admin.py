from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from pydantic import BaseModel
import uuid
import re
import json
import logging

log = logging.getLogger(__name__)

from app.services.grassroots_scores_client import get_match_scorecard

from app.models.db import (
    Player, PlayerSeasonStats, BattingInnings, BowlingSpell,
    FieldingStat, FallOfWicket, Partnership, Milestone, User, Organisation, get_db,
)
from app.routers.auth import get_current_user
from app.auth.capabilities import require_cap, MANAGE_MERGES
from app.auth.modules import require_module

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
async def ignore_pair(req: IgnorePairRequest, db: AsyncSession = Depends(get_db), _: User = Depends(require_cap(MANAGE_MERGES))):
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
async def merge_players(req: MergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
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

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=org_id, user_id=current_user.id,
        action="merge_players", target_type="player", target_id=str(keep_id),
        details={
            "kept_player": {"id": str(keep_id), "name": keep.name},
            "removed_player": {"id": str(remove_id), "name": removed_name},
            "rows_moved": {
                "season_stats": len(moved_pss_ids),
                "batting": len(_ids(batting_rows)),
                "bowling": len(_ids(bowling_rows)),
                "fielding": len(_ids(fielding_rows)),
                "milestones": len(_ids(milestone_rows)),
            },
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
            LEFT JOIN v_effective_games g ON g.grade_id = gr.id
            LEFT JOIN v_effective_batting_innings bi ON bi.game_id = g.id
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
async def merge_grades(req: MergeGradesRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
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

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="merge_grades", target_type="grade", target_id=resolved_canonical,
        details={"alias_name": alias, "canonical_name": resolved_canonical},
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
async def undo_grade_merge(req: UndoGradeMergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
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

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="undo_merge_grades", target_type="grade_merge_log",
        target_id=str(req.merge_log_id),
    )
    await db.commit()
    return {"status": "undone"}


@router.post("/undo-merge")
async def undo_merge(req: UndoMergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
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

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="undo_merge_players", target_type="player", target_id=str(remove_id),
        details={
            "merge_log_id": req.merge_log_id,
            "restored_player": {"id": str(remove_id), "name": log["removed_player_name"]},
            "kept_player": {"id": str(keep_id), "name": log["keep_player_name"]},
        },
    )

    await db.commit()

    return {"status": "undone", "restored_player_id": str(remove_id)}


# ─── Social: fetch Grassroots scorecard for social image builder ──────────────

_DNB_TYPES = {"did not bat", "dnb", "absent", "absent hurt"}
_NOT_OUT_ID = 1  # dismissalTypeId == 1 means "not out" in GR API


def _overs_str(overs_raw) -> str:
    """Convert oversBowled string/float or balls int to 'X.Y' display string."""
    if overs_raw is None:
        return "0"
    if isinstance(overs_raw, str) and "." in overs_raw:
        return overs_raw
    try:
        balls = int(float(str(overs_raw)) * 6) if "." not in str(overs_raw) else None
        if balls is not None:
            return f"{balls // 6}.{balls % 6}"
        # already X.Y format
        return str(overs_raw)
    except (TypeError, ValueError):
        return str(overs_raw)


async def _org_logo_for_team(team_name: str, db: AsyncSession) -> str | None:
    """Try to find a matching org in the DB and return its logo URL."""
    from sqlalchemy import or_, func
    words = [w for w in re.split(r"\W+", team_name.upper()) if len(w) > 3]
    if not words:
        return None
    conditions = [func.upper(Organisation.name).contains(w) for w in words[:3]]
    res = await db.execute(
        select(Organisation)
        .where(or_(*conditions))
        .where(or_(Organisation.logo_url.isnot(None), Organisation.logo_data.isnot(None)))
        .limit(1)
    )
    org = res.scalars().first()
    if not org:
        return None
    if org.logo_url:
        return org.logo_url
    return f"/api/images/organisations/{org.id}/logo"


def _team_id_from_inn(inn: dict) -> str | None:
    for k in ("battingTeamId", "teamId"):
        v = inn.get(k)
        if v:
            return str(v).lower()
    for k in ("battingTeam", "team"):
        obj = inn.get(k)
        if isinstance(obj, dict) and obj.get("id"):
            return str(obj["id"]).lower()
    return None


@router.get("/social/scorecard/{match_id}", dependencies=[Depends(require_module("socials"))])
async def get_social_scorecard(match_id: str, db: AsyncSession = Depends(get_db), _user=Depends(get_current_user)):
    """Fetch a Grassroots scorecard and return it in the social template format.

    Gated behind the BetterSocials module (require_module).
    """
    try:
        return await _get_social_scorecard_inner(match_id, db)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social scorecard %s failed", match_id)
        raise HTTPException(500, f"Scorecard parse error: {exc}") from exc


async def _get_social_scorecard_inner(match_id: str, db: AsyncSession):
    raw = await get_match_scorecard(match_id)
    if raw is None:
        raise HTTPException(404, "Scorecard not found — match may be PlayHQ-only or not yet completed")

    match_summary = raw.get("matchSummary") or {}
    teams_raw = raw.get("teams") or []
    innings_list = raw.get("innings") or []

    # Identify home team from matchSummary.teams[].isHome
    summary_teams = match_summary.get("teams") or []
    home_id = next((str(t.get("id", "")).lower() for t in summary_teams if t.get("isHome")), None)

    def find_team(tid):
        if tid:
            t = next((t for t in teams_raw if str(t.get("id", "")).lower() == tid), None)
            if t:
                return t
        return teams_raw[0] if teams_raw else {}

    home_team_raw = find_team(home_id)
    away_id = next((str(t.get("id", "")).lower() for t in teams_raw if str(t.get("id", "")).lower() != home_id), None)
    away_team_raw = find_team(away_id)

    # Map innings to teams: home team batting = innings where battingTeamId == home_id
    home_inn = next((i for i in innings_list if _team_id_from_inn(i) == home_id), innings_list[0] if innings_list else {})
    away_inn = next((i for i in innings_list if _team_id_from_inn(i) != home_id), innings_list[1] if len(innings_list) > 1 else {})

    # Collect all participantIds to look up names from DB
    all_pids: set[str] = set()
    for inn in [home_inn, away_inn]:
        for row in (inn.get("batting") or []):
            if row.get("participantId"):
                all_pids.add(row["participantId"])
        for row in (inn.get("bowling") or []):
            if row.get("participantId"):
                all_pids.add(row["participantId"])

    # Build merge-redirect map: removed player UUID → kept player UUID (transitive, no cycles)
    try:
        merge_res = await db.execute(
            text("SELECT removed_player_id::text AS r, kept_player_id::text AS k FROM merge_logs WHERE undone_at IS NULL")
        )
        raw_merge = {row.r: row.k for row in merge_res.mappings().all()}
    except Exception:
        log.exception("merge_logs lookup failed for scorecard %s", match_id)
        await db.rollback()
        raw_merge = {}

    def _resolve_merge(rid, seen=None):
        seen = seen or set()
        if rid in seen or rid not in raw_merge:
            return rid
        seen.add(rid)
        return _resolve_merge(raw_merge[rid], seen)

    merged_away: dict[str, str] = {k: _resolve_merge(k) for k in raw_merge}

    # Include kept-player IDs in the DB query so redirected lookups succeed
    for removed_id in list(all_pids):
        kept = merged_away.get(removed_id.lower())
        if kept:
            all_pids.add(kept)

    name_map: dict[str, tuple[str, str]] = {}  # participantId -> (first, last)
    if all_pids:
        pid_uuids = []
        for p in all_pids:
            try:
                pid_uuids.append(uuid.UUID(p))
            except (ValueError, AttributeError, TypeError):
                continue
        if pid_uuids:
            try:
                res = await db.execute(select(Player).where(Player.id.in_(pid_uuids)))
                for p in res.scalars().all():
                    raw_name = (p.display_name or p.name or "").strip()
                    if ", " in raw_name:
                        # "Surname, Firstname" → last="SURNAME", first="Firstname"
                        last_part, first_part = raw_name.split(", ", 1)
                        first = first_part.strip()
                        last = last_part.strip().upper()
                    else:
                        parts = raw_name.split()
                        if len(parts) >= 2:
                            first = " ".join(parts[1:])
                            last = parts[0].upper()
                        else:
                            first = ""
                            last = parts[0].upper() if parts else ""
                    last = last.rstrip(".,;:")
                    name_map[str(p.id).lower()] = (first, last)
            except Exception:
                log.exception("player name lookup failed for scorecard %s", match_id)
                await db.rollback()

    # Build roster name map from team player lists (covers opposition players not in our DB)
    roster_name_map: dict[str, tuple[str, str]] = {}
    for team_r in teams_raw:
        for rp in (team_r.get("players") or []):
            pid = rp.get("participantId") or ""
            if not pid:
                continue
            dn = rp.get("displayName") or rp.get("name") or ""
            if dn:
                dn = dn.strip()
                if ", " in dn:
                    lp, fp = dn.split(", ", 1)
                    roster_name_map[pid.lower()] = (fp.strip(), lp.strip().upper().rstrip(".,;:"))
                else:
                    pts = dn.split()
                    if len(pts) >= 2:
                        roster_name_map[pid.lower()] = (" ".join(pts[1:]), pts[0].upper().rstrip(".,;:"))
                    else:
                        roster_name_map[pid.lower()] = ("", dn.upper().rstrip(".,;:"))

    def get_name(pid: str) -> tuple[str, str]:
        key = str(pid).lower()
        if key in name_map:
            return name_map[key]
        kept_id = merged_away.get(key)
        if kept_id and kept_id.lower() in name_map:
            return name_map[kept_id.lower()]
        return roster_name_map.get(key) or ("", "")

    def parse_batting(batting_rows: list) -> list:
        rows = sorted(batting_rows, key=lambda b: b.get("batOrder") or 99)
        result = []
        for i, b in enumerate(rows):
            dt = (b.get("dismissalType") or "").lower()
            dt_id = b.get("dismissalTypeId") or 0
            dnb = dt in _DNB_TYPES
            not_out = (dt_id == _NOT_OUT_ID or dt == "not out") and not dnb
            pid = b.get("participantId") or ""
            first, last = get_name(pid)
            runs = int(b.get("runsScored") or 0)
            balls = int(b.get("ballsFaced") or 0)
            result.append({
                "num": i + 1,
                "first": first,
                "last": last,
                "r": runs,
                "b": balls,
                "fours": int(b.get("foursScored") or 0),
                "sixes": int(b.get("sixesScored") or 0),
                "sr": round(runs / balls * 100, 2) if balls > 0 else 0,
                "out": dt if not dnb and not not_out else ("not out" if not_out else "did not bat"),
                "notOut": not_out,
                "didNotBat": dnb,
                "role": None,
            })
        return result

    def parse_bowling(bowling_rows: list) -> list:
        result = []
        for bw in bowling_rows:
            pid = bw.get("participantId") or ""
            first, last = get_name(pid)
            overs_raw = bw.get("oversBowled")
            overs = _overs_str(overs_raw)
            runs = int(bw.get("runsConceded") or 0)
            try:
                o_float = float(str(overs_raw or 0).replace(",", "."))
                whole = int(o_float)
                part = round((o_float - whole) * 10)
                o_float_real = whole + part / 6
            except (TypeError, ValueError):
                o_float_real = 0
            result.append({
                "first": first,
                "last": last,
                "o": overs,
                "m": int(bw.get("maidensBowled") or 0),
                "r": runs,
                "w": int(bw.get("wicketsTaken") or 0),
                "econ": round(runs / o_float_real, 2) if o_float_real > 0 else 0,
            })
        return result

    def parse_extras(inn: dict) -> dict:
        # GR top-level fields confirmed from games router (523-538)
        return {
            "total": inn.get("totalExtras") or 0,
            "b": inn.get("byesRuns") or 0,
            "lb": inn.get("legByesRuns") or 0,
            "nb": inn.get("noBalls") or 0,
            "wd": inn.get("wideBalls") or 0,
        }

    def team_totals(inn: dict, batting: list):
        # GR authoritative fields (confirmed from games router)
        rs_raw = inn.get("runsScored")
        total_runs = int(rs_raw) if rs_raw is not None else (
            sum(b["r"] for b in batting if not b["didNotBat"])
            + int(inn.get("totalExtras") or 0)
        )
        wkts_raw = inn.get("numberOfWicketsFallen")
        total_wkts = int(wkts_raw) if wkts_raw is not None else sum(
            1 for b in batting if not b["notOut"] and not b["didNotBat"]
        )
        overs_raw = inn.get("totalOvers") or inn.get("overs")
        overs = _overs_str(overs_raw) if overs_raw else "0"
        try:
            o_float = float(str(overs_raw or 0))
            whole = int(o_float)
            part = round((o_float - whole) * 10)
            o_real = whole + part / 6
        except (TypeError, ValueError):
            o_real = 0
        rr = round(total_runs / o_real, 2) if o_real > 0 else 0
        return str(total_runs), total_wkts, overs, str(rr)

    def build_team(team_raw: dict, bat_inn: dict, bowl_inn: dict, default_color: str) -> dict:
        # bat_inn  = innings where THIS team batted  → use for batting rows + extras + totals
        # bowl_inn = innings where OPPONENT batted   → use for bowling rows (team bowled in opp innings)
        batting = parse_batting(bat_inn.get("batting") or [])
        bowling = parse_bowling(bowl_inn.get("bowling") or [])
        name = (team_raw.get("displayName") or team_raw.get("name") or "TEAM").upper()
        short = "".join(w[0] for w in name.split()[:3])
        total, wickets, overs, rr = team_totals(bat_inn, batting)
        logo_url = (team_raw.get("logoUrl") or team_raw.get("logo") or
                    team_raw.get("imageUrl") or team_raw.get("image") or None)
        return {
            "name": name,
            "short": short,
            "color": default_color,
            "logo": logo_url,
            "monogram": short,
            "total": total,
            "wickets": wickets,
            "overs": overs,
            "runRate": rr,
            "batting": batting,
            "bowling": bowling,
            "extras": parse_extras(bat_inn),
        }

    home = build_team(home_team_raw, bat_inn=home_inn, bowl_inn=away_inn, default_color="#1a4eb8")
    away = build_team(away_team_raw, bat_inn=away_inn, bowl_inn=home_inn, default_color="#cc1f2c")

    # Fallback logo lookup: if GR didn't provide a logo, match against orgs in our DB
    if not home.get("logo"):
        home["logo"] = await _org_logo_for_team(home["name"], db)
    if not away.get("logo"):
        away["logo"] = await _org_logo_for_team(away["name"], db)

    result_text = (match_summary.get("result") or match_summary.get("statusText") or "RESULT").upper()
    venue = (match_summary.get("venue") or {}).get("name") or ""
    date_raw = match_summary.get("dateTimeUTC") or match_summary.get("startDateTime") or ""
    date_str = date_raw[:10] if date_raw else ""
    grade_obj = raw.get("grade") or match_summary.get("grade") or {}
    grade_name = (grade_obj.get("name") or "").upper()
    round_raw = match_summary.get("round") or raw.get("round") or ""
    if isinstance(round_raw, dict):
        round_name = round_raw.get("name") or round_raw.get("shortName") or ""
    else:
        round_name = str(round_raw)

    meta = {
        "competition": grade_name,
        "round": f"ROUND {round_name}".strip() if round_name else "ROUND",
        "format": "T20",
        "overs": 20,
        "venue": venue,
        "date": date_str,
        "toss": "",
        "result": result_text,
        "series": "",
        "motm": {"first": "", "last": "", "team": "", "line": ""},
    }

    return {"meta": meta, "home": home, "away": away}
