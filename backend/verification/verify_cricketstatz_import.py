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
try:  # A CONTROL RUN MUST REPORT, NOT CRASH — the feature may be absent.
    from app.services import match_pairing  # noqa: E402
except ImportError:  # pragma: no cover - control runs only
    match_pairing = None
from app.services.cricketstatz_ddl import DOWNGRADE, STATEMENTS  # noqa: E402
from app.services import superseded_ddl as importer_ddl  # noqa: E402
from app.services.superseded_ddl import DOWNGRADE as SUPERSEDED_DOWNGRADE  # noqa: E402
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




async def verify_migration_287_applies(engine) -> None:
    """287 must apply to a database that is at 286, not to an empty one.

    `CREATE OR REPLACE VIEW` cannot drop a column, so re-issuing an OLDER
    definition of a view aborts the migration — and the container runs
    `alembic upgrade head && uvicorn`, so a failed migration means the API
    never starts. The first cut took `v_effective_games` from migration 169,
    which predates the `status` column 266 added, and took production down.

    A suite that builds the views from 287's own SQL cannot catch that: it has
    to build them the way the migrations leave them FIRST, which is what
    `_view_ddl` is for.
    """
    print("\nMigration 287 against a database at 286")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _view_ddl import view_statements

    async with engine.begin() as conn:
        await conn.execute(text("DROP VIEW IF EXISTS v_effective_games CASCADE"))
        # Production's games.raw_payload is jsonb; the ORM model says JSON, so a
        # create_all harness needs reconciling before the migrations' own views
        # will build. The app is unaffected.
        await conn.execute(text(
            "ALTER TABLE games ALTER COLUMN raw_payload TYPE jsonb "
            "USING raw_payload::text::jsonb"))
        for _name, sql in view_statements():
            await conn.execute(text(sql))
    before = await _view_columns(engine, "v_effective_games")
    check("the database is at 286 with every migrated view in place",
          "status" in before, str(sorted(before)))

    # Three times: alembic runs it once and the lifespan mirror re-runs the
    # whole list on every boot. Caught rather than raised — a migration that
    # aborts IS the outage, and a control run has to report it rather than kill
    # the suite and say nothing about the other checks.
    failure = None
    try:
        for _ in range(3):
            async with engine.begin() as conn:
                for statement in SUPERSEDED_DDL:
                    await conn.execute(text(statement))
    except Exception as exc:
        failure = str(exc).splitlines()[0][:160]
    check("287 applies three times without error", failure is None, failure or "")
    after = await _view_columns(engine, "v_effective_games")
    check("and drops no column the view already had",
          before <= after, str(sorted(before - after)))
    async with engine.begin() as conn:
        await conn.execute(text("SELECT COUNT(*) FROM v_effective_player_season_stats"))
    check("both views are still readable afterwards", True)


