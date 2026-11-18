"""A club marks a player as named in the side but not having played a synced game.

WHY THIS EXISTS
---------------
Cricket Australia's team sheet carries no 12th man marker, so a player named for a game they did
not play (12th man, 13th man in a final, a late withdrawal) is counted as having played it. The
app judges some of those itself (`reserve_players`: off the card in slot 12 or later, or dropped
from the final sheet), but a player listed inside the XI who recorded nothing cannot be told from
one who simply did not bat, bowl or take a catch. Roy Marsh (Piara Waters) read 297 games against
Play Cricket's 295: East Fremantle, 5th Grade, 7 March 2015 and Cannington Tigers, One Day D,
17 March 2018 are on his team sheets with nothing recorded, and CA's season totals leave both out.

Until now the only fix was a season adjustment of -1, which corrects the total but says nothing
about which game it was for. A club can now mark the game itself, from the match page or from the
player's Adjustments screen, with a reason.

HOW IT COUNTS
-------------
The mark sets `game_appearances.is_reserve` TRUE. Every games-played count already reads that flag:
`game_status.appearance_counts_as_match` (StatLab, Records, boards, fees, Formats), the season
view's reserve rule (`LEAST(R, CA - N)`: CA's total loses the game only as far as CA counted it),
the by-grade grid's `uncounted` map (so the header, which is raised to the grid, follows) and the
fantasy and player card readers. Nothing else needed changing.

The club's decision lives in `game_exclusions` (migration 391), never only on the appearance: sync
deletes and re-stores a game's appearances, and a Full Rebuild re-stores the game itself. `reapply`
writes the flag back from sync, the lifespan writes every mark back on boot, and the backfill and
withdrawal writers leave a marked appearance alone.

WHAT IT REFUSES
---------------
A player with a batting, bowling or fielding line in the game played it (a substitute fielder's
catch is a line), so the mark is refused for them. Only a synced game of this club can be marked:
an uploaded or imported card is edited from Manual entries.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql
from app.services.game_status import not_played_game_sql
from app.services.season_kind import season_kind_sql

logger = logging.getLogger(__name__)

REASONS: dict[str, str] = {
    "twelfth_man": "12th man",
    "thirteenth_man": "13th man",
    "late_withdrawal": "Late withdrawal",
    "other": "Did not play",
}

# What a player's place in one game reads as. Ordered by precedence in `_status`.
PLAYED = "played"                 # a batting, bowling or fielding line: the game counts, cannot be marked
MARKED = "marked"                 # the club marked it: does not count
GAME_NOT_PLAYED = "game_not_played"  # the fixture was called off or never started: does not count
AUTO_RESERVE = "auto_reserve"     # the app read the player as 12th man (slot 12 or later)
AUTO_WITHDRAWN = "auto_withdrawn"  # the app read the player as dropped from the final sheet
NAMED = "named"                   # named, nothing recorded, counted: the club can mark it

COUNTS = {PLAYED, NAMED}

_REAPPLY = """
    UPDATE game_appearances ga SET is_reserve = TRUE
      FROM game_exclusions e
     WHERE e.game_id = ga.game_id AND e.player_id = ga.player_id
       AND ga.is_reserve IS NOT TRUE
