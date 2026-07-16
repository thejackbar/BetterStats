"""BetterFees — Xero OAuth callback (unauthenticated).

Xero redirects the admin's browser back here after they authorize. The signed
``state`` (a short-lived JWT minted by /club-admin/fees/xero/connect-url)
identifies the club + user, so this route needs no session. We exchange the
code for tokens, then list the connected tenants — if there's exactly one we
auto-select it (the common case for a single club), otherwise the club picks
from the Xero page. Then bounce the browser back to BetterFees' Xero page.

Not gated by require_module — it is part of the OAuth handshake and protects
itself with the signed state.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import FeeXeroConnection, get_db
from app.services import xero_client
from app.routers.fees import XERO_STATE_TYP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/xero", tags=["public-xero"])


def _back(ok: bool, msg: str | None = None) -> RedirectResponse:
    base = settings.public_base_url.rstrip("/")
    if ok:
        return RedirectResponse(url=f"{base}/admin/fees/xero?connected=1", status_code=302)
    return RedirectResponse(url=f"{base}/admin/fees/xero?error={quote(msg or 'connect_failed')}", status_code=302)


@router.get("/callback")
async def xero_callback(
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
    if payload.get("typ") != XERO_STATE_TYP:
        return _back(False, "bad_state")
    try:
        org_id = uuid.UUID(payload["org"])
        user_id = uuid.UUID(payload["uid"]) if payload.get("uid") else None
    except (KeyError, ValueError, TypeError):
        return _back(False, "bad_state")

    try:
        data = await xero_client.obtain_token(code)
    except xero_client.XeroError as e:
        logger.warning(f"Xero token exchange failed: {e}")
        return _back(False, "token_exchange_failed")
    access = data.get("access_token")
    if not access:
        return _back(False, "no_token")

    conn = (await db.execute(
        select(FeeXeroConnection).where(FeeXeroConnection.organisation_id == org_id)
    )).scalar_one_or_none()
    if conn is None:
        conn = FeeXeroConnection(organisation_id=org_id)
        db.add(conn)
    conn.access_token = access
    conn.refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")
    conn.token_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in else None
    )
    conn.scopes = " ".join(xero_client.SCOPES)
    conn.connected_by_user_id = user_id
    conn.connected_at = datetime.now(timezone.utc)
    conn.last_sync_status = None
    conn.last_sync_error = None

    # Auto-pick the tenant when the grant covers exactly one organisation
    # (the common case for a single club) — otherwise leave tenant_id unset
    # and the Xero page offers a picker.
    try:
        tenants = await xero_client.list_connections(access)
        if len(tenants) == 1:
            conn.tenant_id = tenants[0].get("tenantId")
            conn.tenant_name = tenants[0].get("tenantName")
    except Exception as e:
        logger.warning(f"Xero tenant prefetch failed: {e}")

    await db.commit()
    return _back(True)
