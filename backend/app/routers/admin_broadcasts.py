"""Super-admin messages shown on the club admin dashboard (migration 312).

A super admin writes one line of text and decides three things about it:

  * WHO sees it — every club, a chosen set of clubs, or chosen users. For the
    first two it can be narrowed to Club Admins only, or the Primary Club Admin
    only; by default it reaches everybody who uses the admin app at the club
    (``club_admin`` and ``club_member``). Archived clubs are never reached.
  * WHEN — it starts now or at a set time, and may stop at a set time.
  * WHAT MAKES IT GO AWAY — a super admin clearing it (``until_cleared``), each
    recipient dismissing it (``dismissible``), each recipient seeing it once
    (``view_once_user``), or anybody at the club seeing it once
    (``view_once_club``). An expiry applies on top of any of the four, and a
    super admin can always clear any message.

The message is drawn only on the club admin dashboard. The rules are applied
here, on read, so the screen never decides who sees what.

SUPER ADMINS AND SALES STAFF SEE A PREVIEW AND LEAVE NO TRACE. Acting as a club,
they see what that club's admins see (every live message aimed at it, whatever
has been dismissed), and they never write a receipt: a staff member glancing at
a club must not use up that club's view-once message.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, Organisation, User, get_db
from app.routers.auth import get_current_club, get_current_user, require_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin", tags=["admin-broadcasts"])

TONES = ("info", "success", "warning", "critical")
AUDIENCES = ("all", "clubs", "users")
AUDIENCE_ROLES = ("all_admins", "club_admins", "primary")
PERSISTENCE = ("until_cleared", "dismissible", "view_once_user", "view_once_club")
RECIPIENT_ROLES = ("club_admin", "club_member")
STAFF_ROLES = ("super_admin", "sales")

MAX_MESSAGE = 500
MAX_LINK_LABEL = 60
MAX_LINK_URL = 1000
MAX_SHOWN = 10

# Most urgent first, then newest. Drives the dashboard's stacking order.
_TONE_ORDER_SQL = (
    "CASE b.tone WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 "
    "WHEN 'info' THEN 2 ELSE 3 END"
)

_LINK_RE = re.compile(r"^(https?://[^\s]+|/[^\s]*)$", re.IGNORECASE)

_COLS = """
    b.id, b.message, b.tone, b.link_url, b.link_label, b.audience,
    b.audience_roles, b.org_ids, b.user_ids, b.persistence, b.starts_at,
    b.expires_at, b.cleared_at, b.created_at, b.updated_at,
    b.created_by_user_id
"""

# A message is live between its start and its expiry, unless cleared.
_LIVE_SQL = (
    "b.cleared_at IS NULL AND b.starts_at <= NOW() "
    "AND (b.expires_at IS NULL OR b.expires_at > NOW())"
)


# ── helpers ────────────────────────────────────────────────────────────────

def _iso(dt):
    return dt.isoformat() if dt else None


def _aware(dt: datetime | None) -> datetime | None:
    """A naive timestamp from a caller is read as UTC rather than refused."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _uuid_list(values, what: str) -> list[str]:
    out: list[str] = []
    for v in values or []:
        try:
            s = str(uuid.UUID(str(v)))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, f"{what} contains an id that is not valid")
        if s not in out:
            out.append(s)
    return out


def _status(row, now: datetime) -> str:
    if row["cleared_at"] is not None:
        return "cleared"
    if row["expires_at"] is not None and row["expires_at"] <= now:
        return "expired"
    if row["starts_at"] > now:
        return "scheduled"
    return "live"


def _public(row, *, preview: bool = False) -> dict:
    """The shape the dashboard draws. Carries nothing about the audience beyond
    what a preview needs to say who it is for."""
    out = {
        "id": str(row["id"]),
        "message": row["message"],
        "tone": row["tone"],
        "link_url": row["link_url"],
        "link_label": row["link_label"],
        "persistence": row["persistence"],
        "dismissible": row["persistence"] != "until_cleared",
        "starts_at": _iso(row["starts_at"]),
        "expires_at": _iso(row["expires_at"]),
    }
    if preview:
        out["preview"] = True
        out["audience"] = row["audience"]
        out["audience_roles"] = row["audience_roles"]
    return out


async def _membership(db: AsyncSession, user: User) -> ClubMembership | None:
    return (await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )).scalar_one_or_none()


