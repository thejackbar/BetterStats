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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base  # noqa: E402
from app.services import cricketstatz_import as importer  # noqa: E402
from app.services.cricketstatz_ddl import DOWNGRADE, STATEMENTS  # noqa: E402
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL  # noqa: E402
from app.services.cricketstatz_parse import (  # noqa: E402
    RECORD_REPORTS,
    CricketStatzError,
    parse_club_page,
    parse_club_url,
    parse_player_notes,
    parse_report,
    parse_results,
    parse_scorecard,
    parse_teams,
    unwrap,
)
from app.services.cricketstatz_awards import classify_note, season_label

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cricketstatz"
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/bettercricket?host=/tmp&port=5599",
)

PASS, FAIL = [], []

# Lifespan-created (raw SQL in main.py), so the ORM's create_all never makes
# them. Kept here in the same shape the app builds.
AWARD_DDL = (
    """
    CREATE TABLE IF NOT EXISTS player_achievements (
        id SERIAL PRIMARY KEY,
        org_id UUID NOT NULL,
        player_id UUID,
        player_name TEXT NOT NULL,
        season TEXT,
        season_end TEXT,
        category TEXT NOT NULL,
        subcategory TEXT,
        achievement TEXT NOT NULL,
        detail TEXT,
        import_batch_id UUID,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS achievement_import_batches (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        filename TEXT,
        row_count INTEGER NOT NULL DEFAULT 0,
        created_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'imported',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        undone_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_award_definitions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        category TEXT NOT NULL,
        subcategory TEXT,
        achievement TEXT,
        display_name TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
)

# Players the club already holds before the import runs.
HELD_PLAYER = uuid.UUID("11111111-1111-4111-8111-111111111111")
HELD_MIDDLE = uuid.UUID("22222222-2222-4222-8222-222222222222")


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
            # `games.raw_payload` is JSON on the ORM model and JSONB in the
            # database the migrations build, so a create_all harness gets the
            # narrower type and the view's `NULL::jsonb` cannot union with it.
            # The app is unaffected — this only reconciles the harness with
            # what production actually holds.
            # Dropped first: the second and third pass find the view already
            # built on the column, and a type change cannot go through it.
            await conn.execute(text("DROP VIEW IF EXISTS v_effective_games CASCADE"))
            await conn.execute(text(
                "ALTER TABLE games ALTER COLUMN raw_payload TYPE jsonb "
                "USING raw_payload::text::jsonb"))
            # Migration 287 rides here too: the same idempotent-three-times
            # rule, and the views it replaces have to exist before the overlap
            # checks below can read them.
            for statement in SUPERSEDED_DDL:
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
        self.note_calls = 0
        self.notes_by_player = {}
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

    async def fetch_player_notes(self, club_id, player_id):
        # A player with a full honour board, one with only a life membership
        # and a cap, and one whose notes are biography — every line real,
        # captured live. Assigned per player and REMEMBERED, so a second import
        # reads the same notes back the way the real site would; keying on call
        # order alone would serve nothing at all on the second pass and the
        # checks would be measuring the harness.
        key = str(player_id)
        if key not in self.notes_by_player:
            fixtures = [
                parse_player_notes(fixture("player_notes_rich.txt")),
                parse_player_notes(fixture("player_notes_plain.txt")),
                ["COLLINGWOOD FC (313 Games)", "wk"],
            ]
            idx = len(self.notes_by_player)
            self.notes_by_player[key] = fixtures[idx] if idx < len(fixtures) else []
        self.note_calls += 1
        return self.notes_by_player[key]

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
        # The club already holds its players, spelled the way a club's own
        # records spell them — surname first, and one with a middle initial the
        # CricketStatz card does not carry. This is the reported case.
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name) VALUES
                (:a, :org, 'McSwain, Tommy A'),
                (:b, :org, 'Crosta, T')
        """), {"a": str(HELD_PLAYER), "b": str(HELD_MIDDLE), "org": str(org_id)})
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

            classified = (await db.execute(text("""
                SELECT g.name, g.category, g.categories, g.grassroots_id
                  FROM grades g JOIN seasons s ON s.id = g.season_id
                 WHERE s.organisation_id = :org ORDER BY g.name
            """), {"org": str(org_id)})).mappings().all()
            check("every grade is classified on the way in, like the other importers",
                  all(c["category"] for c in classified),
                  str([(c["name"], c["category"]) for c in classified]))
            check("both category columns are written, never just the one",
                  all(c["categories"] for c in classified),
                  str([(c["name"], c["categories"]) for c in classified]))
            junior = next(c for c in classified if c["name"] == "UNDER 9")
            check("a junior grade is filed as junior, so it stays out of senior careers",
                  junior["category"] == "junior", str(junior["category"]))
            senior = next(c for c in classified if c["name"] == "A-GRADE")
            check("a senior grade is filed as senior", senior["category"] == "senior",
                  str(senior["category"]))
            check("an imported grade is marked as not from a sync",
                  all(c["grassroots_id"] is None for c in classified))
            marker = (await db.execute(text("""
                SELECT COUNT(*) FROM seasons
                 WHERE organisation_id = :org AND grassroots_id IS NOT NULL
            """), {"org": str(org_id)})).scalar()
            check("and so is an imported season", marker == 0, str(marker))

            # Only OUR players — the cross-club leak rule.
            players = (await db.execute(text("""
                SELECT name, cricketstatz_player_id FROM players
                 WHERE organisation_id = :org
            """), {"org": str(org_id)})).mappings().all()
            names = {p["name"] for p in players}
            check("our own players were created", "Warren Stewart Snr" in names)
            # The reported bug: the club holds "Quinsee, Brad" while the card
            # says "Brad Quinsee", and matching on the raw spelling minted a
            # second record for every player the club already had.
            check("a player the club already held is matched, not duplicated",
                  "McSwain, Tommy A" in names and "Tommy A McSwain" not in names,
                  str(sorted(n for n in names if "McSwain" in n)))
            held = (await db.execute(text("""
                SELECT COUNT(*) FROM players
                 WHERE organisation_id = :org AND id = :pid
                   AND cricketstatz_player_id IS NOT NULL
            """), {"org": str(org_id), "pid": str(HELD_PLAYER)})).scalar()
            check("and the record the club already had is the one that was used",
                  held == 1, str(held))
            # An initial is not an identity — "Crosta, T" could be a Torey, a
            # Tim or a Tom — so this is deliberately NOT merged, and is
            # reported instead for Merge Duplicates to settle.
            crosta = sorted(n for n in names if "Crosta" in n)
            check("a bare initial is never merged into a full name on a guess",
                  crosta == ["Crosta, T", "Torey Crosta"], str(crosta))
            notes = " ".join((row["progress"] or {}).get("notes") or [])
            check("and a near match is reported so it can be merged by hand",
                  "Torey Crosta" in notes and "Merge Duplicates" in notes,
                  notes[:120])
            check("an opponent who only ever batted against us is not one of our players",
                  "Jon Bunn" not in names, "Jon Bunn was created")
            check("every player the import resolved carries their CricketStatz id",
                  all(p["cricketstatz_player_id"] for p in players
                      if p["name"] != "Crosta, T"),
                  str([p["name"] for p in players if not p["cricketstatz_player_id"]]))

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


