"""A club leaves a whole match out of its players' stats ("Exclude scorecard from career stats").

WHY THIS EXISTS
---------------
Cricket Australia lists friendlies, pre-season cups and social midweek T20s beside the real
competition, and its season totals count every one of them. Kalamunda's Tuesday T20 against Hills
(the Mountford Tillemans Shield) is the case that asked for it: the club wants the match on its
Results and its scorecard, and nowhere in a player's career.

WHAT IT DOES
------------
One row in ``game_stat_exclusions`` (migration 401, ``services/stat_exclusion_ddl``) per club and
match. While it is in force, for that club's players only:

  * the six per-innings effective views leave the match's rows out (``superseded_ddl``,
    ``kept_sql``), so every per-match figure follows: records, milestones, StatLab, boards, the
    by-grade grid, best figures, partnerships;
  * Cricket Australia's season total stays, LESS the match: ``v_effective_player_season_stats`` reads
    the match's own scorecard for the player (the ``sx`` lateral, through ``v_stat_excluded_seasons``,
    which names the club's own season for it) and takes its runs, wickets, catches and the match off.
    Every other match in CA's total keeps counting, including one we hold no scorecard for. A season
    best (high score, best bowling) set in the excluded match falls to the best of the season's other
    scorecards, the one figure subtraction cannot answer exactly. In a season Card review counts from
    scorecards, the ``api_scorecard`` branch leaves the match out instead;
  * ``game_status.appearance_counts_as_match`` stops counting the team sheet as a match played.

The match itself stays on Fixtures, Results and its scorecard, which reads the ``v_card_*`` copies
of the fall-of-wickets and partnership views. Fees still count it as a match day.

WHOSE FIGURES
-------------
Only the club that excluded it. A fixture between two clubs is one ``games`` row (CLAUDE.md rule 2),
so every test is keyed through the player's own club, never the season that holds the game: the
other club's players keep the match unless their club excludes it too.

UNDO
----
Counting the match again sets ``restored_at`` and keeps the row (rule 7). Both directions are on
the Manual entries audit trail, where either can be undone.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLE = "game_stat_exclusions"

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class Refused(Exception):
    """A request the club can read and act on. ``status`` is the HTTP code to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def parse_link(raw: str) -> uuid.UUID:
    """The match id in whatever was pasted.

    A play.cricket.com.au match link and a BetterCricket match link both carry Cricket Australia's
    match GUID (``/match/<guid>/...`` and ``/games/<guid>``), and so does a bare id. A PlayHQ
    game-centre link carries a short code that maps to nothing we hold, so it is refused with what to
    paste instead.
    """
    s = (raw or "").strip()
    if not s:
        raise Refused("Paste a match link from play.cricket.com.au or BetterCricket.")
    m = _UUID_RE.search(s)
    if m:
        return uuid.UUID(m.group(0))
    if "playhq.com" in s.lower():
        raise Refused("That's a PlayHQ link. Open the same match on play.cricket.com.au, "
                      "or on your BetterCricket site, and paste that link instead.")
    raise Refused("That doesn't look like a match link. Paste the address of the match from "
                  "play.cricket.com.au or from your BetterCricket site.")


# Every row of one of the club's players in the match, from whichever table holds the card.
_PLAYER_ROWS = {
    "api": """
        SELECT player_id FROM game_appearances WHERE game_id = CAST(:g AS UUID)
        UNION SELECT player_id FROM batting_innings WHERE game_id = CAST(:g AS UUID)
        UNION SELECT player_id FROM bowling_spells WHERE game_id = CAST(:g AS UUID)
        UNION SELECT player_id FROM fielding_stats WHERE game_id = CAST(:g AS UUID)
    """,
    "manual": """
        SELECT player_id FROM manual_batting_innings WHERE manual_game_id = CAST(:g AS UUID)
        UNION SELECT player_id FROM manual_bowling_spells WHERE manual_game_id = CAST(:g AS UUID)
        UNION SELECT player_id FROM manual_fielding_stats WHERE manual_game_id = CAST(:g AS UUID)
    """,
}

_TABLES = {
    "api": ("batting_innings", "bowling_spells", "fielding_stats", "game_id"),
    "manual": ("manual_batting_innings", "manual_bowling_spells", "manual_fielding_stats", "manual_game_id"),
}


async def _locate(db: AsyncSession, game_id: uuid.UUID) -> Optional[dict]:
    """The match, from the synced table or the hand-entered one, with what the club sees of it."""
    row = (await db.execute(text("""
        SELECT 'api' AS source, g.id, g.home_team, g.away_team, g.played_at, g.result, g.status,
               g.home_org_id, g.away_org_id, s.organisation_id AS owner_org_id,
               gr.name AS grade_name, s.name AS season_name
          FROM games g
          LEFT JOIN grades gr ON gr.id = g.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
         WHERE g.id = CAST(:g AS UUID)
        UNION ALL
        SELECT 'manual', mg.id, mg.home_team, mg.away_team, mg.played_at, mg.result, NULL,
               NULL, NULL, mg.organisation_id,
               gr.name, s.name
          FROM manual_games mg
          LEFT JOIN grades gr ON gr.id = mg.grade_id
          LEFT JOIN seasons s ON s.id = mg.season_id
         WHERE mg.id = CAST(:g AS UUID)
         LIMIT 1
    """), {"g": str(game_id)})).mappings().first()
    return dict(row) if row else None


