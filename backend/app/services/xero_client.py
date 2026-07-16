"""Xero API client for the BetterFees bank-transaction import.

Thin async wrapper over Xero's OAuth 2.0 + Accounting API (api.xro/2.0).
Unlike Square's one-token-one-merchant model, a single Xero OAuth grant can
cover several connected organisations ("tenants") — the /connections endpoint
lists which ones a given token can reach, and every Accounting API call is
scoped by an `Xero-tenant-id` header. Reference:
https://developer.xero.com/documentation/guides/oauth2/overview/
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = 30.0
AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
REVOKE_URL = "https://identity.xero.com/connect/revocation"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_BASE = "https://api.xero.com/api.xro/2.0"

# Read-only: identify the user, list connected orgs, read bank transactions.
# offline_access is required to get a refresh token back.
SCOPES = ["openid", "profile", "email", "offline_access", "accounting.transactions.read"]


class XeroError(Exception):
    pass


def authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.xero_client_id,
        "redirect_uri": settings.xero_oauth_redirect,
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _raise_for(resp: httpx.Response):
    if resp.status_code >= 400:
        try:
            body = resp.json()
            if isinstance(body, dict):
                errs = body.get("Detail") or body.get("error_description") or body.get("error") or body
            else:
                errs = body
        except Exception:
            errs = resp.text
        raise XeroError(f"Xero API {resp.status_code}: {errs}")
    return resp.json() if resp.content else {}


# ── OAuth ────────────────────────────────────────────────────────────────────

async def obtain_token(code: str) -> dict:
    body = {"grant_type": "authorization_code", "code": code, "redirect_uri": settings.xero_oauth_redirect}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(TOKEN_URL, data=body, auth=(settings.xero_client_id, settings.xero_client_secret))
    return _raise_for(resp)


async def refresh_token(refresh: str) -> dict:
    body = {"grant_type": "refresh_token", "refresh_token": refresh}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(TOKEN_URL, data=body, auth=(settings.xero_client_id, settings.xero_client_secret))
    return _raise_for(resp)


async def revoke_token(refresh: str) -> dict:
    body = {"token": refresh}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(REVOKE_URL, data=body, auth=(settings.xero_client_id, settings.xero_client_secret))
    return _raise_for(resp)


async def list_connections(access_token: str) -> list[dict]:
    """The Xero organisations ('tenants') this token can reach —
    [{tenantId, tenantName, tenantType}, ...]. Unlike every other endpoint
    here, this one returns a bare JSON array, not an object."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.get(CONNECTIONS_URL, headers={"Authorization": f"Bearer {access_token}"})
    data = _raise_for(resp)
    return data if isinstance(data, list) else []


# ── Accounting API ───────────────────────────────────────────────────────────

def _headers(token: str, tenant_id: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Xero-tenant-id": tenant_id, "Accept": "application/json"}


async def list_bank_accounts(token: str, tenant_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.get(f"{API_BASE}/Accounts", params={"where": 'Type=="BANK"'}, headers=_headers(token, tenant_id))
    return _raise_for(resp).get("Accounts", [])


_LEGACY_DATE_RE = re.compile(r"/Date\((\d+)([+-]\d{4})?\)/")


def parse_xero_date(obj: dict, field: str = "Date"):
    """Xero pairs most date fields with a clean ISO 'XxxString' twin
    (preferred) alongside the legacy ASP.NET AJAX '/Date(1699999999000+0000)/'
    millisecond-epoch form the Accounting API still emits on the bare field.
    Always returns a tz-aware UTC datetime, or None."""
    iso = obj.get(f"{field}String")
    if iso:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = _LEGACY_DATE_RE.match(obj.get(field) or "")
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


async def list_bank_transactions(token: str, tenant_id: str, bank_account_id: str, since: datetime) -> list[dict]:
    """RECEIVE-type (money in) bank transactions for one account, newest
    first, stopping once a page's oldest row falls before `since`. Type and
    account are filtered client-side rather than via Xero's `where` query
    DSL, to keep this call robust against that syntax's rougher edges — the
    same "pull a generous window, filter in Python" tradeoff the Square
    import already makes."""
    headers = _headers(token, tenant_id)
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        for page in range(1, 51):  # hard page cap — 100 rows/page, newest first
            resp = await c.get(f"{API_BASE}/BankTransactions", params={"page": page, "order": "Date DESC"}, headers=headers)
            data = _raise_for(resp)
            batch = data.get("BankTransactions", [])
            if not batch:
                break
            out.extend(batch)
            oldest_on_page = parse_xero_date(batch[-1])
            if oldest_on_page and oldest_on_page < since:
                break
            if len(batch) < 100:
                break
    return [
        t for t in out
        if t.get("Type") == "RECEIVE"
        and (t.get("BankAccount") or {}).get("AccountID") == bank_account_id
        and (parse_xero_date(t) or since) >= since
    ]
