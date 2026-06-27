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
import csv
import html as html_lib
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text, update, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import require_cap, MANAGE_COMMS
from app.config.settings import settings
from app.models.db import (
    User, Organisation, Player, FeeMember, ClubMembership, Team,
    CommsContact, CommsCampaign, CommsRecipient, CommsSegment, CommsTemplate,
    CommsList, CommsListMember, EmailSuppression, EmailEvent,
    MarketingClub, MarketingClubContact,
    async_session_maker, get_db,
)
from app.routers.auth import get_current_user, get_current_club, require_super_admin
from app.services.marketing_org import get_outreach_org, org_is_outreach
from app.services import email_suppression as suppress
from app.services import comms_segments
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


def _dir_fields(c: CommsContact, mc: "Optional[MarketingClub]") -> dict:
    """The five Clubs Directory fields resolved for one contact: a per-contact
    merge_vars override wins, then the linked directory club. Blank for an ordinary
    (non-directory) contact. Used so the Lists editor can search and filter on
    club / association / utm_code / state / website."""
    mv = _marketing_vars(mc)
    ov = c.merge_vars or {}

    def pick(key):
        v = ov.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
        return mv.get(key, "") or ""

    return {k: pick(k) for k in ("club", "association", "utm_code", "state", "website")}


async def _mc_map(db: AsyncSession, contacts) -> dict:
    """Batch-load the MarketingClub for a set of contacts, keyed by id."""
    ids = {c.marketing_club_id for c in contacts if c.marketing_club_id}
    if not ids:
        return {}
    rows = (await db.execute(select(MarketingClub).where(MarketingClub.id.in_(ids)))).scalars().all()
    return {m.id: m for m in rows}


def _contact_out(c: CommsContact, mc: "Optional[MarketingClub]" = None) -> dict:
    return {
        "id": str(c.id),
        "email": c.email,
        "name": c.name,
        "source": c.source,
        "subscribed": c.subscribed,
        "bounced": c.bounced,
        "excluded": c.excluded,
        "player_id": str(c.player_id) if c.player_id else None,
        **_dir_fields(c, mc),
    }


def _campaign_out(c: CommsCampaign) -> dict:
    return {
        "id": str(c.id),
        "subject": c.subject,
        "preheader": c.preheader,
        "body_html": c.body_html,
        "audience": c.audience or {},
        "utm": c.utm or {},
        "status": c.status,
        "stats": c.stats or {},
        "error": c.error,
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _from_address(org: Organisation) -> str:
    """The From address for a send. SES puts the per-club local-part on the
    verified per-silo domain (clubs vs BetterCricket marketing), so no per-club
    AWS setup is needed; other providers keep the configured platform address."""
    if (settings.email_provider or "").strip().lower() == "ses":
        domain = settings.ses_marketing_domain if org_is_outreach(org) else settings.ses_club_domain
        local = re.sub(r"[^a-z0-9._-]", "", (org.slug or "club").lower()) or "club"
        if domain:
            return f"{local}@{domain}"
    return settings.email_from_address


def _sender(org: Organisation) -> tuple[str, str, Optional[str], str]:
    """(from_name, from_email, reply_to, footer) for a club, with fallbacks."""
    from_name = (org.comms_from_name or org.name or settings.email_from_name).strip()
    from_email = _from_address(org)
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


_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
_HREF_RE = re.compile(r'(href=["\'])([^"\']+)(["\'])', re.I)


def _is_full_doc(html: str) -> bool:
    """A pasted/imported template is a full HTML document; the compose box is a
    fragment. Full docs render as-is (no double club shell)."""
    low = (html or "").lower()
    return "<html" in low or "<body" in low


def _apply_utm(html: str, utm: dict, utm_code: Optional[str] = None) -> str:
    """Append the campaign's UTM tags to every outbound http(s) link, leaving the
    unsubscribe link, mailto/tel, anchors and already-tagged links alone. Only the
    BetterCricket marketing-outreach org uses this (see _render_parts).

    When ``utm_code`` is given (the recipient club's per-club code) it is added as
    ``utm_id`` so a later anonymous site visit from this link can be tied back to
    the club — that's what powers the "visited the pricing page" segment."""
    params = [(k, str(v).strip()) for k in _UTM_KEYS if (v := (utm or {}).get(k)) and str(v).strip()]
    code = str(utm_code or "").strip()
    if code:
        params.append(("utm_id", code))
    if not params:
        return html
    qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in params)

    def repl(m):
        url = m.group(2)
        low = url.lower()
        if (not low.startswith(("http://", "https://"))
                or "/public/comms/unsubscribe/" in low
                or "utm_source=" in low):
            return m.group(0)
        sep = "&" if "?" in url else "?"
        return f"{m.group(1)}{url}{sep}{qs}{m.group(3)}"

    return _HREF_RE.sub(repl, html)


def _unsub_sentence_html(club_name: str, unsub_url: str, marketing: bool) -> str:
    """The mandatory unsubscribe sentence with the word 'unsubscribe' as the link.
    Marketing (BetterCricket Clubs Directory) and a club's own member email get
    different wording."""
    club = html_lib.escape(club_name or "your club")
    link = (f'<a href="{unsub_url}" style="color:#6b7280;text-decoration:underline;">'
            'unsubscribe</a>')
    if marketing:
        return (f"You are receiving this email because you are listed as a committee "
                f"member or club officer for {club}. If you no longer wish to receive "
                f"emails from BetterCricket, you can {link} at any time.")
    return (f"You are receiving this email because you are a member or associate of "
            f"{club}. If you no longer wish to receive emails from {club}, you can "
            f"{link} at any time.")


