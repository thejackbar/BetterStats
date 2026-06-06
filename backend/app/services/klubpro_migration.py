"""KlubPro → BetterStats migration: business logic.

Reads staged data from the external KlubPro ``klubpro_migration`` schema (raw,
schema-qualified SQL — KlubPro is not ORM-mapped) and, on the BetterStats side,
fills player profile fields and inserts sponsors. Every write is preceded by a
row-level backup so a whole import can be undone (see ``execute_*_import`` /
``rollback_batch``).

Safety invariants enforced here:
  * **Never destructive with empties.** A player field is only overwritten when
    the KlubPro value is non-empty, so an import fills gaps and never blanks data.
  * **Never touches stats.** Only the ten profile fields the handoff lists are
    written (gender/email/phone/photo/skills/role/hands/opening). Games,
    appearances, scores, ids, organisation_id are out of scope.
  * **No duplicate sponsors.** Insert is guarded by (organisation_id,
    klubpro_sponsor_id); an already-imported sponsor is skipped.
  * **No deleted KlubPro players.** The candidate view is the staged set; deleted
    rows never reach it.
"""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    KlubproMigrationBackup,
    KlubproMigrationBatch,
    Player,
    Sponsor,
)

# The exact ten BetterStats player columns the handoff says to fill, mapped from
# the candidate view's already-derived columns. (bowling_action is intentionally
# absent — the staged view doesn't derive it, so we leave it untouched.)
PLAYER_FIELD_LABELS = {
    "gender": "Gender",
    "email": "Email",
    "phone": "Phone",
    "player_role": "Role",
    "batting_hand": "Batting hand",
    "bowling_type": "Bowling type",
    "is_opening_batsman": "Opening batter",
    "skill_positions": "Skills",
    "photo": "Photo",
}


# ── small value helpers ──────────────────────────────────────────────────────

def _empty(v: Any) -> bool:
    """An incoming value we should NOT overwrite a BetterStats field with."""
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if isinstance(v, (list, tuple, dict)) and len(v) == 0:
        return True
    return False


def _as_list(v: Any) -> list:
    """KlubPro jsonb comes back from asyncpg as a JSON string; normalise."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except (ValueError, TypeError):
            return []
    return list(v) if isinstance(v, (list, tuple)) else []


def _skills_differ(a: Any, b: Any) -> bool:
    """Skills are an unordered set — compare ignoring order/dupes."""
    return set(_as_list(a)) != set(_as_list(b))


def _uuid(v: Any) -> Optional[uuid.UUID]:
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


# ── KlubPro reads (dashboard / mappings) ─────────────────────────────────────

async def fetch_dashboard(kp: AsyncSession) -> list[dict]:
    rows = await kp.execute(text("""
        SELECT klubpro_club_id, klubpro_club_name, stage_status,
               staged_players, players_with_skills, players_with_email,
               players_with_mobile, players_with_gender, players_with_image,
               players_with_all_required_data, staged_sponsors, sponsors_with_logo
        FROM klubpro_migration.onboarding_staging_summary
        ORDER BY klubpro_club_name
    """))
    return [dict(r) for r in rows.mappings().all()]


async def fetch_club_mappings(kp: AsyncSession) -> list[dict]:
    rows = await kp.execute(text("""
        SELECT id, betterstats_organisation_id, betterstats_organisation_name,
               klubpro_club_id, klubpro_club_name, migration_status,
               COALESCE(klubpro_club_deleted, false) AS klubpro_club_deleted
        FROM klubpro_migration.club_mappings
        ORDER BY betterstats_organisation_name
    """))
    out = []
    for r in rows.mappings().all():
        d = dict(r)
        d["id"] = str(d["id"])
        d["betterstats_organisation_id"] = (
            str(d["betterstats_organisation_id"]) if d["betterstats_organisation_id"] else None
        )
        out.append(d)
    return out


async def fetch_club_mapping(kp: AsyncSession, club_mapping_id: uuid.UUID) -> Optional[dict]:
    row = await kp.execute(text("""
        SELECT id, betterstats_organisation_id, betterstats_organisation_name,
               klubpro_club_id, klubpro_club_name, migration_status
        FROM klubpro_migration.club_mappings WHERE id = :id
    """), {"id": str(club_mapping_id)})
    r = row.mappings().first()
    if not r:
        return None
    d = dict(r)
    d["id"] = str(d["id"])
    d["betterstats_organisation_id"] = (
        str(d["betterstats_organisation_id"]) if d["betterstats_organisation_id"] else None
    )
    return d


# ── KlubPro reads (players) ──────────────────────────────────────────────────

async def fetch_player_candidates(kp: AsyncSession, klubpro_club_id: str) -> list[dict]:
    """Candidate metadata for the review grid — no image bytes."""
    rows = await kp.execute(text("""
        SELECT klubpro_player_id, firstname, lastname, nickname, gender,
               email, mobile, skill_names, betterstats_player_role,
               betterstats_batting_hand, betterstats_bowling_type,
               betterstats_skill_positions, betterstats_is_opening_batsman,
               profile_image_found, thumbnail_image_found
        FROM klubpro_migration.player_migration_candidates
        WHERE klubpro_club_id = :cid
        ORDER BY lastname, firstname
    """), {"cid": klubpro_club_id})
    out = []
    for r in rows.mappings().all():
        d = dict(r)
        d["skill_names"] = list(d.get("skill_names") or [])
        d["betterstats_skill_positions"] = _as_list(d.get("betterstats_skill_positions"))
        out.append(d)
    return out


async def fetch_player_candidate(kp: AsyncSession, klubpro_player_id: str) -> Optional[dict]:
    """A single candidate's importable values (incl. image bytes)."""
    row = await kp.execute(text("""
        SELECT klubpro_player_id, klubpro_club_id, firstname, lastname, nickname,
               gender, email, mobile, betterstats_player_role,
               betterstats_batting_hand, betterstats_bowling_type,
               betterstats_skill_positions, betterstats_is_opening_batsman,
               profile_image_data, profile_image_mime, profile_image_found
        FROM klubpro_migration.player_migration_candidates
        WHERE klubpro_player_id = :pid
    """), {"pid": klubpro_player_id})
    r = row.mappings().first()
    if not r:
        return None
    d = dict(r)
    d["betterstats_skill_positions"] = _as_list(d.get("betterstats_skill_positions"))
    return d


