"""AFL manual stat entries — admin-typed corrections to a player's totals.

The football counterpart of cricket's ``routers/manual_entries.py``
Adjustments tab. A club's history reaches BetterFootball three ways and only
two of them existed before this: the PlayHQ sync, and an Import Stats /
Import Results upload. Both are bulk, both are all-or-nothing, and neither can
answer "PlayHQ has him at 8 goals for 2019 and the club record book says 12".

An adjustment is a **delta**, never a replacement — the number entered is added
on top of whatever the sync and the imports already hold, which is why
correcting a season means entering the shortfall and the screen says so. See
``services/afl/manual_stats.py`` for the one definition of how that delta reads
back out, and ``models/afl.AflManualAdjustment`` for why a season and a career
adjustment are one table rather than cricket's two.

Every write goes through ``manual_edit_logs`` — the same sport-agnostic audit
table cricket uses, already present in an AFL database because it is ORM-mapped
on the shared Base — and every one is reversible from the Audit tab.

Deliberately NOT built here: a per-game manual scorecard. Football's equivalent
is Import Results (``routers/afl/result_imports.py``), which writes real
``games`` rows from a club's own register and is a better answer than typing a
match in by hand.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.afl import AflManualAdjustment
from app.models.db import (
    Grade,
    ManualEditLog,
    Organisation,
    Player,
    Season,
    User,
    get_db,
)
from app.routers.auth import get_current_club, get_current_user
from app.services.afl.grade_labels import suggest_category

router = APIRouter(prefix="/club-admin/manual-entries", tags=["afl-manual-entries"])

# The stat columns an adjustment carries. Everything else on the row
# (organisation, player, season, grade, audit stamps) is set by the endpoint.
STAT_FIELDS = (
    "games_played", "goals", "behinds", "bog_count",
    "captain_games", "club_bf_votes", "comp_bf_votes",
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _to_uuid(s: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(s))
    except Exception:
        raise HTTPException(422, f"Invalid {label} id")


def _row_to_dict(row) -> dict:
    out = {}
    for k, v in row.__dict__.items():
        if k.startswith("_"):
            continue
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _player_name(p: Player) -> str:
    return p.display_name_override or p.name


async def _assert_player(db: AsyncSession, pid: uuid.UUID, org_id: uuid.UUID) -> Player:
    player = await db.get(Player, pid)
    if not player or player.organisation_id != org_id:
        raise HTTPException(404, "Player not in your club")
    return player


async def _assert_season(db: AsyncSession, sid: uuid.UUID, org_id: uuid.UUID) -> Season:
    season = await db.get(Season, sid)
    if not season or season.organisation_id != org_id:
        raise HTTPException(404, "Season not in your club")
    return season


async def _assert_grade(db: AsyncSession, gid: uuid.UUID, season_id: uuid.UUID) -> Grade:
    grade = await db.get(Grade, gid)
    if not grade or grade.season_id != season_id:
        raise HTTPException(404, "Grade not in the chosen season")
    return grade


async def _log_edit(db: AsyncSession, *, org_id: uuid.UUID, user_id: Optional[uuid.UUID],
                    action: str, target_id: str, summary: str,
                    before: Optional[dict], after: Optional[dict]) -> ManualEditLog:
    entry = ManualEditLog(
        organisation_id=org_id,
        user_id=user_id,
        action=action,
        target_table="afl_manual_adjustments",
        target_id=target_id,
        summary=summary,
        before_json=before,
        after_json=after,
    )
    db.add(entry)
    await db.flush()
    return entry


def _describe(player_name: str, season_name: Optional[str], grade_name: Optional[str]) -> str:
    where = season_name or "career only"
    if grade_name:
        where = f"{where} · {grade_name}"
    return f"{player_name} ({where})"


# ─── Seasons and grades a picker needs ───────────────────────────────────────


@router.get("/grades")
async def list_grades(
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Every grade the club holds, with the season it belongs to.

    The existing ``/club-admin/grades-with-stats`` is keyed on grade NAME
    (it folds merged spellings together for the Merge Grades screen), which
    is the wrong shape for a picker that has to write one grade's id against
    one season.
    """
    rows = await db.execute(
        select(Grade.id, Grade.name, Grade.display_name_override, Grade.season_id)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == club.id)
        .order_by(Grade.name)
    )
    return [
        {"id": str(gid), "name": override or name, "season_id": str(sid)}
        for gid, name, override, sid in rows
    ]


