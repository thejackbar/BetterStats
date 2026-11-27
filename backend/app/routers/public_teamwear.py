"""Teamwear ordering, the member's side: the Kit page of the Player Dashboard (``/playerdash/:token/kit``).

Same trust model as the rest of the link (routers/public_availability): the token names the club,
the PIN cookie names the person, and everything here is that person's own orders. The page is
served only while the club may show the ``teamwear`` module (BetterMerch, the dashboard side on,
and the PIN on, as for fees: orders carry family names and money). Anything else is a 404.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, Player, get_db
from app.routers.public_availability import _club_for_token, _player_for_session
from app.services import player_dashboard
from app.services import teamwear as tw
from app.services import teamwear_notify

router = APIRouter(prefix="/public/availability", tags=["public-teamwear"])
images_router = APIRouter(prefix="/public/teamwear", tags=["public-teamwear"])


@contextmanager
def refusal():
    try:
        yield
    except tw.TeamwearError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


async def _member(db: AsyncSession, token: str, request: Request) -> tuple[Organisation, Player]:
    club = await _club_for_token(db, token, need_select=False, need_dashboard=True)
    if player_dashboard.blocked_reason(club, "teamwear") is not None:
        raise HTTPException(status_code=404, detail="The club's teamwear shop isn't open on this page.")
    player = await _player_for_session(db, request, club)
    return club, player


async def _wearers(db: AsyncSession, club: Organisation, player: Player) -> dict:
    return {f["player_id"]: f["name"] for f in await tw.family_of(db, club.id, player.id)}


@router.get("/{token}/kit")
async def get_kit(token: str, request: Request, paid: Optional[str] = None, order: Optional[str] = None,
                  db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    if paid == "square" and order:
        # Back from a Square payment page: read the link back now rather than waiting for the job.
        try:
            await teamwear_notify.check_square(db, club, uuid.UUID(order))
        except Exception:
            await db.rollback()
    out = await tw.shop_for_member(db, club, player)
    out["card"] = await teamwear_notify.card_options(db, club)
    out["card"].pop("square_needs_reconnect", None)
    return out


class OrderIn(BaseModel):
    campaign_id: Optional[str] = None
    lines: list[dict] = []
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{token}/kit/orders")
async def place(token: str, body: OrderIn, request: Request, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    with refusal():
        oid = await tw.place_order(db, club, campaign_id=body.campaign_id, lines=body.lines,
                                   data=body.model_dump(exclude={"lines", "campaign_id"}),
                                   placed_by=player, allowed_wearers=await _wearers(db, club, player))
    await db.commit()
    await teamwear_notify.send_order_received(db, club, oid)
    return {"order": await tw.get_order(db, club.id, oid)}


@router.put("/{token}/kit/orders/{order_id}")
async def edit(token: str, order_id: str, body: OrderIn, request: Request, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    with refusal():
        await tw.replace_member_lines(db, club, order_id, lines=body.lines,
                                      data=body.model_dump(exclude={"lines", "campaign_id"}, exclude_unset=True),
                                      player=player, allowed_wearers=await _wearers(db, club, player))
    await db.commit()
    return {"order": await tw.get_order(db, club.id, order_id)}


@router.post("/{token}/kit/orders/{order_id}/cancel")
async def cancel(token: str, order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    with refusal():
        await tw.member_cancel(db, club, order_id, player)
    await db.commit()
    return {"ok": True}


class ChangeIn(BaseModel):
    message: str


@router.post("/{token}/kit/orders/{order_id}/change")
async def change(token: str, order_id: str, body: ChangeIn, request: Request, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    with refusal():
        await tw.request_change(db, club, order_id, player, body.message)
    await db.commit()
    return {"ok": True}


@router.post("/{token}/kit/orders/{order_id}/pay/{provider}")
async def pay(token: str, order_id: str, provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    if provider not in ("stripe", "square"):
        raise HTTPException(status_code=404, detail="Unknown payment method")
    with refusal():
        try:
            if provider == "stripe":
                url = await teamwear_notify.start_stripe(db, club, order_id, player)
            else:
                url = await teamwear_notify.start_square(db, club, order_id, player)
        except tw.TeamwearError:
            raise
        except Exception:
            import logging
            logging.getLogger(__name__).exception("teamwear %s checkout failed", provider)
            await db.rollback()
            raise tw.TeamwearError("The card payment page could not be opened. Try again, or pay by bank transfer.", 502)
    return {"url": url}


@router.get("/{token}/kit/number-check")
async def check_number(token: str, request: Request, number: str = "", wearer_player_id: Optional[str] = None,
                       campaign_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    club, player = await _member(db, token, request)
    wearers = await _wearers(db, club, player)
    wid = wearer_player_id if wearer_player_id in wearers else None
    with refusal():
        cid = tw._uuid(campaign_id, "campaign id") if campaign_id else None
        return await tw.number_check(db, club.id, number, wid, cid)


@images_router.get("/images/{image_id}")
async def image(image_id: str, db: AsyncSession = Depends(get_db)):
    """A product picture. Public: the launch email and the shop show them. Re-encoded on upload."""
    try:
        iid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    r = (await db.execute(text("SELECT mime, data FROM teamwear_images WHERE id = CAST(:i AS UUID)"),
                          {"i": str(iid)})).mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=bytes(r["data"]), media_type=r["mime"],
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})
