"""Teamwear email and card checkout: launch, order received, payment request, reminders,
not available this round, change answered, arrival; Stripe Checkout and Square payment links.

Every email goes through ``selection_notify._deliver`` (the club's sender, suppression honoured,
and "no live provider" is a failure, never a send) and is logged in ``teamwear_emails``. A
``dedupe_key`` stops the same reminder, launch or arrival email going to the same place twice.
Nothing here raises to the caller: a failed email is a logged row the coordinator can read.

Callers commit their own change first, then call these (rule 14).
"""
from __future__ import annotations

import html
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import MerchSquareConnection, Organisation
from app.services import teamwear as tw

logger = logging.getLogger(__name__)


def kit_link(club: Organisation) -> Optional[str]:
    if not club.availability_link_token:
        return None
    return f"{settings.public_base_url.rstrip('/')}/playerdash/{club.availability_link_token}/kit"


def _money(v) -> str:
    return f"${Decimal(str(v or 0)):,.2f}"


def _fmt_date(d) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        from datetime import date
        d = date.fromisoformat(d[:10])
    return d.strftime("%a %-d %b %Y")


def _wrap(club: Organisation, title: str, body_html: str) -> str:
    colour = club.primary_color or "#111827"
    return (
        f"<div style=\"font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;color:#111827\">"
        f"<div style=\"background:{html.escape(colour)};color:#fff;padding:16px 20px;font-weight:bold;font-size:18px\">"
        f"{html.escape(club.name)} · {html.escape(title)}</div>"
        f"<div style=\"padding:20px;line-height:1.5;font-size:14px\">{body_html}</div></div>"
    )


def _button(url: Optional[str], label: str) -> str:
    if not url:
        return ""
    return (f"<p><a href=\"{html.escape(url)}\" style=\"display:inline-block;background:#111827;color:#fff;"
            f"padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:bold\">{html.escape(label)}</a></p>")


def _lines_table(order: dict) -> tuple[str, str]:
    rows_h, rows_t = [], []
    for l in order["lines"]:
        what = f"{l['product_name']} ({l['size']})" if l["size"] else l["product_name"]
        extra = " ".join(x for x in [f"#{l['number']}" if l["number"] else "", l["text"] or ""] if x)
        who = l["wearer_name"] or ""
        if l["state"] == "cut":
            price = "Not available this round"
        elif l["state"] != "active":
            continue
        elif l["club_covered"]:
            price = "Covered by the club"
        else:
            price = _money(Decimal(str(l["unit_price"])) * l["qty"])
        rows_h.append(
            f"<tr><td style=\"padding:4px 8px 4px 0\">{l['qty']} × {html.escape(what)}"
            f"{(' · ' + html.escape(extra)) if extra else ''}<br><span style=\"color:#6b7280\">{html.escape(who)}</span></td>"
            f"<td style=\"padding:4px 0;text-align:right;white-space:nowrap\">{html.escape(price)}</td></tr>")
        rows_t.append(f"{l['qty']} x {what}{(' ' + extra) if extra else ''} for {who}: {price}")
    total = (f"<tr><td style=\"padding:6px 8px 0 0;font-weight:bold\">Total</td>"
             f"<td style=\"padding:6px 0 0;text-align:right;font-weight:bold\">{_money(order['total'])}</td></tr>")
    return f"<table style=\"width:100%;border-collapse:collapse\">{''.join(rows_h)}{total}</table>", \
        "\n".join(rows_t) + f"\nTotal: {_money(order['total'])}"


