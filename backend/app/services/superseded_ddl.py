"""The one copy of the two-source DDL, run by alembic and the lifespan.

A club that syncs from Cricket Australia and also imports its CricketStatz
history holds many of the same matches twice, and every career total, average
and record board counted them twice (reported live: a batter reading 14,966
runs where CricketStatz has 10,444, and a career of 527 matches).

**THE TWO SOURCES COMPLEMENT EACH OTHER. IT IS AN AND, NEVER AN OR.** Each
holds matches the other does not — measured across five of one club's seasons,
Cricket Australia had 401 and CricketStatz 473, each with matches missing from
the other. So the rule is a UNION with the duplicates removed, decided **per
MATCH**, not a winner chosen per season:

* a CricketStatz match paired to a synced game is counted once, from whichever
  side actually holds the scorecard,
* a match only one source has is counted, from that source,
* nothing is deleted, the sync keeps running, and unpairing a match brings its
  imported copy straight back.

`manual_games.superseded_by_game_id` is the pair and
`manual_games.pair_prefers_import` says which half of it counts, both written
by `services/match_pairing.py` and applied **on read**, the way migration 060's
org scoping and 266's washout correction are. `pair_prefers_import` is FALSE
almost always — Cricket Australia is the live source and keeps its copy
current — and TRUE only where the synced game carries no scorecard of ours and
the imported one does, which is the "if PlayHQ is incomplete, use CricketStatz
to complete" case.

**THE EARLIER DESIGN CHOSE A WINNER PER SEASON AND THAT LOST MATCHES.**
`seasons.stats_source` hid one whole source for a season the two shared, so a
season where Cricket Australia held five matches CricketStatz lacked lost all
five. The column is left in place and **nothing reads it now** — the call
migration 267 made for `vote_settings` — because a second rule about which
source counts could only ever drift from the pairing.

**EVERY DEFINITION IS TAKEN FROM THE MIGRATION THAT LAST DEFINED IT, and that
is not a detail.** `CREATE OR REPLACE VIEW` cannot drop a column, so re-issuing
an OLDER definition of a view aborts — an early cut took `v_effective_games`
from 169, which predates the `status` column 266 added, and the migration
failed on every boot and took the API down with it. When changing a view here,
start from the newest definition and diff it.
"""
from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    # Left in place and read by nothing since the per-match pairing replaced
    # it; kept so a club's own earlier choice is not silently destroyed.
    "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS stats_source TEXT",
    # THE PAIR. A CricketStatz match that is the same match as a synced game.
    # ON DELETE SET NULL: removing a synced game unpairs its imported twin and
    # brings it back into the count rather than taking the match with it.
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS "
    "superseded_by_game_id UUID",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS "
    "pair_prefers_import BOOLEAN NOT NULL DEFAULT FALSE",
    # A HUMAN DELIBERATELY SET THIS PAIR, via an overwrite import that replaced
    # an incorrect Cricket Australia match with the club's own correct record.
    # `match_pairing.reconcile_org` leaves a locked row and its synced game
    # alone — the automatic matcher must never flip a person's decision back to
    # preferring the synced copy, which is the whole point of the lock. Set
    # together with superseded_by_game_id + pair_prefers_import = TRUE.
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS "
    "pairing_locked BOOLEAN NOT NULL DEFAULT FALSE",
    # A SEASON THE CLUB HAS RE-SOURCED FROM ITS OWN IMPORT, because Cricket
    # Australia's records for it are wrong. Set by an overwrite import told the
    # file holds the WHOLE season. Where TRUE, v_effective_player_season_stats
    # counts the import's own matches and steps CA's season summary aside, so
    # the profile and leaderboard TOTALS match the corrected scorecards rather
    # than PlayHQ's figure. Distinct from the retired `stats_source`: that was
    # set automatically per season and hid the losing source's unique matches;
    # this is human-set and only for a season the club has stated is complete.
    "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS "
    "import_authoritative BOOLEAN NOT NULL DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS ix_seasons_import_authoritative "
    "ON seasons (id) WHERE import_authoritative",
    """DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_manual_games_superseded_by_game') THEN
            ALTER TABLE manual_games
                ADD CONSTRAINT fk_manual_games_superseded_by_game
                FOREIGN KEY (superseded_by_game_id) REFERENCES games(id)
                ON DELETE SET NULL;
        END IF;
    END $$""",
    # ONE SYNCED GAME IS PAIRED TO AT MOST ONE IMPORTED MATCH. The matcher
    # assigns one-to-one; the index is what stops a bug making it many-to-one,
    # which would fan the views' LEFT JOIN out and multiply every figure.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_games_superseded_by_game "
    "ON manual_games (superseded_by_game_id) "
    "WHERE superseded_by_game_id IS NOT NULL",
    # Migration 291's column, guarded here too: this module re-issues
    # v_effective_batting_innings, which reads it, and a view cannot be
    # created against a column that is not there yet.
    "ALTER TABLE manual_batting_innings ADD COLUMN IF NOT EXISTS "
    "caught_behind BOOLEAN",
    # Migration 266's column, guarded for the same reason: this module owns
    # v_effective_games and v_effective_player_season_stats, both of which read
    # `games.status`, and it runs BEFORE the 266 mirror further down the boot.
    "ALTER TABLE games ADD COLUMN IF NOT EXISTS status TEXT",
    "CREATE INDEX IF NOT EXISTS ix_games_status_not_played "
    "ON games (status) WHERE status IN ('ABANDONED', 'CANCELLED')",
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
    -- A synced game steps aside ONLY for the imported twin of the same match,
    -- and only where that twin holds the scorecard this one is missing. Every
    -- other synced game counts, whatever the club has imported. Filtered on
    -- READ: nothing is deleted and unpairing brings it straight back.
    LEFT JOIN manual_games pm
        ON pm.superseded_by_game_id = g.id AND pm.pair_prefers_import
    WHERE pm.id IS NULL
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
    -- An imported match paired to a synced game is the SAME match, so it is
    -- counted once. Everything unpaired counts — including every game a club
    -- typed in by hand, which the matcher never touches.
    WHERE mg.superseded_by_game_id IS NULL OR mg.pair_prefers_import""",
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
          -- CRICKET AUSTRALIA'S OWN SEASON TOTALS ARE ALWAYS COUNTED, and
          -- that is what makes the union work at this level. They cover CA's
          -- matches and nothing else; the 'manual_game' branch below counts
          -- only the imported matches CA does NOT have, since a paired one is
          -- filtered out there. Neither half can reach the other's matches,
          -- so the season is counted once.
          --
          -- THE EXCEPTION IS A SEASON THE CLUB HAS RE-SOURCED. Where a club has
          -- declared its own import authoritative for a season (PlayHQ was
          -- wrong for it), CA's summary is stepped aside — but NOT the
          -- matches behind it. A season total has no per-match granularity,
          -- so the only way to replace SOME of a season's matches is to count
          -- the whole season from scorecards: the import's own rollup below
          -- carries every match the file held, and the 'api_scorecard' branch
          -- carries every synced game the file did NOT hold, from CA's own
          -- per-innings rows. The two are disjoint by construction (a synced
          -- game with a preferred imported twin is in the second, never the
          -- first), so the season is the union of both sources counted once.
          -- Everywhere else this is FALSE and nothing changes.
          AND NOT s.import_authoritative
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
        -- A PAIRED IMPORTED MATCH IS NEVER COUNTED HERE, `pair_prefers_import`
        -- OR NOT, AND THAT IS THE ONE PLACE THIS RULE DIFFERS FROM THE VIEWS
        -- BESIDE IT. Those are per-match, so a paired synced game can step
        -- aside and let the imported copy answer. `player_season_stats` is a
        -- SEASON TOTAL with no per-match granularity: there is no row to drop,
        -- so Cricket Australia's own figure carries that match whatever we do.
        -- Counting the imported copy as well is the same match twice —
        -- reported off a live profile as a career reading 15,333 runs and 28
        -- hundreds beside an innings list of 9,914 and 16, every shared season
        -- exactly double the innings beneath it.
        --
        -- So at this level the rule is Cricket Australia's totals PLUS the
        -- imported matches CA does not have at all. Preferring the imported
        -- copy is a decision about which scorecard to SHOW, and it stays
        -- per-innings, where there is a row to drop.
        -- `counts_here` is the one rule for whether a manual game feeds the
        -- season aggregate: an UNPAIRED match always does; a paired (superseded)
        -- match does ONLY where it is the PREFERRED half of its pair AND its
        -- season is one the club has re-sourced, where CA's own summary is
        -- stepped aside above and the synced twin is left out of the
        -- 'api_scorecard' branch beside this one. Everywhere else a paired
        -- match stays out, so the season is counted once — per MATCH, from
        -- whichever side the pair prefers, never per season.
        -- EVERY CTE HERE IS `NOT MATERIALIZED`, and that is what makes a
        -- single player's read of this view cheap. A CTE referenced more
        -- than once is materialised by default, and a materialised CTE is a
        -- wall the outer `WHERE player_id = X` cannot pass through: the whole
        -- club's imported history was being rolled up for every profile
        -- load, then thrown away. Inlined, the planner pushes the player's id
        -- into each table scan. The `api_scorecard` branch beside this one
        -- had the same wall, and it is what made a player page take seconds.
        WITH counts_here AS NOT MATERIALIZED (
            SELECT mg.id AS manual_game_id, mg.season_id, mg.grade_id
            FROM manual_games mg
            WHERE mg.superseded_by_game_id IS NULL
               OR (mg.pair_prefers_import
                   AND EXISTS (SELECT 1 FROM seasons s
                               WHERE s.id = mg.season_id AND s.import_authoritative))
        ),
        player_games AS NOT MATERIALIZED (
            SELECT ch.manual_game_id, ch.season_id, ch.grade_id, mbi.player_id
            FROM counts_here ch JOIN manual_batting_innings mbi ON mbi.manual_game_id = ch.manual_game_id
            UNION
            SELECT ch.manual_game_id, ch.season_id, ch.grade_id, mbs.player_id
            FROM counts_here ch JOIN manual_bowling_spells mbs ON mbs.manual_game_id = ch.manual_game_id
            UNION
            SELECT ch.manual_game_id, ch.season_id, ch.grade_id, mfs.player_id
            FROM counts_here ch JOIN manual_fielding_stats mfs ON mfs.manual_game_id = ch.manual_game_id
        ),
        -- EACH TABLE IS AGGREGATED ON ITS OWN BEFORE THE THREE ARE JOINED.
        -- Migration 037's shape LEFT JOINed batting, bowling and fielding
        -- side by side on one (player, game) key, which multiplies a player
        -- who batted twice and bowled once in a two-day match into two rows
        -- and doubles the bowling and fielding sums — the same trap the
        -- `api_scorecard` branch was written to avoid. Reported off StatLab
        -- as innings running far ahead of matches played.
        keys AS NOT MATERIALIZED (
            SELECT player_id, season_id, grade_id,
                   COUNT(DISTINCT manual_game_id)::integer AS matches
            FROM player_games GROUP BY player_id, season_id, grade_id
        ),
        bat AS NOT MATERIALIZED (
            SELECT pg.player_id, pg.season_id, pg.grade_id,
                COUNT(*) FILTER (WHERE NOT mbi.did_not_bat)::integer AS batting_innings,
                COALESCE(SUM(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS runs,
                COUNT(*) FILTER (WHERE mbi.not_out)::integer AS not_outs,
                COALESCE(SUM(mbi.balls) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS balls_faced,
                COUNT(*) FILTER (WHERE mbi.runs >= 50 AND mbi.runs < 100)::integer AS fifties,
                COUNT(*) FILTER (WHERE mbi.runs >= 100)::integer AS hundreds,
                COUNT(*) FILTER (WHERE mbi.runs = 0 AND NOT mbi.not_out AND NOT mbi.did_not_bat)::integer AS ducks,
                MAX(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat) AS high_score,
                -- The not-out flag of the highest score; a tie at the top
                -- reads not out if any of them was.
                COALESCE((ARRAY_AGG(mbi.not_out
                                    ORDER BY mbi.runs DESC NULLS LAST, mbi.not_out DESC)
                          FILTER (WHERE NOT mbi.did_not_bat))[1],
                         false) AS is_hs_not_out,
                COALESCE(SUM(mbi.fours) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS fours,
                COALESCE(SUM(mbi.sixes) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS sixes
            FROM player_games pg
            JOIN manual_batting_innings mbi
                ON mbi.manual_game_id = pg.manual_game_id AND mbi.player_id = pg.player_id
            GROUP BY pg.player_id, pg.season_id, pg.grade_id
        ),
        bowl AS NOT MATERIALIZED (
            SELECT pg.player_id, pg.season_id, pg.grade_id,
                COUNT(*)::integer AS bowling_innings,
                COALESCE(SUM(mbs.wickets), 0)::integer AS wickets,
                COALESCE(SUM(mbs.overs), 0)::numeric AS overs,
                COALESCE(SUM(FLOOR(mbs.overs)::integer * 6
                             + ((mbs.overs - FLOOR(mbs.overs)) * 10)::integer), 0)::integer AS bowling_balls,
                COALESCE(SUM(mbs.runs), 0)::integer AS runs_conceded,
                COALESCE(SUM(mbs.maidens), 0)::integer AS maidens,
                MAX(mbs.wickets) AS best_bowling_wickets,
                COUNT(*) FILTER (WHERE mbs.wickets >= 5)::integer AS five_wicket_innings,
                COALESCE(SUM(mbs.wides), 0)::integer AS wides,
                COALESCE(SUM(mbs.no_balls), 0)::integer AS no_balls
            FROM player_games pg
            JOIN manual_bowling_spells mbs
                ON mbs.manual_game_id = pg.manual_game_id AND mbs.player_id = pg.player_id
            GROUP BY pg.player_id, pg.season_id, pg.grade_id
        ),
        field AS NOT MATERIALIZED (
            SELECT pg.player_id, pg.season_id, pg.grade_id,
                COALESCE(SUM(mfs.catches), 0)::integer AS catches,
                COALESCE(SUM(mfs.catches_wk), 0)::integer AS catches_wk,
                COALESCE(SUM(mfs.run_outs), 0)::integer AS run_outs,
                COALESCE(SUM(mfs.stumpings), 0)::integer AS stumpings
            FROM player_games pg
            JOIN manual_fielding_stats mfs
                ON mfs.manual_game_id = pg.manual_game_id AND mfs.player_id = pg.player_id
            GROUP BY pg.player_id, pg.season_id, pg.grade_id
        )
        SELECT
            k.player_id, k.season_id, k.grade_id, k.matches,
            COALESCE(b.batting_innings, 0) AS batting_innings,
            COALESCE(b.runs, 0) AS runs,
            COALESCE(b.not_outs, 0) AS not_outs,
            COALESCE(b.balls_faced, 0) AS balls_faced,
            COALESCE(b.fifties, 0) AS fifties,
            COALESCE(b.hundreds, 0) AS hundreds,
            COALESCE(b.ducks, 0) AS ducks,
            b.high_score,
            COALESCE(b.is_hs_not_out, false) AS is_hs_not_out,
            COALESCE(b.fours, 0) AS fours,
            COALESCE(b.sixes, 0) AS sixes,
            COALESCE(w.bowling_innings, 0) AS bowling_innings,
            COALESCE(w.wickets, 0) AS wickets,
            COALESCE(w.overs, 0)::numeric AS overs,
            COALESCE(w.bowling_balls, 0) AS bowling_balls,
            COALESCE(w.runs_conceded, 0) AS runs_conceded,
            COALESCE(w.maidens, 0) AS maidens,
            w.best_bowling_wickets,
            NULL::text AS best_bowling_figures,
            COALESCE(w.five_wicket_innings, 0) AS five_wicket_innings,
            COALESCE(w.wides, 0) AS wides,
            COALESCE(w.no_balls, 0) AS no_balls,
            COALESCE(f.catches, 0) AS catches,
            COALESCE(f.catches_wk, 0) AS catches_wk,
            COALESCE(f.run_outs, 0) AS run_outs,
            COALESCE(f.stumpings, 0) AS stumpings
        FROM keys k
        LEFT JOIN bat b ON b.player_id = k.player_id AND b.season_id = k.season_id
                       AND b.grade_id IS NOT DISTINCT FROM k.grade_id
        LEFT JOIN bowl w ON w.player_id = k.player_id AND w.season_id = k.season_id
                        AND w.grade_id IS NOT DISTINCT FROM k.grade_id
        LEFT JOIN field f ON f.player_id = k.player_id AND f.season_id = k.season_id
                         AND f.grade_id IS NOT DISTINCT FROM k.grade_id
    ) mg_agg

    UNION ALL

    -- THE SYNCED GAMES A RE-SOURCED SEASON STILL COUNTS, from their own
    -- scorecards. A club's import rarely holds EVERY match Cricket Australia
    -- does — a junior grade the old program never tracked, a fixture the
    -- other club synced first — and stepping CA's whole season summary aside
    -- used to drop every one of those from the totals while the per-innings
    -- views (which every filtered read uses) kept them. That is how a
    -- player's "Men's" figure came to read HIGHER than their "All". So a
    -- synced game in a re-sourced season with no preferred imported twin is
    -- rolled up here, per (player, season, grade), from batting_innings /
    -- bowling_spells / fielding_stats / game_appearances — the same four
    -- sources `_scoped_games_played` unions — org-scoped through `players`
    -- so a shared fixture's opposition rows never count as ours.
    --
    -- Two ways a game belongs to a re-sourced season: it sits in one of the
    -- club's own grades, or it is a shared fixture the OTHER club synced
    -- first (filed under THEIR season, ours by `home_org_id`/`away_org_id`
    -- — the rule club_game_sql already keeps). The second is keyed onto our
    -- own season for the same real season, CA season guid first, year second,
    -- and onto exactly one of ours, so a year with two season rows cannot
    -- count the game twice.
    --
    -- Empty for every club that has re-sourced nothing: the partial index on
    -- `seasons.import_authoritative` is the first thing each arm reads.
    SELECT
        ca_agg.player_id,
        ca_agg.season_id,
        ca_agg.grade_id,
        'api_scorecard'::text AS source,
        ca_agg.matches,
        ca_agg.batting_innings,
        ca_agg.runs,
        ca_agg.not_outs,
        ca_agg.balls_faced,
        ca_agg.fifties,
        ca_agg.hundreds,
        ca_agg.ducks,
        ca_agg.high_score,
        ca_agg.is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        ca_agg.fours,
        ca_agg.sixes,
        NULL::integer AS batting_minutes,
        ca_agg.bowling_innings,
        ca_agg.wickets,
        ca_agg.overs,
        ca_agg.bowling_balls,
        ca_agg.runs_conceded,
        ca_agg.maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        ca_agg.best_bowling_wickets,
        NULL::text AS best_bowling_figures,
        ca_agg.five_wicket_innings,
        ca_agg.wides,
        ca_agg.no_balls,
        ca_agg.catches,
        ca_agg.catches_wk,
        GREATEST(ca_agg.catches - ca_agg.catches_wk, 0) AS catches_non_wk,
        ca_agg.run_outs,
        0 AS assisted_run_outs,
        ca_agg.run_outs AS unassisted_run_outs,
        ca_agg.stumpings,
        NULL::text AS grade_label
    FROM (
        -- `auth_games` IS THE ONE CTE HERE THAT STAYS MATERIALISED. It does
        -- not depend on the player, so there is nothing to push into it, and
        -- inlined it was evaluated once per reference: four arms of
        -- `player_games` times four readers of `ours` is sixteen scans per
        -- view read, which took a player page from slow to 45 seconds
        -- (measured live). Materialised it runs once per read and is small —
        -- only the games of seasons a club has re-sourced.
        --
        -- The second arm is driven FROM those seasons, never from every game
        -- on the platform: for each re-sourced season, the fixtures where
        -- that club is one of the two sides (both columns indexed, migration
        -- 167) but the game sits under the OTHER club's season row. DISTINCT
        -- ON the game keeps the "exactly one of ours" rule — a year with two
        -- season rows cannot count a game twice — CA season guid first.
        WITH auth_games AS MATERIALIZED (
            SELECT g.id AS game_id, s.id AS season_id, g.grade_id,
                   s.organisation_id, g.status
            FROM seasons s
            JOIN grades gr ON gr.season_id = s.id
            JOIN games g ON g.grade_id = gr.id
            WHERE s.import_authoritative
              AND NOT EXISTS (SELECT 1 FROM manual_games pm
                               WHERE pm.superseded_by_game_id = g.id
                                 AND pm.pair_prefers_import)
            UNION
            SELECT game_id, season_id, grade_id, organisation_id, status
            FROM (
                SELECT DISTINCT ON (g.id)
                       g.id AS game_id, s.id AS season_id, g.grade_id,
                       s.organisation_id, g.status
                FROM seasons s
                JOIN games g ON (g.home_org_id = s.organisation_id
                                 OR g.away_org_id = s.organisation_id)
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons theirs ON theirs.id = gr.season_id
                                   AND theirs.organisation_id <> s.organisation_id
                WHERE s.import_authoritative
                  AND ((s.grassroots_id IS NOT NULL
                        AND s.grassroots_id = theirs.grassroots_id)
                       OR (s.year IS NOT NULL AND s.year = theirs.year))
                  AND NOT EXISTS (SELECT 1 FROM manual_games pm
                                   WHERE pm.superseded_by_game_id = g.id
                                     AND pm.pair_prefers_import)
                ORDER BY g.id,
                         (s.grassroots_id IS NOT NULL
                          AND s.grassroots_id = theirs.grassroots_id) DESC,
                         s.id
            ) shared
        ),
        -- `NOT MATERIALIZED` on every CTE from here down, for the reason the
        -- 'manual_game' branch above gives: a materialised CTE stops a single
        -- player's id reaching these scans, and every profile load then
        -- rolled up every re-sourced season on the platform.
        -- Every (player, game) that is a match played, from the four sources.
        -- A player named in the side who recorded nothing counts a match
        -- unless the fixture never went ahead — migration 266's rule.
        player_games AS NOT MATERIALIZED (
            SELECT ag.game_id, ag.season_id, ag.grade_id, ag.organisation_id, bi.player_id
            FROM auth_games ag JOIN batting_innings bi ON bi.game_id = ag.game_id
            UNION
            SELECT ag.game_id, ag.season_id, ag.grade_id, ag.organisation_id, bs.player_id
            FROM auth_games ag JOIN bowling_spells bs ON bs.game_id = ag.game_id
            UNION
            SELECT ag.game_id, ag.season_id, ag.grade_id, ag.organisation_id, fs.player_id
            FROM auth_games ag JOIN fielding_stats fs ON fs.game_id = ag.game_id
            WHERE fs.player_id IS NOT NULL
            UNION
            SELECT ag.game_id, ag.season_id, ag.grade_id, ag.organisation_id, ga.player_id
            FROM auth_games ag JOIN game_appearances ga ON ga.game_id = ag.game_id
            WHERE COALESCE(ag.status, '') NOT IN ('ABANDONED', 'CANCELLED')
        ),
        -- OUR OWN PLAYERS ONLY. A shared fixture carries both clubs' rows on
        -- one game; a NULL-org player is kept, as the api branch keeps it.
        ours AS NOT MATERIALIZED (
            SELECT DISTINCT pg.game_id, pg.season_id, pg.grade_id, pg.player_id
            FROM player_games pg
            JOIN players pl ON pl.id = pg.player_id
             AND (pl.organisation_id IS NULL OR pl.organisation_id = pg.organisation_id)
        ),
        -- Each table is aggregated ON ITS OWN before the three are joined.
        -- Joining the per-innings rows side by side multiplies a player who
        -- batted twice and bowled twice in one match into four rows and
        -- doubles every sum.
        keys AS NOT MATERIALIZED (
            SELECT player_id, season_id, grade_id,
                   COUNT(DISTINCT game_id)::integer AS matches
            FROM ours GROUP BY player_id, season_id, grade_id
        ),
        bat AS NOT MATERIALIZED (
            SELECT o.player_id, o.season_id, o.grade_id,
                COUNT(*) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false))::integer AS batting_innings,
                COALESCE(SUM(bi.runs) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)), 0)::integer AS runs,
                COUNT(*) FILTER (WHERE COALESCE(bi.not_out, false)
                                   AND NOT COALESCE(bi.did_not_bat, false))::integer AS not_outs,
                COALESCE(SUM(bi.balls) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)), 0)::integer AS balls_faced,
                COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100
                                   AND NOT COALESCE(bi.did_not_bat, false))::integer AS fifties,
                COUNT(*) FILTER (WHERE bi.runs >= 100
                                   AND NOT COALESCE(bi.did_not_bat, false))::integer AS hundreds,
                COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT COALESCE(bi.not_out, false)
                                   AND NOT COALESCE(bi.did_not_bat, false))::integer AS ducks,
                MAX(bi.runs) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)) AS high_score,
                -- The not-out flag of the highest score; a tie at the top
                -- reads not out if any of them was, as the manual rollup does.
                COALESCE((ARRAY_AGG(COALESCE(bi.not_out, false)
                                    ORDER BY bi.runs DESC NULLS LAST,
                                             COALESCE(bi.not_out, false) DESC)
                          FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)))[1],
                         false) AS is_hs_not_out,
                COALESCE(SUM(bi.fours) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)), 0)::integer AS fours,
                COALESCE(SUM(bi.sixes) FILTER (WHERE NOT COALESCE(bi.did_not_bat, false)), 0)::integer AS sixes
            FROM ours o
            JOIN batting_innings bi ON bi.game_id = o.game_id AND bi.player_id = o.player_id
            GROUP BY o.player_id, o.season_id, o.grade_id
        ),
        bowl AS NOT MATERIALIZED (
            SELECT o.player_id, o.season_id, o.grade_id,
                COUNT(*)::integer AS bowling_innings,
                COALESCE(SUM(bs.wickets), 0)::integer AS wickets,
                COALESCE(SUM(bs.overs), 0)::numeric AS overs,
                COALESCE(SUM(FLOOR(bs.overs)::integer * 6
                             + ((bs.overs - FLOOR(bs.overs)) * 10)::integer), 0)::integer AS bowling_balls,
                COALESCE(SUM(bs.runs), 0)::integer AS runs_conceded,
                COALESCE(SUM(bs.maidens), 0)::integer AS maidens,
                MAX(bs.wickets) AS best_bowling_wickets,
                COUNT(*) FILTER (WHERE bs.wickets >= 5)::integer AS five_wicket_innings,
                COALESCE(SUM(bs.wides), 0)::integer AS wides,
                COALESCE(SUM(bs.no_balls), 0)::integer AS no_balls
            FROM ours o
            JOIN bowling_spells bs ON bs.game_id = o.game_id AND bs.player_id = o.player_id
            GROUP BY o.player_id, o.season_id, o.grade_id
        ),
        field AS NOT MATERIALIZED (
            SELECT o.player_id, o.season_id, o.grade_id,
                COALESCE(SUM(fs.catches), 0)::integer AS catches,
                COALESCE(SUM(fs.catches_wk), 0)::integer AS catches_wk,
                COALESCE(SUM(fs.run_outs), 0)::integer AS run_outs,
                COALESCE(SUM(fs.stumpings), 0)::integer AS stumpings
            FROM ours o
            JOIN fielding_stats fs ON fs.game_id = o.game_id AND fs.player_id = o.player_id
            GROUP BY o.player_id, o.season_id, o.grade_id
        )
        SELECT
            k.player_id, k.season_id, k.grade_id, k.matches,
            COALESCE(b.batting_innings, 0) AS batting_innings,
            COALESCE(b.runs, 0) AS runs,
            COALESCE(b.not_outs, 0) AS not_outs,
            COALESCE(b.balls_faced, 0) AS balls_faced,
            COALESCE(b.fifties, 0) AS fifties,
            COALESCE(b.hundreds, 0) AS hundreds,
            COALESCE(b.ducks, 0) AS ducks,
            b.high_score,
            COALESCE(b.is_hs_not_out, false) AS is_hs_not_out,
            COALESCE(b.fours, 0) AS fours,
            COALESCE(b.sixes, 0) AS sixes,
            COALESCE(w.bowling_innings, 0) AS bowling_innings,
            COALESCE(w.wickets, 0) AS wickets,
            COALESCE(w.overs, 0)::numeric AS overs,
            COALESCE(w.bowling_balls, 0) AS bowling_balls,
            COALESCE(w.runs_conceded, 0) AS runs_conceded,
            COALESCE(w.maidens, 0) AS maidens,
            w.best_bowling_wickets,
            COALESCE(w.five_wicket_innings, 0) AS five_wicket_innings,
            COALESCE(w.wides, 0) AS wides,
            COALESCE(w.no_balls, 0) AS no_balls,
            COALESCE(f.catches, 0) AS catches,
            COALESCE(f.catches_wk, 0) AS catches_wk,
            COALESCE(f.run_outs, 0) AS run_outs,
            COALESCE(f.stumpings, 0) AS stumpings
        FROM keys k
        LEFT JOIN bat b ON b.player_id = k.player_id AND b.season_id = k.season_id
                       AND b.grade_id IS NOT DISTINCT FROM k.grade_id
        LEFT JOIN bowl w ON w.player_id = k.player_id AND w.season_id = k.season_id
                        AND w.grade_id IS NOT DISTINCT FROM k.grade_id
        LEFT JOIN field f ON f.player_id = k.player_id AND f.season_id = k.season_id
                         AND f.grade_id IS NOT DISTINCT FROM k.grade_id
    ) ca_agg

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
    LEFT JOIN manual_games pm
        ON pm.superseded_by_game_id = {t}.game_id AND pm.pair_prefers_import
    WHERE pm.id IS NULL
"""

