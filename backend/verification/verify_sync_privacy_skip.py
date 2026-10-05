"""Verification: a sync never collects for a person who asked to be removed. Real Postgres.

A person who asks to be removed is hidden (migration 316), and a suppression keeps a new
row for them hidden. That stops them being SHOWN. It did not stop them being COLLECTED: the
next sync still wrote their season totals, their batting, bowling and fielding, and kept
their name as text on fall-of-wicket, partnership, fielding and bowler-wicket rows. A Full
Rebuild wiped their games and wrote all of it back.

Runs the SHIPPED `sync.sync_organisation` (season aggregates, per-grade aggregates, then the
scorecard pass), with the Cricket Australia client stubbed at its two seams
(`playhq_client.*` and `grassroots_scores_client.*`). Synthetic names and ids only.

The club has:
  KEEP    an ordinary player. The control: everything about them must still be collected.
  REMY    asked to be removed: hidden at request, suppression recorded.
  FILLIN  on the team sheet with no `players` row, so the sync keeps their name as text.

Cases, each paired with a check that the thing COULD be present (rule 21):
  1  season totals and per-grade totals are not written for REMY (KEEP's are)
  2  no batting / bowling / fielding / appearance / partnership / fall-of-wicket id for REMY
  3  REMY's name is on no text column (fielding, fall of wickets, partnerships, bowler wickets);
     the wicket itself stays in the card, and FILLIN's name is still kept (the pairing)
  4  an old participant id merged into REMY does not land a game line on REMY
  5  a team-sheet entry with an id the club never stored, but REMY's full name, is not
     attached to REMY by name
  6  a second club's sync creates NO row at all for REMY (it used to create a hidden one)
  7  a club that hid a player with `is_public` alone (no request) is still collected
  8  the club's own record of the game survives (the game, KEEP's lines, the opposition's)

CONTROL (`--control`): run the same file from a checkout of the commit before this change
(see CONTROL_REV). It must fail exactly the checks above and nothing that is not about
collection.

Run:  DATABASE_URL=postgresql+asyncpg://root@/sync_privacy_test?host=/var/run/postgresql \
      python verification/verify_sync_privacy_skip.py [--control]
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Organisation, Player
from app.services import grassroots_scores_client as gr
from app.services import playhq_client
from app.services import sync as sync_mod
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL

Session, check = base.Session, base.check
CONTROL = "--control" in sys.argv
CONTROL_REV = "853a7e7"       # the commit before sync learned to skip suppressed people

TODAY = date.today()
ORG_A, ORG_B, OPP = (uuid.uuid4() for _ in range(3))
SEASON, GRADE = str(uuid.uuid4()), str(uuid.uuid4())
KEEP, REMY, CLUBHID, OLD_OWNER = (uuid.uuid4() for _ in range(4))
G_KEEP, G_REMY, G_CLUBHID, G_FILLIN = (str(uuid.uuid4()) for _ in range(4))
G_REMY_OLD, G_REMY_NEWREG, G_OPP, G_OPP2 = (str(uuid.uuid4()) for _ in range(4))
M1, M2, M3, M4 = (str(uuid.uuid4()) for _ in range(4))

REMY_FULL = "Remy Removed"
REMY_SHORT = "R Removed"


def team_sheet(players):
    return [{"participantId": g, "playerShortName": n} for g, n in players]


def card(match_id, ours_first, mode="main"):
    """One scorecard. M1: our side bats and REMY plays for us. M2: REMY bats for the OPPOSITION.
    M3: only an OLD id that was merged into REMY. M4: only a new id that carries REMY's full name.
    (Kept apart: in the old code two ids landing on one person in one innings broke a unique
    constraint and rolled the whole game back, which would have hidden every other check.)"""
    if mode in ("merge", "byname"):
        extra = (G_REMY_OLD, "R Removed", 5) if mode == "merge" else (G_REMY_NEWREG, REMY_FULL, 7)
        c = {
            "id": match_id, "grade": {"id": GRADE, "name": "Firsts"}, "venue": {"name": "Test Oval"},
            "matchSchedule": [{"startDateTime": f"{(TODAY - timedelta(days=20 if mode == 'merge' else 25)).isoformat()}T00:00:00Z"}],
            "matchSummary": {"resultText": "Alpha won by 10 runs",
                             "teams": [{"id": "t1", "isHome": True, "displayName": "Alpha - 1s", "isWinner": True},
                                       {"id": "t2", "isHome": False, "displayName": "Opp - 1s"}]},
            "teams": [
                {"id": "t1", "displayName": "Alpha - 1s", "owningOrganisation": {"id": str(ORG_A), "name": "Alpha CC"},
                 "players": team_sheet([(G_KEEP, "K Keep"), (extra[0], extra[1])])},
                {"id": "t2", "displayName": "Opp - 1s", "owningOrganisation": {"id": str(OPP), "name": "Opp CC"},
                 "players": team_sheet([(G_OPP, "O Opp")])},
            ],
            "innings": [{
                "inningsOrder": 1, "inningsNumber": 1, "battingTeamId": "t1",
                "batting": [
                    {"participantId": G_KEEP, "playerShortName": "K Keep", "batOrder": 1, "runsScored": 20, "ballsFaced": 25,
                     "dismissalTypeId": 1, "dismissalType": "Not Out"},
                    {"participantId": extra[0], "playerShortName": extra[1], "batOrder": 2, "runsScored": extra[2],
                     "ballsFaced": 8, "dismissalTypeId": 1, "dismissalType": "Not Out"},
                ],
                "bowling": [], "fielding": [], "fallOfWickets": [],
            }],
        }
        return c
    if ours_first:
        ours = team_sheet([(G_KEEP, "K Keep"), (G_REMY, REMY_SHORT), (G_FILLIN, "F Fillin"),
                           (G_CLUBHID, "C Clubhid")])
        opp = team_sheet([(G_OPP, "O Opp")])
    else:
        ours = team_sheet([(G_KEEP, "K Keep"), (G_CLUBHID, "C Clubhid")])
        opp = team_sheet([(G_OPP, "O Opp"), (G_REMY, REMY_SHORT)])
    c = {
        "id": match_id,
        "grade": {"id": GRADE, "name": "Firsts"},
        "venue": {"name": "Test Oval"},
        "matchSchedule": [{"startDateTime": f"{(TODAY - timedelta(days=10 if ours_first else 5)).isoformat()}T00:00:00Z"}],
        "matchSummary": {"resultText": "Alpha won by 10 runs",
                         "teams": [{"id": "t1", "isHome": True, "displayName": "Alpha - 1s", "isWinner": True},
                                   {"id": "t2", "isHome": False, "displayName": "Opp - 1s"}]},
        "teams": [
            {"id": "t1", "displayName": "Alpha - 1s", "owningOrganisation": {"id": str(ORG_A), "name": "Alpha CC"},
             "players": ours},
            {"id": "t2", "displayName": "Opp - 1s", "owningOrganisation": {"id": str(OPP), "name": "Opp CC"},
             "players": opp},
        ],
    }
    if ours_first:
        c["innings"] = [{
            "inningsOrder": 1, "inningsNumber": 1, "battingTeamId": "t1",
            "batting": [
                {"participantId": G_KEEP, "playerShortName": "K Keep", "batOrder": 1, "runsScored": 31, "ballsFaced": 40,
                 "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b O Opp"},
                {"participantId": G_REMY, "playerShortName": REMY_SHORT, "batOrder": 2, "runsScored": 22, "ballsFaced": 30,
                 "dismissalTypeId": 2, "dismissalType": "Caught", "dismissalText": "c O Opp b O Opp"},
                {"participantId": G_FILLIN, "playerShortName": "F Fillin", "batOrder": 3, "runsScored": 9, "ballsFaced": 12,
                 "dismissalTypeId": 1, "dismissalType": "Not Out"},
                {"participantId": G_CLUBHID, "playerShortName": "C Clubhid", "batOrder": 6, "runsScored": 3, "ballsFaced": 4,
                 "dismissalTypeId": 1, "dismissalType": "Not Out"},
            ],
            "bowling": [],
            "fielding": [],
            "fallOfWickets": [
                {"participantId": G_KEEP, "playerShortName": "K Keep", "order": 1, "runs": 33},
                {"participantId": G_REMY, "playerShortName": REMY_SHORT, "order": 2, "runs": 58},
            ],
        }, {
            "inningsOrder": 2, "inningsNumber": 1, "battingTeamId": "t2",
            "batting": [
                {"participantId": G_OPP, "playerShortName": "O Opp", "batOrder": 1, "runsScored": 12, "ballsFaced": 20,
                 "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b R Removed"},
            ],
            "bowling": [
                {"participantId": G_REMY, "playerShortName": REMY_SHORT, "bowlOrder": 1, "oversBowled": 8, "maidensBowled": 1,
                 "runsConceded": 30, "wicketsTaken": 1, "wideBalls": 0, "noBalls": 0, "economy": "3.75"},
                {"participantId": G_KEEP, "playerShortName": "K Keep", "bowlOrder": 2, "oversBowled": 6, "maidensBowled": 0,
                 "runsConceded": 25, "wicketsTaken": 0, "economy": "4.17"},
            ],
            "fielding": [
                {"participantId": G_REMY, "playerShortName": REMY_SHORT, "totalCatches": 1, "wicketKeeperCatches": 0},
                {"participantId": G_FILLIN, "playerShortName": "F Fillin", "totalCatches": 1, "wicketKeeperCatches": 0},
                {"participantId": G_KEEP, "playerShortName": "K Keep", "totalCatches": 2, "wicketKeeperCatches": 0},
            ],
            "fallOfWickets": [{"participantId": G_OPP, "playerShortName": "O Opp", "order": 1, "runs": 12}],
        }]
    else:
        # REMY bats for the opposition and is bowled by KEEP: a wicket on our bowler's record.
        c["innings"] = [{
            "inningsOrder": 1, "inningsNumber": 1, "battingTeamId": "t2",
            "batting": [
                {"participantId": G_OPP, "playerShortName": "O Opp", "batOrder": 1, "runsScored": 4, "ballsFaced": 9,
                 "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b K Keep"},
                {"participantId": G_REMY, "playerShortName": REMY_SHORT, "batOrder": 2, "runsScored": 40, "ballsFaced": 50,
                 "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b K Keep"},
            ],
            "bowling": [{"participantId": G_KEEP, "playerShortName": "K Keep", "bowlOrder": 1, "oversBowled": 9,
                         "maidensBowled": 2, "runsConceded": 40, "wicketsTaken": 2, "economy": "4.44"}],
            "fielding": [],
            "fallOfWickets": [{"participantId": G_OPP, "playerShortName": "O Opp", "order": 1, "runs": 6},
                              {"participantId": G_REMY, "playerShortName": REMY_SHORT, "order": 2, "runs": 90}],
        }]
    return c


CARDS = {M1: card(M1, True), M2: card(M2, False), M3: card(M3, False, "merge"), M4: card(M4, False, "byname")}


def match_item(mid, days_ago):
    return {"id": mid, "status": "COMPLETED", "matchType": "One Day", "round": {"name": "Round 1"},
            "matchSchedule": [{"startDateTime": f"{(TODAY - timedelta(days=days_ago)).isoformat()}T00:00:00Z"}],
            "teams": [{"owningOrganisation": {"id": str(ORG_A), "name": "Alpha CC"}, "displayName": "Alpha - 1s"},
                      {"owningOrganisation": {"id": str(OPP), "name": "Opp CC"}, "displayName": "Opp - 1s"}]}


def stat_row(guid, name, runs):
    return {"id": guid, "name": name, "shortName": name,
            "statistics": {"matches": 4, "battingInnings": 4, "battingAggregate": runs, "battingNotOuts": 1,
                           "bowlingInnings": 2, "bowlingWickets": 3, "bowlingBalls": 60, "bowlingRuns": 40,
                           "fieldingTotalCatches": 2}}


FEED = [stat_row(G_KEEP, "Keep, Kay", 120), stat_row(G_REMY, REMY_FULL, 200), stat_row(G_CLUBHID, "Clubhid, Cam", 15)]


async def stub_org(org_id):
    return {"id": org_id, "name": "Alpha CC" if org_id == str(ORG_A) else "Bravo CC", "shortName": ""}


async def stub_phq_id(*a, **k):
    return None


async def stub_seasons(org_id):
    return [{"id": SEASON, "name": "Summer", "startDate": f"{TODAY.year}-01-01"}]


async def stub_teams(org_id, season_id):
    return [{"id": str(uuid.uuid4()), "grades": [{"id": GRADE, "name": "Firsts"}]}]


async def stub_stats(org_id, season_id, grade_id=None):
    return FEED


async def stub_empty_stats(org_id, season_id, grade_id=None):
    return []


async def stub_grade_matches(grade_guid, *a, **k):
    return [match_item(M1, 10), match_item(M2, 5), match_item(M3, 20), match_item(M4, 25)]


async def stub_scorecard(match_id, *a, **k):
    return CARDS.get(str(match_id))


def install_stubs() -> None:
    playhq_client.get_organisation = stub_org
    playhq_client.lookup_playhq_id = stub_phq_id
    playhq_client.get_seasons = stub_seasons
    playhq_client.get_teams = stub_teams
    playhq_client.get_batting_stats = stub_stats
    playhq_client.get_bowling_stats = stub_empty_stats
    playhq_client.get_fielding_stats = stub_empty_stats
    gr.get_grade_matches = stub_grade_matches
    gr.get_match_scorecard = stub_scorecard


async def seed() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID, keep_player_id UUID, keep_player_name TEXT,
            removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
            canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    async with Session() as s:
        s.add_all([Organisation(id=ORG_A, name="Alpha CC", slug="alpha", is_active=True),
                   Organisation(id=ORG_B, name="Bravo CC", slug="bravo", is_active=True)])
        await s.flush()
        s.add_all([
            Player(id=uuid.UUID(G_KEEP), name="Keep, Kay", organisation_id=ORG_A, grassroots_id=G_KEEP),
            Player(id=uuid.UUID(G_REMY), name="Removed, Remy", organisation_id=ORG_A, grassroots_id=G_REMY,
                   is_public=False),
            # The club hid this one itself, with the display switch only. Still collected.
            Player(id=uuid.UUID(G_CLUBHID), name="Clubhid, Cam", organisation_id=ORG_A, grassroots_id=G_CLUBHID,
                   is_public=False),
            # An older record of the same person that was merged into REMY.
            Player(id=OLD_OWNER, name="Removed, R", organisation_id=ORG_A, grassroots_id=G_REMY_OLD),
        ])
        await s.flush()
        await s.execute(text("""UPDATE players SET privacy_hidden_at = NOW(), privacy_hidden_by = 'test',
                                   privacy_hidden_reason = 'asked to be removed' WHERE id = :p"""), {"p": uuid.UUID(G_REMY)})
        await s.execute(text("INSERT INTO player_privacy_suppressions (grassroots_id, reason, created_by) "
                             "VALUES (:g, 'asked to be removed', 'test')"), {"g": G_REMY})
        await s.execute(text("INSERT INTO merge_logs (org_id, keep_player_id, keep_player_name, removed_player_id, "
                             "removed_player_name) VALUES (:o, :k, 'Removed, Remy', :r, 'Removed, R')"),
                        {"o": ORG_A, "k": uuid.UUID(G_REMY), "r": OLD_OWNER})
        await s.commit()
    # The merge map is keyed on the removed player's id; sync reads the removed GUID as that id.
    async with Session() as s:
        await s.execute(text("UPDATE merge_logs SET removed_player_id = :r"), {"r": uuid.UUID(G_REMY_OLD)})
        await s.execute(text("DELETE FROM players WHERE id = :p"), {"p": OLD_OWNER})
        await s.commit()


async def count(sql: str, **p) -> int:
    async with Session() as s:
        return int((await s.execute(text(sql), p)).scalar() or 0)


async def run() -> None:
    install_stubs()
    await seed()

    print("running the shipped sync for the club (aggregates, per-grade, scorecards)")
    res = await sync_mod.sync_organisation(str(ORG_A), kind="org_full")
    print("   stats:", {k: v for k, v in (res or {}).items() if k in
                        ("seasons", "season_stats", "grade_stats", "gr_batting", "gr_bowling", "gr_fielding",
                         "gr_games_new", "gr_matches_seen", "suppressed_people_skipped", "match_pull_failed", "error")})
    check("the sync ran and found all four matches", int((res or {}).get("gr_matches_seen", 0)) == 4, str(res))

    R, K, C = uuid.UUID(G_REMY), uuid.UUID(G_KEEP), uuid.UUID(G_CLUBHID)

    print("\n1. Season and per-grade totals")
    check("KEEP's season totals are written (could be present)",
          await count("SELECT COUNT(*) FROM player_season_stats WHERE player_id = :p", p=K) == 1)
    check("KEEP's per-grade totals are written",
          await count("SELECT COUNT(*) FROM player_season_grade_stats WHERE player_id = :p", p=K) >= 1)
    check("REMY's season totals are not written",
          await count("SELECT COUNT(*) FROM player_season_stats WHERE player_id = :p", p=R) == 0)
    check("REMY's per-grade totals are not written",
          await count("SELECT COUNT(*) FROM player_season_grade_stats WHERE player_id = :p", p=R) == 0)

    print("\n2. Game lines")
    check("KEEP's batting, bowling, fielding and appearance are written (could be present)",
          await count("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p", p=K) >= 1
          and await count("SELECT COUNT(*) FROM bowling_spells WHERE player_id = :p", p=K) >= 1
          and await count("SELECT COUNT(*) FROM fielding_stats WHERE player_id = :p", p=K) >= 1
          and await count("SELECT COUNT(*) FROM game_appearances WHERE player_id = :p", p=K) >= 1)
    for tbl in ("batting_innings", "bowling_spells", "fielding_stats", "game_appearances", "fall_of_wickets"):
        check(f"no {tbl} row for REMY", await count(f"SELECT COUNT(*) FROM {tbl} WHERE player_id = :p", p=R) == 0)
    check("no partnership names REMY as a batter",
          await count("SELECT COUNT(*) FROM partnerships WHERE batter1_id = :p OR batter2_id = :p", p=R) == 0)
    check("no bowler-wicket row has REMY as bowler or fielder",
          await count("SELECT COUNT(*) FROM bowler_wickets WHERE bowler_id = :p OR fielder_id = :p", p=R) == 0)

    print("\n3. His name as text")
    pat = "%removed%"
    check("FILLIN's name is still kept as text, on fielding (could be present)",
          await count("SELECT COUNT(*) FROM fielding_stats WHERE player_name ILIKE '%fillin%'") >= 1)
    check("KEEP's name is on the fall-of-wicket rows (could be present)",
          await count("SELECT COUNT(*) FROM fall_of_wickets WHERE batter_name ILIKE '%keep%'") >= 1)
    check("no fielding row carries REMY's name",
          await count("SELECT COUNT(*) FROM fielding_stats WHERE player_name ILIKE :p", p=pat) == 0)
    check("no fall-of-wicket row carries REMY's name",
          await count("SELECT COUNT(*) FROM fall_of_wickets WHERE batter_name ILIKE :p", p=pat) == 0)
    check("no partnership carries REMY's name",
          await count("SELECT COUNT(*) FROM partnerships WHERE batter1_name ILIKE :p OR batter2_name ILIKE :p", p=pat) == 0)
    check("no bowler-wicket row carries REMY's name",
          await count("SELECT COUNT(*) FROM bowler_wickets WHERE batter_name ILIKE :p", p=pat) == 0)
    check("the wicket REMY fell on is still in the card (second wicket of match 1, no name)",
          await count("SELECT COUNT(*) FROM fall_of_wickets WHERE game_id = :g AND wicket_number = 2 "
                      "AND score_at_fall = 58 AND batter_name IS NULL", g=uuid.UUID(M1)) == 1)
    check("KEEP's wicket of REMY on match 2 is still KEEP's (bowler record stays, no batter name)",
          await count("SELECT COUNT(*) FROM bowler_wickets WHERE game_id = :g AND bowler_id = :k AND batter_name IS NULL "
                      "AND batter_runs = 40", g=uuid.UUID(M2), k=K) == 1)

    print("\n4. A merge that points at him")
    check("KEEP is on the merge match (could be present)",
          await count("SELECT COUNT(*) FROM batting_innings WHERE game_id = :g AND player_id = :k",
                      g=uuid.UUID(M3), k=K) == 1)
    check("the old id merged into REMY lands no batting line on REMY",
          await count("SELECT COUNT(*) FROM batting_innings WHERE game_id = :g AND player_id = :p",
                      g=uuid.UUID(M3), p=R) == 0)

    print("\n5. Attach by name")
    check("KEEP is on the by-name match (could be present)",
          await count("SELECT COUNT(*) FROM batting_innings WHERE game_id = :g AND player_id = :k",
                      g=uuid.UUID(M4), k=K) == 1)
    check("a team-sheet entry with his full name and an unknown id is not attached to REMY",
          await count("SELECT COUNT(*) FROM batting_innings WHERE game_id = :g AND player_id = :p",
                      g=uuid.UUID(M4), p=R) == 0)
    check("(and no line at all landed on REMY from any match)",
          await count("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p", p=R) == 0)

    print("\n7. A player the club hid without a request is still collected")
    check("CLUBHID's season totals, batting and appearance are written",
          await count("SELECT COUNT(*) FROM player_season_stats WHERE player_id = :p", p=C) == 1
          and await count("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p", p=C) >= 1
          and await count("SELECT COUNT(*) FROM game_appearances WHERE player_id = :p", p=C) >= 1)

    print("\n8. The club's own record survives")
    check("all four games exist", await count("SELECT COUNT(*) FROM games WHERE id = ANY(:g)",
                                              g=[uuid.UUID(m) for m in (M1, M2, M3, M4)]) == 4)
    check("the opposition's batting stays on the card (fall-of-wicket row for them)",
          await count("SELECT COUNT(*) FROM fall_of_wickets WHERE batter_name ILIKE '%opp%'") >= 1)

    print("\n6. A second club's sync")
    await sync_mod.sync_organisation(str(ORG_B), kind="org_full")
    check("the second club syncs and stores the ordinary player (could be present)",
          await count("SELECT COUNT(*) FROM players WHERE organisation_id = :o AND grassroots_id = :g",
                      o=ORG_B, g=G_KEEP) == 1)
    check("the second club creates NO row for REMY",
          await count("SELECT COUNT(*) FROM players WHERE organisation_id = :o AND LOWER(grassroots_id) = :g",
                      o=ORG_B, g=G_REMY) == 0)

    print("\n9. A Full Rebuild's re-pull does not bring him back")
    # A Full Rebuild wipes games that have batting rows, then re-pulls the whole history.
    async with Session() as s:
        await s.execute(text("DELETE FROM games WHERE id IN (SELECT DISTINCT game_id FROM batting_innings)"))
        await s.commit()
    await sync_mod.sync_organisation(str(ORG_A), kind="org_hard_refresh")
    check("after the rebuild KEEP's lines are back (could be present)",
          await count("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p", p=K) >= 1)
    check("after the rebuild there is still nothing for REMY",
          await count("SELECT COUNT(*) FROM batting_innings WHERE player_id = :p", p=R) == 0
          and await count("SELECT COUNT(*) FROM fielding_stats WHERE player_name ILIKE :p", p=pat) == 0
          and await count("SELECT COUNT(*) FROM player_season_stats WHERE player_id = :p", p=R) == 0)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
