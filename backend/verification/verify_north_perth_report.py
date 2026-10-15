"""Verification: the five faults a trialling club reported, and the two send features, against a real Postgres.

Reported by a club that shares a first word with a neighbour ("North Perth" and
"North Beach"):

  1. The neighbour's fixtures were pulled into the club's Fixtures.
     Cause: "is this team ours" was a substring test on the club's FIRST WORD.
  2. Clicking into a game against the club that synced it first showed a loss and
     took the visitor to that other club's site.
     Cause: the scorecard always read the match from the owning club's side.
  3. Squads: selection listed squads the club never made.
     Cause: the pool's squad names were every team name a scorecard ever carried,
     plus squads the club had switched off.
  4. Results not reaching the club's stats.
     Cause: home/away ownership was decided by exact team-name equality.
  5. A fixture (1st Team, Round 3) showing wrongly.
     Cause: sides derived by the same first-word test ("North Beach v North
     Perth" filed as HOME with North Perth as its own opponent), and a
     sponsor-named side dropped for carrying no part of the club's name.

Features: the confirmed side emailed to its captain (with phones) and to the
players; the automatic send on Confirm.

Drives the SHIPPED functions and route bodies. CONTROL MODE: against the commit
before this change, new names are read with getattr and report failed checks
rather than crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_north_perth_report.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, User, Player, Team, Grade, Season, Fixture, FixtureLineup, Game, GameAppearance,
)
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def _create_stmt(table):
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", MAIN.read_text())
    return m.group(1) if m else None


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        for mod in ("junior_hiding_ddl", "player_privacy_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for mod in ("selection_draft_ddl", "selection_notice_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass


class Recorder:
    """An email provider that records instead of sending."""
    name = "recorder"

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        from app.services import email_service
        self.sent.append(msg)
        return email_service.SendResult(ok=True, message_id="rec")


async def main():
    await build_schema()
    from app.services import club_match, email_service, grassroots_scores_client as gr

    NP, NB, APP, BAY = (uuid.uuid4() for _ in range(4))
    np_club = SimpleNamespace(id=NP, name="North Perth Cricket Club", short_name=None, playhq_id=None)

    # ── 1 and 5: who is "us" in a payload ────────────────────────────────────
    print("\n[1,5] Telling the club's own sides from a neighbour's")
    fixture_side = getattr(club_match, "fixture_side", None)
    check("North Beach v North Perth is an AWAY game for North Perth (by org id)",
          fixture_side and fixture_side(np_club, "North Beach 1st XI", "North Perth 1st XI", NB, NP), "away")
    check("a neighbour's own fixture is not ours although the first word matches",
          fixture_side and fixture_side(np_club, "North Beach Women", "Scarborough Women", NB, uuid.uuid4()), None)
    check("a sponsor-named side with no part of our name is ours by org id",
          fixture_side and fixture_side(np_club, "Fieldmasters 1st Grade", "Bayswater 1sts", NP, BAY), "home")
    check("no org ids: the fuller name beats the shared word (we are away)",
          fixture_side and fixture_side(np_club, "North Beach 1sts", "North Perth 1sts"), "away")
    check("no org ids: nobody named like us is nobody",
          fixture_side and fixture_side(np_club, "Bayswater", "Scarborough"), None)

    live = [
        {"id": "m-ours-home", "home_team": "Fieldmasters 1st Grade", "away_team": "Bayswater 1sts",
         "home_org_id": str(NP), "away_org_id": str(BAY), "played_at": "2999-01-02", "grade_id": "g1"},
        {"id": "m-ours-away", "home_team": "North Beach 1sts", "away_team": "North Perth 1sts",
         "home_org_id": str(NB), "away_org_id": str(NP), "played_at": "2999-01-02", "grade_id": "g1"},
        {"id": "m-neighbour", "home_team": "North Beach Women", "away_team": "Scarborough Women",
         "home_org_id": str(NB), "away_org_id": str(uuid.uuid4()), "played_at": "2999-01-02", "grade_id": "g1"},
    ]

    async def fake_grade_fixtures(grade_id, include_live=True, force=False):
        return list(live)
    original = gr.get_grade_fixtures
    gr.get_grade_fixtures = fake_grade_fixtures
    try:
        try:
            got = await gr.get_grades_fixtures(["g1"], club=np_club)
        except TypeError:   # control: the old signature has no club=
            got = await gr.get_grades_fixtures(["g1"], club_match.club_match_keys(np_club))
        ids = sorted(f["id"] for f in got)
    finally:
        gr.get_grade_fixtures = original
    check("Fixtures: ours (sponsor-named home side, away at North Beach) in, the neighbour's women out",
          ids, ["m-ours-away", "m-ours-home"])

    import app.routers.fixtures as fxr
    check("the sync files North Beach v North Perth as AWAY with North Beach as the opponent",
          fxr._derive_sides(live[1], np_club), ("AWAY", "North Beach 1sts"))
    check("the sync files the sponsor-named side as HOME",
          fxr._derive_sides(live[0], np_club), ("HOME", "Bayswater 1sts"))

    import app.routers.ladders as lad
    payload = {"ladders": [{"name": "Ladder", "columns": [], "pools": [{"teams": [
        {"rank": 1, "id": "a", "displayName": "North Beach 1sts", "owningOrganisation": {"id": str(NB), "name": "North Beach CC"}},
        {"rank": 2, "id": "b", "displayName": "Fieldmasters 1st Grade", "owningOrganisation": {"id": str(NP), "name": "North Perth CC"}},
    ]}]}]}
    try:
        views = lad._parse_ladder_payload(payload, np_club)
    except Exception:
        views = lad._parse_ladder_payload(payload, club_match.club_match_keys(np_club))
    marked = {r["team_name"]: r["is_club"] for r in views[0]["rows"]}
    check("Ladder highlights North Perth (a sponsor-named row), not North Beach",
          (marked.get("North Beach 1sts"), marked.get("Fieldmasters 1st Grade")), (False, True))

    # ── 4: the winner is recorded even before CA flags it ─────────────────────
    print("\n[4] Recording who won")
    from app.services import sync as sync_mod
    winner_fn = getattr(sync_mod, "winning_team_name", None)
    flagged = {"matchSummary": {"teams": [
        {"displayName": "Applecross T20 Div 1", "isWinner": False, "resultType": "LOST"},
        {"displayName": "North Perth T20 Div 1", "isWinner": True, "resultType": "WON"}]}}
    unflagged = {"matchSummary": {"teams": [
        {"displayName": "Applecross T20 Div 1", "resultType": "LOST"},
        {"displayName": "North Perth T20 Div 1", "resultType": None}]}}
    drawn = {"matchSummary": {"teams": [
        {"displayName": "A", "resultType": "DRAWN"}, {"displayName": "B", "resultType": "DRAWN"}]}}
    check("a flagged winner is the winner", winner_fn and winner_fn(flagged), "North Perth T20 Div 1")
    check("an unflagged result still names the winner from the other side's LOST",
          winner_fn and winner_fn(unflagged), "North Perth T20 Div 1")
    check("a draw has no winner", winner_fn and winner_fn(drawn) is None, True)

    # ── data for the DB-backed checks ────────────────────────────────────────
    user_id, u2 = uuid.uuid4(), uuid.uuid4()
    np_season, app_season, g_np, g_app = (uuid.uuid4() for _ in range(4))
    t1, t2, t3 = (uuid.uuid4() for _ in range(3))
    shared_game, other_game = uuid.uuid4(), uuid.uuid4()
    P = [uuid.uuid4() for _ in range(8)]
    d = date.today() + timedelta(days=9)
    fx_a, fx_b = uuid.uuid4(), uuid.uuid4()

    async with Session() as db:
        db.add(Organisation(id=NP, name="North Perth Cricket Club", slug=f"northperth-{NP.hex[:6]}",
                            contact_email="coordinator@np.test"))
        db.add(Organisation(id=APP, name="Applecross Cricket Club", slug=f"applecross-{APP.hex[:6]}"))
        db.add(Organisation(id=NB, name="North Beach Cricket Club", slug=f"northbeach-{NB.hex[:6]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=np_season, organisation_id=NP, name="Summer", year=2026))
        db.add(Season(id=app_season, organisation_id=APP, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_np, season_id=np_season, name="1st Grade"))
        db.add(Grade(id=g_app, season_id=app_season, name="1st Grade"))
        await db.flush()
        db.add(Team(id=t1, organisation_id=NP, name="1st XI", sequence=1, grade_id=g_np))
        db.add(Team(id=t2, organisation_id=NP, name="Old Seconds", sequence=2, is_active=False))
        db.add(Team(id=t3, organisation_id=NP, name="2nd XI", sequence=2))
        await db.flush()
        names = ["Cara Captain", "Sam Smith", "Pat Phone", "Jess Junior", "Noel NoEmail", "Una Unsub", "Ed Elder", "Fran Fill"]
        for i, pid in enumerate(P):
            db.add(Player(id=pid, organisation_id=NP, name=names[i], gender="male", is_player=True, status="active"))
        await db.flush()
        # a game filed under Applecross (it synced first) that North Perth also played
        db.add(Game(id=shared_game, grade_id=g_app, played_at=date.today() - timedelta(days=3),
                    home_team="Applecross 1sts", away_team="North Perth 1sts",
                    winning_team="North Perth 1sts", result="LOSS",   # Applecross's verdict
                    home_org_id=APP, away_org_id=NP))
        # a game NP is not in at all
        db.add(Game(id=other_game, grade_id=g_app, played_at=date.today() - timedelta(days=4),
                    home_team="Applecross 2nds", away_team="North Beach 2nds",
                    winning_team="Applecross 2nds", result="WIN", home_org_id=APP, away_org_id=NB))
        await db.flush()
        # appearances under names that are not squads
        db.add(GameAppearance(game_id=shared_game, player_id=P[2], team_name="North Perth - Sponsor 1st"))
        db.add(GameAppearance(game_id=shared_game, player_id=P[1], team_name="North Beach Fill-In Side"))
        await db.flush()
        db.add(GameAppearance(game_id=other_game, player_id=P[2], team_name="1st XI"))
        await db.commit()
    async with engine.begin() as conn:
        # memberships: P0 only in the switched-off squad (and has it as primary); P1 in 1st + 2nd XI
        await conn.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES "
                                "(:t2, :p0, :o), (:t1, :p1, :o), (:t3, :p1, :o), (:t1, :p2, :o)"),
                           {"t1": t1, "t2": t2, "t3": t3, "p0": P[0], "p1": P[1], "p2": P[2], "o": NP})
        await conn.execute(text("UPDATE players SET squad_team_id = :t2 WHERE id = :p0"), {"t2": t2, "p0": P[0]})
        await conn.execute(text("UPDATE players SET squad_team_id = :t1 WHERE id IN (:p1, :p2)"),
                           {"t1": t1, "p1": P[1], "p2": P[2]})

    # ── 3: squads ────────────────────────────────────────────────────────────
    print("\n[3] The squads a selector sees")
    from app.services.selection_pool import assemble_selection
    async with Session() as db:
        db.add(Fixture(id=fx_a, organisation_id=NP, grade_id=g_np, team_id=t1, source="manual",
                       played_on=d, status="UPCOMING", label="x", opponent_name="Bayswater", venue="Hamer Park",
                       start_time="12:00"))
        await db.commit()
        club = await db.get(Organisation, NP)
        fx = await db.get(Fixture, fx_a)
        pool = {p["display_name"]: p for p in (await assemble_selection(db, club, fx))["pool"]}
    cara, sam, pat = pool["Cara Captain"], pool["Sam Smith"], pool["Pat Phone"]
    check("a player only in a switched-off squad shows no squad", cara["squads"], [])
    check("...and their primary squad is not the hidden one", cara["squad_team_id"], None)
    check("...and they are not a match for the 1st XI fixture", cara["squad_match"], False)
    check("a player in two live squads lists both, top squad first", sam["squads"], ["1st XI", "2nd XI"])
    check("team names off old scorecards that are not squads are not listed", pat["squads"], ["1st XI"])
    check("a live-squad member still matches the fixture", sam["squad_match"], True)

    import app.routers.teams as tr
    TeamUpdate = tr.TeamUpdate
    async with Session() as db:
        club = await db.get(Organisation, NP)
        recompute = getattr(tr, "recompute_primary_squads_for_team", None)
        await tr.update_team(str(t1), TeamUpdate(is_active=False), db=db, club=club, _user=None)
        prim = await db.scalar(text("SELECT squad_team_id FROM players WHERE id = :p"), {"p": P[1]})
        check("switching a squad off moves its members' primary to their next live squad",
              str(prim) if prim else None, str(t3) if recompute else str(t1))
        only = await db.scalar(text("SELECT squad_team_id FROM players WHERE id = :p"), {"p": P[2]})
        check("...and a member of only that squad has none", only, None if recompute else t1)
        await tr.update_team(str(t1), TeamUpdate(is_active=True), db=db, club=club, _user=None)
        back = await db.scalar(text("SELECT squad_team_id FROM players WHERE id = :p"), {"p": P[2]})
        check("...and switching it back on restores it (memberships were kept)", str(back) if back else None, str(t1))

    # ── 2 and 4: the shared fixture ─────────────────────────────────────────
    print("\n[2,4] A fixture that Applecross synced first, read by North Perth")
    import app.routers.games as games
    from app.services import grassroots_scores_client
    async def no_gr(*a, **k):
        return None
    grassroots_scores_client.get_match_scorecard = no_gr
    grassroots_scores_client.get_match_detail = no_gr

    async def scorecard(**kw):
        async with Session() as db:
            try:
                return await games.get_scorecard(str(shared_game), db=db, viewer=None, **kw)
            except TypeError:       # control: no org parameter yet
                kw.pop("org_param", None)
                return await games.get_scorecard(str(shared_game), db=db, viewer=None)
    owner_view = await scorecard()
    check("with no club named it reads from the owner's side, as before", owner_view["result"], "LOSS")
    check("...and names the owner", owner_view["organisation_id"], str(APP))
    np_view = await scorecard(org_param=str(NP))
    check("naming North Perth shows North Perth's WIN", np_view["result"], "WIN")
    check("...and the page belongs to North Perth (its theme and site, not Applecross's)",
          np_view["organisation_id"], str(NP))
    async with Session() as db:
        np_slug = await db.scalar(text("SELECT slug FROM organisations WHERE id = :i"), {"i": NP})
    by_slug = await scorecard(org_param=np_slug)
    check("a club slug works as well as an id", (by_slug["result"], by_slug["organisation_id"]), ("WIN", str(NP)))
    nb_view = await scorecard(org_param=str(NB))
    check("a club that did not play in the game cannot take it over (stays the owner's)",
          (nb_view["result"], nb_view["organisation_id"]), ("LOSS", str(APP)))
    async with Session() as db:
        try:
            other = await games.get_scorecard(str(other_game), org_param=str(NP), db=db, viewer=None)
            other_org = other["organisation_id"]
        except TypeError:
            other_org = str(APP)
    check("a game North Perth is not in ignores a North Perth hint (a 'north' look-alike match is no proof)",
          other_org, str(APP))

    # ── features ─────────────────────────────────────────────────────────────
    print("\n[+] Emailing the confirmed side")
    notify = importlib.import_module("app.services.selection_notify") if (
        Path(__file__).resolve().parent.parent / "app/services/selection_notify.py").exists() else None
    if notify is None:
        check("selection_notify exists", False)
    else:
        rec = Recorder()
        email_service.get_email_provider = lambda: rec
        email_service.email_is_live = lambda: True
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE players SET email = :e, phone = :ph WHERE id = :p"),
                               {"e": "cara@np.test", "ph": "0411 111 111", "p": P[0]})
            await conn.execute(text("UPDATE players SET email = :e, phone = :ph WHERE id = :p"),
                               {"e": "sam@np.test", "ph": "0422 222 222", "p": P[1]})
            await conn.execute(text("UPDATE players SET email = :e WHERE id = :p"), {"e": "pat@np.test", "p": P[2]})
            await conn.execute(text("UPDATE players SET email = :e, phone = :ph, date_of_birth = :dob WHERE id = :p"),
                               {"e": "jess@np.test", "ph": "0433 333 333",
                                "dob": date.today().replace(year=date.today().year - 15), "p": P[3]})
            await conn.execute(text("UPDATE players SET phone = :ph WHERE id = :p"), {"ph": "0444 444 444", "p": P[4]})
            await conn.execute(text("UPDATE players SET email = :e, phone = :ph WHERE id = :p"),
                               {"e": "una@np.test", "ph": "0455 555 555", "p": P[5]})
            await conn.execute(text("INSERT INTO email_suppressions (id, email, reason) VALUES (gen_random_uuid(), 'una@np.test', 'hard_bounce')"))
        async with Session() as db:
            db.add(Fixture(id=fx_b, organisation_id=NP, grade_id=g_np, team_id=t3, source="manual",
                           played_on=d, status="UPCOMING", label="x", opponent_name="Scarborough",
                           venue="Hamer Park", start_time="12:00", round="Round 3"))
            await db.commit()
            club = await db.get(Organisation, NP)

            r0 = await notify.send_to_captain(db, club, fx_b, user_id=user_id)
            check("nothing confirmed: nothing sent, and it says why", (r0["status"], r0["reason"]), ("skipped", "no_lineup"))

            for i in range(6):
                db.add(FixtureLineup(fixture_id=fx_b, player_id=P[i], organisation_id=NP, batting_order=i + 1,
                                     is_captain=(i == 1), is_wicket_keeper=(i == 2)))
            await db.commit()
            # Sam (index 1) is captain, so the sheet goes to sam@np.test
            r = await notify.send_to_captain(db, club, fx_b, user_id=user_id)
            check("the captain is emailed", (r["status"], r["captain"]), ("sent", "Sam Smith"))
            msg = rec.sent[-1]
            check("...at their own address", msg.to_email, "sam@np.test")
            for ph in ("0411 111 111", "0422 222 222", "0433 333 333", "0444 444 444"):
                check(f"...with {ph} from the player's profile", ph in msg.html and ph in msg.text, True)
            check("...and says who has no number instead of leaving a blank",
                  "Pat Phone" in msg.text and "no number on file" in msg.text, True)
            check("...and names the match", "Scarborough" in msg.subject and "2nd XI" in msg.subject, True)
            check("...and tells the selector who is missing a mobile", "Pat Phone" in r["missing_phones"], True)

            n = len(rec.sent)
            r2 = await notify.send_to_captain(db, club, fx_b, user_id=user_id, automatic=True)
            check("the automatic send does not repeat a side the captain already has",
                  (r2["status"], r2["reason"], len(rec.sent)), ("skipped", "already_sent", n))
            r3 = await notify.send_to_captain(db, club, fx_b, user_id=user_id)
            check("a deliberate send always goes", (r3["status"], len(rec.sent)), ("sent", n + 1))
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE fixture_lineups SET batting_order = 9 WHERE fixture_id = :f AND player_id = :p"),
                                   {"f": fx_b, "p": P[0]})
            r4 = await notify.send_to_captain(db, club, fx_b, user_id=user_id, automatic=True)
            check("a changed side is sent again by the automatic send", (r4["status"], len(rec.sent)), ("sent", n + 2))

            rp = await notify.send_to_players(db, club, fx_b, user_id=user_id, message="Be there at 11.")
            reasons = {s["name"]: s["reason"] for s in rp["skipped"] + rp["failed"]}
            check("players are emailed", rp["sent"], 3)       # Cara, Sam, Pat
            check("an under 18 is not emailed directly", reasons.get("Jess Junior"), "junior")
            check("a player with no address is named, not skipped silently", reasons.get("Noel NoEmail"), "no_email")
            check("a bounced address is named with the reason", reasons.get("Una Unsub"), "hard_bounce")
            last = rec.sent[-1]
            check("a player's email carries the match and the note, and no one's phone number",
                  ("Scarborough" in last.text and "Be there at 11." in last.text and "0422" not in last.text), True)
            check("...and names the captain", "Sam Smith" in last.text, True)

            rec_before = len(rec.sent)
            email_service.email_is_live = lambda: False
            rn = await notify.send_to_captain(db, club, fx_b, user_id=user_id)
            check("with no live email provider it fails readably and sends nothing",
                  (rn["status"], rn["reason"], len(rec.sent)), ("failed", "email_not_live", rec_before))
            rpn = await notify.send_to_players(db, club, fx_b, user_id=user_id)
            check("...players too", (rpn["status"], rpn["sent"]), ("failed", 0))
            email_service.email_is_live = lambda: True

            async with engine.begin() as conn:
                await conn.execute(text("UPDATE fixture_lineups SET is_captain = FALSE WHERE fixture_id = :f"), {"f": fx_b})
            rc = await notify.send_to_captain(db, club, fx_b, user_id=user_id)
            check("no captain flagged: says so", (rc["status"], rc["reason"]), ("skipped", "no_captain"))
            foreign = await notify.send_to_captain(db, SimpleNamespace(id=APP), fx_b)
            check("another club's fixture is not found", foreign["status"], "failed")
            log = await notify.list_notices(db, club, fx_b)
            check("every send is on the record", any(x["status"] == "sent" and x["kind"] == "captain" for x in log), True)

            # the route: another club's fixture is a 404; the automatic send on Confirm
            import app.routers.selection as sel
            try:
                await sel.notify_selection(str(fx_b), sel.NotifyBody(to="captain"), db=db,
                                           club=await db.get(Organisation, APP), user=None)
                check("the route refuses a fixture that is not the club's", False)
            except HTTPException as e:
                check("the route refuses a fixture that is not the club's", e.status_code, 404)

            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM fixture_lineups WHERE fixture_id = :f"), {"f": fx_b})
                await conn.execute(text("DELETE FROM selection_notices WHERE fixture_id = :f"), {"f": fx_b})
            club = await db.get(Organisation, NP)
            slots = [sel.LineupSlot(player_id=str(P[i]), batting_order=i + 1, is_captain=(i == 1)) for i in range(4)]
            for flag in (False, True):
                club.selection_rules_config = {"notify_captain_on_confirm": flag} if flag else None
                await db.commit()
                before = len(rec.sent)
                bg = BackgroundTasks()
                u = SimpleNamespace(id=user_id)
                await sel.set_selection(str(fx_b), sel.LineupSet(players=slots), db=db, club=club, user=u, background_tasks=bg)
                await bg()
                check(f"Confirm with the setting {'on' if flag else 'off'}: captain email "
                      f"{'sent' if flag else 'not sent'}", len(rec.sent) - before, 1 if flag else 0)
            check("the setting reads back", importlib.import_module("app.services.selection_rules").club_config(club)
                  ["notify_captain_on_confirm"], True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