async def visible_broadcasts(
    db: AsyncSession, user: User, club: Organisation, membership: ClubMembership | None,
) -> tuple[list[dict], bool]:
    """(messages, is_preview) for this user on this club's dashboard."""
    role = membership.role if membership else None
    org_id = str(club.id)

    if role in STAFF_ROLES:
        # Everything live aimed at this club, however it was aimed: at every
        # club, at this one, or at a named user who belongs to it.
        rows = (await db.execute(text(f"""
            SELECT {_COLS} FROM admin_broadcasts b
            WHERE {_LIVE_SQL}
              AND (
                    b.audience = 'all'
                 OR (b.audience = 'clubs' AND CAST(:org AS uuid) = ANY(b.org_ids))
                 OR (b.audience = 'users' AND EXISTS (
                        SELECT 1 FROM club_memberships cm
                        WHERE cm.club_id = CAST(:org AS uuid)
                          AND cm.user_id = ANY(b.user_ids)))
              )
            ORDER BY {_TONE_ORDER_SQL}, b.starts_at DESC
            LIMIT :lim
        """), {"org": org_id, "lim": MAX_SHOWN})).mappings().all()
        return [_public(r, preview=True) for r in rows], True

    if role not in RECIPIENT_ROLES:
        return [], False

    is_primary = bool(getattr(membership, "is_primary_admin", False))
    rows = (await db.execute(text(f"""
        SELECT {_COLS} FROM admin_broadcasts b
        WHERE {_LIVE_SQL}
          AND (
                (
                    (b.audience = 'all'
                     OR (b.audience = 'clubs' AND CAST(:org AS uuid) = ANY(b.org_ids)))
                    AND (
                           b.audience_roles = 'all_admins'
                        OR (b.audience_roles = 'club_admins' AND :role = 'club_admin')
                        OR (b.audience_roles = 'primary' AND :role = 'club_admin' AND :primary)
                    )
                )
             OR (b.audience = 'users' AND CAST(:uid AS uuid) = ANY(b.user_ids))
          )
          AND NOT EXISTS (
                SELECT 1 FROM admin_broadcast_receipts r
                WHERE r.broadcast_id = b.id AND r.user_id = CAST(:uid AS uuid)
                  AND (
                        -- seen once is enough for a view-once-each message
                        b.persistence = 'view_once_user'
                        -- and a dismissal ends it for this user on anything
                        -- a recipient is allowed to dismiss
                     OR (b.persistence <> 'until_cleared' AND r.dismissed_at IS NOT NULL)
                  )
          )
          AND NOT (
                b.persistence = 'view_once_club' AND EXISTS (
                    SELECT 1 FROM admin_broadcast_receipts r
                    WHERE r.broadcast_id = b.id
                      AND r.organisation_id = CAST(:org AS uuid))
          )
        ORDER BY {_TONE_ORDER_SQL}, b.starts_at DESC
        LIMIT :lim
    """), {
        "org": org_id, "uid": str(user.id), "role": role,
        "primary": is_primary, "lim": MAX_SHOWN,
    })).mappings().all()
    return [_public(r) for r in rows], False


# ── the club admin's dashboard ─────────────────────────────────────────────

