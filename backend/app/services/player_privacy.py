"""Hiding a player at their own request (migration 316).

A person who asks to be taken off the public site is not a club's call to
reverse. ``players.is_public`` (migration 265) already hides a player from the
public roster, search, profile, leaderboards, records, sitemap and share card.
This module adds the part that makes it a REQUEST:

  * ``privacy_hidden_at`` / ``_by`` / ``_reason`` on the row, so the reason is
    written down where the next person looks;
  * the player's photographs are removed, here and in BetterIQ's scouting copy;
  * while the marker is set, a club admin's profile edit, a bulk profile import
    and a photo upload may not switch the player back on;
  * an audit entry the club can read.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It hides EVERY club's row for the same person (the Cricket Australia participant
id is shared, the ``players`` row is per club) and records a suppression keyed on
that id, so a row minted LATER (a new club, a fixture another club syncs) is
created hidden too.

It never deletes the ``players`` row or anything the player did. The club's own
match records (scorecards, partnerships, ladders, the other players' figures)
hang off it, and a deleted row is simply re-created by the next sync. The row
stays, marked, which is also why the person is not re-imported.

It does NOT mask the name inside a public scorecard, a fall-of-wickets line or
a dismissal string ("c Smith b Jones"): those are the match record, and the
same lines are public on Cricket Australia. See the guide for the open decision.

Photographs cannot be restored by :func:`restore_public`: keeping a copy would
defeat the request. Only the hidden state comes back.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ManualEditLog, Player

# What a club admin is told when they try to undo a person's request.
HOLD_MESSAGE = (
    "This player asked to be removed from the public website, so they cannot be "
    "switched back on or given a photo here. Contact BetterSports support if "
    "that has changed."
)

AUDIT_HIDE = "privacy_hide"
AUDIT_RESTORE = "privacy_restore"


def is_privacy_hidden(player: Optional[Player]) -> bool:
    """Did this person ask to be hidden? The one definition every guard reads."""
    return bool(player is not None and getattr(player, "privacy_hidden_at", None) is not None)


def _unlink_upload(photo_url: Optional[str]) -> bool:
    """Remove a legacy on-disk headshot (``/uploads/players/...``), if there is one."""
    if not photo_url or not photo_url.startswith("/uploads/players/"):
        return False
    p = Path("/app") / photo_url.lstrip("/")
    existed = p.exists()
    p.unlink(missing_ok=True)
    return existed


async def holdings(session: AsyncSession, player: Player) -> dict:
    """Everything we hold against this player, for the access request. Read-only.

    Counts rows in every table with a foreign key to ``players(id)``, read from
    the live catalogue so a table added later is not missed, plus the places a
    person can sit WITHOUT a foreign key: BetterIQ's scouting copy (keyed on the
    Cricket Australia participant id) and the people spine.
    """
    fk_tables = (await session.execute(text("""
        SELECT cl.relname AS tbl, att.attname AS col
          FROM pg_constraint c
          JOIN pg_class cl   ON cl.oid = c.conrelid
          JOIN pg_class ref  ON ref.oid = c.confrelid
          JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = ANY(c.conkey)
         WHERE c.contype = 'f' AND ref.relname = 'players' AND array_length(c.conkey, 1) = 1
         ORDER BY cl.relname, att.attname
    """))).fetchall()

    linked: list[dict] = []
    for tbl, col in fk_tables:
        # Identifiers come from pg_catalog, never from a caller.
        n = await session.scalar(
            text(f'SELECT COUNT(*) FROM "{tbl}" WHERE "{col}" = :pid'), {"pid": player.id}
        )
        if n:
            linked.append({"table": tbl, "column": col, "rows": int(n)})

    scouted = (await session.execute(text("""
        SELECT id, source, club_name, grade_name,
               (photo_data IS NOT NULL OR photo_url IS NOT NULL) AS has_photo
          FROM scouted_players
         WHERE internal_player_id = :pid
            OR (CAST(:guid AS TEXT) IS NOT NULL AND grassroots_participant_id = CAST(:guid AS TEXT))
    """), {"pid": player.id, "guid": player.grassroots_id})).fetchall()

    sibs = await siblings(session, player)
    suppressed = await is_suppressed(session, person_key(player))
    from app.services import privacy_email
    addrs = sorted(await privacy_email.addresses_for_players(session, [player.id] + [sp.id for sp in sibs]))
    return {
        "email_addresses": addrs,
        # None, not False, when there is nothing to block: False reads as "not
        # protected". The block is derived from the records at each send, so an
        # address added later is refused too.
        "email_blocked": (all([await privacy_email.is_removed_address(a, session) for a in addrs]) if addrs else None),
        "email_note": ("no email address is on record, so there is nothing to block yet; one added later is blocked automatically"
                       if not addrs else "every address on record is blocked"),
        "other_club_rows": [
            {"id": str(sp.id), "organisation_id": str(sp.organisation_id), "name": sp.name,
             "is_public": sp.is_public is not False, "has_photo": bool(sp.photo_data or sp.photo_url)}
            for sp in sibs
        ],
        "suppressed": bool(suppressed),
        "player": {
            "id": str(player.id),
            "name": player.name,
            "grassroots_id": player.grassroots_id,
            "organisation_id": str(player.organisation_id) if player.organisation_id else None,
            "is_public": player.is_public is not False,
            "has_photo": bool(player.photo_data or player.photo_url),
            "has_action_photo": bool(player.hero_photo_data or player.hero_photo_url),
            "has_email": bool(player.email),
            "has_phone": bool(player.phone),
            "has_date_of_birth": player.date_of_birth is not None,
            "privacy_hidden_at": player.privacy_hidden_at.isoformat() if player.privacy_hidden_at else None,
        },
        "linked_tables": linked,
        "scouting_copies": [
            {"id": str(r[0]), "source": r[1], "club": r[2], "grade": r[3], "has_photo": bool(r[4])}
            for r in scouted
        ],
    }


async def hide_at_request(
    session: AsyncSession,
    player: Player,
    *,
    by: str,
    reason: str,
    remove_photos: bool = True,
    include_siblings: bool = True,
) -> dict:
    """Hide a PERSON at their own request: this row, every other club's row for
    the same participant id, and a suppression for rows created later.
    Idempotent; caller commits. Returns what changed on THIS row, plus
    ``siblings`` (the other rows hidden) and ``suppression_recorded``.
    """
    out = await _hide_one(session, player, by=by, reason=reason, remove_photos=remove_photos)
    out["siblings"] = []
    if include_siblings:
        for sib in await siblings(session, player):
            res = await _hide_one(session, sib, by=by, reason=reason, remove_photos=remove_photos)
            out["siblings"].append({"id": str(sib.id), "organisation_id": str(sib.organisation_id), **res})
    await session.execute(text("""
        INSERT INTO player_privacy_suppressions (grassroots_id, reason, created_by)
        SELECT :g, :r, :b
         WHERE NOT EXISTS (SELECT 1 FROM player_privacy_suppressions WHERE grassroots_id = :g)
    """), {"g": person_key(player), "r": reason, "b": by})
    out["suppression_recorded"] = True
    out["emails"] = await _suppress_emails(
        session, [player] + (await siblings(session, player) if include_siblings else []), reason, by)
    from app.services import privacy_scrub
    privacy_scrub.forget()
    return out


async def _suppress_emails(session: AsyncSession, players: list, reason: str, by: str) -> dict:
    """No email to this person, from any module.

    Every address on record goes on the global suppression list (marked so a club
    cannot lift it), and each BetterComms contact for them is excluded. Contacts
    are kept, never deleted: an exclusion is a decision somebody made. The send
    guard in services/privacy_email also derives the addresses live, so one added
    later is covered without re-running this.
    """
    from app.services import email_suppression, privacy_email
    addrs = await privacy_email.addresses_for_players(session, [p.id for p in players])
    added = 0
    for a in sorted(addrs):
        if await email_suppression.add_privacy_suppression(session, a, f"{reason} ({by})"):
            added += 1
    res = await session.execute(text("""
        UPDATE comms_contacts
           SET excluded = TRUE, excluded_at = COALESCE(excluded_at, NOW())
         WHERE excluded IS NOT TRUE
           AND (LOWER(email) = ANY(:addrs)
                OR player_id::text = ANY(:pids)
                OR member_id IN (SELECT id FROM fee_members WHERE player_id::text = ANY(:pids)))
    """), {"addrs": list(addrs), "pids": [str(p.id) for p in players]})
    privacy_email.forget()
    return {"addresses": sorted(addrs), "suppressions_added": added, "contacts_excluded": res.rowcount or 0}


async def _hide_one(
    session: AsyncSession,
    player: Player,
    *,
    by: str,
    reason: str,
    remove_photos: bool = True,
) -> dict:
    """Mark ONE row hidden at the person's request. Idempotent; caller commits."""
    changed = {"already_hidden": is_privacy_hidden(player), "photos_removed": [], "scouting_photos_cleared": 0}

    before = {
        "is_public": player.is_public is not False,
        "privacy_hidden_at": player.privacy_hidden_at.isoformat() if player.privacy_hidden_at else None,
        "had_photo": bool(player.photo_data or player.photo_url),
        "had_action_photo": bool(player.hero_photo_data or player.hero_photo_url),
    }

    player.is_public = False
    if player.privacy_hidden_at is None:
        player.privacy_hidden_at = datetime.now(timezone.utc)
    player.privacy_hidden_by = by
    player.privacy_hidden_reason = reason

    if remove_photos:
        if player.photo_data or player.photo_url:
            _unlink_upload(player.photo_url)
            player.photo_data = None
            player.photo_mime = None
            player.photo_url = None
            changed["photos_removed"].append("photo")
        if player.hero_photo_data or player.hero_photo_url:
            player.hero_photo_data = None
            player.hero_photo_mime = None
            player.hero_photo_url = None
            changed["photos_removed"].append("action photo")

        # BetterIQ keeps its own copy for a scouted opponent, keyed on the
        # Cricket Australia participant id and, for a club's own player, on
        # internal_player_id. A scouting card with a photo of him is the same
        # photograph under another table name.
        res = await session.execute(text("""
            UPDATE scouted_players
               SET photo_data = NULL, photo_mime = NULL, photo_url = NULL
             WHERE (internal_player_id = :pid
                    OR (CAST(:guid AS TEXT) IS NOT NULL AND grassroots_participant_id = CAST(:guid AS TEXT)))
               AND (photo_data IS NOT NULL OR photo_url IS NOT NULL)
        """), {"pid": player.id, "guid": player.grassroots_id})
        changed["scouting_photos_cleared"] = res.rowcount or 0

    if player.organisation_id:
        session.add(ManualEditLog(
            organisation_id=player.organisation_id,
            user_id=None,
            action=AUDIT_HIDE,
            target_table="players",
            target_id=str(player.id),
            summary=f"Hidden from the public site at the player's request ({by})",
            before_json=before,
            after_json={"is_public": False, "reason": reason, **{k: v for k, v in changed.items() if k != "already_hidden"}},
        ))
    return changed


