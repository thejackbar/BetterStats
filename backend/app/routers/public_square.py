"""BetterMerch — Square OAuth callback (unauthenticated).

Square redirects the admin's browser back here after they authorize. The signed
``state`` (a short-lived JWT minted by /club-admin/merch/square/connect-url)
identifies the club + user, so this route needs no session. We exchange the code
for tokens, store the connection, auto-pick the location when there's only one,
then bounce the browser back to the BetterMerch Square page.

Not gated by require_module — it is part of the OAuth handshake and protects
itself with the signed state.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import MerchSquareConnection, get_db
from app.services import square_client
from app.routers.merch import SQUARE_STATE_TYP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/square", tags=["public-square"])


def _back(ok: bool, msg: str | None = None) -> RedirectResponse:
    base = settings.public_base_url.rstrip("/")
    if ok:
        return RedirectResponse(url=f"{base}/admin/merch/square?connected=1", status_code=302)
    return RedirectResponse(url=f"{base}/admin/merch/square?error={quote(msg or 'connect_failed')}", status_code=302)


def _parse_dt(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@router.get("/callback")
async def square_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if error or not code or not state:
        return _back(False, error or "missing_code")
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return _back(False, "bad_state")
    if payload.get("typ") != SQUARE_STATE_TYP:
        return _back(False, "bad_state")
    try:
        org_id = uuid.UUID(payload["org"])
        user_id = uuid.UUID(payload["uid"]) if payload.get("uid") else None
    except (KeyError, ValueError, TypeError):
        return _back(False, "bad_state")

    try:
        data = await square_client.obtain_token(code)
    except square_client.SquareError as e:
        logger.warning(f"Square token exchange failed: {e}")
        return _back(False, "token_exchange_failed")
    access = data.get("access_token")
    if not access:
        return _back(False, "no_token")

    conn = (await db.execute(
        select(MerchSquareConnection).where(MerchSquareConnection.organisation_id == org_id)
    )).scalar_one_or_none()
    if conn is None:
        conn = MerchSquareConnection(organisation_id=org_id)
        db.add(conn)
    conn.access_token = access
    conn.refresh_token = data.get("refresh_token")
    conn.token_expires_at = _parse_dt(data.get("expires_at"))
    conn.merchant_id = data.get("merchant_id")
    conn.environment = settings.square_environment
    conn.scopes = " ".join(square_client.SCOPES)
    conn.connected_by_user_id = user_id
    conn.connected_at = datetime.now(timezone.utc)
    conn.last_sync_status = None
    conn.last_sync_error = None

    # Auto-pick the location when the merchant has exactly one (the common case).
    try:
        locs = await square_client.list_locations(access)
        active = [l for l in locs if l.get("status", "ACTIVE") == "ACTIVE"] or locs
        if len(active) == 1:
            conn.location_id = active[0].get("id")
            conn.location_name = active[0].get("name")
    except Exception as e:
        logger.warning(f"Square location prefetch failed: {e}")

    await db.commit()
    return _back(True)
