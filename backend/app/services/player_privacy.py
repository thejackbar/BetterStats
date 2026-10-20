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
# privacy_hidden_by for a row held only because its NAME matches a removed person.
NAME_MATCH = "name-match"

NAME_MATCH_HOLD_MESSAGE = (
    "This player is held because the name matches a person who asked to be removed "
    "from the public website. If they are a different person, confirm that with "
    "'This is a different person' on their profile."
)

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


def is_name_match_hold(player: Optional[Player]) -> bool:
    """Hidden only because the name matches a removed person (an admin can release it)."""
    return bool(is_privacy_hidden(player) and getattr(player, "privacy_hidden_by", None) == NAME_MATCH)


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
    people = [player] + (await siblings(session, player) if include_siblings else [])
    out["names_recorded"] = await _record_names(session, player, people)
    out["name_matches_held"] = await _sweep_name_matches(session, person_key(player))
    out["emails"] = await _suppress_emails(
        session, [player] + (await siblings(session, player) if include_siblings else []), reason, by)
    from app.services import privacy_scrub
    privacy_scrub.forget()
    return out


async def _record_names(session: AsyncSession, player: Player, people: list) -> int:
    """Keep the person's names on the global record, so a hand-typed row with the
    same name can be recognised even if every row of theirs is gone. Names are
    stored as canonical keys (``privacy_name_key``); a single word never counts."""
    raw: set[str] = set()
    for p in people:
        for n in (p.name, getattr(p, "display_name_override", None)):
            if n and n.strip():
                raw.add(n)
    try:
        async with session.begin_nested():
            for pid, alias in (await session.execute(
                text("SELECT player_id::text, alias_name FROM player_name_aliases WHERE player_id::text = ANY(:ids)"),
                {"ids": [str(p.id) for p in people]},
            )).fetchall():
                if alias and alias.strip():
                    raw.add(alias)
    except Exception:
        pass  # a database without the aliases table: the names on the rows are enough
    res = await session.execute(text("""
        UPDATE player_privacy_suppressions
           SET names = COALESCE((
                 SELECT array_agg(DISTINCT k) FROM (
                     SELECT UNNEST(COALESCE(names, CAST('{}' AS TEXT[]))) AS k
                     UNION
                     SELECT privacy_name_key(n) FROM UNNEST(CAST(:raw AS TEXT[])) AS n
                 ) q
                 WHERE k IS NOT NULL AND array_length(string_to_array(k, ' '), 1) >= 2
                   AND NOT EXISTS (SELECT 1 FROM unnest(string_to_array(k, ' ')) w WHERE length(w) < 2)
               ), CAST('{}' AS TEXT[]))
         WHERE grassroots_id = :g
    """), {"raw": sorted(raw), "g": person_key(player)})
    return res.rowcount or 0


async def _sweep_name_matches(session: AsyncSession, key: str) -> int:
    """Hold every existing row with no participant id whose name is on the
    suppression. SET name = name makes the UPDATE trigger do the matching, so
    there is one rule, in the database."""
    res = await session.execute(text("""
        UPDATE players p SET name = p.name
         WHERE NULLIF(p.grassroots_id, '') IS NULL
           AND p.privacy_name_cleared_at IS NULL
           AND p.privacy_hidden_at IS NULL
           AND EXISTS (SELECT 1 FROM player_privacy_suppressions s
                        WHERE s.grassroots_id = :g
                          AND (privacy_name_key(p.name) = ANY(s.names)
                               OR privacy_name_key(to_jsonb(p) ->> 'display_name_override') = ANY(s.names)))
    """), {"g": key})
    return res.rowcount or 0


