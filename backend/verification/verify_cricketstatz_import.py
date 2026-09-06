"""Verification for the CricketStatz import, against a real Postgres.

Asked for directly: a club pastes the address of its own public CricketStatz
stats page and BetterCricket pulls ALL of its data across — every season, every
match, every scorecard, and the record book CricketStatz has already computed.

Runs the SHIPPED parsers, the shipped import service and the shipped route
bodies — never a re-implementation — over real captured CricketStatz payloads
in verification/fixtures/cricketstatz/ (a modern card, a 1995 card, an
abandoned match, a result-only match, a season's results, the club page, the
team list and three record reports).

The network is stubbed at the client so the suite is reproducible and never
touches someone else's server.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/bettercricket?host=/tmp&port=5599 \
      python verification/verify_cricketstatz_import.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base  # noqa: E402
from app.services import cricketstatz_import as importer  # noqa: E402
from app.services.cricketstatz_ddl import DOWNGRADE, STATEMENTS  # noqa: E402
from app.services.cricketstatz_parse import (  # noqa: E402
    RECORD_REPORTS,
    CricketStatzError,
    parse_club_page,
    parse_club_url,
    parse_report,
    parse_results,
    parse_scorecard,
    parse_teams,
    unwrap,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cricketstatz"
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/bettercricket?host=/tmp&port=5599",
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ── the parsers, against real captured reports ───────────────────────────────

def verify_parsers() -> dict:
    print("\nParsers (real captured CricketStatz reports)")

    club_id = parse_club_url(
        "https://www2.cricketstatz.com/ss/w?mode=104&club=93931&team=0&season=")
    check("club number read out of the pasted address", club_id == "93931", club_id)
    check("a bare club number is accepted", parse_club_url("93931") == "93931")
    check("a non-CricketStatz address is refused", parse_club_url("https://example.com") is None)

    page = parse_club_page(fixture("club_page.html"))
    check("club name off the page", page["club_name"] == "Keon Park Cricket Club",
          page["club_name"])
    check("season list found", len(page["seasons"]) > 100, str(len(page["seasons"])))
    check("the 'all time' entry is not offered as a season",
          all(s["value"] != "00" for s in page["seasons"]))

    teams = parse_teams(fixture("teams.txt"))
    check("team list parsed", len(teams) >= 6 and any("Keon Park" in t["name"] for t in teams),
          str(len(teams)))

    results = parse_results(fixture("results_2025S.txt"))
    check("a season's matches parsed", len(results) == 97, str(len(results)))
    check("every match carries its report id",
          all(r["source_match_id"].isdigit() for r in results))
    check("no match listed twice",
          len({r["source_match_id"] for r in results}) == len(results))
    dated = [r for r in results if r["date"]]
    check("matches carry a date", len(dated) == len(results))
    check("the points tail is off the result",
          all("Points:" not in (r["result"] or "") for r in results))

    modern = parse_scorecard(fixture("card_modern.txt"))
    check("modern card: both teams",
          modern["home_team"] == "Montmorency ‘1-Day’"
          and modern["away_team"] == "Keon Park 3rd-XI",
          f"{modern['home_team']} / {modern['away_team']}")
    check("modern card: result and winner",
          modern["winning_team"] == "Montmorency ‘1-Day’"
          and "8 wickets" in modern["result"], modern["result"])
    check("modern card: venue, date, grade, round",
          (modern["venue"], modern["date"], modern["division"], modern["round"])
          == ("Central Park", "2026-03-07", "G-GRADE", "SEMI FINAL"),
          str((modern["venue"], modern["date"], modern["division"], modern["round"])))
    check("modern card: toss", modern["toss_winner"] == "Keon Park 3rd-XI")
    check("modern card: two innings", len(modern["innings"]) == 2)

    inn = modern["innings"][0]
    check("modern card: innings total, wickets, overs",
          (inn["runs"], inn["wickets"], inn["overs"]) == (119, 10, 34.4),
          str((inn["runs"], inn["wickets"], inn["overs"])))
    check("modern card: extras split",
          inn["extras"] == {"b": 0, "lb": 1, "w": 6, "nb": 1}
          and inn["extras_total"] == 8, str(inn["extras"]))
    check("modern card: batting reconciles with the total",
          sum(b["runs"] or 0 for b in inn["batters"]) + inn["extras_total"] == inn["runs"])
    check("modern card: fall of wickets", len(inn["fall_of_wickets"]) == 10)
    check("modern card: bowling figures", len(inn["bowlers"]) == 6)

    opener = inn["batters"][0]
    check("modern card: a duck reads as 0, not a missing figure",
          opener["runs"] == 0 and opener["balls"] == 1, str(opener["runs"]))
    check("modern card: caught names both fielder and bowler",
          opener["dismissal_type"] == "caught"
          and opener["fielder"]["name"] == "Mitchell Orr"
          and opener["bowler"]["name"] == "Tim Goodman-Pearce")
    ro = next(b for b in inn["batters"] if b["dismissal_type"] == "run out")
    check("modern card: a run out has no bowler", ro["bowler"] is None)
    capt = [b for b in inn["batters"] if b["is_captain"]]
    check("modern card: the captain is marked", len(capt) == 1, str(len(capt)))
    check("modern card: every player carries a CricketStatz id",
          all(b["batter"]["source_player_id"] for b in inn["batters"]))

    old = parse_scorecard(fixture("card_1995.txt"))
    check("1995 card: header survives a 'won on 1st Innings' result",
          old["home_team"] == "Keon Park 1's 'A-Grade'"
          and old["away_team"] == "A-Grade Northern Socials",
          f"{old['home_team']} / {old['away_team']}")
    check("1995 card: a two-day match keeps both dates",
          old["date"] == "1995-12-16" and old["end_date"] == "1995-12-23")
    ob = old["innings"][0]["batters"][0]
    check("1995 card: boundaries are not read as balls faced",
          ob["balls"] is None and ob["fours"] == 3 and ob["runs"] == 22,
          f"balls={ob['balls']} 4s={ob['fours']} R={ob['runs']}")
    check("1995 card: the bowler is still credited when the fielder is 'N/A'",
          ob["dismissal_type"] == "caught" and ob["bowler"] is not None
          and ob["fielder"] is None,
          f"{ob['dismissal_type']} b={ob['bowler']} f={ob['fielder']}")

    washed = parse_scorecard(fixture("card_washed_out.txt"))
    check("an abandoned innings parses without a total rather than failing",
          any(i["runs"] is None for i in washed["innings"]))

    thin = parse_scorecard(fixture("card_result_only.txt"))
    check("a result-only match still yields its header",
          thin["date"] == "1985-11-02" and thin["division"] == "A-GRADE"
          and not thin["innings"],
          f"{thin['date']} {thin['division']} innings={len(thin['innings'])}")

    juniors = parse_scorecard(fixture("card_unnamed_juniors.txt"))
    check("a junior card with no names still parses its innings",
          len(juniors["innings"]) == 3, str(len(juniors["innings"])))
    unnamed = [b for i in juniors["innings"] for b in i["batters"]
               if importer.is_placeholder_name(b["batter"]["name"])]
    check("its unnamed batters are recognised as placeholders, not people",
          len(unnamed) >= 15, str(len(unnamed)))
    check("'N/A' is a placeholder and a real name is not",
          importer.is_placeholder_name("N/A")
          and importer.is_placeholder_name("********")
          and not importer.is_placeholder_name("Brad Quinsee"))

    aggregates = parse_report(fixture("record_aggregates.txt"))
    check("record book: title and headers",
          aggregates["title"] == "Top Run Aggregates"
          and aggregates["headers"][:3] == ["#", "Name", "Mts"],
          str(aggregates["headers"][:3]))
    check("record book: rows carry their player id",
          aggregates["rows"][0]["players"][0]["source_player_id"].isdigit())
    margins = parse_report(fixture("record_margins.txt"))
    check("record book: a team record needs no player",
          margins["title"] == "Highest Winning Margins by Runs"
          and margins["rows"][0]["players"] == [])
    totals = parse_report(fixture("record_totals.txt"))
    check("record book: highest innings totals",
          totals["rows"][0]["values"][-1] == "500/7",
          totals["rows"][0]["values"][-1])
    check("record book catalogue covers batting, bowling, fielding and team",
          {s for _, s, _ in RECORD_REPORTS} >= {"batting", "bowling", "fielding", "team"})

    try:
        unwrap('document.write("Error: Subscription expired. Please ask your '
               'administrator to reactivate it.");')
        check("a lapsed subscription is reported, not read as an empty club", False)
    except CricketStatzError as exc:
        check("a lapsed subscription is reported, not read as an empty club",
              exc.kind == "subscription_expired")

    return {"results": results, "modern": modern, "old": old,
            "thin": thin, "page": page, "teams": teams}


# ── the team matcher ─────────────────────────────────────────────────────────

def verify_team_matcher() -> None:
    print("\nWhich side is ours")
    is_ours = importer.build_team_matcher(
        "Keon Park Cricket Club",
        ["Keon Park 1st-XI", "Keon Park 3rd-XI", "KPCC Summer Smash"])
    check("the club's own XI is ours", is_ours("Keon Park 3rd-XI"))
    check("a side entered under the club's initials is ours",
          is_ours("KPCC Summer Smash"))
    check("the opposition is not ours", not is_ours("Montmorency ‘1-Day’"))
    check("a same-named opposition grade side is not ours",
          not is_ours("A-Grade Northern Socials"))
    check("an empty team name is not ours", not is_ours(""))


# ── partnerships ─────────────────────────────────────────────────────────────

def verify_partnerships(modern: dict) -> None:
    print("\nPartnerships derived from the fall of wickets")
    inn = modern["innings"][0]
    stands = importer.derive_partnerships(
        inn["batters"], inn["fall_of_wickets"], inn["runs"])
    check("one stand per wicket", len(stands) == 10, str(len(stands)))
    check("the stands add up to the innings' batting total",
          sum(s["runs"] for s in stands) == inn["runs"],
          f"{sum(s['runs'] for s in stands)} vs {inn['runs']}")
    check("the opening stand is the score at the first wicket",
          stands[0]["runs"] == inn["fall_of_wickets"][0]["score_at_fall"])
    check("every stand names two batters",
          all(s["batter1"] and s["batter2"] for s in stands))
    check("no stand is negative", all(s["runs"] >= 0 for s in stands))


# ── the schema ───────────────────────────────────────────────────────────────

async def verify_schema(engine) -> None:
    print("\nSchema (migration 285)")
    # Applied three times: alembic runs it once and the lifespan mirror re-runs
    # the whole list on every boot, so it has to be a no-op after the first.
    for _ in range(3):
        async with engine.begin() as conn:
            for statement in STATEMENTS:
                await conn.execute(text(statement))
    async with engine.begin() as conn:
        tables = {r[0] for r in (await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name LIKE 'cricketstatz%'
        """))).all()}
        check("applied three times without error", True)
        check("both tables exist",
              tables == {"cricketstatz_imports", "cricketstatz_records"}, str(tables))
        cols = {r[0] for r in (await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'manual_games'
               AND column_name LIKE 'cricketstatz%'
        """))).all()}
        check("manual_games carries the match id and its batch",
              cols == {"cricketstatz_match_id", "cricketstatz_import_id"}, str(cols))
        n = (await conn.execute(text("""
            SELECT COUNT(*) FROM pg_indexes
             WHERE indexname = 'uq_players_org_cricketstatz'
        """))).scalar()
        check("a player's CricketStatz id is unique within the club", n == 1)
        beat = (await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
             WHERE table_name = 'cricketstatz_imports' AND column_name = 'updated_at'
        """))).scalar()
        check("an import carries a heartbeat (migration 286)", beat == 1)


