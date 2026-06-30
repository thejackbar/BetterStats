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

import asyncio
import json
import logging
import re
import time
from collections import deque
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Twenty rate-limits the REST API (observed: 100 requests / 60 s per workspace key).
# A burst export blows through it, so we (a) proactively pace to stay under a safe
# ceiling and (b) retry a 429 honouring Retry-After. The limiter is process-global
# (one workspace key), guarded by a lock so the pacing sleep serialises requests.
_RL_MAX = 90            # headroom under Twenty's 100/60s
_RL_WINDOW = 60.0
_rl_lock = asyncio.Lock()
_rl_hits: "deque[float]" = deque()


def _rl_cap() -> int:
    """The client-side ceiling. Configurable so it can track Twenty's server limit if
    that's raised (settings.twenty_rate_per_min), else the safe default."""
    try:
        return int(getattr(settings, "twenty_rate_per_min", 0)) or _RL_MAX
    except (TypeError, ValueError):
        return _RL_MAX


async def _rate_limit() -> None:
    cap = _rl_cap()
    async with _rl_lock:
        now = time.monotonic()
        while _rl_hits and now - _rl_hits[0] >= _RL_WINDOW:
            _rl_hits.popleft()
        if len(_rl_hits) >= cap:
            wait = _RL_WINDOW - (now - _rl_hits[0]) + 0.1
            if wait > 0:
                await asyncio.sleep(wait)
            now = time.monotonic()
            while _rl_hits and now - _rl_hits[0] >= _RL_WINDOW:
                _rl_hits.popleft()
        _rl_hits.append(time.monotonic())


class TwentyApiError(Exception):
    """A Twenty REST error carrying the response body, so logs show which field
    Twenty rejected (raise_for_status alone only gives the status code)."""


def _raise(r: httpx.Response, method: str, plural: str):
    try:
        detail = r.json()
    except Exception:
        detail = {"text": (r.text or "")[:200]}
    raise TwentyApiError(f"{method} /rest/{plural} -> {r.status_code}: "
                         f"{json.dumps(detail)[:400]}")


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

    async def _send(self, http: httpx.AsyncClient, method: str, url: str,
                    **kwargs) -> httpx.Response:
        """One request, paced under the rate limit and retried on a 429 (honouring
        Retry-After, else exponential backoff). Returns the response; callers handle
        non-429 error codes as before."""
        last = None
        for attempt in range(6):
            await _rate_limit()
            last = await http.request(method, url, headers=self._headers, timeout=30, **kwargs)
            if last.status_code != 429:
                return last
            ra = last.headers.get("retry-after")
            try:
                wait = float(ra) if ra else min(2 ** attempt, 30)
            except ValueError:
                wait = min(2 ** attempt, 30)
            logger.warning("twenty 429 (%s %s) — retrying in %.0fs (attempt %d/6)",
                           method, url.rsplit("/", 1)[-1], wait, attempt + 1)
            await asyncio.sleep(wait)
        return last  # exhausted retries — return the last 429 so the caller raises

    async def create(self, http: httpx.AsyncClient, plural: str, values: dict) -> dict:
        r = await self._send(http, "POST", f"{self.base}/rest/{plural}", json=values)
        if r.status_code >= 400:
            _raise(r, "POST", plural)
        return _record(r.json())

    async def update(self, http: httpx.AsyncClient, plural: str, record_id: str,
                     values: dict):
        """PATCH a record. Returns the updated record, or None if it no longer
        exists in Twenty (404) — e.g. an operator deleted it — so the caller can
        drop the stale link and re-create instead of failing."""
        # Always clear deletedAt. Twenty soft-deletes: a record "deleted" in the UI
        # still exists (PATCH returns 200 with deletedAt set) but is hidden from
        # lists. Sending deletedAt=null restores it (no-op on an active record), so
        # the export — the source of truth for the subset — un-trashes records and
        # they reappear, instead of silently "updating" a hidden record.
        body = dict(values)
        body["deletedAt"] = None
        r = await self._send(http, "PATCH", f"{self.base}/rest/{plural}/{record_id}", json=body)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            _raise(r, "PATCH", plural)
        return _record(r.json())

    async def list_page(self, http: httpx.AsyncClient, plural: str, limit: int = 60,
                        starting_after: Optional[str] = None,
                        filter: Optional[str] = None) -> dict:
        """One page of records. Returns the raw JSON payload (``data.<plural>`` array
        plus ``pageInfo``), so the caller can paginate with the cursor. Used to build a
        complete local index when a server-side filter can't be trusted. Pass
        ``filter`` (e.g. ``deletedAt[is]:NOT_NULL``) to reach soft-deleted records,
        which Twenty hides from a default list but still counts as duplicates."""
        params: dict = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if filter:
            params["filter"] = filter
        r = await self._send(http, "GET", f"{self.base}/rest/{plural}", params=params)
        if r.status_code >= 400:
            _raise(r, "GET", plural)
        return r.json()

    async def find_by(self, http: httpx.AsyncClient, plural: str, field: str,
                      value: str) -> Optional[dict]:
        """First record whose ``field`` equals ``value`` (the external-key dedupe
        fallback when the local link table has no row). Returns None on miss or
        error — the caller falls back to create."""
        try:
            r = await self._send(http, "GET", f"{self.base}/rest/{plural}",
                                 params={"filter": f"{field}[eq]:{value}", "limit": 1})
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


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def emails_value(raw: Optional[str]) -> Optional[dict]:
    """A Twenty EMAILS value from a messy directory field — Twenty 400s on a
    malformed or whitespace-padded address. Splits on common separators and
    returns the first token that is a valid single email, else None (so the
    person is created without an email rather than failing)."""
    if not raw:
        return None
    for part in re.split(r"[\s,;/]+", str(raw).strip()):
        p = part.strip().strip(".,;<>()")
        if _EMAIL_RE.match(p):
            return {"primaryEmail": p.lower()}
    return None


def phone(number: Optional[str], country: str = "AU", calling: str = "+61") -> Optional[dict]:
    """A Twenty PHONES value from a messy directory field — Twenty 400s on an
    invalid number (e.g. two numbers mashed together). Splits on explicit
    separators only (NOT spaces, which appear inside one number), and returns the
    first part whose digits are a plausible phone length, else None."""
    if not number:
        return None
    for tok in re.split(r"[/;,|]| or | and |&", str(number), flags=re.I):
        digits = "".join(ch for ch in tok if ch.isdigit())
        if 7 <= len(digits) <= 15:
            return {"primaryPhoneNumber": digits, "primaryPhoneCountryCode": country,
                    "primaryPhoneCallingCode": calling}
    return None


def full_name(name: Optional[str]) -> dict:
    parts = (name or "").strip().split()
    if not parts:
        return {"firstName": "", "lastName": ""}
    if len(parts) == 1:
        return {"firstName": parts[0], "lastName": ""}
    return {"firstName": parts[0], "lastName": " ".join(parts[1:])}


client = TwentyClient()