async def verify_repair(session_maker, org_id) -> None:
    """The repair for a club imported before names were matched properly."""
    print("\nRepairing a club imported before names were matched")
    from app.scripts.merge_cricketstatz_duplicates import plan_for_org

    # Recreate the reported state: the club's own record beside the one an
    # earlier import minted for the same person.
    stray = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name, cricketstatz_player_id)
            VALUES (:id, :org, 'Brad Quinsee', '99000001')
        """), {"id": str(stray), "org": str(org_id)})
        held = uuid.uuid4()
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name)
            VALUES (:id, :org, 'Quinsee, Brad')
        """), {"id": str(held), "org": str(org_id)})
        await db.commit()

        plan = await plan_for_org(db, org_id)
        pairs = {(k_name, r_name) for _, k_name, _, r_name in plan}
        check("the reported duplicate is found",
              ("Quinsee, Brad", "Brad Quinsee") in pairs, str(pairs))
        check("the club's own record is the one kept",
              all(k_id != str(stray) for k_id, _, _, _ in plan))
        check("a bare initial is not merged on a guess",
              not any("Crosta" in r for _, _, _, r in plan), str(pairs))
        check("a player with no CricketStatz id is never the one removed",
              all(r_id != str(held) for _, _, r_id, _ in plan))

        await db.execute(text("DELETE FROM players WHERE id IN (:a,:b)"),
                         {"a": str(stray), "b": str(held)})
        await db.commit()


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