@router.get("/broadcasts")
async def my_broadcasts(
    user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    membership = await _membership(db, user)
    items, preview = await visible_broadcasts(db, user, club, membership)
    return {"items": items, "preview": preview}


class SeenBody(BaseModel):
    ids: list[str] = []


@router.post("/broadcasts/seen")
async def mark_seen(
    body: SeenBody,
    user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Records that this user's dashboard showed these messages. Only messages
    the user can actually see right now are recorded, so an id off a browser
    cannot plant a receipt, and a staff preview records nothing."""
    membership = await _membership(db, user)
    if not membership or membership.role not in RECIPIENT_ROLES:
        return {"recorded": 0}
    wanted = set(_uuid_list(body.ids[:MAX_SHOWN * 2], "ids"))
    if not wanted:
        return {"recorded": 0}
    items, _ = await visible_broadcasts(db, user, club, membership)
    ids = [i["id"] for i in items if i["id"] in wanted]
    for bid in ids:
        await db.execute(text("""
            INSERT INTO admin_broadcast_receipts (broadcast_id, user_id, organisation_id)
            VALUES (CAST(:b AS uuid), CAST(:u AS uuid), CAST(:o AS uuid))
            ON CONFLICT (broadcast_id, user_id) DO NOTHING
        """), {"b": bid, "u": str(user.id), "o": str(club.id)})
    await db.commit()
    return {"recorded": len(ids)}


@router.post("/broadcasts/{broadcast_id}/dismiss")
async def dismiss(
    broadcast_id: str,
    user: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    bid = _uuid_list([broadcast_id], "id")[0]
    membership = await _membership(db, user)
    if not membership or membership.role not in RECIPIENT_ROLES:
        # A preview is hidden on the screen alone; there is nothing to store.
        return {"dismissed": False, "preview": True}
    items, _ = await visible_broadcasts(db, user, club, membership)
    item = next((i for i in items if i["id"] == bid), None)
    if item is None:
        raise HTTPException(404, "Message not found")
    if not item["dismissible"]:
        raise HTTPException(409, "This message stays until BetterCricket removes it.")
    await db.execute(text("""
        INSERT INTO admin_broadcast_receipts
            (broadcast_id, user_id, organisation_id, dismissed_at)
        VALUES (CAST(:b AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), NOW())
        ON CONFLICT (broadcast_id, user_id)
        DO UPDATE SET dismissed_at = COALESCE(admin_broadcast_receipts.dismissed_at, NOW())
    """), {"b": bid, "u": str(user.id), "o": str(club.id)})
    await db.commit()
    return {"dismissed": True}


# ── the super admin's side ─────────────────────────────────────────────────

class BroadcastIn(BaseModel):
    message: str | None = None
    tone: str | None = None
    link_url: str | None = None
    link_label: str | None = None
    audience: str | None = None
    audience_roles: str | None = None
    org_ids: list[str] | None = None
    user_ids: list[str] | None = None
    persistence: str | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None


async def _eligible_recipients(db: AsyncSession) -> list[dict]:
    """Every user a message could reach: admin-app users at a club that is not
    archived. Small (one row per club admin on the platform), so each message's
    reach is worked out from it in Python rather than per message in SQL."""
    rows = (await db.execute(text("""
        SELECT cm.user_id, cm.club_id, cm.role, cm.is_primary_admin,
               u.display_name, u.username, u.email, o.name AS club_name
        FROM club_memberships cm
        JOIN organisations o ON o.id = cm.club_id
        JOIN users u ON u.id = cm.user_id
        WHERE cm.role IN ('club_admin', 'club_member')
          AND o.archived_at IS NULL
    """))).mappings().all()
    return [dict(r) for r in rows]


def _reaches(row, rec: dict) -> bool:
    audience = row["audience"]
    if audience == "users":
        return str(rec["user_id"]) in {str(u) for u in (row["user_ids"] or [])}
    if audience == "clubs" and str(rec["club_id"]) not in {str(o) for o in (row["org_ids"] or [])}:
        return False
    roles = row["audience_roles"]
    if roles == "club_admins":
        return rec["role"] == "club_admin"
    if roles == "primary":
        return rec["role"] == "club_admin" and bool(rec["is_primary_admin"])
    return True


async def _validate(db: AsyncSession, data: dict) -> dict:
    message = (data.get("message") or "").strip()
    message = re.sub(r"\s+", " ", message)
    if not message:
        raise HTTPException(422, "Write a message")
    if len(message) > MAX_MESSAGE:
        raise HTTPException(422, f"Keep the message to {MAX_MESSAGE} characters")
    data["message"] = message

    if data.get("tone") not in TONES:
        raise HTTPException(422, "Unknown tone")
    if data.get("audience") not in AUDIENCES:
        raise HTTPException(422, "Unknown audience")
    if data.get("audience_roles") not in AUDIENCE_ROLES:
        raise HTTPException(422, "Unknown recipient group")
    if data.get("persistence") not in PERSISTENCE:
        raise HTTPException(422, "Unknown rule for when the message goes away")

    link_url = (data.get("link_url") or "").strip() or None
    link_label = (data.get("link_label") or "").strip() or None
    if link_url:
        if len(link_url) > MAX_LINK_URL or not _LINK_RE.match(link_url):
            raise HTTPException(422, "A link must start with https:// or with / for a page in the app")
    elif link_label:
        raise HTTPException(422, "Add the link the button should open, or remove its label")
    if link_label and len(link_label) > MAX_LINK_LABEL:
        raise HTTPException(422, f"Keep the link label to {MAX_LINK_LABEL} characters")
    data["link_url"], data["link_label"] = link_url, link_label

    org_ids = _uuid_list(data.get("org_ids"), "Clubs")
    user_ids = _uuid_list(data.get("user_ids"), "Users")
    if data["audience"] == "clubs":
        if not org_ids:
            raise HTTPException(422, "Pick at least one club")
        found = {str(r[0]) for r in (await db.execute(text("""
            SELECT id FROM organisations
            WHERE id = ANY(CAST(:ids AS uuid[])) AND archived_at IS NULL
        """), {"ids": org_ids})).all()}
        if len(found) != len(org_ids):
            raise HTTPException(422, "One of the chosen clubs no longer exists or is archived")
        user_ids = []
    elif data["audience"] == "users":
        if not user_ids:
            raise HTTPException(422, "Pick at least one user")
        found = {str(r[0]) for r in (await db.execute(text("""
            SELECT cm.user_id FROM club_memberships cm
            JOIN organisations o ON o.id = cm.club_id
            WHERE cm.user_id = ANY(CAST(:ids AS uuid[]))
              AND cm.role IN ('club_admin', 'club_member')
              AND o.archived_at IS NULL
        """), {"ids": user_ids})).all()}
        if len(found) != len(user_ids):
            raise HTTPException(422, "One of the chosen users is not a club admin any more")
        org_ids = []
        # A named list of people is not narrowed further by role.
        data["audience_roles"] = "all_admins"
    else:
        org_ids, user_ids = [], []
    data["org_ids"], data["user_ids"] = org_ids, user_ids

    starts = _aware(data.get("starts_at")) or datetime.now(timezone.utc)
    expires = _aware(data.get("expires_at"))
    if expires is not None and expires <= starts:
        raise HTTPException(422, "The message must stop after it starts")
    data["starts_at"], data["expires_at"] = starts, expires
    return data


async def _serialise_all(db: AsyncSession, rows) -> list[dict]:
    if not rows:
        return []
    now = datetime.now(timezone.utc)
    eligible = await _eligible_recipients(db)
    ids = [str(r["id"]) for r in rows]
    receipts = {str(r["broadcast_id"]): r for r in (await db.execute(text("""
        SELECT broadcast_id,
               COUNT(*) AS seen,
               COUNT(dismissed_at) AS dismissed,
               COUNT(DISTINCT organisation_id) AS clubs_seen
        FROM admin_broadcast_receipts
        WHERE broadcast_id = ANY(CAST(:ids AS uuid[]))
        GROUP BY broadcast_id
    """), {"ids": ids})).mappings().all()}
    creators = {}
    creator_ids = list({str(r["created_by_user_id"]) for r in rows if r["created_by_user_id"]})
    if creator_ids:
        creators = {str(r[0]): (r[1] or r[2]) for r in (await db.execute(text(
            "SELECT id, display_name, username FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": creator_ids})).all()}
    clubs_by_id = {}
    org_ids = {str(o) for r in rows for o in (r["org_ids"] or [])}
    if org_ids:
        clubs_by_id = {str(r[0]): r[1] for r in (await db.execute(text(
            "SELECT id, name FROM organisations WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": list(org_ids)})).all()}
    names_by_user = {str(e["user_id"]): (e["display_name"] or e["username"]) for e in eligible}

    out = []
    for r in rows:
        reached = [e for e in eligible if _reaches(r, e)]
        rc = receipts.get(str(r["id"]))
        seen = int(rc["seen"]) if rc else 0
        dismissed = int(rc["dismissed"]) if rc else 0
        clubs_seen = int(rc["clubs_seen"]) if rc else 0
        recipients = len(reached)
        clubs = len({str(e["club_id"]) for e in reached})
        status = _status(r, now)
        if status == "live" and recipients:
            p = r["persistence"]
            if ((p == "view_once_user" and seen >= recipients)
                    or (p == "dismissible" and dismissed >= recipients)
                    or (p == "view_once_club" and clubs_seen >= clubs)):
                status = "complete"
        out.append({
            **_public(r),
            "audience": r["audience"],
            "audience_roles": r["audience_roles"],
            "org_ids": [str(o) for o in (r["org_ids"] or [])],
            "user_ids": [str(u) for u in (r["user_ids"] or [])],
            "club_names": [clubs_by_id.get(str(o), "Unknown club") for o in (r["org_ids"] or [])],
            "user_names": [names_by_user.get(str(u), "No longer an admin") for u in (r["user_ids"] or [])],
            "cleared_at": _iso(r["cleared_at"]),
            "created_at": _iso(r["created_at"]),
            "updated_at": _iso(r["updated_at"]),
            "created_by": creators.get(str(r["created_by_user_id"])) if r["created_by_user_id"] else None,
            "status": status,
            "recipients": recipients,
            "clubs": clubs,
            "seen": seen,
            "dismissed": dismissed,
            "clubs_seen": clubs_seen,
        })
    return out


async def _load(db: AsyncSession, bid: str):
    row = (await db.execute(text(f"SELECT {_COLS} FROM admin_broadcasts b WHERE b.id = CAST(:id AS uuid)"),
                            {"id": bid})).mappings().first()
    if row is None:
        raise HTTPException(404, "Message not found")
    return row


@router.get("/super/broadcasts")
async def list_broadcasts(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text(f"""
        SELECT {_COLS} FROM admin_broadcasts b
        ORDER BY b.created_at DESC
        LIMIT 200
    """))).mappings().all()
    return {"items": await _serialise_all(db, rows)}


@router.get("/super/broadcasts/audience")
async def audience_options(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every club that is not archived, with the admin-app users at each, for
    the composer's club and user pickers."""
    clubs = (await db.execute(text("""
        SELECT id, name, slug FROM organisations
        WHERE archived_at IS NULL
        ORDER BY lower(name)
    """))).mappings().all()
    by_club: dict[str, list] = {}
    for e in sorted(await _eligible_recipients(db),
                    key=lambda e: (not e["is_primary_admin"], (e["display_name"] or e["username"] or "").lower())):
        by_club.setdefault(str(e["club_id"]), []).append({
            "id": str(e["user_id"]),
            "name": e["display_name"] or e["username"] or "Unnamed",
            "username": e["username"],
            "email": e["email"],
            "role": e["role"],
            "is_primary": bool(e["is_primary_admin"]),
        })
    return {"clubs": [
        {"id": str(c["id"]), "name": c["name"], "slug": c["slug"], "users": by_club.get(str(c["id"]), [])}
        for c in clubs
    ]}


@router.post("/super/broadcasts", status_code=201)
async def create_broadcast(
    body: BroadcastIn,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["tone"] = data.get("tone") or "info"
    data["audience"] = data.get("audience") or "all"
    data["audience_roles"] = data.get("audience_roles") or "all_admins"
    data["persistence"] = data.get("persistence") or "until_cleared"
    data = await _validate(db, data)
    bid = (await db.execute(text("""
        INSERT INTO admin_broadcasts
            (message, tone, link_url, link_label, audience, audience_roles,
             org_ids, user_ids, persistence, starts_at, expires_at, created_by_user_id)
        VALUES
            (:message, :tone, :link_url, :link_label, :audience, :audience_roles,
             CAST(:org_ids AS uuid[]), CAST(:user_ids AS uuid[]), :persistence,
             :starts_at, :expires_at, CAST(:by AS uuid))
        RETURNING id
    """), {**{k: data[k] for k in (
        "message", "tone", "link_url", "link_label", "audience", "audience_roles",
        "org_ids", "user_ids", "persistence", "starts_at", "expires_at")}, "by": str(user.id)})).scalar_one()
    await db.commit()
    row = await _load(db, str(bid))
    return (await _serialise_all(db, [row]))[0]


@router.patch("/super/broadcasts/{broadcast_id}")
async def update_broadcast(
    broadcast_id: str,
    body: BroadcastIn,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Only the fields present in the body change; an explicit null clears an
    optional one (the link, the expiry). The whole result is validated again."""
    bid = _uuid_list([broadcast_id], "id")[0]
    row = await _load(db, bid)
    data = {k: row[k] for k in (
        "message", "tone", "link_url", "link_label", "audience", "audience_roles",
        "org_ids", "user_ids", "persistence", "starts_at", "expires_at")}
    data["org_ids"] = [str(o) for o in (data["org_ids"] or [])]
    data["user_ids"] = [str(u) for u in (data["user_ids"] or [])]
    for key in body.model_fields_set:
        val = getattr(body, key)
        if key == "starts_at" and val is None:
            continue  # a start cannot be removed, only moved
        data[key] = val
    data = await _validate(db, data)
    await db.execute(text("""
        UPDATE admin_broadcasts SET
            message = :message, tone = :tone, link_url = :link_url, link_label = :link_label,
            audience = :audience, audience_roles = :audience_roles,
            org_ids = CAST(:org_ids AS uuid[]), user_ids = CAST(:user_ids AS uuid[]),
            persistence = :persistence, starts_at = :starts_at, expires_at = :expires_at,
            updated_at = NOW()
        WHERE id = CAST(:id AS uuid)
    """), {**{k: data[k] for k in (
        "message", "tone", "link_url", "link_label", "audience", "audience_roles",
        "org_ids", "user_ids", "persistence", "starts_at", "expires_at")}, "id": bid})
    await db.commit()
    return (await _serialise_all(db, [await _load(db, bid)]))[0]


@router.post("/super/broadcasts/{broadcast_id}/clear")
async def clear_broadcast(
    broadcast_id: str,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    bid = _uuid_list([broadcast_id], "id")[0]
    await _load(db, bid)
    await db.execute(text("""
        UPDATE admin_broadcasts
        SET cleared_at = COALESCE(cleared_at, NOW()), cleared_by_user_id = CAST(:by AS uuid),
            updated_at = NOW()
        WHERE id = CAST(:id AS uuid)
    """), {"id": bid, "by": str(user.id)})
    await db.commit()
    return (await _serialise_all(db, [await _load(db, bid)]))[0]


@router.post("/super/broadcasts/{broadcast_id}/restore")
async def restore_broadcast(
    broadcast_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Puts a cleared message back. Who has already seen or dismissed it is
    kept, so a view-once message does not come back for somebody who saw it."""
    bid = _uuid_list([broadcast_id], "id")[0]
    await _load(db, bid)
    await db.execute(text("""
        UPDATE admin_broadcasts SET cleared_at = NULL, cleared_by_user_id = NULL, updated_at = NOW()
        WHERE id = CAST(:id AS uuid)
    """), {"id": bid})
    await db.commit()
    return (await _serialise_all(db, [await _load(db, bid)]))[0]


@router.post("/super/broadcasts/{broadcast_id}/reset-views")
async def reset_views(
    broadcast_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Forgets who has seen and dismissed it, so it shows again to everybody
    it is aimed at."""
    bid = _uuid_list([broadcast_id], "id")[0]
    await _load(db, bid)
    await db.execute(text("DELETE FROM admin_broadcast_receipts WHERE broadcast_id = CAST(:id AS uuid)"),
                     {"id": bid})
    await db.commit()
    return (await _serialise_all(db, [await _load(db, bid)]))[0]


@router.delete("/super/broadcasts/{broadcast_id}", status_code=204)
async def delete_broadcast(
    broadcast_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    bid = _uuid_list([broadcast_id], "id")[0]
    await _load(db, bid)
    await db.execute(text("DELETE FROM admin_broadcasts WHERE id = CAST(:id AS uuid)"), {"id": bid})
    await db.commit()
    return None


@router.get("/super/broadcasts/{broadcast_id}/recipients")
async def broadcast_recipients(
    broadcast_id: str,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Everybody the message reaches, with when each one saw and dismissed it."""
    bid = _uuid_list([broadcast_id], "id")[0]
    row = await _load(db, bid)
    receipts = {str(r["user_id"]): r for r in (await db.execute(text("""
        SELECT user_id, first_seen_at, dismissed_at FROM admin_broadcast_receipts
        WHERE broadcast_id = CAST(:id AS uuid)
    """), {"id": bid})).mappings().all()}
    items = []
    for e in await _eligible_recipients(db):
        if not _reaches(row, e):
            continue
        rc = receipts.get(str(e["user_id"]))
        items.append({
            "user_id": str(e["user_id"]),
            "name": e["display_name"] or e["username"] or "Unnamed",
            "email": e["email"],
            "club_id": str(e["club_id"]),
            "club_name": e["club_name"],
            "role": e["role"],
            "is_primary": bool(e["is_primary_admin"]),
            "seen_at": _iso(rc["first_seen_at"]) if rc else None,
            "dismissed_at": _iso(rc["dismissed_at"]) if rc else None,
        })
    items.sort(key=lambda i: ((i["club_name"] or "").lower(), (i["name"] or "").lower()))
    return {"items": items}
