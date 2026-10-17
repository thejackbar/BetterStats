"""BetterSelect Fines: the money maths and the player's own view.

After a game a side sits down, hands out fines and collects them into a pot.
This is only the tracker: a fine is a row in ``fine_entries``, money in is a row
in ``fine_payments``, and what a player owes is DERIVED on every read
(fined minus paid). Nothing is stored as a balance and nothing is deleted: a
wrong row is voided (``voided_at``), so the trail stays and an undo is possible.

Both the admin router (``routers/fines.py``) and the player's page
(``routers/public_availability.py``) read through here, so the two cannot
disagree about what somebody owes.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# How to pay: the fields a squad can fill in on the Fines setup screen.
PAY_FIELDS = (
    "payid", "payid_name", "account_name", "bsb", "account_number",
    "reference_hint", "other_instructions",
)

MAX_AMOUNT = Decimal("100000")


def money(value) -> float:
    """A NUMERIC from the database as a 2 dp float for JSON."""
    return round(float(value or 0), 2)


def parse_amount(value, *, allow_zero: bool = False) -> Decimal:
    """A typed amount as a 2 dp Decimal, or ValueError. Refuses negatives, junk
    and silly sizes, so a mistyped extra zero is caught here and not in the pot."""
    try:
        amt = Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        raise ValueError("Enter an amount like 5 or 12.50")
    if amt < 0 or (amt == 0 and not allow_zero):
        raise ValueError("The amount must be more than zero")
    if amt > MAX_AMOUNT:
        raise ValueError("That amount is too large")
    return amt


def pay_details(row: dict) -> dict:
    """The how-to-pay fields of a settings row, with the empty ones left out."""
    return {k: row[k].strip() for k in PAY_FIELDS if row.get(k) and str(row[k]).strip()}


async def squad_totals(db: AsyncSession, org_id, team_id) -> dict:
    """{player_id: {"fined": float, "paid": float}} for one squad, voided rows
    left out. One query for both ledgers."""
    rows = (await db.execute(
        text(
            "SELECT player_id, COALESCE(SUM(f), 0), COALESCE(SUM(p), 0) FROM ("
            " SELECT player_id, amount AS f, 0::numeric AS p FROM fine_entries"
            "  WHERE organisation_id = :org AND team_id = :t AND voided_at IS NULL"
            " UNION ALL"
            " SELECT player_id, 0::numeric, amount FROM fine_payments"
            "  WHERE organisation_id = :org AND team_id = :t AND voided_at IS NULL"
            ") x GROUP BY player_id"
        ),
        {"org": org_id, "t": team_id},
    )).fetchall()
    return {pid: {"fined": money(f), "paid": money(p)} for pid, f, p in rows}


async def player_fines(db: AsyncSession, org_id, player_id, weeks: int = 8) -> list[dict]:
    """What this player's page shows for Fines: one block per squad that has Fines
    switched on and that they are in (or have been fined in). Their own rows and
    the squad's pot total only, nobody else's name or amount."""
    squads = (await db.execute(
        text(
            "SELECT t.id, COALESCE(NULLIF(t.short_name, ''), t.name) AS name, "
            "fs.payid, fs.payid_name, fs.account_name, fs.bsb, fs.account_number, "
            "fs.reference_hint, fs.other_instructions "
            "FROM fine_settings fs JOIN teams t ON t.id = fs.team_id "
            "WHERE fs.organisation_id = :org AND fs.enabled AND COALESCE(t.is_active, true) "
            "AND (EXISTS (SELECT 1 FROM team_members tm WHERE tm.team_id = t.id AND tm.player_id = :p) "
            "     OR EXISTS (SELECT 1 FROM fine_entries fe WHERE fe.team_id = t.id AND fe.player_id = :p "
            "                AND fe.voided_at IS NULL)) "
            "ORDER BY t.sequence NULLS LAST, t.name"
        ),
        {"org": org_id, "p": player_id},
    )).mappings().all()

    out = []
    for sq in squads:
        tid = sq["id"]
        mine = (await squad_totals(db, org_id, tid)).get(player_id, {"fined": 0.0, "paid": 0.0})
        entries = (await db.execute(
            text(
                "SELECT fined_on, reason, amount, note FROM fine_entries "
                "WHERE organisation_id = :org AND team_id = :t AND player_id = :p AND voided_at IS NULL "
                "ORDER BY fined_on DESC, created_at DESC LIMIT 200"
            ),
            {"org": org_id, "t": tid, "p": player_id},
        )).fetchall()
        by_date: dict[date, list] = {}
        for d, reason, amount, note in entries:
            by_date.setdefault(d, []).append({"reason": reason, "amount": money(amount), "note": note})
        recent_weeks = [
            {"date": d.isoformat(), "total": round(sum(i["amount"] for i in items), 2), "items": items}
            for d, items in list(by_date.items())[:weeks]
        ]
        payments = (await db.execute(
            text(
                "SELECT paid_on, amount, method FROM fine_payments "
                "WHERE organisation_id = :org AND team_id = :t AND player_id = :p AND voided_at IS NULL "
                "ORDER BY paid_on DESC, created_at DESC LIMIT 5"
            ),
            {"org": org_id, "t": tid, "p": player_id},
        )).fetchall()
        pot = (await db.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) FROM fine_payments "
                "WHERE organisation_id = :org AND team_id = :t AND voided_at IS NULL"
            ),
            {"org": org_id, "t": tid},
        )).scalar()
        out.append({
            "squad": sq["name"],
            "fined": mine["fined"],
            "paid": mine["paid"],
            # Positive = owes; negative = has tipped in more than they were fined.
            "owing": round(mine["fined"] - mine["paid"], 2),
            "weeks": recent_weeks,
            "payments": [
                {"date": d.isoformat(), "amount": money(a), "method": m} for d, a, m in payments
            ],
            "pot": money(pot),
            "how_to_pay": pay_details(dict(sq)),
        })
    return out
