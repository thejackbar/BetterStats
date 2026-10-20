"""Card review routes: reconcile a match stored twice, the Cricket Australia card and the club's.

Everything is club-scoped through `get_current_club` and needs MANAGE_MANUAL_ENTRIES, the same
capability that gates the manual-entry and import tools: whoever can import a club's history can
decide which version of a match the site shows. A capability held at View level answers the
reads and refuses the writes (the gate checks the verb), so every read here is a GET and every
change is a POST.

The service layer does the work (`services/card_review*.py`); nothing here decides anything.
"""
from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import date as date_cls
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.config.settings import settings
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import card_review as cr
from app.services import card_review_actions as act
from app.services import card_review_hybrid as hy

router = APIRouter(prefix="/club-admin/card-review", tags=["card-review"])

# Comparing 3,000+ matches reads about eight queries' worth of rows. Several screens ask for the
# same comparison in a row, so it is kept for a short time per club and dropped by every change.
_TTL = 30.0
_CACHE: dict = {}


async def _rows(db, club_id) -> list:
    key = str(club_id)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    rows = await cr.review_rows(db, club_id)
    _CACHE[key] = (time.monotonic(), rows)
    return rows


def _drop(club_id) -> None:
    _CACHE.pop(str(club_id), None)


def _line(r: dict) -> dict:
    """A match as one line of a list: the headline, and the full difference list behind its caret."""
    return {
        "match_id": r["match_id"], "game_id": r["game_id"], "season": r["season"], "grade": r["grade"],
        "date": r["date"], "opposition": r["opposition"], "group": r["group"],
        "headline": r["headline"], "item_count": len(r["items"]), "items": r["items"],
        "size": r["size"], "suggested": r["suggested"], "current": r["current"],
        "club_richer": r["club_richer"], "decided_by_hand": r["decided_by_hand"], "decided_at": r["decided_at"], "note": r["note"],
        "source": r["source"], "ca_holds": r["ca_holds"], "club_holds": r["club_holds"],
        "shared": r["shared"], "club_batters": r["club_batters"], "ca_batters": r["ca_batters"],
    }


