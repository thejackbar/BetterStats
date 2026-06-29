"""Thin async client for the Twenty CRM core REST API.

Record CRUD only (the data model is built separately by
``app/scripts/bootstrap_twenty.py`` via the metadata API). Used by
``twenty_sync`` to push the targeted subset of the Clubs Directory into Twenty.

Value shapes Twenty expects on create/update (verified against the live 2.x
instance): SELECT = the option value string, MULTI_SELECT = list of value
strings, NUMBER = int/float, BOOLEAN = bool, DATE_TIME = ISO-8601 string,
CURRENCY = ``{"amountMicros": int, "currencyCode": "AUD"}``, LINKS =
``{"primaryLinkUrl": ..., "primaryLinkLabel": ...}``, FULL_NAME =
``{"firstName": ..., "lastName": ...}``, EMAILS = ``{"primaryEmail": ...}``, and a
many-to-one relation is set with ``<fieldName>Id``.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _record(payload: dict):
    """Unwrap a create/update response: ``{"data": {"createCompany": {...}}}`` ->
    the record dict."""
    data = (payload or {}).get("data")
    if isinstance(data, dict):
        # single mutation key (createCompany / updateCompany / …)
        if len(data) == 1:
            return next(iter(data.values()))
        return data
    return data


def _first(payload: dict):
    """First item of a list response: ``{"data": {"companies": [...]}}`` -> item."""
    data = (payload or {}).get("data")
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v[0] if v else None
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return None


class TwentyClient:
    """Stateless wrapper around the Twenty REST API. Pass an ``httpx.AsyncClient``
    into each call so the caller controls the connection pool/lifetime."""

    def __init__(self, base: Optional[str] = None, key: Optional[str] = None):
        self.base = (base if base is not None else settings.twenty_api_url).rstrip("/")
        self.key = key if key is not None else settings.twenty_api_key

    @property
    def configured(self) -> bool:
        return bool(self.base and self.key)

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json"}

    async def create(self, http: httpx.AsyncClient, plural: str, values: dict) -> dict:
        r = await http.post(f"{self.base}/rest/{plural}", headers=self._headers,
                            json=values, timeout=30)
        r.raise_for_status()
        return _record(r.json())

    async def update(self, http: httpx.AsyncClient, plural: str, record_id: str,
                     values: dict):
        """PATCH a record. Returns the updated record, or None if it no longer
        exists in Twenty (404) — e.g. an operator deleted it — so the caller can
        drop the stale link and re-create instead of failing."""
        r = await http.patch(f"{self.base}/rest/{plural}/{record_id}",
                             headers=self._headers, json=values, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _record(r.json())

    async def find_by(self, http: httpx.AsyncClient, plural: str, field: str,
                      value: str) -> Optional[dict]:
        """First record whose ``field`` equals ``value`` (the external-key dedupe
        fallback when the local link table has no row). Returns None on miss or
        error — the caller falls back to create."""
        try:
            r = await http.get(f"{self.base}/rest/{plural}", headers=self._headers,
                               params={"filter": f"{field}[eq]:{value}", "limit": 1},
                               timeout=30)
            if r.status_code >= 400:
                return None
            return _first(r.json())
        except httpx.HTTPError as e:
            logger.warning("twenty find_by %s.%s failed: %s", plural, field, e)
            return None


# ── value helpers ────────────────────────────────────────────────────────────

def currency(amount_dollars, code: str = "AUD") -> Optional[dict]:
    if amount_dollars is None:
        return None
    return {"amountMicros": int(round(float(amount_dollars) * 1_000_000)),
            "currencyCode": code}


def link(url: Optional[str], label: Optional[str] = None) -> Optional[dict]:
    if not url:
        return None
    return {"primaryLinkUrl": url, "primaryLinkLabel": label or ""}


def phone(number: Optional[str], country: str = "AU", calling: str = "+61") -> Optional[dict]:
    if not number:
        return None
    n = "".join(ch for ch in str(number) if ch.isdigit() or ch == "+")
    if not n:
        return None
    return {"primaryPhoneNumber": n, "primaryPhoneCountryCode": country,
            "primaryPhoneCallingCode": calling}


def full_name(name: Optional[str]) -> dict:
    parts = (name or "").strip().split()
    if not parts:
        return {"firstName": "", "lastName": ""}
    if len(parts) == 1:
        return {"firstName": parts[0], "lastName": ""}
    return {"firstName": parts[0], "lastName": " ".join(parts[1:])}


client = TwentyClient()
