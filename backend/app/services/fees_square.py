"""BetterFees ← Square: surface completed Square sales that look like a
match-fee or membership payment, matched to a club member for review.

Reuses BetterMerch's existing per-club Square OAuth connection (the same
Square account, whichever module connected it first) — there is no separate
OAuth flow here, and nothing here writes back to Square. An admin turns on
`sync_fees` and sets which catalog item names count as a fee sale (e.g. "Match
Fee, Membership"); a Square line item whose name contains one of those
keywords becomes a candidate row with a suggested member match, using the same
`clean_description`/`match_score` fuzzy-matcher the bank-statement CSV import
uses — the buyer name or order note stands in for the bank description.

Preview is stateless (no sync cursor): it re-scans a fixed lookback window of
completed orders on every call and filters out anything already resolved
(applied or dismissed) via `fee_square_import_log`. A small club's "Match Fee"
sales are low-volume, so re-scanning is cheap and much simpler than tracking a
watermark that has to account for orders resolved out of order.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.db import FeeMember, FeeMemberSeason, FeeSquareImportLog, MerchSquareConnection
from app.services import square_client, square_sync
from app.services.fees import clean_description, match_score

LOOKBACK = timedelta(days=400)  # comfortably covers a season, generous either side
DEFAULT_KEYWORDS = "match fee, membership"


def parse_keywords(raw: str | None) -> list[str]:
    raw = (raw or DEFAULT_KEYWORDS).strip()
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _buyer_name(order: dict) -> str:
    """Best-effort human name off an order — a pickup/fulfillment recipient is
    the only place Square Orders reliably carries one for an in-person sale."""
    for f in order.get("fulfillments", []) or []:
        recipient = (f.get("pickup_details") or {}).get("recipient") or {}
        if recipient.get("display_name"):
            return recipient["display_name"]
    return ""


async def fetch_candidates(session, club, season_id, conn: MerchSquareConnection) -> list[dict]:
    """Completed Square sales matching the club's fee-item keywords that
    haven't already been applied or dismissed, each with up to 3 suggested
    member matches (against this season's members) by confidence."""
    if not conn.access_token or not conn.location_id:
        return []
    keywords = parse_keywords(conn.fee_item_keywords)
    if not keywords:
        return []

    token = await square_sync.ensure_fresh_token(session, conn)
    start = datetime.now(timezone.utc) - LOOKBACK
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    orders = await square_client.search_completed_orders(token, conn.location_id, start_iso)

    resolved = set((await session.execute(
        select(FeeSquareImportLog.external_ref).where(
            FeeSquareImportLog.organisation_id == club.id
        )
    )).scalars().all())

    member_rows = (await session.execute(
        select(FeeMemberSeason, FeeMember)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .where(FeeMemberSeason.season_id == season_id)
    )).all()

    out = []
    for order in orders:
        closed = _parse_dt(order.get("closed_at"))
        oid = order.get("id")
        note = (order.get("note") or "").strip()
        buyer = _buyer_name(order)
        for li in order.get("line_items", []) or []:
            name = (li.get("name") or "").strip()
            if not name or not any(k in name.lower() for k in keywords):
                continue
            uid = li.get("uid") or li.get("catalog_object_id") or name
            ref = f"square:{oid}:{uid}"
            if ref in resolved:
                continue
            total = (li.get("total_money") or li.get("gross_sales_money") or {}).get("amount")
            if total is None:
                continue
            amount = float((Decimal(total) / 100).quantize(Decimal("0.01")))
            if amount <= 0:
                continue

            text_for_match = buyer or note or name
            cleaned = clean_description(text_for_match)
            scored = [(match_score(cleaned, m.full_name), ms, m) for ms, m in member_rows]
            scored.sort(key=lambda x: -x[0])
            top = [
                {
                    "member_id": str(m.id),
                    "member_season_id": str(ms.id),
                    "full_name": m.full_name,
                    "confidence": round(score, 3),
                }
                for score, ms, m in scored[:3] if score > 0
            ]
            out.append({
                "external_ref": ref,
                "item_name": name,
                "note": buyer or note or None,
                "amount": amount,
                "occurred_at": closed.date().isoformat() if closed else None,
                "suggested": top[0] if top else None,
                "candidates": top,
            })

    out.sort(key=lambda r: r["occurred_at"] or "")
    return out
