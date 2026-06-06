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
    Organisation,
    Player,
    Sponsor,
)

# The migratable BetterStats player fields, mapped from the candidate view's
# already-derived columns. `profile_image` → photo_data/photo_mime. These keys
# are the canonical `migrate_fields` keys stored on each match mapping.
# (bowling_action is intentionally absent — the staged view doesn't derive it;
#  first/last/nickname are NOT migratable — BetterStats has a single `name`
#  field, so name parts are shown for context only, never written.)
PLAYER_FIELD_LABELS = {
    "gender": "Gender",
    "email": "Email",
    "phone": "Phone",
    "player_role": "Role",
    "batting_hand": "Batting hand",
    "bowling_type": "Bowling type",
    "is_opening_batsman": "Opening batter",
    "skill_positions": "Skills",
    "profile_image": "Profile image",
}
MIGRATABLE_FIELDS = tuple(PLAYER_FIELD_LABELS.keys())


def _incoming_map(candidate: dict) -> dict:
    """The 9 migratable values as staged in KlubPro for one candidate."""
    return {
        "gender": candidate.get("gender"),
        "email": candidate.get("email"),
        "phone": candidate.get("mobile"),
        "player_role": candidate.get("betterstats_player_role"),
        "batting_hand": candidate.get("betterstats_batting_hand"),
        "bowling_type": candidate.get("betterstats_bowling_type"),
        "is_opening_batsman": candidate.get("betterstats_is_opening_batsman"),
        "skill_positions": _as_list(candidate.get("betterstats_skill_positions")),
        "profile_image": "image" if candidate.get("profile_image_found") else None,
    }


def _current_map(current: dict) -> dict:
    """The same 9 fields as they currently stand on the BetterStats player."""
    return {
        "gender": current.get("gender"),
        "email": current.get("email"),
        "phone": current.get("phone"),
        "player_role": current.get("player_role"),
        "batting_hand": current.get("batting_hand"),
        "bowling_type": current.get("bowling_type"),
        "is_opening_batsman": current.get("is_opening_batsman"),
        "skill_positions": list(current.get("skill_positions") or []),
        "profile_image": "image" if current.get("has_photo") else None,
    }


def _field_empty(field: str, inc: Any) -> bool:
    """Is the incoming KlubPro value one we must not write for this field?"""
    if field == "is_opening_batsman":
        # The staged view returns False rather than NULL — False == "no info".
        return inc is not True
    return _empty(inc)


def recommended_fields(current: dict, candidate: dict) -> dict:
    """Safe-default checkbox state: every field KlubPro has a value for is ticked.

    - Any non-empty KlubPro value → checked (incl. when it differs from BS).
    - profile_image → checked whenever KlubPro has an image (the operator can
      untick it to keep a newer BetterStats photo).
    - KlubPro empty/missing → unchecked (and a populated BS value is never blanked).
    """
    inc = _incoming_map(candidate)
    out = {}
    for f in MIGRATABLE_FIELDS:
        if f == "profile_image":
            out[f] = inc[f] is not None
        else:
            out[f] = not _field_empty(f, inc[f])
    return out


def _differ(field: str, a: Any, b: Any) -> bool:
    if field == "skill_positions":
        return _skills_differ(a, b)
    return a != b


def plan_player(current: dict, candidate: dict, migrate_fields: Optional[dict]) -> list[dict]:
    """Per-field migration plan honouring the stored `migrate_fields` selections.

    Returns one row per migratable field with: current, incoming, recommended,
    selected (what the operator chose, defaulting to recommended for any field a
    legacy/empty `migrate_fields` omits), differ (BetterStats vs KlubPro), and
    will_apply (what the import will actually write). The import and the dry-run
    both read this so they always agree.
    """
    inc = _incoming_map(candidate)
    cur = _current_map(current)
    rec = recommended_fields(current, candidate)
    mf = migrate_fields or {}
    plans = []
    for f, label in PLAYER_FIELD_LABELS.items():
        selected = bool(mf.get(f, rec[f]))
        empty = _field_empty(f, inc[f])
        differ = _differ(f, inc[f], cur[f])
        if f == "profile_image":
            # Opt-in replace: when selected and KlubPro has an image, apply it
            # (overwrite allowed — the operator ticked it); byte-diff can't be
            # previewed so we apply whenever it differs in presence or selected.
            will_apply = selected and (inc[f] is not None)
        else:
            will_apply = selected and (not empty) and differ
        plans.append({
            "field": f, "label": label,
            "current": cur[f], "incoming": inc[f],
            "recommended": rec[f], "selected": selected,
            "differ": differ, "skipped_empty": empty,
            "change": will_apply,
        })
    return plans


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
    # LEFT JOIN club_mappings so every staged club row carries its current
    # mapping (or NULL) — drives the editable "Mapped To" column.
    rows = await kp.execute(text("""
        SELECT s.klubpro_club_id, s.klubpro_club_name, s.stage_status,
               s.staged_players, s.players_with_skills, s.players_with_email,
               s.players_with_mobile, s.players_with_gender, s.players_with_image,
               s.players_with_all_required_data, s.staged_sponsors, s.sponsors_with_logo,
               cm.betterstats_organisation_id, cm.betterstats_organisation_name,
               cm.migration_status
        FROM klubpro_migration.onboarding_staging_summary s
        LEFT JOIN klubpro_migration.club_mappings cm
          ON cm.klubpro_club_id = s.klubpro_club_id
        ORDER BY s.klubpro_club_name
    """))
    out = []
    for r in rows.mappings().all():
        d = dict(r)
        d["betterstats_organisation_id"] = (
            str(d["betterstats_organisation_id"]) if d["betterstats_organisation_id"] else None
        )
        out.append(d)
    return out


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