async def restore_public(session: AsyncSession, player: Player, *, by: str) -> dict:
    """Put a person back on the public site (every club's row, and the
    suppression). Photographs are NOT restored."""
    for sib in await siblings(session, player):
        if is_privacy_hidden(sib):
            await _restore_one(session, sib, by=by)
    await session.execute(
        text("DELETE FROM player_privacy_suppressions WHERE grassroots_id = :g"), {"g": person_key(player)})
    # Lift the email block this removal recorded. Contacts the removal excluded
    # stay excluded (an admin re-includes them): restoring must never re-email
    # someone by itself.
    from app.services import privacy_email
    people = [player] + await siblings(session, player)
    for addr in await privacy_email.addresses_for_players(session, [p.id for p in people]):
        await session.execute(text(
            "DELETE FROM email_suppressions WHERE LOWER(email) = :e AND source = 'privacy_request'"), {"e": addr})
    privacy_email.forget()
    from app.services import privacy_scrub
    privacy_scrub.forget()
    return await _restore_one(session, player, by=by)


async def _restore_one(session: AsyncSession, player: Player, *, by: str) -> dict:
    was = is_privacy_hidden(player)
    player.is_public = True
    player.privacy_hidden_at = None
    player.privacy_hidden_by = None
    player.privacy_hidden_reason = None
    if player.organisation_id:
        session.add(ManualEditLog(
            organisation_id=player.organisation_id,
            user_id=None,
            action=AUDIT_RESTORE,
            target_table="players",
            target_id=str(player.id),
            summary=f"Put back on the public site ({by})",
            before_json={"privacy_hidden": was},
            after_json={"is_public": True},
        ))
    return {"was_hidden": was}


