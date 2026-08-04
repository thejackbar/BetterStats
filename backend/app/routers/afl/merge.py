"""Merge Grades + Merge Players.

Merge Grades touches only ``grades``/``grade_merge_logs`` (a name-alias
table, org-scoped) and never a stat table, so it's ported near-verbatim from
cricket's routers/admin.py — 100% sport-agnostic.

Merge Players walks AFL's own two stat tables — ``afl_player_game_lines``
(the source of truth, reassigned directly) and ``afl_player_season_stats``
(fully derived from game lines, so rather than hand-merging summed totals a
merge just reassigns the game lines and calls sync's own rollup to
recompute season stats correctly for both players in one step — see
``_rollup_season_stats`` below). Candidate-finding (exact + fuzzy name
matching) is ported near-verbatim from cricket's routers/admin.py since it's
pure Python string matching with no stat-table coupling at all.
"""
import json
import re
import uuid
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MERGES, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services.afl.sync import _rollup_season_stats
from app.services.audit_log import log_activity
from app.services.player_aliases import seed_alias_on_rename

router = APIRouter(prefix="/club-admin", tags=["afl-merge"])


def _resolve_canonical_grade(chain: dict[str, str], name: str, _seen: set | None = None) -> str:
    """Follow the alias chain to its root, guarding against a cycle."""
    seen = _seen or set()
    if name in seen:
        return name
    seen.add(name)
    nxt = chain.get(name)
    if nxt is None:
        return name
    return _resolve_canonical_grade(chain, nxt, seen)


class MergeGradesRequest(BaseModel):
    alias_name: str
    canonical_name: str


@router.post("/merge-grades")
async def merge_grades(
    req: MergeGradesRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    """Mark `alias_name` as a variant of `canonical_name` for this club."""
    alias = req.alias_name.strip()
    canonical = req.canonical_name.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="Both grade names are required")
    if alias == canonical:
        raise HTTPException(status_code=400, detail="Alias and canonical grade are the same")

    org_id = str(club.id)
    existing = await db.execute(text("""
        SELECT alias_name, canonical_name FROM grade_merge_logs
        WHERE org_id = :org_id AND undone_at IS NULL
    """), {"org_id": org_id})
    chain = {r["alias_name"]: r["canonical_name"] for r in existing.mappings().all()}

    resolved_canonical = _resolve_canonical_grade(chain, canonical)
    if resolved_canonical == alias:
        raise HTTPException(status_code=400, detail="That merge would create a cycle")

    await db.execute(text("""
        UPDATE grade_merge_logs SET canonical_name = :new_canonical
        WHERE org_id = :org_id AND undone_at IS NULL AND canonical_name = :alias
    """), {"org_id": org_id, "new_canonical": resolved_canonical, "alias": alias})

    await db.execute(text("""
        UPDATE grade_merge_logs SET undone_at = NOW()
        WHERE org_id = :org_id AND undone_at IS NULL AND alias_name = :alias
    """), {"org_id": org_id, "alias": alias})

    await db.execute(text("""
        INSERT INTO grade_merge_logs (org_id, alias_name, canonical_name)
        VALUES (:org_id, :alias, :canonical)
    """), {"org_id": org_id, "alias": alias, "canonical": resolved_canonical})

    await log_activity(
        db, org_id=org_id, user_id=current_user.id,
        action="merge_grades", target_type="grade", target_id=resolved_canonical,
        details={"alias_name": alias, "canonical_name": resolved_canonical},
    )
    await db.commit()
    return {"status": "merged", "alias": alias, "canonical": resolved_canonical}


