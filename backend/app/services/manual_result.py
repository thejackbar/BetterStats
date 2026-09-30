"""Settling a hand-entered or imported game's winner when its own figures disagree.

A manual game carries three independent answers to "who won": the recorded
`winning_team`, the `result` line ("Lost by 7 Runs"), and the two innings
totals. Reported off Hamilton Veterans' 7 Feb 2012 match: the sheet named
Portland as the winner, its own result line said Portland lost by 7, and the
scores were Portland 159 v Vic Country 166. Every screen reads `winning_team`
(the WON tag, the Games list, the club's W/L), so the one wrong field won over
the two right ones.

The rule is deliberately narrow, because this is the club's own record:

* the result line must say WON or LOST from our side's point of view, as its
  opening word ("Won by 70 runs", "Lost By 16 Runs"). A line naming a team
  ("Rockingham won by 5 wickets") is not read, since its point of view is not
  ours;
* the recorded winner must name one of the two sides, and the OTHER one to the
  result line;
* the match must be one innings each, with both totals, and the scores must
  agree with the result line. A two-innings match, a tie, a missing total or a
  rain-adjusted result where the lower score won all leave it alone.

Only then is the winner changed, to the side the result line and the scores
both name. Anything short of that is left exactly as the club wrote it.
"""
from __future__ import annotations

import re
from typing import Optional

_WON = re.compile(r"^\s*(won|win|wins)\b", re.I)
_LOST = re.compile(r"^\s*(lost|loss|lose|loses)\b", re.I)


def _key(name: Optional[str]) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split())


def text_outcome(result: Optional[str]) -> Optional[str]:
    """'won' / 'lost' when the result line opens with it, else None."""
    if not result:
        return None
    if _WON.match(result):
        return "won"
    if _LOST.match(result):
        return "lost"
    return None


def recorded_outcome(winning_team: Optional[str], ours: str, theirs: str) -> Optional[str]:
    """Our result as the recorded winner has it, or None when it names neither side."""
    w = _key(winning_team)
    if not w:
        return None
    if w == _key(ours) and w != _key(theirs):
        return "won"
    if w == _key(theirs) and w != _key(ours):
        return "lost"
    return None


def score_outcome(our_total: Optional[int], their_total: Optional[int]) -> Optional[str]:
    if our_total is None or their_total is None or our_total == their_total:
        return None
    return "won" if our_total > their_total else "lost"


def settled_winner(winning_team: Optional[str], result: Optional[str], ours: str,
                   theirs: str, our_total: Optional[int],
                   their_total: Optional[int]) -> Optional[str]:
    """The corrected winning team, or None to leave the record as it is."""
    said = text_outcome(result)
    recorded = recorded_outcome(winning_team, ours, theirs)
    if said is None or recorded is None or said == recorded:
        return None
    if score_outcome(our_total, their_total) != said:
        return None
    return ours if said == "won" else theirs


def _needs_scores(game, ours: str, theirs: str) -> bool:
    """Cheap pre-check: only a game whose two fields disagree is worth scoring."""
    said = text_outcome(game.result)
    recorded = recorded_outcome(game.winning_team, ours, theirs)
    return said is not None and recorded is not None and said != recorded


def side_totals(card: dict, ours: str, theirs: str, club_name: Optional[str]):
    """(our total, their total) from a scorecard payload, or (None, None).

    One innings each only. An innings is ours when it is labelled with our side
    or the club's own name, theirs when labelled with theirs; with one side
    placed, the other innings is the other side.
    """
    totals = card.get("innings_totals") or {}
    if len(totals) != 2:
        return None, None
    our_keys = {_key(ours), _key(club_name)} - {""}
    placed: dict[str, int] = {}
    unplaced: list[int] = []
    for t in totals.values():
        total = (t.get("runs") or 0) + (t.get("extras") or 0)
        k = _key(t.get("batting_team"))
        if k and k in our_keys:
            side = "ours"
        elif k and k == _key(theirs):
            side = "theirs"
        else:
            unplaced.append(total)
            continue
        if side in placed:
            return None, None
        placed[side] = total
    if len(placed) == 1 and len(unplaced) == 1:
        placed["theirs" if "ours" in placed else "ours"] = unplaced[0]
    if len(placed) != 2:
        return None, None
    return placed["ours"], placed["theirs"]


async def settle_manual_game(db, game, org) -> Optional[dict]:
    """Correct `game.winning_team` in place when the rule above says to.

    Returns what changed, or None. Does not commit; the caller's transaction
    carries the change with the rest of its write.
    """
    from app.routers.games import _manual_side_names, get_scorecard

    ours, theirs = _manual_side_names(game, org)
    if not _needs_scores(game, ours, theirs):
        return None
    await db.flush()
    card = await get_scorecard(str(game.id), db=db)
    our_total, their_total = side_totals(card, ours, theirs, getattr(org, "name", None))
    now = settled_winner(game.winning_team, game.result, ours, theirs, our_total, their_total)
    if now is None:
        return None
    was = game.winning_team
    game.winning_team = now
    return {
        "game_id": str(game.id),
        "played_at": game.played_at.isoformat() if game.played_at else None,
        "result": game.result,
        "was": was,
        "now": now,
        "scores": f"{ours} {our_total}, {theirs} {their_total}",
    }


def describe(change: dict) -> str:
    when = change.get("played_at") or "undated"
    return (f"{when}: the winner was recorded as {change['was']}, but the result "
            f"says \"{change['result']}\" and the scores were {change['scores']}, "
            f"so the winner is now {change['now']}.")
