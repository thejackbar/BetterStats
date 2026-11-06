"""Junior Rotation: the parent link.

A page parents open from a link the coach shares, showing who bats where and
who fields where for the group's recent games. No sign-in, no PIN: the token
is the only secret, so the page is built to say little.

  * **Off by default.** ``rotation_groups.public_enabled`` starts false, and a
    group with it off, a club without BetterSelect, or an unknown token is the
    same plain 404, so a probe learns nothing.
  * **Locked rounds only.** A draft is the coach's working state and never
    leaves the admin screens.
  * **First names.** Children's names, so the default is a first name and last
    initial (``public_show_surnames`` turns surnames on). Two kids who would
    read the same fall back to their full typed names so nobody is mistaken
    for another.
  * **No ids**, no notes, no avoid lists, nothing about other groups.
  * Read only and rate limited per address.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import MODULE_SELECT, org_has_module
from app.models.db import Organisation, get_db
from app.services.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/public/rotation", tags=["public-rotation"])

_limiter = SlidingWindowLimiter()
LIMIT = 60
WINDOW = 60
RECENT_ROUNDS = 8


def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def public_names(names: dict[str, str], show_surnames: bool) -> dict[str, str]:
    """player id -> the name a parent sees. First name and last initial unless
    surnames are on; any two that would still read the same keep their full
    typed names."""
    if show_surnames:
        return dict(names)
    short: dict[str, str] = {}
    for pid, full in names.items():
        parts = full.split()
        short[pid] = full if len(parts) < 2 else f"{parts[0]} {parts[-1][0].upper()}."
    counts: dict[str, int] = {}
    for v in short.values():
        counts[v.casefold()] = counts.get(v.casefold(), 0) + 1
    return {pid: (names[pid] if counts[short[pid].casefold()] > 1 else short[pid]) for pid in names}


@router.get("/{token}")
async def landing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    ok, _ = _limiter.check(f"rotation:{_client_ip(request)}", LIMIT, WINDOW)
    if not ok:
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.")
    grp = (await db.execute(
        text("SELECT * FROM rotation_groups WHERE public_token = :t"), {"t": token or ""},
    )).mappings().first() if token else None
    club = await db.get(Organisation, grp["organisation_id"]) if grp else None
    if (
        grp is None or club is None or not grp["public_enabled"]
        or grp["archived_at"] is not None or not org_has_module(club, MODULE_SELECT)
    ):
        raise HTTPException(status_code=404, detail="This link isn't active")
    players = (await db.execute(
        text("SELECT id, name FROM rotation_players WHERE group_id = :g"), {"g": grp["id"]},
    )).mappings().all()
    shown = public_names({str(p["id"]): p["name"] for p in players}, grp["public_show_surnames"])
    positions = [p for p in (grp["positions"] or []) if isinstance(p, dict) and p.get("id")]
    rounds = (await db.execute(text("""
        SELECT round_date, label, batting_order, fielding FROM rotation_rounds
        WHERE group_id = :g AND status = 'locked'
        ORDER BY round_date DESC, created_at DESC LIMIT :n
    """), {"g": grp["id"], "n": RECENT_ROUNDS})).mappings().all()
    out = []
    for r in rounds:
        changes = []
        for change in r["fielding"] or []:
            slots = []
            for pos in positions:
                who = next((pid for pid, v in (change or {}).items() if v == pos["id"]), None)
                slots.append({"position": pos["name"], "key": bool(pos.get("key")), "name": shown.get(who) if who else None})
            resting = [shown[pid] for pid, v in (change or {}).items() if v is None and pid in shown]
            changes.append({"slots": slots, "resting": resting})
        out.append({
            "date": r["round_date"].isoformat(),
            "label": r["label"],
            "batting": [shown[p] for p in (r["batting_order"] or []) if p in shown],
            "changes": changes,
        })
    return {"group": {"name": grp["name"], "bats": grp["bats"]}, "club": club.name, "rounds": out}