# ── the honour board out of a player's own notes ─────────────────────────────

def got(line: str, field: str = None):
    """One field of a classified note, or None when it was not classified.

    A control run in which nothing classifies has to REPORT each check rather
    than raising on the first subscript and saying nothing about the other
    thirty.
    """
    found = classify_note(line)
    if field is None:
        return found
    return (found or {}).get(field)


def verify_notes() -> None:
    print("\nPlayer notes read as awards")

    lines = parse_player_notes(fixture("player_notes_rich.txt"))
    check("every note line is read off the page", len(lines) == 10, str(len(lines)))
    check("the block's own line breaks are the only structure it has",
          lines[0] == "LIFE MEMBER ~ 1969-70", lines[0])
    check("a page with no Notes block reads as none",
          parse_player_notes("<html><body>nothing here</body></html>") == [])

    # "1982-83" is a season; "2011-15" is a stretch of years. The one test is
    # whether the second half is the first plus one.
    check("a consecutive pair is a season", season_label("1982", "83") == "1982/83")
    check("and it holds across the century", season_label("1999", "00") == "1999/00")
    check("a wider pair is not a season", season_label("2011", "15") is None)
    check("nor is one that only looks like it crosses a century",
          season_label("1998", "00") is None)

    life = classify_note("LIFE MEMBER ~ 1992-93")
    check("a life membership is filed as one",
          (life or {}).get("category") == "Life Membership", str(life))
    check("with the season the club gave it", (life or {}).get("season") == "1992/93", str(life))
    check("the bracketed form of the same line reads the same",
          got("LIFE MEMBER (2009-10)", "season") == "2009/10")

    cap = classify_note("A-GRADE CAP AND DEBUT \U0001f9e2 #102 (1982-83)")
    check("a first-grade cap is a milestone",
          (cap or {}).get("subcategory") == "Cap Number", str(cap))
    check("named for the grade it was awarded in",
          (cap or {}).get("achievement") == "A Grade Cap", str(cap))
    check("carrying the cap number", (cap or {}).get("detail") == "#102", str(cap))
    check("the emoji does not ride into the award's name",
          bool(cap) and "\U0001f9e2" not in (cap.get("achievement") or ""),
          str(cap))
    check("the club's other spelling of the same thing reads the same",
          got("'A' GRADE CAP ~ #103 (1982-83)", "achievement") == "A Grade Cap")
    bare = got("A-GRADE CAP AND DEBUT #212")
    check("a cap with no season recorded still reads as a cap",
          bool(bare) and bare["subcategory"] == "Cap Number"
          and bare["season"] is None, str(bare))

    won = classify_note("5x TED GARLAND BATTING AVERAGE WINNER")
    check("a trophy won several times is one award, not five",
          (won or {}).get("times") == 5, str(won))
    check("saying how many times it was won", (won or {}).get("detail") == "Won 5 times", str(won))
    check("under a name a person would recognise",
          (won or {}).get("achievement") == "Ted Garland Batting Average Winner", str(won))
    check("an association's initials are left as the club wrote them",
          got("3x N.M.C.A. TEAM OF THE YEAR", "achievement")
          == "N.M.C.A. Team of the Year")
    check("and so is a name the club cased itself",
          got("4x BILL McFARLANE CLUB CHAMPION", "achievement")
          == "Bill McFarlane Club Champion")

    # An "Nx" prefix means the line is something won N times, which is what
    # separates a team-of-the-year award naming a captain from a captaincy.
    counted = classify_note("2x N.M.C.A. TEAM OF THE YEAR - CAPTAIN")
    check("an award that names a role is still an award",
          (counted or {}).get("category") == "Club Award", str(counted))
    captain = classify_note("INAUGURAL K.P.C.C. 'A' GRADE CAPTAIN (1962-63)")
    check("a captaincy is a role, not a trophy",
          (captain or {}).get("subcategory") == "Captains", str(captain))
    check("filed under the season it was held", (captain or {}).get("season") == "1962/63")

    coach = classify_note("SENIOR HEAD COACH (2011-15, 2023-25)")
    check("a coaching stint is a role", (coach or {}).get("subcategory") == "Coaches",
          str(coach))
    check("recorded across both ends of the stretch",
          ((coach or {}).get("season"), (coach or {}).get("season_end"))
          == ("2011", "2025"), str(coach))
    check("with every stint it names kept",
          (coach or {}).get("detail") == "2011-15, 2023-25", str(coach))
    check("a stint crossing a century ends where it really ended",
          got("SENIOR HEAD COACH (1998-00)", "season_end") == "2000")

    check("the hall of fame is its own honour",
          (classify_note("N.M.C.A. - HALL OF FAME") or {}).get("category")
          == "Hall of Fame")

    # THE ONE THING THIS MUST NOT DO. The same block carries plain biography,
    # and a football career on a cricket club's honour board is worse than
    # reading nothing at all.
    check("a football career is not a cricket honour",
          classify_note("COLLINGWOOD FC (313 Games)") is None)
    check("nor is a two-club one", classify_note("ESSENDON FC / MELBOURNE FC (95/3 Games)") is None)
    check("a playing note is left alone", classify_note("wk") is None)
    check("and so is an empty line", classify_note("   ") is None)


