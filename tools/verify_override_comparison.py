"""Checks `ops/diagnostics/override_comparison.sql` against a real Postgres.

The script compares the imported version of a match with the synced one it
replaced. Each check builds the tables the script reads (only the columns it
uses, named as in `backend/app/models/db.py`), loads matches whose differences
are known, runs the shipped script with psql, and reads the CSVs it writes.

Every case is paired with its opposite: an agreeing pair must read AGREE, and a
pair that differs in one thing must name exactly that thing. A script that
flagged everything, or nothing, would fail one half.

    python3 tools/verify_override_comparison.py

Needs a local Postgres the current user can create databases in (psql on PATH).
"""
from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
import os
SQL = Path(os.environ["OV_SQL"]) if os.environ.get("OV_SQL") else HERE.parent / "ops" / "diagnostics" / "override_comparison.sql"
DB = "ov_cmp_test"
PASS = FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}\n        got  {got!r}\n        want {want!r}")


def psql(db, sql=None, file=None, cwd=None, vars_=()):
    cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db]
    for k, v in vars_:
        cmd += ["-v", f"{k}={v}"]
    cmd += ["-f", str(file)] if file else ["-c", sql]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


DDL = """
CREATE TABLE organisations (id uuid PRIMARY KEY, slug text, name text);
CREATE TABLE seasons (id uuid PRIMARY KEY, organisation_id uuid, name text);
CREATE TABLE grades (id uuid PRIMARY KEY, season_id uuid, name text);
CREATE TABLE players (id uuid PRIMARY KEY, name text, display_name_override text, organisation_id uuid);
CREATE TABLE games (id uuid PRIMARY KEY, grade_id uuid, played_at date, home_team text, away_team text,
  home_org_id uuid, away_org_id uuid, opp_club_name text, result text, winning_team text);
CREATE TABLE batting_innings (id serial PRIMARY KEY, game_id uuid, player_id uuid, innings_number int,
  runs int, balls int, fours int, sixes int, dismissal_type text, not_out boolean, batting_position int,
  did_not_bat boolean DEFAULT false);
CREATE TABLE bowling_spells (id serial PRIMARY KEY, game_id uuid, player_id uuid, innings_number int,
  overs numeric, maidens int, runs int, wickets int);
CREATE TABLE fielding_stats (id serial PRIMARY KEY, game_id uuid, player_id uuid);
CREATE TABLE bowler_wickets (id serial PRIMARY KEY, game_id uuid);
CREATE TABLE fall_of_wickets (id serial PRIMARY KEY, game_id uuid);
CREATE TABLE partnerships (id serial PRIMARY KEY, game_id uuid);
CREATE TABLE game_appearances (game_id uuid, player_id uuid);
CREATE TABLE manual_games (id uuid PRIMARY KEY, organisation_id uuid, season_id uuid, grade_id uuid,
  played_at date, opposition text, result text, superseded_by_game_id uuid,
  pair_prefers_import boolean NOT NULL DEFAULT false, pairing_locked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE manual_batting_innings (id serial PRIMARY KEY, manual_game_id uuid, player_id uuid,
  innings_number int, runs int NOT NULL DEFAULT 0, balls int, did_not_bat boolean NOT NULL DEFAULT false);
CREATE TABLE manual_bowling_spells (id serial PRIMARY KEY, manual_game_id uuid, player_id uuid,
  innings_number int, runs int NOT NULL DEFAULT 0, wickets int NOT NULL DEFAULT 0);
CREATE TABLE manual_fielding_stats (id serial PRIMARY KEY, manual_game_id uuid, player_id uuid);
CREATE TABLE manual_fall_of_wickets (id serial PRIMARY KEY, manual_game_id uuid);
CREATE TABLE manual_partnerships (id serial PRIMARY KEY, manual_game_id uuid);
CREATE TABLE manual_bowler_wickets (id serial PRIMARY KEY, manual_game_id uuid);
"""


def uid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


A, B = uid(1), uid(2)                       # our club, an opposition club
SEASON, GRADE = uid(10), uid(11)
OURS = [uid(100 + i) for i in range(1, 6)]  # five of our players
THEIRS = [uid(200 + i) for i in range(1, 4)]