@router.get("/grade-merge-history")
async def grade_merge_history(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT id, merged_at, alias_name, canonical_name, undone_at
        FROM grade_merge_logs WHERE org_id = :org_id
        ORDER BY merged_at DESC LIMIT 100
    """), {"org_id": str(club.id)})
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


@router.post("/undo-grade-merge")
async def undo_grade_merge(
    req: UndoGradeMergeRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        UPDATE grade_merge_logs SET undone_at = NOW()
        WHERE id = :id AND org_id = :org_id AND undone_at IS NULL
        RETURNING id
    """), {"id": req.merge_log_id, "org_id": str(club.id)})
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Merge log not found or already undone")

    await log_activity(
        db, org_id=str(club.id), user_id=current_user.id,
        action="undo_merge_grades", target_type="grade_merge_log", target_id=str(req.merge_log_id),
    )
    await db.commit()
    return {"status": "undone"}


@router.get("/grade-names")
async def list_grade_names(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Distinct grade names for this club, for the merge picker."""
    rows = await db.execute(text("""
        SELECT DISTINCT gr.name FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org
        ORDER BY gr.name
    """), {"org": str(club.id)})
    return {"names": [r[0] for r in rows.all()]}


# ─── Merge Players ────────────────────────────────────────────────────────────

_REDACTED_NAME_RE = re.compile(r"^\*+$")


def _normalise(name: str) -> str:
    """'Last, First' → 'first last', collapse whitespace, lowercase."""
    name = (name or "").strip()
    if "," in name:
        parts = name.split(",", 1)
        name = f"{parts[1].strip()} {parts[0].strip()}".strip()
    return re.sub(r"\s+", " ", name).strip().lower()


def _is_redacted_name(name: str) -> bool:
    return bool(_REDACTED_NAME_RE.match((name or "").strip()))


async def _enrich_player(db: AsyncSession, p: Player) -> dict:
    stats_res = await db.execute(text("""
        SELECT COALESCE(SUM(games),0) AS games, COALESCE(SUM(goals),0) AS goals,
               COALESCE(SUM(behinds),0) AS behinds, COALESCE(SUM(bog_count),0) AS bogs,
               COUNT(*) AS season_rows
        FROM afl_player_season_stats WHERE player_id = :pid AND grade_id IS NULL
    """), {"pid": str(p.id)})
    row = stats_res.mappings().first() or {}
    lines_res = await db.execute(text(
        "SELECT COUNT(*) FROM afl_player_game_lines WHERE player_id = :pid"), {"pid": str(p.id)})
    return {
        "id": str(p.id),
        "name": p.display_name,
        "playhq_id": p.playhq_id,
        "seasons_count": row.get("season_rows", 0),
        "total_games": row.get("games", 0),
        "total_goals": row.get("goals", 0),
        "total_behinds": row.get("behinds", 0),
        "total_bogs": row.get("bogs", 0),
        "game_lines_count": lines_res.scalar() or 0,
    }


FUZZY_MERGE_THRESHOLD = 0.90
MAX_FUZZY_PAIRS = 500


def _fuzzy_name_pairs(players: list, ignored: set) -> list:
    """Near-miss spelling pairs the exact-name grouping can't see — blocked by
    the first character of the normalised name so this stays fast on a large
    roster. Never bulk-mergeable — always needs a human to confirm."""
    blocks: dict[str, list] = {}
    for p in players:
        key = _normalise(p.name)
        if not key or _is_redacted_name(p.name):
            continue
        blocks.setdefault(key[:1], []).append((p, key))

    seen_pairs: set = set()
    scored = []
    for block in blocks.values():
        for i in range(len(block)):
            p1, k1 = block[i]
            for j in range(i + 1, len(block)):
                p2, k2 = block[j]
                if k1 == k2 or abs(len(k1) - len(k2)) > 3:
                    continue
                ratio = SequenceMatcher(None, k1, k2).ratio()
                if ratio < FUZZY_MERGE_THRESHOLD:
                    continue
                pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
                if pair_key in ignored or pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                scored.append((ratio, p1, p2))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:MAX_FUZZY_PAIRS]


@router.get("/merge-candidates")
async def get_merge_candidates(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    result = await db.execute(select(Player).where(Player.organisation_id == club.id))
    players = result.scalars().all()

    ignored_res = await db.execute(text(
        "SELECT player_a_id::text, player_b_id::text FROM afl_merge_pair_ignores WHERE org_id = :org_id"
    ), {"org_id": org_id})
    ignored = {(r.player_a_id, r.player_b_id) for r in ignored_res.mappings().all()}

    groups: dict[str, list] = {}
    for p in players:
        groups.setdefault(_normalise(p.name), []).append(p)

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
                    "kind": "exact", "normalised_name": key,
                    "redacted": _is_redacted_name(enriched[i]["name"]) or _is_redacted_name(enriched[j]["name"]),
                    "player_a": enriched[i], "player_b": enriched[j],
                })

    for ratio, p1, p2 in _fuzzy_name_pairs(players, ignored):
        a, b = await _enrich_player(db, p1), await _enrich_player(db, p2)
        candidate_pairs.append({
            "kind": "fuzzy", "confidence": round(ratio, 2), "normalised_name": None,
            "redacted": False, "player_a": a, "player_b": b,
        })

    return candidate_pairs


@router.get("/player-info/{player_id}")
async def get_player_info(
    player_id: str,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(Player, uuid.UUID(player_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    return await _enrich_player(db, p)


class IgnorePairRequest(BaseModel):
    player_a_id: str
    player_b_id: str


@router.post("/ignore-pair")
async def ignore_pair(
    req: IgnorePairRequest,
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    a, b = sorted([req.player_a_id, req.player_b_id])
    await db.execute(text("""
        INSERT INTO afl_merge_pair_ignores (org_id, player_a_id, player_b_id)
        VALUES (:org_id, :a, :b) ON CONFLICT (org_id, player_a_id, player_b_id) DO NOTHING
    """), {"org_id": str(club.id), "a": a, "b": b})
    await db.commit()
    return {"status": "ignored"}


@router.get("/merge-history")
async def get_merge_history(
    club: Organisation = Depends(get_current_club),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT id, merged_at, keep_player_id, keep_player_name,
               removed_player_id, removed_player_name, undone_at
        FROM afl_merge_logs WHERE org_id = :org_id
        ORDER BY merged_at DESC LIMIT 2000
    """), {"org_id": str(club.id)})
    return [
        {
            "id": r.id, "merged_at": r.merged_at.isoformat() if r.merged_at else None,
            "keep_player_id": str(r.keep_player_id), "keep_player_name": r.keep_player_name,
            "removed_player_id": str(r.removed_player_id), "removed_player_name": r.removed_player_name,
            "undone": r.undone_at is not None,
        }
        for r in rows.mappings().all()
    ]