def _unsub_sentence_text(club_name: str, unsub_url: str, marketing: bool) -> str:
    club = club_name or "your club"
    if marketing:
        return (f"You are receiving this email because you are listed as a committee "
                f"member or club officer for {club}. If you no longer wish to receive "
                f"emails from BetterCricket, you can unsubscribe at any time: {unsub_url}")
    return (f"You are receiving this email because you are a member or associate of {club}. "
            f"If you no longer wish to receive emails from {club}, you can unsubscribe at "
            f"any time: {unsub_url}")


def _footer_block(footer: str, unsub_url: str, club_name: str, marketing: bool) -> str:
    """The mandatory sender-id + unsubscribe footer, injected into a full-HTML
    template before </body>. Inherits the email's font so it adopts its style; the
    unsubscribe link can never be removed by the author (Spam Act 2003)."""
    safe_footer = html_lib.escape(footer).replace("\n", "<br>") if footer else ""
    # A blank line between the sender-id block and the unsubscribe sentence.
    prefix = f"{safe_footer}<br><br>" if safe_footer else ""
    sentence = _unsub_sentence_html(club_name, unsub_url, marketing)
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin-top:8px;"><tr><td align="center" '
        'style="padding:14px 28px;border-top:1px solid #e5e7eb;color:#6b7280;'
        'font-size:12px;line-height:1.5;font-family:inherit;text-align:center;">'
        f'{prefix}{sentence}</td></tr></table>'
    )


def _inject_footer(full_html: str, footer: str, unsub_url: str, club_name: str, marketing: bool) -> str:
    block = _footer_block(footer, unsub_url, club_name, marketing)
    if re.search(r"</body>", full_html, flags=re.I):
        return re.sub(r"</body>", block + "</body>", full_html, count=1, flags=re.I)
    return full_html + block


def _wrap_html(org: Organisation, inner: str, footer: str, unsub_url: str, club_name: str) -> str:
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
    {safe_footer}<br><br>
    {_unsub_sentence_html(club_name, unsub_url, org_is_outreach(org))}
  </td></tr>