async def fetch_player_image(kp: AsyncSession, klubpro_player_id: str, thumb: bool) -> Optional[tuple[bytes, str]]:
    col = "thumbnail_image" if thumb else "profile_image"
    row = await kp.execute(text(f"""
        SELECT {col}_data AS data, {col}_mime AS mime
        FROM klubpro_migration.player_migration_candidates
        WHERE klubpro_player_id = :pid
    """), {"pid": klubpro_player_id})
    r = row.mappings().first()
    if not r or not r["data"]:
        return None
    return bytes(r["data"]), (r["mime"] or "image/png")


async def fetch_match_mappings(kp: AsyncSession, club_mapping_id: uuid.UUID) -> list[dict]:
    rows = await kp.execute(text("""
        SELECT betterstats_player_id, betterstats_player_name, klubpro_player_id,
               klubpro_player_firstname, klubpro_player_lastname,
               klubpro_player_nickname, match_status, match_score,
               COALESCE(approved, false) AS approved, notes
        FROM klubpro_migration.player_match_mappings
        WHERE club_mapping_id = :cmid
    """), {"cmid": str(club_mapping_id)})
    out = []
    for r in rows.mappings().all():
        d = dict(r)
        d["betterstats_player_id"] = str(d["betterstats_player_id"]) if d["betterstats_player_id"] else None
        d["match_score"] = float(d["match_score"]) if d["match_score"] is not None else None
        out.append(d)
    return out


async def upsert_match_mapping(
    kp: AsyncSession,
    *,
    club_mapping_id: uuid.UUID,
    betterstats_player_id: uuid.UUID,
    betterstats_player_name: Optional[str],
    klubpro_player_id: Optional[str],
    klubpro_player_firstname: Optional[str],
    klubpro_player_lastname: Optional[str],
    klubpro_player_nickname: Optional[str],
    match_status: str,
    approved: bool,
    notes: Optional[str],
) -> None:
    """Record an operator decision. Keyed on (club_mapping_id, betterstats_player_id)."""
    await kp.execute(text("""
        DELETE FROM klubpro_migration.player_match_mappings
        WHERE club_mapping_id = :cmid AND betterstats_player_id = :bpid
    """), {"cmid": str(club_mapping_id), "bpid": str(betterstats_player_id)})
    await kp.execute(text("""
        INSERT INTO klubpro_migration.player_match_mappings
            (id, club_mapping_id, betterstats_player_id, betterstats_player_name,
             klubpro_player_id, klubpro_player_firstname, klubpro_player_lastname,
             klubpro_player_nickname, match_status, approved, notes,
             created_at, updated_at)
        VALUES
            (gen_random_uuid(), :cmid, :bpid, :bname, :kpid, :kfn, :kln, :knn,
             :status, :approved, :notes, NOW(), NOW())
    """), {
        "cmid": str(club_mapping_id), "bpid": str(betterstats_player_id),
        "bname": betterstats_player_name, "kpid": klubpro_player_id,
        "kfn": klubpro_player_firstname, "kln": klubpro_player_lastname,
        "knn": klubpro_player_nickname, "status": match_status,
        "approved": approved, "notes": notes,
    })
    await kp.commit()