async def verify_award_import(session_maker, org_id, import_id) -> None:
    print("\nThe honour board, written")

    async with session_maker() as db:
        rows = (await db.execute(text("""
            SELECT player_name, category, subcategory, achievement, season,
                   season_end, detail, import_batch_id
              FROM player_achievements WHERE org_id = :org
             ORDER BY player_name, achievement
        """), {"org": str(org_id)})).mappings().all()

    check("the honour board was written", len(rows) == 12, str(len(rows)))
    check("every honour carries the import as its batch",
          all(str(r["import_batch_id"]) == str(import_id) for r in rows))
    check("a player whose notes are biography got no honours at all",
          len({r["player_name"] for r in rows}) == 2,
          str(sorted({r["player_name"] for r in rows})))
    check("the life membership landed",
          any(r["category"] == "Life Membership" and r["season"] == "1969/70"
              for r in rows))
    check("so did the cap, with its number",
          any(r["achievement"] == "A Grade Cap" and r["detail"] == "#1" for r in rows))
    check("and the hall of fame",
          any(r["category"] == "Hall of Fame" for r in rows))
    check("a trophy won thirteen times is one row that says so",
          any(r["detail"] == "Won 13 times" for r in rows), "")

    async with session_maker() as db:
        defs = (await db.execute(text("""
            SELECT category, subcategory, achievement FROM org_award_definitions
             WHERE org_id = :org
        """), {"org": str(org_id)})).mappings().all()
    names = {d["achievement"] for d in defs}
    check("each honour was added to the club's own award catalogue",
          {"Life Membership", "Hall of Fame", "A Grade Cap"} <= names,
          str(sorted(names)))
    check("so a second winner can be picked from the list rather than retyped",
          "Ted Garland Batting Average Winner" in names)

    async with session_maker() as db:
        batch = (await db.execute(text("""
            SELECT filename, created_count, status FROM achievement_import_batches
             WHERE id = :id
        """), {"id": str(import_id)})).mappings().first()
    check("the Awards screen lists it alongside its own imports",
          batch is not None and batch["created_count"] == 12, str(batch))

    # A re-read must not hand anybody a second life membership.
    stub = StubSite()
    real_client = importer.client
    importer.client = stub
    try:
        async with session_maker() as db:
            again = await importer.import_notes(db, org_id, import_id, "93931")
    finally:
        importer.client = real_client
    check("reading the same notes again creates nothing",
          again["awards_created"] == 0, str(again))
    check("and carries none onto a different import either",
          again["awards_carried"] == 0, str(again))
    check("and says what it could not read rather than dropping it silently",
          again["unread"] == 2, str(again))

    async with session_maker() as db:
        total = (await db.execute(text(
            "SELECT COUNT(*) FROM player_achievements WHERE org_id = :org"),
            {"org": str(org_id)})).scalar()
    check("so the honour board is the same size afterwards", total == 12, str(total))



