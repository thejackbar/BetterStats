"""Import Stats — historical CSV import.

For seasons PlayHQ's discover API doesn't surface (older competitions, or a
club not yet registered when those games were played) — the same class of
gap cricket's own PlayHQ Partner API has, which is why cricket built the
same kind of tool. Flow: upload → parse + auto-map columns → match player
names (exact/close, with bulk approval) → confirm season → confirm grade →
confirm.

Deliberately simpler than cricket's BetterImport (routers/imports.py):
cricket's sync can have *partial* per-season coverage (a Grassroots pull that
stopped partway), so it needs a full "GR wins per season, residual catches
the gap" reconciler (services/import_reconcile.py) that merges at the
individual-metric level. AFL's sync either has a season/grade fully or not
at all (a one-shot PlayHQ discover call, not an incremental scrape), so a
simpler rule is honest and correct: imported rows live in their own table
(``afl_imported_stats``), and a combined read SUMS synced + imported totals
per player, EXCLUDING any (player, season) the sync already has games for —
sync always wins where it has data; import only fills a genuine gap. Reuses
the generic, DB-free matching engine from ``services/import_ingest`` (
``parse_upload``/``match_players``/``match_seasons``/``match_grades`` — none
of that is cricket-specific) and the shared ``ImportBatch`` model (already
sport-agnostic, already exists in the AFL DB via create_all).
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Grade, ImportBatch, Organisation, Player, Season, User, get_db
from app.routers.auth import get_current_club
from app.services import import_ingest as ingest
from app.services.afl.grade_labels import suggest_category
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/imports", tags=["afl-imports"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

STAT_FIELDS = ("games_played", "goals", "behinds", "bog_count", "captain_games",
               "club_bf_votes", "comp_bf_votes")
KEY_FIELDS = ("player_name", "season_label", "grade_label")
ALL_FIELDS = KEY_FIELDS + STAT_FIELDS

SYNONYMS = {
    "player_name": ["player", "name", "player name", "full name"],
    "season_label": ["season", "year", "yr", "season year"],
    "grade_label": ["grade", "team", "division", "comp", "competition"],
    "games_played": ["games", "matches", "gp", "games played", "played", "m"],
    "goals": ["goals", "g", "goal"],
    "behinds": ["behinds", "b", "behind"],
    "bog_count": ["bog", "boG", "best on ground", "b.o.g"],
    "captain_games": ["captain", "capt", "c", "captain games"],
    # Two distinct historical tallies clubs commonly track alongside season
    # stats: votes in the CLUB's own internal best & fairest count, vs votes
    # in the wider association/league's best & fairest — never the same
    # number. Kept separate from bog_count (an actual best-on-ground TALLY,
    # not a vote count) rather than folded in as a synonym of it.
    "club_bf_votes": ["club bf votes", "club b&f votes", "clubbfvotes", "club votes",
                       "b&f votes", "bf votes", "votes", "best and fairest votes"],
    "comp_bf_votes": ["comp bf votes", "compbfvotes", "competition bf votes",
                       "comp b&f votes", "competition b&f votes", "comp votes",
                       "association votes", "league votes", "league medal votes"],
}


# ── column auto-mapping (AFL-flavoured copy of import_ingest's algorithm —
#    that module's own suggest_column_mapping is hardcoded to cricket's own
#    SYNONYMS dict, so it can't be reused directly for a different field set) ──

def _norm(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(h).lower())).strip()


def _field_score(nh: str, syns: list) -> float:
    if nh in syns:
        return 1.0
    return max((SequenceMatcher(None, nh, syn).ratio() for syn in syns), default=0.0)


def _suggest_column_mapping(headers: list) -> dict:
    per_header = {}
    for h in headers:
        nh = _norm(h)
        if not nh:
            continue
        best_field, best_score = None, 0.0
        for field, syns in SYNONYMS.items():
            s = _field_score(nh, [_norm(x) for x in syns])
            if s > best_score:
                best_field, best_score = field, s
        if best_field and best_score >= 0.6:
            per_header[h] = (best_field, best_score)
    mapping: dict = {}
    for h, (field, score) in per_header.items():
        if field not in mapping or score > mapping[field]["confidence"]:
            mapping[field] = {"column": h, "confidence": round(score, 2)}
    return mapping


def _col(mapping: dict, field: str) -> Optional[str]:
    v = mapping.get(field)
    if isinstance(v, dict):
        return v.get("column")
    return v or None


def _row_to_truth(row: dict, mapping: dict) -> dict:
    return {f: (ingest.to_int(row.get(_col(mapping, f))) or 0) if _col(mapping, f) else 0
            for f in STAT_FIELDS}


async def _org_players(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(select(Player).where(Player.organisation_id == org_id))).scalars().all()
    return [(str(p.id), p.display_name or p.name or "") for p in rows]


async def _org_seasons(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(select(Season).where(Season.organisation_id == org_id))).scalars().all()
    return [(str(s.id), s.name or "", s.year) for s in rows]


async def _org_grade_names(db: AsyncSession, org_id) -> list:
    rows = await db.execute(text("""
        SELECT DISTINCT gr.name FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org ORDER BY gr.name
    """), {"org": str(org_id)})
    return [r[0] for r in rows.all()]


def _apply_player_overrides(matches: dict, overrides: dict) -> None:
    for name, choice in (overrides or {}).items():
        if name not in matches:
            matches[name] = {"candidates": []}
        if choice == "__skip__":
            matches[name].update(player_id=None, status="skip")
        elif choice == "__new__":
            matches[name].update(player_id=None, status="new")
        elif choice:
            matches[name].update(player_id=str(choice), status="manual", confidence=1.0)


def _apply_season_overrides(matches: dict, overrides: dict) -> None:
    for label, choice in (overrides or {}).items():
        if label not in matches:
            matches[label] = {"candidates": []}
        if choice == "__unassigned__":
            matches[label].update(season_id=None, is_prior=True, status="unassigned")
        elif choice:
            matches[label].update(season_id=str(choice), is_prior=False, status="manual")


def _apply_grade_overrides(matches: dict, overrides: dict) -> None:
    for label, choice in (overrides or {}).items():
        if label not in matches:
            matches[label] = {"candidates": []}
        if choice == "__own__":
            matches[label].update(grade_name=label, status="own")
        elif choice:
            matches[label].update(grade_name=str(choice), status="manual")


class ResolveRequest(BaseModel):
    rows: list[dict] = []
    mapping: dict = {}
    player_overrides: dict = {}
    season_overrides: dict = {}
    grade_overrides: dict = {}


class CommitRequest(ResolveRequest):
    filename: Optional[str] = None


async def _resolve(db: AsyncSession, org_id, req: ResolveRequest) -> dict:
    name_col = _col(req.mapping, "player_name")
    season_col = _col(req.mapping, "season_label")
    grade_col = _col(req.mapping, "grade_label")
    if not name_col:
        raise HTTPException(422, "No column is mapped to the player name.")

    names, season_labels, grade_labels = [], [], []
    for r in req.rows:
        nm = str(r.get(name_col, "")).strip()
        if nm and nm not in names:
            names.append(nm)
        if season_col:
            lb = str(r.get(season_col, "")).strip()
            if lb and lb not in season_labels:
                season_labels.append(lb)
        if grade_col:
            gl = str(r.get(grade_col, "")).strip()
            if gl and gl not in grade_labels:
                grade_labels.append(gl)

    players = await _org_players(db, org_id)
    seasons = await _org_seasons(db, org_id)
    grade_names = await _org_grade_names(db, org_id) if grade_col else []

    pmatch = ingest.match_players(names, players)
    _apply_player_overrides(pmatch, req.player_overrides)
    smatch = ingest.match_seasons(season_labels, seasons) if season_col else {}
    _apply_season_overrides(smatch, req.season_overrides)
    gmatch = ingest.match_grades(grade_labels, grade_names) if grade_col else {}
    _apply_grade_overrides(gmatch, req.grade_overrides)

    items_by_player: dict = {}
    new_items_by_name: dict = {}
    name_by_pid: dict = {}
    skipped_rows = 0

    def build_item(r):
        truth = _row_to_truth(r, req.mapping)
        lb = str(r.get(season_col, "")).strip() if season_col else None
        sm = smatch.get(lb) if lb else None
        season_id = (sm or {}).get("season_id")
        raw_grade = str(r.get(grade_col, "")).strip() if grade_col else None
        grade_name = (gmatch.get(raw_grade) or {}).get("grade_name") if raw_grade else None
        return {
            "season_id": uuid.UUID(season_id) if season_id else None,
            "season_label": lb, "grade_label": grade_name or raw_grade, **truth,
        }

    for r in req.rows:
        nm = str(r.get(name_col, "")).strip()
        if not nm:
            continue
        pm = pmatch.get(nm) or {}
        pid = pm.get("player_id")
        if pid:
            items_by_player.setdefault(pid, []).append(build_item(r))
            name_by_pid[pid] = nm
        elif pm.get("status") == "new":
            new_items_by_name.setdefault(nm, []).append(build_item(r))
        else:
            skipped_rows += 1

    # Flag rows whose (player, season) the sync already has games for — sync
    # always wins there, so these still import (stored) but won't count in
    # the combined Players-list total.
    already_synced_pairs: set = set()
    all_pids = [uuid.UUID(p) for p in items_by_player.keys()]
    if all_pids:
        season_ids = {it["season_id"] for items in items_by_player.values() for it in items if it["season_id"]}
        if season_ids:
            rows = await db.execute(text("""
                SELECT player_id, season_id FROM afl_player_season_stats
                WHERE player_id = ANY(:pids) AND season_id = ANY(:sids)
                  AND grade_id IS NULL AND games > 0
            """), {"pids": all_pids, "sids": list(season_ids)})
            already_synced_pairs = {(str(r.player_id), str(r.season_id)) for r in rows}

    preview = []
    for pid, items in items_by_player.items():
        overlapping = any((pid, str(it["season_id"])) in already_synced_pairs for it in items if it["season_id"])
        preview.append({
            "player_id": pid, "player_name": name_by_pid.get(pid), "new": False,
            "rows": len(items),
            "games": sum(it["games_played"] for it in items),
            "goals": sum(it["goals"] for it in items),
            "behinds": sum(it["behinds"] for it in items),
            "club_bf_votes": sum(it["club_bf_votes"] for it in items),
            "comp_bf_votes": sum(it["comp_bf_votes"] for it in items),
            "already_synced_overlap": overlapping,
        })
    for nm, items in new_items_by_name.items():
        preview.append({
            "player_id": None, "player_name": nm, "new": True, "rows": len(items),
            "games": sum(it["games_played"] for it in items),
            "goals": sum(it["goals"] for it in items),
            "behinds": sum(it["behinds"] for it in items),
            "club_bf_votes": sum(it["club_bf_votes"] for it in items),
            "comp_bf_votes": sum(it["comp_bf_votes"] for it in items),
            "already_synced_overlap": False,
        })
    preview.sort(key=lambda p: p["games"], reverse=True)

    warnings = []
    unresolved = [n for n, m in pmatch.items() if not m.get("player_id") and m.get("status") not in ("skip", "new")]
    if unresolved:
        warnings.append(f"{len(unresolved)} player name(s) need a match before import: "
                        + ", ".join(unresolved[:8]) + ("…" if len(unresolved) > 8 else ""))
    ambiguous = [n for n, m in pmatch.items() if m.get("status") == "ambiguous"]
    if ambiguous:
        warnings.append(f"{len(ambiguous)} name(s) match two players — merge those first: " + ", ".join(ambiguous[:5]))
    overlap_names = [p["player_name"] for p in preview if p["already_synced_overlap"]]
    if overlap_names:
        warnings.append("Already synced from PlayHQ for some season(s) shown for: "
                        + ", ".join(overlap_names[:5]) + " — those rows still import but won't be "
                          "double-counted in totals; the synced figures win.")

    return {
        "players": [{"raw_name": n, **m} for n, m in pmatch.items()],
        "seasons": [{"raw_label": lb, **m} for lb, m in smatch.items()],
        "grades": [{"raw_label": lb, **m} for lb, m in gmatch.items()],
        "grade_options": grade_names,
        "preview": preview,
        "warnings": warnings,
        "totals": {
            "rows": len(req.rows), "players_matched": len(items_by_player),
            "players_new": len(new_items_by_name), "players_unresolved": len(unresolved),
            "rows_skipped": skipped_rows,
        },
        "_items_by_player": items_by_player,
        "_new_names": [n for n, m in pmatch.items() if m.get("status") == "new"],
    }


@router.get("/seasons")
async def list_org_seasons(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The club's seasons for the Seasons step's full "search all seasons"
    picker — the auto-matched candidates already come back on each row from
    /resolve, but a manual full browse needs the whole list up front."""
    rows = await _org_seasons(db, club.id)
    return [{"id": sid, "name": name, "year": year} for sid, name, year in rows]


