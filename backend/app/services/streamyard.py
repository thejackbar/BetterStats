"""Push a webinar registrant into StreamYard, so they only ever fill in one form.

WHY THIS EXISTS. StreamYard's own webinar registration was switched on for this
broadcast, so somebody who registered on `/demo` was handed a link and asked for
their details a second time — by StreamYard, on StreamYard's domain. Every field
that second form asks for (email, first name, last name, phone) is already on our
own row, so asking again is pure friction on paid traffic.

THE FIX IS TWO HALVES AND ONLY ONE OF THEM IS CODE:

  1. StreamYard's registration gate is turned OFF, in StreamYard. That is what
     removes the second form, and nothing in this repo can reach it — see
     `_WHY_THE_LINK_CANNOT_CARRY_A_REGISTRATION` below for what was tried.
  2. This module pushes each registrant into StreamYard anyway, so their
     registrant list, their attendee report and their own reminders still know
     who is coming. That is this file.

BEST-EFFORT, ALWAYS. A registration is complete the moment our own row is
written — the page has already handed the link over by then. Nothing here may
raise, block, slow or fail a registration, so every call returns an outcome
rather than throwing, and the outcome lands on the row so a failure is visible
rather than silent.

UNDOCUMENTED AND UNVERSIONED. `oa-api.streamyard.com/api/public` is what their
own watch page calls; there is no published API. So this is written to fail
softly and say so, never to be depended on: the registration, the confirmation
email, the reminder and the viewing link all work with this switched off,
erroring, or removed by StreamYard tomorrow.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API = "https://oa-api.streamyard.com/api/public"
WATCH = "https://streamyard.com/watch"

# Their API refuses an unauthenticated call, so a session has to be minted by
# loading the watch page first (it sets a `jwtOnAir` cookie). Cheap, and it is
# what a real visitor's browser does.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# The registration form's field ids are per-DEFINITION, and change the moment
# somebody edits the form in StreamYard — so they are FETCHED and mapped by
# `type`, never hardcoded. Cached only briefly, so an edit is picked up within
# the hour rather than at the next deploy.
_DEFINITION_TTL = 600
_definition_cache: dict[str, tuple[float, dict]] = {}

_WHY_THE_LINK_CANNOT_CARRY_A_REGISTRATION = """
Measured, not assumed, before settling on "turn the gate off":

  * The browser cannot register from our page. A CORS preflight to
    `POST /webinars/{id}/registrations` with `Origin: https://betterat.cricket`
    answers `{"message":"CORS error: Origin not allowed"}`.
  * A registration is bound to the SESSION that created it. `GET /webinars/{id}`
    reads `isUserRegistered: true` for the session that POSTed and 401s on the
    registration id alone, so a registration our backend creates cannot be
    handed to the visitor's own browser.
  * The `?token=` a StreamYard reminder email links to is not the registration
    id. Loading `/watch/{id}?token={registration id}` leaves
    `sessionRegistrationId` empty in the page's own server-rendered props, and
    so do `registrationId=`, `rid=` and the `embed=true` variants.

So with the gate ON there is no way to skip the second form, and with it OFF
there is no second form to skip. This module is only about their list.
"""


def webinar_id_from(watch_url: str) -> Optional[str]:
    """The broadcast id out of the watch link we already hold.

    Derived rather than declared as a second constant: `webinar.EVENT.watch_url`
    is the one place the broadcast is named, and a separate id would be one more
    thing to keep in step when the next event is set up. A watch link that is
    not StreamYard's simply yields None, and every function here no-ops.
    """
    match = re.match(r"^https?://(?:www\.)?streamyard\.com/watch/([A-Za-z0-9_-]+)",
                     (watch_url or "").strip())
    return match.group(1) if match else None


def split_name(name: str) -> tuple[str, str]:
    """Our form asks for one Name; theirs asks for two.

    Split at the LAST space, so the two join back to exactly what the person
    typed — that is what StreamYard shows beside their chat messages.
    A single-word name yields an empty surname, which their API refuses (a
    required field cannot be blank, verified against the live endpoint) — the
    caller skips the push rather than inventing one. See `push_registration`.
    """
    parts = (name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


async def _session(client: httpx.AsyncClient, webinar_id: str) -> None:
    """Mint the session their API requires by loading the watch page, exactly as
    a visitor's browser does. Sets a `jwtOnAir` cookie on the client."""
    await client.get(f"{WATCH}/{webinar_id}")


