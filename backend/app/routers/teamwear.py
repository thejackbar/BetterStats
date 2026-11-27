"""Teamwear ordering, the coordinator's side (BetterAdmin > Stock > Teamwear).

Every route needs ``MANAGE_MERCH`` (reads are GETs, so a View holder can read), and the router is
module-gated by ``require_module("merch")`` where main.py includes it. The rules live in
services/teamwear.py; emails and card checkout in services/teamwear_notify.py; the supplier form
in services/teamwear_export.py.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MERCH, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user
from app.services import teamwear as tw
from app.services import teamwear_export, teamwear_notify

router = APIRouter(prefix="/club-admin/teamwear", tags=["club-admin-teamwear"])
_require = Depends(require_cap(MANAGE_MERCH))


@contextmanager
def refusal():
    try:
        yield
    except tw.TeamwearError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


class Body(BaseModel):
    """A loose body: the service reads only the keys that were sent (key presence is intent)."""
    model_config = {"extra": "allow"}

    def sent(self) -> dict:
        return {k: v for k, v in (self.model_extra or {}).items()}


# ── settings ────────────────────────────────────────────────────────────────

@router.get("/settings", dependencies=[_require])
async def get_settings(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    s = await tw.get_settings(db, club.id)
    return {"settings": tw.settings_out(s), "card": await teamwear_notify.card_options(db, club),
            "dashboard_link": teamwear_notify.kit_link(club)}


@router.patch("/settings", dependencies=[_require])
async def patch_settings(body: Body, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        s = await tw.save_settings(db, club.id, body.sent())
    await db.commit()
    return {"settings": tw.settings_out(s)}


# ── the shop range ──────────────────────────────────────────────────────────

@router.get("/range", dependencies=[_require])
async def get_range(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    products = await tw.list_range(db, club.id)
    in_range = {p["product_id"] for p in products}
    others = (await db.execute(text(
        "SELECT id, name, category FROM merch_products WHERE organisation_id = CAST(:o AS UUID) AND is_active "
        "AND source = 'manual' ORDER BY name"), {"o": str(club.id)})).mappings().all()
    s = await tw.get_settings(db, club.id)
    return {
        "products": products,
        "available_products": [{"id": str(r["id"]), "name": r["name"], "category": r["category"]}
                               for r in others if str(r["id"]) not in in_range],
        "settings": tw.settings_out(s),
    }


@router.post("/range", dependencies=[_require])
async def create_range_product(body: Body, user: User = Depends(get_current_user),
                               club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        pid = await tw.save_range_product(db, club.id, body.sent(), user_id=user.id)
    await db.commit()
    return {"product": (await tw.list_range(db, club.id, product_ids=[pid]))[0]}


@router.patch("/range/{product_id}", dependencies=[_require])
async def update_range_product(product_id: str, body: Body, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    with refusal():
        pid = await tw.save_range_product(db, club.id, body.sent(), product_id=product_id)
    await db.commit()
    return {"product": (await tw.list_range(db, club.id, product_ids=[pid]))[0]}


@router.post("/range/{product_id}/link", dependencies=[_require])
async def link_existing(product_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        pid = await tw.add_existing_product(db, club.id, product_id)
    await db.commit()
    return {"product": (await tw.list_range(db, club.id, product_ids=[pid]))[0]}


@router.delete("/range/{product_id}", dependencies=[_require])
async def unlink(product_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.remove_from_range(db, club.id, product_id)
    await db.commit()
    return {"ok": True}


@router.post("/range/{product_id}/images", dependencies=[_require])
async def upload_image(product_id: str, file: UploadFile = File(...), club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    from app.services.player_card_designs import DesignError, process_image
    with refusal():
        pid = tw._uuid(product_id, "product id")
    owned = (await db.execute(text(
        "SELECT 1 FROM teamwear_products WHERE product_id = CAST(:p AS UUID) AND organisation_id = CAST(:o AS UUID)"),
        {"p": str(pid), "o": str(club.id)})).first()
    if not owned:
        raise HTTPException(status_code=404, detail="Product not found")
    count = (await db.execute(text("SELECT COUNT(*) FROM teamwear_images WHERE product_id = CAST(:p AS UUID)"),
                              {"p": str(pid)})).scalar() or 0
    if count >= 6:
        raise HTTPException(status_code=422, detail="A product can have six pictures.")
    try:
        data, mime = process_image(await file.read(), "bg")
    except DesignError as e:
        raise HTTPException(status_code=getattr(e, "status", 422) or 422, detail=str(e))
    await db.execute(text(
        "INSERT INTO teamwear_images (organisation_id, product_id, mime, data, sort_order) "
        "VALUES (CAST(:o AS UUID), CAST(:p AS UUID), :m, :d, :so)"),
        {"o": str(club.id), "p": str(pid), "m": mime, "d": data, "so": count})
    await db.commit()
    return {"product": (await tw.list_range(db, club.id, product_ids=[pid]))[0]}


@router.delete("/images/{image_id}", dependencies=[_require])
async def delete_image(image_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        iid = tw._uuid(image_id, "image id")
    r = await db.execute(text(
        "DELETE FROM teamwear_images WHERE id = CAST(:i AS UUID) AND organisation_id = CAST(:o AS UUID)"),
        {"i": str(iid), "o": str(club.id)})
    if not r.rowcount:
        raise HTTPException(status_code=404, detail="Picture not found")
    await db.commit()
    return {"ok": True}


# ── campaigns ───────────────────────────────────────────────────────────────

async def _campaign_payload(db: AsyncSession, club: Organisation, campaign_id) -> dict:
    c = await tw.get_campaign(db, club.id, campaign_id)
    s = await tw.get_settings(db, club.id)
    items = await tw.campaign_items(db, c["id"])
    rng = {p["product_id"]: p for p in await tw.list_range(db, club.id, product_ids=[i["product_id"] for i in items])}
    return {
        "campaign": tw.campaign_out(c, settings=s),
        "items": [{"product_id": str(i["product_id"]), "name": i["name"], "supplier_code": i["supplier_code"],
                   "price": tw.f2(i["price"]), "personalisation": i["personalisation"], "decision": i["decision"],
                   "sizes": [{"variant_id": z["variant_id"], "label": z["label"]} for z in rng.get(str(i["product_id"]), {}).get("sizes", [])],
                   "images": rng.get(str(i["product_id"]), {}).get("images", []),
                   "range_price": rng.get(str(i["product_id"]), {}).get("price")} for i in items],
        "orders": await tw.load_orders(db, club.id, campaign_id=c["id"]),
        "changes": await tw.list_changes(db, club.id, campaign_id=c["id"]),
    }


@router.get("/campaigns", dependencies=[_require])
async def list_campaigns(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"campaigns": await tw.list_campaigns(db, club.id)}


@router.post("/campaigns", dependencies=[_require])
async def create_campaign(body: Body, user: User = Depends(get_current_user),
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        cid = await tw.create_campaign(db, club.id, body.sent(), user_id=user.id)
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, cid)


@router.get("/campaigns/{campaign_id}", dependencies=[_require])
async def get_campaign(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


@router.patch("/campaigns/{campaign_id}", dependencies=[_require])
async def patch_campaign(campaign_id: str, body: Body, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.update_campaign(db, club.id, campaign_id, body.sent())
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


class PriceBody(BaseModel):
    price: Any


@router.put("/campaigns/{campaign_id}/items/{product_id}/price", dependencies=[_require])
async def set_item_price(campaign_id: str, product_id: str, body: PriceBody,
                         club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.set_item_price(db, club.id, campaign_id, product_id, body.price)
    await db.commit()
    return {"ok": True}


@router.get("/campaigns/{campaign_id}/launch-preview", dependencies=[_require])
async def launch_preview(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        subject, h, _t = await teamwear_notify.launch_body(db, club, campaign_id)
    from app.services.email_service import email_is_live
    return {"subject": subject, "html": teamwear_notify._wrap(club, subject, h),
            "recipients": len(await teamwear_notify.launch_recipients(db, club)), "email_live": email_is_live(),
            "dashboard_link": teamwear_notify.kit_link(club)}


class LaunchBody(BaseModel):
    send_email: bool = False


@router.post("/campaigns/{campaign_id}/launch", dependencies=[_require])
async def launch(campaign_id: str, body: LaunchBody, club: Organisation = Depends(get_current_club),
                 db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.launch_campaign(db, club.id, campaign_id)
    await db.commit()
    emails = await teamwear_notify.send_launch(db, club, campaign_id) if body.send_email else None
    with refusal():
        out = await _campaign_payload(db, club, campaign_id)
    out["emails"] = emails
    return out


class TestBody(BaseModel):
    to: Optional[str] = None


@router.post("/campaigns/{campaign_id}/launch-email", dependencies=[_require])
async def launch_email(campaign_id: str, body: TestBody, user: User = Depends(get_current_user),
                       club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Send the launch email: a test to one address, or to the club's players (each once)."""
    with refusal():
        c = await tw.get_campaign(db, club.id, campaign_id)
    if body.to is None and c["stage"] != "open":
        raise HTTPException(status_code=409, detail="Launch the campaign before emailing members.")
    test_to = (body.to or "").strip() or None
    if body.to is not None and not test_to:
        test_to = user.email
    return {"emails": await teamwear_notify.send_launch(db, club, c["id"], test_to=test_to)}


