"""BetterComms — bulk email to a club's member database (part of BetterAdmin).

A Mailchimp-style send tool, scoped to the caller's club (``get_current_club``)
and gated by the ``MANAGE_COMMS`` capability + the ``comms`` module entitlement
(applied where the router is mounted in main.py).

Three surfaces:
  * **Contacts** — the club's audience. Built from players / fee members (reuse
    existing emails), CSV/paste import, or manual entry. Deduped per club by
    email; ``subscribed`` is the suppression gate.
  * **Campaigns** — compose → preview → test → send. The send runs as a
    detached background task (network kept out of the DB session, like sync),
    writing a per-recipient delivery row for the history view.
  * **Settings** — sender name / reply-to / the Spam Act footer.

Compliance (Spam Act 2003) is baked in, not optional: every send appends a
sender-identification footer + a working one-click unsubscribe link that needs
no login, and every send skips unsubscribed / bounced contacts.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import require_cap, MANAGE_COMMS
from app.config.settings import settings
from app.models.db import (
    User, Organisation, Player, FeeMember,
    CommsContact, CommsCampaign, CommsRecipient,
    async_session_maker, get_db,
)
from app.routers.auth import get_current_user, get_current_club
from app.services.email_service import EmailMessage, get_email_provider, provider_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin/comms", tags=["club-admin-comms"])

_require = Depends(require_cap(MANAGE_COMMS))

# Hold detached send tasks so they aren't garbage-collected mid-flight (same
# pattern as the hard-refresh / dossier builders).
_SEND_TASKS: set[asyncio.Task] = set()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UNSUB_TYP = "comms_unsub"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _norm_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL_RE.match(e) else None


def _first_name(name: Optional[str], email: str) -> str:
    n = (name or "").strip()
    if n:
        return n.split()[0]
    return (email.split("@", 1)[0] or "there").replace(".", " ").split()[0].title()


def _contact_out(c: CommsContact) -> dict:
    return {
        "id": str(c.id),
        "email": c.email,
        "name": c.name,
        "source": c.source,
        "subscribed": c.subscribed,
        "bounced": c.bounced,
        "excluded": c.excluded,
        "player_id": str(c.player_id) if c.player_id else None,
    }


def _campaign_out(c: CommsCampaign) -> dict:
    return {
        "id": str(c.id),
        "subject": c.subject,
        "preheader": c.preheader,
        "body_html": c.body_html,
        "audience": c.audience or {},
        "status": c.status,
        "stats": c.stats or {},
        "error": c.error,
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _sender(org: Organisation) -> tuple[str, str, Optional[str], str]:
    """(from_name, from_email, reply_to, footer) for a club, with fallbacks."""
    from_name = (org.comms_from_name or org.name or settings.email_from_name).strip()
    from_email = settings.email_from_address  # platform domain (authenticated)
    reply_to = (org.comms_reply_to or org.contact_email or settings.email_reply_to or "").strip() or None
    footer = (org.comms_sender_footer or org.name or "").strip()
    return from_name, from_email, reply_to, footer


def _unsub_token(org_id, cid) -> str:
    return jwt.encode(
        {"org": str(org_id), "cid": str(cid), "typ": UNSUB_TYP},
        settings.secret_key, algorithm=settings.algorithm,
    )


def _unsub_url(token: str) -> str:
    # nginx strips /api → backend route /public/comms/unsubscribe/{token}
    return f"{settings.public_base_url.rstrip('/')}/api/public/comms/unsubscribe/{token}"


def _merge(text: str, ctx: dict) -> str:
    out = text or ""
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v)).replace("{{ " + k + " }}", str(v))
    return out


def _body_to_html(body: str) -> str:
    """The compose box may hold plain text or simple HTML. If there's no markup,
    escape it and turn line breaks into <br> so paragraphs survive."""
    b = body or ""
    if "<" in b and ">" in b:
        return b  # author supplied HTML
    return html_lib.escape(b).replace("\n", "<br>\n")


def _html_to_text(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return html_lib.unescape(t).strip()


def _wrap_html(org: Organisation, inner: str, footer: str, unsub_url: str) -> str:
    accent = org.accent_color or "#243352"
    name = html_lib.escape(org.name or "Our Club")
    logo = (
        f'<img src="{html_lib.escape(org.logo_url)}" alt="" height="40" '
        f'style="height:40px;max-height:40px;display:block">'
        if org.logo_url else f'<strong style="color:#fff;font-size:18px">{name}</strong>'
    )
    safe_footer = html_lib.escape(footer).replace("\n", "<br>") if footer else name
    return f"""\