def person_key(player: Player) -> str:
    """The Cricket Australia participant id this row stands for.

    ``grassroots_id`` when set (a per-club row), else the row's own id (the
    legacy scheme keeps the raw participant id as the primary key).
    """
    return str(player.grassroots_id or player.id).lower()


async def siblings(session: AsyncSession, player: Player) -> list[Player]:
    """Every OTHER club's row for the same person."""
    key = person_key(player)
    rows = (await session.execute(text("""
        SELECT id FROM players
         WHERE id <> :pid
           AND (LOWER(grassroots_id) = :k OR LOWER(id::text) = :k)
    """), {"pid": player.id, "k": key})).scalars().all()
    out = []
    for pid in rows:
        p = await session.get(Player, pid)
        if p is not None:
            out.append(p)
    return out


async def is_suppressed(session: AsyncSession, guid: Optional[str]) -> Optional[dict]:
    """The suppression for a participant id, or None. Never raises: a missing
    table (a database that has not run migration 316) reads as 'nobody asked'
    rather than breaking player creation. The savepoint keeps a failed lookup
    from aborting the caller's transaction."""
    if not guid:
        return None
    try:
        async with session.begin_nested():
            row = (await session.execute(
                text("SELECT reason, created_by FROM player_privacy_suppressions WHERE grassroots_id = :g"),
                {"g": str(guid).lower()},
            )).first()
    except Exception:
        return None
    return {"reason": row[0], "by": row[1]} if row else None


async def protect_new_player(session: AsyncSession, player: Player, guid: Optional[str] = None) -> bool:
    """Create-time guard: a new row for a person who asked to be removed is born hidden.

    Call it on a ``Player`` that is about to be added, from any creator that
    knows the participant id. Returns True when it hid the row. The photographs
    never come with a sync, so there is nothing to strip here.
    """
    hit = await is_suppressed(session, guid or player.grassroots_id or player.id)
    if not hit:
        return False
    player.is_public = False
    player.privacy_hidden_at = datetime.now(timezone.utc)
    player.privacy_hidden_by = hit["by"] or "suppression"
    player.privacy_hidden_reason = hit["reason"]
    return True


async def load_player(session: AsyncSession, raw_id: str) -> Optional[Player]:
    try:
        pid = uuid.UUID(str(raw_id))
    except (ValueError, TypeError):
        return None
    return await session.get(Player, pid)