def _pay_block(s: dict, order: dict, link: Optional[str]) -> tuple[str, str]:
    owing = Decimal(str(order["balance"]))
    if owing <= 0:
        return "<p>There is nothing to pay on this order.</p>", "There is nothing to pay on this order."
    due = _fmt_date(order["due_on"])
    h = [f"<p><b>Amount due: {_money(owing)}</b>{(' by ' + html.escape(due)) if due else ''}</p>"]
    t = [f"Amount due: {_money(owing)}{(' by ' + due) if due else ''}"]
    if s.get("bank_bsb") and s.get("bank_account_number"):
        h.append("<p>Pay by bank transfer:<br>"
                 f"Account name: {html.escape(s.get('bank_account_name') or '')}<br>"
                 f"BSB: {html.escape(s['bank_bsb'])}<br>Account: {html.escape(s['bank_account_number'])}<br>"
                 f"Reference: <b>{html.escape(order['reference'])}</b></p>")
        t.append(f"Bank transfer: {s.get('bank_account_name') or ''} BSB {s['bank_bsb']} account "
                 f"{s['bank_account_number']}, reference {order['reference']}")
    h.append(_button(link, "View your order and pay by card"))
    if link:
        t.append(f"View your order and pay by card: {link}")
    return "".join(h), "\n".join(t)


async def _log(db: AsyncSession, club, *, kind: str, status: str, to_email: Optional[str], campaign_id=None,
               order_id=None, dedupe_key: Optional[str] = None, detail: Optional[str] = None) -> None:
    await db.execute(text(
        "INSERT INTO teamwear_emails (organisation_id, campaign_id, order_id, kind, dedupe_key, to_email, status, detail) "
        "VALUES (CAST(:o AS UUID), CAST(:c AS UUID), CAST(:ord AS UUID), :k, :dk, :e, :s, :d)"),
        {"o": str(club.id), "c": str(campaign_id) if campaign_id else None, "ord": str(order_id) if order_id else None,
         "k": kind, "dk": dedupe_key, "e": to_email, "s": status, "d": detail})


async def _already(db: AsyncSession, club, dedupe_key: str) -> bool:
    return bool((await db.execute(text(
        "SELECT 1 FROM teamwear_emails WHERE organisation_id = CAST(:o AS UUID) AND dedupe_key = :k AND status = 'sent'"),
        {"o": str(club.id), "k": dedupe_key})).first())


async def send(db: AsyncSession, club, *, kind: str, to_email: Optional[str], to_name: str, subject: str,
               body_html: str, body_text: str, campaign_id=None, order_id=None,
               dedupe_key: Optional[str] = None) -> str:
    """One email, logged. Returns sent, skipped (already sent) or failed. Never raises."""
    from app.services.selection_notify import _deliver
    try:
        if dedupe_key and await _already(db, club, dedupe_key):
            return "skipped"
        if not to_email:
            await _log(db, club, kind=kind, status="failed", to_email=None, campaign_id=campaign_id,
                       order_id=order_id, detail="no_email")
            return "failed"
        ok, reason = await _deliver(db, club, to_email=to_email, to_name=to_name, subject=subject,
                                    body_html=_wrap(club, subject, body_html), body_text=body_text)
        await _log(db, club, kind=kind, status="sent" if ok else "failed", to_email=to_email,
                   campaign_id=campaign_id, order_id=order_id, dedupe_key=dedupe_key if ok else None,
                   detail=None if ok else reason)
        await db.commit()
        return "sent" if ok else "failed"
    except Exception:
        logger.exception("teamwear %s email to %s failed", kind, to_email)
        try:
            await db.rollback()
        except Exception:
            pass
        return "failed"


def _tally(results: list[str]) -> dict:
    return {k: results.count(k) for k in ("sent", "failed", "skipped")}


# ── the emails ──────────────────────────────────────────────────────────────

async def launch_recipients(db: AsyncSession, club) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (lower(email)) email, COALESCE(display_name_override, name) AS name FROM players "
        "WHERE organisation_id = CAST(:o AS UUID) AND email IS NOT NULL AND email LIKE '%@%' "
        "AND COALESCE(status, 'active') = 'active' ORDER BY lower(email), name"),
        {"o": str(club.id)})).mappings().all()
    return [dict(r) for r in rows]


