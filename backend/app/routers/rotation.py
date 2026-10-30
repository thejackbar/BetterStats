"""BetterSelect → Junior Rotation.

A fair batting order and fielding rotation for a junior side. A coach saves a
group of kids by name, and each game the generator (``services/rotation.py``)
hands back a batting order and who fields where, weighted by what each kid has
already had. Built to be lifted out of BetterSelect later, so it keeps to its
own tables (``services/rotation_ddl.py``) and never reads the club's player
roster: the kids are typed names saved on the group.

  * rotation_groups   - the side, its field positions and its settings
  * rotation_players  - the saved names (never deleted: ``former_at``)
  * rotation_rounds   - one game: who is here, the batting order, the field

**A draft is working state, a locked round is history.** Only locked rounds
feed the next generation and the season tally, so re-rolling a draft, fixing a
position by hand or deleting a draft never changes what a kid has had. A locked
round refuses every write until it is unlocked. Tallies are derived on read,
never stored.

Every endpoint is scoped to the caller's club and gated by
``SELECT_ROTATION`` (or the BetterSelect umbrella). The router sits behind
``require_module("select")`` at registration in main.py. The parent link is
``routers/public_rotation.py``.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, SELECT_ROTATION, require_any_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import rotation as rot

router = APIRouter(prefix="/rotation", tags=["rotation"])

_GATE = require_any_cap(SELECT_ROTATION, MANAGE_SELECTIONS)


# ─── helpers ────────────────────────────────────────────────────────────────

def _uuid(raw: str, what: str = "Not found") -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail=what)


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _json(v: Any) -> str:
    return json.dumps(v)


def _positions(raw) -> list[dict]:
    return [p for p in (raw or []) if isinstance(p, dict) and p.get("id")]


def _group_dict(row, *, extra: Optional[dict] = None) -> dict:
    token = row["public_token"]
    out = {
        "id": str(row["id"]),
        "name": row["name"],
        "kind": row["kind"],
        "positions": _positions(row["positions"]),
        "innings": row["innings"],
        "fairness": row["fairness"],
        "bats": row["bats"],
        "public_enabled": row["public_enabled"],
        "public_show_surnames": row["public_show_surnames"],
        "public_path": f"/rotation/{token}" if token else None,
        "archived": row["archived_at"] is not None,
    }
    out.update(extra or {})
    return out


def _player_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "avoid_positions": list(row["avoid_positions"] or []),
        "note": row["note"],
        "former_at": _iso(row["former_at"]),
    }


def _round_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "group_id": str(row["group_id"]),
        "round_date": _iso(row["round_date"]),
        "label": row["label"],
        "fixture_id": str(row["fixture_id"]) if row["fixture_id"] else None,
        "status": row["status"],
        "present": [str(p) for p in (row["present"] or [])],
        "batting_order": [str(p) for p in (row["batting_order"] or [])],
        "fielding": row["fielding"] or [],
        "warnings": row["warnings"] or [],
        "version": row["version"],
        "locked_at": _iso(row["locked_at"]),
    }


async def _group_row(db: AsyncSession, club: Organisation, group_id: str):
    gid = _uuid(group_id)
    row = (await db.execute(
        text("SELECT * FROM rotation_groups WHERE id = :g AND organisation_id = :o"),
        {"g": gid, "o": club.id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    return row


async def _players(db: AsyncSession, group_id) -> list[dict]:
    rows = (await db.execute(
        text("SELECT * FROM rotation_players WHERE group_id = :g ORDER BY sort_order, created_at, name"),
        {"g": group_id},
    )).mappings().all()
    return [_player_dict(r) for r in rows]


async def _round_row(db: AsyncSession, club: Organisation, round_id: str):
    rid = _uuid(round_id)
    row = (await db.execute(
        text("SELECT * FROM rotation_rounds WHERE id = :r AND organisation_id = :o"),
        {"r": rid, "o": club.id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Round not found")
    return row


async def _locked_rounds(db: AsyncSession, group_id, exclude=None) -> list[dict]:
    rows = (await db.execute(
        text("""SELECT * FROM rotation_rounds
                WHERE group_id = :g AND status = 'locked' AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))
                ORDER BY round_date, created_at"""),
        {"g": group_id, "x": exclude},
    )).mappings().all()
    return [_round_dict(r) for r in rows]


async def _valid_fixture(db: AsyncSession, club: Organisation, fixture_id) -> Optional[uuid.UUID]:
    if not fixture_id:
        return None
    fid = _uuid(fixture_id, "Fixture not found")
    ok = (await db.execute(
        text("SELECT 1 FROM fixtures WHERE id = :f AND organisation_id = :o"),
        {"f": fid, "o": club.id},
    )).first()
    if not ok:
        raise HTTPException(status_code=400, detail="That fixture is not one of this club's.")
    return fid


def _locked_409(row) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "locked", "message": "This round is locked. Unlock it to change it."})


def _clean_round_body(group_positions: list[dict], players: list[dict], present: list[str],
                      batting_order: Optional[list], fielding: Optional[list]) -> tuple[Optional[list], Optional[list]]:
    """Validate a hand-edited batting order and field against the group: only
    kids who are here, nobody twice, no position double-booked in a change,
    only positions the group has. Raises 400 in plain words."""
    ids = {p["id"] for p in players}
    here = set(present)
    pos_ids = {p["id"] for p in group_positions}
    order = None
    if batting_order is not None:
        order = [str(p) for p in batting_order]
        if len(set(order)) != len(order):
            raise HTTPException(status_code=400, detail="A player is in the batting order twice.")
        if any(p not in ids for p in order):
            raise HTTPException(status_code=400, detail="The batting order names someone who is not in this group.")
        if any(p not in here for p in order):
            raise HTTPException(status_code=400, detail="The batting order names someone who is not here.")
    field = None
    if fielding is not None:
        if not isinstance(fielding, list) or len(fielding) > 6:
            raise HTTPException(status_code=400, detail="The field is not in the shape the screen sends.")
        field = []
        for change in fielding:
            if not isinstance(change, dict):
                raise HTTPException(status_code=400, detail="The field is not in the shape the screen sends.")
            row: dict[str, Optional[str]] = {}
            used: set[str] = set()
            for pid, pos in change.items():
                pid = str(pid)
                if pid not in ids or pid not in here:
                    raise HTTPException(status_code=400, detail="The field names someone who is not here.")
                if pos is not None and str(pos) not in pos_ids:
                    raise HTTPException(status_code=400, detail="The field names a position this group does not have.")
                if pos is not None:
                    if str(pos) in used:
                        raise HTTPException(status_code=400, detail="Two players are on the same position.")
                    used.add(str(pos))
                row[pid] = str(pos) if pos is not None else None
            field.append(row)
    return order, field


# ─── presets and groups ─────────────────────────────────────────────────────

@router.get("/presets")
async def presets(_: User = Depends(_GATE)):
    return {"presets": [
        {"key": k, "label": v["label"], "innings": v["innings"],
         "positions": [{"name": n, "key": key} for n, key in v["positions"]]}
        for k, v in rot.PRESETS.items()
    ]}


@router.get("/groups")
async def list_groups(
    archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    rows = (await db.execute(text("""
        SELECT g.*,
          (SELECT COUNT(*) FROM rotation_players p WHERE p.group_id = g.id AND p.former_at IS NULL) AS n_players,
          (SELECT COUNT(*) FROM rotation_rounds r WHERE r.group_id = g.id AND r.status = 'locked') AS n_locked,
          (SELECT MAX(r.round_date) FROM rotation_rounds r WHERE r.group_id = g.id AND r.status = 'locked') AS last_round
        FROM rotation_groups g
        WHERE g.organisation_id = :o AND ((:a AND g.archived_at IS NOT NULL) OR (NOT :a AND g.archived_at IS NULL))
        ORDER BY g.name
    """), {"o": club.id, "a": archived})).mappings().all()
    return {"groups": [
        _group_dict(r, extra={"player_count": r["n_players"], "locked_rounds": r["n_locked"], "last_round": _iso(r["last_round"])})
        for r in rows
    ]}


class GroupCreate(BaseModel):
    name: str
    preset: str = "custom"
    names: Optional[str] = None
    innings: Optional[int] = None


@router.post("/groups")
async def create_group(
    body: GroupCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(_GATE),
):
    name = rot.clean_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Give the group a name.")
    kind = body.preset if body.preset in rot.PRESETS else "custom"
    innings = body.innings if body.innings is not None else rot.PRESETS[kind]["innings"]
    innings = max(1, min(6, int(innings)))
    gid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO rotation_groups (id, organisation_id, name, kind, positions, innings, created_by)
        VALUES (:id, :o, :n, :k, CAST(:p AS jsonb), :i, :u)
    """), {"id": gid, "o": club.id, "n": name, "k": kind, "p": _json(rot.preset_positions(kind)), "i": innings, "u": user.id})
    for i, nm in enumerate(rot.split_names(body.names or "")):
        await db.execute(text(
            "INSERT INTO rotation_players (group_id, organisation_id, name, sort_order) VALUES (:g, :o, :n, :s)"
        ), {"g": gid, "o": club.id, "n": nm, "s": i})
    await db.commit()
    return await get_group(str(gid), db, club, user)


