"""Attach the games sync dropped for a player whose participant id it did not know.

Sync stores a game's rows by Cricket Australia's participant id. A player whose id on
the team sheet is not the one the club holds for them (a new registration id, or a
player new to the club this season who only exists hand-added) had their batting,
bowling and appearance dropped, and a game already stored is never re-read for them.
``services/participant_names`` now lets sync recognise them by full name from here on;
this finds the games already stored without them and adds just their rows.

Adds rows only. Nothing is deleted, no other player's row is touched, and a row that
is already there is left as it is, so running it twice changes nothing the second time.
Partnerships, fall of wickets and the wicket-by-wicket list are not rebuilt (they hold
other players' rows too); a Full Rebuild rewrites those. Batting, bowling, fielding
and the appearance are what Fantasy, the profile and the career figures read.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Awaitable, Callable, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import BattingInnings, BowlingSpell, FieldingStat, GameAppearance
from app.services import dismissal, participant_names
from app.services.boundary_counts import clean as _bounds
from app.services.club_grades import club_game_sql
from app.services.sync import (
    _GR_DISMISSAL_SHORT, _caught_by_keeper, _innings_keeper_names, _parse_uuid,
)

logger = logging.getLogger(__name__)

Fetch = Callable[[str], Awaitable[Optional[dict]]]


async def _org_maps(db: AsyncSession, org_id) -> tuple[dict, dict, dict]:
    """(guid -> player id, merged-away redirect, unique full names) for a club, built the
    way sync builds them so the two cannot disagree about who is "known"."""
    players = (await db.execute(text("""
        SELECT id, grassroots_id, name, display_name_override, is_player
        FROM players WHERE organisation_id = CAST(:o AS UUID)"""), {"o": str(org_id)})).all()
    by_guid: dict[str, uuid.UUID] = {}
    pairs = []
    for pid, gid, name, over, is_player in players:
        g = _parse_uuid(gid) if gid else None
        if g is not None:
            by_guid[str(g)] = pid
        if is_player is not False:
            pairs.append((pid, over or name))
    raw = {r[0]: r[1] for r in (await db.execute(text("""
        SELECT removed_player_id, keep_player_id FROM merge_logs
        WHERE org_id = CAST(:o AS UUID) AND undone_at IS NULL"""), {"o": str(org_id)})).all()}
    merged: dict = {}
    for removed, target in raw.items():
        seen = {removed}
        while target in raw and target not in seen:
            seen.add(target)
            target = raw[target]
        merged[removed] = target
    return by_guid, merged, participant_names.unique_by_full_name(pairs)


def _known(guid: str, by_guid: dict, merged: dict):
    """sync's ``_team_pid``: the raw id, then a merge redirect, then the redirect's own."""
    g = _parse_uuid(guid)
    if g is None:
        return None
    p = by_guid.get(str(g))
    if p is None:
        p = merged.get(g)
        if p is None:
            return None
    return merged.get(p, p)


def _our_team(scorecard: dict, org_id) -> Optional[dict]:
    return next((t for t in (scorecard.get("teams") or [])
                 if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == str(org_id).lower()), None)


async def plan(db: AsyncSession, org_id, year: int, fetch: Fetch, today: Optional[date] = None) -> dict:
    """Games of this club in ``year`` whose stored rows lack a rostered player sync can
    now recognise (by full name, or by an id that a later merge now resolves). Reads the live team sheet of each synced game (one
    request per game, cached by the client)."""
    today = today or date.today()
    by_guid, merged, unique = await _org_maps(db, org_id)
    games = (await db.execute(text(f"""
        SELECT g.id, g.played_at, g.home_team, g.away_team, gr.name AS grade
        FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
        WHERE {club_game_sql("g", "org")} AND s.year = :y AND g.source = 'api' AND g.played_at <= :today
        ORDER BY g.played_at"""), {"org": str(org_id), "y": year, "today": today})).mappings().all()
    out, deferred, no_data = [], [], 0
    for g in games:
        sc = await fetch(str(g["id"]))
        if not sc:
            no_data += 1
            continue
        team = _our_team(sc, org_id)
        if not team:
            continue
        sheet = team.get("players") or []
        known = {}
        for p in sheet:
            guid = p.get("participantId") or ""
            kp = _known(guid, by_guid, merged) if guid else None
            if kp is not None:
                known[guid] = kp
        found = participant_names.resolve_roster_by_name(sheet, known, unique)
        if not found and not known:
            continue
        have = {r[0] for r in (await db.execute(text(
            "SELECT player_id FROM game_appearances WHERE game_id = :g"), {"g": g["id"]})).all()}
        names = {p.get("participantId"): (p.get("playerShortName") or p.get("displayName") or p.get("name")) for p in sheet}
        # Two kinds: an id we do not know but whose full name matches one player, and an
        # id we DO know (directly, or through a merge made after the game was stored)
        # whose player has no appearance in the stored game.
        # Sync stores a game's rows in one go and skips the game once any of our
        # players has an appearance in it. Where none has, sync has not finished our
        # side and will add every row itself on its next run; rows added here first
        # would collide with its inserts and fail the game for good. Leave those to it.
        if not (have & (set(known.values()) | set(found.values()))):
            deferred.append({"game_id": str(g["id"]), "date": g["played_at"], "match": f"{g['home_team']} v {g['away_team']}",
                             "grade": g["grade"], "players": len(sheet)})
            continue
        wanted, taken = {}, set()
        for guid, pid in {**known, **found}.items():
            if pid not in have and pid not in taken:
                wanted[guid] = pid
                taken.add(pid)
        missing = wanted
        if not missing:
            continue
        pname = {r[0]: r[1] for r in (await db.execute(text(
            "SELECT id, COALESCE(display_name_override, name) FROM players WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": [str(p) for p in missing.values()]})).all()}
        out.append({
            "game_id": str(g["id"]), "date": g["played_at"], "match": f"{g['home_team']} v {g['away_team']}", "grade": g["grade"],
            "missing": [{"guid": guid, "sheet_name": names.get(guid), "player_id": str(pid), "player": pname.get(pid)}
                        for guid, pid in missing.items()],
            "scorecard": sc,
        })
    return {"games": out, "deferred": deferred, "games_checked": len(games), "no_data": no_data}


async def attach(db: AsyncSession, org_id, game_id, scorecard: dict, wanted: dict) -> dict:
    """Add the appearance, batting, bowling and fielding rows for ``wanted``
    (``{participant guid: player id}``) to an already stored game. Mirrors what
    ``sync_grassroots_game_level_data`` writes for one of our players; skips any row
    already there."""
    team = _our_team(scorecard, org_id)
    if not team or not wanted:
        return {"appearances": 0, "batting": 0, "bowling": 0, "fielding": 0}
    gid = game_id if isinstance(game_id, uuid.UUID) else uuid.UUID(str(game_id))
    team_name = team.get("displayName") or team.get("name") or ""
    n = {"appearances": 0, "batting": 0, "bowling": 0, "fielding": 0}

    for p in team.get("players") or []:
        pid = wanted.get(p.get("participantId") or "")
        if pid is None:
            continue
        roles = p.get("roles") or []
        if (await db.get(GameAppearance, (gid, pid))) is None:
            db.add(GameAppearance(
                game_id=gid, player_id=pid, team_name=team_name,
                is_captain=any((r or "").lower() == "captain" for r in roles),
                is_wicket_keeper=any("wicket" in (r or "").lower() for r in roles)))
            n["appearances"] += 1

    for inn in scorecard.get("innings") or []:
        inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
        keeper_names = _innings_keeper_names(inn.get("fielding") or [])

        for row in inn.get("batting") or []:
            pid = wanted.get(row.get("participantId") or "")
            if pid is None:
                continue
            dt_id = row.get("dismissalTypeId") or 0
            if dt_id == 0:
                continue
            if (await db.execute(select(BattingInnings.id).where(
                    BattingInnings.game_id == gid, BattingInnings.player_id == pid,
                    BattingInnings.innings_number == inn_num))).first():
                continue
            dt_long = row.get("dismissalType") or ""
            if dt_long.lower() in ("absent", "did not bat", "dnb"):
                db.add(BattingInnings(game_id=gid, player_id=pid, innings_number=inn_num,
                                      batting_position=row.get("batOrder"), runs=None, balls=None,
                                      fours=None, sixes=None, not_out=False, dismissal_type=None,
                                      did_not_bat=True))
            else:
                bounds = _bounds(row.get("runsScored") or 0, row.get("foursScored"), row.get("sixesScored"))
                db.add(BattingInnings(
                    game_id=gid, player_id=pid, innings_number=inn_num, batting_position=row.get("batOrder"),
                    runs=row.get("runsScored") or 0, balls=row.get("ballsFaced"),
                    fours=bounds[0], sixes=bounds[1], not_out=dismissal.is_not_out(dt_id, dt_long),
                    dismissal_type=(_GR_DISMISSAL_SHORT.get(dt_long, dt_long.lower()) or None),
                    caught_behind=(dt_long == "Caught"
                                   and _caught_by_keeper(row.get("dismissalText") or "", keeper_names)),
                    did_not_bat=False))
            n["batting"] += 1

        for row in inn.get("bowling") or []:
            pid = wanted.get(row.get("participantId") or "")
            if pid is None:
                continue
            if (await db.execute(select(BowlingSpell.id).where(
                    BowlingSpell.game_id == gid, BowlingSpell.player_id == pid,
                    BowlingSpell.innings_number == inn_num))).first():
                continue
            try:
                econ = float(row["economy"]) if row.get("economy") is not None else None
            except (TypeError, ValueError):
                econ = None
            db.add(BowlingSpell(
                game_id=gid, player_id=pid, innings_number=inn_num, overs=row.get("oversBowled"),
                maidens=row.get("maidensBowled"), runs=row.get("runsConceded"),
                wickets=row.get("wicketsTaken"), wides=row.get("wideBalls"),
                no_balls=row.get("noBalls"), economy=econ))
            n["bowling"] += 1

        for row in inn.get("fielding") or []:
            pid = wanted.get(row.get("participantId") or "")
            if pid is None:
                continue
            short = row.get("playerShortName")
            # Sync kept an unregistered fielder's catches under their name with no id:
            # give that row its player rather than writing a second one.
            orphan = (await db.execute(select(FieldingStat).where(
                FieldingStat.game_id == gid, FieldingStat.player_id.is_(None),
                FieldingStat.player_name == short))).scalars().first() if short else None
            if orphan is not None:
                orphan.player_id, orphan.player_name = pid, None
                n["fielding"] += 1
                continue
            if (await db.execute(select(FieldingStat.id).where(
                    FieldingStat.game_id == gid, FieldingStat.player_id == pid))).first():
                continue
            catches_wk = row.get("wicketKeeperCatches") or 0
            total = row.get("totalCatches")
            if total is None:
                total = (row.get("catches") or 0) + catches_wk
            db.add(FieldingStat(game_id=gid, player_id=pid, player_name=None, catches=total or 0,
                                catches_wk=catches_wk, run_outs=row.get("runOuts") or 0,
                                stumpings=row.get("stumpings") or 0))
            n["fielding"] += 1
    await db.flush()
    return n