async def launch_body(db: AsyncSession, club, campaign_id) -> tuple[str, str, str]:
    c = await tw.get_campaign(db, club.id, campaign_id)
    items = await tw.campaign_items(db, c["id"])
    rng = {r["product_id"]: r for r in await tw.list_range(db, club.id, product_ids=[i["product_id"] for i in items])}
    base = settings.public_base_url.rstrip("/")
    link = kit_link(club)
    cards_h, cards_t = [], []
    for i in items:
        p = rng.get(str(i["product_id"]))
        if not p:
            continue
        img = f"<img src=\"{html.escape(base + p['images'][0])}\" alt=\"\" width=\"120\" style=\"border-radius:6px\">" if p["images"] else ""
        sizes = ", ".join(z["label"] for z in p["sizes"])
        pers = {"number_name": "Number and name", "number_initials": "Number and initials"}.get(p["personalisation"], "")
        cards_h.append(
            f"<tr><td style=\"padding:8px 12px 8px 0;vertical-align:top;width:130px\">{img}</td>"
            f"<td style=\"padding:8px 0;vertical-align:top\"><b>{html.escape(p['name'])}</b> {_money(i['price'])}<br>"
            f"<span style=\"color:#6b7280\">Sizes: {html.escape(sizes)}{('<br>' + pers) if pers else ''}</span></td></tr>")
        cards_t.append(f"{p['name']} {_money(i['price'])}. Sizes: {sizes}. {pers}".strip())
    closes = c["closes_at"].astimezone(tw.TZ).strftime("%a %-d %b %Y, %-I:%M %p") if c["closes_at"] else ""
    subject = f"Teamwear order open: {c['name']}"
    h = (f"{('<p>' + html.escape(c['intro']).replace(chr(10), '<br>') + '</p>') if c['intro'] else ''}"
         f"<p>Order by <b>{html.escape(closes)}</b>. Nobody pays until the club has confirmed which items are being made.</p>"
         f"<table style=\"width:100%;border-collapse:collapse\">{''.join(cards_h)}</table>"
         f"{_button(link, 'Order on your Player Dashboard')}")
    t = "\n".join(([c["intro"]] if c["intro"] else []) + [f"Order by {closes}.", ""] + cards_t
                  + ([f"\nOrder on your Player Dashboard: {link}"] if link else []))
    return subject, h, t


async def send_launch(db: AsyncSession, club, campaign_id, *, test_to: Optional[str] = None) -> dict:
    subject, h, t = await launch_body(db, club, campaign_id)
    if test_to:
        r = await send(db, club, kind="launch_test", to_email=test_to, to_name=test_to, subject="[Test] " + subject,
                       body_html=h, body_text=t, campaign_id=campaign_id)
        return _tally([r])
    results = []
    for r in await launch_recipients(db, club):
        results.append(await send(db, club, kind="launch", to_email=r["email"], to_name=r["name"], subject=subject,
                                  body_html=h, body_text=t, campaign_id=campaign_id,
                                  dedupe_key=f"launch:{campaign_id}:{r['email'].lower()}"))
    return _tally(results)


async def send_order_received(db: AsyncSession, club, order_id) -> str:
    o = await tw.get_order(db, club.id, order_id)
    table_h, table_t = _lines_table(o)
    link = kit_link(club)
    if o["campaign_id"]:
        subject = f"We have your teamwear order ({o['reference']})"
        lead = ("<p>Thanks, your order is in. Nothing is charged yet: once ordering closes the club checks which items "
                "reach the supplier's minimum and then sends you a payment request.</p>")
        return await send(db, club, kind="order_received", to_email=o["contact_email"], to_name=o["contact_name"],
                          subject=subject, body_html=lead + table_h + _button(link, "View or change your order"),
                          body_text=f"Thanks, your order is in. Nothing is charged yet.\n\n{table_t}\n{link or ''}",
                          campaign_id=o["campaign_id"], order_id=o["id"])
    return await send_payment_request(db, club, order_id)