async def _club_players(db: AsyncSession, org_id, game_id, source: str) -> list[dict]:
    """The club's players in the match and what they did in it: what the exclusion takes away."""
    bat, bowl, field, col = _TABLES[source]
    rows = (await db.execute(text(f"""
        WITH ours AS (
            SELECT DISTINCT r.player_id FROM ({_PLAYER_ROWS[source]}) r
            JOIN players p ON p.id = r.player_id AND p.organisation_id = CAST(:o AS UUID)
        )
        SELECT p.id::text AS player_id,
               COALESCE(p.display_name_override, p.name) AS name,
               (SELECT COALESCE(SUM(b.runs), 0) FROM {bat} b
                 WHERE b.{col} = CAST(:g AS UUID) AND b.player_id = p.id
                   AND NOT COALESCE(b.did_not_bat, FALSE))::int AS runs,
               (SELECT COUNT(*) FROM {bat} b
                 WHERE b.{col} = CAST(:g AS UUID) AND b.player_id = p.id
                   AND NOT COALESCE(b.did_not_bat, FALSE))::int AS innings,
               (SELECT COALESCE(SUM(w.wickets), 0) FROM {bowl} w
                 WHERE w.{col} = CAST(:g AS UUID) AND w.player_id = p.id)::int AS wickets,
               (SELECT COALESCE(SUM(COALESCE(f.catches, 0) + COALESCE(f.stumpings, 0)
                                    + COALESCE(f.run_outs, 0)), 0) FROM {field} f
                 WHERE f.{col} = CAST(:g AS UUID) AND f.player_id = p.id)::int AS dismissals
          FROM ours JOIN players p ON p.id = ours.player_id
         ORDER BY runs DESC, wickets DESC, name
    """), {"o": str(org_id), "g": str(game_id)})).mappings().all()
    return [dict(r) for r in rows]


def _iso(v) -> Optional[str]:
    return v.isoformat() if v is not None else None