async def fetch_target_club(kp: AsyncSession, klubpro_club_id: str) -> Optional[dict]:
    """The KlubPro onboarding target — the authoritative name for a club id."""
    row = await kp.execute(text("""
        SELECT klubpro_club_id, klubpro_club_name
        FROM klubpro_migration.onboarding_targets
        WHERE klubpro_club_id = :cid
    """), {"cid": klubpro_club_id})
    r = row.mappings().first()
    return dict(r) if r else None


async def org_mapped_elsewhere(kp: AsyncSession, org_id: str, klubpro_club_id: str) -> Optional[dict]:
    """If this BetterStats org is already mapped to a DIFFERENT KlubPro club,
    return that other mapping (so the caller can warn before overwriting)."""
    row = await kp.execute(text("""
        SELECT klubpro_club_id, klubpro_club_name
        FROM klubpro_migration.club_mappings
        WHERE betterstats_organisation_id = :org AND klubpro_club_id <> :cid
        LIMIT 1
    """), {"org": str(org_id), "cid": klubpro_club_id})
    r = row.mappings().first()
    return dict(r) if r else None


async def upsert_club_mapping(
    kp: AsyncSession,
    *,
    klubpro_club_id: str,
    klubpro_club_name: str,
    betterstats_organisation_id: str,
    betterstats_organisation_name: str,
) -> dict:
    """Map a KlubPro club to a BetterStats org — repeatable / update-safe.

    UPDATE-or-INSERT (never DELETE) so an existing mapping's row id is preserved
    and the player_match_mappings FK that references it stays valid. Then bumps
    the onboarding target's stage_status to 'mapped' (keeping 'validated').
    """
    existing = await kp.execute(text("""
        SELECT id FROM klubpro_migration.club_mappings WHERE klubpro_club_id = :cid
    """), {"cid": klubpro_club_id})
    row = existing.mappings().first()
    params = {
        "org": str(betterstats_organisation_id),
        "oname": betterstats_organisation_name,
        "cid": klubpro_club_id,
        "kname": klubpro_club_name,
    }
    if row:
        await kp.execute(text("""
            UPDATE klubpro_migration.club_mappings
            SET betterstats_organisation_id = :org,
                betterstats_organisation_name = :oname,
                klubpro_club_name = :kname,
                klubpro_club_deleted = false,
                migration_status = 'mapped',
                updated_at = now()
            WHERE klubpro_club_id = :cid
        """), params)
        mapping_id = str(row["id"])
    else:
        ins = await kp.execute(text("""
            INSERT INTO klubpro_migration.club_mappings
                (id, betterstats_organisation_id, betterstats_organisation_name,
                 klubpro_club_id, klubpro_club_name, klubpro_club_deleted,
                 migration_status, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :org, :oname, :cid, :kname, false,
                 'mapped', now(), now())
            RETURNING id
        """), params)
        mapping_id = str(ins.scalar())

    # Keep the onboarding target's lifecycle in step (don't downgrade 'validated').
    await kp.execute(text("""
        UPDATE klubpro_migration.onboarding_targets
        SET stage_status = CASE WHEN stage_status = 'validated' THEN 'validated' ELSE 'mapped' END,
            updated_at = now()
        WHERE klubpro_club_id = :cid
    """), {"cid": klubpro_club_id})
    await kp.commit()
    return {"id": mapping_id, "klubpro_club_id": klubpro_club_id,
            "betterstats_organisation_id": str(betterstats_organisation_id),
            "betterstats_organisation_name": betterstats_organisation_name}

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