class SeasonCreate(BaseModel):
    name: str
    year: Optional[int] = None


@router.post("/seasons")
async def create_season(
    data: SeasonCreate,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """A season with no PlayHQ equivalent (a pre-sync era) — mirrors cricket's
    /club-admin/seasons (routers/manual_entries.py::create_manual_season).
    grassroots_id stays NULL, which is itself the "not from a sync" marker:
    every synced season carries the raw PlayHQ id there."""
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "Season name is required")
    existing = await db.execute(select(Season).where(
        Season.organisation_id == club.id, func.lower(Season.name) == name.lower(),
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"A season named '{name}' already exists — pick it from the list instead.")

    season = Season(id=uuid.uuid4(), organisation_id=club.id, grassroots_id=None, name=name, year=data.year)
    db.add(season)
    await db.flush()
    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="create_season",
        target_type="season", target_id=str(season.id), details={"name": name, "year": data.year},
    )
    await db.commit()
    return {"id": str(season.id), "name": season.name, "year": season.year}


@router.get("/template.csv")
async def template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Player Name", "Season", "Grade", "Games", "Goals", "Behinds", "BOG", "Captain",
                      "Club B&F Votes", "Comp B&F Votes"])
    writer.writerow(["Smith, John", "2019", "A Grade", "18", "12", "8", "2", "0", "12", "3"])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afl_historical_import_template.csv"},
    )