class MergePlayersRequest(BaseModel):
    keep_player_id: str
    remove_player_id: str


async def _merge_players_core(
    db: AsyncSession, keep_id: uuid.UUID, remove_id: uuid.UUID, org_id: uuid.UUID, current_user: User,
) -> dict:
    keep = await db.get(Player, keep_id)
    remove = await db.get(Player, remove_id)
    if not keep or not remove:
        raise HTTPException(status_code=404, detail="Player not found")
    if keep.organisation_id != org_id or remove.organisation_id != org_id:
        raise HTTPException(status_code=400, detail="Players must belong to this club")
    if keep_id == remove_id:
        raise HTTPException(status_code=400, detail="Cannot merge a player with itself")

    try:
        line_rows = (await db.execute(text(
            "SELECT id FROM afl_player_game_lines WHERE player_id = :rid"
        ), {"rid": str(remove_id)})).scalars().all()
        line_ids = [str(i) for i in line_rows]

        if line_ids:
            await db.execute(text(
                "UPDATE afl_player_game_lines SET player_id = :kid WHERE player_id = :rid"
            ), {"kid": str(keep_id), "rid": str(remove_id)})

        removed_playhq_id = remove.playhq_id
        removed_display_name = remove.display_name
        keep_original_playhq_id = keep.playhq_id

        await db.flush()
        await db.execute(text("DELETE FROM players WHERE id = :rid"), {"rid": str(remove_id)})
        if not keep.playhq_id and removed_playhq_id:
            keep.playhq_id = removed_playhq_id

        await seed_alias_on_rename(db, org_id, keep_id, removed_display_name)

        await db.execute(text("""
            INSERT INTO afl_merge_logs
                (org_id, keep_player_id, keep_player_name, removed_player_id, removed_player_name,
                 removed_player_playhq_id, keep_original_playhq_id, line_ids)
            VALUES (:org, :kid, :kname, :rid, :rname, :rphq, :kphq, CAST(:line_ids AS JSONB))
        """), {
            "org": str(org_id), "kid": str(keep_id), "kname": keep.display_name,
            "rid": str(remove_id), "rname": removed_display_name,
            "rphq": removed_playhq_id, "kphq": keep_original_playhq_id,
            "line_ids": json.dumps(line_ids),
        })

        # afl_player_season_stats is fully derived from game lines (delete +
        # reinsert per org on every sync) — rather than hand-merging summed
        # totals, just recompute it now from the now-correctly-attributed
        # game lines so both players' totals are correct immediately.
        await _rollup_season_stats(db, org_id)

        await log_activity(
            db, org_id=org_id, user_id=current_user.id,
            action="merge_players", target_type="player", target_id=str(keep_id),
            details={"removed_player_id": str(remove_id), "removed_player_name": removed_display_name,
                    "game_lines_moved": len(line_ids)},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Merge failed: {exc}") from exc

    return {"status": "merged", "kept_player_id": str(keep_id), "removed_player_id": str(remove_id)}


@router.post("/merge-players")
async def merge_players(
    req: MergePlayersRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    return await _merge_players_core(
        db, uuid.UUID(req.keep_player_id), uuid.UUID(req.remove_player_id), club.id, current_user)


class UndoMergePlayersRequest(BaseModel):
    merge_log_id: int


@router.post("/undo-merge-players")
async def undo_merge_players(
    req: UndoMergePlayersRequest,
    club: Organisation = Depends(get_current_club),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    log_row = (await db.execute(text(
        "SELECT * FROM afl_merge_logs WHERE id = :id AND org_id = :org"
    ), {"id": req.merge_log_id, "org": org_id})).mappings().first()
    if not log_row:
        raise HTTPException(status_code=404, detail="Merge log not found")
    if log_row["undone_at"] is not None:
        raise HTTPException(status_code=400, detail="This merge was already undone")

    keep_id = log_row["keep_player_id"]
    remove_id = log_row["removed_player_id"]
    keep = await db.get(Player, keep_id)
    if not keep:
        raise HTTPException(status_code=404, detail="The kept player no longer exists — can't undo")

    if log_row["keep_original_playhq_id"] is None and log_row["removed_player_playhq_id"]:
        keep.playhq_id = None
        await db.flush()

    await db.execute(text("""
        INSERT INTO players (id, name, organisation_id, playhq_id)
        VALUES (:id, :name, :org, :phq)
        ON CONFLICT (id) DO NOTHING
    """), {
        "id": str(remove_id), "name": log_row["removed_player_name"],
        "org": org_id, "phq": log_row["removed_player_playhq_id"],
    })

    line_ids = log_row["line_ids"] or []
    if isinstance(line_ids, str):
        line_ids = json.loads(line_ids)
    if line_ids:
        await db.execute(text(
            "UPDATE afl_player_game_lines SET player_id = :rid WHERE id = ANY(:ids)"
        ), {"rid": str(remove_id), "ids": [uuid.UUID(i) for i in line_ids]})

    await _rollup_season_stats(db, club.id)

    await db.execute(text(
        "UPDATE afl_merge_logs SET undone_at = NOW() WHERE id = :id"
    ), {"id": req.merge_log_id})
    await log_activity(
        db, org_id=org_id, user_id=current_user.id,
        action="undo_merge_players", target_type="player", target_id=str(keep_id),
        details={"restored_player_id": str(remove_id)},
    )
    await db.commit()
    return {"status": "undone", "restored_player_id": str(remove_id)}