_MANUAL_SOURCE_JOIN = """
    LEFT JOIN manual_games mg ON mg.id = {t}.manual_game_id
    WHERE mg.superseded_by_game_id IS NULL OR mg.pair_prefers_import
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

# NOTHING MARKS A SEASON ANY MORE. The earlier rule set
# `seasons.stats_source = 'cricketstatz'` for every season holding an imported
# match, which hid that season's whole synced side — and with it every match
# Cricket Australia had and CricketStatz did not. The pairing replaces it, so
# there is no backfill here and no statement writing that column. Rows already
# carrying a value are left exactly as they are: nothing reads them, and
# destroying a club's own earlier choice to tidy up would be its own bug.

_DROP_PAIR: tuple[str, ...] = (
    "DROP INDEX IF EXISTS uq_manual_games_superseded_by_game",
    "ALTER TABLE manual_games DROP CONSTRAINT IF EXISTS "
    "fk_manual_games_superseded_by_game",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS pair_prefers_import",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS superseded_by_game_id",
    # The overwrite-import lock and per-season re-source flag. The DOWNGRADE
    # views above are the pre-pairing ones, which reference neither, so both
    # drop cleanly here.
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS pairing_locked",
    "DROP INDEX IF EXISTS ix_seasons_import_authoritative",
    "ALTER TABLE seasons DROP COLUMN IF EXISTS import_authoritative",
)

# The views have to stop reading the pair columns BEFORE they can be dropped,
# so the originals go back first and the drops come last. Found by running it:
# dropping first fails while six views still reference them.
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
) + _DROP_PAIR


# ── the schema must actually match the code ──────────────────────────────────
# Cost a whole afternoon to find, so it is checked from now on. `stats_source`
# was set on 73 of a club's seasons and `v_effective_games` carried no clause
# to act on it — the marker was live, the view was not, and every screen
# counted both sources with nothing anywhere reporting a problem. The
# statements above apply cleanly when run by hand, so the DDL was never wrong;
# the boot path simply had not run them, and alembic's own version table said
# otherwise. A migration recorded as applied is not evidence that its effect is
# in the database.
# What each view's body must contain for the pairing to be in force. A
# migration recorded as applied is not evidence its effect is there — a live
# database once carried `stats_source` on 73 seasons with `v_effective_games`
# holding no clause to act on, and nothing anywhere reported it.
VERIFIED_VIEWS: tuple[tuple[str, str], ...] = (
    ("v_effective_games", "superseded_by_game_id"),
    ("v_effective_player_season_stats", "superseded_by_game_id"),
    ("v_effective_batting_innings", "superseded_by_game_id"),
    ("v_effective_bowling_spells", "superseded_by_game_id"),
    ("v_effective_fielding_stats", "superseded_by_game_id"),
    ("v_effective_fall_of_wickets", "superseded_by_game_id"),
    ("v_effective_partnerships", "superseded_by_game_id"),
    ("v_effective_bowler_wickets", "superseded_by_game_id"),
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