@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    parsed = ingest.parse_upload(file.filename or "", content)
    if not parsed["rows"]:
        raise HTTPException(400, "No data found in file")
    mapping = _suggest_column_mapping(parsed["headers"])
    return {"headers": parsed["headers"], "rows": parsed["rows"], "mapping": mapping,
            "row_count": len(parsed["rows"])}


@router.post("/resolve")
async def resolve(
    req: ResolveRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    resolved = await _resolve(db, club.id, req)
    resolved.pop("_items_by_player")
    resolved.pop("_new_names")
    return resolved


@router.post("/commit")
async def commit(
    req: CommitRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    resolved = await _resolve(db, club.id, req)
    items_by_player = resolved["_items_by_player"]
    new_names = set(resolved["_new_names"])

    batch = ImportBatch(
        id=uuid.uuid4(), organisation_id=club.id, filename=req.filename, status="committed",
        granularity="season", column_mapping={f: _col(req.mapping, f) for f in ALL_FIELDS if _col(req.mapping, f)},
        row_count=len(req.rows), created_by_user_id=current_user.id,
        committed_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    await db.flush()

    created_players = 0
    if new_names:
        name_col = _col(req.mapping, "player_name")
        new_pid_by_name: dict = {}
        for nm in new_names:
            p = Player(id=uuid.uuid4(), name=nm, organisation_id=club.id)
            db.add(p)
            new_pid_by_name[nm] = str(p.id)
            created_players += 1
        await db.flush()
        season_col = _col(req.mapping, "season_label")
        grade_col = _col(req.mapping, "grade_label")
        smatch = {s["raw_label"]: s for s in resolved["seasons"]}
        gmatch = {g["raw_label"]: g for g in resolved["grades"]}
        for r in req.rows:
            nm = str(r.get(name_col, "")).strip()
            if nm not in new_pid_by_name:
                continue
            truth = _row_to_truth(r, req.mapping)
            lb = str(r.get(season_col, "")).strip() if season_col else None
            sm = smatch.get(lb) if lb else None
            raw_grade = str(r.get(grade_col, "")).strip() if grade_col else None
            grade_name = (gmatch.get(raw_grade) or {}).get("grade_name") if raw_grade else None
            items_by_player.setdefault(new_pid_by_name[nm], []).append({
                "season_id": uuid.UUID(sm["season_id"]) if (sm or {}).get("season_id") else None,
                "season_label": lb, "grade_label": grade_name or raw_grade, **truth,
            })

    if not items_by_player:
        raise HTTPException(422, "Nothing to import — no rows matched a player. Resolve the player matches and try again.")

    pids = [uuid.UUID(p) for p in items_by_player.keys()]
    # Latest-upload-wins: replace this batch's players' prior imported rows.
    await db.execute(text("DELETE FROM afl_imported_stats WHERE organisation_id = :org AND player_id = ANY(:pids)"),
                     {"org": str(club.id), "pids": pids})

    # Promote a resolved (season, grade label) pair into a real, mergeable
    # Grade row — without this, an imported grade only ever existed as free
    # text on afl_imported_stats.grade_label, invisible to the grade filter,
    # Merge Grades, and everywhere else that reads the grades table. A grade
    # needs a season to hang off (grades.season_id), so a still-unassigned
    # row's label stays free-text only, same as before. Cached per commit so
    # the same (season, label) pair across many rows only looks up/creates once.
    grade_cache: dict = {}

    async def _resolve_grade_id(season_id, label):
        if not season_id or not label:
            return None
        key = (str(season_id), label.strip().lower())
        if key in grade_cache:
            return grade_cache[key]
        existing = await db.execute(select(Grade).where(
            Grade.season_id == season_id, func.lower(Grade.name) == label.strip().lower(),
        ))
        row = existing.scalar_one_or_none()
        if row is None:
            row = Grade(id=uuid.uuid4(), season_id=season_id, grassroots_id=None,
                        name=label.strip(), category=suggest_category(label))
            db.add(row)
            await db.flush()
        grade_cache[key] = row.id
        return row.id

    inserted = 0
    for pid_str, items in items_by_player.items():
        for it in items:
            grade_id = await _resolve_grade_id(it.get("season_id"), it.get("grade_label"))
            await db.execute(text("""
                INSERT INTO afl_imported_stats
                    (organisation_id, import_batch_id, player_id, season_id, season_label,
                     grade_label, grade_id, games_played, goals, behinds, bog_count, captain_games,
                     club_bf_votes, comp_bf_votes)
                VALUES (:org, :batch, :pid, :sid, :slabel, :glabel, :gid, :games, :goals, :behinds, :bog, :capt,
                        :club_votes, :comp_votes)
            """), {
                "org": str(club.id), "batch": str(batch.id), "pid": pid_str,
                "sid": str(it["season_id"]) if it["season_id"] else None,
                "slabel": it.get("season_label"), "glabel": it.get("grade_label"),
                "gid": str(grade_id) if grade_id else None,
                "games": it["games_played"], "goals": it["goals"], "behinds": it["behinds"],
                "bog": it["bog_count"], "capt": it["captain_games"],
                "club_votes": it["club_bf_votes"], "comp_votes": it["comp_bf_votes"],
            })
            inserted += 1

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="afl_import",
        target_type="import_batch", target_id=str(batch.id),
        details={"players": len(items_by_player), "rows": inserted, "players_created": created_players},
    )
    await db.commit()

    return {
        "batch_id": str(batch.id), "players_imported": len(items_by_player),
        "rows_written": inserted, "players_created": created_players,
        "rows_skipped": resolved["totals"]["rows_skipped"],
        "preview": resolved["preview"][:50],
    }


@router.get("")
async def list_imports(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ImportBatch).where(ImportBatch.organisation_id == club.id)
        .order_by(ImportBatch.created_at.desc())
    )).scalars().all()
    return [
        {
            "id": str(b.id), "filename": b.filename, "status": b.status,
            "row_count": b.row_count, "created_at": b.created_at.isoformat() if b.created_at else None,
            "committed_at": b.committed_at.isoformat() if b.committed_at else None,
            "undone_at": b.undone_at.isoformat() if b.undone_at else None,
        }
        for b in rows
    ]


