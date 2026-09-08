"""The one copy of the superseded-season DDL, run by alembic and the lifespan.

A club that syncs from Cricket Australia and also imports its CricketStatz
history holds the same matches twice, and every career total, average and
record board counts them twice (reported live: a batter reading 14,966 runs
where CricketStatz has 10,444). A club may decide CricketStatz is the record
for a season it already syncs.

`seasons.stats_source = 'cricketstatz'` is that decision, and it is applied
**on read, in the effective views**, the way migration 060's org scoping and
266's washout correction are:

* nothing is deleted, so the club's Cricket Australia data is still there,
* the sync keeps running and keeps the synced copy current underneath,
* clearing the marker puts it straight back, with no re-sync and no migration.

**ONE SOURCE PER SEASON. NEVER BOTH.** Three states, and the invariant is that
a season holding CricketStatz matches is never left in the third:

* `'cricketstatz'` — count the imported matches, step the synced side aside.
* `'playhq'`       — count the synced games, step the imported side aside.
* NULL             — count both, which is only ever safe because a season that
                     receives a CricketStatz match is set to `'cricketstatz'`
                     in the SAME transaction as the match (see
                     `cricketstatz_import.import_match`), so NULL and imported
                     matches cannot coexist.

The earlier design worked the overlap out ONCE at the start of a run and marked
the seasons as it walked them. Anything that changed `games` in between — a
Full Rebuild finishing, a sync landing — left that snapshot wrong, and the club
counted both sources with nothing on screen to say so. Reported live: a career
reading 14,966 runs against CricketStatz's 10,444, and every shared season
holding exactly synced + imported. **Decide it from the data, not from a step.**

**BOTH DEFINITIONS ARE TAKEN FROM MIGRATION 266, THE LAST ONE TO DEFINE EACH,
and that is not a detail.** `CREATE OR REPLACE VIEW` cannot drop a column, so
re-issuing an OLDER definition of a view aborts — the first cut took
`v_effective_games` from 169, which predates the `status` column 266 added, and
the migration failed on every boot and took the API down with it. When adding a
clause to a view here, start from the newest definition and diff it.
"""
from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS stats_source TEXT",
    # Migration 291's column, guarded here too: this module re-issues
    # v_effective_batting_innings, which reads it, and a view cannot be
    # created against a column that is not there yet.
    "ALTER TABLE manual_batting_innings ADD COLUMN IF NOT EXISTS "
    "caught_behind BOOLEAN",
    # Tiny by construction — only the seasons a club has re-sourced — so the
    # views' own test is an index lookup rather than a scan.
    "CREATE INDEX IF NOT EXISTS ix_seasons_stats_source "
    "ON seasons (organisation_id) WHERE stats_source IS NOT NULL",
    """CREATE OR REPLACE VIEW v_effective_games AS
    SELECT
        g.id, g.grade_id, g.played_at, g.home_team, g.away_team,
        g.home_club, g.away_club, g.opp_org_id, g.opp_club_name,
        g.result, g.winning_team, g.is_final,
        g.raw_payload, g.venue, g.match_format,
        'api'::text AS source,
        g.home_org_id, g.away_org_id,
        gr.season_id AS season_id,
        s.organisation_id AS organisation_id,
        g.status AS status
    FROM games g
    LEFT JOIN grades gr ON gr.id = g.grade_id
    LEFT JOIN seasons s ON s.id = gr.season_id
    -- A season the club has said CricketStatz is the record for keeps its
    -- imported matches and steps its synced ones aside, so one match is
    -- never counted from two sources. Filtered on READ: nothing is
    -- deleted, the sync keeps working, and clearing the marker brings the
    -- synced copy straight back.
    WHERE s.stats_source IS DISTINCT FROM 'cricketstatz'
    UNION ALL
    SELECT
        mg.id, mg.grade_id, mg.played_at, mg.home_team, mg.away_team,
        NULL::text AS home_club,
        NULL::text AS away_club,
        NULL::text AS opp_org_id,
        mg.opposition AS opp_club_name,
        mg.result, mg.winning_team, mg.is_final,
        NULL::jsonb AS raw_payload,
        mg.venue, mg.match_format,
        'manual'::text AS source,
        NULL::uuid AS home_org_id,
        NULL::uuid AS away_org_id,
        mg.season_id AS season_id,
        mg.organisation_id AS organisation_id,
        NULL::text AS status
    FROM manual_games mg
    LEFT JOIN seasons ms ON ms.id = mg.season_id
    WHERE mg.cricketstatz_import_id IS NULL
       OR ms.stats_source IS DISTINCT FROM 'playhq'""",
    """CREATE OR REPLACE VIEW v_effective_player_season_stats AS
    SELECT
        player_id, season_id,
        NULL::uuid AS grade_id,
        'api'::text AS source,
        -- Abandoned and cancelled fixtures the player was named in but
        -- never actually played come off CA's own counter. See the
        -- migration docstring for why they are in it in the first place.
        GREATEST(matches - COALESCE(unplayed.unplayed_matches, 0), 0) AS matches,
        batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out, batting_average, batting_strike_rate,
        fours, sixes, batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        bowling_economy, bowling_average, bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk, catches_non_wk, run_outs,
        assisted_run_outs, unassisted_run_outs, stumpings,
        NULL::text AS grade_label
    FROM player_season_stats pss
    LEFT JOIN (
        -- One row per (player, season): how many abandoned or cancelled
        -- fixtures that player was NAMED in and recorded nothing at all in.
        -- Named-but-nothing-recorded is the whole test. A game abandoned
        -- after play started leaves real batting/bowling/fielding rows behind
        -- and the club counts it as played, so it must stay counted; a washout
        -- leaves a team sheet and nothing else, and that is the one CA counts
        -- and the club does not.
        SELECT
            ga.player_id AS unplayed_player_id,
            gr.season_id AS unplayed_season_id,
            COUNT(DISTINCT ga.game_id)::integer AS unplayed_matches
        FROM game_appearances ga
        JOIN games g ON g.id = ga.game_id
        JOIN grades gr ON gr.id = g.grade_id
        WHERE g.status IN ('ABANDONED', 'CANCELLED')
          AND NOT EXISTS (
              SELECT 1 FROM batting_innings bi
              WHERE bi.game_id = ga.game_id AND bi.player_id = ga.player_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM bowling_spells bs
              WHERE bs.game_id = ga.game_id AND bs.player_id = ga.player_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM fielding_stats fs
              WHERE fs.game_id = ga.game_id AND fs.player_id = ga.player_id
          )
        GROUP BY ga.player_id, gr.season_id
    ) unplayed
        ON unplayed.unplayed_player_id = pss.player_id
       AND unplayed.unplayed_season_id = pss.season_id
    -- Only surface a season-stats row when its season belongs to the same
    -- organisation as the player. Filters out cross-club rows that CA's shared
    -- participant GUID lets a second club's sync attach to a player owned by
    -- the first club. NULL-org players are kept (can't be scoped).
    WHERE EXISTS (
        SELECT 1
        FROM players pl
        JOIN seasons s ON s.id = pss.season_id
        WHERE pl.id = pss.player_id
          AND (pl.organisation_id IS NULL OR pl.organisation_id = s.organisation_id)
          -- Cricket Australia's own season totals for a season the club
          -- has said CricketStatz is the record for. The 'manual_game'
          -- branch below rolls the imported matches up instead, so the
          -- season is counted once.
          AND s.stats_source IS DISTINCT FROM 'cricketstatz'
    )

    UNION ALL

    SELECT
        player_id, season_id, grade_id,
        'manual_aggregate'::text AS source,
        games_played AS matches,
        batting_innings,
        batting_runs AS runs,
        batting_not_outs AS not_outs,
        batting_balls AS balls_faced,
        batting_fifties AS fifties,
        batting_hundreds AS hundreds,
        batting_ducks AS ducks,
        batting_high_score AS high_score,
        batting_high_score_not_out AS is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        batting_fours AS fours,
        batting_sixes AS sixes,
        NULL::integer AS batting_minutes,
        bowling_innings,
        bowling_wickets AS wickets,
        bowling_overs AS overs,
        bowling_balls,
        bowling_runs AS runs_conceded,
        bowling_maidens AS maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        bowling_best_wickets AS best_bowling_wickets,
        bowling_best_figures AS best_bowling_figures,
        bowling_five_wicket_innings AS five_wicket_innings,
        bowling_wides AS wides,
        bowling_no_balls AS no_balls,
        fielding_catches AS catches,
        fielding_catches_wk AS catches_wk,
        GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
        fielding_run_outs AS run_outs,
        0 AS assisted_run_outs,
        fielding_run_outs AS unassisted_run_outs,
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
    FROM manual_season_adjustments

    UNION ALL

    -- Career-only adjustments (NULL season_id so they're invisible
    -- to season-keyed leaderboards but flow into career profile views).
    SELECT
        player_id,
        NULL::uuid AS season_id,
        NULL::uuid AS grade_id,
        'manual_career'::text AS source,
        games_played AS matches,
        batting_innings,
        batting_runs AS runs,
        batting_not_outs AS not_outs,
        batting_balls AS balls_faced,
        batting_fifties AS fifties,
        batting_hundreds AS hundreds,
        batting_ducks AS ducks,
        batting_high_score AS high_score,
        batting_high_score_not_out AS is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        batting_fours AS fours,
        batting_sixes AS sixes,
        NULL::integer AS batting_minutes,
        bowling_innings,
        bowling_wickets AS wickets,
        bowling_overs AS overs,
        bowling_balls,
        bowling_runs AS runs_conceded,
        bowling_maidens AS maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        bowling_best_wickets AS best_bowling_wickets,
        bowling_best_figures AS best_bowling_figures,
        bowling_five_wicket_innings AS five_wicket_innings,
        0 AS wides,
        0 AS no_balls,
        fielding_catches AS catches,
        fielding_catches_wk AS catches_wk,
        GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
        fielding_run_outs AS run_outs,
        0 AS assisted_run_outs,
        fielding_run_outs AS unassisted_run_outs,
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
    FROM manual_career_adjustments

    UNION ALL

    -- Manual games rolled up per (player, season, grade) — unchanged
    -- from migration 037.
    SELECT
        mg_agg.player_id,
        mg_agg.season_id,
        mg_agg.grade_id,
        'manual_game'::text AS source,
        mg_agg.matches,
        mg_agg.batting_innings,
        mg_agg.runs,
        mg_agg.not_outs,
        mg_agg.balls_faced,
        mg_agg.fifties,
        mg_agg.hundreds,
        mg_agg.ducks,
        mg_agg.high_score,
        mg_agg.is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        mg_agg.fours,
        mg_agg.sixes,
        NULL::integer AS batting_minutes,
        mg_agg.bowling_innings,
        mg_agg.wickets,
        mg_agg.overs,
        mg_agg.bowling_balls,
        mg_agg.runs_conceded,
        mg_agg.maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        mg_agg.best_bowling_wickets,
        mg_agg.best_bowling_figures,
        mg_agg.five_wicket_innings,
        mg_agg.wides,
        mg_agg.no_balls,
        mg_agg.catches,
        mg_agg.catches_wk,
        GREATEST(mg_agg.catches - mg_agg.catches_wk, 0) AS catches_non_wk,
        mg_agg.run_outs,
        0 AS assisted_run_outs,
        mg_agg.run_outs AS unassisted_run_outs,
        mg_agg.stumpings,
        NULL::text AS grade_label
    FROM (
        WITH player_games AS (
            SELECT mg.id AS manual_game_id, mg.season_id, mg.grade_id, mbi.player_id
            FROM manual_games mg JOIN manual_batting_innings mbi ON mbi.manual_game_id = mg.id
            LEFT JOIN seasons ms ON ms.id = mg.season_id
            WHERE mg.cricketstatz_import_id IS NULL
               OR ms.stats_source IS DISTINCT FROM 'playhq'
            UNION
            SELECT mg.id, mg.season_id, mg.grade_id, mbs.player_id
            FROM manual_games mg JOIN manual_bowling_spells mbs ON mbs.manual_game_id = mg.id
            LEFT JOIN seasons ms ON ms.id = mg.season_id
            WHERE mg.cricketstatz_import_id IS NULL
               OR ms.stats_source IS DISTINCT FROM 'playhq'
            UNION
            SELECT mg.id, mg.season_id, mg.grade_id, mfs.player_id
            FROM manual_games mg JOIN manual_fielding_stats mfs ON mfs.manual_game_id = mg.id
            LEFT JOIN seasons ms ON ms.id = mg.season_id
            WHERE mg.cricketstatz_import_id IS NULL
               OR ms.stats_source IS DISTINCT FROM 'playhq'
        )
        SELECT
            pg.player_id,
            pg.season_id,
            pg.grade_id,
            COUNT(DISTINCT pg.manual_game_id)::integer AS matches,
            COUNT(*) FILTER (WHERE mbi.id IS NOT NULL AND NOT mbi.did_not_bat)::integer AS batting_innings,
            COALESCE(SUM(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS runs,
            COUNT(*) FILTER (WHERE mbi.not_out)::integer AS not_outs,
            COALESCE(SUM(mbi.balls) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS balls_faced,
            COUNT(*) FILTER (WHERE mbi.runs >= 50 AND mbi.runs < 100)::integer AS fifties,
            COUNT(*) FILTER (WHERE mbi.runs >= 100)::integer AS hundreds,
            COUNT(*) FILTER (WHERE mbi.runs = 0 AND NOT mbi.not_out AND NOT mbi.did_not_bat)::integer AS ducks,
            MAX(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat) AS high_score,
            COALESCE(BOOL_OR(mbi.not_out) FILTER (
                WHERE mbi.runs = (
                    SELECT MAX(mbi2.runs)
                    FROM manual_batting_innings mbi2
                    JOIN manual_games mg2 ON mg2.id = mbi2.manual_game_id
                    WHERE mbi2.player_id = pg.player_id
                      AND mg2.season_id = pg.season_id
                      AND COALESCE(mg2.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                          = COALESCE(pg.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                      AND NOT mbi2.did_not_bat
                )
            ), false) AS is_hs_not_out,
            COALESCE(SUM(mbi.fours) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS fours,
            COALESCE(SUM(mbi.sixes) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS sixes,
            COUNT(*) FILTER (WHERE mbs.id IS NOT NULL)::integer AS bowling_innings,
            COALESCE(SUM(mbs.wickets), 0)::integer AS wickets,
            COALESCE(SUM(mbs.overs), 0)::numeric AS overs,
            COALESCE(SUM(FLOOR(mbs.overs)::integer * 6
                         + ((mbs.overs - FLOOR(mbs.overs)) * 10)::integer), 0)::integer AS bowling_balls,
            COALESCE(SUM(mbs.runs), 0)::integer AS runs_conceded,
            COALESCE(SUM(mbs.maidens), 0)::integer AS maidens,
            MAX(mbs.wickets) AS best_bowling_wickets,
            NULL::text AS best_bowling_figures,
            COUNT(*) FILTER (WHERE mbs.wickets >= 5)::integer AS five_wicket_innings,
            COALESCE(SUM(mbs.wides), 0)::integer AS wides,
            COALESCE(SUM(mbs.no_balls), 0)::integer AS no_balls,
            COALESCE(SUM(mfs.catches), 0)::integer AS catches,
            COALESCE(SUM(mfs.catches_wk), 0)::integer AS catches_wk,
            COALESCE(SUM(mfs.run_outs), 0)::integer AS run_outs,
            COALESCE(SUM(mfs.stumpings), 0)::integer AS stumpings
        FROM player_games pg
        LEFT JOIN manual_batting_innings mbi
            ON mbi.manual_game_id = pg.manual_game_id AND mbi.player_id = pg.player_id
        LEFT JOIN manual_bowling_spells mbs
            ON mbs.manual_game_id = pg.manual_game_id AND mbs.player_id = pg.player_id
        LEFT JOIN manual_fielding_stats mfs
            ON mfs.manual_game_id = pg.manual_game_id AND mfs.player_id = pg.player_id
        GROUP BY pg.player_id, pg.season_id, pg.grade_id
    ) mg_agg

    UNION ALL

    SELECT
        player_id, season_id,
        grade_id,
        'import'::text AS source,
        matches, batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        fours, sixes,
        NULL::integer AS batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk,
        GREATEST(catches - catches_wk, 0) AS catches_non_wk,
        run_outs,
        0 AS assisted_run_outs,
        run_outs AS unassisted_run_outs,
        stumpings,
        grade_label
    FROM import_effective_deltas""",
)

