"""Shared non-player member CSV importer — the ONE importer for bringing in
volunteers / parents / committee / third parties, reached from both the
ClubManager Directory and BetterFees Members (players are imported in Stats).

Creates/updates rows on the shared `fee_members` spine via services/members.py
and optionally assigns club roles by title. De-dupes against existing members by
name so a re-run tops up contact details and roles rather than duplicating.

CSV columns (header row, case-insensitive; only `name` is required):
    name | email | mobile (or phone) | category (or type) | roles (or role)
    | shirt size | pants size | shirt number
`roles` is a comma/semicolon-separated list of club role titles.

THE THREE KIT COLUMNS DO NOT ALL WRITE TO THE SAME TABLE, for the reason
migration 287 records: the two SIZES belong to the person (a coach and a scorer
take a polo size, and neither is a player) and land on `fee_members`; the
NUMBER is a playing attribute and lands on `players.shirt_number`. So a number
has to resolve to one of the club's players before it means anything, and a row
that names nobody who plays reports that rather than storing it somewhere it
would never be read.

The sizes are BetterAdmin's, so a sheet that carries one is refused for a club
without the module — refused rather than quietly ignored, because a club that
uploads sizes and is told nothing would believe they were imported.
"""
from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import members as members_svc
from app.services.player_kit import clean_kit_size, clean_shirt_number

_CANON = {
    "name": "name", "full_name": "name", "fullname": "name",
    "email": "email", "e-mail": "email",
    "mobile": "mobile", "phone": "mobile", "phone_number": "mobile",
    "category": "category", "type": "category", "member_type": "category",
    "roles": "roles", "role": "roles",
    # Kit (migration 287). "shirt" on its own is deliberately NOT mapped: it is
    # as likely to be a size column as a number one, and guessing wrong puts a
    # size in a number field. A club whose header is that vague picks the
    # column itself by renaming it.
    "shirt_size": "shirt_size", "shirt size": "shirt_size", "top_size": "shirt_size",
    "top size": "shirt_size", "playing_shirt_size": "shirt_size", "shirt/top size": "shirt_size",
    "pants_size": "pants_size", "pants size": "pants_size", "pant_size": "pants_size",
    "pant size": "pants_size", "trouser_size": "pants_size", "trouser size": "pants_size",
    "trousers": "pants_size", "shorts_size": "pants_size", "shorts size": "pants_size",
    "shirt_number": "shirt_number", "shirt number": "shirt_number", "shirt no": "shirt_number",
    "player_number": "shirt_number", "player number": "shirt_number",
    "playing_number": "shirt_number", "playing number": "shirt_number",
    "squad_number": "shirt_number", "squad number": "shirt_number",
    "number": "shirt_number", "no": "shirt_number", "jumper_number": "shirt_number",
    "jumper number": "shirt_number",
}

# The columns that are BetterAdmin's. Named here so a caller can gate a sheet
# before it is imported without knowing how the parser works.
KIT_SIZE_FIELDS = ("shirt_size", "pants_size")


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


def columns_used(csv_text: str) -> set:
    """The canonical fields this sheet's headers map to. What a caller gates on
    — the sheet's own columns, not what happens to be filled in on a row, so a
    club is told before it uploads rather than after some rows silently lose a
    value."""
    reader = csv.DictReader(io.StringIO(csv_text or ""))
    return {_CANON[k.strip().lower()] for k in (reader.fieldnames or []) if k
            and k.strip().lower() in _CANON}


async def _player_index(db: AsyncSession, org_id) -> tuple[dict, dict, dict]:
    """Three maps for resolving a sheet row to one of the club's players.

    `by_name` is a NAME KEY to the list of players holding it — a list, not a
    single id, because two people at a club really can share a name (a father
    and a son) and a number written onto the wrong one of them is worse than a
    number not written at all. Both the stored name and any display override
    are keys, so a renamed player is found under either.
    """
    rows = (await db.execute(text("""
        SELECT p.id, p.name, p.display_name_override,
               (SELECT fm.id FROM fee_members fm
                 WHERE fm.organisation_id = p.organisation_id AND fm.player_id = p.id
                 LIMIT 1) AS member_id
        FROM players p WHERE p.organisation_id = :org
    """), {"org": org_id})).mappings().all()
    by_name: dict = {}
    member_by_player: dict = {}
    name_of: dict = {}
    for r in rows:
        pid = str(r["id"])
        name_of[pid] = (r["display_name_override"] or r["name"] or "").strip()
        if r["member_id"]:
            member_by_player[pid] = str(r["member_id"])
        for n in (r["name"], r["display_name_override"]):
            k = (n or "").strip().lower()
            if k and pid not in by_name.setdefault(k, []):
                by_name[k].append(pid)
    return by_name, member_by_player, name_of