@router.get("/{batch_id}/players")
async def list_import_players(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT i.player_id, COALESCE(p.display_name_override, p.name) AS player_name,
               i.season_label, i.grade_label, i.games_played, i.goals, i.behinds, i.bog_count,
               i.club_bf_votes, i.comp_bf_votes
        FROM afl_imported_stats i JOIN players p ON p.id = i.player_id
        WHERE i.import_batch_id = :batch AND i.organisation_id = :org
        ORDER BY player_name
    """), {"batch": batch_id, "org": str(club.id)})
    return [dict(r._mapping) for r in rows]


@router.post("/{batch_id}/undo")
async def undo_import(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    batch = await db.get(ImportBatch, uuid.UUID(batch_id))
    if not batch or batch.organisation_id != club.id:
        raise HTTPException(404, "Import batch not found")
    if batch.undone_at is not None:
        raise HTTPException(400, "This import was already undone")

    result = await db.execute(text(
        "DELETE FROM afl_imported_stats WHERE import_batch_id = :batch AND organisation_id = :org"
    ), {"batch": batch_id, "org": str(club.id)})
    batch.status = "undone"
    batch.undone_at = datetime.now(timezone.utc)

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="undo_afl_import",
        target_type="import_batch", target_id=batch_id,
    )
    await db.commit()
    return {"status": "undone", "rows_removed": result.rowcount}