_match_columns_ensured = False


async def ensure_match_columns(kp: AsyncSession) -> None:
    """Idempotently add the field-level-approval columns to the KlubPro match
    table. KlubPro is external (not in our Alembic), so we run defensive ALTERs
    once per process the first time a migration endpoint touches the table."""
    global _match_columns_ensured
    if _match_columns_ensured:
        return
    await kp.execute(text(
        "ALTER TABLE klubpro_migration.player_match_mappings "
        "ADD COLUMN IF NOT EXISTS migrate_fields jsonb NOT NULL DEFAULT '{}'::jsonb"
    ))
    for col, typ in (
        ("reviewed_at", "timestamptz"), ("reviewed_by", "text"),
        ("imported_at", "timestamptz"), ("imported_by", "text"),
    ):
        await kp.execute(text(
            f"ALTER TABLE klubpro_migration.player_match_mappings "
            f"ADD COLUMN IF NOT EXISTS {col} {typ}"
        ))
    await kp.commit()
    _match_columns_ensured = True


async def fetch_match_mappings(kp: AsyncSession, club_mapping_id: uuid.UUID) -> list[dict]:
    await ensure_match_columns(kp)
    rows = await kp.execute(text("""
        SELECT betterstats_player_id, betterstats_player_name, klubpro_player_id,
               klubpro_player_firstname, klubpro_player_lastname,
               klubpro_player_nickname, match_status, match_score,
               COALESCE(approved, false) AS approved, notes,
               COALESCE(migrate_fields, '{}'::jsonb) AS migrate_fields,
               reviewed_at, reviewed_by, imported_at, imported_by
        FROM klubpro_migration.player_match_mappings
        WHERE club_mapping_id = :cmid
    """), {"cmid": str(club_mapping_id)})
    out = []
    for r in rows.mappings().all():
        d = dict(r)
        d["betterstats_player_id"] = str(d["betterstats_player_id"]) if d["betterstats_player_id"] else None
        d["match_score"] = float(d["match_score"]) if d["match_score"] is not None else None
        mf = d.get("migrate_fields")
        d["migrate_fields"] = mf if isinstance(mf, dict) else (json.loads(mf) if isinstance(mf, str) and mf else {})
        for k in ("reviewed_at", "imported_at"):
            d[k] = d[k].isoformat() if d.get(k) else None
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
    migrate_fields: Optional[dict] = None,
    reviewed_by: Optional[str] = None,
    commit: bool = True,
) -> None:
    """Record an operator decision (incl. field-level selections on approve).
    Keyed on (club_mapping_id, betterstats_player_id).

    Reject/skip **UPDATE the existing row in place** rather than re-inserting, so
    we never null an existing ``klubpro_player_id`` (the column may be NOT NULL)
    and never re-insert a row that could trip a constraint. ``match_status`` is
    normalised to the past-tense lifecycle values (approved/rejected/skipped) the
    KlubPro schema uses — sending the imperative 'reject'/'skip' was the cause of
    the reject error.
    """
    await ensure_match_columns(kp)
    status = {"approve": "approved", "reject": "rejected", "skip": "skipped"}.get(match_status, match_status)
    base = {"cmid": str(club_mapping_id), "bpid": str(betterstats_player_id)}

    if not approved:
        # reject / skip — flip the existing decision without touching the match id
        existing = await kp.execute(text(
            "SELECT id FROM klubpro_migration.player_match_mappings "
            "WHERE club_mapping_id = :cmid AND betterstats_player_id = :bpid"
        ), base)
        if existing.first():
            await kp.execute(text("""
                UPDATE klubpro_migration.player_match_mappings
                SET approved = false, match_status = :status, migrate_fields = '{}'::jsonb,
                    reviewed_at = NOW(), reviewed_by = :rby, updated_at = NOW()
                WHERE club_mapping_id = :cmid AND betterstats_player_id = :bpid
            """), {**base, "status": status, "rby": reviewed_by})
        elif klubpro_player_id:
            await kp.execute(text("""
                INSERT INTO klubpro_migration.player_match_mappings
                    (id, club_mapping_id, betterstats_player_id, betterstats_player_name,
                     klubpro_player_id, klubpro_player_firstname, klubpro_player_lastname,
                     klubpro_player_nickname, match_status, approved, notes, migrate_fields,
                     reviewed_at, reviewed_by, created_at, updated_at)
                VALUES (gen_random_uuid(), :cmid, :bpid, :bname, :kpid, :kfn, :kln, :knn,
                        :status, false, :notes, '{}'::jsonb, NOW(), :rby, NOW(), NOW())
            """), {**base, "bname": betterstats_player_name, "kpid": klubpro_player_id,
                   "kfn": klubpro_player_firstname, "kln": klubpro_player_lastname,
                   "knn": klubpro_player_nickname, "status": status, "notes": notes, "rby": reviewed_by})
        # else: nothing matched to reject/skip — no-op
        if commit:
            await kp.commit()
        return

    # approve — replace the row with the approved decision (klubpro_player_id present)
    await kp.execute(text(
        "DELETE FROM klubpro_migration.player_match_mappings "
        "WHERE club_mapping_id = :cmid AND betterstats_player_id = :bpid"
    ), base)
    await kp.execute(text("""
        INSERT INTO klubpro_migration.player_match_mappings
            (id, club_mapping_id, betterstats_player_id, betterstats_player_name,
             klubpro_player_id, klubpro_player_firstname, klubpro_player_lastname,
             klubpro_player_nickname, match_status, approved, notes, migrate_fields,
             reviewed_at, reviewed_by, created_at, updated_at)
        VALUES
            (gen_random_uuid(), :cmid, :bpid, :bname, :kpid, :kfn, :kln, :knn,
             :status, true, :notes, CAST(:mf AS jsonb), NOW(), :rby, NOW(), NOW())
    """), {
        **base, "bname": betterstats_player_name, "kpid": klubpro_player_id,
        "kfn": klubpro_player_firstname, "kln": klubpro_player_lastname,
        "knn": klubpro_player_nickname, "status": status, "notes": notes,
        "mf": json.dumps(migrate_fields or {}), "rby": reviewed_by,
    })
    if commit:
        await kp.commit()


