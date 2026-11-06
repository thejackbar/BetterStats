"""A player Cricket Australia drops from a game's team sheet stops counting for that game.

The sync stores one `game_appearances` row per name on a team sheet the first time it reads a game, and
a finished game is not read again for appearances. A sheet read before the game can still name somebody
who pulls out late, and CA then removes them from the final sheet. The row stayed, so the player was
counted in a match CA never gave them: Applecross's Nuwani Jayaweera read 51 matches against CA's 50
because of one game she withdrew from.

For a RECENT stored game (the same window the sync already reads again, `participant_relink.REREAD_DAYS`)
whose scorecard is settled (`reserve_players.card_is_settled`), an appearance is marked withdrawn when
all of these hold:
  1. the player has no batting, bowling or fielding row in the game
  2. none of the sheet's participant ids resolves to them (`resolve` is the sync's own `_team_pid`, so
     a merged id and a person attached by full name are both still "on the sheet")
  3. nobody has set the flag since (`is_reserve` is NULL): a decision made by a person stands

The mark is `is_reserve` TRUE with `sheet_slot` NULL (see `reserve_players`), so every reader that skips
a reserve skips a withdrawal. If CA puts the person back on the sheet the mark is cleared.

One guard keeps a bad card from deleting matches: when more than half of the club's stored appearances in
the game would be marked, the card is treated as damaged and nothing is touched. In a fixture between two
sides of the same club a player is on the sheet if either of the club's sheets names them.

Older games are not read again by the sync. `app.scripts.backfill_reserve_flags` applies the same rule
to history, with a plan to read first, an audit entry and `--restore`.

Every change here writes one `audit_logs` entry in `changes` form, so `backfill_reserve_flags --restore
AUDIT_ID` undoes it. The caller catches anything this raises: a repair must never fail a sync.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import reserve_players
logger = logging.getLogger(__name__)

ACTION = "sync_withdrawn_appearances"


def _our_teams(scorecard: dict, org_id) -> list[dict]:
    """Every side on the card this club owns (two when the club plays itself)."""
    mine = str(org_id).lower()
    return [t for t in (scorecard.get("teams") or [])
            if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == mine]


async def mark_withdrawn(
    db: AsyncSession, org_id, game_id, scorecard: dict, resolve: Callable[[str], Optional[uuid.UUID]]
) -> Optional[dict]:
    """Mark or clear withdrawals on one stored game. Returns `{"marked": n, "cleared": n}`, or None
    when nothing was changed. Commits its own work.

    `resolve` is sync's `_team_pid` applied to a participant id string.
    """
    teams = _our_teams(scorecard, org_id)
    if not teams or not reserve_players.card_is_settled(scorecard):
        return None
    gid = game_id if isinstance(game_id, uuid.UUID) else uuid.UUID(str(game_id))

    on_sheet: set = set()
    for team in teams:
        for p in team.get("players") or []:
            guid = p.get("participantId") or ""
            pid = resolve(guid) if guid else None
            if pid is not None:
                on_sheet.add(pid)

    rows = (await db.execute(text("""
        SELECT ga.player_id, ga.is_reserve, ga.sheet_slot
        FROM game_appearances ga
        JOIN players p ON p.id = ga.player_id
        WHERE ga.game_id = :g AND p.organisation_id = CAST(:o AS UUID)"""),
        {"g": gid, "o": str(org_id)})).all()
    if not rows:
        return None
    has_stats = {r[0] for r in (await db.execute(text("""
        SELECT player_id FROM v_effective_batting_innings WHERE game_id = :g
        UNION SELECT player_id FROM v_effective_bowling_spells WHERE game_id = :g
        UNION SELECT player_id FROM v_effective_fielding_stats WHERE game_id = :g"""), {"g": gid})).all()}

    stale = [r[0] for r in rows if r[0] not in on_sheet and r[0] not in has_stats and r[1] is None]
    back = [r[0] for r in rows if r[0] in on_sheet and r[1] is True and r[2] is None]
    if stale and len(stale) > reserve_players.WITHDRAWN_MAX_SHARE * len(rows):
        logger.warning("GR-sync: %s: %d of %d stored appearances are not on the final team sheet; "
                       "treated as a damaged card, nothing marked", gid, len(stale), len(rows))
        stale = []
    if not stale and not back:
        return None

    if stale:
        await db.execute(text(
            "UPDATE game_appearances SET is_reserve = TRUE, sheet_slot = NULL "
            "WHERE game_id = :g AND player_id = ANY(CAST(:p AS uuid[])) AND is_reserve IS NULL"),
            {"g": gid, "p": [str(p) for p in stale]})
    if back:
        await db.execute(text(
            "UPDATE game_appearances SET is_reserve = NULL "
            "WHERE game_id = :g AND player_id = ANY(CAST(:p AS uuid[])) "
            "AND is_reserve IS TRUE AND sheet_slot IS NULL"),
            {"g": gid, "p": [str(p) for p in back]})
    details = {"by": "sync", "game_id": str(gid),
               "changes": [{"game_id": str(gid), "player_id": str(p), "is_reserve": True, "slot": None}
                           for p in stale],
               "cleared": [str(p) for p in back]}
    await db.execute(text(
        "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
        "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB))"),
        {"o": str(org_id), "a": ACTION, "d": json.dumps(details)})
    await db.commit()
    logger.info("GR-sync: %s: %d appearance(s) marked withdrawn, %d put back", gid, len(stale), len(back))
    return {"marked": len(stale), "cleared": len(back)}