def _resolve_player(key, by_name) -> tuple:
    """(player_id, note). A name matching more than one player resolves to
    neither — the refuse-to-guess rule this repo keeps everywhere a name is an
    identity."""
    cands = by_name.get(key) or []
    if len(cands) == 1:
        return cands[0], None
    if len(cands) > 1:
        return None, "more than one player of that name"
    return None, "no player of that name"


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
    by_name, member_by_player, name_of = await _player_index(db, org_id)
    out = []
    for r in rows:
        name = r["name"]
        key = name.strip().lower()
        role_titles = _split_roles(r.get("roles"))
        matched = [rt for rt in role_titles if rt.lower() in rolemap]
        unknown = [rt for rt in role_titles if rt.lower() not in rolemap]
        number = clean_shirt_number(r.get("shirt_number"))
        # A number is only ever worth reporting against a real player, so the
        # preview says which one it found — or why it found none — BEFORE the
        # club commits, rather than leaving them to notice afterwards.
        pid, why = (None, None)
        if number is not None:
            pid, why = _resolve_player(key, by_name)
        out.append({
            "name": name, "email": r.get("email") or "", "mobile": r.get("mobile") or "",
            "category": members_svc.normalise_category(r.get("category")),
            "roles": matched, "unknown_roles": unknown,
            "existing": key in existing,
            "shirt_size": clean_kit_size(r.get("shirt_size")) or "",
            "pants_size": clean_kit_size(r.get("pants_size")) or "",
            "shirt_number": number or "",
            "player": name_of.get(pid) if pid else None,
            "number_skipped": why if (number is not None and not pid) else None,
        })
    return {
        "rows": out, "total": len(out),
        "new": sum(1 for r in out if not r["existing"]),
        "existing": sum(1 for r in out if r["existing"]),
        # What the sheet is actually carrying, so the screen only draws the kit
        # columns for a sheet that has them.
        "columns": sorted(columns_used(csv_text)),
    }


async def commit(db: AsyncSession, org_id, csv_text: str) -> dict:
    rows = _parse(csv_text)
    existing = await members_svc.find_by_name(db, org_id)
    rolemap = await _role_map(db, org_id)
    by_name, member_by_player, _name_of = await _player_index(db, org_id)
    created = updated = roles_added = 0
    numbers_set = numbers_skipped = sizes_set = 0
    member_ids = []
    for r in rows:
        name = r["name"]
        key = name.strip().lower()
        cat = members_svc.normalise_category(r.get("category"))
        shirt = clean_kit_size(r.get("shirt_size"))
        pants = clean_kit_size(r.get("pants_size"))
        number = clean_shirt_number(r.get("shirt_number"))
        mid = existing.get(key)
        # Which player this row is about, if any. A row matched to an existing
        # member takes that member's own link; otherwise the name has to
        # resolve to exactly one player.
        pid, _why = _resolve_player(key, by_name) if (number is not None or mid is None) else (None, None)
        if mid is None and pid and member_by_player.get(pid):
            # That player already has a person row under a different spelling.
            # Using it is what stops a sheet of kit sizes minting a second
            # record for somebody the club already holds.
            mid = member_by_player[pid]
            existing[key] = mid
        if mid:
            # Only overwrite a field the CSV actually carries (don't wipe on a
            # top-up row that omits email/mobile). A size is the same: a sheet
            # that says nothing about it leaves what is stored alone.
            fields = {}
            if r.get("email"):
                fields["email"] = r["email"]
            if r.get("mobile"):
                fields["mobile"] = r["mobile"]
            if cat:
                fields["member_category"] = cat
            if shirt:
                fields["shirt_size"] = shirt
            if pants:
                fields["pants_size"] = pants
            if fields:
                await members_svc.update_person(db, org_id, uuid.UUID(mid), **fields)
                updated += 1
        else:
            mid = await members_svc.create_person(
                db, org_id, full_name=name, email=r.get("email"), mobile=r.get("mobile"),
                member_category=cat, shirt_size=shirt, pants_size=pants,
                # Linked when the name resolves to exactly one player who has no
                # person row yet — the same row `ensure_for_player` would have
                # made. Without it a club importing kit sizes for its players
                # ends up with every one of them in the Directory twice.
                player_id=(pid if pid and not member_by_player.get(pid) else None))
            if pid and not member_by_player.get(pid):
                member_by_player[pid] = mid
            existing[key] = mid
            created += 1
        if shirt or pants:
            sizes_set += 1
        # The NUMBER is a playing attribute, so it goes to the player or
        # nowhere. Reported either way; never written onto the person row,
        # where nothing would ever read it.
        if number is not None:
            if pid:
                await db.execute(text(
                    "UPDATE players SET shirt_number = :n WHERE id = :p AND organisation_id = :org"
                ), {"n": number, "p": pid, "org": org_id})
                numbers_set += 1
            else:
                numbers_skipped += 1
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
    return {"created": created, "updated": updated, "roles_added": roles_added,
            "sizes_set": sizes_set, "numbers_set": numbers_set,
            "numbers_skipped": numbers_skipped, "member_ids": member_ids}


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
