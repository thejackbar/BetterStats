"""The manual games CSV import, with the historical-stats wizard's review step.

The strict endpoint refuses a row naming a season, grade or player the club
does not already hold — which, for a club importing a whole history out of an
old scoring program, is every row. This suite drives the SHIPPED route bodies
for the preview/resolve/commit wizard that creates them instead, and the undo
that takes them back.

The two things worth failing on:

  * a season or grade is created without ceremony (there is no identity
    question to get wrong), but a PLAYER is proposed and never auto-created —
    this codebase already carries the scars of a name matcher putting two
    people on one record;
  * an undo removes what the import created and NOTHING ELSE, so a player who
    has since been synced, or a season that now holds another club's own work,
    survives it.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_manual_games_import.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Grade, ManualBattingInnings, ManualBowlingSpell, ManualEditLog,
    ManualFieldingStat, ManualGame, Organisation, Player, Season, User,
)

# Behind a guard so a CONTROL RUN against the previous commit reports the
# feature missing as failed checks rather than dying on an ImportError before
# a single one runs.
MISSING: list[str] = []
try:
    from app.routers.manual_entries import (
        GameResolveRequest, commit_manual_games, preview_manual_games,
        resolve_manual_games,
    )
    HAVE = True
except ImportError as exc:  # pragma: no cover - control run only
    HAVE = False
    MISSING.append(str(exc))

from app.routers.manual_entries import (
    GAME_CSV_COLUMNS, import_manual_games, list_audit, undo_edit,
)

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER = uuid.uuid4()
USER = uuid.uuid4()

S_HELD = uuid.uuid4()      # the one season the club already has
G_HELD = uuid.uuid4()      # and its one grade
P_HELD = uuid.uuid4()      # a player the sheet names exactly
P_FUZZY = uuid.uuid4()     # a player the sheet names with a middle initial
P_TWIN_A = uuid.uuid4()    # two people sharing one name — must never be
P_TWIN_B = uuid.uuid4()    # auto-matched
P_SYNCED = uuid.uuid4()    # carries a grassroots id, so never deletable
P_OTHER = uuid.uuid4()     # another club's player


class FakeUpload:
    """Enough of UploadFile for the preview route body."""

    def __init__(self, text_: str, filename: str = "scorecards.csv"):
        self._data = text_.encode("utf-8-sig")
        self.filename = filename

    async def read(self):
        return self._data


def csv_text(rows: list[dict], headers: list[str] | None = None) -> str:
    import csv as _csv
    buf = io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=headers or GAME_CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def game_row(**kw) -> dict:
    row = {c: "" for c in GAME_CSV_COLUMNS}
    row.update(kw)
    return row


# The sheet a club's converted history actually looks like: a season, a grade
# and most of the people are new, one person is already on the roster, one is
# the same person under a slightly different spelling.
SHEET = [
    # 1992/93 Grade 2 — none of the season, grade or these players exist yet
    game_row(game_key="1992-001", played_at="1992-10-17", opposition="Mandurah",
             venue="Peelwood", season_name="1992/93", grade_name="Grade 2",
             winning_team="Shoalwater Bay", result="Won",
             player_name="Guest, Rob", innings_number="1", batting_position="1",
             batting_runs="19", batting_fours="2", batting_sixes="0",
             batting_not_out="false", did_not_bat="false", dismissal_type="Bowled",
             bowling_overs="8.0", bowling_maidens="1", bowling_runs="30",
             bowling_wickets="2", fielding_catches="1"),
    game_row(game_key="1992-001", played_at="1992-10-17", opposition="Mandurah",
             venue="Peelwood", season_name="1992/93", grade_name="Grade 2",
             player_name="Appleby, Rick", innings_number="1", batting_position="2",
             batting_runs="57", batting_not_out="true", did_not_bat="false"),
    game_row(game_key="1992-001", played_at="1992-10-17", opposition="Mandurah",
             venue="Peelwood", season_name="1992/93", grade_name="Grade 2",
             player_name="Barlow, Craig R", innings_number="1", batting_position="3",
             batting_runs="12", did_not_bat="false", dismissal_type="Caught"),
    # second leg of the same two-day match, as its own innings
    game_row(game_key="1992-001", played_at="1992-10-17", opposition="Mandurah",
             venue="Peelwood", season_name="1992/93", grade_name="Grade 2",
             player_name="Guest, Rob", innings_number="2", batting_position="1",
             batting_runs="4", did_not_bat="false", dismissal_type="LBW"),
    # a second match, in a season the club DOES hold, under its existing grade
    game_row(game_key="2010-001", played_at="2010-11-13", opposition="Bayswater",
             venue="Hyde Park", season_name="Summer 2010/11", grade_name="1st Grade",
             player_name="Held, Harry", innings_number="1", batting_position="4",
             batting_runs="45", batting_balls="60", did_not_bat="false",
             dismissal_type="Run out", bowling_overs="8.2", bowling_maidens="2",
             bowling_runs="25", bowling_wickets="3", bowling_wides="1",
             fielding_catches_wk="2", fielding_stumpings="1"),
]


async def reset(session) -> None:
    for tbl in ("manual_fielding_stats", "manual_bowling_spells", "manual_batting_innings",
                "manual_games", "manual_edit_logs", "grades", "seasons", "players",
                "club_memberships", "organisations", "users"):
        await session.execute(text(f"TRUNCATE {tbl} CASCADE"))
    await session.commit()


async def seed(session) -> None:
    session.add_all([
        User(id=USER, username="admin", password_hash="x"),
        Organisation(id=ORG, name="Shoalwater Bay", slug="shoalwater"),
        Organisation(id=OTHER, name="Somebody Else", slug="other"),
        Season(id=S_HELD, organisation_id=ORG, name="Summer 2010/11", year=2010),
        Grade(id=G_HELD, season_id=S_HELD, name="1st Grade"),
        Player(id=P_HELD, organisation_id=ORG, name="Held, Harry"),
        Player(id=P_FUZZY, organisation_id=ORG, name="Craig Barlow"),
        Player(id=P_TWIN_A, organisation_id=ORG, name="Twin, Sam"),
        Player(id=P_TWIN_B, organisation_id=ORG, name="Twin, Sam"),
        Player(id=P_SYNCED, organisation_id=ORG, name="Synced, Sid",
               grassroots_id=str(uuid.uuid4())),
        Player(id=P_OTHER, organisation_id=OTHER, name="Guest, Rob"),
    ])
    await session.commit()


async def club(session) -> Organisation:
    return await session.get(Organisation, ORG)


async def user(session) -> User:
    return await session.get(User, USER)


def by_label(rows, key, value):
    return next((r for r in rows if r.get(key) == value), None)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        # A lifespan-only table this route body reaches through the undo's
        # player cleanup — create_all cannot see it.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY,
                player_id UUID,
                organisation_id UUID,
                season TEXT
            )
        """))

    async with Session() as session:
        await reset(session)
        await seed(session)

    if not HAVE:  # pragma: no cover - control run only
        check("the games import wizard is available", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    print("\n-- THE REPORTED CASE: a whole history, none of which the club holds --")
    async with Session() as session:
        c = await club(session)
        u = await user(session)
        prev = await preview_manual_games(
            file=FakeUpload(csv_text(SHEET)), current_user=u, club=c)
        check("the preview reads every row", prev["row_count"] == len(SHEET),
              str(prev["row_count"]))
        check("and reports no unknown columns", prev["unknown_columns"] == [],
              str(prev["unknown_columns"]))

        req = GameResolveRequest(filename="scorecards.csv", rows=prev["rows"])
        res = await resolve_manual_games(req=req, current_user=u, club=c, db=session)

        check("it counts the two matches, not the five rows", res["games"] == 2,
              str(res["games"]))
        s_new = by_label(res["seasons"], "raw_label", "1992/93")
        s_old = by_label(res["seasons"], "raw_label", "Summer 2010/11")
        check("the season the club has no row for is proposed for creation",
              (s_new or {}).get("status") == "new" and (s_new or {}).get("will_create") is True,
              str(s_new))
        check("the season it already holds is matched, not created again",
              (s_old or {}).get("season_id") == str(S_HELD)
              and not (s_old or {}).get("will_create"), str(s_old))
        g_new = by_label(res["grades"], "raw_label", "Grade 2")
        g_old = by_label(res["grades"], "raw_label", "1st Grade")
        check("the grade the club has never run is proposed for creation",
              (g_new or {}).get("status") == "new" and (g_new or {}).get("grade_name") == "Grade 2",
              str(g_new))
        check("its own existing grade is matched by name",
              (g_old or {}).get("grade_name") == "1st Grade"
              and not (g_old or {}).get("will_create"), str(g_old))
        check("and each grade says which seasons it is used in",
              (g_new or {}).get("used_in_seasons") == ["1992/93"], str(g_new))

        print("\n-- PLAYERS: matched, proposed, never silently created --")
        p_held = by_label(res["players"], "raw_name", "Held, Harry")
        p_fuzzy = by_label(res["players"], "raw_name", "Barlow, Craig R")
        p_new = by_label(res["players"], "raw_name", "Guest, Rob")
        check("a name the club already holds is matched outright",
              (p_held or {}).get("player_id") == str(P_HELD)
              and (p_held or {}).get("status") == "exact", str(p_held))
        check("a middle initial the roster lacks still finds the same person",
              (p_fuzzy or {}).get("player_id") == str(P_FUZZY), str(p_fuzzy))
        check("a name nobody holds is NOT auto-created — it needs an answer",
              (p_new or {}).get("player_id") is None
              and (p_new or {}).get("status") not in ("new", "manual"), str(p_new))
        check("another club's player of that exact name is never offered",
              str(P_OTHER) not in str(res["players"]))
        check("the review says how many names are still unanswered",
              res["totals"]["players_unresolved"] == 2,
              str(res["totals"]))
        check("and warns in words, naming them",
              any("still need an answer" in w for w in res["warnings"]),
              str(res["warnings"]))
        check("the sheet's own figures ride along, so two people sharing a "
              "surname can be told apart without opening the file",
              (p_new or {}).get("sheet", {}).get("runs") == 23
              and (p_new or {}).get("sheet", {}).get("wickets") == 2,
              str((p_new or {}).get("sheet")))
        check("nothing is created by a resolve — it is read-only",
              (await session.execute(select(Season).where(Season.organisation_id == ORG))
               ).scalars().all().__len__() == 1)

        print("\n-- COMMIT REFUSES while a name is unanswered --")
        try:
            await commit_manual_games(req=req, current_user=u, club=c, db=session)
            check("an unanswered name blocks the commit", False, "it committed")
        except Exception as e:
            check("an unanswered name blocks the commit", "need an answer" in str(e), str(e)[:120])
        await session.rollback()
        check("and nothing was written by the attempt",
              len((await session.execute(select(ManualGame))).scalars().all()) == 0)

    print("\n-- THE ADMIN ANSWERS, AND THE IMPORT LANDS --")
    async with Session() as session:
        c = await club(session)
        u = await user(session)
        req = GameResolveRequest(
            filename="scorecards.csv", rows=csv_rows,
            player_overrides={"Guest, Rob": "__new__", "Appleby, Rick": "__new__"},
        )
        res = await resolve_manual_games(req=req, current_user=u, club=c, db=session)
        check("with both answered, nothing is left unresolved",
              res["totals"]["players_unresolved"] == 0, str(res["totals"]))
        check("the review names exactly what it will create: 1 season",
              res["will_create"]["seasons"] == 1, str(res["will_create"]))
        check("1 grade — one row per (season, grade) actually used",
              res["will_create"]["grades"] == 1, str(res["will_create"]))
        check("and 2 players", res["will_create"]["players"] == 2, str(res["will_create"]))

        out = await commit_manual_games(req=req, current_user=u, club=c, db=session)
        check("the commit reports what it did", out["games_created"] == 2, str(out))
        check("creating the season", out["seasons_created"] == 1, str(out))
        check("the grade", out["grades_created"] == 1, str(out))
        check("and the two players", out["players_created"] == 2, str(out))
        check("with no row errors", out["errors"] == 0, str(out.get("errors_detail")))

    async with Session() as session:
        seasons = (await session.execute(
            select(Season).where(Season.organisation_id == ORG))).scalars().all()
        made = next((s for s in seasons if s.name == "1992/93"), None)
        check("the created season carries the sheet's own label, not a renamed one",
              made is not None, str([s.name for s in seasons]))
        check("its year is read off that label", made and made.year == 1992,
              str(made and made.year))
        check("and grassroots_id stays NULL — the not-from-a-sync marker",
              made and made.grassroots_id is None)
        grades = (await session.execute(
            select(Grade).join(Season, Season.id == Grade.season_id)
            .where(Season.organisation_id == ORG))).scalars().all()
        check("the grade was created inside that season, not another",
              any(g.name == "Grade 2" and g.season_id == made.id for g in grades),
              str([(g.name, str(g.season_id)) for g in grades]))
        g2 = next(g for g in grades if g.name == "Grade 2")
        check("with its category and categories BOTH set, per the house rule",
              g2.category and g2.categories, f"{g2.category} / {g2.categories}")

        games = (await session.execute(
            select(ManualGame).where(ManualGame.organisation_id == ORG))).scalars().all()
        check("both matches landed", len(games) == 2, str(len(games)))
        old = next(g for g in games if str(g.season_id) == str(S_HELD))
        check("the one in an existing season reused it rather than making a second",
              old.grade_id == G_HELD, str(old.grade_id))
        check("with its date, opposition and venue", (
            old.played_at == date(2010, 11, 13) and old.opposition == "Bayswater"
            and old.venue == "Hyde Park"))

        bat = (await session.execute(select(ManualBattingInnings))).scalars().all()
        check("every batting row is written", len(bat) == 5, str(len(bat)))
        check("a not out is flagged", any(b.not_out for b in bat))
        check("the second leg is its own innings, not a duplicate of the first",
              sorted({b.innings_number for b in bat}) == [1, 2],
              str(sorted({b.innings_number for b in bat})))
        bowl = (await session.execute(select(ManualBowlingSpell))).scalars().all()
        check("bowling figures land, overs in cricket notation",
              sorted(round(float(b.overs), 1) for b in bowl) == [8.0, 8.2],
              str([str(b.overs) for b in bowl]))
        check("and wides come with them", any(b.wides == 1 for b in bowl))
        fld = (await session.execute(select(ManualFieldingStat))).scalars().all()
        check("keeper catches and stumpings are kept apart",
              any(f.catches_wk == 2 and f.stumpings == 1 for f in fld),
              str([(f.catches, f.catches_wk, f.stumpings) for f in fld]))

    print("\n-- THE UNDO TAKES BACK WHAT IT CREATED, AND ONLY THAT --")
    async with Session() as session:
        u = await user(session)
        c = await club(session)
        logs = await list_audit(limit=10, current_user=u, club=c, db=session)
        entry = logs[0]
        after = entry.get("after_json") or entry.get("after") or {}
        check("the audit entry records the seasons it created",
              len(after.get("created_season_ids") or []) == 1, str(after.keys()))
        check("the grades", len(after.get("created_grade_ids") or []) == 1)
        check("and the players — without which an undo could not find them",
              len(after.get("created_player_ids") or []) == 2)

        res = await undo_edit(log_id=entry["id"], current_user=u, club=c, db=session)
        # Read through .get throughout: a CONTROL RUN with the cleanup removed
        # must REPORT every one of these, not die on the first missing key and
        # say nothing about the rest.
        rm = res.get("removed") or {}
        check("the undo reports what it removed", bool(rm), str(res))
        check("both created players are gone", rm.get("players") == 2, str(res))
        check("the created grade with them", rm.get("grades") == 1, str(res))
        check("and the created season", rm.get("seasons") == 1, str(res))

    async with Session() as session:
        left = (await session.execute(
            select(Player).where(Player.organisation_id == ORG))).scalars().all()
        check("the club is back to the players it started with", len(left) == 5,
              str([p.name for p in left]))
        check("the player it already held is untouched",
              any(p.id == P_HELD for p in left))
        seasons = (await session.execute(
            select(Season).where(Season.organisation_id == ORG))).scalars().all()
        check("its own season survives the undo", [s.name for s in seasons] == ["Summer 2010/11"],
              str([s.name for s in seasons]))
        grades = (await session.execute(
            select(Grade).join(Season, Season.id == Grade.season_id)
            .where(Season.organisation_id == ORG))).scalars().all()
        check("and its own grade", [g.name for g in grades] == ["1st Grade"],
              str([g.name for g in grades]))
        check("every game is gone",
              len((await session.execute(select(ManualGame))).scalars().all()) == 0)

    print("\n-- AN UNDO NEVER TAKES DOWN WHAT ARRIVED SOME OTHER WAY --")
    async with Session() as session:
        await reset(session)
        await seed(session)
    async with Session() as session:
        c, u = await club(session), await user(session)
        rows = [game_row(game_key="G1", played_at="1993-01-09", season_name="1993/94",
                         grade_name="Grade 3", opposition="Rockingham",
                         player_name="Newman, Ned", innings_number="1",
                         batting_runs="20", did_not_bat="false")]
        req = GameResolveRequest(rows=rows, player_overrides={"Newman, Ned": "__new__"})
        out = await commit_manual_games(req=req, current_user=u, club=c, db=session)
        check("a one-game import lands", out["games_created"] == 1, str(out))
        new_pid = (await session.execute(
            select(Player.id).where(Player.organisation_id == ORG,
                                    Player.name == "Newman, Ned"))).scalar_one()

    async with Session() as session:
        # the club syncs, and this person turns out to be a real registered
        # player — an undo must not now delete them
        p = await session.get(Player, new_pid)
        p.grassroots_id = str(uuid.uuid4())
        await session.commit()

    async with Session() as session:
        c, u = await club(session), await user(session)
        logs = await list_audit(limit=10, current_user=u, club=c, db=session)
        entry = logs[0]
        res = await undo_edit(log_id=entry["id"], current_user=u, club=c, db=session)
        rm = res.get("removed") or {}
        check("the game is still removed", res.get("undone") is True, str(res))
        check("but the player is KEPT, because a sync has since claimed them",
              rm.get("players") == 0 and rm.get("players_kept") == 1,
              str(res.get("removed")))
    async with Session() as session:
        check("and they are genuinely still there",
              (await session.get(Player, new_pid)) is not None)
        check("the season it created goes, since nothing else needs it",
              (await session.execute(
                  select(Season).where(Season.organisation_id == ORG,
                                       Season.name == "1993/94"))).scalar_one_or_none() is None)

    print("\n-- REFUSALS AND SCOPE --")
    async with Session() as session:
        await reset(session)
        await seed(session)
    async with Session() as session:
        c, u = await club(session), await user(session)
        # a season id belonging to somebody else
        stranger = uuid.uuid4()
        session.add(Season(id=stranger, organisation_id=OTHER, name="Theirs", year=2001))
        await session.commit()
        rows = [game_row(game_key="G1", season_name="Theirs", player_name="Held, Harry",
                         batting_runs="1", did_not_bat="false")]
        try:
            await commit_manual_games(
                req=GameResolveRequest(rows=rows,
                                       season_overrides={"Theirs": str(stranger)}),
                current_user=u, club=c, db=session)
            check("another club's season cannot be imported into", False, "it committed")
        except Exception as e:
            check("another club's season cannot be imported into",
                  "does not belong" in str(e), str(e)[:120])
        await session.rollback()

    async with Session() as session:
        c, u = await club(session), await user(session)
        rows = [game_row(game_key="G1", season_name="Theirs2", player_name="Somebody, New",
                         batting_runs="1", did_not_bat="false")]
        try:
            await commit_manual_games(
                req=GameResolveRequest(rows=rows,
                                       player_overrides={"Somebody, New": str(P_OTHER)}),
                current_user=u, club=c, db=session)
            check("another club's player cannot be picked", False, "it committed")
        except Exception as e:
            check("another club's player cannot be picked",
                  "does not belong" in str(e), str(e)[:120])
        await session.rollback()

    async with Session() as session:
        c, u = await club(session), await user(session)
        res = await resolve_manual_games(
            req=GameResolveRequest(rows=[game_row(
                game_key="G1", season_name="1994/95", player_name="Twin, Sam",
                batting_runs="1", did_not_bat="false")]),
            current_user=u, club=c, db=session)
        twin = by_label(res["players"], "raw_name", "Twin, Sam")
        check("a name two people share is reported as ambiguous, never guessed",
              (twin or {}).get("status") == "ambiguous" and not (twin or {}).get("player_id"),
              str(twin))
        check("and the review says to merge them first",
              any("merge" in w for w in res["warnings"]), str(res["warnings"]))

    print("\n-- SKIPPING A NAME LEAVES THEM OUT, IT DOES NOT DROP THE MATCH --")
    async with Session() as session:
        c, u = await club(session), await user(session)
        rows = [
            game_row(game_key="G9", played_at="1995-02-04", season_name="1995/96",
                     grade_name="Grade 1", player_name="Held, Harry",
                     batting_runs="30", did_not_bat="false"),
            game_row(game_key="G9", played_at="1995-02-04", season_name="1995/96",
                     grade_name="Grade 1", player_name="Nobody, Nigel",
                     batting_runs="7", did_not_bat="false"),
        ]
        out = await commit_manual_games(
            req=GameResolveRequest(rows=rows,
                                   player_overrides={"Nobody, Nigel": "__skip__"}),
            current_user=u, club=c, db=session)
        check("the match still imports", out["games_created"] == 1, str(out))
        check("with no error raised for the skipped name", out["errors"] == 0,
              str(out.get("errors_detail")))
        check("nobody was created for them", out["players_created"] == 0, str(out))
    async with Session() as session:
        bat = (await session.execute(select(ManualBattingInnings))).scalars().all()
        check("and the skipped person has no innings on the card", len(bat) == 1,
              str(len(bat)))

    print("\n-- A GRADE THE ADMIN SAYS IS NO GRADE AT ALL --")
    async with Session() as session:
        await reset(session)
        await seed(session)
    async with Session() as session:
        c, u = await club(session), await user(session)
        rows = [game_row(game_key="G1", played_at="1996-01-06", season_name="1996/97",
                         grade_name="Social", player_name="Held, Harry",
                         batting_runs="11", did_not_bat="false")]
        out = await commit_manual_games(
            req=GameResolveRequest(rows=rows, grade_overrides={"Social": "__none__"}),
            current_user=u, club=c, db=session)
        check("the match imports ungraded", out["games_created"] == 1, str(out))
        check("and no grade was invented", out["grades_created"] == 0, str(out))
    async with Session() as session:
        g = (await session.execute(select(ManualGame))).scalars().first()
        check("the game genuinely carries no grade", g.grade_id is None)

    print("\n-- HEADERS, AND THE SHEET THAT IS NOT ONE --")
    async with Session() as session:
        c, u = await club(session), await user(session)
        odd = csv_text([{"Game Key": "G1", "Season Name": "1997/98",
                         "Player Name": "Held, Harry", "Batting Runs": "5"}],
                       headers=["Game Key", "Season Name", "Player Name",
                                "Batting Runs", "Notes"])
        prev = await preview_manual_games(file=FakeUpload(odd), current_user=u, club=c)
        check("a header reading 'Batting Runs' lands on batting_runs",
              prev["rows"][0].get("batting_runs") == "5", str(prev["rows"][0]))
        check("and a column nobody asked for is reported, not silently dropped",
              prev["unknown_columns"] == ["Notes"], str(prev["unknown_columns"]))
        try:
            await preview_manual_games(
                file=FakeUpload(csv_text([{"player_name": "x"}],
                                         headers=["player_name"])),
                current_user=u, club=c)
            check("a sheet with no game_key column is refused", False, "it was accepted")
        except Exception as e:
            check("a sheet with no game_key column is refused",
                  "missing required column" in str(e).lower(), str(e)[:120])

    print("\n-- THE STRICT ENDPOINT IS UNCHANGED --")
    async with Session() as session:
        await reset(session)
        await seed(session)
    async with Session() as session:
        c, u = await club(session), await user(session)
        out = await import_manual_games(
            file=FakeUpload(csv_text(SHEET)), current_user=u, club=c, db=session)
        check("it still refuses a season the club does not hold",
              out["games_created"] == 1, str(out))
        check("naming the one it could not find",
              any("Season not found" in e["error"] for e in out["errors_detail"]),
              str(out["errors_detail"])[:200])
    async with Session() as session:
        check("and creates nothing on the way",
              len((await session.execute(
                  select(Season).where(Season.organisation_id == ORG))).scalars().all()) == 1)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


csv_rows: list[dict] = []

if __name__ == "__main__":
    import csv as _csv
    csv_rows = [{k: (v or "") for k, v in r.items()}
                for r in _csv.DictReader(io.StringIO(csv_text(SHEET)))]
    asyncio.run(main())