async def send_payment_request(db: AsyncSession, club, order_id) -> str:
    s = await tw.get_settings(db, club.id)
    o = await tw.get_order(db, club.id, order_id)
    table_h, table_t = _lines_table(o)
    pay_h, pay_t = _pay_block(s, o, kit_link(club))
    cut = any(l["state"] == "cut" for l in o["lines"])
    note = ("<p>Some items did not reach the supplier's minimum and are not being made this round. "
            "They are marked below and are not charged.</p>") if cut else ""
    subject = f"Teamwear payment request ({o['reference']})"
    return await send(db, club, kind="payment_request", to_email=o["contact_email"], to_name=o["contact_name"],
                      subject=subject, body_html=note + table_h + pay_h,
                      body_text=f"{table_t}\n\n{pay_t}", campaign_id=o["campaign_id"], order_id=o["id"],
                      dedupe_key=f"payreq:{o['id']}")


async def send_not_available(db: AsyncSession, club, order_id) -> str:
    o = await tw.get_order(db, club.id, order_id)
    table_h, table_t = _lines_table(o)
    subject = "Your teamwear order: not available this round"
    h = ("<p>None of the items in your order reached the supplier's minimum this round, so nothing is being made "
         "and there is nothing to pay. There is no waitlist; watch for the next order round.</p>" + table_h)
    return await send(db, club, kind="not_available", to_email=o["contact_email"], to_name=o["contact_name"],
                      subject=subject, body_html=h, body_text=f"Nothing in your order is being made this round.\n{table_t}",
                      campaign_id=o["campaign_id"], order_id=o["id"], dedupe_key=f"notavail:{o['id']}")


async def send_payment_requests(db: AsyncSession, club, asked: list, emptied: list) -> dict:
    results = [await send_payment_request(db, club, oid) for oid in asked]
    results += [await send_not_available(db, club, oid) for oid in emptied]
    return _tally(results)


async def send_reminder(db: AsyncSession, club, order: dict, offset: int, *, manual: bool = False) -> str:
    s = await tw.get_settings(db, club.id)
    table_h, table_t = _lines_table(order)
    pay_h, pay_t = _pay_block(s, order, kit_link(club))
    when = "is due today" if offset == 0 else ("is due soon" if offset < 0 else "is overdue")
    subject = f"Reminder: teamwear payment {when} ({order['reference']})"
    key = None if manual else f"reminder:{order['id']}:{offset}"
    return await send(db, club, kind="reminder", to_email=order["contact_email"], to_name=order["contact_name"],
                      subject=subject, body_html=f"<p>Your teamwear payment {when}.</p>" + pay_h + table_h,
                      body_text=f"Your teamwear payment {when}.\n\n{pay_t}\n\n{table_t}",
                      campaign_id=order["campaign_id"], order_id=order["id"], dedupe_key=key)


async def send_change_answer(db: AsyncSession, club, request_id) -> str:
    r = (await db.execute(text(
        "SELECT r.order_id, r.message, r.status, r.response FROM teamwear_change_requests r "
        "WHERE r.id = CAST(:i AS UUID) AND r.organisation_id = CAST(:o AS UUID)"),
        {"i": str(request_id), "o": str(club.id)})).mappings().first()
    if not r:
        return "failed"
    o = await tw.get_order(db, club.id, r["order_id"])
    table_h, table_t = _lines_table(o)
    verdict = "made" if r["status"] == "done" else "not made"
    h = (f"<p>You asked: <i>{html.escape(r['message'])}</i></p><p>The change was {verdict}."
         f"{(' ' + html.escape(r['response'])) if r['response'] else ''}</p><p>Your order now:</p>{table_h}"
         f"<p>Balance: <b>{_money(o['balance'])}</b></p>{_button(kit_link(club), 'View your order')}")
    return await send(db, club, kind="change_answer", to_email=o["contact_email"], to_name=o["contact_name"],
                      subject=f"Your teamwear change request ({o['reference']})", body_html=h,
                      body_text=f"You asked: {r['message']}\nThe change was {verdict}. {r['response'] or ''}\n\n{table_t}",
                      campaign_id=o["campaign_id"], order_id=o["id"])