class Fx:
    """Builds the rows for one synced/imported pair."""
    n = 1000

    def __init__(self, sql):
        self.sql = sql

    def nid(self):
        Fx.n += 1
        return uid(Fx.n)

    def synced(self, date, opp, winner_ours, ours_runs, *, balls=True, theirs=True, wkts=(3, 2),
               detail=True, ours_batters=True):
        """A synced game: we are the home side. Returns its id."""
        g = self.nid()
        win = "'Payneham'" if winner_ours is True else ("'" + opp + "'" if winner_ours is False else "NULL")
        res = "'WIN'" if winner_ours is True else ("'LOSS'" if winner_ours is False else "'DRAW'")
        self.sql.append(
            f"INSERT INTO games VALUES ('{g}','{GRADE}','{date}','Payneham','{opp}','{A}','{B}','{opp}',{res},{win});")
        if ours_batters:
            for i, r in enumerate(ours_runs):
                self.sql.append(
                    f"INSERT INTO batting_innings (game_id,player_id,innings_number,runs,balls,fours,sixes) "
                    f"VALUES ('{g}','{OURS[i]}',1,{r},{(r * 2 + 5) if balls else 'NULL'},1,0);")
        if theirs:
            self.sql.append(f"INSERT INTO batting_innings (game_id,player_id,innings_number,runs,balls) "
                            f"VALUES ('{g}','{THEIRS[0]}',2,20,30),('{g}','{THEIRS[1]}',2,5,9);")
            self.sql.append(f"INSERT INTO bowling_spells (game_id,player_id,innings_number,runs,wickets) "
                            f"VALUES ('{g}','{THEIRS[2]}',1,40,2);")
        for i, w in enumerate(wkts):
            self.sql.append(f"INSERT INTO bowling_spells (game_id,player_id,innings_number,runs,wickets) "
                            f"VALUES ('{g}','{OURS[i]}',2,30,{w});")
        if detail:
            self.sql.append(f"INSERT INTO bowler_wickets (game_id) VALUES ('{g}'),('{g}');")
            self.sql.append(f"INSERT INTO fall_of_wickets (game_id) VALUES ('{g}'),('{g}'),('{g}');")
            self.sql.append(f"INSERT INTO partnerships (game_id) VALUES ('{g}'),('{g}');")
            self.sql.append(f"INSERT INTO fielding_stats (game_id,player_id) VALUES ('{g}','{OURS[0]}');")
            self.sql.append(f"INSERT INTO game_appearances VALUES ('{g}','{OURS[0]}'),('{g}','{THEIRS[0]}');")
        return g

    def manual(self, date, opp, result, scores, *, pair=None, wkts=(3, 2), runs_conceded=60, fow=0,
               created="now()"):
        m = self.nid()
        sup = f"'{pair}'" if pair else "NULL"
        flag = "true" if pair else "false"
        res = f"'{result}'" if result else "NULL"
        self.sql.append(
            f"INSERT INTO manual_games (id,organisation_id,season_id,grade_id,played_at,opposition,result,"
            f"superseded_by_game_id,pair_prefers_import,pairing_locked,created_at) VALUES "
            f"('{m}','{A}','{SEASON}','{GRADE}','{date}','{opp}',{res},{sup},{flag},{flag},{created});")
        for i, r in enumerate(scores):
            self.sql.append(f"INSERT INTO manual_batting_innings (manual_game_id,player_id,innings_number,runs) "
                            f"VALUES ('{m}','{OURS[i]}',1,{r});")
        for i, w in enumerate(wkts):
            rc = runs_conceded // max(len(wkts), 1)
            self.sql.append(f"INSERT INTO manual_bowling_spells (manual_game_id,player_id,innings_number,runs,wickets) "
                            f"VALUES ('{m}','{OURS[i]}',2,{rc},{w});")
        for _ in range(fow):
            self.sql.append(f"INSERT INTO manual_fall_of_wickets (manual_game_id) VALUES ('{m}');")
        return m


