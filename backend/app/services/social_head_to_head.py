"""BetterPosts: our past results against one opponent, for the Head to Head
post and the match-day layouts' "last meetings" strip.

Read from ``v_effective_games`` (synced games and the club's own hand-typed
ones, paired imports counted once), scoped to games that are the club's by
``club_game_sql``: a fixture between two synced clubs is ONE row whose season
may belong to the other club (rule 2), so ownership is never read from the
season owner.

Which side is ours comes from the owning organisation ids where the row has
them, else the names (``club_match.fixture_side``). The other side is the
opponent. A win or a loss is re-derived from ``winning_team`` against our side,
never read from ``games.result``: that column is written from the point of view
of whichever club synced the game first. Only the symmetric outcomes (a tie, a
draw) are taken from it. A hand-typed game is the club's own, so its result is
the club's word where no winner was typed.

The opponent is matched on club-identifying name tokens with BetterIQ's
matcher (``iq._best_opp_key_by_name``): "Subiaco-Floreat 1st XI" from a ladder
and "Subiaco Floreat Cricket Club" on a card are the same club, and when two
different clubs tie for the name nothing is guessed.

Pure read. Nothing is written.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_game_sql
from app.services.club_match import fixture_side, name_score
from app.services.grade_labels import grade_alias_map, grade_key
from app.services.iq import _best_opp_key_by_name, _club_core_tokens
from app.services.sync import strip_team_suffix

RECENT_LIMIT = 8
FORM_LIMIT = 5


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _outcome(r, ours: str, theirs: str, club) -> Optional[str]:
    """'W', 'L', 'D', 'T', 'NR', or None when the card cannot say."""
    win = _norm(r["winning_team"])
    status = (r["status"] or "").upper()
    if win:
        if win == _norm(ours):
            return "W"
        if win == _norm(theirs):
            return "L"
        # The winner spelled another way (club name in place of the team):
        # whichever side it names more strongly, if it names one at all.
        us_hit = name_score(club, r["winning_team"]) > 0
        them_hit = bool(_club_core_tokens(r["winning_team"]) & _club_core_tokens(theirs))
        if us_hit and not them_hit:
            return "W"
        if them_hit and not us_hit:
            return "L"
        return None
    res = (r["result"] or "").upper()
    if r["source"] == "manual":
        return {"WIN": "W", "WON": "W", "LOSS": "L", "LOST": "L", "DRAW": "D", "DRAWN": "D", "TIE": "T",
                "NO RESULT": "NR", "ABANDONED": "NR"}.get(res)
    if "TIE" in res:
        return "T"
    if "DRAW" in res:
        return "D"
    if status and status != "COMPLETED":
        return "NR"
    if "NO RESULT" in res or "ABANDON" in res:
        return "NR"
    return None


def _empty(target: str, grade: Optional[str]) -> dict:
    return {"found": False, "opponent": target or None, "grade": grade or None,
            "meetings": 0, "wins": 0, "losses": 0, "draws": 0, "ties": 0, "no_result": 0,
            "form": [], "recent": []}


async def _club_games(db: AsyncSession, club) -> list[dict]:
    """Every past game that is the club's, each with our side, their team and
    the key their club is grouped under. Read once, matched per opponent."""
    rows = (await db.execute(text(f"""
        SELECT g.id::text AS id, g.played_at, g.home_team, g.away_team,
               g.home_org_id::text AS home_org_id, g.away_org_id::text AS away_org_id,
               g.opp_club_name, g.winning_team, g.result, g.status, g.venue, g.source,
               gr.name AS grade_name
        FROM v_effective_games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        WHERE {club_game_sql('g', 'club_org')}
          AND g.played_at IS NOT NULL AND g.played_at <= CAST(:today AS DATE)
        ORDER BY g.played_at DESC, g.id
        LIMIT 3000
    """), {"club_org": str(club.id), "today": date.today()})).mappings().all()

    games = []
    for r in rows:
        if r["home_org_id"] and r["away_org_id"] and r["home_org_id"] == r["away_org_id"]:
            continue  # both sides the club's own: no opponent
        if r["source"] == "manual":
            opp = r["opp_club_name"] or ""
            if opp and _club_core_tokens(opp) & _club_core_tokens(r["away_team"]):
                side = "home"
            elif opp and _club_core_tokens(opp) & _club_core_tokens(r["home_team"]):
                side = "away"
            else:
                side = fixture_side(club, r["home_team"], r["away_team"])
        else:
            side = fixture_side(club, r["home_team"], r["away_team"], r["home_org_id"], r["away_org_id"])
        if side is None:
            continue
        ours = r["home_team"] if side == "home" else r["away_team"]
        theirs = r["away_team"] if side == "home" else r["home_team"]
        if r["source"] == "manual" and r["opp_club_name"] and not theirs:
            theirs = r["opp_club_name"]
        their_org = (r["away_org_id"] if side == "home" else r["home_org_id"]) or None
        if not theirs:
            continue
        club_name = strip_team_suffix(theirs)
        key = f"org:{their_org.lower()}" if their_org else "name:" + " ".join(sorted(_club_core_tokens(club_name)))
        games.append({"r": r, "side": side, "ours": ours, "theirs": theirs, "club_name": club_name, "key": key})

    # One club, one key: a game that only names the club joins the key of a game
    # that carries its organisation id when the two names are the same club.
    org_tokens = {}
    for gm in games:
        if gm["key"].startswith("org:"):
            org_tokens.setdefault(frozenset(_club_core_tokens(gm["club_name"])), set()).add(gm["key"])
    for gm in games:
        if gm["key"].startswith("name:"):
            owners = org_tokens.get(frozenset(_club_core_tokens(gm["club_name"])))
            if owners and len(owners) == 1:
                gm["key"] = next(iter(owners))
    return games


def _record(games: list[dict], club, opponent: str, grade: Optional[str], aliases: dict) -> dict:
    target = (opponent or "").strip()
    base = _empty(target, grade)
    if not target or not _club_core_tokens(target):
        return {**base, "reason": "no opponent name to match"}
    candidates = {}
    for gm in games:
        candidates.setdefault(gm["key"], gm["club_name"])
    best = _best_opp_key_by_name(candidates.items(), target)
    if not best:
        return {**base, "reason": "no past games against that club" if candidates else "no past games"}
    best_key, best_name = best
    best_tokens = _club_core_tokens(best_name)
    picked = [gm for gm in games if gm["key"] == best_key
              or (gm["key"].startswith("name:") and _club_core_tokens(gm["club_name"]) == best_tokens)]
    if grade:
        k = grade_key(grade)
        want = aliases.get(k, k)

        def _gk(name):
            kk = grade_key(name)
            return aliases.get(kk, kk)
        picked = [gm for gm in picked if gm["r"]["grade_name"] and _gk(gm["r"]["grade_name"]) == want]

    out = {**base, "found": True, "opponent": best_name}
    tally = {"W": "wins", "L": "losses", "D": "draws", "T": "ties", "NR": "no_result"}
    recent = []
    for gm in picked:
        r = gm["r"]
        oc = _outcome(r, gm["ours"], gm["theirs"], club)
        out["meetings"] += 1
        if oc in tally:
            out[tally[oc]] += 1
        if len(recent) < RECENT_LIMIT:
            recent.append({
                "played_at": r["played_at"].isoformat() if r["played_at"] else None,
                "grade_name": r["grade_name"], "venue": r["venue"],
                "home_away": "HOME" if gm["side"] == "home" else "AWAY",
                "our_team": gm["ours"], "their_team": gm["theirs"],
                "outcome": oc, "source": r["source"],
            })
    out["recent"] = recent
    out["form"] = [x["outcome"] for x in recent if x["outcome"] in ("W", "L", "D", "T")][:FORM_LIMIT]
    return out


async def head_to_head(db: AsyncSession, club, opponent: str, grade: Optional[str] = None) -> dict:
    target = (opponent or "").strip()
    if not target or not _club_core_tokens(target):
        return {**_empty(target, grade), "reason": "no opponent name to match"}
    games = await _club_games(db, club)
    aliases = await grade_alias_map(db, club.id) if grade else {}
    return _record(games, club, target, grade, aliases)


MAX_BATCH = 40


async def head_to_head_many(db: AsyncSession, club, items: list[dict]) -> list[dict]:
    """The same answer for several opponents at once (a roundup's rows): the
    club's games are read once. ``items``: ``[{opponent, grade}]``, answered in
    the same order."""
    items = list(items or [])[:MAX_BATCH]
    if not items:
        return []
    games = await _club_games(db, club)
    aliases = await grade_alias_map(db, club.id) if any((it or {}).get("grade") for it in items) else {}
    return [_record(games, club, (it or {}).get("opponent") or "", (it or {}).get("grade") or None, aliases) for it in items]