<!doctype html><html><body style="margin:0;padding:0;background:#f3f4f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <tr><td style="background:{accent};padding:18px 28px;">{logo}</td></tr>
  <tr><td style="padding:28px;color:#1f2937;font-size:15px;line-height:1.6;">{inner}</td></tr>
  <tr><td style="padding:18px 28px;border-top:1px solid #e5e7eb;color:#6b7280;font-size:12px;line-height:1.5;">
    {safe_footer}<br>
    <a href="{unsub_url}" style="color:#6b7280;text-decoration:underline;">Unsubscribe</a> from these emails.
  </td></tr>
</table>
</td></tr></table></body></html>"""


def _render(org: Organisation, campaign: CommsCampaign, *, email: str, name: Optional[str],
            unsub_url: str, footer: str) -> EmailMessage:
    ctx = {
        "first_name": _first_name(name, email),
        "name": (name or "").strip() or _first_name(name, email),
        "club_name": org.name or "",
        "email": email,
        # Lets a template invite unsubscribe inline in the body/subject as well as
        # the automatic footer, e.g. "…or [unsubscribe]({{unsubscribe_url}})".
        "unsubscribe_url": unsub_url,
    }
    subject = _merge(campaign.subject or "", ctx)
    inner = _merge(_body_to_html(campaign.body_html or ""), ctx)
    html = _wrap_html(org, inner, footer, unsub_url)
    text = _html_to_text(inner) + f"\n\n—\n{footer}\nUnsubscribe: {unsub_url}"
    return EmailMessage(
        to_email=email, to_name=name, subject=subject, html=html, text=text,
        from_email=settings.email_from_address,
        from_name=_sender(org)[0],
        reply_to=_sender(org)[2],
        headers={
            "List-Unsubscribe": f"<{unsub_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


async def _campaign_or_404(db: AsyncSession, club: Organisation, cid: str) -> CommsCampaign:
    try:
        u = uuid.UUID(cid)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid campaign id")
    c = await db.get(CommsCampaign, u)
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


async def _resolve_audience(db: AsyncSession, club: Organisation, audience: dict) -> list[CommsContact]:
    """Subscribed, non-bounced, non-excluded contacts matching the chosen segment."""
    base = select(CommsContact).where(
        CommsContact.organisation_id == club.id,
        CommsContact.subscribed.is_(True),
        CommsContact.bounced.is_(False),
        CommsContact.excluded.is_(False),
    )
    atype = (audience or {}).get("type", "all")
    if atype == "list":
        ids = []
        for raw in (audience.get("contact_ids") or []):
            try:
                ids.append(uuid.UUID(str(raw)))
            except (ValueError, TypeError):
                continue
        if not ids:
            return []
        base = base.where(CommsContact.id.in_(ids))
    elif atype == "squad":
        try:
            team_id = uuid.UUID(str(audience.get("team_id")))
        except (ValueError, TypeError):
            return []
        squad_pids = select(Player.id).where(
            Player.organisation_id == club.id, Player.squad_team_id == team_id
        )
        base = base.where(CommsContact.player_id.in_(squad_pids))
    # else "all"
    rows = (await db.execute(base.order_by(CommsContact.email))).scalars().all()
    # dedupe by email (defensive — unique constraint should already guarantee it)
    seen, out = set(), []
    for c in rows:
        if c.email in seen:
            continue
        seen.add(c.email)
        out.append(c)
    return out


# ─── Contacts ────────────────────────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts(
    query: str = "",
    subscribed: Optional[bool] = None,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CommsContact).where(CommsContact.organisation_id == club.id)
    if query.strip():
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(or_(
            func.lower(CommsContact.email).like(like),
            func.lower(func.coalesce(CommsContact.name, "")).like(like),
        ))
    if subscribed is not None:
        stmt = stmt.where(CommsContact.subscribed.is_(subscribed))
    rows = (await db.execute(stmt.order_by(CommsContact.name.nullslast(), CommsContact.email).limit(2000))).scalars().all()

    counts = (await db.execute(
        select(
            func.count(CommsContact.id),
            func.count(CommsContact.id).filter(CommsContact.subscribed.is_(True),
                                               CommsContact.bounced.is_(False),
                                               CommsContact.excluded.is_(False)),
            func.count(CommsContact.id).filter(CommsContact.subscribed.is_(False)),
            func.count(CommsContact.id).filter(CommsContact.bounced.is_(True)),
            func.count(CommsContact.id).filter(CommsContact.excluded.is_(True)),
        ).where(CommsContact.organisation_id == club.id)
    )).one()
    return {
        "contacts": [_contact_out(c) for c in rows],
        "summary": {"total": counts[0], "subscribed": counts[1], "unsubscribed": counts[2],
                    "bounced": counts[3], "excluded": counts[4]},
    }


class ContactCreate(BaseModel):
    email: str
    name: Optional[str] = None


async def _upsert_contact(db: AsyncSession, club: Organisation, email: str, name: Optional[str],
                          source: str, player_id=None, member_id=None) -> str:
    """Insert or update a contact by (org, email). Returns 'added' | 'updated'.
    Never resurrects a suppressed address — subscribed/bounced are left as-is."""
    existing = (await db.execute(select(CommsContact).where(
        CommsContact.organisation_id == club.id, CommsContact.email == email
    ))).scalar_one_or_none()
    if existing:
        if name and not existing.name:
            existing.name = name
        if player_id and not existing.player_id:
            existing.player_id = player_id
        if member_id and not existing.member_id:
            existing.member_id = member_id
        existing.updated_at = datetime.now(timezone.utc)
        return "updated"
    db.add(CommsContact(
        organisation_id=club.id, email=email, name=name, source=source,
        player_id=player_id, member_id=member_id,
    ))
    return "added"


@router.post("/contacts")
async def create_contact(
    data: ContactCreate,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    email = _norm_email(data.email)
    if not email:
        raise HTTPException(status_code=422, detail="A valid email is required")
    result = await _upsert_contact(db, club, email, (data.name or "").strip() or None, "manual")
    await db.commit()
    return {"status": result, "email": email}


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    subscribed: Optional[bool] = None


@router.patch("/contacts/{contact_id}")
async def update_contact(
    contact_id: str,
    data: ContactUpdate,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        c = await db.get(CommsContact, uuid.UUID(contact_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid contact id")
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    if data.name is not None:
        c.name = data.name.strip() or None
    if data.subscribed is not None:
        c.subscribed = data.subscribed
        c.unsubscribed_at = None if data.subscribed else datetime.now(timezone.utc)
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}


@router.delete("/contacts/{contact_id}")
async def delete_contact(
    contact_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        c = await db.get(CommsContact, uuid.UUID(contact_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid contact id")
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(c)
    await db.commit()
    return {"status": "ok"}


class ContactImport(BaseModel):
    text: str  # pasted emails / "Name <email>" / CSV "name,email" — one per line


@router.post("/contacts/import")
async def import_contacts(
    data: ContactImport,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Bulk add from pasted text. Accepts one entry per line in any of:
    ``email``, ``Name <email>``, ``name,email`` or ``email,name`` (comma/semicolon/tab)."""
    added = updated = invalid = 0
    seen: set[str] = set()
    for line in (data.text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, email = _parse_import_line(line)
        email = _norm_email(email)
        if not email or email in seen:
            if not email:
                invalid += 1
            continue
        seen.add(email)
        res = await _upsert_contact(db, club, email, name, "import")
        added += res == "added"
        updated += res == "updated"
    await db.commit()
    return {"added": added, "updated": updated, "invalid": invalid}


def _parse_import_line(line: str) -> tuple[Optional[str], Optional[str]]:
    # "Name <email>"
    m = re.match(r"^(.*?)<([^>]+)>$", line)
    if m:
        return (m.group(1).strip() or None), m.group(2).strip()
    parts = re.split(r"[,;\t]", line)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) == 1:
        return None, parts[0]
    # two columns — whichever looks like the email is the email
    if _EMAIL_RE.match(parts[0].lower()):
        return (parts[1] or None), parts[0]
    return (parts[0] or None), parts[1]