@router.get("/groups/{group_id}")
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    row = await _group_row(db, club, group_id)
    return {"group": _group_dict(row), "players": await _players(db, row["id"])}


class GroupPatch(BaseModel):
    name: Optional[str] = None
    positions: Optional[list] = None
    innings: Optional[int] = None
    fairness: Optional[int] = None
    bats: Optional[bool] = None
    public_enabled: Optional[bool] = None
    public_show_surnames: Optional[bool] = None


@router.patch("/groups/{group_id}")
async def patch_group(
    group_id: str,
    body: GroupPatch,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(_GATE),
):
    row = await _group_row(db, club, group_id)
    sent = body.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"g": row["id"]}
    if "name" in sent:
        name = rot.clean_name(body.name)
        if not name:
            raise HTTPException(status_code=400, detail="Give the group a name.")
        sets.append("name = :name")
        params["name"] = name
    if "positions" in sent:
        sets.append("positions = CAST(:positions AS jsonb)")
        params["positions"] = _json(rot.clean_positions(body.positions, _positions(row["positions"])))
    if "innings" in sent and body.innings is not None:
        sets.append("innings = :innings")
        params["innings"] = max(1, min(6, int(body.innings)))
    if "fairness" in sent and body.fairness is not None:
        sets.append("fairness = :fairness")
        params["fairness"] = max(0, min(100, int(body.fairness)))
    if "bats" in sent and body.bats is not None:
        sets.append("bats = :bats")
        params["bats"] = bool(body.bats)
    if "public_show_surnames" in sent and body.public_show_surnames is not None:
        sets.append("public_show_surnames = :surn")
        params["surn"] = bool(body.public_show_surnames)
    if "public_enabled" in sent and body.public_enabled is not None:
        sets.append("public_enabled = :pe")
        params["pe"] = bool(body.public_enabled)
        if body.public_enabled and not row["public_token"]:
            sets.append("public_token = :tok")
            params["tok"] = secrets.token_urlsafe(18)
    if sets:
        sets.append("updated_at = NOW()")
        await db.execute(text(f"UPDATE rotation_groups SET {', '.join(sets)} WHERE id = :g"), params)
        await db.commit()
    return await get_group(group_id, db, club, user)