# The views have to stop referencing the column before it can be dropped, so
# the downgrade puts migration 266's own definitions back rather than dropping
# the views and leaving every reader broken.

# ── the per-innings views ────────────────────────────────────────────────────
# Reported live: a record board listing the same 270 twice and a career at
# 14,806 runs. `v_effective_games` and `v_effective_player_season_stats` were
# filtered; these six were not, so for a superseded season BOTH the synced
# innings and the imported innings were present — every century, every wicket
# and every catch counted from two sources.
#
# Each is taken from the migration that LAST defined it (075, 038, 147, 092,
# 147, 093), with the column list untouched and every column qualified — a
# `CREATE OR REPLACE VIEW` cannot change the output columns, and joining
# `games` makes a bare `id` ambiguous. The joins are all on primary keys, so
# they add no rows; LEFT JOIN throughout, so an innings whose game has no
# grade (a manual upload with no grade is ordinary) is KEPT rather than
# silently dropped, exactly as `v_effective_games` does it.
_SYNCED_SOURCE_JOIN = """
    LEFT JOIN games g ON g.id = {t}.game_id
    LEFT JOIN grades gr ON gr.id = g.grade_id
    LEFT JOIN seasons s ON s.id = gr.season_id
    WHERE s.stats_source IS DISTINCT FROM 'cricketstatz'
"""