async def send_arrival(db: AsyncSession, club, campaign_id, order_ids: Optional[list] = None) -> dict:
    c = await tw.get_campaign(db, club.id, campaign_id)
    s = await tw.get_settings(db, club.id)
    results = []
    for o in await tw.load_orders(db, club.id, campaign_id=c["id"]):
        if o["status"] == "cancelled" or not o["packed_at"] or o["collected_at"]:
            continue
        if order_ids is not None and o["id"] not in order_ids:
            continue
        table_h, table_t = _lines_table(o)
        who = s.get("coordinator_name") or "the kit coordinator"
        h = (f"<p>Your teamwear from <b>{html.escape(c['name'])}</b> has arrived and is packed with your name on it. "
             f"Collect it from {html.escape(who)} at the club.</p>{table_h}")
        results.append(await send(db, club, kind="arrival", to_email=o["contact_email"], to_name=o["contact_name"],
                                  subject=f"Your teamwear has arrived ({o['reference']})", body_html=h,
                                  body_text=f"Your teamwear has arrived. Collect it from {who}.\n\n{table_t}",
                                  campaign_id=c["id"], order_id=o["id"], dedupe_key=f"arrival:{o['id']}"))
    await db.execute(text("UPDATE teamwear_campaigns SET arrival_emailed_at = NOW() WHERE id = CAST(:c AS UUID)"),
                     {"c": str(c["id"])})
    await db.commit()
    return _tally(results)


async def email_log(db: AsyncSession, org_id, campaign_id) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT e.kind, e.to_email, e.status, e.detail, e.created_at, o.reference FROM teamwear_emails e "
        "LEFT JOIN teamwear_orders o ON o.id = e.order_id WHERE e.organisation_id = CAST(:o AS UUID) "
        "AND e.campaign_id = CAST(:c AS UUID) ORDER BY e.created_at DESC LIMIT 300"),
        {"o": str(org_id), "c": str(campaign_id)})).mappings().all()
    return [{**dict(r), "created_at": tw.iso(r["created_at"])} for r in rows]


# ── reminders (daily job) ───────────────────────────────────────────────────

async def due_reminders(db: AsyncSession, club, today=None) -> list[tuple[dict, int]]:
    """Orders asked to pay, still owing, whose due date plus one of the schedule's offsets is today.
    Never cancels anything: an unpaid order waits for the coordinator."""
    today = today or tw.today_local()
    s = await tw.get_settings(db, club.id)
    out = []
    orders = await tw.load_orders(db, club.id)
    camps = {}
    for o in orders:
        if o["status"] != "confirmed" or not o["payment_requested_at"] or not o["due_on"] or o["balance"] <= 0:
            continue
        if o["unpaid_decision"] == "proceed":
            continue
        if o["campaign_id"]:
            c = camps.get(o["campaign_id"]) or await tw.get_campaign(db, club.id, o["campaign_id"])
            camps[o["campaign_id"]] = c
            if c["stage"] != "payment":
                continue
            offsets = tw.parse_offsets(c["reminder_offsets"]) if c["reminder_offsets"] is not None else tw.parse_offsets(s["reminder_offsets"])
        else:
            offsets = tw.parse_offsets(s["reminder_offsets"])
        from datetime import date
        due = date.fromisoformat(o["due_on"])
        for off in offsets:
            if due + timedelta(days=off) == today:
                out.append((o, off))
    return out


async def run_reminders(today=None) -> dict:
    """Scheduler entry: every club with teamwear orders, its reminders for today."""
    from app.models.db import async_session_maker as AsyncSessionLocal
    sent = failed = 0
    async with AsyncSessionLocal() as db:
        org_ids = (await db.execute(text(
            "SELECT DISTINCT organisation_id FROM teamwear_orders WHERE status = 'confirmed' AND payment_requested_at IS NOT NULL"
        ))).scalars().all()
    for oid in org_ids:
        try:
            async with AsyncSessionLocal() as db:
                club = await db.get(Organisation, oid)
                if club is None:
                    continue
                from app.auth.modules import MODULE_MERCH, org_has_module
                if not org_has_module(club, MODULE_MERCH):
                    continue
                for o, off in await due_reminders(db, club, today):
                    r = await send_reminder(db, club, o, off)
                    sent += r == "sent"
                    failed += r == "failed"
        except Exception:
            logger.exception("teamwear reminders failed for %s", oid)
    return {"sent": sent, "failed": failed}