def build():
    sql = [f"INSERT INTO organisations VALUES ('{A}','test-club','Payneham'),('{B}','opp-club','Fulham');",
           f"INSERT INTO seasons VALUES ('{SEASON}','{A}','Summer 2025/26');",
           f"INSERT INTO grades VALUES ('{GRADE}','{SEASON}','1st XI');"]
    for i, p in enumerate(OURS):
        sql.append(f"INSERT INTO players VALUES ('{p}','Our Player {i}',NULL,'{A}');")
    for i, p in enumerate(THEIRS):
        sql.append(f"INSERT INTO players VALUES ('{p}','Their Player {i}',NULL,'{B}');")
    f = Fx(sql)
    # 1. AGREE: same date, result and scores. The synced one has far more detail.
    g1 = f.synced("2025-10-11", "Fulham", True, [101, 41, 7])
    f.manual("2025-10-11", "Fulham", "WIN", [101, 41, 7], pair=g1, fow=3)
    # 2. DIFFERS in one score (55 against 65), everything else equal.
    g2 = f.synced("2025-10-18", "Athelstone", True, [55, 30, 9])
    f.manual("2025-10-18", "Athelstone", "WIN", [65, 30, 9], pair=g2)
    # 3. PlayHQ holds no card of ours (only the opposition's), the import is the only card.
    g3 = f.synced("2025-10-25", "Goodwood", True, [], ours_batters=False, detail=False, wkts=())
    f.manual("2025-10-25", "Goodwood", "WIN", [80, 20], pair=g3, wkts=())
    # 4. Same scores, but the two dates are three days apart: matched on the scorecard.
    g4 = f.synced("2025-11-01", "Gaza", False, [12, 8, 3], detail=False)
    f.manual("2025-11-04", "Gaza", "LOSS", [12, 8, 3], pair=g4)
    # 5. Same everything except the result: we won on PlayHQ, the import says lost.
    g5 = f.synced("2025-11-08", "Grange", True, [40, 30], detail=False)
    f.manual("2025-11-08", "Grange", "LOSS", [40, 30], pair=g5)
    # 6. An EARLIER overwrite import (before :since) - must be left out.
    g6 = f.synced("2020-01-04", "Old", True, [1, 2, 3], detail=False)
    f.manual("2020-01-04", "Old", "WIN", [1, 2, 3], pair=g6, created="'2020-01-05'")
    # 7. A probable double: the import was not paired, but the same scores sit
    #    on a synced match the day after.
    g7 = f.synced("2025-11-15", "Mawson", True, [30, 20, 10], detail=False)
    f.manual("2025-11-16", "Mawson Lakes", "WIN", [30, 20, 10], pair=None)
    # 8. NOT a double: an unpaired import and a synced match with different scores.
    g8 = f.synced("2025-12-01", "Reynella", True, [5, 6, 7], detail=False)
    f.manual("2025-12-02", "Reynella", "WIN", [99, 98, 97], pair=None)
    return "\n".join(sql), {"g1": g1, "g2": g2, "g3": g3, "g4": g4, "g5": g5, "g7": g7, "g8": g8}


def read(path):
    return list(csv.DictReader(open(path, newline="")))


