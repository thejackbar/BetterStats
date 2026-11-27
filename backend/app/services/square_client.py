"""Square API client for the BetterMerch POS integration.

Thin async wrapper over the Square Connect API: OAuth (obtain / refresh / revoke
a token), locations, catalog, inventory counts and completed orders. Host is
picked from settings.square_environment (sandbox vs production). Reference:
https://developer.squareup.com/reference/square
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = 30.0
# Read scopes: merchant profile (name), catalog items, inventory counts,
# completed orders (sales). Plus, from migration 402, ORDERS_WRITE and
# PAYMENTS_WRITE so teamwear can create a Square payment link for a member's
# order. A connection made before then has only the read scopes and must be
# reconnected before it can take a card payment (`can_take_payments`).
READ_SCOPES = ["MERCHANT_PROFILE_READ", "ITEMS_READ", "INVENTORY_READ", "ORDERS_READ"]
PAYMENT_SCOPES = ["ORDERS_WRITE", "PAYMENTS_WRITE"]
SCOPES = READ_SCOPES + PAYMENT_SCOPES


class SquareError(Exception):
    pass


def _headers(token: str) -> dict:
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if settings.square_api_version:
        h["Square-Version"] = settings.square_api_version
    return h


def authorize_url(state: str) -> str:
    """The Square authorize URL the admin's browser is sent to."""
    params = {
        "client_id": settings.square_app_id,
        "scope": " ".join(SCOPES),
        "session": "false",
        "state": state,
        "redirect_uri": settings.square_oauth_redirect,
    }
    return f"{settings.square_api_base}/oauth2/authorize?{urlencode(params)}"


def _raise_for(resp: httpx.Response) -> dict:
    if resp.status_code >= 400:
        try:
            body = resp.json()
            errs = body.get("errors") or body.get("error_description") or body
        except Exception:
            errs = resp.text
        raise SquareError(f"Square API {resp.status_code}: {errs}")
    return resp.json() if resp.content else {}


# ── OAuth ────────────────────────────────────────────────────────────────────

async def obtain_token(code: str) -> dict:
    body = {
        "client_id": settings.square_app_id,
        "client_secret": settings.square_app_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.square_oauth_redirect,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{settings.square_api_base}/oauth2/token", json=body)
    return _raise_for(resp)


async def refresh_token(refresh: str) -> dict:
    body = {
        "client_id": settings.square_app_id,
        "client_secret": settings.square_app_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{settings.square_api_base}/oauth2/token", json=body)
    return _raise_for(resp)


async def revoke_token(access_token: str) -> dict:
    # Revoke is authenticated with the application secret, not the access token.
    headers = {"Authorization": f"Client {settings.square_app_secret}", "Content-Type": "application/json"}
    body = {"client_id": settings.square_app_id, "access_token": access_token}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{settings.square_api_base}/oauth2/revoke", json=body, headers=headers)
    return _raise_for(resp)


# ── Resources ────────────────────────────────────────────────────────────────

async def list_locations(token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.get(f"{settings.square_api_base}/v2/locations", headers=_headers(token))
    return _raise_for(resp).get("locations", [])


async def list_catalog_items(token: str) -> list[dict]:
    """All catalog ITEM objects (each carries its ITEM_VARIATIONs nested in
    item_data.variations), following the cursor to exhaustion."""
    items: list[dict] = []
    cursor = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        for _ in range(200):  # hard page cap
            params = {"types": "ITEM"}
            if cursor:
                params["cursor"] = cursor
            resp = await c.get(f"{settings.square_api_base}/v2/catalog/list",
                               params=params, headers=_headers(token))
            data = _raise_for(resp)
            items.extend(data.get("objects", []))
            cursor = data.get("cursor")
            if not cursor:
                break
    return items


async def inventory_counts(token: str, object_ids: list[str], location_id: str) -> dict:
    """Map of catalog_object_id -> IN_STOCK quantity (int) for the given
    variation ids at one location. Batched in chunks."""
    out: dict[str, int] = {}
    if not object_ids:
        return out
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        for i in range(0, len(object_ids), 250):
            chunk = object_ids[i:i + 250]
            cursor = None
            for _ in range(50):
                body = {"catalog_object_ids": chunk, "location_ids": [location_id]}
                if cursor:
                    body["cursor"] = cursor
                resp = await c.post(f"{settings.square_api_base}/v2/inventory/counts/batch-retrieve",
                                   json=body, headers=_headers(token))
                data = _raise_for(resp)
                for cnt in data.get("counts", []):
                    if cnt.get("state") == "IN_STOCK":
                        try:
                            out[cnt["catalog_object_id"]] = int(float(cnt.get("quantity", "0")))
                        except (ValueError, TypeError):
                            out[cnt["catalog_object_id"]] = 0
                cursor = data.get("cursor")
                if not cursor:
                    break
    return out


async def search_completed_orders(token: str, location_id: str, start_at_iso: str | None) -> list[dict]:
    """Completed orders for a location, closed after start_at_iso, oldest first."""
    orders: list[dict] = []
    cursor = None
    date_filter = {"closed_at": {"start_at": start_at_iso}} if start_at_iso else None
    query_filter = {"state_filter": {"states": ["COMPLETED"]}}
    if date_filter:
        query_filter["date_time_filter"] = date_filter
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        for _ in range(100):
            body = {
                "location_ids": [location_id],
                "query": {
                    "filter": query_filter,
                    "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
                },
                "limit": 200,
            }
            if cursor:
                body["cursor"] = cursor
            resp = await c.post(f"{settings.square_api_base}/v2/orders/search",
                               json=body, headers=_headers(token))
            data = _raise_for(resp)
            orders.extend(data.get("orders", []))
            cursor = data.get("cursor")
            if not cursor:
                break
    return orders


# ── Online payments (teamwear) ──────────────────────────────────────────────

async def create_payment_link(token: str, *, location_id: str, name: str, amount_cents: int,
                              currency: str, idempotency_key: str, redirect_url: str,
                              reference: str | None = None) -> dict:
    """A Square-hosted checkout for one amount (Checkout API, quick pay).
    Returns the ``payment_link`` object: ``id``, ``url`` and ``order_id``. The
    order id is what ``retrieve_order`` reads back to see whether it was paid."""
    body = {
        "idempotency_key": idempotency_key,
        "quick_pay": {
            "name": name[:255],
            "price_money": {"amount": int(amount_cents), "currency": currency.upper()},
            "location_id": location_id,
        },
        "checkout_options": {"redirect_url": redirect_url},
    }
    if reference:
        body["payment_note"] = reference[:500]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{settings.square_api_base}/v2/online-checkout/payment-links",
                            json=body, headers=_headers(token))
    return _raise_for(resp).get("payment_link") or {}


async def retrieve_order(token: str, order_id: str) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.get(f"{settings.square_api_base}/v2/orders/{order_id}", headers=_headers(token))
    return _raise_for(resp).get("order") or {}


def order_paid_cents(order: dict) -> int:
    """What a Square order has collected: the sum of its card/cash tenders, or 0
    while it is still open. A payment link's order is COMPLETED once paid."""
    if (order or {}).get("state") not in ("COMPLETED",):
        return 0
    total = 0
    for t in order.get("tenders") or []:
        total += int(((t.get("amount_money") or {}).get("amount")) or 0)
    if not total:
        total = int(((order.get("total_money") or {}).get("amount")) or 0)
    return total