async def _view_columns(engine, view: str) -> set:
    async with engine.begin() as conn:
        return set((await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = :v
        """), {"v": view})).scalars().all())



async def _source_of(session_maker, season_id):
    """What the season records as its source — the whole invariant in one read."""
    async with session_maker() as db:
        return (await db.execute(text(
            "SELECT stats_source FROM seasons WHERE id = :s"),
            {"s": str(season_id)})).scalar()


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

    # A club that brings those years across as well. THE TWO SOURCES ARE
    # UNIONED: a match both hold is counted once, and a match only one holds is
    # still counted — the whole point of pairing per match rather than picking
    # a winner per season.
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
    check("asking for CricketStatz brings those seasons across",
          1995 in years2 and 2025 in years2, str(years2))

    # NOT ONE SEASON IS MARKED. The marker chose a winner for a whole season,
    # which is how the club lost every match the losing source alone held.
    async with session_maker() as db:
        marked = await importer.superseded_years(db, org)
    check("and marks no season as read from one source or the other",
          marked == [], str(marked))

    # THE POINT OF THE WHOLE THING: every match counted, exactly once.
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
            "SELECT COUNT(*) FROM games"))).scalar()
        raw_manual = (await db.execute(text("""
            SELECT COUNT(*) FROM manual_games WHERE organisation_id = :o
        """), {"o": str(org)})).scalar()
        paired = (await db.execute(text("""
            SELECT COUNT(*) FROM manual_games
             WHERE organisation_id = :o AND superseded_by_game_id IS NOT NULL
        """), {"o": str(org)})).scalar()
    check("the club's own synced games are still counted",
          synced_left == 2, str(synced_left))
    check("the imported matches are counted alongside them",
          imported_shown > 0, str(imported_shown))
    check("and every match is counted exactly once",
          synced_left + imported_shown == raw_synced + raw_manual - paired,
          f"api={synced_left} manual={imported_shown} raw={raw_synced}+{raw_manual} "
          f"paired={paired}")
    check("nothing was deleted — the club's synced data is still there",
          raw_synced == 2, str(raw_synced))

    # CRICKET AUSTRALIA'S OWN SEASON TOTALS ARE ALWAYS COUNTED. They cover CA's
    # matches and nothing else, and a CricketStatz match that is the same match
    # is paired away before its scorecard is rolled up, so the two halves add
    # to a union rather than to a double count.
    async with session_maker() as db:
        api_rows = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_player_season_stats pss
              JOIN seasons s ON s.id = pss.season_id
             WHERE s.organisation_id = :o AND pss.source = 'api'
        """), {"o": str(org)})).scalar()
        raw_pss = (await db.execute(text(
            "SELECT COUNT(*) FROM player_season_stats"))).scalar()
    check("Cricket Australia's own season totals are never suppressed",
          api_rows == 2, str(api_rows))
    check("and they are all still stored", raw_pss == 2, str(raw_pss))

    # A club with no sync at all is untouched by any of this.
    fresh = uuid.uuid4()
    async with session_maker() as db:
        covered_none = await importer.synced_coverage(db, fresh)
    check("a club that has never synced has nothing to skip", covered_none == {})

    # MID-RUN, A SEASON ALREADY WALKED MUST NOT BE COUNTED TWICE. Pairing
    # every season only at the END leaves each finished season reading its
    # duplicates from BOTH sources for as long as the rest of the import takes
    # — reported off a live record board as duplicate high scores.
    #
    # The run is cut off part way by refusing a scorecard from the LAST season
    # in the plan (oldest first, so 1985 then 1995 then 2025) — a real network
    # failure, the one exception `run_import` re-raises rather than noting.
    stub3 = StubSite()
    last_season_matches = {"3177313", "3082300"}

    async def refuse_last_season(club_id, match_id):
        if str(match_id) in last_season_matches:
            raise importer.CricketStatzError("stopped part way")
        return await StubSite.fetch_scorecard(stub3, club_id, match_id)
    stub3.fetch_scorecard = refuse_last_season
    importer.client = stub3

    third = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            UPDATE manual_games SET superseded_by_game_id = NULL,
                                    pair_prefers_import = false
             WHERE organisation_id = :o
        """), {"o": str(org)})
        # A synced game that IS one of the imported matches (the 1985 card,
        # the first season the run walks). Without a real duplicate in the
        # fixture there is nothing for a mid-run pass to find, and the check
        # below would pass whenever it was run.
        early_season = (await db.execute(text("""
            SELECT id FROM seasons WHERE organisation_id = :o AND year = 1985
        """), {"o": str(org)})).scalar()
        early_grade = uuid.uuid4()
        await db.execute(text("""
            INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'A-GRADE')
        """), {"g": str(early_grade), "s": str(early_season)})
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Keon Park CC', 'A-Grade Oakhill')
        """), {"i": str(uuid.uuid4()), "g": str(early_grade),
               "d": date(1985, 11, 2)})
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:id, :org, '93931', 'u', 'running', 'starting')
        """), {"id": str(third), "org": str(org)})
        await db.commit()
    try:
        await importer.run_import(session_maker, org, third, "93931",
                                  synced_years="cricketstatz")
    finally:
        importer.client = real_client

    async def _paired_years(o):
        async with session_maker() as db:
            return set((await db.execute(text("""
                SELECT DISTINCT s.year FROM manual_games mg
                  JOIN seasons s ON s.id = mg.season_id
                 WHERE mg.organisation_id = :o
                   AND mg.superseded_by_game_id IS NOT NULL
            """), {"o": str(o)})).scalars().all())

    async with session_maker() as db:
        status3 = (await db.execute(text(
            "SELECT status FROM cricketstatz_imports WHERE id = :i"),
            {"i": str(third)})).scalar()
    part_paired = await _paired_years(org)
    check("the part-way run really did stop", status3 == "error", str(status3))
    check("a season already walked is paired before the run moves on",
          1985 in part_paired, str(part_paired))
    check("and a season the run never reached has nothing paired",
          2025 not in part_paired, str(part_paired))

    # UNDOING AN IMPORT TAKES ITS PAIRS WITH IT. Where the synced game had
    # stepped aside for a better imported copy of the same match, removing that
    # copy has to bring the synced one straight back — the "neither source"
    # state reached from the other end.
    undo_org = uuid.uuid4()
    imp_a, imp_b = uuid.uuid4(), uuid.uuid4()
    kept_player = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Undo Test CC', 'undo-test-cc', true)
        """), {"o": str(undo_org)})
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name)
            VALUES (:p, :o, 'Kept Player')
        """), {"p": str(kept_player), "o": str(undo_org)})
        for imp in (imp_a, imp_b):
            await db.execute(text("""
                INSERT INTO cricketstatz_imports
                    (id, organisation_id, club_id, source_url, status, phase)
                VALUES (:id, :o, '93931', 'u', 'complete', 'done')
            """), {"id": str(imp), "o": str(undo_org)})
        # A synced fixture with NO scorecard of ours behind it, and an imported
        # copy of the same match that HAS one. The import is the better record
        # of that match, so the synced game steps aside for it.
        for year, imps in ((1995, (imp_a,)), (2025, (imp_b,))):
            sid, grid, gid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await db.execute(text("""
                INSERT INTO seasons (id, organisation_id, name, year)
                VALUES (:s, :o, :n, :y)
            """), {"s": str(sid), "o": str(undo_org),
                   "n": f"Summer {year}/{str(year+1)[2:]}", "y": year})
            await db.execute(text("""
                INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'A-GRADE')
            """), {"g": str(grid), "s": str(sid)})
            await db.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team)
                VALUES (:i, :g, CAST(:d AS date), 'Undo Test CC', 'Panton Hill')
            """), {"i": str(gid), "g": str(grid), "d": date(year, 11, 5)})
            for imp in imps:
                mgid = uuid.uuid4()
                await db.execute(text("""
                    INSERT INTO manual_games
                        (id, organisation_id, season_id, played_at, opposition,
                         cricketstatz_import_id, cricketstatz_match_id)
                    VALUES (:i, :o, :s, CAST(:d AS date), 'Panton Hill', :imp, :mid)
                """), {"i": str(mgid), "o": str(undo_org), "s": str(sid),
                       "d": date(year, 11, 5), "imp": str(imp),
                       "mid": f"undo-{year}"})
                await db.execute(text("""
                    INSERT INTO manual_batting_innings
                        (manual_game_id, player_id, innings_number, runs,
                         did_not_bat, not_out)
                    VALUES (:g, :p, 1, 44, false, false)
                """), {"g": str(mgid), "p": str(kept_player)})
        await db.commit()

    async with session_maker() as db:
        pair_stats = await match_pairing.reconcile_org(db, undo_org)
    check("both matches are paired to the synced fixture they duplicate",
          pair_stats["paired"] == 2, str(pair_stats))
    check("and the imported half wins, since it holds the scorecard",
          pair_stats["prefer_import"] == 2, str(pair_stats))

    async def _counted(o, source):
        async with session_maker() as db:
            return (await db.execute(text("""
                SELECT COUNT(*) FROM v_effective_games
                 WHERE organisation_id = :o AND source = :s
            """), {"o": str(o), "s": source})).scalar()

    check("so the synced fixtures step aside rather than being counted twice",
          await _counted(undo_org, "api") == 0
          and await _counted(undo_org, "manual") == 2,
          f"api={await _counted(undo_org, 'api')} "
          f"manual={await _counted(undo_org, 'manual')}")

    async with session_maker() as db:
        undone = await importer.undo_import(db, undo_org, imp_a)
    async with session_maker() as db:
        counted = (await db.execute(text("""
            SELECT s.year FROM v_effective_games g
              JOIN seasons s ON s.id = g.season_id
             WHERE g.organisation_id = :o AND g.source = 'api'
        """), {"o": str(undo_org)})).scalars().all()
    check("undoing brings back the synced game its import had replaced",
          list(counted) == [1995], str(counted))
    check("and the other import's match still counts for itself",
          await _counted(undo_org, "manual") == 1,
          str(await _counted(undo_org, "manual")))
    check("the undo says how much it removed",
          undone.get("matches_removed") == 1, str(undone))

    # RE-DERIVING MOVES A GAME FROM ONE IMPORTED MATCH TO ANOTHER, and the
    # unique index allows one imported match per synced game. Reported live:
    # every run after the first died on that index and wrote NOTHING, leaving
    # the club counting both its sources —
    #   duplicate key value violates unique constraint
    #   "uq_manual_games_superseded_by_game"
    # — because the new holder's write landed while the old one still carried
    # it. The fix is to clear every changing row before setting any of them.
    swap_org, swap_imp = uuid.uuid4(), uuid.uuid4()
    swap_season, swap_grade = uuid.uuid4(), uuid.uuid4()
    g_one, g_two = uuid.uuid4(), uuid.uuid4()
    m_one, m_two = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Swap Test CC', 'swap-test-cc', true)
        """), {"o": str(swap_org)})
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:i, :o, '93931', 'u', 'complete', 'done')
        """), {"i": str(swap_imp), "o": str(swap_org)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2002/03', 2002)
        """), {"s": str(swap_season), "o": str(swap_org)})
        await db.execute(text(
            "INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'A')"),
            {"g": str(swap_grade), "s": str(swap_season)})
        for gid, day, opp in ((g_one, date(2002, 11, 2), 'Panton Hill'),
                              (g_two, date(2002, 11, 9), 'Epping')):
            await db.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team,
                                   opp_club_name)
                VALUES (:i, :g, CAST(:d AS date), 'Swap Test CC', :o, :o)
            """), {"i": str(gid), "g": str(swap_grade), "d": day, "o": opp})
        # Written the WRONG way round, as a run with an older matcher would
        # leave them: each imported match holds the other's game.
        for mid, day, opp, held in ((m_one, date(2002, 11, 2), 'Panton Hill', g_two),
                                    (m_two, date(2002, 11, 9), 'Epping', g_one)):
            await db.execute(text("""
                INSERT INTO manual_games
                    (id, organisation_id, season_id, grade_id, played_at,
                     home_team, away_team, opposition, cricketstatz_import_id,
                     cricketstatz_match_id, superseded_by_game_id)
                VALUES (:i, :o, :s, :g, CAST(:d AS date), 'Swap Test CC', :opp,
                        :opp, :imp, :mid, :held)
            """), {"i": str(mid), "o": str(swap_org), "s": str(swap_season),
                   "g": str(swap_grade), "d": day, "opp": opp,
                   "imp": str(swap_imp), "mid": f"swap-{opp}", "held": str(held)})
        await db.commit()

    swap_error = None
    try:
        async with session_maker() as db:
            swapped = await match_pairing.reconcile_org(db, swap_org)
    except Exception as exc:
        swap_error = f"{type(exc).__name__}: {exc}"
        swapped = {}
    check("re-deriving a pairing that moves a game does not die on the index",
          swap_error is None, str(swap_error))
    async with session_maker() as db:
        held_now = {
            str(r["id"]): str(r["pair"]) if r["pair"] else None
            for r in (await db.execute(text("""
                SELECT id, superseded_by_game_id AS pair FROM manual_games
                 WHERE organisation_id = :o
            """), {"o": str(swap_org)})).mappings()
        }
    check("and each imported match ends on its own synced game",
          held_now.get(str(m_one)) == str(g_one)
          and held_now.get(str(m_two)) == str(g_two), str(held_now))
    check("with both still counted once",
          swapped.get("paired") == 2, str(swapped))

    # A CLUSTER NOTHING CAN TELL APART IS PAIRED OFF, AND IT HAS TO LAND THE
    # SAME WAY EVERY TIME. Four of our sides out on one Saturday against one
    # club, no scorecards on either side, no side marker in any name: every
    # combination scores identically, so which imported match takes which
    # synced game is decided purely by the order equally-scored candidates are
    # walked in. That order followed frozenset iteration, which is not stable
    # between processes — so the nightly pass re-paired the cluster and wrote
    # rows for nothing, night after night. The ids are the final tiebreak now.
    tie_org, tie_imp = uuid.uuid4(), uuid.uuid4()
    tie_season, tie_grade = uuid.uuid4(), uuid.uuid4()
    tie_games = [uuid.uuid4() for _ in range(4)]
    tie_manual = [uuid.uuid4() for _ in range(4)]
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Tie Test CC', 'tie-test-cc', true)
        """), {"o": str(tie_org)})
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:i, :o, '93931', 'u', 'complete', 'done')
        """), {"i": str(tie_imp), "o": str(tie_org)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2004/05', 2004)
        """), {"s": str(tie_season), "o": str(tie_org)})
        await db.execute(text(
            "INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'A')"),
            {"g": str(tie_grade), "s": str(tie_season)})
        for gid in tie_games:
            await db.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team,
                                   opp_club_name)
                VALUES (:i, :g, CAST(:d AS date), 'Tie Test CC', 'Reservoir',
                        'Reservoir')
            """), {"i": str(gid), "g": str(tie_grade), "d": date(2004, 12, 4)})
        for n, mid in enumerate(tie_manual):
            await db.execute(text("""
                INSERT INTO manual_games
                    (id, organisation_id, season_id, grade_id, played_at,
                     home_team, away_team, opposition, cricketstatz_import_id,
                     cricketstatz_match_id)
                VALUES (:i, :o, :s, :g, CAST(:d AS date), 'Tie Test CC',
                        'Reservoir', 'Reservoir', :imp, :mid)
            """), {"i": str(mid), "o": str(tie_org), "s": str(tie_season),
                   "g": str(tie_grade), "d": date(2004, 12, 4),
                   "imp": str(tie_imp), "mid": f"tie-{n}"})
        await db.commit()

    async def _tie_pairs():
        async with session_maker() as db:
            res = await match_pairing.reconcile_org(db, tie_org)
        async with session_maker() as db:
            rows = (await db.execute(text("""
                SELECT id, superseded_by_game_id AS pair FROM manual_games
                 WHERE organisation_id = :o
            """), {"o": str(tie_org)})).mappings()
            held = {str(r["id"]): str(r["pair"]) if r["pair"] else None
                    for r in rows}
        return res, held

    first_res, first_held = await _tie_pairs()
    second_res, second_held = await _tie_pairs()
    third_res, third_held = await _tie_pairs()
    check("every match of an indistinguishable cluster is still counted once",
          first_res.get("paired") == 4
          and len({v for v in first_held.values() if v}) == 4,
          f"{first_res} {first_held}")
    check("the first pass writes the cluster",
          first_res.get("changed") == 4, str(first_res))
    check("and a second pass writes nothing at all",
          second_res.get("changed") == 0, str(second_res))
    check("nor a third",
          third_res.get("changed") == 0, str(third_res))
    check("the assignment is the same every time",
          first_held == second_held == third_held,
          f"{first_held} {second_held} {third_held}")

    # THE REPORTED FAILURE, REPLAYED. The overlap used to be worked out ONCE at
    # the start of the run: a club whose synced games were not in `games` at
    # that moment (a Full Rebuild still running, a sync that had not landed)
    # read as having no overlap at all, and once the synced side arrived the
    # club counted BOTH. Live: every shared season holding exactly synced +
    # imported, a career at 14,966 against CricketStatz's 10,444. The pairing
    # RE-DERIVES rather than accumulating, so the pass that runs after a full
    # sync is what settles it.
    late = uuid.uuid4()
    late_imp = uuid.uuid4()
    late_season, late_grade = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Late Sync CC', 'late-sync-cc', true)
        """), {"o": str(late)})
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:i, :o, '93931', 'u', 'complete', 'done')
        """), {"i": str(late_imp), "o": str(late)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2002/03', 2002)
        """), {"s": str(late_season), "o": str(late)})
        await db.execute(text("""
            INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'A-GRADE')
        """), {"g": str(late_grade), "s": str(late_season)})
        # The import writes its match while the club holds NO synced games —
        # so the old overlap check would have found nothing to mark.
        await db.execute(text("""
            INSERT INTO manual_games
                (id, organisation_id, season_id, played_at, opposition,
                 cricketstatz_import_id)
            VALUES (:i, :o, :s, CAST(:d AS date), 'Panton Hill', :imp)
        """), {"i": str(uuid.uuid4()), "o": str(late), "s": str(late_season),
               "d": date(2002, 11, 5), "imp": str(late_imp)})
        await db.commit()

    # THE SCHEMA MUST MATCH THE CODE, AND THE ONLY WAY TO KNOW IS TO READ IT
    # BACK. Found live: 73 seasons marked and the view carrying no clause to
    # act on them, with alembic reporting the migration applied.
    async with engine.begin() as conn:
        before = await importer_ddl.verify(conn)
        # A view without the clause is REPORTED, not raised on — a boot check
        # must never be the thing that stops the app.
        await conn.execute(text("""
            CREATE OR REPLACE VIEW v_effective_games AS
            SELECT g.id, g.grade_id, g.played_at, g.home_team, g.away_team,
                   g.home_club, g.away_club, g.opp_org_id, g.opp_club_name,
                   g.result, g.winning_team, g.is_final, g.raw_payload,
                   g.venue, g.match_format, 'api'::text AS source,
                   g.home_org_id, g.away_org_id, gr.season_id AS season_id,
                   s.organisation_id AS organisation_id, g.status AS status
              FROM games g
              LEFT JOIN grades gr ON gr.id = g.grade_id
              LEFT JOIN seasons s ON s.id = gr.season_id
        """))
        stale = await importer_ddl.verify(conn)
        for statement in SUPERSEDED_DDL:
            await conn.execute(text(statement))
        after = await importer_ddl.verify(conn)
    # MIGRATION 291 GAVE `manual_batting_innings` ITS OWN `caught_behind`, and
    # this module re-issues that view LAST in the lifespan — so selecting NULL
    # there would silently revert someone else's feature on every boot.
    batting = next(st for st in SUPERSEDED_DDL
                   if "VIEW v_effective_batting_innings" in st)
    check("the batting view keeps 291's manual caught_behind",
          "NULL::boolean AS caught_behind" not in batting
          and batting.count("caught_behind") >= 2, batting[-400:])

    check("a view carrying its pairing clause is reported as sound",
          all(before.values()), str(before))
    check("a view that has lost it is caught rather than assumed",
          stale.get("v_effective_games") is False, str(stale))
    check("and applying the shipped statements puts it back",
          all(after.values()), str(after))

    async with engine.begin() as conn:
        for statement in SUPERSEDED_DDL:
            await conn.execute(text(statement))

    # NOW the synced side arrives — a Full Rebuild finishing, or the next sync.
    # Nothing was paired when the import ran, because there was nothing to pair
    # to; the pass that runs after a full sync is what finds it.
    late_game = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Late Sync CC', 'Panton Hill')
        """), {"i": str(late_game), "g": str(late_grade),
               "d": date(2002, 11, 5)})
        await db.commit()

    async def _late_sources():
        async with session_maker() as db:
            rows = (await db.execute(text("""
                SELECT source, COUNT(*) FROM v_effective_games
                 WHERE organisation_id = :o GROUP BY source
            """), {"o": str(late)})).all()
        return {r[0]: r[1] for r in rows}

    before_pass = await _late_sources()
    check("a sync landing after an import is counted twice until it is paired",
          before_pass.get("api", 0) == 1 and before_pass.get("manual", 0) == 1,
          str(before_pass))

    async with session_maker() as db:
        late_pairs = await match_pairing.reconcile_org(db, late)
    after_pass = await _late_sources()
    check("the pass that follows a full sync finds the pair",
          late_pairs["paired"] == 1, str(late_pairs))
    check("so the match is counted once, from Cricket Australia",
          after_pass.get("api", 0) == 1 and after_pass.get("manual", 0) == 0,
          str(after_pass))
    check("and nothing was deleted to do it",
          (await _raw_count(session_maker,
                            "SELECT COUNT(*) FROM manual_games "
                            "WHERE organisation_id = :o", late)) == 1)

    # RUNNING IT AGAIN IS RUNNING IT ONCE.
    async with session_maker() as db:
        again = await match_pairing.reconcile_org(db, late)
    check("a second pass changes nothing",
          again["changed"] == 0 and again["paired"] == 1, str(again))

    # AND A MATCH ONLY CRICKETSTATZ HAS IS STILL COUNTED. This is the whole
    # difference from choosing a winner per season: the season is shared, and
    # the match Cricket Australia does not have still reaches the club's
    # records.
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO manual_games
                (id, organisation_id, season_id, played_at, opposition,
                 cricketstatz_import_id)
            VALUES (:i, :o, :s, CAST(:d AS date), 'Bundoora United', :imp)
        """), {"i": str(uuid.uuid4()), "o": str(late), "s": str(late_season),
               "d": date(2002, 12, 14), "imp": str(late_imp)})
        await db.commit()
    async with session_maker() as db:
        with_gap = await match_pairing.reconcile_org(db, late)
    gap_sources = await _late_sources()
    check("a match only CricketStatz has is left unpaired",
          with_gap["only_cricketstatz"] == 1, str(with_gap))
    check("and it is counted alongside the synced one, not instead of it",
          gap_sources.get("api", 0) == 1 and gap_sources.get("manual", 0) == 1,
          str(gap_sources))

    # AND A MATCH ONLY CRICKET AUSTRALIA HAS IS STILL COUNTED. The season-level
    # rule lost exactly this — it hid the club's whole synced side.
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Late Sync CC', 'Epping')
        """), {"i": str(uuid.uuid4()), "g": str(late_grade),
               "d": date(2003, 1, 18)})
        await db.commit()
    async with session_maker() as db:
        both_ways = await match_pairing.reconcile_org(db, late)
    both_sources = await _late_sources()
    check("a match only Cricket Australia has is left unpaired too",
          both_ways["only_synced"] == 1, str(both_ways))
    check("so the club ends with the union of the two, each match once",
          both_sources.get("api", 0) == 2 and both_sources.get("manual", 0) == 1,
          str(both_sources))


