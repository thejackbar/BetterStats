"""Create a BetterComms List from a set of CRM Sales Pipeline deals.

The super-admin CRM board/list can turn its current filtered result set into an
auto-generated BetterComms List (source='auto', origin='CRM Sales Pipeline'),
one contact per deal. This module resolves each deal to an emailable contact and
matches it against the marketing-outreach org's existing BetterComms contacts.

Contact resolution per deal, in priority order:
  1. The deal's own designated point of contact (CrmPerson via CrmDealContact),
     when it carries a valid email — the "Contact Name recorded on the Deal
     card" case.
  2. Otherwise the linked Clubs Directory club's office bearers, by role:
     President → Secretary → Treasurer.
  3. Otherwise any other club contact that has an email (e.g. the generic
     "Club contact" mailbox).
  4. Otherwise the club's own default ``contact_email`` (no name attached).

A resolved email that already exists as a BetterComms contact is matched and
added straight to the list. One that doesn't (or a deal with no resolvable
email) is returned as "unmatched" for the operator to resolve in a modal —
pick one of the club's email-bearing contacts, or type a first/last/email by
hand. Those become new BetterComms contacts (linked to the directory club so
utm_code / club / association / state / website resolve automatically, plus a
per-recipient unsubscribe link at send time) and are added to the list.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, CommsList, CommsListMember, CrmDeal, CrmDealContact, CrmPerson,
    MarketingClub, MarketingClubContact, Organisation,
)
from app.services.marketing_org import get_outreach_org

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Office-bearer roles, in the fallback order the spec asks for. MarketingClubContact
# stores the role as a free-text label ("President", "Secretary", "Treasurer",
# "Vice President", "Club contact", …) — see services/club_directory.py.
_ROLE_PRIORITY = ("president", "secretary", "treasurer")
ORIGIN_LABEL = "CRM Sales Pipeline"


def norm_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL_RE.match(e) else None


def _role_key(role: Optional[str]) -> str:
    return (role or "").strip().lower()


def _resolve_from_club_contacts(contacts: list[MarketingClubContact],
                                club: Optional[MarketingClub]) -> tuple[Optional[str], Optional[str]]:
    """(name, email) for a club, by office-bearer priority then any emailed
    contact then the club's own default email. Returns (None, None) if nothing
    emailable is available."""
    with_email = [c for c in contacts if norm_email(c.email)]
    # President → Secretary → Treasurer (exact role, else role starts with it —
    # tolerates "President (Senior)" style labels).
    for want in _ROLE_PRIORITY:
        for c in with_email:
            rk = _role_key(c.role)
            if rk == want or rk.startswith(want):
                return (c.full_name or None), norm_email(c.email)
    # Any other emailed contact (e.g. the generic "Club contact" mailbox). Prefer
    # the lowest role_rank (office bearers already handled above, so this is the
    # next-best generic contact).
    if with_email:
        best = sorted(with_email, key=lambda c: (c.role_rank if c.role_rank is not None else 99))[0]
        return (best.full_name or None), norm_email(best.email)
    # The club's own mirrored default email (no name attached).
    if club is not None:
        ce = norm_email(getattr(club, "contact_email", None))
        if ce:
            return None, ce
    return None, None


def _club_contact_options(contacts: list[MarketingClubContact]) -> list[dict]:
    """The club's emailed contacts for the resolution dropdown — deduped by
    email, office bearers first."""
    seen: set[str] = set()
    out: list[dict] = []
    for c in sorted(contacts, key=lambda c: (c.role_rank if c.role_rank is not None else 99,
                                             (c.full_name or "").lower())):
        e = norm_email(c.email)
        if not e or e in seen:
            continue
        seen.add(e)
        out.append({"name": c.full_name or "", "email": e, "role": c.role or ""})
    return out


async def _poc_by_deal(session: AsyncSession, deal_ids) -> dict:
    """deal_id -> (full_name, email) of its designated point of contact, batched."""
    ids = [d for d in deal_ids]
    if not ids:
        return {}
    from app.services.crm import POINT_OF_CONTACT_ROLE
    rows = (await session.execute(
        select(CrmDealContact.deal_id, CrmPerson.full_name, CrmPerson.email)
        .join(CrmPerson, CrmPerson.id == CrmDealContact.person_id)
        .where(CrmDealContact.deal_id.in_(ids),
               CrmDealContact.role_on_deal == POINT_OF_CONTACT_ROLE)
    )).all()
    return {deal_id: (name, email) for deal_id, name, email in rows}


async def prepare_list_from_deals(session: AsyncSession, deal_ids: list[str]) -> dict:
    """Resolve every deal to a contact and split into matched (an existing
    BetterComms contact) vs unmatched (needs the operator to resolve)."""
    outreach = await get_outreach_org(session)
    if outreach is None:
        return {"error": "no_outreach_org",
                "detail": "Designate a BetterCricket marketing org in BetterComms first."}

    uids: list[uuid.UUID] = []
    for raw in (deal_ids or []):
        try:
            uids.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    if not uids:
        return {"error": "no_deals", "detail": "No deals were provided."}

    deals = (await session.execute(
        select(CrmDeal).where(CrmDeal.id.in_(uids))
    )).scalars().all()

    club_ids = {d.marketing_club_id for d in deals if d.marketing_club_id}
    clubs: dict = {}
    contacts_by_club: dict = {}
    if club_ids:
        clubs = {c.id: c for c in (await session.execute(
            select(MarketingClub).where(MarketingClub.id.in_(club_ids)))).scalars().all()}
        rows = (await session.execute(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id.in_(club_ids)))).scalars().all()
        for c in rows:
            contacts_by_club.setdefault(c.marketing_club_id, []).append(c)

    poc = await _poc_by_deal(session, [d.id for d in deals])

    # Existing BetterComms contacts in the outreach org, keyed by email — so the
    # match check is one query, not one per deal.
    existing = {c.email: c for c in (await session.execute(
        select(CommsContact).where(CommsContact.organisation_id == outreach.id))).scalars().all()}

    matched: list[dict] = []
    unmatched: list[dict] = []
    seen_matched: set[uuid.UUID] = set()

    for d in deals:
        club = clubs.get(d.marketing_club_id) if d.marketing_club_id else None
        club_contacts = contacts_by_club.get(d.marketing_club_id, []) if d.marketing_club_id else []
        club_name = (club.name if club else None) or d.title or "—"

        # 1. deal's own point of contact (only when it carries a usable email)
        name, email = None, None
        p = poc.get(d.id)
        if p and norm_email(p[1]):
            name, email = (p[0] or None), norm_email(p[1])
        else:
            name, email = _resolve_from_club_contacts(club_contacts, club)

        hit = existing.get(email) if email else None
        if hit is not None:
            if hit.id not in seen_matched:
                seen_matched.add(hit.id)
                matched.append({
                    "deal_id": str(d.id), "club_name": club_name,
                    "contact_id": str(hit.id),
                    "contact_name": hit.name or (hit.merge_vars or {}).get("first_name") or "",
                    "contact_email": hit.email,
                })
            continue

        unmatched.append({
            "deal_id": str(d.id),
            "club_id": str(d.marketing_club_id) if d.marketing_club_id else None,
            "club_name": club_name,
            # Pre-selected suggestion for the dropdown, if we resolved one.
            "suggested": ({"name": name or "", "email": email} if email else None),
            "club_contacts": _club_contact_options(club_contacts),
            "utm_code": (club.utm_code if club else "") or "",
            "association": (club.association_name if club else "") or "",
            "state": (club.state if club else "") or "",
            "website": (club.website_url if club else "") or "",
        })

    return {
        "outreach_org_id": str(outreach.id),
        "outreach_org_name": outreach.name,
        "total_deals": len(deals),
        "matched": matched,
        "unmatched": unmatched,
    }


async def _unique_list_name(session: AsyncSession, org_id, base: str) -> str:
    base = (base or "").strip() or "CRM list"
    existing = set((await session.execute(
        select(CommsList.name).where(CommsList.organisation_id == org_id))).scalars().all())
    if base not in existing:
        return base
    for n in range(2, 1000):
        cand = f"{base} ({n})"
        if cand not in existing:
            return cand
    return f"{base} ({uuid.uuid4().hex[:6]})"


async def commit_list_from_deals(session: AsyncSession, *, name: str,
                                 matched_contact_ids: list[str],
                                 resolutions: list[dict]) -> dict:
    """Create the auto list and populate it. ``matched_contact_ids`` are existing
    BetterComms contacts to add as-is; ``resolutions`` are the modal's chosen
    contacts ({club_id?, email, first_name?, last_name?, name?}) — each is
    upserted into BetterComms (linked to the directory club) and added."""
    outreach = await get_outreach_org(session)
    if outreach is None:
        return {"error": "no_outreach_org",
                "detail": "Designate a BetterCricket marketing org in BetterComms first."}

    final_name = await _unique_list_name(session, outreach.id, name)
    lst = CommsList(organisation_id=outreach.id, name=final_name,
                    source="auto", origin=ORIGIN_LABEL)
    session.add(lst)
    await session.flush()  # need lst.id for the membership rows

    # Existing outreach contacts by email, so a resolution email that already
    # exists reuses that row rather than colliding on the (org, email) unique.
    existing = {c.email: c for c in (await session.execute(
        select(CommsContact).where(CommsContact.organisation_id == outreach.id))).scalars().all()}

    contact_ids: set[uuid.UUID] = set()
    created = 0
    skipped: list[str] = []

    # 1. Existing contacts matched during prepare.
    valid_ids: set[uuid.UUID] = set()
    for raw in (matched_contact_ids or []):
        try:
            valid_ids.add(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            continue
    if valid_ids:
        rows = (await session.execute(
            select(CommsContact.id).where(
                CommsContact.organisation_id == outreach.id,
                CommsContact.id.in_(valid_ids)))).scalars().all()
        contact_ids |= set(rows)

    # 2. Operator-resolved contacts (dropdown pick or hand-typed).
    for r in (resolutions or []):
        email = norm_email(r.get("email"))
        if not email:
            skipped.append(r.get("email") or "")
            continue
        club_id = None
        raw_club = r.get("club_id")
        if raw_club:
            try:
                club_id = uuid.UUID(str(raw_club))
            except (ValueError, TypeError):
                club_id = None
        first = (r.get("first_name") or "").strip()
        last = (r.get("last_name") or "").strip()
        full = (r.get("name") or "").strip() or " ".join(x for x in (first, last) if x).strip() or None

        existing_c = existing.get(email)
        if existing_c is not None:
            # Fill in only what's missing — never clobber, never resurrect a
            # suppressed address (subscribed is left untouched).
            if full and not existing_c.name:
                existing_c.name = full
            if club_id and not existing_c.marketing_club_id:
                existing_c.marketing_club_id = club_id
            if first:
                mv = dict(existing_c.merge_vars or {})
                mv.setdefault("first_name", first)
                existing_c.merge_vars = mv
            contact_ids.add(existing_c.id)
            continue

        c = CommsContact(
            organisation_id=outreach.id, email=email, name=full, source="manual",
            marketing_club_id=club_id,
            merge_vars=({"first_name": first} if first else {}),
        )
        session.add(c)
        await session.flush()
        existing[email] = c
        contact_ids.add(c.id)
        created += 1

    # 3. Membership rows — skip any already-present (defensive; a fresh list has
    # none, but keeps the op idempotent on re-commit).
    added = 0
    if contact_ids:
        already = set((await session.execute(
            select(CommsListMember.contact_id).where(
                CommsListMember.list_id == lst.id))).scalars().all())
        for cid in contact_ids:
            if cid in already:
                continue
            session.add(CommsListMember(list_id=lst.id, contact_id=cid))
            added += 1

    await session.commit()
    return {
        "list_id": str(lst.id),
        "name": final_name,
        "added": added,
        "created_contacts": created,
        "skipped": [s for s in skipped if s],
    }