# ── KlubPro reads (sponsors) ─────────────────────────────────────────────────

async def fetch_sponsor_candidates(kp: AsyncSession, klubpro_club_id: str) -> list[dict]:
    rows = await kp.execute(text("""
        SELECT klubpro_sponsor_id, sponsor_name, sequence, contact_name, email,
               logo_found, logo_mime, octet_length(logo_data) AS logo_bytes
        FROM klubpro_migration.sponsor_migration_candidates
        WHERE klubpro_club_id = :cid
        ORDER BY sequence NULLS LAST, sponsor_name
    """), {"cid": klubpro_club_id})
    return [dict(r) for r in rows.mappings().all()]


async def fetch_sponsor_candidate(kp: AsyncSession, klubpro_sponsor_id: str) -> Optional[dict]:
    row = await kp.execute(text("""
        SELECT klubpro_sponsor_id, klubpro_club_id, sponsor_name, sequence,
               contact_name, email, logo_data, logo_mime
        FROM klubpro_migration.sponsor_migration_candidates
        WHERE klubpro_sponsor_id = :sid
    """), {"sid": klubpro_sponsor_id})
    r = row.mappings().first()
    return dict(r) if r else None


async def fetch_sponsor_logo(kp: AsyncSession, klubpro_sponsor_id: str) -> Optional[tuple[bytes, str]]:
    row = await kp.execute(text("""
        SELECT logo_data AS data, logo_mime AS mime
        FROM klubpro_migration.sponsor_migration_candidates
        WHERE klubpro_sponsor_id = :sid
    """), {"sid": klubpro_sponsor_id})
    r = row.mappings().first()
    if not r or not r["data"]:
        return None
    return bytes(r["data"]), (r["mime"] or "image/png")


# ── BetterStats reads ────────────────────────────────────────────────────────

