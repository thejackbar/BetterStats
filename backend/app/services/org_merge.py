"""Club merger — bulk-reassign one organisation's synced history onto another.

Built for a real-world club merger where the BetterCricket target org only
carries ONE of the merged clubs' PlayHQ/CA identities and the other club's
history sits under its own, still-separately-synced CA organisation (e.g.
Hilton Bicton ⟵ Hilton Palmyra + Bicton Attadale — Hilton Bicton's org is
Hilton Palmyra's identity; Bicton Attadale still exists as its own club in
PlayHQ). The flow:

  1. Sync the second club as its own temporary BetterCricket org — ordinary
     onboarding, no new code needed for that half.
  2. Call `merge_organisation(source=temp org, target=real club org)` — this
     module — to bulk-reassign every player/season/grade/game/leaf-stat row
     from the temp org onto the target, then archive the temp org (reversible
     via the existing club archive/restore flow).

Mirrors the existing per-row merge tools at org scale: a season/grade/player
that's genuinely the SAME real entity in both orgs (same `grassroots_id` — a
competition both clubs already independently synced, or a player who turned
out for both clubs historically) is MERGED onto the target's existing row,
exactly like a live sync's `_resolve_org_grade`/`_resolve_org_player` would
treat it. Anything with no counterpart in the target org is MOVED onto it
directly (organisation_id updated in place, same row id) — the common case
for a club whose history the target has never seen before.

Player merges are done via the real `admin._merge_players_core` (temporarily
re-homing the source player into the target org first, since that function
requires both players to already share an org) — so a colliding player gets
the SAME de-duplication and `merge_logs` audit trail, and the SAME real
`undo_merge`, as an ordinary same-club player merge.

Reversibility is PARTIAL — see `org_merge_logs`. Un-archiving the source org
does NOT undo the reassignment; season/grade/game moves and redirects have
no built-in undo in this first cut. A merged (collided) player DOES have a
real undo via the existing per-player `undo_merge`.

NOT handled (flagged, not silently mangled): a match where the two merging
clubs played EACH OTHER historically. After the merge both `home_org_id` and
`away_org_id` on that one shared game row would resolve to the SAME target
org — accurate in a sense (two clubs that are now one club used to play each
other) but a genuine display oddity; this tool repoints the game's grade_id
but does not attempt to rewrite home_org_id/away_org_id for that case.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, User


async def merge_organisation(
    db: AsyncSession,
    source_org_id: uuid.UUID,
    target_org_id: uuid.UUID,
    current_user: User,
) -> dict:
    if source_org_id == target_org_id:
        raise ValueError("Cannot merge an organisation into itself")

    source_org = await db.get(Organisation, source_org_id)
    target_org = await db.get(Organisation, target_org_id)
    if not source_org or not target_org:
        raise ValueError("Both organisations must exist")

    counts = {
        "seasons_moved": 0, "seasons_merged": 0,
        "grades_moved": 0, "grades_merged": 0,
        "games_repointed": 0,
        "players_moved": 0, "players_merged": 0,
    }

    # ── Seasons ──────────────────────────────────────────────────────────
    # season_redirect[source_season_id] = target_season_id, only populated
    # when the season was MERGED (collision) rather than moved in place.
    season_redirect: dict[uuid.UUID, uuid.UUID] = {}
    source_seasons = (await db.execute(
        text("SELECT id, grassroots_id FROM seasons WHERE organisation_id = :oid"),
        {"oid": str(source_org_id)},
    )).all()
    for sid, grassroots_id in source_seasons:
        target_match = None
        if grassroots_id:
            target_match = (await db.execute(
                text(
                    "SELECT id FROM seasons WHERE organisation_id = :oid AND grassroots_id = :gid LIMIT 1"
                ),
                {"oid": str(target_org_id), "gid": grassroots_id},
            )).scalar_one_or_none()
        if target_match:
            season_redirect[sid] = target_match
            counts["seasons_merged"] += 1
        else:
            await db.execute(
                text("UPDATE seasons SET organisation_id = :tid WHERE id = :sid"),
                {"tid": str(target_org_id), "sid": str(sid)},
            )
            counts["seasons_moved"] += 1

    # ── Grades ───────────────────────────────────────────────────────────
    # grade_redirect[source_grade_id] = target_grade_id, only populated when
    # the grade was MERGED (collision) rather than moved in place.
    grade_redirect: dict[uuid.UUID, uuid.UUID] = {}
    source_grades = (await db.execute(
        text("SELECT id, season_id, grassroots_id FROM grades WHERE season_id = ANY(:sids)"),
        {"sids": [sid for sid, _ in source_seasons]},
    )).all()
    for gid, season_id, grassroots_id in source_grades:
        effective_season_id = season_redirect.get(season_id, season_id)
        target_match = None
        if grassroots_id:
            target_match = (await db.execute(
                text(
                    "SELECT id FROM grades WHERE season_id = :sid AND grassroots_id = :gid LIMIT 1"
                ),
                {"sid": str(effective_season_id), "gid": grassroots_id},
            )).scalar_one_or_none()
        if target_match:
            grade_redirect[gid] = target_match
            counts["grades_merged"] += 1
        else:
            await db.execute(
                text("UPDATE grades SET season_id = :sid WHERE id = :gid"),
                {"sid": str(effective_season_id), "gid": str(gid)},
            )
            counts["grades_moved"] += 1

    # ── Games ────────────────────────────────────────────────────────────
    # Only grades that were MERGED (collision) need their games repointed —
    # a MOVED grade keeps its own id, so games under it are already
    # correctly parented via the grade's now-updated season_id chain.
    # games.id is a global PK (the raw CA match GUID); this UPDATEs the
    # EXISTING row's grade_id in place, it never creates or collides a row.
    for source_grade_id, target_grade_id in grade_redirect.items():
        result = await db.execute(
            text("UPDATE games SET grade_id = :tgid WHERE grade_id = :sgid"),
            {"tgid": str(target_grade_id), "sgid": str(source_grade_id)},
        )
        counts["games_repointed"] += result.rowcount or 0

    # ── Players ──────────────────────────────────────────────────────────
    from app.routers.admin import _merge_players_core

    # _merge_players_core commits internally on every call (existing
    # behaviour, unchanged here) — so a club merge with several colliding
    # players is NOT one atomic transaction; the season/grade/game work above
    # is flushed along with the first player commit. That's an accepted
    # trade-off for reusing the real, already-battle-tested dedup/undo logic
    # rather than re-deriving it (see module docstring). To stop one bad
    # pair from aborting the WHOLE merge, a per-player conflict is caught and
    # skipped (left re-homed under the target org, unmerged, for manual
    # reconciliation via the ordinary Merge Players tool) rather than raising.
    skipped_player_conflicts: list[dict] = []

    source_players = (await db.execute(
        text("SELECT id, grassroots_id FROM players WHERE organisation_id = :oid"),
        {"oid": str(source_org_id)},
    )).all()
    for pid, grassroots_id in source_players:
        target_match = None
        if grassroots_id:
            target_match = (await db.execute(
                text(
                    "SELECT id FROM players WHERE organisation_id = :oid AND grassroots_id = :gid LIMIT 1"
                ),
                {"oid": str(target_org_id), "gid": grassroots_id},
            )).scalar_one_or_none()
        if target_match:
            # _merge_players_core requires both players already in the SAME
            # org — re-home the source player into the target org first,
            # nulling grassroots_id in the same statement so the move itself
            # can't trip the UNIQUE(organisation_id, grassroots_id)
            # constraint against the very row it's about to be merged into
            # (harmless: this row is deleted by the merge moments later).
            await db.execute(
                text("UPDATE players SET organisation_id = :tid, grassroots_id = NULL WHERE id = :pid"),
                {"tid": str(target_org_id), "pid": str(pid)},
            )
            try:
                await _merge_players_core(db, target_match, pid, target_org_id, current_user)
                counts["players_merged"] += 1
            except HTTPException as exc:
                skipped_player_conflicts.append({
                    "source_player_id": str(pid),
                    "target_player_id": str(target_match),
                    "detail": exc.detail,
                })
        else:
            await db.execute(
                text("UPDATE players SET organisation_id = :tid WHERE id = :pid"),
                {"tid": str(target_org_id), "pid": str(pid)},
            )
            counts["players_moved"] += 1

    # ── Archive the source org ──────────────────────────────────────────
    source_org.archived_at = datetime.now(timezone.utc)
    await db.execute(
        text("UPDATE users SET active_club_id = NULL WHERE active_club_id = :oid"),
        {"oid": str(source_org_id)},
    )

    await db.execute(
        text("""
            INSERT INTO org_merge_logs (
                source_org_id, source_org_name, target_org_id, performed_by_user_id,
                seasons_moved, seasons_merged, grades_moved, grades_merged,
                games_repointed, players_moved, players_merged
            ) VALUES (
                :source_org_id, :source_org_name, :target_org_id, :performed_by_user_id,
                :seasons_moved, :seasons_merged, :grades_moved, :grades_merged,
                :games_repointed, :players_moved, :players_merged
            )
        """),
        {
            "source_org_id": str(source_org_id),
            "source_org_name": source_org.name,
            "target_org_id": str(target_org_id),
            "performed_by_user_id": str(current_user.id),
            **counts,
        },
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=target_org_id, user_id=current_user.id,
        action="merge_organisation", target_type="organisation", target_id=str(target_org_id),
        details={"source_org": {"id": str(source_org_id), "name": source_org.name}, **counts},
    )

    await db.commit()
    return {
        "source_org_id": str(source_org_id),
        "source_org_name": source_org.name,
        "target_org_id": str(target_org_id),
        **counts,
        "skipped_player_conflicts": skipped_player_conflicts,
    }