async def _in_force(db: AsyncSession, org_id, game_id) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT x.id, x.game_id::text AS game_id, x.source, x.note, x.entered_at,
               x.entered_by::text AS entered_by, u.username AS entered_by_name
          FROM game_stat_exclusions x
          LEFT JOIN users u ON u.id = x.entered_by
         WHERE x.organisation_id = CAST(:o AS UUID) AND x.game_id = CAST(:g AS UUID)
           AND x.restored_at IS NULL
    """), {"o": str(org_id), "g": str(game_id)})).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["entered_at"] = _iso(out["entered_at"])
    return out


async def match_info(db: AsyncSession, org_id, game_id: uuid.UUID) -> dict:
    """Everything the confirm step shows: the match, the club's players in it and their figures,
    and the exclusion in force if there is one. Refuses a match the club did not play in."""
    m = await _locate(db, game_id)
    if m is None:
        raise Refused("We don't hold that match yet. It can be excluded once it has synced to "
                      "BetterCricket.", status=404)
    players = await _club_players(db, org_id, game_id, m["source"])
    org = str(org_id)
    ours = (str(m.get("owner_org_id") or "") == org or str(m.get("home_org_id") or "") == org
            or str(m.get("away_org_id") or "") == org or bool(players))
    if not ours:
        raise Refused("That match isn't one of your club's. Only a match your club played in can be "
                      "excluded.", status=404)
    # The club's own side, from its players' team sheet, so the confirm step can name the side that
    # keeps the match. Nothing is guessed from names: with no sheet (an uploaded card) it is left out.
    club_team = None
    if m["source"] == "api":
        club_team = (await db.execute(text("""
            SELECT ga.team_name FROM game_appearances ga
              JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:o AS UUID)
             WHERE ga.game_id = CAST(:g AS UUID) AND ga.team_name IS NOT NULL
             GROUP BY ga.team_name ORDER BY COUNT(*) DESC LIMIT 1
        """), {"o": org, "g": str(game_id)})).scalar()
    other_team = None
    if club_team and club_team in (m["home_team"], m["away_team"]):
        other_team = m["away_team"] if club_team == m["home_team"] else m["home_team"]
    return {
        "game_id": str(m["id"]),
        "source": m["source"],
        "club_team": club_team,
        "other_team": other_team,
        "home_team": m["home_team"],
        "away_team": m["away_team"],
        "played_at": _iso(m["played_at"]),
        "result": m["result"],
        "status": m["status"],
        "grade_name": m["grade_name"],
        "season_name": m["season_name"],
        "players": players,
        "totals": {
            "players": len(players),
            "runs": sum(p["runs"] for p in players),
            "wickets": sum(p["wickets"] for p in players),
            "dismissals": sum(p["dismissals"] for p in players),
        },
        "exclusion": await _in_force(db, org_id, game_id),
    }


def summary(info: dict, what: str) -> str:
    """"HWCC Tuesday T20 v KCC Tuesday T20 on 25 Nov 2026 left out of career stats"."""
    when = ""
    if info.get("played_at"):
        d = datetime.fromisoformat(str(info["played_at"])).date()
        when = f" on {d.day} {d.strftime('%b %Y')}"
    match = f"{info.get('home_team') or ''} v {info.get('away_team') or ''}".strip()
    return f"{match}{when} {what}"


async def exclude(db: AsyncSession, org_id, user_id, game_id: uuid.UUID, source: str,
                  note: Optional[str]) -> dict:
    """Put an exclusion in force. Refused when one already is. Returns the row as a snapshot."""
    if await _in_force(db, org_id, game_id):
        raise Refused("That match is already left out of your stats.", status=409)
    row = (await db.execute(text("""
        INSERT INTO game_stat_exclusions (organisation_id, game_id, source, note, entered_by)
        VALUES (CAST(:o AS UUID), CAST(:g AS UUID), :s, :n, CAST(:u AS UUID))
        RETURNING id, entered_at
    """), {"o": str(org_id), "g": str(game_id), "s": source, "n": (note or "").strip() or None,
           "u": str(user_id) if user_id else None})).mappings().one()
    return {"id": row["id"], "game_id": str(game_id), "source": source,
            "note": (note or "").strip() or None, "entered_at": _iso(row["entered_at"])}


async def restore(db: AsyncSession, org_id, user_id, exclusion_id: int) -> Optional[dict]:
    """Count the match again: the row is kept and marked. None when it was not in force."""
    row = (await db.execute(text("""
        UPDATE game_stat_exclusions
           SET restored_at = NOW(), restored_by = CAST(:u AS UUID)
         WHERE id = :i AND organisation_id = CAST(:o AS UUID) AND restored_at IS NULL
        RETURNING id, game_id::text AS game_id, source, note
    """), {"i": int(exclusion_id), "o": str(org_id), "u": str(user_id) if user_id else None})).mappings().first()
    return dict(row) if row else None


async def players_in(db: AsyncSession, org_id, game_id, source: str) -> list[uuid.UUID]:
    """The club's players in the match, for the milestone recompute after a change."""
    return [uuid.UUID(p["player_id"]) for p in await _club_players(db, org_id, game_id, source)]


async def list_for_org(db: AsyncSession, org_id) -> list[dict]:
    """Every match the club has left out, newest first, with what the admin needs to recognise it."""
    rows = (await db.execute(text("""
        SELECT x.id, x.game_id::text AS game_id, x.source, x.note, x.entered_at,
               u.username AS entered_by_name,
               COALESCE(g.home_team, mg.home_team) AS home_team,
               COALESCE(g.away_team, mg.away_team) AS away_team,
               COALESCE(g.played_at, mg.played_at) AS played_at,
               COALESCE(g.result, mg.result) AS result,
               COALESCE(gr.name, mgr.name) AS grade_name,
               COALESCE(s.name, ms.name) AS season_name
          FROM game_stat_exclusions x
          LEFT JOIN users u ON u.id = x.entered_by
          LEFT JOIN games g ON g.id = x.game_id AND x.source = 'api'
          LEFT JOIN grades gr ON gr.id = g.grade_id
          LEFT JOIN seasons s ON s.id = gr.season_id
          LEFT JOIN manual_games mg ON mg.id = x.game_id AND x.source = 'manual'
          LEFT JOIN grades mgr ON mgr.id = mg.grade_id
          LEFT JOIN seasons ms ON ms.id = mg.season_id
         WHERE x.organisation_id = CAST(:o AS UUID) AND x.restored_at IS NULL
         ORDER BY x.entered_at DESC, x.id DESC
    """), {"o": str(org_id)})).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["entered_at"] = _iso(d["entered_at"])
        d["played_at"] = _iso(d["played_at"])
        out.append(d)
    return out


async def is_excluded(db: AsyncSession, org_id, game_id) -> bool:
    """Public: has this club left the match out of its stats? For the badge on the scorecard."""
    if org_id is None:
        return False
    return bool((await db.execute(text("""
        SELECT 1 FROM game_stat_exclusions
         WHERE organisation_id = CAST(:o AS UUID) AND game_id = CAST(:g AS UUID) AND restored_at IS NULL
    """), {"o": str(org_id), "g": str(game_id)})).first())
