"""BetterImport — overlap-safe historical CSV/XLSX import (onboarding tool).

Flow (stateless until commit):
  1. POST /preview        — upload a file → parsed grid + auto column mapping.
  2. POST /resolve        — {rows, mapping, overrides} → matched players/seasons
                            + the "GR + residual = final" reconciliation preview.
                            Called repeatedly as the user adjusts mapping/matches.
  3. POST /commit         — writes imported_stats (the club's truth) and runs the
                            reconciler so the non-GR remainder shows. Audit-logged.
  4. GET  /               — list past imports.   POST /{batch}/undo — reverse one.

The guarantee lives in services/import_reconcile (GR wins per season, a career
residual catches the gap). This router only parses, matches, and persists truth;
it never adds a club's total to GR directly.

Gated by MANAGE_MANUAL_ENTRIES — a free, core onboarding capability (the import
is a historical-data tool and reuses the manual-entries audit/undo log).
"""

from __future__ import annotations

import io
import csv
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete, func, text, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import (
    ImportBatch, ImportedStat, Organisation, Player, Season, User, get_db,
)
from app.routers.auth import get_current_club, get_current_user
from app.routers.manual_entries import _log_edit, _recompute_milestones
from app.services import import_cleanup as cleanup
from app.services import import_ingest as ingest
from app.services import import_reconcile as recon