def main():
    r = subprocess.run(["psql", "-X", "-d", "postgres", "-tAc", "select 1"], capture_output=True, text=True)
    if r.returncode:
        print("no local Postgres to run against:", r.stderr.strip()[:200])
        sys.exit(2)
    subprocess.run(["psql", "-X", "-q", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {DB}"], check=True)
    subprocess.run(["psql", "-X", "-q", "-d", "postgres", "-c", f"CREATE DATABASE {DB}"], check=True)
    try:
        data, ids = build()
        res = psql(DB, DDL + data)
        if res.returncode:
            print("fixture failed:", res.stderr[:400])
            sys.exit(2)
        counts_before = psql(DB, "SELECT (SELECT count(*) FROM manual_games), (SELECT count(*) FROM games), "
                                 "(SELECT count(*) FROM batting_innings)").stdout
        with tempfile.TemporaryDirectory() as td:
            res = psql(DB, file=SQL, cwd=td,
                       vars_=(("org_slug", "test-club"), ("since", "2025-01-01")))
            if res.returncode:
                print("script failed:", res.stderr[:600])
                sys.exit(1)
            td = Path(td)
            pairs = {(x["g_id"]): x for x in read(td / "ov_pairs.csv")}
            check("only matches the import created on or after `since` are compared (the 2020 one is left out)",
                  len(pairs), 5)

            def row(key):
                return pairs[ids[key]]

            a = row("g1")
            check("matching date, result and scores read AGREE", a["verdict"], "AGREE")
            lost = a["detail_lost"]
            check("an AGREE pair still reports what the imported version lost", bool(lost), True)
            check("the lost detail names balls faced (3 batters)", "3 batters' balls faced" in lost, True)
            check("the lost detail names the opposition's batting and bowling cards",
                  "opposition batting card (2)" in lost and "opposition bowling card (1)" in lost, True)
            check("the lost detail names the bowler/fielder credits (2) and the partnerships (2)",
                  "2 dismissals with bowler/fielder named" in lost and "2 partnerships" in lost, True)
            check("fall of wickets the import also has is NOT reported as lost (3 on each side)",
                  "fall of wickets" not in lost, True)

            b = row("g2")
            check("one score differing (55 v 65) reads DIFFERS and names batting scores, nothing else",
                  (b["verdict"], b["differences"]), ("DIFFERS", "batting scores"))
            c = row("g3")
            check("a synced match with no card of ours reads PLAYHQ HAS NO CARD OF OURS",
                  c["verdict"], "PLAYHQ HAS NO CARD OF OURS")
            d = row("g4")
            check("the same scores on dates three days apart read DIFFERS for the date only",
                  (d["verdict"], d["differences"]), ("DIFFERS", "date"))
            e = row("g5")
            check("a result that differs (WIN on PlayHQ, LOSS imported) is named, and only that",
                  (e["verdict"], e["differences"], e["g_result"], e["m_result"]),
                  ("DIFFERS", "result", "WIN", "LOSS"))
            check("the result is worked out for OUR side from winning_team (the Gaza loss is a LOSS)",
                  (d["g_result"], d["m_result"]), ("LOSS", "LOSS"))

            unp = read(td / "ov_unpaired.csv")
            check("an unpaired import with the same scores a day from a synced match is listed as a probable double",
                  [(x["g_id"] == ids["g7"], x["scores_in_common"], x["same_date"]) for x in unp],
                  [(True, "3", "f")])
            check("an unpaired import with different scores is NOT listed (control)",
                  any(x["g_id"] == ids["g8"] for x in unp), False)

            enrich = read(td / "ov_enrich_batting.csv")
            g1rows = [x for x in enrich if x["g_id"] == ids["g1"]]
            check("the synced batting lines of a replaced match are exported with their balls faced",
                  sorted((int(x["runs"]), int(x["balls"])) for x in g1rows),
                  [(7, 19), (41, 87), (101, 207)])
            check("the export carries only OUR batters (the opposition's rows are not in it)",
                  all(x["player_name"].startswith("Our Player") for x in enrich), True)
            seasons = read(td / "ov_by_season.csv")
            check("the season summary adds up (1 agree, 3 differ, 1 no card)",
                  [(x["replaced"], x["agree"], x["differs"], x["no_playhq_card"]) for x in seasons],
                  [("5", "1", "3", "1")])

        after = psql(DB, "SELECT (SELECT count(*) FROM manual_games), (SELECT count(*) FROM games), "
                         "(SELECT count(*) FROM batting_innings)").stdout
        check("the script changed nothing (row counts before and after are equal)", after, counts_before)
        # a slug that matches nothing must fail loudly, not report an empty club
        with tempfile.TemporaryDirectory() as td2:
            bad = psql(DB, file=SQL, cwd=td2, vars_=(("org_slug", "no-such-club"), ("since", "2025-01-01")))
            check("an unknown organisation slug is refused", bad.returncode != 0 and "expected exactly 1" in bad.stderr, True)
    finally:
        subprocess.run(["psql", "-X", "-q", "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {DB}"])
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


main()
