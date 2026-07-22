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
        "season_stats_repointed": 0, "grade_stats_repointed": 0,
        "manual_games_moved": 0,
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

    # ── Leaf per-player-season stats ────────────────────────────────────────
    # player_season_stats / player_season_grade_stats reference season_id (and
    # grade_id) directly by FK — NOT via the game/grade chain — so a MERGED
    # (collided) season or grade leaves these rows silently pointing at the
    # OLD source-org season/grade row forever: it's never deleted (only a
    # MOVED season/grade updates its own organisation_id in place; a MERGED
    # one is left as-is, only recorded in season_redirect/grade_redirect for
    # the games repoint above). A player whose stats hang off a merged season
    # then has an org mismatch (their own organisation_id is now the target,
    # but their season's organisation_id is still the archived source) that
    # the cross-club-safety view (v_effective_player_season_stats) uses to
    # decide what's "theirs" — so the player's whole season of stats vanishes
    # from every view-based summary while remaining visible to any reader
    # that queries player_season_stats directly without checking the season's
    # org (e.g. a raw per-player analysis query). Must run before the Players
    # section below, since _merge_players_core reads/merges these rows by
    # season_id and needs the corrected value to detect a genuine same-season
    # collision (rather than silently duplicating a season under a stale id).
    if season_redirect:
        for source_season_id, target_season_id in season_redirect.items():
            result = await db.execute(
                text("""
                    UPDATE player_season_stats pss
                    SET season_id = :tid
                    FROM players p
                    WHERE pss.player_id = p.id
                      AND p.organisation_id = :source_org_id
                      AND pss.season_id = :sid
                """),
                {"tid": str(target_season_id), "sid": str(source_season_id), "source_org_id": str(source_org_id)},
            )
            counts["season_stats_repointed"] += result.rowcount or 0
            await db.execute(
                text("""
                    UPDATE player_season_grade_stats pgs
                    SET season_id = :tid
                    FROM players p
                    WHERE pgs.player_id = p.id
                      AND p.organisation_id = :source_org_id
                      AND pgs.season_id = :sid
                """),
                {"tid": str(target_season_id), "sid": str(source_season_id), "source_org_id": str(source_org_id)},
            )
    if grade_redirect:
        for source_grade_id, target_grade_id in grade_redirect.items():
            result = await db.execute(
                text("""
                    UPDATE player_season_grade_stats pgs
                    SET grade_id = :tid
                    FROM players p
                    WHERE pgs.player_id = p.id
                      AND p.organisation_id = :source_org_id
                      AND pgs.grade_id = :gid
                """),
                {"tid": str(target_grade_id), "gid": str(source_grade_id), "source_org_id": str(source_org_id)},
            )
            counts["grade_stats_repointed"] += result.rowcount or 0

    # ── Manual (photo-upload / hand-typed) games ─────────────────────────────
    # manual_games carries organisation_id/season_id/grade_id directly (it
    # isn't reached via grades → games at all), so it needs the same move +
    # redirect treatment as the synced Games above or it's silently orphaned
    # under the archived source org forever.
    source_manual_games = (await db.execute(
        text("SELECT id, season_id, grade_id FROM manual_games WHERE organisation_id = :oid"),
        {"oid": str(source_org_id)},
    )).all()
    for mgid, season_id, grade_id in source_manual_games:
        effective_season_id = season_redirect.get(season_id, season_id)
        effective_grade_id = grade_redirect.get(grade_id, grade_id) if grade_id else None
        await db.execute(
            text(
                "UPDATE manual_games SET organisation_id = :tid, season_id = :sid, grade_id = :gid WHERE id = :mgid"
            ),
            {"tid": str(target_org_id), "sid": str(effective_season_id), "gid": str(effective_grade_id) if effective_grade_id else None, "mgid": str(mgid)},
        )
        counts["manual_games_moved"] += 1

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