"""


async def reapply(db: AsyncSession, game_id=None, player_ids: Optional[list] = None) -> int:
    """Write the club's marks back onto the appearances (after sync re-stores a game, or a merge).

    Never raises: a sync must not fail on this. A failure is logged and the next boot heals it.
    """
    sql, params = _REAPPLY, {}
    if game_id is not None:
        sql += " AND e.game_id = CAST(:g AS UUID)"
        params["g"] = str(game_id)
    if player_ids:
        sql += " AND e.player_id = ANY(CAST(:pids AS uuid[]))"
        params["pids"] = [str(p) for p in player_ids]
    try:
        async with db.begin_nested():
            res = await db.execute(text(sql), params)
        return res.rowcount or 0
    except Exception:
        logger.exception("game exclusions: could not reapply (game %s)", game_id)
        return 0


def _status(r) -> str:
    if r["has_row"]:
        return PLAYED
    if r["exclusion_id"] is not None:
        return MARKED
    if r["not_played"]:
        return GAME_NOT_PLAYED
    if r["is_reserve"] is True:
        return AUTO_RESERVE if r["sheet_slot"] is not None else AUTO_WITHDRAWN
    return NAMED


def _rows_sql(where: str) -> str:
    """Every appearance of one of the club's players in one of the club's synced games."""
    return f"""
        SELECT ga.game_id, ga.player_id, ga.is_reserve, ga.sheet_slot, COALESCE(ga.team_name, '') AS team_name,
               p.name AS player_name, p.display_name_override,
               g.played_at, g.home_team, g.away_team,
               gr.name AS grade_name, s.name AS season_name, s.year AS season_year,
               (EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = ga.game_id AND b.player_id = ga.player_id)
                OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = ga.game_id AND w.player_id = ga.player_id)
                OR EXISTS (SELECT 1 FROM fielding_stats f WHERE f.game_id = ga.game_id AND f.player_id = ga.player_id)
               ) AS has_row,
               {not_played_game_sql('rg')} AS not_played,
               e.id AS exclusion_id, e.reason, e.note, e.entered_at, e.source
          FROM game_appearances ga
          JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
          JOIN v_effective_games g ON g.id = ga.game_id AND g.source = 'api'
          JOIN games rg ON rg.id = ga.game_id
          LEFT JOIN grades gr ON gr.id = rg.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
          LEFT JOIN game_exclusions e
                 ON e.game_id = ga.game_id AND e.player_id = ga.player_id
                AND e.organisation_id = CAST(:org AS UUID)
         WHERE {club_game_sql('g', 'org')} AND {where}
    """


def _row_out(r) -> dict:
    status = _status(r)
    return {
        "game_id": str(r["game_id"]),
        "player_id": str(r["player_id"]),
        "player_name": r["display_name_override"] or r["player_name"],
        "team_name": r["team_name"],
        "played_at": r["played_at"].isoformat() if r["played_at"] else None,
        "home_team": r["home_team"],
        "away_team": r["away_team"],
        "grade_name": r["grade_name"],
        "season_name": r["season_name"],
        "season_year": r["season_year"],
        "status": status,
        "counts": status in COUNTS,
        "can_mark": status == NAMED,
        "reason": r["reason"],
        "reason_label": REASONS.get(r["reason"]) if r["reason"] else None,
        "note": r["note"],
        "source": r["source"],
    }


async def team_list(db: AsyncSession, org_id, game_id) -> list[dict]:
    """The club's players named in one game, each with whether the game counts for them and why."""
    res = await db.execute(
        text(_rows_sql("ga.game_id = CAST(:g AS UUID)") + " ORDER BY ga.sheet_slot NULLS LAST, p.name"),
        {"org": str(org_id), "g": str(game_id)})
    return [_row_out(r) for r in res.mappings()]


async def player_games(db: AsyncSession, org_id, player_id) -> list[dict]:
    """Every synced game of the club the player was named in, newest first, with the same status."""
    res = await db.execute(
        text(_rows_sql("ga.player_id = CAST(:p AS UUID)") + " ORDER BY g.played_at DESC NULLS LAST"),
        {"org": str(org_id), "p": str(player_id)})
    return [_row_out(r) for r in res.mappings()]


async def one(db: AsyncSession, org_id, game_id, player_id) -> Optional[dict]:
    res = await db.execute(
        text(_rows_sql("ga.game_id = CAST(:g AS UUID) AND ga.player_id = CAST(:p AS UUID)")),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id)})
    r = res.mappings().first()
    return _row_out(r) if r else None


async def adjustments_to_swap(db: AsyncSession, org_id, player_id, game_id) -> list[dict]:
    """The player's season adjustments that already take games off the season this game is in.

    A club that typed a -1 before it could pick the game would lose the game twice once it marks it.
    Matched by season year and kind (a shared fixture can hang off the other club's season row),
    never by grade id (the grade row can be the other club's too).
    """
    res = await db.execute(text(f"""
        SELECT a.id, a.games_played AS matches, s.name AS season_name, gr2.name AS grade_name
          FROM manual_season_adjustments a
          JOIN seasons s ON s.id = a.season_id
          LEFT JOIN grades gr2 ON gr2.id = a.grade_id
          JOIN games rg ON rg.id = CAST(:g AS UUID)
          JOIN grades gr ON gr.id = rg.grade_id
          JOIN seasons gs ON gs.id = gr.season_id
         WHERE a.organisation_id = CAST(:org AS UUID) AND a.player_id = CAST(:p AS UUID)
           AND COALESCE(a.games_played, 0) < 0
           AND s.year = gs.year AND {season_kind_sql('s.name')} = {season_kind_sql('gs.name')}
         ORDER BY (a.grade_id IS NULL), a.id
    """), {"org": str(org_id), "p": str(player_id), "g": str(game_id)})
    return [{"id": r["id"], "matches": r["matches"], "season_name": r["season_name"],
             "grade_name": r["grade_name"]} for r in res.mappings()]