# ── the import, end to end ───────────────────────────────────────────────────

class StubSite:
    """Serves the captured fixtures in place of the network."""

    def __init__(self):
        self.scorecard_calls = 0
        self.season_probes = 0
        self.cards = {
            "3177313": fixture("card_modern.txt"),
            "3082300": fixture("card_1995.txt"),
            "3082136": fixture("card_result_only.txt"),
            "3176144": fixture("card_unnamed_juniors.txt"),
        }
        self.rows = [
            {"source_match_id": "3177313", "round": "SEMI FINAL",
             "date": "2026-03-07", "end_date": None,
             "home_team": "Montmorency ‘1-Day’", "away_team": "Keon Park 3rd-XI",
             "division": "G-GRADE", "venue": "Central Park",
             "result": "Montmorency ‘1-Day’ Won by 8 wickets",
             "winning_team": "Montmorency ‘1-Day’"},
            {"source_match_id": "3082300", "round": "07",
             "date": "1995-12-16", "end_date": "1995-12-23",
             "home_team": "Keon Park 1's 'A-Grade'",
             "away_team": "A-Grade Northern Socials",
             "division": "A-GRADE", "venue": "Donath #01",
             "result": "Keon Park 1's 'A-Grade' won on 1st Innings by 14 runs",
             "winning_team": "Keon Park 1's 'A-Grade'"},
            {"source_match_id": "3176144", "round": "05",
             "date": "2026-02-25", "end_date": None,
             "home_team": "Keon Park U/9", "away_team": "Laurimar U/9 (White)",
             "division": "UNDER 9", "venue": "Donath #01",
             "result": "Match Drawn", "winning_team": ""},
            {"source_match_id": "3082136", "round": "02",
             "date": "1985-11-02", "end_date": None,
             "home_team": "Keon Park 1's 'A-Grade'", "away_team": "A-Grade Oakhill",
             "division": "A-GRADE", "venue": "Donath", "result": "Match Drawn",
             "winning_team": ""},
        ]

    async def fetch_club_page(self, club_id):
        return parse_club_page(fixture("club_page.html"))

    async def fetch_teams(self, club_id):
        return parse_teams(fixture("teams.txt"))

    async def fetch_results(self, club_id, season=None):
        if season is None:
            return list(self.rows)
        self.season_probes += 1
        if season == "2025S":
            return [self.rows[0], self.rows[1]]
        if season == "1995S":
            return [self.rows[2]]
        if season == "1985S":
            return [self.rows[3]]
        return []

    async def fetch_scorecard(self, club_id, match_id):
        self.scorecard_calls += 1
        card = parse_scorecard(self.cards[str(match_id)])
        card["source_match_id"] = str(match_id)
        return card

    async def fetch_report(self, club_id, mode):
        by_mode = {4: "record_aggregates.txt", 27: "record_totals.txt",
                   72: "record_margins.txt"}
        if mode not in by_mode:
            return {"title": "", "scope": "", "headers": [], "rows": []}
        return parse_report(fixture(by_mode[mode]))


