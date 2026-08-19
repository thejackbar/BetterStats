"""BetterFootball — the team list PlayHQ returns with a game.

The cricket silo fetches a team list LIVE from Grassroots on every request and
persists nothing (see ``services/lineups.py``). Football doesn't need to: the
same array cricket has to go and fetch — PlayHQ's
``gameView.statistics.{home,away}.players[]`` — is already pulled by the sync
and stored as ``afl_player_game_lines``, one row per player per side, both
teams, carrying the jumper number, the captain flag and who the club's own
players resolve to. So a team list here is a plain read of held data: no
upstream call, no cache, and it keeps working when PlayHQ is down.

The consequence worth knowing is that a team list only exists once the game has
been synced, and the sync only fetches games PlayHQ has marked FINAL. That is
deliberate (post-game only, per direct instruction) — a scheduled game reads as
"not played yet" rather than as an empty side.

``publish_lineup`` is PlayHQ's own flag for whether the club published a side,
which is what separates "this club never named a team" from "we haven't synced
this game yet". Both render as an empty list; only one is worth chasing.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def game_lineups(db: AsyncSession, org_id, game_id) -> Optional[dict]:
    """Both teams' named sides for one game, or None when the game isn't ours.

    Ordered the way a team sheet reads: captains first, then by jumper number,
    then by name — an unnumbered player sorts last rather than first, which is
    what a NULL would otherwise do.
    """
    res = await db.execute(
        text(
            """
            SELECT g.id, d.our_side, d.round_name, d.status, d.publish_lineup,
                   d.home_logo_url, d.away_logo_url, d.venue_name,
                   g.played_at, g.home_team, g.away_team,
                   gr.id AS grade_id, gr.name AS grade_name, s.id AS season_id, s.name AS season_name
            FROM games g
            JOIN afl_game_details d ON d.game_id = g.id
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = gr.season_id
            WHERE g.id = :gid AND s.organisation_id = :org
            """
        ),
        {"gid": game_id, "org": org_id},
    )
    row = res.mappings().first()
    if not row:
        return None

    lines = await db.execute(
        text(
            """
            SELECT l.side, l.team_name, l.player_id, l.name, l.jumper_number,
                   l.is_captain, l.played, l.goals, l.behinds, l.bog_ranking,
                   p.photo_url
            FROM afl_player_game_lines l
            LEFT JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
            WHERE l.game_id = :gid
            ORDER BY l.side,
                     l.is_captain DESC,
                     NULLIF(regexp_replace(COALESCE(l.jumper_number, ''), '\\D', '', 'g'), '')::int
                         NULLS LAST,
                     l.name
            """
        ),
        {"gid": game_id, "org": org_id},
    )

    sides: dict[str, list[dict]] = {"HOME": [], "AWAY": []}
    team_names: dict[str, Optional[str]] = {"HOME": row["home_team"], "AWAY": row["away_team"]}
    for r in lines.mappings().all():
        side = r["side"] if r["side"] in sides else "HOME"
        team_names[side] = r["team_name"] or team_names.get(side)
        sides[side].append({
            "player_id": str(r["player_id"]) if r["player_id"] else None,
            "name": r["name"],
            "jumper_number": r["jumper_number"],
            "is_captain": bool(r["is_captain"]),
            "played": r["played"] is not False,
            "goals": r["goals"],
            "behinds": r["behinds"],
            "bog_ranking": r["bog_ranking"],
            "photo_url": r["photo_url"],
        })

    our = row["our_side"] if row["our_side"] in sides else None
    return {
        "game_id": str(row["id"]),
        "round": row["round_name"],
        "status": row["status"],
        "date": row["played_at"].isoformat() if row["played_at"] else None,
        "venue": row["venue_name"],
        "grade_id": str(row["grade_id"]) if row["grade_id"] else None,
        "grade": row["grade_name"],
        "season_id": str(row["season_id"]) if row["season_id"] else None,
        "season": row["season_name"],
        # NULL means PlayHQ didn't tell us either way (an older sync, or a game
        # synced before this flag was stored). Reported as-is rather than
        # guessed at, so the screen can stay quiet instead of claiming a club
        # failed to publish a side it may well have published.
        "published": row["publish_lineup"],
        "our_side": our,
        "teams": [
            {
                "side": side,
                "name": team_names.get(side),
                "logo_url": row["home_logo_url"] if side == "HOME" else row["away_logo_url"],
                "is_ours": side == our,
                "players": sides[side],
            }
            for side in ("HOME", "AWAY")
        ],
    }


async def our_lineup_players(db: AsyncSession, org_id, game_id) -> tuple[list[dict], list[str]]:
    """``(players, unmatched)`` for the club's own side — the votable list.

    Only a line that resolved to one of our ``players`` rows can be voted for
    or vote, since a ballot pick is a real player foreign key. A named player
    we hold no record for (a fill-in, a late inclusion the sync hasn't minted
    yet) comes back in ``unmatched`` rather than being silently dropped, so an
    admin can see why the list is short instead of wondering.

    ``played`` is respected where the sync has set it: someone named on the
    team sheet who didn't take the field shouldn't be on the ballot. Today
    nothing writes it false, so this is a no-op that starts working the moment
    something does — which is the point of reading it now rather than later.
    """
    res = await db.execute(
        text(
            """
            SELECT l.player_id, l.name, l.is_captain, l.played,
                   COALESCE(p.display_name_override, p.name) AS player_name
            FROM afl_player_game_lines l
            JOIN afl_game_details d ON d.game_id = l.game_id
            LEFT JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
            WHERE l.game_id = :gid AND l.side = d.our_side
            ORDER BY 5, 2
            """
        ),
        {"gid": game_id, "org": org_id},
    )
    players: list[dict] = []
    unmatched: list[str] = []
    seen: set[str] = set()
    for r in res.mappings().all():
        if r["played"] is False:
            continue
        pid = r["player_id"]
        if not pid or not r["player_name"]:
            if r["name"]:
                unmatched.append(r["name"])
            continue
        key = str(pid)
        if key in seen:
            continue
        seen.add(key)
        players.append({
            "id": key,
            "name": r["player_name"],
            "is_captain": bool(r["is_captain"]),
        })
    return players, unmatched


async def lineup_counts(db: AsyncSession, org_id, game_ids: list) -> dict[str, int]:
    """How many votable players each game has, in one query rather than one per
    row — the games list needs this for every game on the page."""
    if not game_ids:
        return {}
    res = await db.execute(
        text(
            """
            SELECT l.game_id, COUNT(DISTINCT l.player_id)
            FROM afl_player_game_lines l
            JOIN afl_game_details d ON d.game_id = l.game_id
            JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
            WHERE l.game_id = ANY(:ids) AND l.side = d.our_side
              AND l.played IS NOT FALSE
            GROUP BY l.game_id
            """
        ),
        {"ids": game_ids, "org": org_id},
    )
    return {str(gid): n for gid, n in res.fetchall()}