async def bulk_approve_matches(kp: AsyncSession, club_mapping_id: uuid.UUID, items: list[dict],
                               reviewed_by: Optional[str]) -> list[dict]:
    """Approve many matches at once, each with its own field selections. Existing
    rows supply the descriptive KlubPro name columns. Returns item-level results."""
    await ensure_match_columns(kp)
    existing = {m["betterstats_player_id"]: m for m in await fetch_match_mappings(kp, club_mapping_id)}
    results = []
    for it in items:
        bpid = it.get("betterstats_player_id")
        kpid = it.get("klubpro_player_id") or (existing.get(bpid) or {}).get("klubpro_player_id")
        if not bpid or not kpid or _uuid(bpid) is None:
            results.append({"betterstats_player_id": bpid, "ok": False,
                            "error": "needs a betterstats_player_id and a matched klubpro_player_id"})
            continue
        prev = existing.get(bpid) or {}
        try:
            # commit per item so a DB failure on one can't poison the others
            # (a failed statement aborts the whole asyncpg transaction).
            await upsert_match_mapping(
                kp,
                club_mapping_id=club_mapping_id,
                betterstats_player_id=_uuid(bpid),
                betterstats_player_name=prev.get("betterstats_player_name") or it.get("betterstats_player_name"),
                klubpro_player_id=kpid,
                klubpro_player_firstname=prev.get("klubpro_player_firstname") or it.get("klubpro_player_firstname"),
                klubpro_player_lastname=prev.get("klubpro_player_lastname") or it.get("klubpro_player_lastname"),
                klubpro_player_nickname=prev.get("klubpro_player_nickname") or it.get("klubpro_player_nickname"),
                match_status="approved", approved=True, notes=prev.get("notes"),
                migrate_fields=it.get("migrate_fields") or {}, reviewed_by=reviewed_by,
                commit=True,
            )
            results.append({"betterstats_player_id": bpid, "ok": True})
        except Exception as e:  # item-level error reporting; keep the rest going
            await kp.rollback()
            results.append({"betterstats_player_id": bpid, "ok": False, "error": str(e)})
    return results


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

async def fetch_all_orgs(bs: AsyncSession) -> list[dict]:
    """Every BetterStats organisation (id + name) — the mapping dropdown source."""
    rows = await bs.execute(select(Organisation.id, Organisation.name).order_by(Organisation.name))
    return [{"id": str(r.id), "name": r.name} for r in rows.all()]


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