class GradeCreate(BaseModel):
    season_id: str
    name: str


@router.post("/grades")
async def create_grade(
    data: GradeCreate,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """A grade with no PlayHQ equivalent — a pre-sync era's competition.

    ``grassroots_id`` stays NULL, which is itself the "not from a sync" marker,
    and the category is suggested from the name so the new grade sorts and
    filters like any other rather than landing unclassified.

    There is no matching season endpoint here on purpose: the Import Stats
    wizard already owns ``POST /club-admin/imports/seasons`` and creates
    exactly the same row. Two ways to mint a season is how the two start
    disagreeing about what one is.
    """
    season_id = _to_uuid(data.season_id, "season")
    await _assert_season(db, season_id, club.id)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "Grade name is required")
    existing = await db.execute(select(Grade).where(
        Grade.season_id == season_id, func.lower(Grade.name) == name.lower(),
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"A grade named '{name}' already exists in this season.")

    grade = Grade(id=uuid.uuid4(), season_id=season_id, grassroots_id=None,
                  name=name, category=suggest_category(name))
    db.add(grade)
    await db.flush()
    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="create_grade",
        target_id=str(grade.id), summary=f"Created grade '{name}'",
        before=None, after={"id": str(grade.id), "name": name, "season_id": str(season_id)},
    )
    await db.commit()
    return {"id": str(grade.id), "name": grade.name, "season_id": str(season_id)}


# ─── Adjustments ─────────────────────────────────────────────────────────────


class AdjustmentIn(BaseModel):
    player_id: str
    season_id: Optional[str] = None
    grade_id: Optional[str] = None
    games_played: int = 0
    goals: int = 0
    behinds: int = 0
    bog_count: int = 0
    captain_games: int = 0
    club_bf_votes: int = 0
    comp_bf_votes: int = 0
    notes: Optional[str] = None