@router.post("/campaigns/{campaign_id}/close", dependencies=[_require])
async def close(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.close_ordering(db, club.id, campaign_id)
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


class ReopenBody(BaseModel):
    closes_at: str


@router.post("/campaigns/{campaign_id}/reopen", dependencies=[_require])
async def reopen(campaign_id: str, body: ReopenBody, club: Organisation = Depends(get_current_club),
                 db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.reopen_ordering(db, club.id, campaign_id, body.closes_at)
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


@router.post("/campaigns/{campaign_id}/cancel", dependencies=[_require])
async def cancel(campaign_id: str, user: User = Depends(get_current_user), club: Organisation = Depends(get_current_club),
                 db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.cancel_campaign(db, club.id, campaign_id, user.id)
    await db.commit()
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/complete", dependencies=[_require])
async def complete(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.complete_campaign(db, club.id, campaign_id)
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


@router.get("/campaigns/{campaign_id}/emails", dependencies=[_require])
async def emails(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        c = await tw.get_campaign(db, club.id, campaign_id)
    return {"emails": await teamwear_notify.email_log(db, club.id, c["id"])}


# ── orders ──────────────────────────────────────────────────────────────────

class OrderIn(BaseModel):
    lines: list[dict] = []
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    send_email: bool = False


@router.post("/campaigns/{campaign_id}/orders", dependencies=[_require])
async def coordinator_order(campaign_id: str, body: OrderIn, user: User = Depends(get_current_user),
                            club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        oid = await tw.place_order(db, club, campaign_id=campaign_id, lines=body.lines,
                                   data=body.model_dump(exclude={"lines", "send_email"}), user_id=user.id)
    await db.commit()
    if body.send_email:
        await teamwear_notify.send_order_received(db, club, oid)
    return {"order": await tw.get_order(db, club.id, oid)}


@router.get("/stock-orders", dependencies=[_require])
async def stock_orders(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"orders": list(reversed(await tw.load_orders(db, club.id, stock_only=True)))}


@router.post("/stock-orders", dependencies=[_require])
async def coordinator_stock_order(body: OrderIn, user: User = Depends(get_current_user),
                                  club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        oid = await tw.place_order(db, club, campaign_id=None, lines=body.lines,
                                   data=body.model_dump(exclude={"lines", "send_email"}), user_id=user.id)
    await db.commit()
    if body.send_email:
        await teamwear_notify.send_payment_request(db, club, oid)
    return {"order": await tw.get_order(db, club.id, oid)}


@router.get("/orders/{order_id}", dependencies=[_require])
async def get_order(order_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        o = await tw.get_order(db, club.id, order_id)
    o["payments"] = await tw.list_payments(db, club.id, order_id=o["id"])
    o["changes"] = await tw.list_changes(db, club.id, order_ids=[o["id"]])
    return {"order": o}


@router.patch("/orders/{order_id}", dependencies=[_require])
async def patch_order(order_id: str, body: Body, user: User = Depends(get_current_user),
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.update_order(db, club, order_id, body.sent(), user_id=user.id)
    await db.commit()
    return {"order": await tw.get_order(db, club.id, order_id)}


class LinesIn(BaseModel):
    lines: list[dict]


@router.post("/orders/{order_id}/lines", dependencies=[_require])
async def add_lines(order_id: str, body: LinesIn, club: Organisation = Depends(get_current_club),
                    db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.coordinator_add_lines(db, club, order_id, body.lines)
    await db.commit()
    return {"order": await tw.get_order(db, club.id, order_id)}


@router.patch("/lines/{line_id}", dependencies=[_require])
async def patch_line(line_id: str, body: Body, user: User = Depends(get_current_user),
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        line = await tw.update_line(db, club, line_id, body.sent(), user_id=user.id)
    await db.commit()
    return {"line": line}


@router.post("/orders/{order_id}/remind", dependencies=[_require])
async def remind(order_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        o = await tw.get_order(db, club.id, order_id)
    if not o["payment_requested_at"] or o["balance"] <= 0:
        raise HTTPException(status_code=409, detail="This order has nothing owing.")
    from datetime import date
    off = (tw.today_local() - date.fromisoformat(o["due_on"])).days if o["due_on"] else 0
    r = await teamwear_notify.send_reminder(db, club, o, off, manual=True)
    if r != "sent":
        raise HTTPException(status_code=502, detail="The reminder did not send. Check the club's email settings.")
    return {"ok": True}


@router.post("/orders/{order_id}/payment-request", dependencies=[_require])
async def resend_payment_request(order_id: str, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    """Send (again) the payment request for one order, e.g. after a change."""
    with refusal():
        o = await tw.get_order(db, club.id, order_id)
    if not o["payment_requested_at"]:
        raise HTTPException(status_code=409, detail="This order has not been asked to pay yet.")
    # Sent without the dedupe key the first request carried, so it goes again.
    from app.services.teamwear_notify import _lines_table, _pay_block, send
    s = await tw.get_settings(db, club.id)
    table_h, table_t = _lines_table(o)
    pay_h, pay_t = _pay_block(s, o, teamwear_notify.kit_link(club))
    r = await send(db, club, kind="payment_request", to_email=o["contact_email"], to_name=o["contact_name"],
                   subject=f"Teamwear payment request ({o['reference']})", body_html=table_h + pay_h,
                   body_text=f"{table_t}\n\n{pay_t}", campaign_id=o["campaign_id"], order_id=o["id"])
    if r != "sent":
        raise HTTPException(status_code=502, detail="The email did not send. Check the club's email settings.")
    return {"ok": True}


@router.get("/players", dependencies=[_require])
async def find_players(q: str = "", club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Wearer picker for an order the coordinator enters."""
    term = (q or "").strip()
    if len(term) < 2:
        return {"players": []}
    rows = (await db.execute(text(
        "SELECT id, COALESCE(display_name_override, name) AS name, shirt_number, email, phone FROM players "
        "WHERE organisation_id = CAST(:o AS UUID) AND COALESCE(display_name_override, name) ILIKE :t "
        "ORDER BY name LIMIT 15"), {"o": str(club.id), "t": f"%{term}%"})).mappings().all()
    return {"players": [{**dict(r), "id": str(r["id"])} for r in rows]}


# ── change requests ─────────────────────────────────────────────────────────

class ChangeAnswer(BaseModel):
    status: str
    response: Optional[str] = None
    send_email: bool = True


@router.post("/changes/{request_id}", dependencies=[_require])
async def answer_change(request_id: str, body: ChangeAnswer, user: User = Depends(get_current_user),
                        club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        out = await tw.resolve_change(db, club.id, request_id, body.status, body.response, user.id)
    await db.commit()
    emailed = await teamwear_notify.send_change_answer(db, club, request_id) if body.send_email else None
    return {**out, "emailed": emailed}


# ── triage and approval ─────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/triage", dependencies=[_require])
async def get_triage(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        return await tw.triage(db, club.id, campaign_id)


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None


@router.put("/campaigns/{campaign_id}/triage/{product_id}", dependencies=[_require])
async def put_decision(campaign_id: str, product_id: str, body: DecisionIn,
                       club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        cleared = await tw.set_decision(db, club.id, campaign_id, product_id, body.decision, body.note)
    await db.commit()
    with refusal():
        return {**await tw.triage(db, club.id, campaign_id), "approval_cleared": cleared}


class TopupsIn(BaseModel):
    by_variant: dict[str, int]


@router.put("/campaigns/{campaign_id}/triage/{product_id}/topups", dependencies=[_require])
async def put_topups(campaign_id: str, product_id: str, body: TopupsIn,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        cleared = await tw.set_topups(db, club.id, campaign_id, product_id, body.by_variant)
    await db.commit()
    with refusal():
        return {**await tw.triage(db, club.id, campaign_id), "approval_cleared": cleared}


@router.post("/campaigns/{campaign_id}/triage/{product_id}/suggest", dependencies=[_require])
async def suggest(campaign_id: str, product_id: str, club: Organisation = Depends(get_current_club),
                  db: AsyncSession = Depends(get_db)):
    with refusal():
        cleared = await tw.apply_suggested_topups(db, club.id, campaign_id, product_id)
    await db.commit()
    with refusal():
        return {**await tw.triage(db, club.id, campaign_id), "approval_cleared": cleared}


class ApprovalIn(BaseModel):
    approved_on: Optional[str] = None
    note: Optional[str] = None


@router.post("/campaigns/{campaign_id}/approval", dependencies=[_require])
async def approve(campaign_id: str, body: ApprovalIn, user: User = Depends(get_current_user),
                  club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        out = await tw.record_approval(db, club.id, campaign_id, body.approved_on, body.note, user.id)
    await db.commit()
    with refusal():
        return {**await tw.triage(db, club.id, campaign_id), "warnings": out}


@router.delete("/campaigns/{campaign_id}/approval", dependencies=[_require])
async def unapprove(campaign_id: str, user: User = Depends(get_current_user),
                    club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.revoke_approval(db, club.id, campaign_id, user.id)
    await db.commit()
    with refusal():
        return await tw.triage(db, club.id, campaign_id)


@router.post("/campaigns/{campaign_id}/payment-requests", dependencies=[_require])
async def payment_requests(campaign_id: str, user: User = Depends(get_current_user),
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        out = await tw.confirm_and_request_payment(db, club.id, campaign_id, user.id)
    await db.commit()
    emails = await teamwear_notify.send_payment_requests(db, club, out["asked"], out["emptied"])
    return {**out, "emails": emails}


# ── payments ────────────────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/payments", dependencies=[_require])
async def campaign_payments(campaign_id: str, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    with refusal():
        c = await tw.get_campaign(db, club.id, campaign_id)
    return {"payments": await tw.list_payments(db, club.id, campaign_id=c["id"])}


class PaymentIn(BaseModel):
    amount: Any
    method: str = "bank"
    paid_on: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None


@router.post("/orders/{order_id}/payments", dependencies=[_require])
async def add_payment(order_id: str, body: PaymentIn, user: User = Depends(get_current_user),
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.record_payment(db, club.id, order_id, amount=body.amount, method=body.method, paid_on=body.paid_on,
                                reference=body.reference, note=body.note, user_id=user.id)
    await db.commit()
    return {"order": await tw.get_order(db, club.id, order_id)}


class VoidIn(BaseModel):
    reason: Optional[str] = None


@router.post("/payments/{payment_id}/void", dependencies=[_require])
async def void(payment_id: str, body: VoidIn, user: User = Depends(get_current_user),
               club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.void_payment(db, club.id, payment_id, body.reason, user.id)
    await db.commit()
    return {"ok": True}


@router.post("/payments/bank/preview", dependencies=[_require])
async def bank_preview(file: UploadFile = File(...), campaign_id: Optional[str] = Form(None),
                       club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    raw = (await file.read()).decode("utf-8-sig", errors="ignore")
    with refusal():
        cid = tw._uuid(campaign_id, "campaign id") if campaign_id else None
        return await tw.bank_preview(db, club.id, raw, cid)


class BankCommit(BaseModel):
    rows: list[dict]


@router.post("/payments/bank/commit", dependencies=[_require])
async def bank_commit(body: BankCommit, user: User = Depends(get_current_user),
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        out = await tw.bank_commit(db, club.id, body.rows, user.id)
    await db.commit()
    return out


# ── export, receive and pack ────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/export", dependencies=[_require])
async def export_status(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        blockers = await tw.export_blockers(db, club.id, campaign_id)
        rows = await teamwear_export.build_rows(db, club.id, campaign_id)
    rows.pop("campaign", None)
    return {**blockers, "form": rows}


@router.post("/campaigns/{campaign_id}/export", dependencies=[_require])
async def export_lock(campaign_id: str, user: User = Depends(get_current_user),
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        await tw.mark_exported(db, club.id, campaign_id, user.id)
    await db.commit()
    with refusal():
        return await _campaign_payload(db, club, campaign_id)


@router.get("/campaigns/{campaign_id}/export.xlsx", dependencies=[_require])
async def export_file(campaign_id: str, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        c = await tw.get_campaign(db, club.id, campaign_id)
        if c["stage"] not in ("exported", "received", "closed"):
            raise tw.TeamwearError("Lock the order first: the form is built once every order is paid or decided.", 409)
        data, fname = await teamwear_export.build_xlsx(db, club, c["id"])
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/campaigns/{campaign_id}/received", dependencies=[_require])
async def received(campaign_id: str, user: User = Depends(get_current_user),
                   club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    with refusal():
        n = await tw.mark_received(db, club, campaign_id, user.id)
    await db.commit()
    with refusal():
        return {**await _campaign_payload(db, club, campaign_id), "to_stock": n}


class ArrivalIn(BaseModel):
    order_ids: Optional[list[str]] = None


@router.post("/campaigns/{campaign_id}/arrival-email", dependencies=[_require])
async def arrival(campaign_id: str, body: ArrivalIn, club: Organisation = Depends(get_current_club),
                  db: AsyncSession = Depends(get_db)):
    with refusal():
        c = await tw.get_campaign(db, club.id, campaign_id)
    if c["stage"] not in ("received", "closed"):
        raise HTTPException(status_code=409, detail="Mark the kit received first.")
    return {"emails": await teamwear_notify.send_arrival(db, club, c["id"], body.order_ids)}