async def _raw_count(session_maker, sql, org) -> int:
    async with session_maker() as db:
        return (await db.execute(text(sql), {"o": str(org)})).scalar()


def verify_matcher() -> None:
    """The rules that decide two records are one match. No database needed.

    The whole union rests on this: a pair we miss is a match counted twice, and
    a pair we invent is a match that disappears. Both directions are checked.
    """
    print("\nWhich two records are one match")
    if match_pairing is None:
        check("services/match_pairing.py is present", False,
              "the matcher is absent — every pairing check below "
              "is reported rather than run")
        return
    MR = match_pairing.MatchRow

    def card(*pairs):
        return frozenset(pairs)

    # THE SCORECARD CARRIES THE PAIRS A DATE CANNOT. A two-day match is dated
    # by one source under the day it started and the other under the day it
    # finished — measured on real data at a week apart, and the reason a date
    # key alone paired only about two thirds of them.
    a = MR("i1", date(2003, 3, 1), "Croxton", card(("p1", 87), ("p2", 12), ("p3", 40)))
    b = MR("g1", date(2003, 3, 8), "Fairfield", card(("p1", 87), ("p2", 12), ("p3", 40)))
    check("three batters with the same scores are one match, whatever the date",
          match_pairing.score_pair(a, b) is not None)

    # AND THE DATE CARRIES THE SEASONS THERE ARE NO SCORECARDS FOR.
    c = MR("i2", date(2003, 3, 1), "Croxton Park CC")
    d = MR("g2", date(2003, 3, 1), "Croxton Park Cricket Club")
    check("the same day against the same club is one match with no cards at all",
          match_pairing.score_pair(c, d) is not None)

    e = MR("i3", date(2003, 3, 1), "Epping")
    check("the same day against a different club is not",
          match_pairing.score_pair(e, d) is None)

    f = MR("i4", date(2003, 3, 4), "Croxton", card(("p1", 87)))
    f2 = MR("g4", date(2003, 3, 1), "Croxton Park Cricket Club", card(("p1", 87)))
    check("one shared score, the same club and a few days apart is one match",
          match_pairing.score_pair(f, f2) is not None)

    g = MR("i5", date(2003, 3, 4), "Croxton", card(("p9", 3)))
    h = MR("g5", date(2003, 3, 6), "Northcote", card(("p9", 3), ("p8", 21)))
    check("two shared scores close together stand on their own",
          match_pairing.score_pair(
              MR("i5", date(2003, 3, 4), "Croxton", card(("p9", 3), ("p8", 21))),
              h) is not None)
    check("but one shared score against a club named differently is not enough",
          match_pairing.score_pair(g, h) is None)

    far = MR("g6", date(2004, 3, 1), "Croxton")
    check("the same club a year apart is two different matches",
          match_pairing.score_pair(c, far) is None)

    # ONE SYNCED GAME TAKES AT MOST ONE IMPORTED MATCH.
    twin1 = MR("i7", date(2003, 3, 1), "Croxton", card(("p1", 87), ("p2", 12), ("p3", 40)))
    twin2 = MR("i8", date(2003, 3, 1), "Croxton", card(("p1", 87), ("p2", 12), ("p3", 40)))
    one = MR("g7", date(2003, 3, 1), "Croxton", card(("p1", 87), ("p2", 12), ("p3", 40)))
    both = match_pairing.assign([twin1, twin2], [one])
    check("two imported matches cannot both take the same synced game",
          len(both) == 1, str(both))

    # OUR OWN CLUB'S NAME MUST NEVER BE WHAT MAKES TWO RECORDS AGREE. The
    # reported bug: both sides of every candidate carry it, so comparing the
    # raw team names made every pair look identical, the whole Saturday read as
    # one fixture, and 6 of a real season's 86 matches paired. Measured on that
    # same live season, this takes it to 77 before a single card is read.
    club = match_pairing.team_tokens("Keon Park Cricket Club")
    ours, opp = match_pairing.split_sides(
        "Keon Park 3rd-XI", "Sumner Colts 'D'", "", club)
    check("our own side and the opposition are told apart",
          ours == "Keon Park 3rd-XI" and opp == "Sumner Colts 'D'", f"{ours}|{opp}")
    ours2, opp2 = match_pairing.split_sides(
        "Rosebank", "Keon Park", "", club)
    check("whichever way round the fixture is written",
          ours2 == "Keon Park" and opp2 == "Rosebank", f"{ours2}|{opp2}")
    check("and a stored opposition is taken at its word",
          match_pairing.split_sides("A v B", "Keon Park U12", "Cameron U12",
                                    club)[1] == "Cameron U12")

    # ONE SHARED WORD IS NOT A CLUB. A real Saturday: Preston Trinity, Preston
    # Druids, Preston YCW and West Preston are four different clubs.
    check("two clubs sharing one word are not the same club",
          not match_pairing.teams_agree("Preston Trinity", "Preston Druids"))
    check("but a name contained in the other is",
          match_pairing.teams_agree("Preston YCW 'B'",
                                    "Preston YCW District 2nd XI"))
    check("and an age group is not what tells two clubs apart",
          match_pairing.teams_agree("Preston U17 Trinity", "Preston Trinity"))

    # OUR 2nd XI's MATCH IS NEVER OUR 1st XI's, however well everything else
    # agrees — which is what separates the two fixtures a club plays against
    # one opposition on one day.
    check("our own side's number is read from either spelling",
          match_pairing.side_marker("Keon Park 2nd-XI") == "xi2"
          and match_pairing.side_marker("Keon Park 2nd XI") == "xi2"
          and match_pairing.side_marker("Keon Park 1's 'A-Grade'") == "xi1"
          and match_pairing.side_marker("Keon Park U17") == "u17"
          and match_pairing.side_marker("Keon Park") is None)
    # A GRADE LETTER IS NEVER READ AS A TEAM NUMBER: this club's 3rd XI plays
    # D Grade and its 4th plays E, so mapping the letters would pair the wrong
    # fixtures.
    check("a grade letter is not read as a team number",
          match_pairing.side_marker("Keon Park 'D-Grade'") is None)
    firsts = MR("iF", date(2003, 1, 25), "Kingsbury", ours="Keon Park 1's 'A-Grade'")
    seconds_syn = MR("gS", date(2003, 1, 25), "Kingsbury 2nd XI", ours="Keon Park 2nd XI")
    check("our firsts' match is never paired to our seconds'",
          match_pairing.score_pair(firsts, seconds_syn) is None)
    both = match_pairing.assign(
        [firsts, MR("iS", date(2003, 1, 25), "Kingsbury 'B'", ours="Keon Park 2nd-XI")],
        [seconds_syn, MR("gF", date(2003, 1, 25), "Kingsbury", ours="Keon Park")])
    check("so each of our sides takes its own fixture",
          both.get("iF", ("",))[0] == "gF" and both.get("iS", ("",))[0] == "gS",
          str(both))

    # A CLUSTER THAT CANNOT BE TOLD APART IS PAIRED OFF, NOT REFUSED. Cricket
    # Australia writes both of a Saturday's fixtures as a bare "Keon Park", so
    # refusing every such tie left a real season reading 149 games against a
    # true ~117. Pairing them off gets the count right whichever way round.
    cluster = match_pairing.assign(
        [MR("iX", date(2011, 11, 11), "Brunswick"),
         MR("iY", date(2011, 11, 11), "Brunswick")],
        [MR("gX", date(2011, 11, 11), "Brunswick"),
         MR("gY", date(2011, 11, 11), "Brunswick")])
    check("two fixtures nothing can tell apart are still counted once each",
          len(cluster) == 2 and len(set(g for g, _ in cluster.values())) == 2,
          str(cluster))

    # WHICH HALF OF THE PAIR COUNTS.
    thin = match_pairing.assign(
        [MR("iC", date(2003, 3, 1), "Croxton", card(("p1", 87)))],
        [MR("gC", date(2003, 3, 1), "Croxton")])
    check("the imported half wins where the synced game has no card of ours",
          thin.get("iC", (None, False))[1] is True, str(thin))
    fat = match_pairing.assign(
        [MR("iD", date(2003, 3, 1), "Croxton", card(("p1", 87)))],
        [MR("gD", date(2003, 3, 1), "Croxton", card(("p1", 87)))])
    check("and Cricket Australia wins wherever it holds one too",
          fat.get("iD", (None, True))[1] is False, str(fat))

    # A team name is only ever a supporting signal, so it is forgiving — but
    # never on the strength of a word that says nothing about which club.
    check("a club spelled two ways reads as one club",
          match_pairing.teams_agree("Panton Hill CC", "Panton Hill Cricket Club"))
    check("two different clubs do not",
          not match_pairing.teams_agree("Panton Hill", "Epping"))
    check("and a shared grade word is not a club",
          not match_pairing.teams_agree("1st XI", "2nd XI"))

    # THE ASSIGNMENT MUST NOT DEPEND ON THE ORDER THE ROWS ARRIVE IN. Four of
    # our sides out on one Saturday against one club, no cards either side:
    # every combination scores identically, so which imported match takes which
    # synced game came down to the order equally-scored candidates were walked
    # in — which followed frozenset iteration and is not stable between
    # processes. Reported as a nightly pass that wrote rows every run: 302 the
    # first time, 2 more the next, for ever. The ids are the final tiebreak now.
    #
    # Shuffling the inputs is what makes this fail against the old code: the
    # sort was stable, so a tie kept whatever order it was given.
    day = date(2004, 12, 4)
    tie_i = [MR(f"ti{n}", day, "Reservoir") for n in range(4)]
    tie_g = [MR(f"tg{n}", day, "Reservoir") for n in range(4)]
    forward = match_pairing.assign(tie_i, tie_g)
    backward = match_pairing.assign(list(reversed(tie_i)), list(reversed(tie_g)))
    rotated = match_pairing.assign(tie_i[1:] + tie_i[:1], tie_g[2:] + tie_g[:2])
    check("a cluster nothing can tell apart is still paired off, one for one",
          len(forward) == 4 and len({g for g, _ in forward.values()}) == 4,
          str(forward))
    check("and the same rows in any order give the same assignment",
          forward == backward == rotated,
          f"{forward} {backward} {rotated}")

    # THE PAIRING HAS TO BE WIRED IN, not merely written. A pass nothing calls
    # leaves a club counting both sources with nothing on screen to say so.
    root = Path(__file__).resolve().parent.parent / "app"
    main_src = (root / "main.py").read_text()
    check("the boot re-derives the pairing for a club that holds an import",
          "match_pairing" in main_src and "_run_match_pairing_sweep" in main_src)
    orgs_src = (root / "routers" / "organisations.py").read_text()
    admin_src = (root / "routers" / "club_admin.py").read_text()
    check("a full sync re-derives it once its own matches have landed",
          "match_pairing.reconcile_org" in orgs_src)
    check("and so does a Full Rebuild", "match_pairing.reconcile_org" in admin_src)
    import_src = (root / "services" / "cricketstatz_import.py").read_text()
    check("an import pairs each season as its own matches land",
          import_src.count("match_pairing.reconcile_org") >= 2, )
    # Matched on the WRITE, not on the column name — `superseded_years` still
    # READS it so the screen can say the marker no longer decides anything, and
    # a check that matched any mention would fail against correct code.
    # THE PASS MUST SURVIVE A BOOT THAT NEVER REACHED IT. Reported live: the
    # code was deployed, correct, and nothing was paired — a club counting both
    # its sources with nothing on screen to say so. A silent log could not tell
    # "ran and found nothing" from "never ran".
    sched = (root / "jobs" / "scheduler.py").read_text()
    check("a nightly pass retries the pairing",
          "pair_all_imported_matches" in sched
          and "nightly_match_pairing" in sched)
    check("the boot sweep is held, not just started — a bare create_task can "
          "be collected before it runs",
          "_BACKGROUND_TASKS.add" in main_src)
    check("and it says what it did whether or not anything changed",
          'logger.info("Match pairing for %s: %s", _org, res)' in main_src)

    # A CARD QUERY BOUND TO THE CLUB'S PLAYERS ALONE SCANS THE WHOLE PLATFORM'S
    # `batting_innings`, which is slow enough to be killed by a statement
    # timeout — and a pairing pass that dies there is a club counting twice.
    pairing_src = (root / "services" / "match_pairing.py").read_text()
    check("both card queries are bound to the games already loaded",
          all("= ANY(CAST(:ids AS UUID[]))" in pairing_src.split(const, 1)[1][:600]
              for const in ("_SYNCED_CARD_SQL = ", "_IMPORTED_CARD_SQL = ")),
          "a card query is not bound to an id list")
    check("and the matching itself runs off the event loop",
          "asyncio.to_thread(assign" in pairing_src)

    check("and nothing marks a season as read from one source any more",
          "SET stats_source = 'cricketstatz'" not in import_src
          and "season.stats_source =" not in import_src,
          "the retired season-level marker is still being written")