async def _list_rows(db: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    rows = await db.execute(
        select(AflManualAdjustment, Player, Season.name, Grade.name)
        .join(Player, Player.id == AflManualAdjustment.player_id)
        .outerjoin(Season, Season.id == AflManualAdjustment.season_id)
        .outerjoin(Grade, Grade.id == AflManualAdjustment.grade_id)
        .where(AflManualAdjustment.organisation_id == org_id)
        .order_by(AflManualAdjustment.created_at.desc())
    )
    out = []
    for adj, player, season_name, grade_name in rows.all():
        out.append({
            **_row_to_dict(adj),
            "player_name": _player_name(player),
            "season_name": season_name,
            "grade_name": grade_name,
        })
    return out


@router.get("/adjustments")
async def list_adjustments(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return await _list_rows(db, club.id)


async def _resolve_targets(db: AsyncSession, data: AdjustmentIn, org_id: uuid.UUID):
    player = await _assert_player(db, _to_uuid(data.player_id, "player"), org_id)
    season = None
    grade = None
    if data.season_id:
        season = await _assert_season(db, _to_uuid(data.season_id, "season"), org_id)
        if data.grade_id:
            grade = await _assert_grade(db, _to_uuid(data.grade_id, "grade"), season.id)
    elif data.grade_id:
        # A grade belongs to a season, so a grade with no season is a state
        # that can't be read back out — refused rather than silently dropped.
        raise HTTPException(422, "Choose a season before a grade, or leave both blank for a career adjustment.")
    return player, season, grade


@router.post("/adjustments")
async def create_adjustment(
    data: AdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    player, season, grade = await _resolve_targets(db, data, club.id)

    clash = await db.execute(select(AflManualAdjustment).where(
        AflManualAdjustment.organisation_id == club.id,
        AflManualAdjustment.player_id == player.id,
        AflManualAdjustment.season_id.is_(None) if season is None else AflManualAdjustment.season_id == season.id,
        AflManualAdjustment.grade_id.is_(None) if grade is None else AflManualAdjustment.grade_id == grade.id,
    ))
    if clash.scalar_one_or_none():
        raise HTTPException(
            409,
            "An adjustment already exists for this player and season — edit that one instead, "
            "or its figures will be counted twice.",
        )

    adj = AflManualAdjustment(
        organisation_id=club.id,
        player_id=player.id,
        season_id=season.id if season else None,
        grade_id=grade.id if grade else None,
        created_by_user_id=current_user.id,
        notes=(data.notes or "").strip() or None,
        **{f: getattr(data, f) for f in STAT_FIELDS},
    )
    db.add(adj)
    await db.flush()
    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="create",
        target_id=str(adj.id),
        summary=f"Added adjustment for {_describe(_player_name(player), season.name if season else None, grade.name if grade else None)}",
        before=None, after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.patch("/adjustments/{adj_id}")
async def update_adjustment(
    adj_id: int,
    data: AdjustmentIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(AflManualAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(404, "Adjustment not found")
    before = _row_to_dict(adj)
    player, season, grade = await _resolve_targets(db, data, club.id)

    adj.player_id = player.id
    adj.season_id = season.id if season else None
    adj.grade_id = grade.id if grade else None
    adj.notes = (data.notes or "").strip() or None
    for f in STAT_FIELDS:
        setattr(adj, f, getattr(data, f))
    adj.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="update",
        target_id=str(adj.id),
        summary=f"Updated adjustment for {_describe(_player_name(player), season.name if season else None, grade.name if grade else None)}",
        before=before, after=_row_to_dict(adj),
    )
    await db.commit()
    return _row_to_dict(adj)


@router.delete("/adjustments/{adj_id}")
async def delete_adjustment(
    adj_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    adj = await db.get(AflManualAdjustment, adj_id)
    if not adj or adj.organisation_id != club.id:
        raise HTTPException(404, "Adjustment not found")
    before = _row_to_dict(adj)
    player = await db.get(Player, adj.player_id)
    season = await db.get(Season, adj.season_id) if adj.season_id else None
    grade = await db.get(Grade, adj.grade_id) if adj.grade_id else None
    summary = (
        "Deleted adjustment for "
        f"{_describe(_player_name(player), season.name if season else None, grade.name if grade else None)}"
    )
    await db.delete(adj)
    await db.flush()
    await _log_edit(
        db, org_id=club.id, user_id=current_user.id, action="delete",
        target_id=str(adj_id), summary=summary, before=before, after=None,
    )
    await db.commit()
    return {"deleted": True}


# ─── CSV bulk import ─────────────────────────────────────────────────────────


CSV_COLUMNS = [
    "player_name", "season_name", "grade_name",
    *STAT_FIELDS,
    "notes",
]


def _parse_int(v) -> int:
    if v is None or str(v).strip() == "":
        return 0
    return int(float(str(v).strip()))


@router.get("/adjustments/template.csv")
async def adjustments_template(
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    # Two example rows: a season correction, and a career-only one (blank
    # season) — the blank cell is the whole distinction, so the template has
    # to show it rather than describe it.
    w.writerow(["Smith, John", "2019", "Seniors", 4, 6, 3, 1, 0, 12, 0, "Source: club record book"])
    w.writerow(["Brown, Alan", "", "", 42, 55, 30, 3, 5, 0, 0, "Pre-1990 totals, no season detail"])
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="afl_adjustments_template.csv"'},
    )


def _player_lookup(players: list[Player]) -> dict[str, Player]:
    """Lower-cased name → Player, matching "Smith, John" and "John Smith"
    alike — a club's own spreadsheet uses whichever it uses."""
    out: dict[str, Player] = {}
    for p in players:
        name = (p.display_name_override or p.name or "").strip()
        if not name:
            continue
        out.setdefault(name.lower(), p)
        if "," in name:
            last, first = [x.strip() for x in name.split(",", 1)]
            out.setdefault(f"{first} {last}".lower(), p)
        else:
            parts = name.split()
            if len(parts) >= 2:
                out.setdefault(f"{parts[-1]}, {' '.join(parts[:-1])}".lower(), p)
    return out


@router.post("/adjustments/import")
async def import_adjustments(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Upsert on (player, season, grade) — re-uploading a corrected sheet
    rewrites the same rows rather than stacking a second set on top, which for
    additive deltas would double every figure in it.

    The audit entry carries each row's BEFORE state, not just the ids it
    created, so undoing an import puts an overwritten adjustment back as it
    was instead of leaving the overwrite standing.
    """
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV is empty or missing a header row")

    players = (await db.execute(select(Player).where(Player.organisation_id == club.id))).scalars().all()
    seasons = (await db.execute(select(Season).where(Season.organisation_id == club.id))).scalars().all()
    grades = (await db.execute(
        select(Grade).join(Season, Season.id == Grade.season_id).where(Season.organisation_id == club.id)
    )).scalars().all()
    by_player = _player_lookup(players)
    by_season = {(s.name or "").strip().lower(): s for s in seasons}
    by_grade: dict = {}
    for g in grades:
        if g.name:
            by_grade.setdefault((g.season_id, g.name.strip().lower()), g)
        if g.display_name_override:
            by_grade.setdefault((g.season_id, g.display_name_override.strip().lower()), g)

    errors: list[dict] = []
    created = 0
    updated = 0
    snapshots: list[dict] = []

    for row_num, raw in enumerate(reader, start=2):  # row 1 is the header
        try:
            pname = (raw.get("player_name") or "").strip()
            sname = (raw.get("season_name") or "").strip()
            gname = (raw.get("grade_name") or "").strip()
            if not pname:
                raise ValueError("player_name is required")
            player = by_player.get(pname.lower())
            if not player:
                raise ValueError(f"Player not found: '{pname}'")

            season = None
            grade = None
            if sname:
                season = by_season.get(sname.lower())
                if not season:
                    raise ValueError(f"Season not found: '{sname}'")
                if gname:
                    grade = by_grade.get((season.id, gname.lower()))
                    if not grade:
                        raise ValueError(f"Grade '{gname}' not found in season '{sname}'")
            elif gname:
                raise ValueError("A grade needs a season — fill season_name in, or clear grade_name")

            fields = {f: _parse_int(raw.get(f)) for f in STAT_FIELDS}
            fields["notes"] = (raw.get("notes") or "").strip() or None

            existing_q = await db.execute(select(AflManualAdjustment).where(
                AflManualAdjustment.organisation_id == club.id,
                AflManualAdjustment.player_id == player.id,
                AflManualAdjustment.season_id.is_(None) if season is None else AflManualAdjustment.season_id == season.id,
                AflManualAdjustment.grade_id.is_(None) if grade is None else AflManualAdjustment.grade_id == grade.id,
            ))
            existing = existing_q.scalar_one_or_none()
            if existing:
                snapshots.append({"before": _row_to_dict(existing)})
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                adj = AflManualAdjustment(
                    organisation_id=club.id,
                    player_id=player.id,
                    season_id=season.id if season else None,
                    grade_id=grade.id if grade else None,
                    created_by_user_id=current_user.id,
                    **fields,
                )
                db.add(adj)
                await db.flush()
                snapshots.append({"before": None, "id": adj.id})
                created += 1
        except Exception as e:  # one bad row never stops the rest of the sheet
            errors.append({"row": row_num, "error": str(e)})

    summary = {
        "created": created,
        "updated": updated,
        "errors": len(errors),
        "errors_detail": errors[:50],
    }
    if created or updated:
        await _log_edit(
            db, org_id=club.id, user_id=current_user.id, action="import",
            target_id=f"bulk:{created}created+{updated}updated",
            summary=f"CSV import — adjustments: {created} created, {updated} updated, {len(errors)} errors",
            before={"rows": snapshots}, after=None,
        )
        await db.commit()
    return summary


# ─── Audit log and undo ──────────────────────────────────────────────────────


@router.get("/audit")
async def list_audit(
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 1000))
    rows = await db.execute(
        select(ManualEditLog, User.display_name, User.email)
        .outerjoin(User, User.id == ManualEditLog.user_id)
        .where(ManualEditLog.organisation_id == club.id)
        .order_by(ManualEditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {**_row_to_dict(log), "user_name": name or email or "system"}
        for log, name, email in rows.all()
    ]


def _restore(db: AsyncSession, snapshot: dict, org_id: uuid.UUID) -> None:
    """Put a deleted or overwritten adjustment back exactly as it was, id
    included — the audit entry that removed it names that id, so keeping it is
    what lets a later entry about the same row still resolve."""
    if snapshot.get("organisation_id") != str(org_id):
        raise HTTPException(403, "Audit row belongs to a different club")
    fields = {k: v for k, v in snapshot.items() if k not in {"created_at", "updated_at"}}
    for fk in ("organisation_id", "player_id", "season_id", "grade_id", "created_by_user_id"):
        if isinstance(fields.get(fk), str):
            fields[fk] = uuid.UUID(fields[fk])
    db.add(AflManualAdjustment(**fields))


@router.post("/audit/{log_id}/undo")
async def undo_edit(
    log_id: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(ManualEditLog, log_id)
    if not log or log.organisation_id != club.id:
        raise HTTPException(404, "Audit entry not found")
    if log.undone_at is not None:
        raise HTTPException(409, "This change has already been undone")
    if log.target_table != "afl_manual_adjustments":
        raise HTTPException(400, f"Cannot undo an entry on {log.target_table}")

    action = log.action

    async def _get_own(adj_id: int) -> Optional[AflManualAdjustment]:
        row = await db.get(AflManualAdjustment, adj_id)
        return row if row and row.organisation_id == club.id else None

    if action == "create":
        row = await _get_own(int(log.target_id))
        if row:
            await db.delete(row)
    elif action == "delete":
        _restore(db, dict(log.before_json or {}), club.id)
    elif action == "update":
        row = await _get_own(int(log.target_id))
        if not row:
            raise HTTPException(404, "That adjustment no longer exists")
        snap = dict(log.before_json or {})
        for k, v in snap.items():
            if k in {"id", "created_at", "updated_at", "organisation_id"}:
                continue
            if k in {"player_id", "season_id", "grade_id", "created_by_user_id"} and isinstance(v, str):
                v = uuid.UUID(v)
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
    elif action == "import":
        # Rows the import created are removed; rows it overwrote go back to
        # the state snapshotted at import time.
        for entry in (log.before_json or {}).get("rows", []):
            before = entry.get("before")
            if before is None:
                row = await _get_own(int(entry["id"])) if entry.get("id") is not None else None
                if row:
                    await db.delete(row)
                continue
            row = await _get_own(int(before["id"]))
            if not row:
                _restore(db, before, club.id)
                continue
            for k, v in before.items():
                if k in {"id", "created_at", "updated_at", "organisation_id"}:
                    continue
                if k in {"player_id", "season_id", "grade_id", "created_by_user_id"} and isinstance(v, str):
                    v = uuid.UUID(v)
                setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
    elif action == "create_grade":
        raise HTTPException(400, "A grade is removed from Merge Grades, not from here.")
    else:
        raise HTTPException(400, f"Unknown action: {action}")

    log.undone_at = datetime.now(timezone.utc)
    log.undone_by_user_id = current_user.id
    await db.commit()
    return {"undone": True}
