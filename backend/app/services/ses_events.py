"""Ingest Amazon SES events delivered via SNS, and verify the SNS signature.

SES → configuration-set event destination → SNS topic → HTTPS POST to
``/public/ses/events``. Each message is a delivery / bounce / complaint / reject /
delay (and optionally open / click). We:

  * verify the SNS message signature (the suppression list is an abuse vector
    otherwise — anyone could forge a complaint and silence a contact),
  * confirm the SubscriptionConfirmation handshake,
  * write an append-only email_events row (deduped on the SES messageId),
  * maintain the global suppression list + the per-club contact flags.

Linkage to the person: the SES ``messageId`` equals the ``provider_message_id``
we stored on comms_recipients at send time, so a matching recipient gives us the
org / campaign / contact. See docs/bettercomms-architecture.md.
"""
from __future__ import annotations

import base64
import json
import logging
from urllib.parse import urlparse

import httpx
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import EmailEvent, CommsContact, CommsRecipient, CommsCampaign
from app.services.email_suppression import add_suppression
from app.services import twenty_sync
from app.services import ses_tenants
from app.services import comms_lists

logger = logging.getLogger(__name__)

# Field order AWS signs over, by message Type. Subject is included only if present.
_SIGNING_KEYS = {
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
    "UnsubscribeConfirmation": ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"],
}

_CERT_CACHE: dict[str, object] = {}


def _canonical(msg: dict) -> bytes:
    parts: list[str] = []
    for k in _SIGNING_KEYS.get(msg.get("Type"), []):
        if k not in msg:
            continue  # Subject (and only Subject) is legitimately optional
        parts.append(k)
        parts.append(str(msg[k]))
    return ("\n".join(parts) + "\n").encode("utf-8")


async def _public_key(url: str):
    if url in _CERT_CACHE:
        return _CERT_CACHE[url]
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host.endswith(".amazonaws.com"):
        raise ValueError(f"untrusted SigningCertURL host: {host}")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    key = load_pem_x509_certificate(resp.content).public_key()
    _CERT_CACHE[url] = key
    return key


async def verify_signature(msg: dict) -> bool:
    """True if the SNS message signature checks out against its (amazonaws.com)
    signing cert. SignatureVersion 1 = SHA1, 2 = SHA256."""
    try:
        signature = base64.b64decode(msg["Signature"])
        key = await _public_key(msg["SigningCertURL"])
        algo = hashes.SHA256() if str(msg.get("SignatureVersion")) == "2" else hashes.SHA1()
        key.verify(signature, _canonical(msg), padding.PKCS1v15(), algo)
        return True
    except (InvalidSignature, KeyError, ValueError, httpx.HTTPError) as e:
        logger.warning("SNS signature verification failed: %s", e)
        return False


async def handle_sns_message(session: AsyncSession, msg: dict) -> dict:
    """Dispatch one SNS envelope. Confirms a subscription handshake, or parses a
    Notification's SES event and ingests it."""
    typ = msg.get("Type")
    if typ in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        url = msg.get("SubscribeURL")
        if url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.get(url)
            except httpx.HTTPError as e:
                logger.warning("SNS subscription confirm failed: %s", e)
                return {"status": "subscription_confirm_failed"}
        return {"status": "subscription_confirmed"}
    if typ == "Notification":
        try:
            event = json.loads(msg.get("Message") or "{}")
        except json.JSONDecodeError:
            return {"status": "ignored", "reason": "bad message json"}
        return await ingest_ses_event(session, event)
    return {"status": "ignored", "reason": f"type {typ}"}


async def _maybe_tenant_status(session: AsyncSession, event: dict) -> "dict | None":
    """Recognise an SES tenant status-change event (EventBridge → SNS) and reflect
    a paused/resumed tenant onto the owning club. Returns a result dict when it's a
    tenant event, else None so normal per-email ingest continues. Defensive about
    field names — confirm the exact detail shape against a live event."""
    source = (event.get("source") or "").lower()
    dtype = (event.get("detail-type") or event.get("detailType") or "").lower()
    detail = event.get("detail") or {}
    if source != "aws.ses" and "tenant" not in dtype:
        return None
    if "tenant" not in dtype and "tenant" not in json.dumps(detail).lower():
        return None
    name = (detail.get("tenantName") or detail.get("TenantName")
            or detail.get("tenant") or event.get("tenantName"))
    if not name:
        return None
    status = str(detail.get("sendingStatus") or detail.get("status")
                 or detail.get("sendingPaused") or "").lower()
    paused = ("paus" in status or detail.get("sendingEnabled") is False
              or detail.get("sendingPaused") is True)
    matched = await ses_tenants.set_tenant_paused(session, str(name), bool(paused))
    return {"status": "ok", "event": "tenant_status", "tenant": name,
            "paused": bool(paused), "matched": matched}