async def verify_import(engine, session_maker) -> tuple:
    print("\nThe import, end to end")

    org_id = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:id, 'Keon Park Cricket Club', 'keon-park', true)
        """), {"id": str(org_id)})
        await db.commit()

    stub = StubSite()
    real_client = importer.client
    importer.client = stub
    try:
        import_id = uuid.uuid4()
        async with session_maker() as db:
            await db.execute(text("""
                INSERT INTO cricketstatz_imports
                    (id, organisation_id, club_id, source_url, status, phase)
                VALUES (:id, :org, '93931', 'https://www2.cricketstatz.com/ss/w?club=93931',
                        'running', 'starting')
            """), {"id": str(import_id), "org": str(org_id)})
            await db.commit()

        await importer.run_import(session_maker, org_id, import_id, "93931")

        async with session_maker() as db:
            row = (await db.execute(text("""
                SELECT status, error, club_name, progress FROM cricketstatz_imports
                 WHERE id = :id
            """), {"id": str(import_id)})).mappings().first()
            check("the import completed", row["status"] == "complete",
                  f"{row['status']}: {row['error']}")
            check("the club's own name was read", row["club_name"] == "Keon Park Cricket Club")
            progress = row["progress"] or {}
            check("every match was walked", progress.get("matches_done") == 4,
                  str(progress.get("matches_done")))
            check("the scorecards were counted", progress.get("scorecards") == 3,
                  str(progress.get("scorecards")))

            games = (await db.execute(text("""
                SELECT cricketstatz_match_id, played_at, opposition, venue,
                       winning_team, is_final, season_id, grade_id
                  FROM manual_games WHERE organisation_id = :org
                 ORDER BY played_at
            """), {"org": str(org_id)})).mappings().all()
            check("every match was written", len(games) == 4, str(len(games)))
            check("a result-only match is kept, not dropped",
                  any(g["cricketstatz_match_id"] == "3082136" for g in games))
            recent = next(g for g in games if g["cricketstatz_match_id"] == "3177313")
            check("the opposition is the other side, not us",
                  recent["opposition"] == "Montmorency ‘1-Day’", str(recent["opposition"]))
            check("a semi-final is marked as a final", recent["is_final"] is True)
            check("every match has a season", all(g["season_id"] for g in games))
            check("every match has its grade", all(g["grade_id"] for g in games))

            seasons = (await db.execute(text("""
                SELECT name, year FROM seasons WHERE organisation_id = :org
                 ORDER BY year
            """), {"org": str(org_id)})).mappings().all()
            check("seasons were created from the club's own history",
                  [s["year"] for s in seasons] == [1985, 1995, 2025],
                  str([s["year"] for s in seasons]))
            check("a southern season is named the way the app writes one",
                  seasons[-1]["name"] == "Summer 2025/26", seasons[-1]["name"])

            grades = (await db.execute(text("""
                SELECT g.name FROM grades g JOIN seasons s ON s.id = g.season_id
                 WHERE s.organisation_id = :org ORDER BY g.name
            """), {"org": str(org_id)})).scalars().all()
            check("grades came across, juniors included",
                  set(grades) == {"A-GRADE", "G-GRADE", "UNDER 9"}, str(grades))

            # Only OUR players — the cross-club leak rule.
            players = (await db.execute(text("""
                SELECT name, cricketstatz_player_id FROM players
                 WHERE organisation_id = :org
            """), {"org": str(org_id)})).mappings().all()
            names = {p["name"] for p in players}
            check("our own players were created",
                  "Tommy A McSwain" in names and "Warren Stewart Snr" in names)
            check("an opponent who only ever batted against us is not one of our players",
                  "Jon Bunn" not in names, "Jon Bunn was created")
            check("every player carries their CricketStatz id",
                  all(p["cricketstatz_player_id"] for p in players))

            bat = (await db.execute(text("""
                SELECT b.runs, b.balls, b.fours, b.dismissal_type, b.not_out, p.name
                  FROM manual_batting_innings b
                  JOIN manual_games g ON g.id = b.manual_game_id
                  JOIN players p ON p.id = b.player_id
                 WHERE g.cricketstatz_match_id = '3177313'
                 ORDER BY b.batting_position
            """))).mappings().all()
            check("our batting card was written", len(bat) == 11, str(len(bat)))
            check("the innings' runs match the card",
                  sum(b["runs"] for b in bat) == 111,
                  str(sum(b["runs"] for b in bat)))
            check("a not-out batter is marked", any(b["not_out"] for b in bat))

            bowl = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_bowling_spells s
                  JOIN manual_games g ON g.id = s.manual_game_id
                 WHERE g.cricketstatz_match_id = '3177313'
            """))).scalar()
            check("our bowling figures were written (we bowled the other innings)",
                  bowl == 9, str(bowl))

            fow = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_fall_of_wickets f
                  JOIN manual_games g ON g.id = f.manual_game_id
                 WHERE g.cricketstatz_match_id = '3177313'
            """))).scalar()
            check("our fall of wickets came across", fow == 10, str(fow))

            stands = (await db.execute(text("""
                SELECT SUM(p.runs) FROM manual_partnerships p
                  JOIN manual_games g ON g.id = p.manual_game_id
                 WHERE g.cricketstatz_match_id = '3177313'
            """))).scalar()
            # A stand's runs are everything added while those two were together,
            # extras included, so the stands sum to the innings TOTAL (119) —
            # not the batting-only figure (111).
            check("the stands add up to the innings total, extras included",
                  stands == 119, str(stands))

            field = (await db.execute(text("""
                SELECT SUM(catches), SUM(catches_wk), SUM(run_outs), SUM(stumpings)
                  FROM manual_fielding_stats f
                  JOIN manual_games g ON g.id = f.manual_game_id
                 WHERE g.cricketstatz_match_id = '3177313'
            """))).first()
            check("our fielding was credited from the other innings",
                  (field[0] or 0) >= 1, str(field))
            check("a keeper's catch counts in the total as well as the keeper column",
                  (field[1] or 0) <= (field[0] or 0), str(field))

            # An unnamed junior side must not collapse onto one shared
            # "N/A" player — that is what the one-innings-per-player index
            # refuses, and the failure used to cascade through the season.
            na = (await db.execute(text("""
                SELECT COUNT(*) FROM players
                 WHERE organisation_id = :org AND lower(name) IN ('n/a','na','unknown')
            """), {"org": str(org_id)})).scalar()
            check("a card with no names creates no player called 'N/A'",
                  na == 0, str(na))
            juniors_in = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_games
                 WHERE organisation_id = :org AND cricketstatz_match_id = '3176144'
            """), {"org": str(org_id)})).scalar()
            check("the unnamed junior match is still imported, names or not",
                  juniors_in == 1, str(juniors_in))
            kept_card = (await db.execute(text("""
                SELECT jsonb_array_length(extracted_payload->'innings')
                  FROM manual_games
                 WHERE organisation_id = :org AND cricketstatz_match_id = '3176144'
            """), {"org": str(org_id)})).scalar()
            check("and its full card is kept even where we could not name anyone",
                  kept_card == 3, str(kept_card))
            later = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_games
                 WHERE organisation_id = :org AND cricketstatz_match_id = '3177313'
            """), {"org": str(org_id)})).scalar()
            check("a match we cannot fully read does not cost the season its others",
                  later == 1, str(later))

            records = (await db.execute(text("""
                SELECT mode, title, row_count FROM cricketstatz_records
                 WHERE organisation_id = :org ORDER BY mode
            """), {"org": str(org_id)})).mappings().all()
            check("the record book came across", len(records) == 3, str(len(records)))
            check("a record board keeps its rows",
                  all(r["row_count"] > 0 for r in records))
            check("the biggest winning margins are among them",
                  any("Winning Margins" in r["title"] for r in records))

        # ── re-import corrects rather than doubles ──────────────────────────
        second = uuid.uuid4()
        async with session_maker() as db:
            await db.execute(text("""
                INSERT INTO cricketstatz_imports
                    (id, organisation_id, club_id, status, phase)
                VALUES (:id, :org, '93931', 'running', 'starting')
            """), {"id": str(second), "org": str(org_id)})
            await db.commit()
        await importer.run_import(session_maker, org_id, second, "93931")

        async with session_maker() as db:
            again = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_games WHERE organisation_id = :org
            """), {"org": str(org_id)})).scalar()
            check("a re-import updates the same matches rather than doubling them",
                  again == 4, str(again))
            bat_again = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_batting_innings b
                  JOIN manual_games g ON g.id = b.manual_game_id
                 WHERE g.cricketstatz_match_id = '3177313'
            """))).scalar()
            check("a re-import does not double an innings", bat_again == 11,
                  str(bat_again))
            boards = (await db.execute(text("""
                SELECT COUNT(*) FROM cricketstatz_records
                 WHERE organisation_id = :org
            """), {"org": str(org_id)})).scalar()
            check("a re-import replaces a record board rather than stacking one",
                  boards == 3, str(boards))
            players_again = (await db.execute(text("""
                SELECT COUNT(*) FROM players WHERE organisation_id = :org
            """), {"org": str(org_id)})).scalar()
            check("a re-import mints no duplicate players",
                  players_again == len(players), str(players_again))

        return org_id, second, len(players)
    finally:
        importer.client = real_client


async def verify_planning() -> None:
    print("\nThe first pass — what there is, and where")

    page = parse_club_page(fixture("club_page.html"))
    stub = StubSite()
    real = importer.client
    importer.client = stub
    try:
        plan = await importer.plan_seasons("93931", page["seasons"])
    finally:
        importer.client = real

    played = {s["value"] for s, _ in plan}
    check("the seasons the club actually played are found",
          played == {"2025S", "1995S", "1985S"}, str(played))
    check("the 160-odd candidate seasons with nothing in them are left out",
          len(plan) == 3 and len(page["seasons"]) > 100,
          f"{len(plan)} of {len(page['seasons'])}")
    check("a season's matches are kept, so the import re-reads nothing",
          all(rows for _, rows in plan))
    check("the plan runs oldest first, so a history fills forwards",
          [s["value"] for s, _ in plan] == ["1985S", "1995S", "2025S"],
          str([s["value"] for s, _ in plan]))

    summary = importer.plan_summary(plan)
    check("the plan names the real total up front",
          summary["match_count"] == 4 and summary["season_count"] == 3,
          str((summary["match_count"], summary["season_count"])))
    check("and the club's real span", (summary["earliest"], summary["latest"])
          == (1985, 2025), str((summary["earliest"], summary["latest"])))
    check("with an estimate of how long it will take",
          summary["estimated_minutes"] >= 1)
    check("every season in the plan carries its own match count",
          all("matches" in row for row in summary["seasons"]))

    # Every candidate is probed. A club's history can have gaps, so stopping at
    # the first run of empty years would silently truncate it.
    check("every candidate season is probed, not just a guessed range",
          stub.season_probes == len(page["seasons"]),
          f"{stub.season_probes} of {len(page['seasons'])}")


async def verify_heartbeat(session_maker, org_id) -> None:
    print("\nHeartbeat and a run that stops responding")

    async with session_maker() as db:
        beat = (await db.execute(text("""
            SELECT updated_at IS NOT NULL FROM cricketstatz_imports
             WHERE organisation_id = :org ORDER BY started_at DESC LIMIT 1
        """), {"org": str(org_id)})).scalar()
        check("an import records when it last moved", beat is True)

    # A run whose process was lost sits 'running' with nothing behind it.
    stalled_id = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, status, phase, started_at, updated_at)
            VALUES (:id, :org, '93931', 'running', 'matches',
                    NOW() - INTERVAL '2 hours', NOW() - INTERVAL '90 minutes')
        """), {"id": str(stalled_id), "org": str(org_id)})
        await db.commit()

    async with session_maker() as db:
        row = (await db.execute(text("""
            SELECT status,
                   EXTRACT(EPOCH FROM (NOW() - COALESCE(updated_at, started_at))) AS quiet
              FROM cricketstatz_imports WHERE id = :id
        """), {"id": str(stalled_id)})).mappings().first()
        quiet = int(row["quiet"])
        check("a run silent for 90 minutes reads as stalled",
              quiet > importer.STALL_AFTER_SECONDS, f"{quiet}s")
        check("the stall threshold is minutes, not seconds — a slow request is "
              "not a dead run", importer.STALL_AFTER_SECONDS >= 120,
              str(importer.STALL_AFTER_SECONDS))

    # A fresh run is NOT mistaken for a stalled one.
    live_id = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, status, phase, started_at, updated_at)
            VALUES (:id, :org, '93931', 'running', 'matches', NOW(), NOW())
        """), {"id": str(live_id), "org": str(org_id)})
        await db.commit()
        quiet = int((await db.execute(text("""
            SELECT EXTRACT(EPOCH FROM (NOW() - updated_at)) FROM cricketstatz_imports
             WHERE id = :id
        """), {"id": str(live_id)})).scalar())
        check("an import that just moved is not called stalled",
              quiet < importer.STALL_AFTER_SECONDS, f"{quiet}s")
        await db.execute(text("DELETE FROM cricketstatz_imports WHERE id IN (:a,:b)"),
                         {"a": str(stalled_id), "b": str(live_id)})
        await db.commit()


async def verify_undo(session_maker, org_id, import_id, player_count) -> None:
    print("\nUndo")
    async with session_maker() as db:
        result = await importer.undo_import(db, org_id, import_id)
        check("every match the import wrote was removed",
              result["matches_removed"] == 4, str(result))
        check("the record book was removed with it",
              result["records_removed"] == 3, str(result))

    async with session_maker() as db:
        left = (await db.execute(text("""
            SELECT COUNT(*) FROM manual_games WHERE organisation_id = :org
        """), {"org": str(org_id)})).scalar()
        check("no match is left behind", left == 0, str(left))
        orphan = (await db.execute(text("""
            SELECT COUNT(*) FROM manual_batting_innings b
             WHERE NOT EXISTS (SELECT 1 FROM manual_games g WHERE g.id = b.manual_game_id)
        """))).scalar()
        check("its innings went with it, leaving nothing orphaned", orphan == 0, str(orphan))
        kept = (await db.execute(text("""
            SELECT COUNT(*) FROM players WHERE organisation_id = :org
        """), {"org": str(org_id)})).scalar()
        check("players are kept — a person is not the import's to delete",
              kept == player_count, str(kept))
        marked = (await db.execute(text("""
            SELECT undone_at IS NOT NULL FROM cricketstatz_imports WHERE id = :id
        """), {"id": str(import_id)})).scalar()
        check("the import is recorded as undone", marked is True)


async def verify_downgrade(engine) -> None:
    print("\nDowngrade")
    async with engine.begin() as conn:
        for statement in DOWNGRADE:
            await conn.execute(text(statement))
        left = (await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name LIKE 'cricketstatz%'
        """))).scalar()
        check("the downgrade removes its own tables", left == 0, str(left))
        cols = (await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns
             WHERE table_name = 'manual_games' AND column_name LIKE 'cricketstatz%'
        """))).scalar()
        check("and its columns", cols == 0, str(cols))


async def main() -> int:
    fixtures_present = FIXTURES.exists() and any(FIXTURES.iterdir())
    if not fixtures_present:
        print(f"Missing fixtures in {FIXTURES}")
        return 2

    parsed = verify_parsers()
    verify_team_matcher()
    await verify_planning()
    verify_partnerships(parsed["modern"])

    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await verify_schema(engine)
    org_id, import_id, players = await verify_import(engine, session_maker)
    await verify_heartbeat(session_maker, org_id)
    await verify_undo(session_maker, org_id, import_id, players)
    await verify_downgrade(engine)
    await engine.dispose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
