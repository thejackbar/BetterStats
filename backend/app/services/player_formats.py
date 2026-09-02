"""A player's record split by the format each match was actually played in.

Two-day, one-day and T20 cricket ask different things of a player, and a career
average that blends them hides the thing a selector wants to know — that a
batter who grinds out 40s across two days is a different proposition from the
one who wins a T20 in six overs.

**Every figure here is per FIXTURE, never per grade.** A grade is not a format:
Applecross 1st Grade plays 32 one-day and 26 two-day games in a single season, so
grouping by grade would put most of a season's games in the wrong column. The
split reads each game's own ``match_format`` through the same
``grade_labels.format_sql_case`` expression the dashboard's Match Type filter
uses, so the two can never disagree.

A game whose format was never recorded is reported in its own ``not_recorded``
bucket rather than being folded into one of the three. That is honest about
coverage — a club whose history predates the sync writing that column will see
most of its games there until ``app.scripts.backfill_match_format`` has run —
and it means the three real columns only ever contain matches we can vouch for.

Read from the per-innings scorecards only. CA's season aggregates carry no game
and therefore no format at all, so they cannot contribute: a player whose record
is an aggregate-only BetterImport residual has nothing to split, and the
endpoint says so instead of inventing a column.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aggregations import _club_game_clause

from app.services.grade_labels import FORMAT_LABELS, MATCH_FORMATS, format_sql_case
from app.services.game_status import appearance_counts_as_match
from app.services import rate_coverage as rc

# Same rule as everywhere else: a fixture the player was named in but that
# was called off is not a match played. See services/game_status.py.
_APPEARANCE_PLAYED = appearance_counts_as_match("ga")

# The bucket a game whose own match_format says nothing lands in. Deliberately
# not one of MATCH_FORMATS — it is the absence of an answer, not an answer.
UNKNOWN = "not_recorded"

_FMT = format_sql_case("g")


def _avg(runs, outs):
    return round(runs / outs, 2) if outs else None


def _rate(num, den, places=2):
    return round(num / den, places) if den else None


async def _season_ids(session: AsyncSession, season_id: Optional[str]) -> Optional[list]:
    """Resolve a season filter the same way the rest of the profile does —
    through the alias map, so a merged season still finds its games."""
    if not season_id:
        return None
    from app.services.season_aliases import resolve_season_filter_no_org
    return await resolve_season_filter_no_org(session, season_id)


async def player_format_splits(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
) -> dict:
    """Batting, bowling and fielding per format, plus what could not be placed.

    Scoped to the games the player's OWN club played, the same call
    ``get_career_batting_from_innings`` makes. A per-club ``player_id`` is not
    enough on its own: CA issues one participant GUID per person across every
    club they turn out for, so their rows can sit on a game belonging to
    another club and be counted here as one of this club's.
    """
    params: dict = {"pid": player_id}
    # The club filter rides along with the season one so every query below
    # picks both up from the same interpolation point.
    season_clause = await _club_game_clause(session, player_id, params)
    sids = await _season_ids(session, season_id)
    if sids:
        params["sids"] = sids
        season_clause += " AND g.season_id = ANY(:sids)"

    # Matches played, from every source of "they were in this game" — a player
    # who only bowled, only fielded, or was named and never got a knock still
    # counts the match. Mirrors _scoped_games_played.
    matches = await session.execute(
        text(f"""
            SELECT COALESCE({_FMT}, '{UNKNOWN}') AS fmt,
                   COUNT(DISTINCT g.id) AS matches,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.is_final) AS finals
            FROM v_effective_games g
            WHERE g.id IN (
                SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:pid AS UUID)
                UNION
                SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:pid AS UUID)
                  AND {_APPEARANCE_PLAYED}
            ){season_clause}
            GROUP BY 1
        """),
        params,
    )

    batting = await session.execute(
        text(f"""
            SELECT COALESCE({_FMT}, '{UNKNOWN}') AS fmt,
                   COUNT(*) AS innings,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   MAX(bi.runs) AS high_score,
                   COALESCE(SUM(bi.not_out::int), 0) AS not_outs,
                   SUM(bi.balls) AS balls,
                   {rc.batting_rate_columns('bi')},
                   SUM(bi.fours) AS fours,
                   SUM(bi.sixes) AS sixes,
                   COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) AS fifties,
                   COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds,
                   COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT bi.not_out) AS ducks
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            WHERE bi.player_id = CAST(:pid AS UUID)
              AND NOT COALESCE(bi.did_not_bat, FALSE)
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {season_clause}
            GROUP BY 1
        """),
        params,
    )

    # Overs are cricket notation (10.2 = 10 overs and 2 balls), so they are
    # converted to balls before summing — the same conversion iq_team's attack
    # structure makes. Summing the decimals directly overstates every economy.
    bowling = await session.execute(
        text(f"""
            SELECT COALESCE({_FMT}, '{UNKNOWN}') AS fmt,
                   COUNT(*) AS spells,
                   COALESCE(SUM(bs.wickets), 0) AS wickets,
                   -- `runs` on bowling_spells is runs CONCEDED. Named plainly on
                   -- the table, so alias it here rather than in the reader.
                   COALESCE(SUM(bs.runs), 0) AS runs_conceded,
                   COALESCE(SUM(
                       FLOOR(COALESCE(bs.overs, 0))::int * 6
                       + ROUND((COALESCE(bs.overs, 0) - FLOOR(COALESCE(bs.overs, 0))) * 10)::int
                   ), 0) AS balls,
                   COALESCE(SUM(bs.maidens), 0) AS maidens,
                   {rc.bowling_rate_columns('bs')},
                   MAX(bs.wickets) AS best_wickets,
                   COUNT(*) FILTER (WHERE bs.wickets >= 5) AS five_fors
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            WHERE bs.player_id = CAST(:pid AS UUID){season_clause}
            GROUP BY 1
        """),
        params,
    )

    fielding = await session.execute(
        text(f"""
            SELECT COALESCE({_FMT}, '{UNKNOWN}') AS fmt,
                   COALESCE(SUM(fs.catches), 0) AS catches,
                   COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
                   COALESCE(SUM(fs.run_outs), 0) AS run_outs,
                   COALESCE(SUM(fs.stumpings), 0) AS stumpings
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id
            WHERE fs.player_id = CAST(:pid AS UUID){season_clause}
            GROUP BY 1
        """),
        params,
    )

    m_by = {r["fmt"]: dict(r) for r in matches.mappings().all()}
    b_by = {r["fmt"]: dict(r) for r in batting.mappings().all()}
    w_by = {r["fmt"]: dict(r) for r in bowling.mappings().all()}
    f_by = {r["fmt"]: dict(r) for r in fielding.mappings().all()}

    def block(key: str) -> Optional[dict]:
        m, b, w, f = m_by.get(key), b_by.get(key), w_by.get(key), f_by.get(key)
        if not any((m, b, w, f)):
            return None
        innings = int((b or {}).get("innings") or 0)
        runs = int((b or {}).get("runs") or 0)
        not_outs = int((b or {}).get("not_outs") or 0)
        balls = (b or {}).get("balls")
        wickets = int((w or {}).get("wickets") or 0)
        conceded = int((w or {}).get("runs_conceded") or 0)
        bowl_balls = int((w or {}).get("balls") or 0)
        catches = int((f or {}).get("catches") or 0)
        catches_wk = int((f or {}).get("catches_wk") or 0)
        run_outs = int((f or {}).get("run_outs") or 0)
        stumpings = int((f or {}).get("stumpings") or 0)
        cov_runs = int((b or {}).get("covered_runs") or 0)
        cov_balls = int((b or {}).get("covered_balls") or 0)
        cov_inns = int((b or {}).get("covered_innings") or 0)
        cov_conceded = int((w or {}).get("covered_conceded") or 0)
        cov_bowl_balls = int((w or {}).get("covered_bowl_balls") or 0)
        cov_wickets = int((w or {}).get("covered_wickets") or 0)
        cov_spells = int((w or {}).get("covered_spells") or 0)
        return {
            "format": key,
            "label": FORMAT_LABELS.get(key, "Not recorded"),
            "matches": int((m or {}).get("matches") or 0),
            "finals": int((m or {}).get("finals") or 0),
            "batting": {
                "innings": innings,
                "runs": runs,
                "not_outs": not_outs,
                # Dismissals, not innings — a not-out is not an average's
                # denominator, and blending formats is exactly what this page
                # exists to stop, so each column recomputes from its own counts.
                "average": _avg(runs, innings - not_outs),
                # Only the innings that carry a ball count, so a format scored
                # partly on paper reports the rate it can actually stand behind.
                "strike_rate": rc.strike_rate(cov_runs, cov_balls),
                "strike_rate_coverage": rc.coverage(cov_inns, innings),
                "high_score": (b or {}).get("high_score"),
                "balls": int(balls) if balls is not None else None,
                "fours": (b or {}).get("fours"),
                "sixes": (b or {}).get("sixes"),
                "fifties": int((b or {}).get("fifties") or 0),
                "hundreds": int((b or {}).get("hundreds") or 0),
                "ducks": int((b or {}).get("ducks") or 0),
            },
            "bowling": {
                "innings": int((w or {}).get("spells") or 0),
                "wickets": wickets,
                "runs_conceded": conceded,
                "balls": bowl_balls,
                "overs": _rate(bowl_balls, 6, 1) if bowl_balls else None,
                "average": _avg(conceded, wickets),
                "economy": rc.economy(cov_conceded, cov_bowl_balls),
                "economy_coverage": rc.coverage(cov_spells, int((w or {}).get("spells") or 0)),
                "strike_rate": _rate(cov_bowl_balls, cov_wickets, 1) if cov_wickets else None,
                "maidens": int((w or {}).get("maidens") or 0),
                "best_wickets": (w or {}).get("best_wickets"),
                "five_fors": int((w or {}).get("five_fors") or 0),
            },
            "fielding": {
                "catches": catches,
                "catches_wk": catches_wk,
                "catches_non_wk": max(catches - catches_wk, 0),
                "run_outs": run_outs,
                "stumpings": stumpings,
                "dismissals": catches + run_outs + stumpings,
            },
        }

    formats = [b for b in (block(k) for k in MATCH_FORMATS) if b]
    unknown = block(UNKNOWN)
    placed = sum(f["matches"] for f in formats)
    unplaced = unknown["matches"] if unknown else 0
    return {
        "formats": formats,
        "not_recorded": unknown,
        "coverage": {
            "matches_placed": placed,
            "matches_not_recorded": unplaced,
            # What share of this player's matches we can actually attribute. A
            # club sitting near zero has not had the match_format backfill run.
            "percent_placed": _rate(placed * 100, placed + unplaced, 1),
        },
    }