@router.post("/groups/{group_id}/regenerate-link")
async def regenerate_link(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(_GATE),
):
    row = await _group_row(db, club, group_id)
    await db.execute(
        text("UPDATE rotation_groups SET public_token = :t, updated_at = NOW() WHERE id = :g"),
        {"t": secrets.token_urlsafe(18), "g": row["id"]},
    )
    await db.commit()
    return await get_group(group_id, db, club, user)


@router.post("/groups/{group_id}/archive")
async def archive_group(
    group_id: str,
    undo: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Archive, never delete: a season of locked rounds is the club's record."""
    row = await _group_row(db, club, group_id)
    await db.execute(
        text("UPDATE rotation_groups SET archived_at = CASE WHEN :undo THEN NULL ELSE NOW() END, updated_at = NOW() WHERE id = :g"),
        {"g": row["id"], "undo": undo},
    )
    await db.commit()
    return {"ok": True}


# ─── players (typed names) ──────────────────────────────────────────────────

class PlayersAdd(BaseModel):
    names: str


@router.post("/groups/{group_id}/players")
async def add_players(
    group_id: str,
    body: PlayersAdd,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Add names (one a line or comma separated). A name already in the group is
    skipped; a name that belonged to a kid who left brings that kid back, so
    their history comes with them instead of starting a second person."""
    row = await _group_row(db, club, group_id)
    existing = await _players(db, row["id"])
    by_name = {p["name"].casefold(): p for p in existing}
    nxt = len(existing)
    added = revived = skipped = 0
    for nm in rot.split_names(body.names):
        hit = by_name.get(nm.casefold())
        if hit and not hit["former_at"]:
            skipped += 1
        elif hit:
            await db.execute(text("UPDATE rotation_players SET former_at = NULL WHERE id = :i"), {"i": uuid.UUID(hit["id"])})
            revived += 1
        else:
            await db.execute(text(
                "INSERT INTO rotation_players (group_id, organisation_id, name, sort_order) VALUES (:g, :o, :n, :s)"
            ), {"g": row["id"], "o": club.id, "n": nm, "s": nxt})
            nxt += 1
            added += 1
    await db.commit()
    return {"added": added, "returned": revived, "skipped": skipped, "players": await _players(db, row["id"])}


class PlayerPatch(BaseModel):
    name: Optional[str] = None
    avoid_positions: Optional[list[str]] = None
    note: Optional[str] = None
    active: Optional[bool] = None


@router.patch("/players/{player_id}")
async def patch_player(
    player_id: str,
    body: PlayerPatch,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    pid = _uuid(player_id, "Player not found")
    prow = (await db.execute(
        text("SELECT * FROM rotation_players WHERE id = :i AND organisation_id = :o"),
        {"i": pid, "o": club.id},
    )).mappings().first()
    if not prow:
        raise HTTPException(status_code=404, detail="Player not found")
    sent = body.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"i": pid}
    if "name" in sent:
        nm = rot.clean_name(body.name)
        if not nm:
            raise HTTPException(status_code=400, detail="A player needs a name.")
        clash = (await db.execute(text(
            "SELECT 1 FROM rotation_players WHERE group_id = :g AND id <> :i AND former_at IS NULL AND lower(name) = lower(:n)"
        ), {"g": prow["group_id"], "i": pid, "n": nm})).first()
        if clash:
            raise HTTPException(status_code=400, detail="Someone in this group already has that name.")
        sets.append("name = :n")
        params["n"] = nm
    if "avoid_positions" in sent:
        grp = await _group_row(db, club, str(prow["group_id"]))
        valid = {p["id"] for p in _positions(grp["positions"])}
        sets.append("avoid_positions = CAST(:av AS jsonb)")
        params["av"] = _json([a for a in dict.fromkeys(body.avoid_positions or []) if a in valid])
    if "note" in sent:
        sets.append("note = :note")
        params["note"] = (body.note or "").strip()[:200] or None
    if "active" in sent and body.active is not None:
        sets.append("former_at = NULL" if body.active else "former_at = COALESCE(former_at, NOW())")
    if sets:
        await db.execute(text(f"UPDATE rotation_players SET {', '.join(sets)} WHERE id = :i"), params)
        await db.commit()
    row = (await db.execute(text("SELECT * FROM rotation_players WHERE id = :i"), {"i": pid})).mappings().first()
    return {"player": _player_dict(row)}


# ─── rounds ─────────────────────────────────────────────────────────────────

@router.get("/fixtures")
async def fixtures_to_tie(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Fixtures a round can be tied to: the last fortnight and the next two
    months, not cancelled, soonest first."""
    today = date.today()
    rows = (await db.execute(text("""
        SELECT f.id, f.played_on, f.label, f.round, f.opponent_name, f.home_away, f.start_time, t.name AS team_name
        FROM fixtures f LEFT JOIN teams t ON t.id = f.team_id
        WHERE f.organisation_id = :o AND f.played_on BETWEEN :a AND :b
          AND f.status NOT IN ('CANCELLED', 'BYE')
        ORDER BY f.played_on, f.start_time NULLS LAST, f.id
        LIMIT 120
    """), {"o": club.id, "a": today - timedelta(days=14), "b": today + timedelta(days=60)})).mappings().all()
    return {"fixtures": [{
        "id": str(r["id"]), "date": _iso(r["played_on"]), "team": r["team_name"],
        "opponent": r["opponent_name"], "round": r["round"], "label": r["label"],
        "home_away": r["home_away"], "start_time": r["start_time"],
    } for r in rows]}


@router.get("/groups/{group_id}/rounds")
async def list_rounds(
    group_id: str,
    limit: int = Query(60, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    grp = await _group_row(db, club, group_id)
    rows = (await db.execute(text(
        "SELECT * FROM rotation_rounds WHERE group_id = :g ORDER BY round_date DESC, created_at DESC LIMIT :l"
    ), {"g": grp["id"], "l": limit})).mappings().all()
    return {"rounds": [_round_dict(r) for r in rows]}


def _generate_for(grp, players: list[dict], present: list[str], history_rounds: list[dict]) -> dict:
    active = {p["id"]: p for p in players}
    here = [p for p in present if p in active]
    positions = _positions(grp["positions"])
    avoid = {p["id"]: p["avoid_positions"] for p in players if p["avoid_positions"]}
    return rot.generate(
        here, positions, rot.history_stats(history_rounds),
        innings=grp["innings"], fairness=grp["fairness"], bats=grp["bats"], avoid=avoid,
    )


class RoundCreate(BaseModel):
    round_date: Optional[date] = None
    label: Optional[str] = None
    fixture_id: Optional[str] = None
    present: Optional[list[str]] = None
    generate: bool = True


@router.post("/groups/{group_id}/rounds")
async def create_round(
    group_id: str,
    body: RoundCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(_GATE),
):
    grp = await _group_row(db, club, group_id)
    players = await _players(db, grp["id"])
    live = [p["id"] for p in players if not p["former_at"]]
    present = [p for p in (body.present if body.present is not None else live) if p in live]
    fid = await _valid_fixture(db, club, body.fixture_id)
    rdate, label = body.round_date, (body.label or "").strip()[:80] or None
    if fid:
        fx = (await db.execute(text(
            "SELECT played_on, opponent_name FROM fixtures WHERE id = :f"), {"f": fid})).mappings().first()
        rdate = rdate or fx["played_on"]
        if not label and fx["opponent_name"]:
            label = f"vs {fx['opponent_name']}"
    rdate = rdate or date.today()
    result = {"batting_order": [], "fielding": [], "warnings": []}
    if body.generate and present:
        result = _generate_for(grp, players, present, await _locked_rounds(db, grp["id"]))
    rid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO rotation_rounds (id, group_id, organisation_id, round_date, label, fixture_id,
                                     present, batting_order, fielding, warnings, created_by)
        VALUES (:id, :g, :o, :d, :l, :f, CAST(:pr AS jsonb), CAST(:bo AS jsonb), CAST(:fi AS jsonb), CAST(:w AS jsonb), :u)
    """), {"id": rid, "g": grp["id"], "o": club.id, "d": rdate, "l": label, "f": fid,
           "pr": _json(present), "bo": _json(result["batting_order"]), "fi": _json(result["fielding"]),
           "w": _json(result["warnings"]), "u": user.id})
    await db.commit()
    return {"round": _round_dict(await _round_row(db, club, str(rid)))}


@router.get("/rounds/{round_id}")
async def get_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    row = await _round_row(db, club, round_id)
    grp = await _group_row(db, club, str(row["group_id"]))
    return {"round": _round_dict(row), "group": _group_dict(grp), "players": await _players(db, grp["id"])}


class RoundPut(BaseModel):
    version: int
    present: Optional[list[str]] = None
    batting_order: Optional[list[str]] = None
    fielding: Optional[list[dict]] = None
    label: Optional[str] = None
    round_date: Optional[date] = None
    fixture_id: Optional[str] = None


def _conflict(row) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "conflict",
        "message": "Someone else changed this round. Reload to see their version.",
        "round": _round_dict(row),
    })


@router.put("/rounds/{round_id}")
async def put_round(
    round_id: str,
    body: RoundPut,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Edit a draft by hand. A field absent from the body is left alone, an
    explicit null on ``fixture_id`` or ``label`` clears it."""
    row = await _round_row(db, club, round_id)
    if row["status"] == "locked":
        raise _locked_409(row)
    if row["version"] != body.version:
        raise _conflict(row)
    grp = await _group_row(db, club, str(row["group_id"]))
    players = await _players(db, grp["id"])
    live = {p["id"] for p in players if not p["former_at"]}
    sent = body.model_fields_set
    present = [str(p) for p in (body.present if "present" in sent and body.present is not None else row["present"] or [])]
    if "present" in sent and any(p not in live for p in present):
        raise HTTPException(status_code=400, detail="That is not someone in this group.")
    order, field = _clean_round_body(
        _positions(grp["positions"]), players, present,
        body.batting_order if "batting_order" in sent else None,
        body.fielding if "fielding" in sent else None,
    )
    sets = ["version = version + 1", "updated_at = NOW()"]
    params: dict[str, Any] = {"r": row["id"], "v": body.version}
    if "present" in sent and body.present is not None:
        sets.append("present = CAST(:present AS jsonb)")
        params["present"] = _json(present)
        # Someone sent home is out of the order and off the field; someone who
        # turns up late goes to the end of the order and rests until the coach
        # places them, so nobody who is here is missing from the round.
        if order is None:
            kept = [p for p in (row["batting_order"] or []) if p in present]
            order = kept + ([p for p in present if p not in kept] if grp["bats"] else [])
        if field is None:
            field = [{**{k: v for k, v in (c or {}).items() if k in present},
                      **{p: None for p in present if p not in (c or {})}} for c in (row["fielding"] or [])]
    if order is not None:
        sets.append("batting_order = CAST(:bo AS jsonb)")
        params["bo"] = _json(order)
    if field is not None:
        sets.append("fielding = CAST(:fi AS jsonb)")
        params["fi"] = _json(field)
        avoid = {p["id"]: p["avoid_positions"] for p in players if p["avoid_positions"]}
        sets.append("warnings = CAST(:w AS jsonb)")
        params["w"] = _json(rot.round_warnings(_positions(grp["positions"]), field, avoid))
    if "label" in sent:
        sets.append("label = :label")
        params["label"] = (body.label or "").strip()[:80] or None
    if "round_date" in sent and body.round_date is not None:
        sets.append("round_date = :d")
        params["d"] = body.round_date
    if "fixture_id" in sent:
        sets.append("fixture_id = :f")
        params["f"] = await _valid_fixture(db, club, body.fixture_id)
    res = await db.execute(text(
        f"UPDATE rotation_rounds SET {', '.join(sets)} WHERE id = :r AND version = :v AND status = 'draft'"), params)
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict(await _round_row(db, club, round_id))
    await db.commit()
    return {"round": _round_dict(await _round_row(db, club, round_id))}


class RoundGenerate(BaseModel):
    part: str = "all"
    present: Optional[list[str]] = None
    version: Optional[int] = None


@router.post("/rounds/{round_id}/generate")
async def regenerate_round(
    round_id: str,
    body: RoundGenerate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Re-roll a draft. The history it leans on is every OTHER locked round, so
    rolling again and again never changes anything but this draft."""
    row = await _round_row(db, club, round_id)
    if row["status"] == "locked":
        raise _locked_409(row)
    if body.version is not None and row["version"] != body.version:
        raise _conflict(row)
    grp = await _group_row(db, club, str(row["group_id"]))
    players = await _players(db, grp["id"])
    live = {p["id"] for p in players if not p["former_at"]}
    present = [str(p) for p in (body.present if body.present is not None else row["present"] or [])]
    present = [p for p in present if p in live]
    result = _generate_for(grp, players, present, await _locked_rounds(db, grp["id"], exclude=row["id"]))
    part = body.part if body.part in ("all", "batting", "fielding") else "all"
    order = result["batting_order"] if part in ("all", "batting") else [p for p in (row["batting_order"] or []) if p in present]
    field = result["fielding"] if part in ("all", "fielding") else [
        {k: v for k, v in (c or {}).items() if k in present} for c in (row["fielding"] or [])]
    avoid = {p["id"]: p["avoid_positions"] for p in players if p["avoid_positions"]}
    warnings = rot.round_warnings(_positions(grp["positions"]), field, avoid)
    res = await db.execute(text("""
        UPDATE rotation_rounds SET present = CAST(:pr AS jsonb), batting_order = CAST(:bo AS jsonb),
            fielding = CAST(:fi AS jsonb), warnings = CAST(:w AS jsonb),
            version = version + 1, updated_at = NOW()
        WHERE id = :r AND version = :v AND status = 'draft'
    """), {"pr": _json(present), "bo": _json(order), "fi": _json(field), "w": _json(warnings),
           "r": row["id"], "v": row["version"]})
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict(await _round_row(db, club, round_id))
    await db.commit()
    return {"round": _round_dict(await _round_row(db, club, round_id))}


@router.post("/rounds/{round_id}/lock")
async def lock_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(_GATE),
):
    row = await _round_row(db, club, round_id)
    if row["status"] == "locked":
        return {"round": _round_dict(row)}
    if not (row["present"] or []):
        raise HTTPException(status_code=400, detail="Tick who is here before locking the round.")
    if not (row["batting_order"] or row["fielding"]):
        raise HTTPException(status_code=400, detail="There is nothing to lock yet. Generate the round first.")
    await db.execute(text("""
        UPDATE rotation_rounds SET status = 'locked', locked_at = NOW(), locked_by = :u,
            version = version + 1, updated_at = NOW() WHERE id = :r
    """), {"u": user.id, "r": row["id"]})
    await db.commit()
    return {"round": _round_dict(await _round_row(db, club, round_id))}


@router.post("/rounds/{round_id}/unlock")
async def unlock_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    row = await _round_row(db, club, round_id)
    if row["status"] != "locked":
        return {"round": _round_dict(row)}
    await db.execute(text("""
        UPDATE rotation_rounds SET status = 'draft', locked_at = NULL, locked_by = NULL,
            version = version + 1, updated_at = NOW() WHERE id = :r
    """), {"r": row["id"]})
    await db.commit()
    return {"round": _round_dict(await _round_row(db, club, round_id))}


@router.delete("/rounds/{round_id}")
async def delete_round(
    round_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    """Drafts only. A locked round is history the club decided something about:
    unlock it first."""
    row = await _round_row(db, club, round_id)
    if row["status"] == "locked":
        raise _locked_409(row)
    await db.execute(text("DELETE FROM rotation_rounds WHERE id = :r"), {"r": row["id"]})
    await db.commit()
    return {"ok": True}


@router.get("/groups/{group_id}/tally")
async def group_tally(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(_GATE),
):
    grp = await _group_row(db, club, group_id)
    players = await _players(db, grp["id"])
    return rot.tally(players, _positions(grp["positions"]), await _locked_rounds(db, grp["id"]))