</table>
</td></tr></table></body></html>"""


def _marketing_vars(mc: Optional[MarketingClub]) -> dict:
    """Per-recipient merge variables drawn from the linked Clubs Directory club —
    so a BetterCricket outreach email can personalise with the prospect club's own
    name / association / UTM code. Empty for an ordinary (non-directory) contact."""
    if mc is None:
        return {}
    assoc = (mc.association_name or "").strip()
    if not assoc and isinstance(mc.associations, list):
        assoc = next((a.get("name") for a in mc.associations
                      if isinstance(a, dict) and a.get("name")), "") or ""
    return {
        "club": mc.name or "",
        "association": assoc,
        "utm_code": mc.utm_code or "",
        "state": mc.state or "",
        "website": mc.website_url or "",
    }


# The merge variables BetterComms understands, for the editor reference. The
# club/association/utm_code set only resolves for BetterCricket directory contacts.
MERGE_VARIABLES = [
    {"name": "first_name", "desc": "Recipient's first name", "marketing_only": False},
    {"name": "name", "desc": "Recipient's full name", "marketing_only": False},
    {"name": "email", "desc": "Recipient's email address", "marketing_only": False},
    {"name": "club", "desc": "The recipient's club name", "marketing_only": False},
    {"name": "unsubscribe_url", "desc": "One-click unsubscribe link (also added to the footer automatically)", "marketing_only": False},
    {"name": "association", "desc": "The recipient club's primary association", "marketing_only": True},
    {"name": "utm_code", "desc": "The recipient club's unique UTM code, for link tracking", "marketing_only": True},
    {"name": "state", "desc": "The recipient club's state", "marketing_only": True},
    {"name": "website", "desc": "The recipient club's website", "marketing_only": True},
    {"name": "utm_source", "desc": "Source from this email's UTM section (place inside a link)", "marketing_only": True},
    {"name": "utm_medium", "desc": "Medium from this email's UTM section (place inside a link)", "marketing_only": True},
    {"name": "utm_campaign", "desc": "Campaign from this email's UTM section (place inside a link)", "marketing_only": True},
]

# Merge-variable keys a user can override per contact (stored in
# comms_contacts.merge_vars). name/email live in their own columns and are edited
# directly; unsubscribe_url is per-recipient and never editable.
EDITABLE_MERGE_KEYS = ("first_name", "club", "association", "utm_code", "state", "website")


def _send_vars(c: "CommsContact", mc: "Optional[MarketingClub]") -> dict:
    """The per-contact extra merge vars used at send time: the linked directory
    club's vars plus the contact's own merge_vars overrides. Mirrors the build in
    _run_send so a preview matches the real send exactly."""
    merged = dict(_marketing_vars(mc))
    for k, v in (c.merge_vars or {}).items():
        if k in EDITABLE_MERGE_KEYS and v is not None and str(v).strip() != "":
            merged[k] = v
    return merged


def _context_var_keys(org: Organisation) -> list:
    """The merge variables that apply in this org's context, in display order.
    The club/association/utm_code set only makes sense for BetterCricket directory
    outreach, so a normal club just sees the universal ones."""
    keys = ["first_name", "name", "email", "club"]
    if org_is_outreach(org):
        keys += ["association", "utm_code", "state", "website"]
    keys.append("unsubscribe_url")
    return keys


def _resolved_vars(c: CommsContact, mc: Optional[MarketingClub], org: Organisation) -> dict:
    """Every merge variable resolved for one contact: a per-contact override wins,
    then the linked directory club, then a sensible default. Used by both the
    contact-detail view and the actual send, so they always agree — regardless of
    whether the contact was added manually, imported, or exported."""
    ov = c.merge_vars or {}
    mv = _marketing_vars(mc)

    def pick(key, default):
        v = ov.get(key)
        return v if (v is not None and str(v).strip() != "") else default

    name = (c.name or "").strip()
    return {
        "first_name": pick("first_name", _first_name(c.name, c.email)),
        "name": name or _first_name(c.name, c.email),
        "email": c.email,
        "club": pick("club", mv.get("club") or (org.name or "")),
        "association": pick("association", mv.get("association", "")),
        "utm_code": pick("utm_code", mv.get("utm_code", "")),
        "state": pick("state", mv.get("state", "")),
        "website": pick("website", mv.get("website", "")),
    }


def _render_parts(org: Organisation, *, subject: str, body_html: str, utm: dict,
                  email: str, name: Optional[str], unsub_url: str, footer: str,
                  extra_vars: Optional[dict] = None) -> tuple[str, str, str]:
    """(subject, html, text) for one recipient. A full-HTML template renders as-is
    with the mandatory unsubscribe footer injected; a fragment gets the club shell.
    UTM tagging of links is applied ONLY for the BetterCricket marketing org."""
    ctx = {
        "first_name": _first_name(name, email),
        "name": (name or "").strip() or _first_name(name, email),
        "email": email,
        # {{club}} is the single club variable: the recipient's club. Defaults to
        # the sending org's name (a club emailing its own members), and is
        # overridden below with the directory club for a BetterCricket contact.
        "club": org.name or "",
        # {{club_name}} is kept as a silent back-compat alias (no longer advertised)
        # so older templates that used it still resolve.
        "club_name": org.name or "",
        # Lets a template invite unsubscribe inline in the body/subject as well as
        # the automatic footer, e.g. "…or [unsubscribe]({{unsubscribe_url}})".
        "unsubscribe_url": unsub_url,
    }
    if extra_vars:
        # Per-recipient directory vars (club / association / utm_code …) override
        # the defaults (e.g. {{club}} → the prospect club's name).
        ctx.update(extra_vars)
    apply_utm = org_is_outreach(org)  # UTM is a BetterCricket-marketing-only feature
    if apply_utm:
        # Expose the email's UTM-section values as merge variables, so a template
        # can build hrefs by hand, e.g.
        #   ?utm_source={{utm_code}}&utm_medium={{utm_medium}}&utm_campaign={{utm_campaign}}
        u = utm or {}
        ctx.setdefault("utm_source", str(u.get("utm_source") or ""))
        ctx.setdefault("utm_medium", str(u.get("utm_medium") or ""))
        ctx.setdefault("utm_campaign", str(u.get("utm_campaign") or ""))
    subject = _merge(subject or "", ctx)
    club_name = ctx.get("club") or org.name or ""
    unsub_text = _unsub_sentence_text(club_name, unsub_url, apply_utm)
    text_tail = f"\n\n—\n{footer}\n{unsub_text}" if footer else f"\n\n—\n{unsub_text}"
    link_code = str(ctx.get("utm_code") or "").strip() if apply_utm else ""
    if _is_full_doc(body_html):
        merged = _merge(body_html or "", ctx)
        if apply_utm:
            merged = _apply_utm(merged, utm, link_code)
        html = _inject_footer(merged, footer, unsub_url, club_name, apply_utm)
        text = _html_to_text(merged) + text_tail
    else:
        inner = _merge(_body_to_html(body_html or ""), ctx)
        if apply_utm:
            inner = _apply_utm(inner, utm, link_code)
        html = _wrap_html(org, inner, footer, unsub_url, club_name)
        text = _html_to_text(inner) + text_tail
    return subject, html, text


def _render(org: Organisation, campaign: CommsCampaign, *, email: str, name: Optional[str],
            unsub_url: str, footer: str, extra_vars: Optional[dict] = None) -> EmailMessage:
    subject, html, text = _render_parts(
        org, subject=campaign.subject or "", body_html=campaign.body_html or "",
        utm=(campaign.utm or {}), email=email, name=name, unsub_url=unsub_url, footer=footer,
        extra_vars=extra_vars)
    return EmailMessage(
        to_email=email, to_name=name, subject=subject, html=html, text=text,
        from_email=_from_address(org),
        from_name=_sender(org)[0],
        reply_to=_sender(org)[2],
        headers={
            "List-Unsubscribe": f"<{unsub_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
        # Campaigns are the bulk (news / marketing) stream — keep them on the
        # campaign configuration set, apart from transactional sends.
        configuration_set=(settings.ses_configuration_set or None),
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
    """Sendable contacts matching the chosen audience: subscribed, not bounced /
    complained / excluded per club, and not on the global suppression list (a
    hard bounce or complaint blocks the address across every club)."""
    atype = (audience or {}).get("type", "all")
    if atype == "segment":
        seg_id = (audience or {}).get("segment_id")
        if not seg_id:
            return []
        try:
            sid = uuid.UUID(str(seg_id))
        except (ValueError, TypeError):
            return []
        seg = await db.get(CommsSegment, sid)
        if not seg or seg.organisation_id != club.id:
            return []
        return await comms_segments.resolve_contacts(db, club, seg.definition)
    if atype == "saved_list":
        try:
            lid = uuid.UUID(str((audience or {}).get("list_id")))
        except (ValueError, TypeError):
            return []
        member_ids = select(CommsListMember.contact_id).where(CommsListMember.list_id == lid)
        base = select(CommsContact).where(
            *comms_segments.sendable_where(club.id), CommsContact.id.in_(member_ids))
        rows = (await db.execute(base.order_by(CommsContact.email))).scalars().all()
        seen, out = set(), []
        for c in rows:
            if c.email in seen:
                continue
            seen.add(c.email)
            out.append(c)
        return out
    base = select(CommsContact).where(*comms_segments.sendable_where(club.id))
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
        # Match the contact's own fields plus its linked Clubs Directory fields
        # (club / association / utm_code / state / website) — an OR across all of
        # them, so a search finds a contact by any one.
        stmt = stmt.outerjoin(MarketingClub, MarketingClub.id == CommsContact.marketing_club_id).where(or_(
            func.lower(CommsContact.email).like(like),
            func.lower(func.coalesce(CommsContact.name, "")).like(like),
            func.lower(func.coalesce(MarketingClub.name, "")).like(like),
            func.lower(func.coalesce(MarketingClub.association_name, "")).like(like),
            func.lower(func.coalesce(MarketingClub.utm_code, "")).like(like),
            func.lower(func.coalesce(MarketingClub.state, "")).like(like),
            func.lower(func.coalesce(MarketingClub.website_url, "")).like(like),
        ))
    if subscribed is not None:
        stmt = stmt.where(CommsContact.subscribed.is_(subscribed))
    rows = (await db.execute(stmt.order_by(CommsContact.name.nullslast(), CommsContact.email).limit(5000))).scalars().all()
    mc_map = await _mc_map(db, rows)

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
        "contacts": [_contact_out(c, mc_map.get(c.marketing_club_id)) for c in rows],
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
    email: Optional[str] = None
    subscribed: Optional[bool] = None
    # Per-contact merge-variable overrides (first_name / club / association /
    # utm_code / state / website). Keys present are applied; a blank value reverts
    # that variable to its derived default.
    merge_vars: Optional[dict] = None


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
    if data.email is not None:
        new_email = _norm_email(data.email)
        if not new_email:
            raise HTTPException(status_code=422, detail="A valid email is required")
        if new_email != c.email:
            dup = await db.scalar(select(CommsContact.id).where(
                CommsContact.organisation_id == club.id,
                func.lower(CommsContact.email) == new_email,
                CommsContact.id != c.id))
            if dup:
                raise HTTPException(status_code=409, detail="Another contact already uses that email")
            c.email = new_email
    if data.merge_vars is not None:
        # Authoritative for the keys present: set non-empty, drop blank (revert to
        # default). Keys not present are left untouched.
        merged = dict(c.merge_vars or {})
        for k in EDITABLE_MERGE_KEYS:
            if k in data.merge_vars:
                val = str(data.merge_vars.get(k) or "").strip()
                if val:
                    merged[k] = val
                else:
                    merged.pop(k, None)
        c.merge_vars = merged
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
    # If this contact came from the Club Directory export, flip its source
    # marketing contact back to not-exported so the directory can re-offer it.
    if c.marketing_club_id and c.email:
        await db.execute(
            update(MarketingClubContact)
            .where(MarketingClubContact.marketing_club_id == c.marketing_club_id,
                   func.lower(MarketingClubContact.email) == c.email.lower())
            .values(exported_at=None, updated_at=func.now()))
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


@router.get("/campaigns/{campaign_id}/preview")
async def preview_campaign(
    campaign_id: str,
    index: int = 0,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Render the email exactly as the Nth contact in the chosen audience will
    receive it (true merged values + footer), so you can page through real
    recipients. Falls back to a sample when the audience is empty."""
    c = await _campaign_or_404(db, club, campaign_id)
    contacts = await _resolve_audience(db, club, c.audience or {"type": "all"})
    total = len(contacts)
    _, _, _, footer = _sender(club)
    if total == 0:
        sample = ({"club": "Sample Cricket Club", "association": "Sample Association",
                   "utm_code": "sample-cricket-club", "state": "WA",
                   "website": "https://example.com"} if org_is_outreach(club) else None)
        unsub = _unsub_url(_unsub_token(club.id, uuid.uuid4()))
        subject, html, _ = _render_parts(
            club, subject=c.subject or "", body_html=c.body_html or "", utm=c.utm or {},
            email="sample@example.com", name="Sam Example", unsub_url=unsub, footer=footer,
            extra_vars=sample)
        return {"total": 0, "index": 0, "html": html, "subject": subject, "contact": None}
    idx = max(0, min(index, total - 1))
    ct = contacts[idx]
    mc = await db.get(MarketingClub, ct.marketing_club_id) if ct.marketing_club_id else None
    unsub = _unsub_url(_unsub_token(club.id, ct.id))
    subject, html, _ = _render_parts(
        club, subject=c.subject or "", body_html=c.body_html or "", utm=c.utm or {},
        email=ct.email, name=ct.name, unsub_url=unsub, footer=footer,
        extra_vars=_send_vars(ct, mc))
    return {"total": total, "index": idx, "html": html, "subject": subject,
            "contact": {"name": ct.name, "email": ct.email}}


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
    utm: Optional[dict] = None


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
        utm=data.utm or {},
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
    if data.utm is not None:
        c.utm = data.utm
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
    # In the BetterCricket marketing context, fill the directory vars with a sample
    # so a test send shows {{club}} / {{utm_code}} rather than blanks.
    sample = ({"club": "Sample Cricket Club", "association": "Sample Association",
               "utm_code": "sample-cricket-club", "state": "WA",
               "website": "https://example.com"} if org_is_outreach(club) else None)
    msg = _render(club, c, email=email, name=None, unsub_url=unsub, footer=footer, extra_vars=sample)
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
            # Per-recipient directory vars (club / association / utm_code) for any
            # contact exported from the Clubs Directory — one batched lookup.
            mc_vars: dict = {}
            cids = [r.contact_id for r in recips if r.contact_id]
            if cids:
                # Outer join so a contact with no directory club still gets its own
                # per-contact merge_vars overrides applied.
                for cid, ov, mc in (await s.execute(
                    select(CommsContact.id, CommsContact.merge_vars, MarketingClub)
                    .outerjoin(MarketingClub, MarketingClub.id == CommsContact.marketing_club_id)
                    .where(CommsContact.id.in_(cids))
                )).all():
                    merged = dict(_marketing_vars(mc))
                    for k, v in (ov or {}).items():
                        if k in EDITABLE_MERGE_KEYS and v is not None and str(v).strip() != "":
                            merged[k] = v
                    if merged:
                        mc_vars[cid] = merged
            # Snapshot to plain data so the network phase touches no ORM objects.
            jobs = [{
                "rid": r.id,
                "email": r.email,
                "name": r.name,
                "unsub": _unsub_url(_unsub_token(org.id, r.contact_id or r.id)),
                "vars": mc_vars.get(r.contact_id, {}),
            } for r in recips]
            # Pre-render every message while we still hold the org (pure CPU).
            messages = {
                j["rid"]: _render(org, camp, email=j["email"], name=j["name"],
                                  unsub_url=j["unsub"], footer=footer, extra_vars=j["vars"])
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


# ─── Context: club vs BetterCricket marketing (super admin) ──────────────────
#
# BetterComms is scoped to the acted-as org (get_current_club), so a super admin
# already manages a club's comms by switching into that club. BetterCricket's own
# Clubs Directory campaigns live on a dedicated "outreach" org (a normal
# organisations row flagged is_marketing_outreach). These endpoints let the
# BetterComms UI surface that outreach org as a first-class choice — switch into
# it with the existing act-as-club mechanism — instead of hunting for it in the
# generic club switcher. Non-super admins see only their own club.

@router.get("/context")
async def comms_context(
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    membership = (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )).scalar_one_or_none()
    is_super = bool(membership and membership.role == "super_admin")

    out = {
        "is_super": is_super,
        "current": {
            "id": str(club.id),
            "name": club.name,
            "is_marketing": org_is_outreach(club),
        },
        "marketing_org": None,
    }
    if is_super:
        mk = await get_outreach_org(db)
        if mk:
            out["marketing_org"] = {"id": str(mk.id), "name": mk.name}
    return out


class DesignateMarketingOrg(BaseModel):
    organisation_id: str


@router.post("/marketing-org")
async def set_marketing_org(
    data: DesignateMarketingOrg,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin: designate which org runs BetterCricket's Clubs Directory
    campaigns. Clears any previous holder first so at most one org is flagged
    (the partial unique index would otherwise reject two true rows)."""
    try:
        target_id = uuid.UUID(data.organisation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid organisation id")
    target = await db.get(Organisation, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await db.execute(
        update(Organisation)
        .where(Organisation.is_marketing_outreach.is_(True),
               Organisation.id != target_id)
        .values(is_marketing_outreach=False))
    target.is_marketing_outreach = True
    await db.commit()
    return {"status": "ok", "marketing_org": {"id": str(target.id), "name": target.name}}


@router.post("/marketing-org/ensure")
async def ensure_marketing_org(
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Designate the BetterCricket marketing org, creating a dedicated platform
    org if none exists yet. The outreach org is NOT a real cricket club — turning
    a club into it would co-mingle their audiences — so when nothing is designated
    we mint a dedicated 'BetterCricket' org and flag it. Idempotent: returns the
    existing one if already set."""
    existing = await get_outreach_org(db)
    if existing:
        return {"status": "ok", "created": False,
                "marketing_org": {"id": str(existing.id), "name": existing.name}}
    base = slug = "bettercricket-marketing"
    n = 1
    while await db.scalar(select(Organisation.id).where(Organisation.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    # Not a real club: a fresh uuid (never synced against Cricket Australia) and
    # is_active False so it stays off public club listings; the super admin reaches
    # it via this context bar / the club switcher, not a login.
    org = Organisation(id=uuid.uuid4(), name="BetterCricket Marketing", slug=slug,
                       is_active=False, is_marketing_outreach=True)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {"status": "ok", "created": True,
            "marketing_org": {"id": str(org.id), "name": org.name}}


# ─── Deliverability: suppression + event history (Phase 1) ───────────────────

@router.get("/suppressions")
async def list_suppressions(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Addresses on the global suppression list that are in THIS club's contacts —
    so a club sees which of its own people are blocked (hard bounce / complaint /
    manual) and why, without seeing other clubs' lists."""
    rows = (await db.execute(
        select(EmailSuppression.email, EmailSuppression.reason,
               EmailSuppression.detail, EmailSuppression.created_at)
        .where(exists().where(
            func.lower(CommsContact.email) == func.lower(EmailSuppression.email),
            CommsContact.organisation_id == club.id))
        .order_by(EmailSuppression.created_at.desc())
    )).all()
    return [{
        "email": r.email, "reason": r.reason, "detail": r.detail,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.delete("/suppressions")
async def delete_suppression(
    email: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Un-suppress an address (the member fixed their mailbox). Removes the global
    row and clears this club's per-contact bounced / complained flags so they can
    be emailed again."""
    e = _norm_email(email)
    if not e:
        raise HTTPException(status_code=422, detail="A valid email is required")
    removed = await suppress.remove_suppression(db, e)
    await db.execute(
        update(CommsContact)
        .where(CommsContact.organisation_id == club.id,
               func.lower(CommsContact.email) == e)
        .values(bounced=False, bounced_at=None, complained=False, complained_at=None))
    await db.commit()
    logger.info("BetterComms: un-suppressed %s for org %s (removed=%d)", e, club.id, removed)
    return {"status": "ok", "removed": removed}


@router.get("/merge-variables")
async def merge_variables(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The merge variables a template can use. The club/association/utm_code set
    only resolves for BetterCricket Clubs Directory contacts, so the editor flags
    them and we report whether we're in that context."""
    return {"is_marketing": org_is_outreach(club), "variables": MERGE_VARIABLES}


@router.get("/contacts/{contact_id}")
async def get_contact(
    contact_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """One contact's full detail, including the Clubs Directory fields it was
    exported with and the resolved value of every merge variable for this person —
    so you can see exactly what {{club}}, {{utm_code}} etc. will become."""
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid contact id")
    c = await db.get(CommsContact, cid)
    if not c or c.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    mc = await db.get(MarketingClub, c.marketing_club_id) if c.marketing_club_id else None
    mvars = _marketing_vars(mc)
    resolved = _resolved_vars(c, mc, club)
    keys = _context_var_keys(club)
    # The full org-context set, resolved (possibly blank) for THIS contact — shown
    # the same way no matter how the contact was added.
    variables = {k: resolved.get(k, "") for k in keys if k != "unsubscribe_url"}
    if "unsubscribe_url" in keys:
        variables["unsubscribe_url"] = "(unique per recipient, added automatically)"
    return {
        "id": str(c.id), "email": c.email, "name": c.name, "source": c.source,
        "subscribed": c.subscribed, "bounced": c.bounced,
        "complained": getattr(c, "complained", False), "excluded": c.excluded,
        "tags": c.tags or [],
        "marketing_club": ({
            "name": mc.name, "association": mvars.get("association", ""),
            "utm_code": mc.utm_code, "state": mc.state, "website": mc.website_url,
        } if mc else None),
        "variables": variables,
        # Which variables can be edited, and the raw per-contact override stored for
        # each (so the editor shows the override, not the resolved/derived value).
        "editable": [k for k in keys if k != "unsubscribe_url"],
        "overrides": {k: (c.merge_vars or {}).get(k, "") for k in EDITABLE_MERGE_KEYS},
    }


@router.get("/contacts/{contact_id}/events")
async def contact_events(
    contact_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Recent delivery events for one contact (delivered / bounce / complaint …)."""
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid contact id")
    contact = await db.get(CommsContact, cid)
    if not contact or contact.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    rows = (await db.execute(
        select(EmailEvent)
        .where(or_(EmailEvent.contact_id == cid,
                   func.lower(EmailEvent.email) == func.lower(contact.email)))
        .order_by(EmailEvent.created_at.desc())
        .limit(50)
    )).scalars().all()
    return [{
        "event_type": ev.event_type, "event_subtype": ev.event_subtype,
        "reason": ev.reason, "created_at": ev.created_at.isoformat() if ev.created_at else None,
    } for ev in rows]


# ─── Dynamic segments (Phase 2) ──────────────────────────────────────────────

def _segment_out(s: CommsSegment) -> dict:
    return {"id": str(s.id), "name": s.name, "definition": s.definition or {}}


@router.get("/segments")
async def list_segments(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(CommsSegment).where(CommsSegment.organisation_id == club.id)
        .order_by(CommsSegment.name)
    )).scalars().all()
    return [_segment_out(s) for s in rows]


class SegmentIn(BaseModel):
    name: str
    definition: dict = {}


@router.post("/segments")
async def create_segment(
    data: SegmentIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A segment name is required")
    seg = CommsSegment(organisation_id=club.id, name=name, definition=data.definition or {})
    db.add(seg)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A segment with that name already exists")
    await db.refresh(seg)
    return _segment_out(seg)


async def _segment_or_404(db: AsyncSession, club: Organisation, sid: str) -> CommsSegment:
    try:
        u = uuid.UUID(sid)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid segment id")
    s = await db.get(CommsSegment, u)
    if not s or s.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Segment not found")
    return s


@router.put("/segments/{segment_id}")
async def update_segment(
    segment_id: str,
    data: SegmentIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    seg = await _segment_or_404(db, club, segment_id)
    name = (data.name or "").strip()
    if name:
        seg.name = name
    seg.definition = data.definition or {}
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A segment with that name already exists")
    return _segment_out(seg)


@router.delete("/segments/{segment_id}")
async def delete_segment(
    segment_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    seg = await _segment_or_404(db, club, segment_id)
    await db.delete(seg)
    await db.commit()
    return {"status": "ok"}


@router.post("/segments/preview")
async def preview_segment(
    data: SegmentIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Live count for an unsaved definition (powers the segment builder)."""
    contacts = await comms_segments.resolve_contacts(db, club, data.definition or {})
    return {
        "count": len(contacts),
        "sample": [{"email": c.email, "name": c.name} for c in contacts[:8]],
    }


@router.post("/segments/resolve")
async def resolve_segment(
    data: SegmentIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The full matching audience for a definition, enriched with each contact's
    Clubs Directory fields — powers the searchable/filterable audience preview and
    its CSV export. Capped for safety; the count is exact."""
    contacts = await comms_segments.resolve_contacts(db, club, data.definition or {})
    rows = contacts[:5000]
    mc_map = await _mc_map(db, rows)
    return {
        "count": len(contacts),
        "contacts": [_contact_out(c, mc_map.get(c.marketing_club_id)) for c in rows],
    }


@router.get("/segments/{segment_id}/export.csv")
async def export_segment_csv(
    segment_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Download a saved segment's current audience as CSV — same columns as the
    Lists export. The segment re-evaluates on each download, so it always reflects
    who fits today."""
    seg = await _segment_or_404(db, club, segment_id)
    contacts = await comms_segments.resolve_contacts(db, club, seg.definition or {})
    mc_map = await _mc_map(db, contacts)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Email", "Club", "Association", "UTM code", "State",
                "Website", "Subscribed"])
    for c in contacts:
        d = _dir_fields(c, mc_map.get(c.marketing_club_id))
        w.writerow([
            c.name or "", c.email or "", d["club"], d["association"],
            d["utm_code"], d["state"], d["website"],
            "yes" if c.subscribed else "no",
        ])
    fname = f"{_csv_safe_filename(seg.name)}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/segments/options")
async def segment_options(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Option lists for the segment rule builder, so dropdowns use real values
    instead of guessed vocab. In the BetterCricket Clubs Directory context this
    returns the directory option lists (states, associations) and flags the
    builder to offer the directory field set instead of the club/player one."""
    if org_is_outreach(club):
        states = [s for (s,) in (await db.execute(
            select(MarketingClub.state)
            .join(CommsContact, CommsContact.marketing_club_id == MarketingClub.id)
            .where(CommsContact.organisation_id == club.id, MarketingClub.state.isnot(None))
            .distinct().order_by(MarketingClub.state)
        )).all() if s]
        assocs = [a for (a,) in (await db.execute(
            select(MarketingClub.association_name)
            .join(CommsContact, CommsContact.marketing_club_id == MarketingClub.id)
            .where(CommsContact.organisation_id == club.id, MarketingClub.association_name.isnot(None))
            .distinct().order_by(MarketingClub.association_name)
        )).all() if a]
        return {"context": "directory", "states": states, "associations": assocs}

    teams = (await db.execute(
        select(Team).where(Team.organisation_id == club.id, Team.is_active.is_(True))
        .order_by(Team.name)
    )).scalars().all()
    return {
        "context": "club",
        "roles": ["Batter", "Bowler", "All Rounder", "Wicketkeeper", "Wicketkeeper-Batter"],
        "genders": [["male", "Male"], ["female", "Female"]],
        "teams": [{"id": str(t.id), "name": t.name} for t in teams],
    }


# ─── Static lists (Phase 2) ──────────────────────────────────────────────────

async def _list_or_404(db: AsyncSession, club: Organisation, lid: str) -> CommsList:
    try:
        u = uuid.UUID(lid)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid list id")
    lst = await db.get(CommsList, u)
    if not lst or lst.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="List not found")
    return lst


async def _list_count(db: AsyncSession, list_id) -> int:
    return int((await db.execute(
        select(func.count(CommsListMember.id)).where(CommsListMember.list_id == list_id)
    )).scalar_one() or 0)


@router.get("/lists")
async def list_lists(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(CommsList).where(CommsList.organisation_id == club.id).order_by(CommsList.name)
    )).scalars().all()
    out = []
    for l in rows:
        out.append({"id": str(l.id), "name": l.name, "count": await _list_count(db, l.id)})
    return out


class ListIn(BaseModel):
    name: str


@router.post("/lists")
async def create_list(
    data: ListIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A list name is required")
    lst = CommsList(organisation_id=club.id, name=name)
    db.add(lst)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A list with that name already exists")
    await db.refresh(lst)
    return {"id": str(lst.id), "name": lst.name, "count": 0}


@router.put("/lists/{list_id}")
async def rename_list(
    list_id: str,
    data: ListIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    lst = await _list_or_404(db, club, list_id)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A list name is required")
    lst.name = name
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A list with that name already exists")
    return {"id": str(lst.id), "name": lst.name, "count": await _list_count(db, lst.id)}


@router.delete("/lists/{list_id}")
async def delete_list(
    list_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    lst = await _list_or_404(db, club, list_id)
    await db.delete(lst)
    await db.commit()
    return {"status": "ok"}


@router.get("/lists/{list_id}/members")
async def list_members(
    list_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _list_or_404(db, club, list_id)
    rows = (await db.execute(
        select(CommsContact)
        .join(CommsListMember, CommsListMember.contact_id == CommsContact.id)
        .where(CommsListMember.list_id == uuid.UUID(list_id))
        .order_by(CommsContact.email)
    )).scalars().all()
    mc_map = await _mc_map(db, rows)
    return [_contact_out(c, mc_map.get(c.marketing_club_id)) for c in rows]


def _csv_safe_filename(name: str) -> str:
    """A tame ASCII filename for the Content-Disposition header."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "list").strip()).strip("-")
    return (slug or "list").lower()


@router.get("/lists/{list_id}/export.csv")
async def export_list_csv(
    list_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Download a list's contacts as CSV — one row per member, with the contact's
    own fields plus the Clubs Directory fields it resolves to."""
    lst = await _list_or_404(db, club, list_id)
    rows = (await db.execute(
        select(CommsContact)
        .join(CommsListMember, CommsListMember.contact_id == CommsContact.id)
        .where(CommsListMember.list_id == lst.id)
        .order_by(CommsContact.name.nullslast(), CommsContact.email)
    )).scalars().all()
    mc_map = await _mc_map(db, rows)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Email", "Club", "Association", "UTM code", "State",
                "Website", "Subscribed"])
    for c in rows:
        d = _dir_fields(c, mc_map.get(c.marketing_club_id))
        w.writerow([
            c.name or "", c.email or "", d["club"], d["association"],
            d["utm_code"], d["state"], d["website"],
            "yes" if c.subscribed else "no",
        ])
    fname = f"{_csv_safe_filename(lst.name)}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


class ListMembersIn(BaseModel):
    contact_ids: list[str] = []


@router.post("/lists/{list_id}/members")
async def add_list_members(
    list_id: str,
    data: ListMembersIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    lst = await _list_or_404(db, club, list_id)
    added = 0
    for raw in (data.contact_ids or []):
        try:
            cid = uuid.UUID(str(raw))
        except (ValueError, TypeError):
            continue
        # Only the club's own contacts can join the list.
        contact = await db.get(CommsContact, cid)
        if not contact or contact.organisation_id != club.id:
            continue
        exists_row = await db.scalar(select(CommsListMember.id).where(
            CommsListMember.list_id == lst.id, CommsListMember.contact_id == cid))
        if exists_row:
            continue
        db.add(CommsListMember(list_id=lst.id, contact_id=cid))
        added += 1
    await db.commit()
    return {"added": added, "count": await _list_count(db, lst.id)}


@router.delete("/lists/{list_id}/members/{contact_id}")
async def remove_list_member(
    list_id: str,
    contact_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    lst = await _list_or_404(db, club, list_id)
    try:
        cid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid contact id")
    await db.execute(
        CommsListMember.__table__.delete().where(
            CommsListMember.list_id == lst.id, CommsListMember.contact_id == cid))
    await db.commit()
    return {"status": "ok", "count": await _list_count(db, lst.id)}


def _uuid_set(raw_ids) -> set:
    out = set()
    for raw in (raw_ids or []):
        try:
            out.add(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    return out


@router.post("/lists/{list_id}/members/remove")
async def remove_list_members(
    list_id: str,
    data: ListMembersIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Remove several contacts from a list in one call (group remove)."""
    lst = await _list_or_404(db, club, list_id)
    cids = _uuid_set(data.contact_ids)
    removed = 0
    if cids:
        res = await db.execute(
            CommsListMember.__table__.delete().where(
                CommsListMember.list_id == lst.id,
                CommsListMember.contact_id.in_(cids)))
        removed = res.rowcount or 0
        await db.commit()
    return {"status": "ok", "removed": removed, "count": await _list_count(db, lst.id)}


class CopyMembersIn(BaseModel):
    contact_ids: list[str] = []
    list_ids: list[str] = []


@router.post("/lists/members/copy")
async def copy_list_members(
    data: CopyMembersIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Copy a set of contacts into one or more target lists (group copy). Only the
    club's own contacts and lists are touched; existing memberships are left alone."""
    cids = _uuid_set(data.contact_ids)
    target_ids = _uuid_set(data.list_ids)
    if not cids or not target_ids:
        return {"results": []}
    # Keep only contacts that belong to this club.
    valid_cids = set((await db.execute(
        select(CommsContact.id).where(
            CommsContact.organisation_id == club.id, CommsContact.id.in_(cids))
    )).scalars().all())
    results = []
    for lid in target_ids:
        lst = await db.get(CommsList, lid)
        if not lst or lst.organisation_id != club.id:
            continue
        existing = set((await db.execute(
            select(CommsListMember.contact_id).where(
                CommsListMember.list_id == lst.id,
                CommsListMember.contact_id.in_(valid_cids))
        )).scalars().all())
        added = 0
        for cid in valid_cids:
            if cid in existing:
                continue
            db.add(CommsListMember(list_id=lst.id, contact_id=cid))
            added += 1
        await db.commit()
        results.append({"list_id": str(lst.id), "name": lst.name,
                        "added": added, "count": await _list_count(db, lst.id)})
    return {"results": results}


# ─── Email templates (Phase 3) ───────────────────────────────────────────────

def _template_out(t: CommsTemplate, *, full: bool = False) -> dict:
    d = {"id": str(t.id), "name": t.name,
         "updated_at": t.updated_at.isoformat() if t.updated_at else None}
    if full:
        d["html"] = t.html or ""
    return d


@router.get("/templates")
async def list_templates(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(CommsTemplate).where(CommsTemplate.organisation_id == club.id)
        .order_by(CommsTemplate.name)
    )).scalars().all()
    return [_template_out(t) for t in rows]


class TemplateIn(BaseModel):
    name: str
    html: str = ""


@router.post("/templates")
async def create_template(
    data: TemplateIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A template name is required")
    t = CommsTemplate(organisation_id=club.id, name=name, html=data.html or "")
    db.add(t)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A template with that name already exists")
    await db.refresh(t)
    return _template_out(t, full=True)


async def _template_or_404(db: AsyncSession, club: Organisation, tid: str) -> CommsTemplate:
    try:
        u = uuid.UUID(tid)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid template id")
    t = await db.get(CommsTemplate, u)
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return _template_out(await _template_or_404(db, club, template_id), full=True)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    data: TemplateIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    t = await _template_or_404(db, club, template_id)
    name = (data.name or "").strip()
    if name:
        t.name = name
    t.html = data.html or ""
    t.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A template with that name already exists")
    return _template_out(t, full=True)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    t = await _template_or_404(db, club, template_id)
    await db.delete(t)
    await db.commit()
    return {"status": "ok"}


class TemplatePreview(BaseModel):
    html: str = ""
    utm: Optional[dict] = None


@router.post("/templates/preview")
async def preview_template(
    data: TemplatePreview,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Render a template the way a real send would (sample recipient, mandatory
    footer injected), so the editor can show a true preview."""
    _, _, _, footer = _sender(club)
    unsub = _unsub_url(_unsub_token(club.id, uuid.uuid4()))
    sample = ({"club": "Sample Cricket Club", "association": "Sample Association",
               "utm_code": "sample-cricket-club", "state": "WA",
               "website": "https://example.com"} if org_is_outreach(club) else None)
    _, html, _ = _render_parts(
        club, subject="", body_html=data.html or "", utm=data.utm or {},
        email="sample@example.com", name="Sam Example", unsub_url=unsub, footer=footer,
        extra_vars=sample)
    return {"html": html}
