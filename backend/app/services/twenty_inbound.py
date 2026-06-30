"""Twenty INBOUND — turn a CRM record-update webhook into a BetterCricket request.

Twenty is otherwise an export-only sink (twenty_sync). This is the one path data
flows the other way: when a salesperson marks a club interested in a module on the
Twenty Company, the webhook lands here and we queue a module trial request
(``module_action_requests``, source=twenty) for a super admin to action. It never
changes entitlement directly.

The dispatcher is deliberately generic — keyed on ``eventName`` — so future
Twenty-origin request types plug into the same entrypoint. Verified against a real
Twenty payload may need the field paths below tweaked; they follow the shape we
export in twenty_sync (``bcClubId``, ``interestedModules`` as uppercase keys).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import ALL_MODULES
from app.models.db import (
    MarketingClub, ModuleActionRequest, Organisation, OrgModuleSubscription,
)

logger = logging.getLogger(__name__)


def _record_from(payload: dict) -> dict:
    """Twenty wraps the changed row under ``record`` (create/update events). Be
    tolerant of a flat payload too."""
    if not isinstance(payload, dict):
        return {}
    rec = payload.get("record")
    return rec if isinstance(rec, dict) else payload


def _modules_from(value) -> list[str]:
    """Normalise an interested-modules value (Twenty multiselect, uppercase keys, or
    a comma string) to our lowercase module keys."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(",", " ").split()]
    elif isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        return []
    return [p.lower() for p in parts if p and p.lower() in ALL_MODULES]


async def _resolve_org(db: AsyncSession, record: dict) -> Organisation | None:
    """Map a Twenty Company back to a BetterCricket org via the bcClubId we export
    (= marketing_clubs.grassroots_guid -> existing_org_id)."""
    bc_club_id = record.get("bcClubId") or record.get("bcclubid")
    if not bc_club_id:
        return None
    mc = (await db.execute(
        select(MarketingClub).where(MarketingClub.grassroots_guid == str(bc_club_id))
    )).scalar_one_or_none()
    if mc is None or mc.existing_org_id is None:
        return None
    return await db.get(Organisation, mc.existing_org_id)


async def dispatch_webhook(db: AsyncSession, payload: dict) -> dict:
    """Route a verified Twenty webhook. Returns a small summary for the response/log.
    Only company create/update events carrying interested modules do anything today."""
    event = str((payload or {}).get("eventName") or (payload or {}).get("event") or "").lower()
    record = _record_from(payload)
    # Only act on company events (ignore people/associations/etc).
    if "company" not in event and "bcClubId" not in record and "bcclubid" not in record:
        return {"handled": False, "reason": "not a company event"}

    interested = _modules_from(record.get("interestedModules") or record.get("interestedmodules"))
    if not interested:
        return {"handled": False, "reason": "no interested modules"}

    org = await _resolve_org(db, record)
    if org is None:
        return {"handled": False, "reason": "no linked club"}

    # Skip modules the club already holds.
    held = {
        s.module_key for s in (await db.execute(
            select(OrgModuleSubscription.module_key)
            .where(OrgModuleSubscription.organisation_id == org.id)
        )).scalars().all()
    }
    record_id = str(record.get("id") or "")
    created = []
    for module_key in interested:
        if module_key in held:
            continue
        ext_ref = f"twenty:{record_id}:{module_key}" if record_id else None
        # Dedupe: an existing outstanding request, or the same external_ref.
        existing_q = select(ModuleActionRequest.id).where(
            ModuleActionRequest.organisation_id == org.id,
            ModuleActionRequest.module_key == module_key,
            ModuleActionRequest.kind == "trial",
            ModuleActionRequest.status == "outstanding",
        )
        if (await db.execute(existing_q)).first():
            continue
        if ext_ref and (await db.execute(
            select(ModuleActionRequest.id).where(ModuleActionRequest.external_ref == ext_ref)
        )).first():
            continue
        db.add(ModuleActionRequest(
            organisation_id=org.id,
            module_key=module_key,
            kind="trial",
            status="outstanding",
            source="twenty",
            note="Interest flagged in the CRM",
            external_ref=ext_ref,
        ))
        created.append(module_key)
    if created:
        await db.commit()
    return {"handled": True, "club": org.name, "created": created}