async def verify_per_innings_source(session_maker) -> None:
    """One innings, one source. Reported live off the record boards.

    `v_effective_games` and `v_effective_player_season_stats` were filtered by
    migration 287; the six PER-INNINGS views were not. So for a season read
    from CricketStatz both the synced innings and the imported innings were
    present, and every century, wicket and catch was counted twice — a record
    board listing the same 270 for the same player in the same season, and a
    career reading 14,806 runs.
    """
    print("\nOne innings, one source")
    org, player = uuid.uuid4(), uuid.uuid4()
    season, ca_grade = uuid.uuid4(), uuid.uuid4()
    game, mgame = uuid.uuid4(), uuid.uuid4()
    imp = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Innings Test CC', 'innings-test-cc', true)
        """), {"o": str(org)})
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:i, :o, '93931', 'u', 'complete', 'done')
        """), {"i": str(imp), "o": str(org)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2002/03', 2002)
        """), {"s": str(season), "o": str(org)})
        await db.execute(text(
            "INSERT INTO grades (id, season_id, name) VALUES (:g, :s, 'NMCA - Jika Shield')"),
            {"g": str(ca_grade), "s": str(season)})
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name)
            VALUES (:p, :o, 'Shephard, Heath')
        """), {"p": str(player), "o": str(org)})
        # The same innings from both sources: 270, one season, one player.
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Innings Test CC', 'Panton Hill')
        """), {"i": str(game), "g": str(ca_grade), "d": date(2002, 11, 5)})
        await db.execute(text("""
            INSERT INTO batting_innings
                (game_id, player_id, innings_number, runs, not_out, did_not_bat)
            VALUES (:g, :p, 1, 270, false, false)
        """), {"g": str(game), "p": str(player)})
        # A synced row in every other per-innings table too, or the checks
        # below assert 0 against a table that was empty anyway and could never
        # have failed.
        await db.execute(text("""
            INSERT INTO bowling_spells (game_id, player_id, innings_number,
                                        overs, maidens, runs, wickets)
            VALUES (:g, :p, 1, 10.0, 2, 30, 3)
        """), {"g": str(game), "p": str(player)})
        await db.execute(text("""
            INSERT INTO fielding_stats (game_id, player_id, catches)
            VALUES (:g, :p, 2)
        """), {"g": str(game), "p": str(player)})
        await db.execute(text("""
            INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number,
                                         score_at_fall, player_id)
            VALUES (:g, 1, 1, 40, :p)
        """), {"g": str(game), "p": str(player)})
        await db.execute(text("""
            INSERT INTO partnerships (game_id, innings_number, wicket_number,
                                      batter1_id, runs, is_club_innings)
            VALUES (:g, 1, 1, :p, 40, true)
        """), {"g": str(game), "p": str(player)})
        await db.execute(text("""
            INSERT INTO bowler_wickets (game_id, innings_number, bowler_id,
                                        batter_name, dismissal_type)
            VALUES (:g, 1, :p, 'A Batter', 'bowled')
        """), {"g": str(game), "p": str(player)})
        await db.execute(text("""
            INSERT INTO manual_games
                (id, organisation_id, season_id, grade_id, played_at, opposition,
                 cricketstatz_import_id)
            VALUES (:i, :o, :s, :gr, CAST(:d AS date), 'Panton Hill', :imp)
        """), {"i": str(mgame), "o": str(org), "s": str(season),
               "gr": str(ca_grade), "d": date(2002, 11, 5), "imp": str(imp)})
        await db.execute(text("""
            INSERT INTO manual_batting_innings
                (manual_game_id, player_id, innings_number, runs, not_out, did_not_bat)
            VALUES (:g, :p, 1, 270, false, false)
        """), {"g": str(mgame), "p": str(player)})
        await db.commit()

    async def innings_rows():
        async with session_maker() as db:
            return (await db.execute(text("""
                SELECT source, COUNT(*) FROM v_effective_batting_innings
                 WHERE player_id = :p GROUP BY source
            """), {"p": str(player)})).all()

    both = {r[0]: r[1] for r in await innings_rows()}
    check("before pairing, a club holding the same match twice sees both",
          both.get("api", 0) == 1 and both.get("manual", 0) == 1, str(both))

    async with session_maker() as db:
        paired = await match_pairing.reconcile_org(db, org)
    check("the two records of one match are recognised as one",
          paired["paired"] == 1, str(paired))
    once = {r[0]: r[1] for r in await innings_rows()}
    check("so the innings is counted once, from Cricket Australia",
          once.get("api", 0) == 1 and once.get("manual", 0) == 0, str(once))

    # The same rule on every per-innings view, not just batting: the IMPORTED
    # side steps aside, and the synced rows are all still there.
    async with session_maker() as db:
        for view in ("v_effective_bowling_spells", "v_effective_fielding_stats",
                     "v_effective_fall_of_wickets", "v_effective_partnerships",
                     "v_effective_bowler_wickets"):
            n = (await db.execute(text(
                f"SELECT COUNT(*) FROM {view} WHERE game_id = :g"),
                {"g": str(game)})).scalar()
            check(f"{view} keeps the synced side", n == 1, str(n))
        gone = (await db.execute(text(
            "SELECT COUNT(*) FROM v_effective_batting_innings WHERE game_id = :g"),
            {"g": str(mgame)})).scalar()
    check("and the imported copy of that innings is not counted again",
          gone == 0, str(gone))

    # WHERE THE SYNCED GAME HAS NO CARD, THE IMPORT IS THE BETTER RECORD.
    # "If PlayHQ is incomplete, use CricketStatz to complete" — decided per
    # match, not per season.
    thin_game, thin_manual = uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Innings Test CC', 'Epping')
        """), {"i": str(thin_game), "g": str(ca_grade), "d": date(2003, 1, 11)})
        await db.execute(text("""
            INSERT INTO manual_games
                (id, organisation_id, season_id, grade_id, played_at, opposition,
                 cricketstatz_import_id)
            VALUES (:i, :o, :s, :gr, CAST(:d AS date), 'Epping', :imp)
        """), {"i": str(thin_manual), "o": str(org), "s": str(season),
               "gr": str(ca_grade), "d": date(2003, 1, 11), "imp": str(imp)})
        await db.execute(text("""
            INSERT INTO manual_batting_innings
                (manual_game_id, player_id, innings_number, runs, not_out, did_not_bat)
            VALUES (:g, :p, 1, 88, false, false)
        """), {"g": str(thin_manual), "p": str(player)})
        await db.commit()
    async with session_maker() as db:
        thin = await match_pairing.reconcile_org(db, org)
        kept_side = (await db.execute(text("""
            SELECT source, COUNT(*) FROM v_effective_games
             WHERE organisation_id = :o AND played_at = CAST(:d AS date)
             GROUP BY source
        """), {"o": str(org), "d": date(2003, 1, 11)})).all()
        card = (await db.execute(text("""
            SELECT COUNT(*) FROM v_effective_batting_innings WHERE game_id = :g
        """), {"g": str(thin_manual)})).scalar()
    sides = {r[0]: r[1] for r in kept_side}
    check("a synced fixture with no card of ours prefers the imported copy",
          thin["prefer_import"] == 1, str(thin))
    check("so that match is counted once, from CricketStatz",
          sides.get("manual", 0) == 1 and sides.get("api", 0) == 0, str(sides))
    check("and its scorecard is the one that reaches the club's figures",
          card == 1, str(card))

    # An innings on a game with NO grade is kept — a manual upload need not
    # have one, and an inner join would drop it silently.
    loose_game = uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO manual_games (id, organisation_id, season_id, played_at,
                                      opposition)
            VALUES (:i, :o, :s, CAST(:d AS date), 'Panton Hill')
        """), {"i": str(loose_game), "o": str(org), "s": str(season),
               "d": date(2002, 12, 1)})
        await db.execute(text("""
            INSERT INTO manual_batting_innings
                (manual_game_id, player_id, innings_number, runs, not_out, did_not_bat)
            VALUES (:g, :p, 1, 44, false, false)
        """), {"g": str(loose_game), "p": str(player)})
        await db.commit()
        kept = (await db.execute(text(
            "SELECT COUNT(*) FROM v_effective_batting_innings WHERE game_id = :g"),
            {"g": str(loose_game)})).scalar()
    check("an innings whose game has no grade is kept, not dropped",
          kept == 1, str(kept))


async def verify_per_grade_aggregate(session_maker) -> None:
    """The by-grade grid reads the union, never one match from two sources.

    Reported live: a career grid showing 28 matches for 2002/03 where
    CricketStatz has 14 — every shared season exactly doubled — while the
    career header two inches above it was correct.
    `player_season_grade_stats` is Cricket Australia's OWN per-grade aggregate
    and the effective views do not cover it; the two sources also file the same
    cricket under different grade names ("NMCA - Jika Shield" against
    "A-GRADE"), so the grid's own max(held, claimed) never compares them.

    The pairing is what settles it, and it settles it in the RIGHT direction:
    CA's per-grade figure is counted in full, and only the imported matches CA
    does not have are added beside it. Suppressing CA's rows for the season —
    what the season-level marker did — read as 0 here and lost every match only
    Cricket Australia had.
    """
    print("\nCricket Australia's per-grade rows")
    # Lifespan-created raw SQL, so `create_all` never makes it. Copied from
    # main.py column for column, per the house rule about harness tables.
    async with session_maker() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                undone_at TIMESTAMPTZ
            )
        """))
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ
            )
        """))
        await db.commit()
    org, player = uuid.uuid4(), uuid.uuid4()
    season, ca_grade, cs_grade = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Grid Test CC', 'grid-test-cc', true)
        """), {"o": str(org)})
        await db.execute(text("""
            INSERT INTO seasons (id, organisation_id, name, year)
            VALUES (:s, :o, 'Summer 2002/03', 2002)
        """), {"s": str(season), "o": str(org)})
        for gid, name in ((ca_grade, "NMCA - Jika Shield"), (cs_grade, "A-GRADE")):
            await db.execute(text(
                "INSERT INTO grades (id, season_id, name) VALUES (:g, :s, :n)"),
                {"g": str(gid), "s": str(season), "n": name})
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name)
            VALUES (:p, :o, 'Quinsee, Brad')
        """), {"p": str(player), "o": str(org)})
        # Cricket Australia's own per-grade figure for the season.
        await db.execute(text("""
            INSERT INTO player_season_grade_stats
                (player_id, season_id, grade_id, matches)
            VALUES (:p, :s, :g, 14)
        """), {"p": str(player), "s": str(season), "g": str(ca_grade)})
        await db.commit()

    from app.services import aggregations as agg
    async with session_maker() as db:
        before = await agg.get_player_team_breakdown(db, str(player), str(org))
    total_before = sum(r["matches"] for r in before["rows"])
    check("with only Cricket Australia's rows the grid reads its figure",
          total_before == 14, str(total_before))

    # NOW THE CLUB IMPORTS THAT SEASON TOO. One imported match is the same
    # match as a synced game; the other is one Cricket Australia does not have.
    imp = uuid.uuid4()
    synced_game, twin, only_cs = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO cricketstatz_imports
                (id, organisation_id, club_id, source_url, status, phase)
            VALUES (:i, :o, '93931', 'u', 'complete', 'done')
        """), {"i": str(imp), "o": str(org)})
        await db.execute(text("""
            INSERT INTO games (id, grade_id, played_at, home_team, away_team)
            VALUES (:i, :g, CAST(:d AS date), 'Grid Test CC', 'Panton Hill')
        """), {"i": str(synced_game), "g": str(ca_grade), "d": date(2002, 11, 5)})
        await db.execute(text("""
            INSERT INTO batting_innings
                (game_id, player_id, innings_number, runs, not_out, did_not_bat)
            VALUES (:g, :p, 1, 61, false, false)
        """), {"g": str(synced_game), "p": str(player)})
        for mid, day, opp, runs in ((twin, date(2002, 11, 5), 'Panton Hill', 61),
                                    (only_cs, date(2002, 12, 14), 'Bundoora', 30)):
            await db.execute(text("""
                INSERT INTO manual_games
                    (id, organisation_id, season_id, grade_id, played_at,
                     opposition, cricketstatz_import_id)
                VALUES (:i, :o, :s, :gr, CAST(:d AS date), :opp, :imp)
            """), {"i": str(mid), "o": str(org), "s": str(season),
                   "gr": str(cs_grade), "d": day, "opp": opp, "imp": str(imp)})
            await db.execute(text("""
                INSERT INTO manual_batting_innings
                    (manual_game_id, player_id, innings_number, runs,
                     not_out, did_not_bat)
                VALUES (:g, :p, 1, :r, false, false)
            """), {"g": str(mid), "p": str(player), "r": runs})
        await db.commit()

    async with session_maker() as db:
        pairs = await match_pairing.reconcile_org(db, org)
    check("the imported twin is paired and the gap match is not",
          pairs["paired"] == 1 and pairs["only_cricketstatz"] == 1, str(pairs))

    async with session_maker() as db:
        after = await agg.get_player_team_breakdown(db, str(player), str(org))
    cells = {r["grade_name"]: r["matches"] for r in after["rows"]}
    check("Cricket Australia's own per-grade figure is still counted in full",
          cells.get("NMCA - Jika Shield") == 14, str(cells))
    check("and only the match it does not have is added beside it",
          cells.get("A-GRADE") == 1, str(cells))
    check("so the grid reads the union, never the two records of one match",
          sum(r["matches"] for r in after["rows"]) == 15, str(cells))