# ── card checkout ───────────────────────────────────────────────────────────

async def card_options(db: AsyncSession, club) -> dict:
    s = await tw.get_settings(db, club.id)
    stripe_ok = bool(s.get("card_stripe") and club.stripe_connect_account_id and club.stripe_connect_charges_enabled)
    conn = (await db.execute(select(MerchSquareConnection).where(MerchSquareConnection.organisation_id == club.id))).scalar_one_or_none()
    square_ok = bool(s.get("card_square") and conn and conn.access_token and conn.location_id and conn.can_take_payments)
    square_reconnect = bool(s.get("card_square") and conn and conn.access_token and not conn.can_take_payments)
    return {"stripe": stripe_ok, "square": square_ok, "square_needs_reconnect": square_reconnect}


async def _owing(db, club, order_id, player) -> dict:
    o = await tw.get_order(db, club.id, order_id)
    if o["placed_by_player_id"] != str(player.id):
        raise tw.TeamwearError("Order not found", 404)
    if o["status"] == "cancelled" or not o["payment_requested_at"]:
        raise tw.TeamwearError("This order has not been asked to pay yet.", 409)
    if Decimal(str(o["balance"])) <= 0:
        raise tw.TeamwearError("This order is paid.", 409)
    return o


async def start_stripe(db: AsyncSession, club, order_id, player) -> str:
    from app.services import stripe_connect_client
    if not (await card_options(db, club))["stripe"]:
        raise tw.TeamwearError("Card payment isn't set up for this club.", 409)
    o = await _owing(db, club, order_id, player)
    amount_cents = int((Decimal(str(o["balance"])) * 100).to_integral_value())
    back = kit_link(club) or settings.public_base_url
    cs = await stripe_connect_client.create_teamwear_checkout_session(
        connected_account_id=club.stripe_connect_account_id, order_id=o["id"], org_id=str(club.id),
        description=f"Teamwear {o['reference']}", amount_cents=amount_cents,
        success_url=f"{back}?paid=stripe&order={o['id']}", cancel_url=f"{back}?order={o['id']}")
    await db.execute(text(
        "INSERT INTO teamwear_checkouts (organisation_id, order_id, provider, external_id, url, amount) "
        "VALUES (CAST(:o AS UUID), CAST(:ord AS UUID), 'stripe', :x, :u, :a)"),
        {"o": str(club.id), "ord": o["id"], "x": cs.id, "u": cs.url, "a": Decimal(amount_cents) / 100})
    await db.commit()
    return cs.url


async def stripe_completed(db: AsyncSession, club, data_object: dict) -> None:
    """Webhook: a teamwear Checkout Session completed. Records the payment once (dedupe on the session)."""
    md = data_object.get("metadata") or {}
    order_id = md.get("order_id")
    if not order_id or data_object.get("payment_status") not in (None, "paid"):
        return
    amount = Decimal(int(data_object.get("amount_total") or 0)) / 100
    if amount <= 0:
        return
    await tw.record_payment(db, club.id, order_id, amount=amount, method="card", source="stripe",
                            reference=data_object.get("payment_intent"), external_ref=f"stripe:{data_object.get('id')}")
    await db.execute(text(
        "UPDATE teamwear_checkouts SET status = 'paid', completed_at = NOW() WHERE provider = 'stripe' AND external_id = :x"),
        {"x": data_object.get("id")})
    await db.commit()


