"""BetterSelect Fines: the admin side (a squad's fines tracker).

After a game a side runs a fines session and the money goes into a pot. This is
the tracker for it: who was fined what and when, who has paid, and the details a
player needs to pay (PayID, bank transfer). It is switched on per squad, and the
players see their own balance on their page (``public_availability``).

* Entering fines and recording payments is the BetterSelect selector's job, so
  every route here needs ``MANAGE_SELECTIONS``. The whole router sits behind
  ``require_module("select")`` at registration in ``main.py``.
* A balance is derived (fined minus paid, voided rows left out) and never stored.
* Nothing is deleted. A wrong fine or payment is voided and can be restored; a
  fine type that is no longer used is archived. ``fine_entries.amount`` is the
  amount at the time, so editing a type's price does not rewrite history.
* A PATCH only touches the fields it carries (``model_fields_set``), so leaving a
  field out never clears it and an explicit empty value does.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import active_self_service_players
from app.services import fines as fines_svc

router = APIRouter(prefix="/fines", tags=["fines"])

WEEKS_SHOWN = 6          # fine dates (columns) on the tracker
MAX_ITEMS = 100          # lines in one fines session
MAX_QUANTITY = 20
TEXT_MAX = 300
METHOD_MAX = 40


class SettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    payid: Optional[str] = None
    payid_name: Optional[str] = None
    account_name: Optional[str] = None
    bsb: Optional[str] = None
    account_number: Optional[str] = None
    reference_hint: Optional[str] = None
    other_instructions: Optional[str] = None


class TypeIn(BaseModel):
    name: str
    amount: float | str


class TypePatch(BaseModel):
    name: Optional[str] = None
    amount: Optional[float | str] = None
    archived: Optional[bool] = None


class FineItem(BaseModel):
    player_id: str
    fine_type_id: Optional[str] = None
    reason: Optional[str] = None
    amount: Optional[float | str] = None
    quantity: int = 1


class EntriesIn(BaseModel):
    fined_on: date
    items: list[FineItem]


class PaymentIn(BaseModel):
    player_id: str
    amount: float | str
    paid_on: Optional[date] = None
    method: Optional[str] = None
    note: Optional[str] = None


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")


def _clean(value: Optional[str], limit: int = TEXT_MAX) -> Optional[str]:
    v = (value or "").strip()
    return v[:limit] or None


def _amount(value, *, allow_zero: bool = False):
    try:
        return fines_svc.parse_amount(value, allow_zero=allow_zero)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _check_date(d: date, what: str) -> date:
    today = date.today()
    # A day of slack either way for the club's timezone being ahead of the server.
    if d > today + timedelta(days=1):
        raise HTTPException(status_code=422, detail=f"The {what} can't be in the future")
    if d < today - timedelta(days=366 * 5):
        raise HTTPException(status_code=422, detail=f"That {what} is too long ago")
    return d


async def _squad_or_404(db: AsyncSession, club: Organisation, team_id: str) -> dict:
    tid = _uuid(team_id, "squad")
    row = (await db.execute(
        text(
            "SELECT id, COALESCE(NULLIF(short_name, ''), name) AS name FROM teams "
            "WHERE id = :t AND organisation_id = :org"
        ),
        {"t": tid, "org": club.id},
    )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Squad not found")
    return dict(row)


async def _ensure_settings(db: AsyncSession, club: Organisation, team_id) -> None:
    await db.execute(
        text(
            "INSERT INTO fine_settings (team_id, organisation_id) VALUES (:t, :org) "
            "ON CONFLICT (team_id) DO NOTHING"
        ),
        {"t": team_id, "org": club.id},
    )


async def _settings(db: AsyncSession, club: Organisation, team_id) -> dict:
    row = (await db.execute(
        text(
            "SELECT enabled, payid, payid_name, account_name, bsb, account_number, "
            "reference_hint, other_instructions FROM fine_settings "
            "WHERE team_id = :t AND organisation_id = :org"
        ),
        {"t": team_id, "org": club.id},
    )).mappings().first()
    out = {"enabled": False, **{k: "" for k in fines_svc.PAY_FIELDS}}
    if row:
        out["enabled"] = bool(row["enabled"])
        for k in fines_svc.PAY_FIELDS:
            out[k] = row[k] or ""
    return out


async def _types(db: AsyncSession, club: Organisation, team_id, archived: bool = False) -> list[dict]:
    rows = (await db.execute(
        text(
            "SELECT id, name, amount, archived_at FROM fine_types "
            "WHERE organisation_id = :org AND team_id = :t "
            "AND ((:arch AND archived_at IS NOT NULL) OR (NOT :arch AND archived_at IS NULL)) "
            "ORDER BY sequence, lower(name)"
        ),
        {"org": club.id, "t": team_id, "arch": archived},
    )).fetchall()
    return [{"id": str(i), "name": n, "amount": fines_svc.money(a)} for i, n, a, _ in rows]


@router.get("/squads")
async def list_squads(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Every active squad, whether Fines is on for it, and what is still owed."""
    rows = (await db.execute(
        text(
            "SELECT t.id, COALESCE(NULLIF(t.short_name, ''), t.name), COALESCE(fs.enabled, false), "
            "(SELECT COALESCE(SUM(amount), 0) FROM fine_entries fe "
            "  WHERE fe.team_id = t.id AND fe.voided_at IS NULL) - "
            "(SELECT COALESCE(SUM(amount), 0) FROM fine_payments fp "
            "  WHERE fp.team_id = t.id AND fp.voided_at IS NULL) "
            "FROM teams t LEFT JOIN fine_settings fs ON fs.team_id = t.id "
            "WHERE t.organisation_id = :org AND COALESCE(t.is_active, true) "
            "ORDER BY t.sequence NULLS LAST, t.name"
        ),
        {"org": club.id},
    )).fetchall()
    return {"squads": [
        {"id": str(i), "name": n, "enabled": bool(en), "owing": fines_svc.money(owed)}
        for i, n, en, owed in rows
    ]}