async def verify_notes_pass(engine, session_maker, org_id, import_id) -> None:
    """The honour board on its own, without re-pulling a single scorecard.

    The notes pass is the LAST phase of an import, so it is the first thing a
    run loses when it is cut off — reported live: a club whose whole history
    imported and whose every player read zero honours.
    """
    print("\nThe honour board on its own")
    async with session_maker() as db:
        await db.execute(text(
            "DELETE FROM player_achievements WHERE import_batch_id = :i"),
            {"i": str(import_id)})
        await db.commit()
        gone = (await db.execute(text(
            "SELECT COUNT(*) FROM player_achievements WHERE import_batch_id = :i"),
            {"i": str(import_id)})).scalar()
    check("a club that lost its honour board has none", gone == 0, str(gone))

    real_client = importer.client
    stub = StubSite()
    importer.client = stub
    before_cards = stub.scorecard_calls
    try:
        await importer.run_notes_pass(session_maker, org_id, import_id, "93931")
    finally:
        importer.client = real_client

    async with session_maker() as db:
        made = (await db.execute(text(
            "SELECT COUNT(*) FROM player_achievements WHERE import_batch_id = :i"),
            {"i": str(import_id)})).scalar()
        state = (await db.execute(text(
            "SELECT status, phase FROM cricketstatz_imports WHERE id = :i"),
            {"i": str(import_id)})).first()
    check("running the notes pass alone puts it back", made == 12, str(made))
    check("and re-pulls no scorecards to do it",
          stub.scorecard_calls == before_cards,
          f"{before_cards} → {stub.scorecard_calls}")
    check("the run reports itself finished", tuple(state) == ("complete", "done"),
          str(state))

    # It reuses the import's own batch, so undoing that import still takes them.
    async with session_maker() as db:
        batched = (await db.execute(text("""
            SELECT COUNT(*) FROM player_achievements
             WHERE org_id = :o AND import_batch_id = :i
        """), {"o": str(org_id), "i": str(import_id)})).scalar()
    check("filed under the import's own batch, so undo still removes them",
          batched == made, f"{batched} of {made}")

    # A second pass over a club whose notes are already read adds nothing.
    importer.client = StubSite()
    try:
        await importer.run_notes_pass(session_maker, org_id, import_id, "93931")
    finally:
        importer.client = real_client
    async with session_maker() as db:
        again = (await db.execute(text(
            "SELECT COUNT(*) FROM player_achievements WHERE import_batch_id = :i"),
            {"i": str(import_id)})).scalar()
    check("a second pass re-stamps rather than duplicating", again == made,
          f"{again} vs {made}")


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
        # 287's downgrade FIRST, and the order is not incidental: its views
        # read manual_games.cricketstatz_import_id, so dropping 285's column
        # while they still stand fails on the dependency. Alembic unwinds
        # newest-first for exactly this reason; the suite has to as well.
        for statement in SUPERSEDED_DOWNGRADE:
            await conn.execute(text(statement))
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
    await verify_migration_287_applies(engine)
    await verify_synced_overlap(engine, session_maker)
    await verify_repair(session_maker, org_id)
    await verify_heartbeat(session_maker, org_id)
    verify_matcher()
    await verify_per_innings_source(session_maker)
    await verify_per_grade_aggregate(session_maker)
    await verify_notes_pass(engine, session_maker, org_id, import_id)
    await verify_undo(session_maker, org_id, import_id, players)
    await verify_downgrade(engine)
    await engine.dispose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name in FAIL:
        print(f"  FAILED: {name}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