async def verify_synced_overlap(engine, session_maker) -> None:
    """A club that already syncs must not have the same cricket imported twice.

    Reported off a live club: 2,324 imported matches beside ~3,000 synced ones,
    a record board listing every top score twice, and a career reading 14,966
    runs where CricketStatz has 10,444. The import was faithful — the club was
    simply holding the same matches from two sources.
    """
    print("\nA club that already syncs from Cricket Australia")
    org = uuid.uuid4()
    SYNCED_PLAYER = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Keon Park Cricket Club', 'keon-park-2', true)
        """), {"o": str(org)})
        # The club's sync covers 1995 and 2025; nothing before that.
        for year, gid in ((1995, uuid.uuid4()), (2025, uuid.uuid4())):
            sid, grid = uuid.uuid4(), uuid.uuid4()
            await db.execute(text("""
                INSERT INTO seasons (id, organisation_id, name, year)
                VALUES (:s, :o, :n, :y)
            """), {"s": str(sid), "o": str(org), "n": f"Summer {year}/{str(year+1)[2:]}",
                   "y": year})
            await db.execute(text("""
                INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'NMCA - Jika Shield')
            """), {"g": str(grid), "s": str(sid)})
            await db.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team)
                VALUES (:i, :g, CAST(:d AS date), 'Keon Park CC 1st XI', 'Panton Hill')
            """), {"i": str(gid), "g": str(grid), "d": date(year, 11, 5)})
            # Cricket Australia's own season total for the same cricket. Without
            # one the "its season totals go too" check below is vacuous — it
            # would pass with the clause removed.
            await db.execute(text("""
                INSERT INTO players (id, organisation_id, name)
                VALUES (:p, :o, 'Quinsee, Brad') ON CONFLICT (id) DO NOTHING
            """), {"p": str(SYNCED_PLAYER), "o": str(org)})
            await db.execute(text("""
                INSERT INTO player_season_stats
                    (player_id, season_id, matches, runs, batting_innings)
                VALUES (:p, :s, 10, 400, 10)
            """), {"p": str(SYNCED_PLAYER), "s": str(sid)})
        await db.commit()

    async with session_maker() as db:
        covered = await importer.synced_coverage(db, org)
    check("the years the sync already covers are known",
          sorted(covered) == [1995, 2025], str(covered))
    check("and a year it does not reach is not claimed", 1985 not in covered)

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
            """), {"id": str(import_id), "org": str(org)})
            await db.commit()
        await importer.run_import(session_maker, org, import_id, "93931")
    finally:
        importer.client = real_client

    async with session_maker() as db:
        row = (await db.execute(text(
            "SELECT progress FROM cricketstatz_imports WHERE id = :id"),
            {"id": str(import_id)})).scalar() or {}
        years = (await db.execute(text("""
            SELECT DISTINCT s.year FROM manual_games mg
              JOIN seasons s ON s.id = mg.season_id
             WHERE mg.organisation_id = :o ORDER BY s.year
        """), {"o": str(org)})).scalars().all()
    check("the seasons the sync covers are left out",
          sorted(row.get("skipped_synced_years") or []) == [1995, 2025],
          str(row.get("skipped_synced_years")))
    check("so the same match is not counted twice",
          1995 not in years and 2025 not in years, str(years))
    check("and the history the sync cannot reach still comes across",
          1985 in years, str(years))
    check("the club is told which years were left out",
          any("counted twice" in n for n in (row.get("notes") or [])),
          str(row.get("notes")))

    # A club that would rather CricketStatz were the record for those years.
    # The synced side steps aside instead of both being counted.
    stub2 = StubSite()
    importer.client = stub2
    try:
        second = uuid.uuid4()
        async with session_maker() as db:
            await db.execute(text("""
                INSERT INTO cricketstatz_imports
                    (id, organisation_id, club_id, source_url, status, phase)
                VALUES (:id, :org, '93931', 'u', 'running', 'starting')
            """), {"id": str(second), "org": str(org)})
            await db.commit()
        await importer.run_import(session_maker, org, second, "93931",
                                  synced_years="cricketstatz")
    finally:
        importer.client = real_client
    async with session_maker() as db:
        years2 = (await db.execute(text("""
            SELECT DISTINCT s.year FROM manual_games mg
              JOIN seasons s ON s.id = mg.season_id
             WHERE mg.organisation_id = :o ORDER BY s.year
        """), {"o": str(org)})).scalars().all()
        marked = await importer.superseded_years(db, org)
    check("asking for CricketStatz brings those seasons across",
          1995 in years2 and 2025 in years2, str(years2))
    check("and marks them as read from CricketStatz",
          marked == [1995, 2025], str(marked))

    # THE POINT OF THE WHOLE THING: the synced side must stop being counted.
    async with session_maker() as db:
        synced_left = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_games
             WHERE organisation_id = :o AND source = 'api'
        """), {"o": str(org)})).scalar()
        imported_shown = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_games
             WHERE organisation_id = :o AND source = 'manual'
        """), {"o": str(org)})).scalar()
        raw_synced = (await db.execute(text(
            "SELECT COUNT(*) FROM games")))
        raw_synced = raw_synced.scalar()
    check("the synced games for those seasons stop being counted",
          synced_left == 0, str(synced_left))
    check("while the imported ones are", imported_shown > 0, str(imported_shown))
    check("and nothing was deleted — the club's synced data is still there",
          raw_synced == 2, str(raw_synced))

    # Cricket Australia's own season totals go with them, or a career would
    # still be counted from both.
    async with session_maker() as db:
        api_rows = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_player_season_stats pss
              JOIN seasons s ON s.id = pss.season_id
             WHERE s.organisation_id = :o AND pss.source = 'api'
        """), {"o": str(org)})).scalar()
    check("and so do Cricket Australia's own season totals for them",
          api_rows == 0, str(api_rows))
    async with session_maker() as db:
        raw_pss = (await db.execute(text(
            "SELECT COUNT(*) FROM player_season_stats"))).scalar()
    check("those totals are kept too, just not counted", raw_pss == 2, str(raw_pss))

    # Handing them back is instant — nothing has to be re-pulled.
    async with session_maker() as db:
        cleared = await importer.clear_seasons_superseded(db, org)
        await db.commit()
    async with session_maker() as db:
        back = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_games
             WHERE organisation_id = :o AND source = 'api'
        """), {"o": str(org)})).scalar()
    check("handing the seasons back counts the synced games again",
          cleared == 2 and back == 2, f"cleared={cleared} shown={back}")

    # A club with no sync at all is untouched by any of this.
    fresh = uuid.uuid4()
    async with session_maker() as db:
        covered_none = await importer.synced_coverage(db, fresh)
    check("a club that has never synced has nothing to skip", covered_none == {})


async def verify_undo(session_maker, org_id, import_id, player_count) -> None:
    print("\nUndo")
    async with session_maker() as db:
        result = await importer.undo_import(db, org_id, import_id)
        check("every match the import wrote was removed",
              result["matches_removed"] == 4, str(result))
        check("the record book was removed with it",
              result["records_removed"] == 3, str(result))
        check("and the honour board it read out of the notes",
              result["awards_removed"] == 12, str(result))

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
        left_awards = (await db.execute(text(
            "SELECT COUNT(*) FROM player_achievements WHERE org_id = :org"),
            {"org": str(org_id)})).scalar()
        check("no honour is left behind", left_awards == 0, str(left_awards))
        undone = (await db.execute(text("""
            SELECT status FROM achievement_import_batches WHERE id = :id
        """), {"id": str(import_id)})).scalar()
        check("the Awards screen shows the batch as undone", undone == "undone", str(undone))
        kept_defs = (await db.execute(text(
            "SELECT COUNT(*) FROM org_award_definitions WHERE org_id = :org"),
            {"org": str(org_id)})).scalar()
        check("the award catalogue is kept — a trophy is not the import's to unmake",
              kept_defs > 0, str(kept_defs))


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
    verify_notes()

    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # The awards tables are created by the app's lifespan in raw SQL, not
        # by the ORM, so `create_all` does not know about them. Copied from
        # main.py column for column — a harness table that merely looks right
        # is worse than none.
        for statement in AWARD_DDL:
            await conn.execute(text(statement))

    await verify_schema(engine)
    org_id, import_id, players = await verify_import(engine, session_maker)
    await verify_award_import(session_maker, org_id, import_id)
    await verify_synced_overlap(engine, session_maker)
    await verify_repair(session_maker, org_id)
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