async def ingest_ses_event(session: AsyncSession, event: dict) -> dict:
    """Parse one SES event (config-set ``eventType`` or feedback
    ``notificationType``) and record it per recipient."""
    # SES tenant status change (multi-tenancy). Delivered via EventBridge → SNS to
    # this same webhook. Shape isn't a per-email event; recognise it first and
    # reflect a paused/resumed tenant onto the owning club. (EventBridge → SNS
    # wiring is the ops step; confirm the exact detail shape on first event.)
    tenant_result = await _maybe_tenant_status(session, event)
    if tenant_result is not None:
        return tenant_result

    etype = (event.get("eventType") or event.get("notificationType") or "").strip().lower()
    if not etype:
        return {"status": "ignored", "reason": "no event type"}
    mail = event.get("mail") or {}
    ses_message_id = mail.get("messageId")

    subtype = reason = None
    recipients: list[str] = []
    if etype == "bounce":
        b = event.get("bounce") or {}
        subtype = b.get("bounceType")            # Permanent | Transient | Undetermined
        reason = b.get("bounceSubType")
        recipients = [r.get("emailAddress") for r in (b.get("bouncedRecipients") or [])]
    elif etype == "complaint":
        c = event.get("complaint") or {}
        subtype = c.get("complaintFeedbackType")
        recipients = [r.get("emailAddress") for r in (c.get("complainedRecipients") or [])]
    if not recipients:
        recipients = mail.get("destination") or []
    recipients = [r for r in recipients if r]

    for email in recipients:
        await _record(session, etype, subtype, reason, ses_message_id, email, event)
    await session.commit()
    # Mirror the event to the CRM (best-effort, after the DB is consistent): a
    # permanent bounce / complaint flips the Person's emailable flags; an open or
    # click records BetterComms Email as their contact source + the campaign.
    await _push_ses_to_twenty(session, etype, subtype, ses_message_id, recipients)
    # Event-driven local-CRM check (independent of whether Twenty is
    # configured, unlike the push above) — an open/click is exactly the kind
    # of signal event the score-based Target/Contacted -> Engaged rule should
    # react to immediately rather than on any periodic schedule. Fired here,
    # not inside _push_ses_to_twenty, so it still runs when Twenty isn't set up.
    if etype in ("open", "click"):
        import asyncio
        from app.services.crm import check_web_signal_promotion
        for email in recipients:
            try:
                asyncio.get_running_loop().create_task(check_web_signal_promotion(email=email))
            except RuntimeError:
                pass
    return {"status": "ok", "event": etype, "recipients": len(recipients)}


async def _campaign_label(session: AsyncSession, ses_message_id) -> "str | None":
    """A human label for the campaign behind a message: its utm_campaign, else the
    subject."""
    if not ses_message_id:
        return None
    rec = await session.scalar(
        select(CommsRecipient).where(
            CommsRecipient.provider_message_id == ses_message_id).limit(1))
    if not rec or not rec.campaign_id:
        return None
    camp = await session.get(CommsCampaign, rec.campaign_id)
    if not camp:
        return None
    return (camp.utm or {}).get("utm_campaign") or camp.subject


async def _push_ses_to_twenty(session: AsyncSession, etype, subtype, ses_message_id,
                              recipients) -> None:
    if not settings.twenty_configured:
        return
    fields: dict = {}
    if etype == "bounce" and (subtype or "").lower() == "permanent":
        fields = {"subscribed": False, "bounced": True}
    elif etype == "complaint":
        fields = {"subscribed": False}
    elif etype in ("open", "click"):
        fields = {"contactSource": "BETTERCOMMS_EMAIL"}
        label = await _campaign_label(session, ses_message_id)
        if label:
            fields["lastCampaign"] = label
    if not fields:
        return
    for email in recipients:
        await twenty_sync.update_person_by_email(email, fields)
        if "subscribed" in fields:
            # A permanent bounce or complaint just opted this person out — check
            # whether every officer of their club(s) has now done so too.
            await twenty_sync.handle_contact_opt_out(session, email)


async def _record(session: AsyncSession, etype: str, subtype, reason,
                  ses_message_id, email: str, payload: dict) -> None:
    e = (email or "").strip().lower()
    if not e:
        return

    rec = None
    if ses_message_id:
        rec = await session.scalar(
            select(CommsRecipient)
            .where(CommsRecipient.provider_message_id == ses_message_id,
                   func.lower(CommsRecipient.email) == e)
            .limit(1))
    org_id = rec.organisation_id if rec else None

    # Append-only, deduped — a redelivered SNS notification is a no-op.
    await session.execute(
        pg_insert(EmailEvent)
        .values(organisation_id=org_id,
                campaign_id=(rec.campaign_id if rec else None),
                recipient_id=(rec.id if rec else None),
                contact_id=(rec.contact_id if rec else None),
                email=e, event_type=etype, event_subtype=subtype, reason=reason,
                ses_message_id=ses_message_id, payload=payload)
        .on_conflict_do_nothing(constraint="uq_email_event_dedupe"))

    hard = etype == "bounce" and (subtype or "").lower() == "permanent"
    complaint = etype == "complaint"

    if hard:
        # The mailbox is dead — global suppression + flag every club that holds it.
        await add_suppression(session, e, "hard_bounce", source="ses", detail=reason)
        await session.execute(
            update(CommsContact).where(func.lower(CommsContact.email) == e)
            .values(bounced=True, bounced_at=func.now()))
        # Drop the dead address from every static list, for each club that has
        # auto-remove enabled (a hard bounce is a fact about the mailbox, so it
        # reaches every club that holds it).
        await comms_lists.auto_remove_from_all_lists(session, email=e)
    elif complaint:
        # A spam complaint — global suppression; flag the sending club (if known)
        # and stop sending them marketing there.
        await add_suppression(session, e, "complaint", source="ses", detail=subtype)
        q = update(CommsContact).where(func.lower(CommsContact.email) == e)
        if org_id:
            q = q.where(CommsContact.organisation_id == org_id)
        await session.execute(q.values(
            complained=True, complained_at=func.now(),
            subscribed=False, unsubscribed_at=func.now()))
        # Drop them from every static list too (scoped to the sending club when
        # known, matching the subscribed flip above), if auto-remove is enabled.
        await comms_lists.auto_remove_from_all_lists(
            session, email=e, organisation_id=org_id)

    if rec is not None:
        if hard or complaint or etype == "reject":
            rec.status = "failed"
            rec.error = (etype + (f":{subtype}" if subtype else ""))[:500]
        elif etype == "delivery" and rec.status != "failed":
            rec.status = "sent"