async def release_name_match(session: AsyncSession, player: Player, *, by: str, user_id=None) -> dict:
    """An admin confirms a row held only by name is a different person.

    Refuses anything that is not a name hold: a person's own request is lifted
    by BetterSports (``restore_public``), never by a club. Caller commits."""
    if not is_name_match_hold(player):
        raise ValueError("Only a hold placed because of a name match can be released here.")
    player.privacy_name_cleared_at = datetime.now(timezone.utc)
    player.privacy_hidden_at = None
    player.privacy_hidden_by = None
    player.privacy_hidden_reason = None
    player.is_public = True
    if player.organisation_id:
        session.add(ManualEditLog(
            organisation_id=player.organisation_id,
            user_id=user_id,
            action=AUDIT_RESTORE,
            target_table="players",
            target_id=str(player.id),
            summary=f"Confirmed a different person from a name match, and put back on the public site ({by})",
            before_json={"privacy_hidden_by": NAME_MATCH},
            after_json={"is_public": True, "privacy_name_cleared": True},
        ))
    from app.services import privacy_email, privacy_scrub
    privacy_scrub.forget()
    privacy_email.forget()
    return {"released": True}


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
    # The suppression goes FIRST: the database trigger keeps a suppressed person
    # hidden, so a row switched back on while the suppression stands would be
    # forced hidden again.
    await session.execute(
        text("DELETE FROM player_privacy_suppressions WHERE grassroots_id = :g"), {"g": person_key(player)})
    # Rows held only by this person's name are let go by the trigger (it lifts a
    # name hold that no longer matches any suppression).
    await session.execute(text("UPDATE players SET name = name WHERE privacy_hidden_by = :nm"), {"nm": NAME_MATCH})
    for sib in await siblings(session, player):
        if is_privacy_hidden(sib):
            await _restore_one(session, sib, by=by)
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


async def protect_restored_player(session: AsyncSession, restored: Player, keep: Optional[Player]) -> bool:
    """Undoing a merge re-creates the merged-away row with a raw INSERT, which
    skips ``protect_new_player``. Hide it again when the person asked: by the
    participant id, or because the row it was merged into is hidden (a merge
    joins two records of ONE person, and a merge carries the hide across, so a
    hidden keeper means the removed record was the person's too). Fails closed."""
    if await protect_new_player(session, restored, str(restored.grassroots_id or restored.id)):
        return True
    if keep is not None and is_privacy_hidden(keep):
        restored.is_public = False
        restored.privacy_hidden_at = keep.privacy_hidden_at or datetime.now(timezone.utc)
        restored.privacy_hidden_by = keep.privacy_hidden_by or "merge"
        restored.privacy_hidden_reason = keep.privacy_hidden_reason
        return True
    return False


async def load_player(session: AsyncSession, raw_id: str) -> Optional[Player]:
    try:
        pid = uuid.UUID(str(raw_id))
    except (ValueError, TypeError):
        return None
    return await session.get(Player, pid)


# ---------------------------------------------------------------------------
# What contact details do we hold? (read-only, for confirming to the person)
# ---------------------------------------------------------------------------

_CONTACT_COLUMN_RE = (
    r"(e[-_]?mail|phone|mobile|telephone|dob|birth|address|street|suburb|postcode|post_code|postal|city|town"
    r"|emergency|next_of_kin|\bkin\b)"
)
_FREE_TEXT_COLUMN_RE = r"^(notes?|comments?|description|details?|memo|remarks?)$"
_CATEGORIES = (
    ("email", r"e[-_]?mail"),
    ("phone", r"phone|mobile|telephone"),
    ("date_of_birth", r"dob|birth"),
    ("address", r"address|street|suburb|postcode|post_code|postal|city|town"),
    ("emergency_contact", r"emergency|next_of_kin|\bkin\b"),
)