class MarkRefused(Exception):
    """The mark cannot be made; the message says why, for the person who asked."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


async def mark(db: AsyncSession, org_id, user_id, game_id, player_id, reason: str,
               note: Optional[str] = None, swap_adjustment_id: Optional[int] = None,
               source: Optional[str] = None) -> dict:
    """Mark one player as not having played one game. Returns the exclusion as stored.

    Does not commit. Raises `MarkRefused` with a reason a club admin can act on.
    """
    if reason not in REASONS:
        raise MarkRefused("Pick a reason: 12th man, 13th man, late withdrawal or other.", 422)
    row = await one(db, org_id, game_id, player_id)
    if row is None:
        raise MarkRefused("That player is not on this club's team sheet for that match, "
                          "or the match is not one of this club's synced games.", 404)
    if row["status"] == PLAYED:
        raise MarkRefused(f"{row['player_name']} has a batting, bowling or fielding line in this game, "
                          "so it counts as played.")
    if row["status"] == MARKED:
        raise MarkRefused(f"{row['player_name']} is already marked as not having played this game.")
    if row["status"] == GAME_NOT_PLAYED:
        raise MarkRefused("This match was called off or never started, so it is already not counted "
                          "for anyone who recorded nothing in it.")

    prior = (await db.execute(text(
        "SELECT is_reserve FROM game_appearances WHERE game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID)"),
        {"g": str(game_id), "p": str(player_id)})).scalar()

    swapped = None
    if swap_adjustment_id is not None:
        allowed = {a["id"]: a for a in await adjustments_to_swap(db, org_id, player_id, game_id)}
        if swap_adjustment_id not in allowed:
            raise MarkRefused("That season adjustment does not take a game off this player's season, "
                              "so it cannot be moved onto this game.", 422)
        await db.execute(text(
            "UPDATE manual_season_adjustments SET games_played = games_played + 1, updated_at = NOW() WHERE id = :i"),
            {"i": swap_adjustment_id})
        swapped = swap_adjustment_id

    new_id = (await db.execute(text("""
        INSERT INTO game_exclusions (organisation_id, game_id, player_id, reason, note,
                                     prior_is_reserve, swapped_adjustment_id, source, entered_by)
        VALUES (CAST(:org AS UUID), CAST(:g AS UUID), CAST(:p AS UUID), :r, :n, :prior, :sw, :src, CAST(:u AS UUID))
        RETURNING id"""),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id), "r": reason,
         "n": (note or "").strip() or None, "prior": prior, "sw": swapped, "src": source,
         "u": str(user_id) if user_id else None})).scalar()
    await db.execute(text(
        "UPDATE game_appearances SET is_reserve = TRUE WHERE game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID)"),
        {"g": str(game_id), "p": str(player_id)})
    return await snapshot(db, new_id)


async def snapshot(db: AsyncSession, exclusion_id: int) -> Optional[dict]:
    r = (await db.execute(text("SELECT * FROM game_exclusions WHERE id = :i"), {"i": exclusion_id})).mappings().first()
    if r is None:
        return None
    out = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(r).items()}
    if out.get("entered_at") is not None:
        out["entered_at"] = out["entered_at"].isoformat()
    return out


async def unmark(db: AsyncSession, org_id, exclusion_id: int) -> Optional[dict]:
    """Take a mark off: the app's own judgement of the appearance comes back, and a season
    adjustment the mark absorbed is restored. Returns the snapshot of what was removed. No commit."""
    snap = await snapshot(db, exclusion_id)
    if snap is None or snap["organisation_id"] != str(org_id):
        return None
    # Only undo the flag this mark set: a sync since may have re-judged the row, and a TRUE that is
    # the app's own reading stays when the prior value was TRUE as well.
    await db.execute(text("""
        UPDATE game_appearances SET is_reserve = CAST(:prior AS BOOLEAN)
         WHERE game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID) AND is_reserve IS TRUE"""),
        {"prior": snap["prior_is_reserve"], "g": snap["game_id"], "p": snap["player_id"]})
    if snap.get("swapped_adjustment_id"):
        await db.execute(text("""
            UPDATE manual_season_adjustments SET games_played = games_played - 1, updated_at = NOW()
             WHERE id = :i AND organisation_id = CAST(:org AS UUID)"""),
            {"i": snap["swapped_adjustment_id"], "org": str(org_id)})
    await db.execute(text("DELETE FROM game_exclusions WHERE id = :i"), {"i": exclusion_id})
    return snap


async def restore(db: AsyncSession, org_id, snap: dict) -> Optional[dict]:
    """Put back a mark that was taken off (undo of an unmark). Skips one that would no longer hold."""
    row = await one(db, org_id, snap["game_id"], snap["player_id"])
    if row is None or row["status"] in (PLAYED, MARKED):
        return None
    return await mark(db, org_id, snap.get("entered_by"), snap["game_id"], snap["player_id"],
                      snap["reason"], snap.get("note"),
                      snap.get("swapped_adjustment_id") if snap.get("swapped_adjustment_id") else None,
                      snap.get("source"))


async def find(db: AsyncSession, org_id, game_id, player_id) -> Optional[int]:
    return (await db.execute(text("""
        SELECT id FROM game_exclusions
         WHERE organisation_id = CAST(:org AS UUID) AND game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID)"""),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id)})).scalar()


# ── Games to check ───────────────────────────────────────────────────────────

async def suggestions(db: AsyncSession, org_id, limit: int = 500) -> dict:
    """Games where a player was named, recorded nothing and is counted, in a season where our count
    is higher than Cricket Australia's own season total. Those are the likeliest 12th man games.

    Nothing is changed: the club confirms (marks) or dismisses each one. A season CA has no total
    for is not compared (no total means nothing to disagree with). Seasons are matched by year and
    kind, the way the season view keys the games we hold, because a shared fixture can hang off the
    other club's season row.
    """
    kind_s = season_kind_sql("s.name")
    res = await db.execute(text(f"""
        WITH ap AS (
            SELECT ga.player_id, ga.game_id, ga.is_reserve, s.year, {kind_s} AS kind,
                   (EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = ga.game_id AND b.player_id = ga.player_id)
                    OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = ga.game_id AND w.player_id = ga.player_id)
                    OR EXISTS (SELECT 1 FROM fielding_stats f WHERE f.game_id = ga.game_id AND f.player_id = ga.player_id)
                   ) AS has_row,
                   {not_played_game_sql('rg')} AS not_played
              FROM game_appearances ga
              JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
              JOIN v_effective_games g ON g.id = ga.game_id AND g.source = 'api'
              JOIN games rg ON rg.id = ga.game_id
              JOIN grades gr ON gr.id = rg.grade_id
              JOIN seasons s ON s.id = gr.season_id
             WHERE {club_game_sql('g', 'org')}
        ),
        ours AS (
            SELECT player_id, year, kind,
                   COUNT(DISTINCT game_id) FILTER (
                       WHERE has_row OR (NOT not_played AND is_reserve IS NOT TRUE)) AS ours
              FROM ap GROUP BY 1, 2, 3
        ),
        ca AS (
            SELECT pss.player_id, s.year, {kind_s} AS kind, SUM(COALESCE(pss.matches, 0)) AS ca
              FROM player_season_stats pss
              JOIN players p ON p.id = pss.player_id AND p.organisation_id = CAST(:org AS UUID)
              JOIN seasons s ON s.id = pss.season_id AND s.organisation_id = CAST(:org AS UUID)
             GROUP BY 1, 2, 3
        )
        SELECT ap.player_id, ap.game_id, o.ours, c.ca
          FROM ap
          JOIN ours o ON o.player_id = ap.player_id AND o.year = ap.year AND o.kind = ap.kind
          JOIN ca c ON c.player_id = ap.player_id AND c.year = ap.year AND c.kind = ap.kind
         WHERE NOT ap.has_row AND NOT ap.not_played AND ap.is_reserve IS NOT TRUE
           AND o.ours > c.ca
           AND NOT EXISTS (SELECT 1 FROM game_check_dismissals d
                            WHERE d.organisation_id = CAST(:org AS UUID)
                              AND d.game_id = ap.game_id AND d.player_id = ap.player_id)
         LIMIT :lim
    """), {"org": str(org_id), "lim": limit + 1})
    found = list(res.mappings())
    truncated = len(found) > limit
    found = found[:limit]
    out = []
    for f in found:
        row = await one(db, org_id, f["game_id"], f["player_id"])
        if row is None or not row["can_mark"]:
            continue
        out.append({**row, "our_season_total": int(f["ours"]), "ca_season_total": int(f["ca"])})
    out.sort(key=lambda r: (r["player_name"] or "", r["played_at"] or ""))
    return {"items": out, "truncated": truncated}


async def dismiss(db: AsyncSession, org_id, user_id, game_id, player_id) -> None:
    await db.execute(text("""
        INSERT INTO game_check_dismissals (organisation_id, game_id, player_id, dismissed_by)
        SELECT CAST(:org AS UUID), CAST(:g AS UUID), CAST(:p AS UUID), CAST(:u AS UUID)
         WHERE NOT EXISTS (SELECT 1 FROM game_check_dismissals
                            WHERE organisation_id = CAST(:org AS UUID)
                              AND game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID))"""),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id), "u": str(user_id) if user_id else None})


async def undismiss(db: AsyncSession, org_id, game_id, player_id) -> None:
    await db.execute(text("""
        DELETE FROM game_check_dismissals
         WHERE organisation_id = CAST(:org AS UUID) AND game_id = CAST(:g AS UUID) AND player_id = CAST(:p AS UUID)"""),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id)})


async def public_marks(db: AsyncSession, game_id, org_id=None) -> list[dict]:
    """The marks on one game for the public scorecard: who was named and did not play, and why."""
    res = await db.execute(text("""
        SELECT e.player_id, e.reason, p.name, p.display_name_override, p.privacy_hidden_at
          FROM game_exclusions e
          JOIN players p ON p.id = e.player_id
         WHERE e.game_id = CAST(:g AS UUID)
           AND (CAST(:org AS UUID) IS NULL OR e.organisation_id = CAST(:org AS UUID))
         ORDER BY p.name"""), {"g": str(game_id), "org": str(org_id) if org_id else None})
    out = []
    for r in res.mappings():
        if r["privacy_hidden_at"] is not None:
            continue
        out.append({"player_id": str(r["player_id"]),
                    "player_name": r["display_name_override"] or r["name"],
                    "reason": r["reason"], "reason_label": REASONS.get(r["reason"], "Did not play")})
    return out


# ── Team sheets with more than 11 names ──────────────────────────────────────

XI = 11


async def big_sheets(db: AsyncSession, org_id, limit: int = 200) -> dict:
    """The club's sides in synced games with more than 11 players still counted as having played.

    A side is eleven, so every one of these named at least one extra: a substitute fielder named
    because they turned up (common in older seasons), the 12th and 13th men of a final. Cricket
    Australia counts them as often as not, so `suggestions` (ours above CA's total) misses most of
    them. The club looks over the sheet and marks the extras, or marks the sheet checked. A sheet
    drops off on its own once no more than 11 still count. Newest first.
    """
    res = await db.execute(text(f"""
        WITH ap AS (
            SELECT ga.game_id, COALESCE(ga.team_name, '') AS team_name, ga.player_id, ga.is_reserve,
                   (EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = ga.game_id AND b.player_id = ga.player_id)
                    OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = ga.game_id AND w.player_id = ga.player_id)
                    OR EXISTS (SELECT 1 FROM fielding_stats f WHERE f.game_id = ga.game_id AND f.player_id = ga.player_id)
                   ) AS has_row,
                   {not_played_game_sql('rg')} AS not_played
              FROM game_appearances ga
              JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
              JOIN v_effective_games g ON g.id = ga.game_id AND g.source = 'api'
              JOIN games rg ON rg.id = ga.game_id
             WHERE {club_game_sql('g', 'org')}
        ),
        sides AS (
            SELECT game_id, team_name, COUNT(*) AS named,
                   COUNT(*) FILTER (WHERE has_row OR (NOT not_played AND is_reserve IS NOT TRUE)) AS counted
              FROM ap GROUP BY 1, 2
        )
        SELECT sd.game_id, sd.team_name, sd.named, sd.counted,
               rg.played_at, rg.home_team, rg.away_team, gr.name AS grade_name, s.name AS season_name
          FROM sides sd
          JOIN games rg ON rg.id = sd.game_id
          LEFT JOIN grades gr ON gr.id = rg.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
         WHERE sd.counted > {XI}
           AND NOT EXISTS (SELECT 1 FROM game_sheet_checks c
                            WHERE c.organisation_id = CAST(:org AS UUID)
                              AND c.game_id = sd.game_id AND c.team_name = sd.team_name)
         ORDER BY rg.played_at DESC NULLS LAST, sd.game_id
         LIMIT :lim
    """), {"org": str(org_id), "lim": limit + 1})
    rows = list(res.mappings())
    out = [{
        "game_id": str(r["game_id"]), "team_name": r["team_name"], "named": int(r["named"]),
        "counted": int(r["counted"]), "extras": int(r["counted"]) - XI,
        "played_at": r["played_at"].isoformat() if r["played_at"] else None,
        "home_team": r["home_team"], "away_team": r["away_team"],
        "grade_name": r["grade_name"], "season_name": r["season_name"],
    } for r in rows[:limit]]
    return {"items": out, "truncated": len(rows) > limit}


async def check_sheet(db: AsyncSession, org_id, user_id, game_id, team_name: str) -> None:
    await db.execute(text("""
        INSERT INTO game_sheet_checks (organisation_id, game_id, team_name, checked_by)
        SELECT CAST(:org AS UUID), CAST(:g AS UUID), :t, CAST(:u AS UUID)
         WHERE NOT EXISTS (SELECT 1 FROM game_sheet_checks
                            WHERE organisation_id = CAST(:org AS UUID)
                              AND game_id = CAST(:g AS UUID) AND team_name = :t)"""),
        {"org": str(org_id), "g": str(game_id), "t": team_name or "", "u": str(user_id) if user_id else None})


# ── The Premiers squad editor's 12th Man and 13th Man ────────────────────────

PREMIERS = "premiers"
_ROLE_REASON = {"12th Man": "twelfth_man", "13th Man": "thirteenth_man"}


async def log_edit(db: AsyncSession, org_id, user_id, action: str, exclusion_id: int, summary: str,
                   before: Optional[dict], after: Optional[dict]) -> None:
    """The same audit row the match page writes, so the Audit tab can undo it."""
    from app.models.db import ManualEditLog
    as_uuid = lambda v: v if v is None or isinstance(v, uuid.UUID) else uuid.UUID(str(v))  # noqa: E731
    db.add(ManualEditLog(organisation_id=as_uuid(org_id), user_id=as_uuid(user_id), action=action, target_table="game_exclusions",
                         target_id=str(exclusion_id), summary=summary, before_json=before, after_json=after))
    await db.flush()


async def premiers_role_set(db: AsyncSession, org_id, user_id, game_id, player_id, role_name: str) -> dict:
    """12th Man or 13th Man given on a premiership card: take the game off the player's games played.

    Returns ``{"changed": bool, "message": str}``. Never raises: the honour is saved either way.
    """
    reason = _ROLE_REASON.get(role_name)
    if reason is None:
        return {"changed": False, "message": ""}
    row = await one(db, org_id, game_id, player_id)
    if row is None:
        return {"changed": False, "message": "Games played were not changed: this premiership is not a synced "
                                             "match with this player on its team sheet."}
    name = row["player_name"]
    if row["status"] == PLAYED:
        return {"changed": False, "message": f"{name} has a batting, bowling or fielding line in this match, "
                                             "so it still counts as a game played."}
    if row["status"] == MARKED:
        return {"changed": False, "message": f"{name} was already marked as not having played this match."}
    if row["status"] != NAMED:
        return {"changed": False, "message": f"This match already does not count as a game played for {name}."}
    try:
        async with db.begin_nested():
            snap = await mark(db, org_id, user_id, game_id, player_id, reason, source=PREMIERS)
    except MarkRefused as e:
        return {"changed": False, "message": str(e)}
    msg = f"{name}: this match no longer counts as a game played ({role_name})."
    await log_edit(db, org_id, user_id, "create", snap["id"],
                   f"{name} marked as {role_name.lower()} from the Premiers squad: "
                   f"{row.get('home_team') or ''} v {row.get('away_team') or ''}".strip(), None, snap)
    return {"changed": True, "message": msg}


async def premiers_role_cleared(db: AsyncSession, org_id, user_id, game_id, player_id) -> dict:
    """The role came off (or the player came off the card): take off the mark it wrote, and only that."""
    ex = (await db.execute(text("""
        SELECT id FROM game_exclusions
         WHERE organisation_id = CAST(:org AS UUID) AND game_id = CAST(:g AS UUID)
           AND player_id = CAST(:p AS UUID) AND source = :src"""),
        {"org": str(org_id), "g": str(game_id), "p": str(player_id), "src": PREMIERS})).scalar()
    if ex is None:
        return {"changed": False, "message": ""}
    row = await one(db, org_id, game_id, player_id)
    snap = await unmark(db, org_id, ex)
    name = (row or {}).get("player_name") or "The player"
    await log_edit(db, org_id, user_id, "delete", ex,
                   f"{name} counted as playing again (role removed in the Premiers squad)", snap, None)
    return {"changed": True, "message": f"{name}: this match counts as a game played again."}