_MANUAL_SOURCE_JOIN = """
    LEFT JOIN manual_games mg ON mg.id = {t}.manual_game_id
    LEFT JOIN seasons ms ON ms.id = mg.season_id
    WHERE mg.cricketstatz_import_id IS NULL
       OR ms.stats_source IS DISTINCT FROM 'playhq'
"""


def _per_innings(view: str, synced_table: str, manual_table: str,
                 synced_cols: str, manual_cols: str, *,
                 filtered: bool = True) -> str:
    """One per-innings view, with the source rule or without it.

    `filtered=False` is what DOWNGRADE emits — the same column list with the
    joins removed, so undoing 287 leaves nothing referencing `stats_source`
    and the column can actually be dropped.
    """
    synced_tail = _SYNCED_SOURCE_JOIN.format(t="t") if filtered else "\n"
    manual_tail = _MANUAL_SOURCE_JOIN.format(t="t") if filtered else "\n"
    return (
        f"CREATE OR REPLACE VIEW {view} AS\n"
        f"    SELECT {synced_cols}\n"
        f"    FROM {synced_table} t"
        + synced_tail
        + "    UNION ALL\n"
        f"    SELECT {manual_cols}\n"
        f"    FROM {manual_table} t"
        + manual_tail
    )




_PER_INNINGS_SPECS = (
    (
        "v_effective_batting_innings", "batting_innings", "manual_batting_innings",
        "t.id, t.game_id, t.player_id, t.innings_number, t.runs, t.balls, "
        "t.fours, t.sixes, t.strike_rate, t.dismissal_type, t.not_out, "
        "t.batting_position, t.did_not_bat, 'api'::text AS source, t.caught_behind",
        "t.id, t.manual_game_id AS game_id, t.player_id, t.innings_number, "
        "t.runs, t.balls, t.fours, t.sixes, t.strike_rate, t.dismissal_type, "
        "t.not_out, t.batting_position, t.did_not_bat, 'manual'::text AS source, "
        # Migration 291 gave manual_batting_innings its own caught_behind, and
        # this module re-issues the view LAST in the lifespan — selecting NULL
        # here would silently revert that feature on every boot.
        "t.caught_behind",
    ),
    (
        "v_effective_bowling_spells", "bowling_spells", "manual_bowling_spells",
        "t.id, t.game_id, t.player_id, t.innings_number, t.overs, t.maidens, "
        "t.runs, t.wickets, t.wides, t.no_balls, t.economy, 'api'::text AS source",
        "t.id, t.manual_game_id AS game_id, t.player_id, t.innings_number, "
        "t.overs, t.maidens, t.runs, t.wickets, t.wides, t.no_balls, t.economy, "
        "'manual'::text AS source",
    ),
    (
        "v_effective_fielding_stats", "fielding_stats", "manual_fielding_stats",
        "t.id, t.game_id, t.player_id, t.catches, t.catches_wk, t.run_outs, "
        "t.stumpings, 'api'::text AS source, t.player_name",
        "t.id, t.manual_game_id AS game_id, t.player_id, t.catches, "
        "t.catches_wk, t.run_outs, t.stumpings, 'manual'::text AS source, "
        "t.player_name",
    ),
    (
        "v_effective_fall_of_wickets", "fall_of_wickets", "manual_fall_of_wickets",
        "t.id, t.game_id, t.innings_number, t.wicket_number, t.score_at_fall, "
        "t.overs_at_fall, t.player_id, t.batter_name, 'api'::text AS source",
        "t.id, t.manual_game_id AS game_id, t.innings_number, t.wicket_number, "
        "t.score_at_fall, t.overs_at_fall, t.player_id, t.batter_name, "
        "'manual'::text AS source",
    ),
    (
        "v_effective_partnerships", "partnerships", "manual_partnerships",
        "t.id, t.game_id, t.innings_number, t.wicket_number, t.batter1_id, "
        "t.batter2_id, t.runs, t.balls, t.batter1_runs, t.batter2_runs, "
        "t.is_club_innings, 'api'::text AS source, t.batter1_name, t.batter2_name",
        "t.id, t.manual_game_id AS game_id, t.innings_number, t.wicket_number, "
        "t.batter1_id, t.batter2_id, t.runs, t.balls, t.batter1_runs, "
        "t.batter2_runs, t.is_club_innings, 'manual'::text AS source, "
        "t.batter1_name, t.batter2_name",
    ),
    (
        "v_effective_bowler_wickets", "bowler_wickets", "manual_bowler_wickets",
        "t.id, t.game_id, t.innings_number, t.bowler_id, t.fielder_id, "
        "t.batter_name, t.batter_position, t.batter_runs, t.batter_balls, "
        "t.dismissal_type, t.caught_behind, 'api'::text AS source",
        "t.id, t.manual_game_id AS game_id, t.innings_number, t.bowler_id, "
        "t.fielder_id, t.batter_name, t.batter_position, t.batter_runs, "
        "t.batter_balls, t.dismissal_type, t.caught_behind, 'manual'::text AS source",
    ),
)