async def contact_audit(session: AsyncSession, player: Player) -> dict:
    """Which contact details do we hold for this person, anywhere? Read-only.

    Looks at every table that records something against the person: the player
    rows, every table with a foreign key to them, every table hanging off their
    fee-membership and family records, and their sign-in account. In each it asks,
    for text and date columns whose name says email, phone, date of birth, address,
    emergency contact, whether any row of THEIRS has a value. It reports yes or no
    per column and never prints the value. Free-text fields (notes) are listed
    separately: a note can hold a number, so a person has to read them.

    It can only see this database. It says nothing about the club's own spreadsheets,
    Play-Cricket or PlayHQ registration, and the result says so.
    """
    import re
    people = [player] + await siblings(session, player)
    pids = [str(p.id) for p in people]

    async def children(parent: str, ids: list[str]) -> list[tuple[str, str, list[str]]]:
        """(table, fk column, ids) for every single-column FK onto parent(id)."""
        rows = (await session.execute(text("""
            SELECT cl.relname, att.attname
              FROM pg_constraint c
              JOIN pg_class cl  ON cl.oid = c.conrelid
              JOIN pg_class ref ON ref.oid = c.confrelid
              JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = ANY(c.conkey)
             WHERE c.contype = 'f' AND ref.relname = :p AND array_length(c.conkey, 1) = 1
        """), {"p": parent})).fetchall()
        return [(t, c, ids) for t, c in rows]

    scopes: list[tuple[str, str, list[str]]] = [("players", "id", pids)] + await children("players", pids)
    fee_ids = [r[0] for r in (await session.execute(
        text("SELECT id::text FROM fee_members WHERE player_id::text = ANY(:p)"), {"p": pids})).fetchall()]
    if fee_ids:
        scopes += await children("fee_members", fee_ids)
    fam_ids = [r[0] for r in (await session.execute(
        text("SELECT DISTINCT family_id::text FROM family_members WHERE player_id::text = ANY(:p)"),
        {"p": pids})).fetchall()]
    if fam_ids:
        scopes += [("families", "id", fam_ids)] + await children("families", fam_ids)
    user_ids = [str(p.user_id) for p in people if getattr(p, "user_id", None)]
    if user_ids:
        scopes.append(("users", "id", user_ids))

    found: dict[tuple[str, str], int] = {}
    free_text: dict[tuple[str, str], int] = {}
    tables_seen: set[str] = set()
    for table, fk, ids in scopes:
        cols = (await session.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = :t
               AND data_type IN ('text', 'character varying', 'character', 'date',
                                 'timestamp with time zone', 'timestamp without time zone')
        """), {"t": table})).scalars().all()
        for col in cols:
            contact = re.search(_CONTACT_COLUMN_RE, col, re.I)
            note = re.match(_FREE_TEXT_COLUMN_RE, col, re.I)
            if not (contact or note):
                continue
            # Identifiers come from the catalogue, never from a caller.
            n = await session.scalar(text(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{fk}"::text = ANY(:ids) '
                f'AND "{col}" IS NOT NULL AND TRIM("{col}"::text) <> \'\''), {"ids": ids})
            tables_seen.add(table)
            (found if contact else free_text)[(table, col)] = (found if contact else free_text).get((table, col), 0) + int(n or 0)

    summary = {}
    for name, rx in _CATEGORIES:
        summary[name] = any(n > 0 for (t, c), n in found.items() if re.search(rx, c, re.I))
    return {
        "scope": "this database only",
        "tables_checked": sorted({t for t, _, _ in scopes}),
        "summary": summary,
        "columns_with_a_value": [
            {"table": t, "column": c, "rows": n} for (t, c), n in sorted(found.items()) if n > 0],
        "columns_checked_and_empty": [
            {"table": t, "column": c} for (t, c), n in sorted(found.items()) if n == 0],
        "free_text_with_a_value_to_read_by_hand": [
            {"table": t, "column": c, "rows": n} for (t, c), n in sorted(free_text.items()) if n > 0],
        "not_covered": (
            "Applecross Cricket Club's own records outside BetterCricket (registration forms, spreadsheets, "
            "Play-Cricket, PlayHQ) and Cricket Australia's systems. Those have to be asked of the club and "
            "of Cricket Australia."),
    }