async def repair_organisation_merge_stats(
    db: AsyncSession, org_id: uuid.UUID, current_user: User,
) -> dict:
    """Retroactively fix the orphaned-season/grade-stats bug for a club that
    was already merged via `merge_organisation` before that repoint existed
    (or for any other reason ended up with this exact shape of stale row).

    Finds every `player_season_stats` / `player_season_grade_stats` row for a
    player CURRENTLY in `org_id` whose season (or grade) belongs to a
    DIFFERENT organisation — the state `merge_organisation` used to leave
    behind for a MERGED (collided) season/grade, since only the games repoint
    used the redirect; these per-player stat rows were never touched, so they
    silently point at the old, now-archived source org's season/grade forever
    and vanish from every view that checks the season's own org (while
    remaining visible to a raw, non-scoped reader — the exact "stats show in
    one tab but not another" symptom this repairs).

    Repointed via `grassroots_id` (the shared CA season/grade GUID) — the
    same identity `merge_organisation`/a live sync already use. A row with no
    same-GUID counterpart under `org_id` is left alone and reported (nothing
    to redirect it onto; needs a manual look). Idempotent — running it again
    finds nothing left to fix. Safe on a club that was never merged (no-op).
    """
    counts = {"season_stats_repointed": 0, "season_stats_deduped": 0,
              "grade_stats_repointed": 0, "grade_stats_deduped": 0}
    unresolved: list[dict] = []

    # ── player_season_stats ─────────────────────────────────────────────────
    orphan_pss = (await db.execute(
        text("""
            SELECT pss.id, pss.player_id, pss.season_id, s.grassroots_id
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            JOIN seasons s ON s.id = pss.season_id
            WHERE p.organisation_id = :oid AND s.organisation_id <> :oid
        """),
        {"oid": str(org_id)},
    )).all()
    for pss_id, player_id, old_season_id, grassroots_id in orphan_pss:
        target_season_id = None
        if grassroots_id:
            target_season_id = (await db.execute(
                text("SELECT id FROM seasons WHERE organisation_id = :oid AND grassroots_id = :gid LIMIT 1"),
                {"oid": str(org_id), "gid": grassroots_id},
            )).scalar_one_or_none()
        if not target_season_id:
            unresolved.append({"table": "player_season_stats", "id": pss_id, "player_id": str(player_id)})
            continue
        clash = (await db.execute(
            text("SELECT 1 FROM player_season_stats WHERE player_id = :pid AND season_id = :sid"),
            {"pid": str(player_id), "sid": str(target_season_id)},
        )).scalar_one_or_none()
        if clash:
            # A proper row for the corrected season already exists (e.g. a
            # regular sync since re-created it) — the orphan is now a stale
            # duplicate of already-correct data, not new information.
            await db.execute(text("DELETE FROM player_season_stats WHERE id = :id"), {"id": pss_id})
            counts["season_stats_deduped"] += 1
        else:
            await db.execute(
                text("UPDATE player_season_stats SET season_id = :sid WHERE id = :id"),
                {"sid": str(target_season_id), "id": pss_id},
            )
            counts["season_stats_repointed"] += 1

    # ── player_season_grade_stats ───────────────────────────────────────────
    orphan_pgs = (await db.execute(
        text("""
            SELECT pgs.id, pgs.player_id, pgs.season_id, pgs.grade_id,
                   s.grassroots_id AS season_gid, gr.grassroots_id AS grade_gid,
                   (s.organisation_id <> :oid) AS season_wrong,
                   (grs.organisation_id <> :oid) AS grade_wrong
            FROM player_season_grade_stats pgs
            JOIN players p ON p.id = pgs.player_id
            JOIN seasons s ON s.id = pgs.season_id
            JOIN grades gr ON gr.id = pgs.grade_id
            JOIN seasons grs ON grs.id = gr.season_id
            WHERE p.organisation_id = :oid
              AND (s.organisation_id <> :oid OR grs.organisation_id <> :oid)
        """),
        {"oid": str(org_id)},
    )).all()
    for pgs_id, player_id, old_season_id, old_grade_id, season_gid, grade_gid, season_wrong, grade_wrong in orphan_pgs:
        target_season_id = old_season_id
        if season_wrong:
            target_season_id = None
            if season_gid:
                target_season_id = (await db.execute(
                    text("SELECT id FROM seasons WHERE organisation_id = :oid AND grassroots_id = :gid LIMIT 1"),
                    {"oid": str(org_id), "gid": season_gid},
                )).scalar_one_or_none()
        target_grade_id = old_grade_id
        if grade_wrong and target_season_id:
            target_grade_id = None
            if grade_gid:
                target_grade_id = (await db.execute(
                    text("SELECT id FROM grades WHERE season_id = :sid AND grassroots_id = :gid LIMIT 1"),
                    {"sid": str(target_season_id), "gid": grade_gid},
                )).scalar_one_or_none()
        if not target_season_id or not target_grade_id:
            unresolved.append({"table": "player_season_grade_stats", "id": pgs_id, "player_id": str(player_id)})
            continue
        clash = (await db.execute(
            text(
                "SELECT 1 FROM player_season_grade_stats "
                "WHERE player_id = :pid AND season_id = :sid AND grade_id = :gid"
            ),
            {"pid": str(player_id), "sid": str(target_season_id), "gid": str(target_grade_id)},
        )).scalar_one_or_none()
        if clash:
            await db.execute(text("DELETE FROM player_season_grade_stats WHERE id = :id"), {"id": pgs_id})
            counts["grade_stats_deduped"] += 1
        else:
            await db.execute(
                text("UPDATE player_season_grade_stats SET season_id = :sid, grade_id = :gid WHERE id = :id"),
                {"sid": str(target_season_id), "gid": str(target_grade_id), "id": pgs_id},
            )
            counts["grade_stats_repointed"] += 1

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=org_id, user_id=current_user.id,
        action="repair_organisation_merge_stats", target_type="organisation", target_id=str(org_id),
        details={**counts, "unresolved": len(unresolved)},
    )

    await db.commit()
    return {"organisation_id": str(org_id), **counts, "unresolved": unresolved}