PER_INNINGS_VIEWS: tuple[str, ...] = tuple(
    _per_innings(*spec) for spec in _PER_INNINGS_SPECS)
PER_INNINGS_ORIGINALS: tuple[str, ...] = tuple(
    _per_innings(*spec, filtered=False) for spec in _PER_INNINGS_SPECS)

STATEMENTS = STATEMENTS + PER_INNINGS_VIEWS

BACKFILL = """
    UPDATE seasons s SET stats_source = 'cricketstatz'
     WHERE s.stats_source IS NULL
       AND EXISTS (SELECT 1 FROM manual_games mg
                    WHERE mg.season_id = s.id
                      AND mg.cricketstatz_import_id IS NOT NULL)
"""

# SELF-HEALING, AND THAT IS THE POINT. Any season holding a CricketStatz match
# with no source recorded is one the club is counting twice, whatever put it in
# that state — an import that predates this rule, a run cut off before it could
# mark, a snapshot of the overlap that went stale mid-run. Guarded on NULL, so
# it never overrides a decision the club has made and a second run writes
# nothing.
STATEMENTS = STATEMENTS + (BACKFILL,)

DOWNGRADE: tuple[str, ...] = PER_INNINGS_ORIGINALS + (
    """CREATE OR REPLACE VIEW v_effective_games AS
    SELECT
        g.id, g.grade_id, g.played_at, g.home_team, g.away_team,
        g.home_club, g.away_club, g.opp_org_id, g.opp_club_name,
        g.result, g.winning_team, g.is_final,
        g.raw_payload, g.venue, g.match_format,
        'api'::text AS source,
        g.home_org_id, g.away_org_id,
        gr.season_id AS season_id,
        s.organisation_id AS organisation_id,
        g.status AS status
    FROM games g
    LEFT JOIN grades gr ON gr.id = g.grade_id
    LEFT JOIN seasons s ON s.id = gr.season_id
    UNION ALL
    SELECT
        mg.id, mg.grade_id, mg.played_at, mg.home_team, mg.away_team,
        NULL::text AS home_club,
        NULL::text AS away_club,
        NULL::text AS opp_org_id,
        mg.opposition AS opp_club_name,
        mg.result, mg.winning_team, mg.is_final,
        NULL::jsonb AS raw_payload,
        mg.venue, mg.match_format,
        'manual'::text AS source,
        NULL::uuid AS home_org_id,
        NULL::uuid AS away_org_id,
        mg.season_id AS season_id,
        mg.organisation_id AS organisation_id,
        NULL::text AS status
    FROM manual_games mg""",
    """CREATE OR REPLACE VIEW v_effective_player_season_stats AS
    SELECT
        player_id, season_id,
        NULL::uuid AS grade_id,
        'api'::text AS source,
        -- Abandoned and cancelled fixtures the player was named in but
        -- never actually played come off CA's own counter. See the
        -- migration docstring for why they are in it in the first place.
        GREATEST(matches - COALESCE(unplayed.unplayed_matches, 0), 0) AS matches,
        batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out, batting_average, batting_strike_rate,
        fours, sixes, batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        bowling_economy, bowling_average, bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk, catches_non_wk, run_outs,
        assisted_run_outs, unassisted_run_outs, stumpings,
        NULL::text AS grade_label
    FROM player_season_stats pss
    LEFT JOIN (
        -- One row per (player, season): how many abandoned or cancelled
        -- fixtures that player was NAMED in and recorded nothing at all in.
        -- Named-but-nothing-recorded is the whole test. A game abandoned
        -- after play started leaves real batting/bowling/fielding rows behind
        -- and the club counts it as played, so it must stay counted; a washout
        -- leaves a team sheet and nothing else, and that is the one CA counts
        -- and the club does not.
        SELECT
            ga.player_id AS unplayed_player_id,
            gr.season_id AS unplayed_season_id,
            COUNT(DISTINCT ga.game_id)::integer AS unplayed_matches
        FROM game_appearances ga
        JOIN games g ON g.id = ga.game_id
        JOIN grades gr ON gr.id = g.grade_id
        WHERE g.status IN ('ABANDONED', 'CANCELLED')
          AND NOT EXISTS (
              SELECT 1 FROM batting_innings bi
              WHERE bi.game_id = ga.game_id AND bi.player_id = ga.player_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM bowling_spells bs
              WHERE bs.game_id = ga.game_id AND bs.player_id = ga.player_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM fielding_stats fs
              WHERE fs.game_id = ga.game_id AND fs.player_id = ga.player_id
          )
        GROUP BY ga.player_id, gr.season_id
    ) unplayed
        ON unplayed.unplayed_player_id = pss.player_id
       AND unplayed.unplayed_season_id = pss.season_id
    -- Only surface a season-stats row when its season belongs to the same
    -- organisation as the player. Filters out cross-club rows that CA's shared
    -- participant GUID lets a second club's sync attach to a player owned by
    -- the first club. NULL-org players are kept (can't be scoped).
    WHERE EXISTS (
        SELECT 1
        FROM players pl
        JOIN seasons s ON s.id = pss.season_id
        WHERE pl.id = pss.player_id
          AND (pl.organisation_id IS NULL OR pl.organisation_id = s.organisation_id)
    )

    UNION ALL

    SELECT
        player_id, season_id, grade_id,
        'manual_aggregate'::text AS source,
        games_played AS matches,
        batting_innings,
        batting_runs AS runs,
        batting_not_outs AS not_outs,
        batting_balls AS balls_faced,
        batting_fifties AS fifties,
        batting_hundreds AS hundreds,
        batting_ducks AS ducks,
        batting_high_score AS high_score,
        batting_high_score_not_out AS is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        batting_fours AS fours,
        batting_sixes AS sixes,
        NULL::integer AS batting_minutes,
        bowling_innings,
        bowling_wickets AS wickets,
        bowling_overs AS overs,
        bowling_balls,
        bowling_runs AS runs_conceded,
        bowling_maidens AS maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        bowling_best_wickets AS best_bowling_wickets,
        bowling_best_figures AS best_bowling_figures,
        bowling_five_wicket_innings AS five_wicket_innings,
        bowling_wides AS wides,
        bowling_no_balls AS no_balls,
        fielding_catches AS catches,
        fielding_catches_wk AS catches_wk,
        GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
        fielding_run_outs AS run_outs,
        0 AS assisted_run_outs,
        fielding_run_outs AS unassisted_run_outs,
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
    FROM manual_season_adjustments

    UNION ALL

    -- Career-only adjustments (NULL season_id so they're invisible
    -- to season-keyed leaderboards but flow into career profile views).
    SELECT
        player_id,
        NULL::uuid AS season_id,
        NULL::uuid AS grade_id,
        'manual_career'::text AS source,
        games_played AS matches,
        batting_innings,
        batting_runs AS runs,
        batting_not_outs AS not_outs,
        batting_balls AS balls_faced,
        batting_fifties AS fifties,
        batting_hundreds AS hundreds,
        batting_ducks AS ducks,
        batting_high_score AS high_score,
        batting_high_score_not_out AS is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        batting_fours AS fours,
        batting_sixes AS sixes,
        NULL::integer AS batting_minutes,
        bowling_innings,
        bowling_wickets AS wickets,
        bowling_overs AS overs,
        bowling_balls,
        bowling_runs AS runs_conceded,
        bowling_maidens AS maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        bowling_best_wickets AS best_bowling_wickets,
        bowling_best_figures AS best_bowling_figures,
        bowling_five_wicket_innings AS five_wicket_innings,
        0 AS wides,
        0 AS no_balls,
        fielding_catches AS catches,
        fielding_catches_wk AS catches_wk,
        GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
        fielding_run_outs AS run_outs,
        0 AS assisted_run_outs,
        fielding_run_outs AS unassisted_run_outs,
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
    FROM manual_career_adjustments

    UNION ALL

    -- Manual games rolled up per (player, season, grade) — unchanged
    -- from migration 037.
    SELECT
        mg_agg.player_id,
        mg_agg.season_id,
        mg_agg.grade_id,
        'manual_game'::text AS source,
        mg_agg.matches,
        mg_agg.batting_innings,
        mg_agg.runs,
        mg_agg.not_outs,
        mg_agg.balls_faced,
        mg_agg.fifties,
        mg_agg.hundreds,
        mg_agg.ducks,
        mg_agg.high_score,
        mg_agg.is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        mg_agg.fours,
        mg_agg.sixes,
        NULL::integer AS batting_minutes,
        mg_agg.bowling_innings,
        mg_agg.wickets,
        mg_agg.overs,
        mg_agg.bowling_balls,
        mg_agg.runs_conceded,
        mg_agg.maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        mg_agg.best_bowling_wickets,
        mg_agg.best_bowling_figures,
        mg_agg.five_wicket_innings,
        mg_agg.wides,
        mg_agg.no_balls,
        mg_agg.catches,
        mg_agg.catches_wk,
        GREATEST(mg_agg.catches - mg_agg.catches_wk, 0) AS catches_non_wk,
        mg_agg.run_outs,
        0 AS assisted_run_outs,
        mg_agg.run_outs AS unassisted_run_outs,
        mg_agg.stumpings,
        NULL::text AS grade_label
    FROM (
        WITH player_games AS (
            SELECT mg.id AS manual_game_id, mg.season_id, mg.grade_id, mbi.player_id
            FROM manual_games mg JOIN manual_batting_innings mbi ON mbi.manual_game_id = mg.id
            UNION
            SELECT mg.id, mg.season_id, mg.grade_id, mbs.player_id
            FROM manual_games mg JOIN manual_bowling_spells mbs ON mbs.manual_game_id = mg.id
            UNION
            SELECT mg.id, mg.season_id, mg.grade_id, mfs.player_id
            FROM manual_games mg JOIN manual_fielding_stats mfs ON mfs.manual_game_id = mg.id
        )
        SELECT
            pg.player_id,
            pg.season_id,
            pg.grade_id,
            COUNT(DISTINCT pg.manual_game_id)::integer AS matches,
            COUNT(*) FILTER (WHERE mbi.id IS NOT NULL AND NOT mbi.did_not_bat)::integer AS batting_innings,
            COALESCE(SUM(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS runs,
            COUNT(*) FILTER (WHERE mbi.not_out)::integer AS not_outs,
            COALESCE(SUM(mbi.balls) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS balls_faced,
            COUNT(*) FILTER (WHERE mbi.runs >= 50 AND mbi.runs < 100)::integer AS fifties,
            COUNT(*) FILTER (WHERE mbi.runs >= 100)::integer AS hundreds,
            COUNT(*) FILTER (WHERE mbi.runs = 0 AND NOT mbi.not_out AND NOT mbi.did_not_bat)::integer AS ducks,
            MAX(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat) AS high_score,
            COALESCE(BOOL_OR(mbi.not_out) FILTER (
                WHERE mbi.runs = (
                    SELECT MAX(mbi2.runs)
                    FROM manual_batting_innings mbi2
                    JOIN manual_games mg2 ON mg2.id = mbi2.manual_game_id
                    WHERE mbi2.player_id = pg.player_id
                      AND mg2.season_id = pg.season_id
                      AND COALESCE(mg2.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                          = COALESCE(pg.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                      AND NOT mbi2.did_not_bat
                )
            ), false) AS is_hs_not_out,
            COALESCE(SUM(mbi.fours) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS fours,
            COALESCE(SUM(mbi.sixes) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS sixes,
            COUNT(*) FILTER (WHERE mbs.id IS NOT NULL)::integer AS bowling_innings,
            COALESCE(SUM(mbs.wickets), 0)::integer AS wickets,
            COALESCE(SUM(mbs.overs), 0)::numeric AS overs,
            COALESCE(SUM(FLOOR(mbs.overs)::integer * 6
                         + ((mbs.overs - FLOOR(mbs.overs)) * 10)::integer), 0)::integer AS bowling_balls,
            COALESCE(SUM(mbs.runs), 0)::integer AS runs_conceded,
            COALESCE(SUM(mbs.maidens), 0)::integer AS maidens,
            MAX(mbs.wickets) AS best_bowling_wickets,
            NULL::text AS best_bowling_figures,
            COUNT(*) FILTER (WHERE mbs.wickets >= 5)::integer AS five_wicket_innings,
            COALESCE(SUM(mbs.wides), 0)::integer AS wides,
            COALESCE(SUM(mbs.no_balls), 0)::integer AS no_balls,
            COALESCE(SUM(mfs.catches), 0)::integer AS catches,
            COALESCE(SUM(mfs.catches_wk), 0)::integer AS catches_wk,
            COALESCE(SUM(mfs.run_outs), 0)::integer AS run_outs,
            COALESCE(SUM(mfs.stumpings), 0)::integer AS stumpings
        FROM player_games pg
        LEFT JOIN manual_batting_innings mbi
            ON mbi.manual_game_id = pg.manual_game_id AND mbi.player_id = pg.player_id
        LEFT JOIN manual_bowling_spells mbs
            ON mbs.manual_game_id = pg.manual_game_id AND mbs.player_id = pg.player_id
        LEFT JOIN manual_fielding_stats mfs
            ON mfs.manual_game_id = pg.manual_game_id AND mfs.player_id = pg.player_id
        GROUP BY pg.player_id, pg.season_id, pg.grade_id
    ) mg_agg

    UNION ALL

    SELECT
        player_id, season_id,
        grade_id,
        'import'::text AS source,
        matches, batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        fours, sixes,
        NULL::integer AS batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk,
        GREATEST(catches - catches_wk, 0) AS catches_non_wk,
        run_outs,
        0 AS assisted_run_outs,
        run_outs AS unassisted_run_outs,
        stumpings,
        grade_label
    FROM import_effective_deltas""",
    "DROP INDEX IF EXISTS ix_seasons_stats_source",
    "ALTER TABLE seasons DROP COLUMN IF EXISTS stats_source",
)