def _bs_player_dict(player: Player) -> dict:
    """A Player ORM row in the shape plan_player / _current_map expect."""
    return {
        "gender": player.gender, "email": player.email, "phone": player.phone,
        "player_role": player.player_role, "batting_hand": player.batting_hand,
        "bowling_type": player.bowling_type,
        "is_opening_batsman": player.is_opening_batsman,
        "skill_positions": list(player.skill_positions or []),
        "has_photo": player.photo_data is not None,
    }


def _apply_plan(player: Player, candidate: dict, plans: list[dict]) -> tuple[list[str], list[str]]:
    """Write the will_apply fields onto the player.

    Returns (applied, skipped). `skipped` = fields the operator excluded or that
    had no usable KlubPro value; a selected field whose value already matches is
    neither (it's in sync). A populated value is never blanked.
    """
    incoming = _incoming_map(candidate)
    applied, skipped_fields = [], []
    for p in plans:
        f = p["field"]
        if not p["change"]:
            if (not p["selected"]) or p["skipped_empty"]:
                skipped_fields.append(f)
            continue
        if f == "profile_image":
            if candidate.get("profile_image_data"):
                player.photo_data = bytes(candidate["profile_image_data"])
                player.photo_mime = candidate.get("profile_image_mime") or "image/png"
                applied.append(f)
        elif f == "skill_positions":
            player.skill_positions = _as_list(candidate.get("betterstats_skill_positions"))
            applied.append(f)
        elif f == "is_opening_batsman":
            player.is_opening_batsman = True
            applied.append(f)
        else:
            setattr(player, f, incoming[f])
            applied.append(f)
    return applied, skipped_fields


async def execute_player_import(
    bs: AsyncSession,
    kp: AsyncSession,
    *,
    org_id: uuid.UUID,
    club_mapping: dict,
    operator,  # User
) -> dict:
    """Apply every approved match, honouring each one's stored migrate_fields.

    Backs up each row first. Only fields the operator selected (and that have a
    non-empty KlubPro value) are written — a populated BetterStats value is never
    blanked. Returns {batch_id, updated, skipped, field_writes}.
    """
    club_mapping_id = _uuid(club_mapping["id"])
    matches = await fetch_match_mappings(kp, club_mapping_id)
    approved = [m for m in matches if m.get("approved") and m.get("klubpro_player_id")]
    operator_name = getattr(operator, "display_name", None) or getattr(operator, "username", None)

    batch = KlubproMigrationBatch(
        kind="player", organisation_id=org_id, club_mapping_id=club_mapping_id,
        klubpro_club_id=club_mapping.get("klubpro_club_id"), status="imported",
        operator_user_id=getattr(operator, "id", None), operator_name=operator_name,
    )
    bs.add(batch)
    await bs.flush()  # get batch.id

    updated = 0
    skipped = 0
    field_writes = 0
    imported_pids = []
    for m in approved:
        player = await bs.get(Player, _uuid(m["betterstats_player_id"]))
        if not player or player.organisation_id != org_id:
            skipped += 1
            continue
        cand = await fetch_player_candidate(kp, m["klubpro_player_id"])
        if not cand:
            skipped += 1
            continue

        current = _bs_player_dict(player)
        plans = plan_player(current, cand, m.get("migrate_fields"))
        before = _player_before(player)
        applied, skipped_fields = _apply_plan(player, cand, plans)

        if not applied:
            skipped += 1
            continue

        field_writes += len(applied)
        bs.add(KlubproMigrationBackup(
            batch_id=batch.id, target_table="players", target_id=player.id,
            action="update", before_data=before,
            after_data={**_player_before(player),
                        "_player_name": m.get("betterstats_player_name") or player.name,
                        "_klubpro_player_id": m.get("klubpro_player_id"),
                        "_applied_fields": applied, "_skipped_fields": skipped_fields},
        ))
        imported_pids.append(m["betterstats_player_id"])
        updated += 1

    batch.counts = {"updated": updated, "skipped": skipped, "field_writes": field_writes}
    await bs.commit()

    # Stamp imported_at/by on the KlubPro mappings we wrote (audit trail). The BS
    # import already committed above, so a stamping hiccup must never fail it.
    if imported_pids:
        try:
            for pid in imported_pids:
                await kp.execute(text("""
                    UPDATE klubpro_migration.player_match_mappings
                    SET imported_at = NOW(), imported_by = :by
                    WHERE club_mapping_id = :cmid AND betterstats_player_id = :pid
                """), {"by": operator_name, "cmid": str(club_mapping_id), "pid": pid})
            await kp.commit()
        except Exception:
            await kp.rollback()

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