def _headers(webinar_id: str) -> dict[str, str]:
    return {
        "content-type": "application/json",
        # Their own CSRF marker. Absent, the API refuses the write.
        "x-csrf-protection": "true",
        "origin": "https://streamyard.com",
        "referer": f"{WATCH}/{webinar_id}",
    }


async def _field_map(client: httpx.AsyncClient, webinar_id: str) -> Optional[dict]:
    """`{definition_id, ids: {type: field id}}` for the broadcast's current form.

    Returns None when the broadcast has no registration form configured at all,
    which is the ordinary state once the gate is switched off — and is why the
    caller treats it as "nothing to push to" rather than an error.
    """
    cached = _definition_cache.get(webinar_id)
    if cached and (time.time() - cached[0]) < _DEFINITION_TTL:
        return cached[1] or None

    response = await client.get(f"{API}/webinars/{webinar_id}",
                                headers={"x-csrf-protection": "true",
                                         "referer": f"{WATCH}/{webinar_id}"})
    response.raise_for_status()
    body = response.json()
    definitions = body.get("registrationFieldDefinitions") or []
    if not definitions:
        _definition_cache[webinar_id] = (time.time(), {})
        return None
    definition = definitions[0]
    resolved = {
        "definition_id": definition.get("id"),
        "ids": {
            field.get("type"): field.get("id")
            for field in ((definition.get("fields") or {}).get("data") or [])
            if field.get("type") and field.get("id")
        },
    }
    _definition_cache[webinar_id] = (time.time(), resolved)
    return resolved


async def push_registration(
    *, watch_url: str, name: str, email: str, phone: Optional[str] = None,
    time_zone: str = "Australia/Perth",
) -> dict[str, Any]:
    """Register one person with StreamYard. Never raises.

    Returns `{"ok": bool, "id": str|None, "error": str|None, "skipped": str|None}`.
    `skipped` is the honest third answer for the cases where there is nothing to
    do and nothing has gone wrong: the broadcast is not a StreamYard one, or it
    has no registration form.

    IDEMPOTENT AT THEIR END, verified against the live endpoint: posting the same
    email twice returns the SAME registration id and does not overwrite the
    stored values. So a retry is free, and a correction on our side does NOT
    reach theirs — first write wins, which is why the caller only pushes a row
    that has not been pushed before rather than re-pushing on every edit.
    """
    webinar_id = webinar_id_from(watch_url)
    if not webinar_id:
        return {"ok": False, "id": None, "error": None,
                "skipped": "the watch link is not a StreamYard broadcast"}

    first, last = split_name(name)
    if not first or not last:
        # Their form requires a surname and refuses a blank one (400). Inventing
        # one would put a name we made up beside this person's chat messages in
        # front of everyone watching, so the push is skipped and said out loud.
        # They are still registered with us, still emailed, and — with the gate
        # off — the link still lets them in.
        return {"ok": False, "id": None, "error": None,
                "skipped": "no surname to send (their form requires one)"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            await _session(client, webinar_id)
            fields = await _field_map(client, webinar_id)
            if not fields:
                return {"ok": False, "id": None, "error": None,
                        "skipped": "the broadcast has no registration form"}

            ids = fields["ids"]
            values: dict[str, str] = {}
            for field_type, value in (("email", email), ("firstName", first),
                                      ("lastName", last), ("phone", phone or "")):
                key = ids.get(field_type)
                # An optional field with nothing in it is omitted rather than
                # sent blank — both are accepted, and omitting is what their own
                # form does.
                if key and value:
                    values[key] = value

            payload = {
                # Their API hoists these three to the top level as well as
                # carrying them in `fields.values`; the rest live only there.
                "firstName": first,
                "lastName": last,
                "email": email,
                "timeZone": time_zone,
                "fields": {"definitionId": fields["definition_id"], "values": values},
            }
            response = await client.post(
                f"{API}/webinars/{webinar_id}/registrations",
                headers=_headers(webinar_id), json=payload,
            )
    except Exception as exc:  # noqa: BLE001 - a registration must never fail on this
        logger.warning("streamyard: push failed for %s: %s", email, exc)
        return {"ok": False, "id": None, "error": str(exc)[:300], "skipped": None}

    if response.status_code in (200, 201):
        try:
            body = response.json()
        except ValueError:
            body = {}
        return {"ok": True, "id": str(body.get("id") or "") or None,
                "error": None, "skipped": None}

    detail = (response.text or "")[:300]
    logger.warning("streamyard: push refused for %s (%s): %s",
                   email, response.status_code, detail)
    return {"ok": False, "id": None,
            "error": f"HTTP {response.status_code}: {detail}", "skipped": None}