# ── the schema must actually match the code ──────────────────────────────────
# Cost a whole afternoon to find, so it is checked from now on. `stats_source`
# was set on 73 of a club's seasons and `v_effective_games` carried no clause
# to act on it — the marker was live, the view was not, and every screen
# counted both sources with nothing anywhere reporting a problem. The
# statements above apply cleanly when run by hand, so the DDL was never wrong;
# the boot path simply had not run them, and alembic's own version table said
# otherwise. A migration recorded as applied is not evidence that its effect is
# in the database.
VERIFIED_VIEWS: tuple[tuple[str, str], ...] = (
    ("v_effective_games", "stats_source"),
    ("v_effective_player_season_stats", "stats_source"),
    ("v_effective_batting_innings", "stats_source"),
    ("v_effective_bowling_spells", "stats_source"),
    ("v_effective_fielding_stats", "stats_source"),
    ("v_effective_fall_of_wickets", "stats_source"),
    ("v_effective_partnerships", "stats_source"),
    ("v_effective_bowler_wickets", "stats_source"),
)


async def verify(conn) -> dict[str, bool]:
    """Which of the effective views actually carry their source clause.

    Read back out of `pg_get_viewdef`, so it reports what Postgres holds rather
    than what the code says it should. A view missing from the database at all
    reads as False rather than raising — a boot check must report, never be the
    thing that stops the app.
    """
    from sqlalchemy import text as _text

    found: dict[str, bool] = {}
    for view, needle in VERIFIED_VIEWS:
        try:
            body = (await conn.execute(_text(
                "SELECT pg_get_viewdef(to_regclass(:v))"), {"v": view})).scalar()
        except Exception:
            body = None
        found[view] = bool(body) and needle in body
    return found