@router.post("/contacts/sync-from-club")
async def sync_from_club(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Pull emails already on file (active players + fee members) into contacts.
    Idempotent; never resurrects an unsubscribed address."""
    added = updated = 0
    players = (await db.execute(select(Player).where(
        Player.organisation_id == club.id, Player.email.isnot(None), Player.status == "active",
    ))).scalars().all()
    for p in players:
        email = _norm_email(p.email)
        if not email:
            continue
        res = await _upsert_contact(db, club, email, p.display_name, "player", player_id=p.id)
        added += res == "added"
        updated += res == "updated"
    members = (await db.execute(select(FeeMember).where(
        FeeMember.organisation_id == club.id, FeeMember.email.isnot(None),
    ))).scalars().all()
    for m in members:
        email = _norm_email(m.email)
        if not email:
            continue
        res = await _upsert_contact(db, club, email, m.full_name, "member", member_id=m.id)
        added += res == "added"
        updated += res == "updated"
    await db.commit()
    return {"added": added, "updated": updated}


# ─── Audience preview ────────────────────────────────────────────────────────

@router.post("/audience/preview")
async def audience_preview(
    audience: dict,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    contacts = await _resolve_audience(db, club, audience or {"type": "all"})
    return {
        "count": len(contacts),
        "sample": [{"email": c.email, "name": c.name} for c in contacts[:8]],
    }


# ─── Campaigns ───────────────────────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(CommsCampaign).where(
        CommsCampaign.organisation_id == club.id
    ).order_by(CommsCampaign.created_at.desc()).limit(200))).scalars().all()
    return [_campaign_out(c) for c in rows]


class CampaignIn(BaseModel):
    subject: str = ""
    preheader: Optional[str] = None
    body_html: str = ""
    audience: Optional[dict] = None


@router.post("/campaigns")
async def create_campaign(
    data: CampaignIn,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = CommsCampaign(
        organisation_id=club.id,
        subject=(data.subject or "").strip(),
        preheader=(data.preheader or None),
        body_html=data.body_html or "",
        audience=data.audience or {"type": "all"},
        status="draft",
        created_by=user.id,
        stats={},
    )
    db.add(c)
    await db.commit()
    return _campaign_out(c)


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    return _campaign_out(c)


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    data: CampaignIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    if c.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft campaigns can be edited")
    c.subject = (data.subject or "").strip()
    c.preheader = data.preheader or None
    c.body_html = data.body_html or ""
    if data.audience is not None:
        c.audience = data.audience
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _campaign_out(c)


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    if c.status == "sending":
        raise HTTPException(status_code=409, detail="Can't delete a campaign while it's sending")
    await db.delete(c)
    await db.commit()
    return {"status": "ok"}


class TestSend(BaseModel):
    email: str


@router.post("/campaigns/{campaign_id}/test")
async def send_test(
    campaign_id: str,
    data: TestSend,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    email = _norm_email(data.email)
    if not email:
        raise HTTPException(status_code=422, detail="A valid email is required")
    _, _, _, footer = _sender(club)
    # Synthetic unsubscribe token (no contact yet) — the public route handles a
    # missing contact gracefully, so the test still shows a real working link.
    unsub = _unsub_url(_unsub_token(club.id, uuid.uuid4()))
    msg = _render(club, c, email=email, name=None, unsub_url=unsub, footer=footer)
    msg.subject = f"[TEST] {msg.subject}"
    res = await get_email_provider().send(msg)
    if not res.ok:
        raise HTTPException(status_code=502, detail=f"Test send failed: {res.error}")
    return {"status": "ok", "live": get_email_provider().name != "console"}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    if c.status != "draft":
        raise HTTPException(status_code=409, detail=f"Campaign already {c.status}")
    if not (c.subject or "").strip():
        raise HTTPException(status_code=422, detail="Add a subject before sending")
    contacts = await _resolve_audience(db, club, c.audience or {"type": "all"})
    if not contacts:
        raise HTTPException(status_code=422, detail="No subscribed contacts match this audience")

    for ct in contacts:
        db.add(CommsRecipient(
            campaign_id=c.id, organisation_id=club.id, contact_id=ct.id,
            email=ct.email, name=ct.name, status="queued",
        ))
    c.status = "sending"
    c.stats = {"recipients": len(contacts), "sent": 0, "failed": 0}
    c.error = None
    await db.commit()

    task = asyncio.create_task(_run_send(str(c.id), str(club.id)))
    _SEND_TASKS.add(task)
    task.add_done_callback(_SEND_TASKS.discard)
    return {"status": "sending", "recipients": len(contacts), "live": get_email_provider().name != "console"}


@router.get("/campaigns/{campaign_id}/status")
async def campaign_status(
    campaign_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    c = await _campaign_or_404(db, club, campaign_id)
    return {"status": c.status, "stats": c.stats or {}, "error": c.error}


async def _run_send(campaign_id: str, org_id: str) -> None:
    """Detached send loop. Reads recipient data first, performs the provider
    sends concurrently OUTSIDE the session (async sessions aren't concurrency
    safe), then writes results back sequentially."""
    try:
        async with async_session_maker() as s:
            camp = await s.get(CommsCampaign, uuid.UUID(campaign_id))
            org = await s.get(Organisation, uuid.UUID(org_id))
            if not camp or not org or camp.status != "sending":
                return
            _, _, _, footer = _sender(org)
            recips = (await s.execute(select(CommsRecipient).where(
                CommsRecipient.campaign_id == camp.id, CommsRecipient.status == "queued"
            ))).scalars().all()
            # Snapshot to plain data so the network phase touches no ORM objects.
            jobs = [{
                "rid": r.id,
                "email": r.email,
                "name": r.name,
                "unsub": _unsub_url(_unsub_token(org.id, r.contact_id or r.id)),
            } for r in recips]
            # Pre-render every message while we still hold the org (pure CPU).
            messages = {
                j["rid"]: _render(org, camp, email=j["email"], name=j["name"],
                                  unsub_url=j["unsub"], footer=footer)
                for j in jobs
            }

        provider = get_email_provider()
        sem = asyncio.Semaphore(6)

        async def _send_one(rid, msg):
            async with sem:
                res = await provider.send(msg)
                return rid, res

        results = await asyncio.gather(*[_send_one(rid, m) for rid, m in messages.items()])

        sent = failed = 0
        async with async_session_maker() as s:
            now = datetime.now(timezone.utc)
            for rid, res in results:
                r = await s.get(CommsRecipient, rid)
                if not r:
                    continue
                if res.ok:
                    r.status = "sent"
                    r.provider_message_id = res.message_id
                    r.sent_at = now
                    sent += 1
                else:
                    r.status = "failed"
                    r.error = (res.error or "")[:500]
                    failed += 1
            camp = await s.get(CommsCampaign, uuid.UUID(campaign_id))
            if camp:
                camp.status = "sent"
                camp.sent_at = now
                camp.stats = {"recipients": sent + failed, "sent": sent, "failed": failed}
                if failed and not sent:
                    camp.status = "error"
                    camp.error = "All sends failed — check the email provider configuration."
            # Reflect a marketing-outreach send back onto the directory: any club
            # whose exported contact was just sent to is flagged emailed_via=
            # 'campaign' so it isn't re-exported. No-op for ordinary club sends
            # (those contacts have no marketing_club_id).
            await s.execute(text("""
                UPDATE marketing_clubs SET emailed_at = :now, emailed_via = 'campaign',
                       updated_at = NOW()
                WHERE emailed_at IS NULL AND id IN (
                    SELECT cc.marketing_club_id FROM comms_recipients r
                    JOIN comms_contacts cc ON cc.id = r.contact_id
                    WHERE r.campaign_id = :cid AND r.status = 'sent'
                      AND cc.marketing_club_id IS NOT NULL)
            """), {"now": now, "cid": uuid.UUID(campaign_id)})
            await s.commit()
        logger.info("BetterComms: campaign %s sent=%d failed=%d", campaign_id, sent, failed)
    except Exception as e:  # never let the task die silently
        logger.error("BetterComms send failed for %s: %s", campaign_id, e, exc_info=True)
        try:
            async with async_session_maker() as s:
                camp = await s.get(CommsCampaign, uuid.UUID(campaign_id))
                if camp:
                    camp.status = "error"
                    camp.error = f"Unexpected error: {e}"
                    await s.commit()
        except Exception:
            pass


# ─── Settings ────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(CommsContact.id)).where(
        CommsContact.organisation_id == club.id, CommsContact.subscribed.is_(True),
        CommsContact.bounced.is_(False),
    ))).scalar_one()
    return {
        "from_name": club.comms_from_name or club.name,
        "reply_to": club.comms_reply_to or club.contact_email or "",
        "sender_footer": club.comms_sender_footer or "",
        "provider": provider_status(),
        "subscribed_contacts": total,
    }


class SettingsIn(BaseModel):
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    sender_footer: Optional[str] = None


@router.put("/settings")
async def update_settings(
    data: SettingsIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, club.id)
    if data.from_name is not None:
        org.comms_from_name = data.from_name.strip() or None
    if data.reply_to is not None:
        rt = data.reply_to.strip()
        if rt and not _EMAIL_RE.match(rt.lower()):
            raise HTTPException(status_code=422, detail="Reply-to must be a valid email")
        org.comms_reply_to = rt or None
    if data.sender_footer is not None:
        org.comms_sender_footer = data.sender_footer.strip() or None
    await db.commit()
    return {"status": "ok"}