async def start_square(db: AsyncSession, club, order_id, player) -> str:
    from app.services import square_client
    from app.services.square_sync import ensure_fresh_token
    if not (await card_options(db, club))["square"]:
        raise tw.TeamwearError("Card payment through Square isn't set up for this club.", 409)
    o = await _owing(db, club, order_id, player)
    conn = (await db.execute(select(MerchSquareConnection).where(MerchSquareConnection.organisation_id == club.id))).scalar_one()
    token = await ensure_fresh_token(db, conn)
    amount_cents = int((Decimal(str(o["balance"])) * 100).to_integral_value())
    back = kit_link(club) or settings.public_base_url
    link = await square_client.create_payment_link(
        token, location_id=conn.location_id, name=f"Teamwear {o['reference']}", amount_cents=amount_cents,
        currency=settings.stripe_currency or "aud", idempotency_key=str(uuid.uuid4()),
        redirect_url=f"{back}?paid=square&order={o['id']}", reference=o["reference"])
    if not link.get("url"):
        raise tw.TeamwearError("Square did not return a payment page. Try again.", 502)
    await db.execute(text(
        "INSERT INTO teamwear_checkouts (organisation_id, order_id, provider, external_id, provider_order_id, url, amount) "
        "VALUES (CAST(:o AS UUID), CAST(:ord AS UUID), 'square', :x, :po, :u, :a)"),
        {"o": str(club.id), "ord": o["id"], "x": link.get("id"), "po": link.get("order_id"), "u": link["url"],
         "a": Decimal(amount_cents) / 100})
    await db.commit()
    return link["url"]


async def check_square(db: AsyncSession, club, order_id=None) -> int:
    """Read back open Square payment links (the member came back, or the 15-minute job) and record
    any that were paid. Returns how many payments were recorded."""
    from app.services import square_client
    from app.services.square_sync import ensure_fresh_token
    q = ("SELECT id, order_id, provider_order_id FROM teamwear_checkouts WHERE organisation_id = CAST(:o AS UUID) "
         "AND provider = 'square' AND status = 'open' AND created_at > NOW() - INTERVAL '7 days'")
    params = {"o": str(club.id)}
    if order_id:
        q += " AND order_id = CAST(:ord AS UUID)"
        params["ord"] = str(order_id)
    rows = (await db.execute(text(q), params)).mappings().all()
    if not rows:
        return 0
    conn = (await db.execute(select(MerchSquareConnection).where(MerchSquareConnection.organisation_id == club.id))).scalar_one_or_none()
    if conn is None or not conn.access_token:
        return 0
    token = await ensure_fresh_token(db, conn)
    n = 0
    for r in rows:
        if not r["provider_order_id"]:
            continue
        try:
            order = await square_client.retrieve_order(token, r["provider_order_id"])
        except Exception:
            logger.exception("teamwear square check failed for %s", r["provider_order_id"])
            continue
        cents = square_client.order_paid_cents(order)
        if cents <= 0:
            continue
        pid = await tw.record_payment(db, club.id, r["order_id"], amount=Decimal(cents) / 100, method="card",
                                      source="square", reference=order.get("id"),
                                      external_ref=f"square:{r['provider_order_id']}")
        await db.execute(text("UPDATE teamwear_checkouts SET status = 'paid', completed_at = NOW() WHERE id = CAST(:i AS UUID)"),
                         {"i": str(r["id"])})
        n += 1 if pid else 0
    await db.commit()
    return n


async def run_square_checks() -> int:
    from app.models.db import async_session_maker as AsyncSessionLocal
    total = 0
    async with AsyncSessionLocal() as db:
        orgs = (await db.execute(text(
            "SELECT DISTINCT organisation_id FROM teamwear_checkouts WHERE provider = 'square' AND status = 'open' "
            "AND created_at > NOW() - INTERVAL '7 days'"))).scalars().all()
    for oid in orgs:
        try:
            async with AsyncSessionLocal() as db:
                club = await db.get(Organisation, oid)
                if club is not None:
                    total += await check_square(db, club)
        except Exception:
            logger.exception("teamwear square checks failed for %s", oid)
    return total
