"""Shared person spine — the ONE place a `fee_members` row is created, edited,
archived, or imported.

`fee_members` is the club's single people record: players (via `player_id`) and
non-players (parents, volunteers, committee, third parties) alike. Modules layer
their own overlay on top of the SAME person and own only that overlay:

- BetterFees   → a fee season + membership tier + payments
- ClubManager  → roles, qualifications, committee terms, roster, hours

So there is one create and one importer here, reached from multiple module
surfaces, rather than a divergent copy per module. This service only ever writes
the `fee_members` row itself; the overlays stay in their own services.

Raw SQL (same posture as services/roster.py / services/directory.py).
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Non-player kinds a person can be tagged with (drives the Directory filters). A
# linked player is a "Player" implicitly and is never given a category here.
MEMBER_CATEGORIES = ["volunteer", "parent", "committee", "life_member", "third_party", "official", "other"]


def normalise_category(v):
    if v is None:
        return None
    v = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in MEMBER_CATEGORIES else None


async def create_person(db: AsyncSession, org_id, *, full_name, email=None, mobile=None,
                        member_category=None, notes=None, player_id=None,
                        membership_type_id=None, current_tier=None) -> str:
    """Insert a fee_members row and return its id. `player_id` NULL = a non-player.
    Fee-specific fields (`membership_type_id`, `current_tier`) are accepted so
    BetterFees can create the person and its tier in one go; ClubManager leaves
    them None and layers roles instead."""
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("Name is required")
    mid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO fee_members (id, organisation_id, player_id, full_name, email, mobile,
                                 member_category, notes, membership_type_id, current_tier)
        VALUES (:id, :org, :pid, :name, :email, :mobile, :cat, :notes, :mt, :tier)
    """), {"id": mid, "org": org_id, "pid": player_id, "name": full_name[:200],
           "email": (email or None), "mobile": (mobile or None),
           "cat": normalise_category(member_category), "notes": (notes or None),
           "mt": membership_type_id, "tier": current_tier})
    return str(mid)


async def update_person(db: AsyncSession, org_id, member_id, **fields) -> None:
    cols = {"full_name": "full_name", "email": "email", "mobile": "mobile", "notes": "notes"}
    sets, params = [], {"id": member_id, "org": org_id}
    for k, col in cols.items():
        if k in fields:
            v = fields[k]
            sets.append(f"{col} = :{k}")
            params[k] = (v.strip()[:200] if k == "full_name" and v else (v or None))
    if "member_category" in fields:
        sets.append("member_category = :cat")
        params["cat"] = normalise_category(fields["member_category"])
    # Already resolved to one of this club's own types (or None to clear) by the
    # caller — this only writes it.
    if "membership_type_id" in fields:
        sets.append("membership_type_id = :mt")
        params["mt"] = fields["membership_type_id"]
    if not sets:
        return
    await db.execute(text(
        f"UPDATE fee_members SET {', '.join(sets)}, updated_at = NOW() WHERE id = :id AND organisation_id = :org"
    ), params)


async def set_archived(db: AsyncSession, org_id, member_id, archived: bool) -> None:
    await db.execute(text(
        "UPDATE fee_members SET archived_at = " + ("NOW()" if archived else "NULL") +
        " WHERE id = :id AND organisation_id = :org"
    ), {"id": member_id, "org": org_id})


async def ensure_for_player(db: AsyncSession, org_id, player_id) -> str:
    """Return the fee_members id for a player, creating the person row on first
    need (so a Stats-owned player can be assigned overlays without any module
    creating a player). Idempotent; un-archives an archived match."""
    row = (await db.execute(text(
        "SELECT id FROM fee_members WHERE organisation_id = :org AND player_id = :pid"
    ), {"org": org_id, "pid": player_id})).scalar()
    if row:
        await db.execute(text("UPDATE fee_members SET archived_at = NULL WHERE id = :id"), {"id": row})
        return str(row)
    name = (await db.execute(text(
        "SELECT COALESCE(display_name_override, name) FROM players WHERE id = :pid AND organisation_id = :org"
    ), {"pid": player_id, "org": org_id})).scalar()
    if not name:
        raise ValueError("Player not found")
    return await create_person(db, org_id, full_name=name, player_id=player_id)


async def find_by_name(db: AsyncSession, org_id) -> dict:
    """lower(full_name) -> member_id, for import de-duplication against existing
    (non-archived) members."""
    rows = (await db.execute(text(
        "SELECT id, full_name FROM fee_members WHERE organisation_id = :org AND archived_at IS NULL"
    ), {"org": org_id})).mappings().all()
    return {(r["full_name"] or "").strip().lower(): str(r["id"]) for r in rows}