async def fetch_bs_players(bs: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    rows = await bs.execute(
        select(
            Player.id, Player.name, Player.gender, Player.email, Player.phone,
            Player.player_role, Player.batting_hand, Player.bowling_type,
            Player.skill_positions, Player.is_opening_batsman, Player.photo_mime,
        ).where(Player.organisation_id == org_id).order_by(Player.name)
    )
    out = []
    for r in rows.all():
        out.append({
            "id": str(r.id), "name": r.name, "gender": r.gender, "email": r.email,
            "phone": r.phone, "player_role": r.player_role,
            "batting_hand": r.batting_hand, "bowling_type": r.bowling_type,
            "skill_positions": list(r.skill_positions or []),
            "is_opening_batsman": r.is_opening_batsman,
            "has_photo": r.photo_mime is not None,
        })
    return out


async def fetch_bs_sponsors(bs: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    rows = await bs.execute(
        select(Sponsor).where(Sponsor.organisation_id == org_id).order_by(Sponsor.display_order, Sponsor.name)
    )
    out = []
    for s in rows.scalars().all():
        out.append({
            "id": str(s.id), "name": s.name, "display_order": s.display_order,
            "contact_name": s.contact_name, "email": s.email,
            "klubpro_sponsor_id": s.klubpro_sponsor_id,
            "has_logo": s.logo_mime is not None,
        })
    return out


# ── dry-run diff (pure, per approved match) ──────────────────────────────────

def diff_player(current: dict, candidate: dict) -> list[dict]:
    """Per-field {field,label,current,incoming,change,skipped_empty} for one match.

    `current` is a fetch_bs_players row; `candidate` a fetch_player_candidate row.
    """
    incoming = {
        "gender": candidate.get("gender"),
        "email": candidate.get("email"),
        "phone": candidate.get("mobile"),
        "player_role": candidate.get("betterstats_player_role"),
        "batting_hand": candidate.get("betterstats_batting_hand"),
        "bowling_type": candidate.get("betterstats_bowling_type"),
        "is_opening_batsman": candidate.get("betterstats_is_opening_batsman"),
        "skill_positions": _as_list(candidate.get("betterstats_skill_positions")),
        "photo": "image" if candidate.get("profile_image_found") else None,
    }
    cur = {
        "gender": current.get("gender"),
        "email": current.get("email"),
        "phone": current.get("phone"),
        "player_role": current.get("player_role"),
        "batting_hand": current.get("batting_hand"),
        "bowling_type": current.get("bowling_type"),
        "is_opening_batsman": current.get("is_opening_batsman"),
        "skill_positions": list(current.get("skill_positions") or []),
        "photo": "image" if current.get("has_photo") else None,
    }
    diffs = []
    for field, label in PLAYER_FIELD_LABELS.items():
        inc = incoming.get(field)
        now = cur.get(field)
        skipped = _empty(inc)
        # is_opening_batsman: the staged view returns False rather than NULL, so
        # we only treat True as a value worth writing (False = "no info").
        if field == "is_opening_batsman" and inc is False:
            skipped = True
        if field == "skill_positions":
            change = (not skipped) and _skills_differ(inc, now)
        else:
            change = (not skipped) and (inc != now)
        diffs.append({
            "field": field, "label": label,
            "current": now, "incoming": inc,
            "change": change, "skipped_empty": skipped,
        })
    return diffs


# ── backup helpers ───────────────────────────────────────────────────────────

def _player_before(player: Player) -> dict:
    """JSON-safe snapshot of the fields an import may overwrite (incl. photo)."""
    return {
        "gender": player.gender, "email": player.email, "phone": player.phone,
        "player_role": player.player_role, "batting_hand": player.batting_hand,
        "bowling_type": player.bowling_type,
        "is_opening_batsman": player.is_opening_batsman,
        "skill_positions": list(player.skill_positions or []),
        "photo_mime": player.photo_mime,
        "photo_b64": base64.b64encode(player.photo_data).decode() if player.photo_data else None,
    }


# ── import execution ─────────────────────────────────────────────────────────

async def execute_player_import(
    bs: AsyncSession,
    kp: AsyncSession,
    *,
    org_id: uuid.UUID,
    club_mapping: dict,
    operator,  # User
) -> dict:
    """Apply every approved, mapped match for the club. Backs up each row first.

    Returns {batch_id, updated, skipped, field_writes}. Idempotent-ish: only
    non-empty values overwrite, so re-running fills nothing new.
    """
    club_mapping_id = _uuid(club_mapping["id"])
    matches = await fetch_match_mappings(kp, club_mapping_id)
    approved = [m for m in matches if m.get("approved") and m.get("klubpro_player_id")]

    batch = KlubproMigrationBatch(
        kind="player", organisation_id=org_id, club_mapping_id=club_mapping_id,
        klubpro_club_id=club_mapping.get("klubpro_club_id"), status="imported",
        operator_user_id=getattr(operator, "id", None),
        operator_name=getattr(operator, "display_name", None) or getattr(operator, "username", None),
    )
    bs.add(batch)
    await bs.flush()  # get batch.id

    updated = 0
    skipped = 0
    field_writes = 0
    for m in approved:
        player = await bs.get(Player, _uuid(m["betterstats_player_id"]))
        if not player or player.organisation_id != org_id:
            skipped += 1
            continue
        cand = await fetch_player_candidate(kp, m["klubpro_player_id"])
        if not cand:
            skipped += 1
            continue

        before = _player_before(player)
        changed_any = False

        def _set(field, value):
            nonlocal changed_any, field_writes
            if _empty(value):
                return
            if getattr(player, field) != value:
                setattr(player, field, value)
                changed_any = True
                field_writes += 1

        _set("gender", cand.get("gender"))
        _set("email", cand.get("email"))
        _set("phone", cand.get("mobile"))
        _set("player_role", cand.get("betterstats_player_role"))
        _set("batting_hand", cand.get("betterstats_batting_hand"))
        _set("bowling_type", cand.get("betterstats_bowling_type"))
        if cand.get("betterstats_is_opening_batsman") is True:
            _set("is_opening_batsman", True)
        skills = _as_list(cand.get("betterstats_skill_positions"))
        if skills and _skills_differ(skills, player.skill_positions):
            player.skill_positions = skills
            changed_any = True
            field_writes += 1
        # Photo is fill-only: a player with no photo gets the KlubPro one; an
        # existing (often hand-curated) photo is kept. This keeps the dry-run
        # exact — we can't preview a byte-level photo diff — and is the safe
        # default. (Scalars above let a non-empty KlubPro value win.)
        if cand.get("profile_image_found") and cand.get("profile_image_data") and not player.photo_data:
            player.photo_data = bytes(cand["profile_image_data"])
            player.photo_mime = cand.get("profile_image_mime") or "image/png"
            changed_any = True
            field_writes += 1

        if not changed_any:
            skipped += 1
            continue

        bs.add(KlubproMigrationBackup(
            batch_id=batch.id, target_table="players", target_id=player.id,
            action="update", before_data=before, after_data=_player_before(player),
        ))
        updated += 1

    batch.counts = {"updated": updated, "skipped": skipped, "field_writes": field_writes}
    await bs.commit()
    return {"batch_id": str(batch.id), "updated": updated, "skipped": skipped, "field_writes": field_writes}


async def execute_sponsor_import(
    bs: AsyncSession,
    kp: AsyncSession,
    *,
    org_id: uuid.UUID,
    club_mapping: dict,
    selected_ids: list[str],
    operator,  # User
) -> dict:
    """Insert the selected KlubPro sponsors. Skips any already imported (dupe-safe)."""
    existing = await bs.execute(
        select(Sponsor.klubpro_sponsor_id).where(
            Sponsor.organisation_id == org_id,
            Sponsor.klubpro_sponsor_id.isnot(None),
        )
    )
    already = {row[0] for row in existing.all()}
    # next display_order after the org's current max
    max_order = await bs.execute(
        select(Sponsor.display_order).where(Sponsor.organisation_id == org_id)
        .order_by(Sponsor.display_order.desc()).limit(1)
    )
    next_order = (max_order.scalar() or 0) + 1

    batch = KlubproMigrationBatch(
        kind="sponsor", organisation_id=org_id, club_mapping_id=_uuid(club_mapping["id"]),
        klubpro_club_id=club_mapping.get("klubpro_club_id"), status="imported",
        operator_user_id=getattr(operator, "id", None),
        operator_name=getattr(operator, "display_name", None) or getattr(operator, "username", None),
    )
    bs.add(batch)
    await bs.flush()

    inserted = 0
    skipped = 0
    for sid in selected_ids:
        if sid in already:
            skipped += 1
            continue
        cand = await fetch_sponsor_candidate(kp, sid)
        if not cand:
            skipped += 1
            continue
        seq = cand.get("sequence")
        order = int(seq) if seq is not None else next_order
        if seq is None:
            next_order += 1
        sponsor = Sponsor(
            organisation_id=org_id,
            name=cand.get("sponsor_name") or "Sponsor",
            display_order=order,
            contact_name=cand.get("contact_name"),
            email=cand.get("email"),
            logo_data=bytes(cand["logo_data"]) if cand.get("logo_data") else None,
            logo_mime=cand.get("logo_mime"),
            klubpro_sponsor_id=sid,
        )
        bs.add(sponsor)
        await bs.flush()
        already.add(sid)
        bs.add(KlubproMigrationBackup(
            batch_id=batch.id, target_table="org_sponsors", target_id=sponsor.id,
            action="insert", before_data=None,
            after_data={"name": sponsor.name, "klubpro_sponsor_id": sid},
        ))
        inserted += 1

    batch.counts = {"inserted": inserted, "skipped": skipped}
    await bs.commit()
    return {"batch_id": str(batch.id), "inserted": inserted, "skipped": skipped}


# ── rollback ─────────────────────────────────────────────────────────────────

async def rollback_batch(bs: AsyncSession, batch: KlubproMigrationBatch) -> dict:
    """Reverse an imported batch: restore updated players, delete inserted sponsors."""
    rows = await bs.execute(
        select(KlubproMigrationBackup).where(KlubproMigrationBackup.batch_id == batch.id)
    )
    backups = rows.scalars().all()
    restored = 0
    deleted = 0
    for b in backups:
        if b.action == "update" and b.target_table == "players":
            player = await bs.get(Player, b.target_id)
            if not player:
                continue
            bd = b.before_data or {}
            player.gender = bd.get("gender")
            player.email = bd.get("email")
            player.phone = bd.get("phone")
            player.player_role = bd.get("player_role")
            player.batting_hand = bd.get("batting_hand")
            player.bowling_type = bd.get("bowling_type")
            player.is_opening_batsman = bd.get("is_opening_batsman")
            player.skill_positions = list(bd.get("skill_positions") or [])
            player.photo_mime = bd.get("photo_mime")
            player.photo_data = base64.b64decode(bd["photo_b64"]) if bd.get("photo_b64") else None
            restored += 1
        elif b.action == "insert" and b.target_table == "org_sponsors":
            sponsor = await bs.get(Sponsor, b.target_id)
            if sponsor:
                await bs.delete(sponsor)
                deleted += 1

    from datetime import datetime, timezone
    batch.status = "rolled_back"
    batch.rolled_back_at = datetime.now(timezone.utc)
    await bs.commit()
    return {"restored": restored, "deleted": deleted}