@router.get("/squads/{team_id}")
async def get_squad(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """One squad's tracker: settings, fine list, and every player's fines by date
    with what they owe. The players are the squad plus anyone who has been fined
    or has paid in it (a fill-in); `candidates` are the other active players, for
    adding a fine to somebody outside the squad."""
    squad = await _squad_or_404(db, club, team_id)
    tid = squad["id"]
    totals = await fines_svc.squad_totals(db, club.id, tid)

    member_ids = {r[0] for r in (await db.execute(
        text("SELECT player_id FROM team_members WHERE team_id = :t AND organisation_id = :org"),
        {"t": tid, "org": club.id},
    )).fetchall()}
    ids = member_ids | set(totals.keys())
    players = {}
    if ids:
        for p in (await db.execute(
            select(Player).where(Player.id.in_(ids), Player.organisation_id == club.id)
        )).scalars().all():
            players[p.id] = p

    date_rows = (await db.execute(
        text(
            "SELECT DISTINCT fined_on FROM fine_entries WHERE organisation_id = :org AND team_id = :t "
            "AND voided_at IS NULL ORDER BY fined_on DESC LIMIT :n"
        ),
        {"org": club.id, "t": tid, "n": WEEKS_SHOWN},
    )).fetchall()
    dates = [d for (d,) in date_rows]
    by_date: dict = {}
    if dates:
        for pid, d, amt in (await db.execute(
            text(
                "SELECT player_id, fined_on, SUM(amount) FROM fine_entries "
                "WHERE organisation_id = :org AND team_id = :t AND voided_at IS NULL "
                "AND fined_on = ANY(CAST(:ds AS date[])) GROUP BY player_id, fined_on"
            ),
            {"org": club.id, "t": tid, "ds": dates},
        )).fetchall():
            by_date.setdefault(pid, {})[d.isoformat()] = fines_svc.money(amt)

    rows = []
    for pid, p in players.items():
        t = totals.get(pid, {"fined": 0.0, "paid": 0.0})
        rows.append({
            "player_id": str(pid),
            "name": p.display_name,
            "in_squad": pid in member_ids,
            "by_date": by_date.get(pid, {}),
            "fined": t["fined"], "paid": t["paid"],
            "owing": round(t["fined"] - t["paid"], 2),
        })
    rows.sort(key=lambda r: (not r["in_squad"], r["name"].lower()))

    taken = set(players.keys())
    candidates = sorted(
        ({"id": str(p.id), "name": p.display_name}
         for p in await active_self_service_players(db, club) if p.id not in taken),
        key=lambda c: c["name"].lower(),
    )

    fined = round(sum(t["fined"] for t in totals.values()), 2)
    paid = round(sum(t["paid"] for t in totals.values()), 2)
    return {
        "squad": {"id": str(tid), "name": squad["name"]},
        "settings": await _settings(db, club, tid),
        "types": await _types(db, club, tid),
        "archived_types": await _types(db, club, tid, archived=True),
        "dates": [d.isoformat() for d in dates],
        "players": rows,
        "candidates": candidates,
        # `paid` is what is in the pot; `owing` is what is still to come in.
        "totals": {"fined": fined, "paid": paid, "owing": round(fined - paid, 2)},
    }


@router.patch("/squads/{team_id}/settings")
async def patch_settings(
    team_id: str,
    body: SettingsPatch,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Switch Fines on or off for a squad and set how players pay. A field that is
    not sent is left alone; an empty string clears it."""
    squad = await _squad_or_404(db, club, team_id)
    await _ensure_settings(db, club, squad["id"])
    sets, params = [], {"t": squad["id"], "org": club.id}
    sent = body.model_fields_set
    if "enabled" in sent and body.enabled is not None:
        sets.append("enabled = :enabled")
        params["enabled"] = bool(body.enabled)
    for k in fines_svc.PAY_FIELDS:
        if k in sent:
            sets.append(f"{k} = :{k}")
            params[k] = _clean(getattr(body, k))
    if sets:
        await db.execute(
            text(f"UPDATE fine_settings SET {', '.join(sets)}, updated_at = NOW() "
                 "WHERE team_id = :t AND organisation_id = :org"),
            params,
        )
    await db.commit()
    return {"settings": await _settings(db, club, squad["id"])}


@router.post("/squads/{team_id}/types")
async def create_type(
    team_id: str,
    body: TypeIn,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    squad = await _squad_or_404(db, club, team_id)
    name = _clean(body.name, 80)
    if not name:
        raise HTTPException(status_code=422, detail="Give the fine a name")
    amount = _amount(body.amount)
    dup = (await db.execute(
        text("SELECT 1 FROM fine_types WHERE team_id = :t AND archived_at IS NULL AND lower(name) = lower(:n)"),
        {"t": squad["id"], "n": name},
    )).first()
    if dup:
        raise HTTPException(status_code=409, detail="There is already a fine with that name")
    new_id = (await db.execute(
        text(
            "INSERT INTO fine_types (organisation_id, team_id, name, amount, sequence) "
            "VALUES (:org, :t, :n, :a, COALESCE((SELECT MAX(sequence) + 1 FROM fine_types WHERE team_id = :t), 0)) "
            "RETURNING id"
        ),
        {"org": club.id, "t": squad["id"], "n": name, "a": amount},
    )).scalar_one()
    await db.commit()
    return {"id": str(new_id), "name": name, "amount": float(amount)}


@router.patch("/types/{type_id}")
async def patch_type(
    type_id: str,
    body: TypePatch,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Rename, reprice, archive or bring back a fine type. Fines already handed out
    keep the name and amount they were given."""
    tid = _uuid(type_id, "fine")
    row = (await db.execute(
        text("SELECT team_id FROM fine_types WHERE id = :i AND organisation_id = :org"),
        {"i": tid, "org": club.id},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fine not found")
    sets, params = [], {"i": tid, "org": club.id}
    sent = body.model_fields_set
    if "name" in sent:
        name = _clean(body.name, 80)
        if not name:
            raise HTTPException(status_code=422, detail="Give the fine a name")
        sets.append("name = :n"); params["n"] = name
    if "amount" in sent and body.amount is not None:
        sets.append("amount = :a"); params["a"] = _amount(body.amount)
    if "archived" in sent and body.archived is not None:
        sets.append("archived_at = NOW()" if body.archived else "archived_at = NULL")
    if sets:
        await db.execute(
            text(f"UPDATE fine_types SET {', '.join(sets)} WHERE id = :i AND organisation_id = :org"), params)
    await db.commit()
    return {"status": "ok"}


@router.post("/squads/{team_id}/entries")
async def add_entries(
    team_id: str,
    body: EntriesIn,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Record a fines session: any number of fines for any number of players on
    one date. Each fine is its own row (so one can be voided on its own). A line
    takes its reason and amount from a fine type unless they are typed over, and
    a quantity above one adds that many rows."""
    squad = await _squad_or_404(db, club, team_id)
    if not body.items:
        raise HTTPException(status_code=422, detail="Add at least one fine")
    if len(body.items) > MAX_ITEMS:
        raise HTTPException(status_code=422, detail=f"No more than {MAX_ITEMS} lines at a time")
    fined_on = _check_date(body.fined_on, "fine date")

    types = {t["id"]: t for t in await _types(db, club, squad["id"])}
    pids = {_uuid(i.player_id, "player") for i in body.items}
    found = {r[0] for r in (await db.execute(
        text("SELECT id FROM players WHERE organisation_id = :org AND id = ANY(CAST(:ids AS uuid[]))"),
        {"org": club.id, "ids": list(pids)},
    )).fetchall()}
    if pids - found:
        raise HTTPException(status_code=404, detail="A player on that list isn't in this club")

    rows = []
    for n, item in enumerate(body.items, 1):
        ftype = None
        if item.fine_type_id:
            ftype = types.get(str(_uuid(item.fine_type_id, "fine")))
            if ftype is None:
                raise HTTPException(status_code=422, detail=f"Line {n}: that fine is no longer on the list")
        reason = _clean(item.reason, 120) or (ftype["name"] if ftype else None)
        if not reason:
            raise HTTPException(status_code=422, detail=f"Line {n}: say what the fine was for")
        if item.amount not in (None, ""):
            amount = _amount(item.amount)
        elif ftype:
            amount = _amount(ftype["amount"])
        else:
            raise HTTPException(status_code=422, detail=f"Line {n}: enter an amount")
        qty = item.quantity if item.quantity else 1
        if qty < 1 or qty > MAX_QUANTITY:
            raise HTTPException(status_code=422, detail=f"Line {n}: quantity must be 1 to {MAX_QUANTITY}")
        for _ in range(qty):
            rows.append({
                "org": club.id, "t": squad["id"], "p": uuid.UUID(item.player_id),
                "ft": uuid.UUID(ftype["id"]) if ftype else None,
                "r": reason, "a": amount, "d": fined_on, "u": user.id,
            })
    await db.execute(
        text(
            "INSERT INTO fine_entries (organisation_id, team_id, player_id, fine_type_id, reason, amount, fined_on, created_by) "
            "VALUES (:org, :t, :p, :ft, :r, :a, :d, :u)"
        ),
        rows,
    )
    await db.commit()
    return {"created": len(rows), "total": float(sum(r["a"] for r in rows))}


async def _set_void(db: AsyncSession, club: Organisation, user: User, table: str, row_id: str, void: bool) -> None:
    rid = _uuid(row_id, "entry")
    res = await db.execute(
        text(
            f"UPDATE {table} SET voided_at = {'NOW()' if void else 'NULL'}, "
            f"voided_by = {':u' if void else 'NULL'} WHERE id = :i AND organisation_id = :org"
        ),
        {"i": rid, "org": club.id, **({"u": user.id} if void else {})},
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.commit()


@router.post("/entries/{entry_id}/void")
async def void_entry(entry_id: str, db: AsyncSession = Depends(get_db),
                     club: Organisation = Depends(get_current_club),
                     user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    await _set_void(db, club, user, "fine_entries", entry_id, True)
    return {"status": "ok"}


@router.post("/entries/{entry_id}/restore")
async def restore_entry(entry_id: str, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    await _set_void(db, club, user, "fine_entries", entry_id, False)
    return {"status": "ok"}


@router.post("/squads/{team_id}/payments")
async def add_payment(
    team_id: str,
    body: PaymentIn,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Record money a player has tipped into the pot. More than they owe is
    allowed (it shows as credit)."""
    squad = await _squad_or_404(db, club, team_id)
    pid = _uuid(body.player_id, "player")
    if (await db.execute(
        text("SELECT 1 FROM players WHERE id = :p AND organisation_id = :org"),
        {"p": pid, "org": club.id},
    )).first() is None:
        raise HTTPException(status_code=404, detail="That player isn't in this club")
    amount = _amount(body.amount)
    paid_on = _check_date(body.paid_on or date.today(), "payment date")
    new_id = (await db.execute(
        text(
            "INSERT INTO fine_payments (organisation_id, team_id, player_id, amount, paid_on, method, note, recorded_by) "
            "VALUES (:org, :t, :p, :a, :d, :m, :n, :u) RETURNING id"
        ),
        {"org": club.id, "t": squad["id"], "p": pid, "a": amount, "d": paid_on,
         "m": _clean(body.method, METHOD_MAX), "n": _clean(body.note), "u": user.id},
    )).scalar_one()
    await db.commit()
    return {"id": str(new_id)}


@router.post("/payments/{payment_id}/void")
async def void_payment(payment_id: str, db: AsyncSession = Depends(get_db),
                       club: Organisation = Depends(get_current_club),
                       user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    await _set_void(db, club, user, "fine_payments", payment_id, True)
    return {"status": "ok"}


@router.post("/payments/{payment_id}/restore")
async def restore_payment(payment_id: str, db: AsyncSession = Depends(get_db),
                          club: Organisation = Depends(get_current_club),
                          user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    await _set_void(db, club, user, "fine_payments", payment_id, False)
    return {"status": "ok"}


@router.get("/squads/{team_id}/players/{player_id}/ledger")
async def player_ledger(
    team_id: str,
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Every fine and payment for one player in a squad, newest first, voided ones
    included and marked, so a mistake can be found and undone."""
    squad = await _squad_or_404(db, club, team_id)
    pid = _uuid(player_id, "player")
    p = (await db.execute(
        select(Player).where(Player.id == pid, Player.organisation_id == club.id)
    )).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Player not found")
    params = {"org": club.id, "t": squad["id"], "p": pid}
    entries = (await db.execute(
        text(
            "SELECT id, fined_on, reason, amount, voided_at FROM fine_entries "
            "WHERE organisation_id = :org AND team_id = :t AND player_id = :p "
            "ORDER BY fined_on DESC, created_at DESC LIMIT 500"
        ), params)).fetchall()
    payments = (await db.execute(
        text(
            "SELECT id, paid_on, amount, method, note, voided_at FROM fine_payments "
            "WHERE organisation_id = :org AND team_id = :t AND player_id = :p "
            "ORDER BY paid_on DESC, created_at DESC LIMIT 500"
        ), params)).fetchall()
    totals = (await fines_svc.squad_totals(db, club.id, squad["id"])).get(pid, {"fined": 0.0, "paid": 0.0})
    return {
        "player": {"id": str(pid), "name": p.display_name},
        "owing": round(totals["fined"] - totals["paid"], 2),
        "entries": [
            {"id": str(i), "date": d.isoformat(), "reason": r, "amount": fines_svc.money(a), "voided": v is not None}
            for i, d, r, a, v in entries
        ],
        "payments": [
            {"id": str(i), "date": d.isoformat(), "amount": fines_svc.money(a), "method": m, "note": n, "voided": v is not None}
            for i, d, a, m, n, v in payments
        ],
    }