router = APIRouter(prefix="/club-admin/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


# ── request bodies ────────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    rows: list[dict] = []
    mapping: dict = {}                  # field -> column header (or {"column": ...})
    granularity: str = "career"         # career | season
    player_overrides: dict = {}         # raw_name -> player_id | "__new__" | "__skip__"
    season_overrides: dict = {}         # raw_label -> season_id | "__prior__"
    grade_overrides: dict = {}          # raw_label -> grade_name | "__none__"


class CommitRequest(ResolveRequest):
    filename: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _col(mapping: dict, field: str) -> Optional[str]:
    v = mapping.get(field)
    if isinstance(v, dict):
        return v.get("column")
    return v or None


def _row_values(row: dict, mapping: dict) -> dict:
    """{field: raw_cell} for every mapped field that has a column in this row."""
    out = {}
    for field in ingest.ALL_FIELDS:
        col = _col(mapping, field)
        if col is not None and col in row:
            out[field] = row[col]
    return out


def _truth_metrics(truth: dict) -> dict:
    """Canonical metric dict from a parsed truth dict (reuses the GR mapper)."""
    return recon.imported_to_metrics(SimpleNamespace(**truth))


async def _org_players(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(select(Player).where(Player.organisation_id == org_id))).scalars().all()
    return [(str(p.id), (p.display_name_override or p.name or "")) for p in rows]


async def _org_seasons(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(select(Season).where(Season.organisation_id == org_id))).scalars().all()
    return [(str(s.id), s.name or "", s.year) for s in rows]


async def _org_grade_options(db: AsyncSession, org_id) -> list:
    """This org's distinct, merge-resolved grade names — the same name-space
    ``aggregations._GRADE_MATCH`` groups by — with rough games/players/runs so
    the matching step can show "does this look right" context. Mirrors the
    canonical-resolution walk ``admin.py::list_grades_with_stats`` already does
    for the (unrelated) grade-merge admin tool; kept as its own small copy here
    rather than a shared import so the two features stay decoupled.
    """
    raw = (await db.execute(
        text("""
            SELECT gr.name AS grade_name,
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
        """),
        {"org_id": str(org_id)},
    )).mappings().all()
    if not raw:
        return []

    log_rows = (await db.execute(
        text("SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org_id AND undone_at IS NULL"),
        {"org_id": str(org_id)},
    )).mappings().all()
    alias_to_canonical = {r["alias_name"]: r["canonical_name"] for r in log_rows}

    def _resolve_canonical(name):
        seen = set()
        cur = name
        while cur in alias_to_canonical and cur not in seen:
            seen.add(cur)
            cur = alias_to_canonical[cur]
        return cur

    display_name_by_raw = {row["grade_name"]: row["display_name"] for row in raw}
    bucket: dict = {}
    for row in raw:
        canonical = _resolve_canonical(row["grade_name"])
        slot = bucket.setdefault(canonical, {
            "name": display_name_by_raw.get(canonical, canonical),
            "games": 0, "players": 0, "runs": 0,
        })
        slot["games"] += int(row["games"] or 0)
        slot["players"] = max(slot["players"], int(row["players"] or 0))
        slot["runs"] += int(row["runs"] or 0)

    return sorted(bucket.values(), key=lambda d: (d["name"] or "").lower())


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
        if choice == "__prior__":
            matches[label].update(season_id=None, is_prior=True, status="prior")
        elif choice:
            matches[label].update(season_id=str(choice), is_prior=False, status="manual")


def _apply_grade_overrides(matches: dict, overrides: dict) -> None:
    for label, choice in (overrides or {}).items():
        if label not in matches:
            matches[label] = {"candidates": []}
        if choice == "__none__":
            # Explicit confirm: no matching online grade — group under the
            # sheet's own literal label (the pre-fix behaviour), now opt-in.
            matches[label].update(grade_name=label, status="own")
        elif choice:
            matches[label].update(grade_name=str(choice), status="manual")


def _resolved_grade_label(raw_label: Optional[str], gmatch: dict) -> Optional[str]:
    """The canonical grade name to group/store for a raw sheet label, or None.

    None means "leave ungraded" — the row folds into the safe whole-career GR
    comparison instead of being scoped to a grade GR has no matched coverage
    under (the exact failure mode this matching step exists to close).
    """
    if not raw_label:
        return None
    info = gmatch.get(raw_label) or {}
    return info.get("grade_name")


async def _resolve(db: AsyncSession, org_id, req: ResolveRequest) -> dict:
    """Shared core of /resolve and /commit: match + build the reconciliation
    preview. Returns everything the wizard's review screen needs, plus an
    internal ``_assignments`` list the commit step writes from."""
    name_col = _col(req.mapping, "player_name")
    season_col = _col(req.mapping, "season_label")
    grade_col = _col(req.mapping, "grade_label")
    if not name_col:
        raise HTTPException(422, "No column is mapped to the player name.")

    names = []
    labels = []
    raw_grade_labels = []
    for r in req.rows:
        nm = str(r.get(name_col, "")).strip()
        if nm and nm not in names:
            names.append(nm)
        if season_col:
            lb = str(r.get(season_col, "")).strip()
            if lb and lb not in labels:
                labels.append(lb)
        if grade_col:
            gl = str(r.get(grade_col, "")).strip()
            if gl and gl not in raw_grade_labels:
                raw_grade_labels.append(gl)

    players = await _org_players(db, org_id)
    seasons = await _org_seasons(db, org_id)
    grade_options = await _org_grade_options(db, org_id) if grade_col else []
    pmatch = ingest.match_players(names, players)
    _apply_player_overrides(pmatch, req.player_overrides)
    smatch = ingest.match_seasons(labels, seasons) if season_col else {}
    _apply_season_overrides(smatch, req.season_overrides)
    gmatch = ingest.match_grades(raw_grade_labels, [g["name"] for g in grade_options]) if grade_col else {}
    _apply_grade_overrides(gmatch, req.grade_overrides)

    # Columns + names we'll summarise straight from the sheet, so the close-review
    # can show "this is what your sheet holds for this name" next to each
    # candidate's existing career (era + totals) and tell two same-surname players
    # apart (e.g. "Ferris, Mitchell" vs "Ferris, Martyn").
    games_col = _col(req.mapping, "games_played")
    sheet_runs_col = _col(req.mapping, "batting_runs")
    sheet_wkts_col = _col(req.mapping, "bowling_wickets")
    need_sheet = {n for n, m in pmatch.items() if m.get("status") in ("fuzzy", "ambiguous", "none")}
    sheet_by_name: dict = {}

    is_season = req.granularity == "season" and bool(season_col)
    rounding = set()
    skipped_rows = 0
    items_by_player: dict = {}       # matched-player id -> reconcile items
    new_items_by_name: dict = {}     # create-new name  -> reconcile items
    name_by_pid: dict = {}

    def build_item(r, nm):
        truth, notes = ingest.row_to_truth(_row_values(r, req.mapping))
        for nt in notes:
            rounding.add(f"{nm}: {nt}")
        scope, season_id, is_prior = "career", None, False
        if is_season:
            lb = str(r.get(season_col, "")).strip()
            sm = smatch.get(lb) or {}
            if sm.get("is_prior"):
                scope, is_prior = "career", True
            elif sm.get("season_id"):
                scope, season_id = "season", sm["season_id"]
            else:
                scope, season_id = "season", None  # unmatched → folds into residual
        raw_grade = str(r.get(grade_col, "")).strip() if grade_col else None
        return {
            "scope": scope, "season_id": (uuid.UUID(season_id) if season_id else None),
            "is_prior_bucket": is_prior, "metrics": _truth_metrics(truth),
            "season_label": (str(r.get(season_col, "")).strip() if season_col else None),
            "grade_label": _resolved_grade_label(raw_grade, gmatch),
            "raw_grade_label": raw_grade,
            "truth": truth,
        }

    for r in req.rows:
        nm = str(r.get(name_col, "")).strip()
        if not nm:
            continue
        if nm in need_sheet:
            sm = sheet_by_name.setdefault(nm, {"games": 0, "runs": 0, "wickets": 0, "years": set()})
            if games_col:
                sm["games"] += ingest.to_int(r.get(games_col)) or 0
            if sheet_runs_col:
                sm["runs"] += ingest.to_int(r.get(sheet_runs_col)) or 0
            if sheet_wkts_col:
                sm["wickets"] += ingest.to_int(r.get(sheet_wkts_col)) or 0
            if season_col:
                sm["years"] |= ingest._season_years(str(r.get(season_col, "")))
        pm = pmatch.get(nm) or {}
        pid = pm.get("player_id")
        if pid:
            items_by_player.setdefault(pid, []).append(build_item(r, nm))
            name_by_pid[pid] = nm
        elif pm.get("status") == "new":
            new_items_by_name.setdefault(nm, []).append(build_item(r, nm))
        else:
            skipped_rows += 1

    # Grade-scope the preview exactly like the commit-time reconciler does
    # (services/import_reconcile.reconcile_imported_totals, migration 154):
    # a grade-labelled group's "what GR already has" must be that grade's own
    # coverage, not the player's whole cross-grade history, or the preview
    # would show a residual the commit wouldn't actually produce.
    items_by_player_grade: dict = {}
    for pid_str, items in items_by_player.items():
        for it in items:
            grade = recon._grade_key(it.get("grade_label"))
            items_by_player_grade.setdefault((pid_str, grade), []).append(it)

    ungraded_pids = [uuid.UUID(pid) for pid, grade in items_by_player_grade if grade is None]
    grade_labels = sorted({grade for _pid, grade in items_by_player_grade if grade is not None})
    gr_by_player = await recon.fetch_gr_by_player(db, org_id, ungraded_pids)
    gr_by_grade: dict = {}
    for grade in grade_labels:
        grade_pids = [uuid.UUID(pid) for pid, g in items_by_player_grade if g == grade]
        gr_by_grade[grade] = await recon.fetch_gr_by_player_for_grade(db, org_id, grade_pids, grade)

    preview_by_player: dict = {}
    for (pid_str, grade), items in items_by_player_grade.items():
        club, import_seasons = recon.assemble_club_inputs(items)
        gr_pool = gr_by_grade[grade] if grade is not None else gr_by_player
        gr = gr_pool.get(uuid.UUID(pid_str), {"season_ids": set(), "totals": None})
        gr_tot = gr["totals"] if gr["totals"] is not None else recon._blank()
        s = recon.summarize(club, gr_tot, import_seasons, gr["season_ids"])
        agg = preview_by_player.setdefault(pid_str, {
            "player_id": pid_str, "player_name": name_by_pid.get(pid_str), "new": False,
            "club_games": 0, "club_runs": 0, "gr_games": 0, "gr_runs": 0,
            "residual_games": 0, "final_games": 0, "final_runs": 0,
            "season_deltas": 0, "gr_exceeds": False,
        })
        agg["club_games"] += club.get("matches", 0)
        agg["club_runs"] += club.get("runs", 0)
        agg["gr_games"] += s["gr"]["matches"]
        agg["gr_runs"] += s["gr"]["runs"]
        agg["residual_games"] += (s["residual"] or {}).get("matches", 0)
        agg["final_games"] += s["final"]["matches"]
        agg["final_runs"] += s["final"]["runs"]
        agg["season_deltas"] += s["season_delta_count"]
        agg["gr_exceeds"] = agg["gr_exceeds"] or s["gr_exceeds"]

    preview = list(preview_by_player.values())
    # Create-new players have no GR — their full club totals are added as-is.
    for nm, items in new_items_by_name.items():
        club, import_seasons = recon.assemble_club_inputs(items)
        preview.append({
            "player_id": None, "player_name": nm, "new": True,
            "club_games": club.get("matches", 0), "club_runs": club.get("runs", 0),
            "gr_games": 0, "gr_runs": 0,
            "residual_games": club.get("matches", 0),
            "final_games": club.get("matches", 0), "final_runs": club.get("runs", 0),
            "season_deltas": len(import_seasons), "gr_exceeds": False,
        })
    preview.sort(key=lambda x: x["final_games"], reverse=True)

    # Enrich every candidate with its career-at-this-club (seasons span + totals)
    # and attach the sheet's own summary per unresolved name — the raw material the
    # review screen shows so you can pick the right player from just "Ferris M".
    cand_ids = {c["player_id"] for m in pmatch.values()
                for c in (m.get("candidates") or []) if c.get("player_id")}
    cand_stats = await recon.fetch_gr_by_player(db, org_id, [uuid.UUID(i) for i in cand_ids]) if cand_ids else {}
    year_by_season = {sid: yr for sid, _n, yr in seasons}

    def _cand_summary(pid_str):
        g = cand_stats.get(uuid.UUID(pid_str))
        tot = g["totals"] if (g and g["totals"]) else {}
        yrs = sorted(y for y in (year_by_season.get(str(s)) for s in (g["season_ids"] if g else ())) if y)
        return {
            "seasons": len(g["season_ids"]) if g else 0,
            "matches": tot.get("matches", 0), "runs": tot.get("runs", 0), "wickets": tot.get("wickets", 0),
            "first_year": (yrs[0] if yrs else None), "last_year": (yrs[-1] if yrs else None),
        }

    for m in pmatch.values():
        for c in (m.get("candidates") or []):
            if c.get("player_id"):
                c["stats"] = _cand_summary(c["player_id"])
    for n in need_sheet:
        sm = sheet_by_name.get(n)
        if sm:
            pmatch[n]["sheet"] = {
                "games": sm["games"], "runs": sm["runs"], "wickets": sm["wickets"],
                "first_year": (min(sm["years"]) if sm["years"] else None),
                "last_year": (max(sm["years"]) if sm["years"] else None),
            }

    warnings = []
    unresolved = [n for n, m in pmatch.items()
                  if not m.get("player_id") and m.get("status") not in ("skip", "new")]
    if unresolved:
        warnings.append(f"{len(unresolved)} player name(s) need a match before import: "
                        + ", ".join(unresolved[:8]) + ("…" if len(unresolved) > 8 else ""))
    ambiguous = [n for n, m in pmatch.items() if m.get("status") == "ambiguous"]
    if ambiguous:
        warnings.append(f"{len(ambiguous)} name(s) match two players — merge those first: "
                        + ", ".join(ambiguous[:5]))
    exceed = [p["player_name"] for p in preview if p["gr_exceeds"]]
    if exceed:
        warnings.append("Online (GR) data already shows more than your sheet for: "
                        + ", ".join(exceed[:5]) + " — we'll show the higher online figure.")
    grade_unresolved = [lb for lb, m in gmatch.items() if m.get("status") in ("fuzzy", "none")]
    if grade_unresolved:
        warnings.append(
            f"{len(grade_unresolved)} grade/team label(s) aren't matched to an online grade: "
            + ", ".join(grade_unresolved[:8]) + ("…" if len(grade_unresolved) > 8 else "")
            + " — for now that part is compared against the player's whole career instead of just "
              "that grade (safe, but can under-count). Match them on the Grades step, or confirm "
              "‘no online equivalent’ if the grade genuinely predates online records."
        )

    return {
        "granularity": "season" if is_season else "career",
        "columns_used": {f: _col(req.mapping, f) for f in ingest.ALL_FIELDS if _col(req.mapping, f)},
        "players": [{"raw_name": n, **m} for n, m in pmatch.items()],
        "seasons": [{"raw_label": lb, **m} for lb, m in smatch.items()],
        "grades": [{"raw_label": lb, **m} for lb, m in gmatch.items()],
        "grade_options": grade_options,
        "preview": preview,
        "rounding_notes": sorted(rounding)[:50],
        "warnings": warnings,
        "totals": {
            "rows": len(req.rows),
            "players_matched": len(items_by_player),
            "players_new": len(new_items_by_name),
            "players_unresolved": len(unresolved),
            "rows_skipped": skipped_rows,
        },
        "_items_by_player": items_by_player,
        "_new_names": [n for n, m in pmatch.items() if m.get("status") == "new"],
        "_grade_matches": gmatch,
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
):
    """Parse an uploaded CSV/XLSX → headers, sample rows, auto column mapping,
    and a granularity guess. No DB writes; the client holds the parsed rows."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 8 MB).")
    parsed = ingest.parse_upload(file.filename or "upload.csv", data)
    if not parsed["headers"]:
        raise HTTPException(422, "Could not find a header row in the file.")
    mapping = ingest.suggest_column_mapping(parsed["headers"])
    return {
        "filename": file.filename,
        "headers": parsed["headers"],
        "field_options": list(ingest.ALL_FIELDS),
        "mapping_suggestions": mapping,
        "granularity_guess": ingest.detect_granularity(mapping, parsed["rows"]),
        "row_count": len(parsed["rows"]),
        "sample_rows": parsed["rows"][:10],
        "rows": parsed["rows"],
    }


@router.post("/resolve")
async def resolve(
    req: ResolveRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Match players/seasons and return the reconciliation preview. Idempotent —
    call repeatedly as the user adjusts the column mapping or fixes matches."""
    out = await _resolve(db, club.id, req)
    out.pop("_items_by_player", None)
    out.pop("_new_names", None)
    out.pop("_grade_matches", None)
    return out


@router.post("/commit")
async def commit(
    req: CommitRequest,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Persist the club's uploaded truth, then run the reconciler. Re-importing a
    player replaces that player's prior imported truth (latest upload wins);
    other players are untouched. Audit-logged + reversible via /undo."""
    resolved = await _resolve(db, club.id, req)
    items_by_player = resolved["_items_by_player"]
    new_names = set(resolved["_new_names"])
    gmatch = resolved["_grade_matches"]

    batch = ImportBatch(
        id=uuid.uuid4(), organisation_id=club.id,
        filename=req.filename, status="committed",
        granularity=resolved["granularity"],
        column_mapping={f: _col(req.mapping, f) for f in ingest.ALL_FIELDS if _col(req.mapping, f)},
        row_count=len(req.rows), created_by_user_id=current_user.id,
        committed_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    await db.flush()

    # Create manual-only players the user chose to add (no GR id).
    created_players = 0
    if new_names:
        name_col = _col(req.mapping, "player_name")
        # map raw name → new player id, then redirect its items
        new_pid_by_name: dict = {}
        for nm in new_names:
            # import_batch_id marks the player as minted by THIS import
            # (migration 234) — it's what lets /undo delete them again when
            # the undo leaves them with nothing attached.
            p = Player(id=uuid.uuid4(), name=nm, organisation_id=club.id,
                       import_batch_id=batch.id)
            db.add(p)
            new_pid_by_name[nm] = str(p.id)
            created_players += 1
        await db.flush()
        # _resolve skipped 'new' players (no player_id yet) — re-bucket their rows.
        for r in req.rows:
            nm = str(r.get(name_col, "")).strip()
            if nm not in new_pid_by_name:
                continue
            truth, _notes = ingest.row_to_truth(_row_values(r, req.mapping))
            metrics = _truth_metrics(truth)
            scope, season_id, is_prior = "career", None, False
            season_col = _col(req.mapping, "season_label")
            grade_col = _col(req.mapping, "grade_label")
            if resolved["granularity"] == "season" and season_col:
                lb = str(r.get(season_col, "")).strip()
                sm = next((s for s in resolved["seasons"] if s["raw_label"] == lb), {})
                if sm.get("is_prior"):
                    scope, is_prior = "career", True
                elif sm.get("season_id"):
                    scope, season_id = "season", sm["season_id"]
                else:
                    scope, season_id = "season", None
            raw_grade = str(r.get(grade_col, "")).strip() if grade_col else None
            items_by_player.setdefault(new_pid_by_name[nm], []).append(
                {"scope": scope, "season_id": (uuid.UUID(season_id) if season_id else None),
                 "is_prior_bucket": is_prior, "metrics": metrics,
                 "season_label": (str(r.get(season_col, "")).strip() if season_col else None),
                 "grade_label": _resolved_grade_label(raw_grade, gmatch),
                 "truth": truth})

    if not items_by_player:
        raise HTTPException(422, "Nothing to import — no rows matched a player. "
                                 "Resolve the player matches and try again.")

    # Latest-upload-wins: replace prior imported truth for these players only.
    pids = [uuid.UUID(p) for p in items_by_player.keys()]
    await db.execute(
        sa_delete(ImportedStat).where(
            ImportedStat.organisation_id == club.id, ImportedStat.player_id.in_(pids))
    )
    # A re-imported player minted by an EARLIER batch now holds rows only from
    # this one, so move the created-by marker forward — undoing THIS batch is
    # what would leave them empty. Players the import didn't create (marker
    # NULL: synced or hand-added) are never stamped.
    await db.execute(
        sa_update(Player).where(
            Player.organisation_id == club.id, Player.id.in_(pids),
            Player.import_batch_id.isnot(None),
        ).values(import_batch_id=batch.id)
    )

    inserted = 0
    for pid_str, items in items_by_player.items():
        for it in items:
            db.add(ImportedStat(
                organisation_id=club.id, import_batch_id=batch.id,
                player_id=uuid.UUID(pid_str), scope=it["scope"],
                season_id=it["season_id"], season_label=it.get("season_label"),
                grade_label=it.get("grade_label"), is_prior_bucket=it["is_prior_bucket"],
                **it["truth"],
            ))
            inserted += 1
    await db.flush()

    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="import",
        target_table="imported_stats",
        target_id=f"batch:{batch.id}",
        summary=f"BetterImport — {len(items_by_player)} players, {inserted} rows "
                f"({created_players} new players created)",
        before=None,
        after={"batch_id": str(batch.id), "players": len(items_by_player), "rows": inserted},
    )
    await db.commit()

    written = await recon.reconcile_imported_totals(str(club.id))
    await _recompute_milestones(db, club.id, pids)

    return {
        "batch_id": str(batch.id),
        "players_imported": len(items_by_player),
        "rows_written": inserted,
        "players_created": created_players,
        "deltas_written": written,
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
    out = []
    for b in rows:
        n = (await db.execute(
            select(ImportedStat.id).where(ImportedStat.import_batch_id == b.id)
        )).scalars().all()
        out.append({
            "id": str(b.id), "filename": b.filename, "status": b.status,
            "granularity": b.granularity, "row_count": b.row_count,
            "stats_rows": len(n),
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "undone_at": b.undone_at.isoformat() if b.undone_at else None,
        })
    return {"imports": out}


@router.get("/{batch_id}/players")
async def list_import_players(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Per-player breakdown of a batch's still-live rows, so a batch can be
    expanded in the history list and one player's import undone without
    touching the rest — see /undo-player."""
    try:
        bid = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(404, "Import not found.")
    batch = (await db.execute(
        select(ImportBatch).where(ImportBatch.id == bid, ImportBatch.organisation_id == club.id)
    )).scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Import not found.")

    rows = (await db.execute(
        select(Player.id, Player.name, func.count(ImportedStat.id))
        .join(ImportedStat, ImportedStat.player_id == Player.id)
        .where(ImportedStat.import_batch_id == bid)
        .group_by(Player.id, Player.name)
        .order_by(Player.name)
    )).all()
    return {
        "players": [
            {"player_id": str(pid), "name": name, "rows": count}
            for pid, name, count in rows
        ]
    }


@router.post("/{batch_id}/undo")
async def undo_import(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Remove a batch's uploaded truth and re-reconcile. Players THIS batch
    created (``players.import_batch_id``) are deleted too when the undo leaves
    them with nothing attached — a mis-mapped upload (e.g. surname-only names
    imported as new players) must not survive its own undo and clog the
    Players page. A created player who has since gained anything real (another
    batch's rows, synced or manual stats, a membership, votes, an edited
    profile…) is kept, with the reasons audit-logged."""
    try:
        bid = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(404, "Import not found.")
    batch = (await db.execute(
        select(ImportBatch).where(ImportBatch.id == bid, ImportBatch.organisation_id == club.id)
    )).scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Import not found.")
    if batch.undone_at:
        raise HTTPException(409, "This import has already been undone.")

    removed = (await db.execute(
        select(ImportedStat.id).where(ImportedStat.import_batch_id == bid)
    )).scalars().all()
    await db.execute(sa_delete(ImportedStat).where(ImportedStat.import_batch_id == bid))
    await db.flush()  # the emptiness check below must not see the rows just deleted

    candidates = (await db.execute(
        select(Player.id, Player.name).where(
            Player.organisation_id == club.id, Player.import_batch_id == bid)
    )).all()
    name_by_pid = {pid: name for pid, name in candidates}
    deletable, kept = await cleanup.deletable_players(db, club.id, list(name_by_pid))
    if deletable:
        await cleanup.delete_players(db, club.id, deletable)

    batch.undone_at = datetime.now(timezone.utc)
    batch.status = "undone"
    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="undo",
        target_table="imported_stats", target_id=f"batch:{bid}",
        summary=f"Undo BetterImport — removed {len(removed)} imported rows"
                + (f", deleted {len(deletable)} players this import created" if deletable else ""),
        before={
            "batch_id": str(bid), "rows": len(removed),
            "players_deleted": sorted(name_by_pid[p] for p in deletable),
            "players_kept": {name_by_pid[p]: why for p, why in kept.items() if p in name_by_pid},
        },
        after=None,
    )
    await db.commit()

    written = await recon.reconcile_imported_totals(str(club.id))
    return {
        "undone": True, "rows_removed": len(removed), "deltas_rebuilt": written,
        "players_deleted": len(deletable), "players_kept": len(kept),
    }


@router.post("/{batch_id}/undo-player/{player_id}")
async def undo_import_for_player(
    batch_id: str,
    player_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Remove JUST one player's rows from a batch, leaving every other
    player's imported truth untouched. `/undo` above only ever removed the
    WHOLE batch — every player in it — which meant a single mismatched name
    (e.g. a historical import that accidentally attached one player's rows
    to the wrong, similarly-named record) could only be fixed by undoing the
    entire club's import and starting over. `ImportedStat` already carries
    `player_id` per row, so this is a WHERE-clause scoping of the same
    delete-then-reconcile shape `/undo` uses, not a new data model.

    If this was the last player still holding rows in the batch, the batch
    itself flips to undone too (so it reads correctly in the imports list —
    a batch showing "committed" with zero rows left would be confusing).
    """
    try:
        bid = uuid.UUID(batch_id)
        pid = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(404, "Import or player not found.")
    batch = (await db.execute(
        select(ImportBatch).where(ImportBatch.id == bid, ImportBatch.organisation_id == club.id)
    )).scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Import not found.")
    if batch.undone_at:
        raise HTTPException(409, "This import has already been undone.")

    player = (await db.execute(
        select(Player).where(Player.id == pid, Player.organisation_id == club.id)
    )).scalar_one_or_none()
    if not player:
        raise HTTPException(404, "Player not found.")

    removed = (await db.execute(
        select(ImportedStat.id).where(
            ImportedStat.import_batch_id == bid, ImportedStat.player_id == pid,
        )
    )).scalars().all()
    if not removed:
        raise HTTPException(404, "No imported stats found for this player in this import.")

    await db.execute(sa_delete(ImportedStat).where(
        ImportedStat.import_batch_id == bid, ImportedStat.player_id == pid,
    ))
    await db.flush()  # the emptiness check below must not see the rows just deleted

    # If this batch minted the player, deleting their rows may leave an empty
    # record — remove it too, same rule as the whole-batch undo above.
    player_name = player.name
    player_deleted = False
    if player.import_batch_id == bid:
        deletable, _kept = await cleanup.deletable_players(db, club.id, [pid])
        if deletable:
            db.expunge(player)  # the ORM instance is about to be a dead row
            await cleanup.delete_players(db, club.id, deletable)
            player_deleted = True

    remaining = (await db.execute(
        select(ImportedStat.id).where(ImportedStat.import_batch_id == bid)
    )).scalars().first()
    batch_fully_undone = remaining is None
    if batch_fully_undone:
        batch.undone_at = datetime.now(timezone.utc)
        batch.status = "undone"

    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="undo",
        target_table="imported_stats", target_id=f"batch:{bid}:player:{pid}",
        summary=f"Undo BetterImport for {player_name} — removed {len(removed)} imported rows"
                + (", deleted the player record this import created" if player_deleted else "")
                + (" (batch now fully undone)" if batch_fully_undone else ""),
        before={"batch_id": str(bid), "player_id": str(pid), "rows": len(removed),
                "player_deleted": player_deleted}, after=None,
    )
    await db.commit()

    written = await recon.reconcile_imported_totals(str(club.id))
    return {
        "undone": True,
        "player_id": str(pid),
        "rows_removed": len(removed),
        "player_deleted": player_deleted,
        "batch_fully_undone": batch_fully_undone,
        "deltas_rebuilt": written,
    }


@router.get("/template.csv")
async def template(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    """A starter template. The wizard maps any headers — this is just a hint."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Player", "Season", "Grade", "Games", "Innings", "Runs", "NO", "HS",
                "Avg", "Wickets", "Overs", "Runs Conceded", "Bowl Avg", "Catches", "Stumpings"])
    w.writerow(["Giles, Wayne", "Prior Seasons & Adjustments", "", 248, "", 6635, "", "186*",
                "", 186, 1173.5, "", 18.41, 182, ""])
    w.writerow(["Giles, Wayne", "2002/03", "9th Grade", 17, 18, 638, "", 122,
                37.53, 31, 169.4, "", 14.03, 4, ""])
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="betterimport_template.csv"'},
    )
