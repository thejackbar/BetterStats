"""Shared non-player member CSV importer — the ONE importer for bringing in
volunteers / parents / committee / third parties, reached from both the
ClubManager Directory and BetterFees Members (players are imported in Stats).

Creates/updates rows on the shared `fee_members` spine via services/members.py
and optionally assigns club roles by title. De-dupes against existing members by
name so a re-run tops up contact details and roles rather than duplicating.

CSV columns (header row, case-insensitive; only `name` is required):
    name | email | mobile (or phone) | category (or type) | roles (or role)
`roles` is a comma/semicolon-separated list of club role titles.
"""
from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import members as members_svc

_CANON = {
    "name": "name", "full_name": "name", "fullname": "name",
    "email": "email", "e-mail": "email",
    "mobile": "mobile", "phone": "mobile", "phone_number": "mobile",
    "category": "category", "type": "category", "member_type": "category",
    "roles": "roles", "role": "roles",
}


def _parse(csv_text: str) -> list[dict]:
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text or ""))
    for raw in reader:
        r = {}
        for k, v in (raw or {}).items():
            if k is None:
                continue
            key = _CANON.get(k.strip().lower())
            if key and v is not None:
                r[key] = v.strip()
        if r.get("name"):
            rows.append(r)
    return rows


def _split_roles(s) -> list[str]:
    if not s:
        return []
    return [p.strip() for p in str(s).replace(";", ",").split(",") if p.strip()]


async def _role_map(db: AsyncSession, org_id) -> dict:
    rows = (await db.execute(text(
        "SELECT id, title FROM club_roles WHERE organisation_id = :org AND is_active = TRUE"
    ), {"org": org_id})).mappings().all()
    return {(r["title"] or "").strip().lower(): str(r["id"]) for r in rows}


async def preview(db: AsyncSession, org_id, csv_text: str) -> dict:
    rows = _parse(csv_text)
    existing = await members_svc.find_by_name(db, org_id)
    rolemap = await _role_map(db, org_id)
    out = []
    for r in rows:
        name = r["name"]
        role_titles = _split_roles(r.get("roles"))
        matched = [rt for rt in role_titles if rt.lower() in rolemap]
        unknown = [rt for rt in role_titles if rt.lower() not in rolemap]
        out.append({
            "name": name, "email": r.get("email") or "", "mobile": r.get("mobile") or "",
            "category": members_svc.normalise_category(r.get("category")),
            "roles": matched, "unknown_roles": unknown,
            "existing": name.strip().lower() in existing,
        })
    return {
        "rows": out, "total": len(out),
        "new": sum(1 for r in out if not r["existing"]),
        "existing": sum(1 for r in out if r["existing"]),
    }


async def commit(db: AsyncSession, org_id, csv_text: str) -> dict:
    rows = _parse(csv_text)
    existing = await members_svc.find_by_name(db, org_id)
    rolemap = await _role_map(db, org_id)
    created = updated = roles_added = 0
    member_ids = []
    for r in rows:
        name = r["name"]
        key = name.strip().lower()
        cat = members_svc.normalise_category(r.get("category"))
        mid = existing.get(key)
        if mid:
            # Only overwrite a field the CSV actually carries (don't wipe on a
            # top-up row that omits email/mobile).
            fields = {}
            if r.get("email"):
                fields["email"] = r["email"]
            if r.get("mobile"):
                fields["mobile"] = r["mobile"]
            if cat:
                fields["member_category"] = cat
            if fields:
                await members_svc.update_person(db, org_id, uuid.UUID(mid), **fields)
                updated += 1
        else:
            mid = await members_svc.create_person(
                db, org_id, full_name=name, email=r.get("email"), mobile=r.get("mobile"), member_category=cat)
            existing[key] = mid
            created += 1
        member_ids.append(mid)
        for rt in _split_roles(r.get("roles")):
            rid = rolemap.get(rt.lower())
            if rid:
                await db.execute(text("""
                    INSERT INTO volunteer_roles (id, organisation_id, member_id, role_id)
                    VALUES (gen_random_uuid(), :org, :mid, :rid)
                    ON CONFLICT (member_id, role_id) DO NOTHING
                """), {"org": org_id, "mid": mid, "rid": rid})
                roles_added += 1
    return {"created": created, "updated": updated, "roles_added": roles_added, "member_ids": member_ids}


async def open_member_seasons(db: AsyncSession, org_id, season_id, member_ids) -> int:
    """Open a fee season row (no tier = "needs tier") for each member that isn't
    already in the season. Lets a BetterFees import surface people in the
    season-scoped members list; the person spine itself is created by commit()."""
    opened = 0
    for mid in member_ids:
        res = await db.execute(text("""
            INSERT INTO fee_member_seasons (id, member_id, season_id, organisation_id)
            SELECT gen_random_uuid(), :mid, :sid, :org
            WHERE NOT EXISTS (SELECT 1 FROM fee_member_seasons WHERE member_id = :mid AND season_id = :sid)
        """), {"mid": mid, "sid": season_id, "org": org_id})
        opened += res.rowcount or 0
    return opened