def _id(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise HTTPException(status_code=422, detail="That is not a valid id.")


def _fail(e: act.ReviewError):
    return HTTPException(status_code=409, detail=str(e))


class ChoiceIn(BaseModel):
    choice: str
    note: Optional[str] = Field(None, max_length=500)


class RelinkIn(BaseModel):
    game_id: str


class AcceptIn(BaseModel):
    match_ids: list[str] = Field(..., max_length=500)


class BulkIn(BaseModel):
    limit: Optional[int] = Field(None, ge=1)


class BulkUndoIn(BaseModel):
    batch_id: str


@router.get("/overview", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_overview(club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    return cr.overview(await _rows(db, club.id))


@router.get("/matches", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_matches(
    group: Optional[str] = Query(None, description="agree, small, differ, pairing or nocard"),
    season: Optional[str] = Query(None),
    decided: Optional[str] = Query(None, description="'yes' only chosen by hand, 'no' only not yet"),
    source_file: Optional[str] = Query(None),
    richer: Optional[str] = Query(None, description="'yes' only where the club card holds more than Cricket Australia's, 'no' only where it does not"),
    recent_seasons: Optional[int] = Query(None, ge=1, description="only the newest N seasons"),
    sort: Optional[str] = Query(None, description="'newest' (the default) or 'worst': the match that most needs a look first"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    if group and group not in cr.GROUPS:
        raise HTTPException(status_code=422, detail="Unknown group.")
    rows = list(await _rows(db, club.id))
    if group:
        rows = [r for r in rows if r["group"] == group]
    if season:
        rows = [r for r in rows if r["season"] == season]
    if decided == "yes":
        rows = [r for r in rows if r["decided_by_hand"]]
    elif decided == "no":
        rows = [r for r in rows if not r["decided_by_hand"]]
    if richer == "yes":
        rows = [r for r in rows if r["club_richer"]]
    elif richer == "no":
        rows = [r for r in rows if not r["club_richer"]]
    if source_file:
        rows = [r for r in rows if (r["source"].get("filename") or r["source"]["label"]) == source_file]
    if recent_seasons:
        newest = sorted({r["season"] for r in await _rows(db, club.id)},
                        key=lambda s: (cr.season_sort_key(s), s or ""))[:recent_seasons]
        rows = [r for r in rows if r["season"] in newest]
    if sort not in (None, "newest", "worst"):
        raise HTTPException(status_code=422, detail="Unknown sort.")
    rows.sort(key=lambda r: (str(r["date"] or ""), r["match_id"]), reverse=True)
    if sort == "worst":
        # a stable sort on top of newest-first: the least shared batters first for a pairing,
        # the biggest difference first for everything else
        rows.sort(key=(lambda r: r["shared"]) if group == "pairing" else (lambda r: -r["size"]))
    sources = sorted({(r["source"].get("filename") or r["source"]["label"]) for r in await _rows(db, club.id)})
    return {"total": len(rows), "offset": offset, "limit": limit, "sources": sources,
            "rows": [_line(r) for r in rows[offset:offset + limit]]}


@router.get("/matches/{match_id}", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_match(match_id: str, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    d = await cr.match_detail(db, club.id, match_id)
    if not d:
        raise HTTPException(status_code=404, detail="That match was not found for this club.")
    return d


@router.get("/matches/{match_id}/preview", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_preview(match_id: str, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    """What the combined choice would bring over and leave out. Reads Cricket Australia's live
    card once, so it is asked for when the reviewer opens that panel, not with every match."""
    match_id = _id(match_id)
    plan = await hy.plan_hybrid(db, club.id, match_id)
    return {"ok": plan["ok"], "reason": plan["reason"], "brought": plan["brought"],
            "left_out": plan["left_out"], "counts": plan.get("counts", {})}


@router.get("/matches/{match_id}/candidates", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_candidates(match_id: str, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    return {"candidates": await cr.pairing_candidates(db, club.id, match_id)}


@router.get("/game/{game_id}", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_for_game(game_id: str, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    """For the admin bar on a match page: the pair this page belongs to, from either of its ids."""
    found = await cr.for_game(db, club.id, _id(game_id))
    return found or {"paired": False}


async def _do(club, call):
    try:
        res = await call
    except act.ReviewError as e:
        raise _fail(e)
    _drop(club.id)
    return res


@router.post("/matches/{match_id}/choice")
async def card_review_choose(match_id: str, data: ChoiceIn,
                             user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                             club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    res = await _do(club, act.set_choice(db, club.id, match_id, data.choice, user.id, note=data.note))
    res.pop("players", None)
    d = await cr.match_detail(db, club.id, match_id)
    return {**res, "match": d}


@router.post("/matches/{match_id}/undo")
async def card_review_undo(match_id: str, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                           club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    res = await _do(club, act.undo_last(db, club.id, match_id, user.id))
    return {**res, "match": await cr.match_detail(db, club.id, match_id)}


@router.post("/matches/{match_id}/refresh")
async def card_review_refresh(match_id: str, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                              club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    res = await _do(club, act.refresh_detail(db, club.id, match_id, user.id))
    return {**res, "match": await cr.match_detail(db, club.id, match_id)}


@router.post("/matches/{match_id}/pair-ok")
async def card_review_pair_ok(match_id: str, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                              club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    return await _do(club, act.mark_pair_ok(db, club.id, match_id, user.id))


@router.post("/matches/{match_id}/relink")
async def card_review_relink(match_id: str, data: RelinkIn,
                             user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                             club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    return await _do(club, act.relink(db, club.id, match_id, _id(data.game_id), user.id))


@router.post("/matches/{match_id}/unlink")
async def card_review_unlink(match_id: str, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                             club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    match_id = _id(match_id)
    return await _do(club, act.unlink(db, club.id, match_id, user.id))


@router.post("/accept")
async def card_review_accept(data: AcceptIn, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                             club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    """Take the suggestion for each selected match, skipping any without one."""
    rows = {r["match_id"]: r for r in await _rows(db, club.id)}
    done, skipped = 0, []
    for mid in (_id(m) for m in data.match_ids):
        r = rows.get(mid)
        if not r or not r["suggested"]:
            skipped.append({"match_id": mid, "reason": "No suggestion for this match."})
            continue
        try:
            await act.set_choice(db, club.id, mid, r["suggested"], user.id, note="Accepted the suggestion")
            done += 1
        except act.ReviewError as e:
            skipped.append({"match_id": mid, "reason": str(e)})
    _drop(club.id)
    return {"switched": done, "skipped": skipped}


@router.get("/bulk/preview", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_bulk_preview(club: Organisation = Depends(get_current_club),
                                   db: AsyncSession = Depends(get_db)):
    return act.bulk_preview(await _rows(db, club.id))


@router.post("/bulk/apply")
async def card_review_bulk_apply(data: BulkIn, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                                 club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    res = await act.bulk_apply(db, club.id, user.id, limit=data.limit)
    _drop(club.id)
    return res


@router.post("/bulk/undo")
async def card_review_bulk_undo(data: BulkUndoIn, user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
                                club: Organisation = Depends(get_current_club),
                                db: AsyncSession = Depends(get_db)):
    try:
        res = await act.bulk_undo(db, club.id, user.id, _id(data.batch_id))
    except act.ReviewError as e:
        raise _fail(e)
    _drop(club.id)
    return res


@router.get("/bulk/batches", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_batches(club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text("""
        SELECT a.target_id AS batch_id, a.created_at, (a.details->>'matches')::int AS matches,
               (SELECT count(*) FROM card_review_log l WHERE l.batch_id = CAST(a.target_id AS UUID)
                   AND l.undone_at IS NULL AND l.action = 'choice') AS still_switched
          FROM audit_logs a
         WHERE a.org_id = CAST(:o AS UUID) AND a.action = 'card_review_bulk'
         ORDER BY a.created_at DESC LIMIT 20"""), {"o": str(club.id)})).mappings().all()
    return {"batches": [dict(r) for r in rows]}


@router.get("/export.csv", dependencies=[Depends(require_cap(MANAGE_MANUAL_ENTRIES))])
async def card_review_export(club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    """Every match with a discrepancy, as a spreadsheet for the reviewer to work through."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cr.EXPORT_HEADERS)
    w.writerows(cr.export_rows(await _rows(db, club.id), settings.public_base_url))
    name = f"card-review-{club.slug}-{date_cls.today().isoformat()}.csv"
    return StreamingResponse(
        iter(["﻿" + out.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
