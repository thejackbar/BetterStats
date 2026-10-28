"""Grand finals the club typed in or imported, read by the automatic premierships.

A synced game says it was a grand final (``games.round_name``) and who won it (``winning_team``,
neutral across both clubs). A hand-entered or imported game says neither in a form the
premiership code can use on its own: ``manual_games.is_grand_final`` is a person's statement that
it was the decider, and the winner is whatever the club typed: a team name that may be the
club's own or only part of it ("Shoalwater Bay"), and a result line that may be a bare "WIN" or
a sentence ("Won by 32 runs"). This module answers one question about such a game, "did our side
win it?", with the rules the rest of the manual-game code already uses, and nothing more.

Nothing is guessed. A game that cannot be read as a win or a loss from our side comes back as
undecided, with the reason in words, so the club can be told why no premiership was written
rather than being left to wonder. This is pure code on a game's own fields; the squad query is
the only database read.

* The recorded winner names our side, or the result line opens with Won, and the other one does
  not say otherwise: a win.
* The winner and the result line disagree: undecided. (``manual_result`` settles a disagreement
  that the scores also settle; here it is left for a person.)
* Neither says anything usable (a draw, a tie, a blank): undecided.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text

from app.services.manual_result import _key, recorded_outcome, text_outcome

WON = "won"
LOST = "lost"


def _club_words(club) -> set[str]:
    """The words of the club's own name that distinguish it from any other club."""
    from app.routers.games import _GENERIC_SIDE_WORDS
    return set(_key(getattr(club, "name", None)).split()) - _GENERIC_SIDE_WORDS


def names_our_club(winner: Optional[str], club, theirs: Optional[str]) -> bool:
    """The winner is written as our club ("Shoalwater Bay" for Shoalwater Bay Cricket Club).

    The recorded winner has to carry every distinguishing word of the club's name, and the
    opposition must not carry them too (a derby between two sides of one club names neither).
    """
    w = _key(winner)
    if not w or w == _key(theirs):
        return False
    for k in (getattr(club, "name", None), getattr(club, "short_name", None)):
        if k and _key(k) == w:
            return True
    words = _club_words(club)
    if not words or not words <= set(w.split()):
        return False
    return not words <= set(_key(theirs).split())


def manual_outcome(game, club) -> tuple[Optional[str], str]:
    """``("won"|"lost", "")`` or ``(None, reason)`` for our side in a hand-entered game.

    ``game`` needs ``home_team``, ``away_team``, ``opposition``, ``winning_team`` and ``result``.
    """
    from app.routers.games import _manual_side_names
    ours, theirs = _manual_side_names(game, club)
    by_winner = recorded_outcome(game.winning_team, ours, theirs)
    if by_winner is None and names_our_club(game.winning_team, club, theirs):
        by_winner = WON
    by_text = text_outcome(game.result)
    if by_winner and by_text and by_winner != by_text:
        return None, "the winner and the result line disagree"
    outcome = by_winner or by_text
    if outcome is None:
        return None, "no winner recorded"
    return outcome, ""


async def squad(db, manual_game_ids: list, org_id) -> dict[str, list[dict]]:
    """``{game id: [{player_id, name, is_captain}]}`` for hand-entered games.

    Everyone the card records for the club: a batter (a "did not bat" row is a named player), a
    bowler or a fielder. The card holds the club's own players only, since the opposition are not
    player rows. A hand-entered card has no captain marker. A player who asked to be removed
    (``privacy_hidden_at``) is left off, as on a synced game.
    """
    if not manual_game_ids:
        return {}
    ids = [uuid.UUID(str(g)) for g in manual_game_ids]
    rows = (await db.execute(text("""
        SELECT c.game_id, c.player_id, COALESCE(p.display_name_override, p.name) AS name
        FROM (
            SELECT manual_game_id AS game_id, player_id FROM manual_batting_innings WHERE manual_game_id = ANY(:ids)
            UNION
            SELECT manual_game_id, player_id FROM manual_bowling_spells WHERE manual_game_id = ANY(:ids)
            UNION
            SELECT manual_game_id, player_id FROM manual_fielding_stats WHERE manual_game_id = ANY(:ids)
        ) c
        JOIN players p ON p.id = c.player_id
        WHERE p.organisation_id = CAST(:org AS UUID) AND p.privacy_hidden_at IS NULL
        ORDER BY name
    """), {"ids": ids, "org": str(org_id)})).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["game_id"]), []).append(
            {"player_id": str(r["player_id"]), "name": r["name"], "is_captain": False})
    return out
