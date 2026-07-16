"""BetterFees ← Xero: pull completed bank transactions from a club's Xero
organisation for reconciliation against fee payments.

This is the same shape as the bank-statement CSV import — a bank-account
transaction with a payer name/reference gets fuzzy-matched to a member and
confirmed by an admin — just sourced live from Xero's bank feed instead of an
uploaded file. Unlike the Square import there's no item-name filtering: every
RECEIVE transaction on the chosen bank account is a candidate, since a bank
account (unlike a Square catalog) isn't mixed with unrelated canteen sales.

Read-only, one Xero OAuth connection per club (fee_xero_connections). Preview
is stateless — it re-scans a lookback window on every call and filters out
anything already resolved (applied/dismissed) via fee_xero_import_log.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.db import FeeMember, FeeMemberSeason, FeeXeroConnection, FeeXeroImportLog
from app.services import xero_client
from app.services.fees import clean_description, match_score

LOOKBACK = timedelta(days=400)  # comfortably covers a season, generous either side
REFRESH_WINDOW = timedelta(minutes=5)  # Xero access tokens only last 30 minutes


async def get_connection(session, org_id) -> FeeXeroConnection | None:
    return (await session.execute(
        select(FeeXeroConnection).where(FeeXeroConnection.organisation_id == org_id)
    )).scalar_one_or_none()


async def ensure_fresh_token(session, conn: FeeXeroConnection) -> str:
    """Return a usable access token, refreshing first if it's missing or close
    to expiry. Commits the refreshed token. Xero's short 30-minute access-token
    life means this refreshes on close to every call — that's expected, it's
    what the refresh token is for."""
    if not conn.refresh_token and not conn.access_token:
        raise xero_client.XeroError("Xero account is not connected")
    now = datetime.now(timezone.utc)
    needs = conn.token_expires_at is None or conn.token_expires_at <= now + REFRESH_WINDOW
    if needs and conn.refresh_token:
        data = await xero_client.refresh_token(conn.refresh_token)
        conn.access_token = data.get("access_token", conn.access_token)
        if data.get("refresh_token"):
            conn.refresh_token = data["refresh_token"]
        expires_in = data.get("expires_in")
        if expires_in:
            conn.token_expires_at = now + timedelta(seconds=int(expires_in))
        await session.commit()
    return conn.access_token


async def fetch_candidates(session, club, season_id, conn: FeeXeroConnection) -> list[dict]:
    """Completed Xero bank transactions (money in) on the chosen account that
    haven't already been applied or dismissed, each with up to 3 suggested
    member matches (against this season's members) by confidence."""
    if not conn.access_token or not conn.tenant_id or not conn.bank_account_id:
        return []

    token = await ensure_fresh_token(session, conn)
    since = datetime.now(timezone.utc) - LOOKBACK
    txns = await xero_client.list_bank_transactions(token, conn.tenant_id, conn.bank_account_id, since)

    resolved = set((await session.execute(
        select(FeeXeroImportLog.external_ref).where(
            FeeXeroImportLog.organisation_id == club.id
        )
    )).scalars().all())

    member_rows = (await session.execute(
        select(FeeMemberSeason, FeeMember)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .where(FeeMemberSeason.season_id == season_id)
    )).all()

    out = []
    for t in txns:
        ref = f"xero:{t.get('BankTransactionID')}"
        if ref in resolved:
            continue
        total = t.get("Total")
        if total is None:
            continue
        try:
            amount = float(Decimal(str(total)).quantize(Decimal("0.01")))
        except Exception:
            continue
        if amount <= 0:
            continue

        contact_name = (t.get("Contact") or {}).get("Name") or ""
        reference = t.get("Reference") or ""
        line_desc = ""
        for li in t.get("LineItems", []) or []:
            if li.get("Description"):
                line_desc = li["Description"]
                break

        text_for_match = contact_name or reference or line_desc
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

        occurred = xero_client.parse_xero_date(t)
        out.append({
            "external_ref": ref,
            "description": contact_name or reference or line_desc or "Xero bank transaction",
            "note": reference or None,
            "amount": amount,
            "occurred_at": occurred.date().isoformat() if occurred else None,
            "suggested": top[0] if top else None,
            "candidates": top,
        })

    out.sort(key=lambda r: r["occurred_at"] or "")
    return out
