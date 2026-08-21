"""Verification for BetterFootball manual stat entries, against a real Postgres.

Exercises the SHIPPED route bodies, the shipped read helpers and the real AFL
boot path — never a re-implementation of any of them.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_manual_entries.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

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


async def status_of(coro):
    """Run a route body and report its HTTPException status, or None."""
    try:
        await coro
        return None
    except HTTPException as e:
        return e.status_code


class Upload:
    """Enough of an UploadFile for the CSV import route body."""
    def __init__(self, data: str):
        self._data = data.encode("utf-8")
        self.filename = "adjustments.csv"

    async def read(self):
        return self._data


async def main():
    from app.models.db import Base, Grade, Organisation, Player, Season, User, engine, async_session_maker
    import app.models.afl  # noqa: F401 — registers the AFL tables
    from app.models.afl import AflManualAdjustment
    from app.afl_main import lifespan
    from app.routers.afl import manual_entries as me
    from app.routers.afl import leaderboard as lb
    from app.routers.afl import merge as mg
    from app.routers.afl import organisations as orgs
    from app.routers.afl import players_admin as padm
    from app.routers.afl import records as rec
    from app.routers.afl import seasons_admin as sadm
    from app.services.afl import aggregations as agg

    # ── Schema, through the real AFL boot path ────────────────────────────
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

    print("\n── Schema, via the shipped AFL lifespan ──")
    async with lifespan(None):
        pass
    # Twice: the lifespan re-runs its whole DDL list on every boot, so every
    # statement in it — including the new adjustment_ids ALTER — has to be
    # idempotent or a second deploy fails outright.
    async with lifespan(None):
        pass

    async with engine.begin() as conn:
        cols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'afl_manual_adjustments'"))).scalars().all())
        check("afl_manual_adjustments created by create_all", "games_played" in cols)
        check("  ... carries the vote columns", {"club_bf_votes", "comp_bf_votes"} <= cols)
        check("  ... season_id is nullable (a career-only row)", bool((await conn.execute(text(
            "SELECT is_nullable = 'YES' FROM information_schema.columns "
            "WHERE table_name='afl_manual_adjustments' AND column_name='season_id'"))).scalar()))
        check("afl_merge_logs.adjustment_ids mirrored, twice over", bool((await conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='afl_merge_logs' AND column_name='adjustment_ids')"))).scalar()))

    Session = async_session_maker

    # ── Fixtures ──────────────────────────────────────────────────────────
    org_id, other_org_id = uuid.uuid4(), uuid.uuid4()
    user_id = uuid.uuid4()
    s2019, s2020, other_season = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    g_sen, g_res, other_grade = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p_ruck, p_wing, p_dup, other_player = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with Session() as db:
        db.add_all([
            Organisation(id=org_id, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other_org_id, name="Hampton Hammers", slug="hh", is_active=True),
            User(id=user_id, username="admin", email="a@b.c", password_hash="x",
                 display_name="Alex Admin"),
            Season(id=s2019, organisation_id=org_id, name="2019", year=2019),
            Season(id=s2020, organisation_id=org_id, name="2020", year=2020, grassroots_id="phq-2020"),
            Season(id=other_season, organisation_id=other_org_id, name="2019", year=2019),
            Player(id=p_ruck, organisation_id=org_id, name="Ruck, Ron"),
            Player(id=p_wing, organisation_id=org_id, name="Wing, Wes"),
            Player(id=p_dup, organisation_id=org_id, name="Ruck, Ron"),
            Player(id=other_player, organisation_id=other_org_id, name="Away, Alan"),
        ])
        await db.flush()
        db.add_all([
            Grade(id=g_sen, season_id=s2019, name="Seniors", category="senior"),
            Grade(id=g_res, season_id=s2019, name="Reserves", category="senior"),
            Grade(id=other_grade, season_id=other_season, name="Seniors", category="senior"),
        ])
        await db.commit()

    club = None
    other_club = None
    async with Session() as db:
        club = await db.get(Organisation, org_id)
        other_club = await db.get(Organisation, other_org_id)
        user = await db.get(User, user_id)

    def mk(**kw):
        base = dict(player_id=str(p_ruck), season_id=None, grade_id=None, games_played=0,
                    goals=0, behinds=0, bog_count=0, captain_games=0,
                    club_bf_votes=0, comp_bf_votes=0, notes=None)
        base.update(kw)
        return me.AdjustmentIn(**base)

    # ── CRUD through the shipped route bodies ─────────────────────────────
    print("\n── Adjustments CRUD ──")
    async with Session() as db:
        row = await me.create_adjustment(
            mk(season_id=str(s2019), games_played=4, goals=6, behinds=3, bog_count=1,
               club_bf_votes=12, notes="Club record book"),
            current_user=user, club=club, db=db)
        adj_id = row["id"]
        check("season adjustment created", row["goals"], 6)
        check("  ... notes stored", row["notes"], "Club record book")
        logs = (await db.execute(text(
            "SELECT action, summary FROM manual_edit_logs WHERE organisation_id = :o"
        ), {"o": str(org_id)})).mappings().all()
        check("  ... one audit entry written", len(logs), 1)
        check("  ... audit names the player and season",
              "Ruck, Ron (2019)" in logs[0]["summary"], True)

    async with Session() as db:
        check("a second adjustment on the same player+season is refused",
              await status_of(me.create_adjustment(
                  mk(season_id=str(s2019), goals=1), current_user=user, club=club, db=db)), 409)

    async with Session() as db:
        career = await me.create_adjustment(
            mk(games_played=42, goals=55, behinds=30, bog_count=3),
            current_user=user, club=club, db=db)
        career_id = career["id"]
        check("a career-only row sits alongside the season one", career["season_id"], None)

    async with Session() as db:
        check("a grade with no season is refused",
              await status_of(me.create_adjustment(
                  mk(grade_id=str(g_sen), goals=1), current_user=user, club=club, db=db)), 422)
        check("another club's player is not found",
              await status_of(me.create_adjustment(
                  mk(player_id=str(other_player), goals=1), current_user=user, club=club, db=db)), 404)
        check("another club's season is not found",
              await status_of(me.create_adjustment(
                  mk(season_id=str(other_season), goals=1), current_user=user, club=club, db=db)), 404)
        check("a grade from a different season is not found",
              await status_of(me.create_adjustment(
                  mk(season_id=str(s2020), grade_id=str(g_sen), goals=1),
                  current_user=user, club=club, db=db)), 404)

    async with Session() as db:
        listed = await me.list_adjustments(current_user=user, club=club, db=db)
        check("both rows listed", len(listed), 2)
        season_row = next(r for r in listed if r["season_id"])
        check("  ... the season one names its season", season_row["season_name"], "2019")
        check("  ... the career one has no season name",
              next(r for r in listed if not r["season_id"])["season_name"], None)

    async with Session() as db:
        upd = await me.update_adjustment(
            adj_id, mk(season_id=str(s2019), grade_id=str(g_res), goals=9, games_played=4, club_bf_votes=12),
            current_user=user, club=club, db=db)
        check("update rewrites the figures", upd["goals"], 9)
        check("  ... and can attach a grade", upd["grade_id"], str(g_res))

    # ── Reads: the adjustment has to actually show up ─────────────────────
    print("\n── The figures reaching the reads ──")
    async with Session() as db:
        # A synced season sitting underneath, so "additive" is testable.
        await db.execute(text("""
            INSERT INTO afl_player_season_stats
                (id, organisation_id, player_id, season_id, grade_id, games, goals,
                 behinds, bog_count, captain_games)
            VALUES (:i1, :org, :p, :s, NULL, 10, 20, 5, 2, 0),
                   (:i2, :org, :p, :s, :g, 10, 20, 5, 2, 0)
        """), {"i1": str(uuid.uuid4()), "i2": str(uuid.uuid4()), "org": str(org_id),
               "p": str(p_ruck), "s": str(s2019), "g": str(g_sen)})
        await db.commit()

    async with Session() as db:
        totals = await agg.career_totals(db, org_id, [p_ruck])
        t = totals[0]
        check("career goals = synced 20 + season adj 9 + career adj 55", t["goals"], 84)
        check("career games = synced 10 + 4 + 42", t["games"], 56)
        check("a career-only row doesn't invent a season", t["seasons"], 1)

        rows = await agg.season_by_season(db, org_id, p_ruck)
        whole = [r for r in rows if r["grade_id"] is None]
        check("one whole-season row per season, not two", len([r for r in whole if r["season_id"]]), 1)
        s19 = next(r for r in whole if r["season_id"] == s2019)
        check("the 2019 line carries the per-grade adjustment", s19["goals"], 29)
        check("  ... and its games", s19["games"], 14)
        career_line = next(r for r in whole if r["season_id"] is None)
        check("the career-only row is labelled, not nameless",
              career_line["season_name"], "Career adjustment")
        check("  ... and carries its figures", career_line["goals"], 55)
        res_row = next((r for r in rows if r["grade_id"] == g_res), None)
        check("the adjusted grade gets its own row", res_row is not None and res_row["goals"], 9)
        check("the season table now sums to the career total",
              sum(r["goals"] for r in whole), 84)

        by_grade = await agg.grade_breakdown(db, org_id, p_ruck)
        reserves = next((g for g in by_grade if g["grade"] == "Reserves"), None)
        check("by-grade shows the adjusted grade", reserves is not None and reserves["goals"], 9)

    async with Session() as db:
        board = await lb.leaderboard(org_id, stat="goals", limit=200, db=db)
        ron = next(r for r in board["rows"] if str(r["player_id"]) == str(p_ruck))
        check("leaderboard goals include both adjustments", int(ron["value"]), 84)

        scoped = await lb.leaderboard(org_id, stat="goals", season_id=s2019, limit=200, db=db)
        ron_s = next(r for r in scoped["rows"] if str(r["player_id"]) == str(p_ruck))
        check("a season filter drops the career-only row", int(ron_s["value"]), 29)

        votes = await lb.leaderboard(org_id, stat="club_bf_votes", limit=200, db=db)
        check("the vote board reads a manual tally",
              int(next(r for r in votes["rows"] if str(r["player_id"]) == str(p_ruck))["value"]), 12)

    async with Session() as db:
        book = await rec.get_records(org_id, db=db)
        season_goals = [r for r in book["most_goals_in_a_season"] if str(r["player_id"]) == str(p_ruck)]
        check("the season record is ONE summed row, not two", len(season_goals), 1)
        check("  ... reading synced + adjustment", int(season_goals[0]["goals"]), 29)
        career_goals = next(r for r in book["most_goals_career"] if str(r["player_id"]) == str(p_ruck))
        check("the career goals record includes both adjustments", int(career_goals["goals"]), 84)

    async with Session() as db:
        summary = await orgs.get_summary(org_id, db=db)
        top = next(r for r in summary["top_goal_kickers"] if str(r["player_id"]) == str(p_ruck))
        check("the dashboard's top-goals panel includes them", int(top["goals"]), 84)
        check("an adjustment carrying games flags the incomplete W/L/D card",
              summary["has_imported_history"], True)

    async with Session() as db:
        roster = await padm.list_players(current_user=user, club=club, db=db)
        ron_row = next(r for r in roster if r["id"] == str(p_ruck))
        check("the admin roster's goals include them", ron_row["goals"], 84)
        check("  ... and the B&F votes", ron_row["club_bf_votes"], 12)

    async with Session() as db:
        check("another club never sees our adjustment",
              len(await me.list_adjustments(current_user=user, club=other_club, db=db)), 0)
        check("  ... nor in its career totals", await agg.career_totals(db, other_org_id), [])

    # ── A season with an adjustment is not deletable ──────────────────────
    print("\n── Guards ──")
    async with Session() as db:
        empty = uuid.uuid4()
        db.add(Season(id=empty, organisation_id=org_id, name="1970", year=1970))
        await db.commit()
        check("an empty manual season deletes",
              (await sadm.delete_season(str(empty), current_user=user, club=club, db=db))["deleted"], True)
    async with Session() as db:
        listed = await sadm.list_seasons(current_user=user, club=club, db=db)
        row2019 = next(r for r in listed if r["name"] == "2019")
        check("the seasons list counts adjustment rows", row2019["adjustments"], 1)
        check("  ... and their games", row2019["adjustment_games"], 4)
        check("a season carrying an adjustment refuses to delete",
              await status_of(sadm.delete_season(str(s2019), current_user=user, club=club, db=db)), 400)

    # ── CSV import ────────────────────────────────────────────────────────
    print("\n── CSV import ──")
    async with Session() as db:
        tpl = await me.adjustments_template(current_user=user, club=club)
        body = b"".join([chunk async for chunk in tpl.body_iterator]).decode("utf-8-sig")
        parsed = list(csv.DictReader(io.StringIO(body)))
        check("the template round-trips through the importer's own parser", len(parsed), 2)
        check("  ... and shows a blank season for the career-only example",
              parsed[1]["season_name"], "")

    sheet = (
        "player_name,season_name,grade_name,games_played,goals,behinds,bog_count,"
        "captain_games,club_bf_votes,comp_bf_votes,notes\n"
        '"Wing, Wes",2019,Seniors,3,7,2,1,0,4,0,From the 2019 program\n'
        "Wes Wing,2020,,2,1,0,0,0,0,0,\n"
        "Nobody At All,2019,,1,1,0,0,0,0,0,\n"
        "Wes Wing,,Seniors,1,1,0,0,0,0,0,\n"
    )
    async with Session() as db:
        res = await me.import_adjustments(file=Upload(sheet), current_user=user, club=club, db=db)
        check("two good rows imported", res["created"], 2)
        check("  ... an unknown player is reported, not silently dropped", res["errors"], 2)
        check("  ... and named", "Nobody At All" in res["errors_detail"][0]["error"], True)
        check("  ... a grade with no season is refused too",
              "grade needs a season" in res["errors_detail"][1]["error"], True)

    async with Session() as db:
        rows = await me.list_adjustments(current_user=user, club=club, db=db)
        wes = [r for r in rows if r["player_name"] == "Wing, Wes"]
        check("both name spellings landed on one player", len(wes), 2)

    # Re-upload the SAME sheet with a corrected figure — an additive row must
    # be replaced, not stacked, or the correction doubles.
    corrected = sheet.replace('"Wing, Wes",2019,Seniors,3,7', '"Wing, Wes",2019,Seniors,3,11')
    async with Session() as db:
        res2 = await me.import_adjustments(file=Upload(corrected), current_user=user, club=club, db=db)
        check("re-uploading updates rather than duplicating", (res2["created"], res2["updated"]), (0, 2))
    async with Session() as db:
        rows = await me.list_adjustments(current_user=user, club=club, db=db)
        wes2019 = next(r for r in rows if r["player_name"] == "Wing, Wes" and r["season_name"] == "2019")
        check("  ... and the figure is the corrected one, not the sum", wes2019["goals"], 11)

    # ── Undo ──────────────────────────────────────────────────────────────
    print("\n── Undo ──")
    async with Session() as db:
        log_rows = (await db.execute(text(
            "SELECT id, action FROM manual_edit_logs WHERE organisation_id = :o ORDER BY id"
        ), {"o": str(org_id)})).mappings().all()
    by_action = {}
    for r in log_rows:
        by_action.setdefault(r["action"], []).append(r["id"])

    async with Session() as db:
        await me.undo_edit(by_action["import"][1], current_user=user, club=club, db=db)
    async with Session() as db:
        rows = await me.list_adjustments(current_user=user, club=club, db=db)
        wes2019 = next(r for r in rows if r["player_name"] == "Wing, Wes" and r["season_name"] == "2019")
        check("undoing an import puts an overwritten row back", wes2019["goals"], 7)
        check("  ... rather than deleting it", len([r for r in rows if r["player_name"] == "Wing, Wes"]), 2)

    async with Session() as db:
        check("an undone entry can't be undone twice",
              await status_of(me.undo_edit(by_action["import"][1], current_user=user, club=club, db=db)), 409)
        check("another club's audit entry is not found",
              await status_of(me.undo_edit(by_action["import"][0], current_user=user,
                                           club=other_club, db=db)), 404)

    async with Session() as db:
        await me.undo_edit(by_action["import"][0], current_user=user, club=club, db=db)
    async with Session() as db:
        rows = await me.list_adjustments(current_user=user, club=club, db=db)
        check("undoing the first import removes the rows it created",
              len([r for r in rows if r["player_name"] == "Wing, Wes"]), 0)

    async with Session() as db:
        await me.undo_edit(by_action["update"][0], current_user=user, club=club, db=db)
    async with Session() as db:
        rows = await me.list_adjustments(current_user=user, club=club, db=db)
        ron = next(r for r in rows if r["season_id"])
        check("undoing an update puts the earlier figures back", ron["goals"], 6)
        check("  ... and the earlier grade", ron["grade_id"], None)

    async with Session() as db:
        await me.delete_adjustment(int(adj_id), current_user=user, club=club, db=db)
    async with Session() as db:
        check("delete removes the row",
              len([r for r in await me.list_adjustments(current_user=user, club=club, db=db) if r["season_id"]]), 0)
        del_log = (await db.execute(text(
            "SELECT id FROM manual_edit_logs WHERE organisation_id = :o AND action = 'delete'"
        ), {"o": str(org_id)})).scalar()
    async with Session() as db:
        await me.undo_edit(del_log, current_user=user, club=club, db=db)
    async with Session() as db:
        restored = [r for r in await me.list_adjustments(current_user=user, club=club, db=db) if r["season_id"]]
        check("undoing a delete restores it", len(restored), 1)
        check("  ... with its id intact", restored[0]["id"], int(adj_id))
        check("  ... and its figures", restored[0]["goals"], 6)

    async with Session() as db:
        create_log = by_action["create"][0]
        await me.undo_edit(create_log, current_user=user, club=club, db=db)
    async with Session() as db:
        check("undoing a create removes the row",
              len([r for r in await me.list_adjustments(current_user=user, club=club, db=db) if r["season_id"]]), 0)

    # ── Merge and split carry adjustments ─────────────────────────────────
    print("\n── Merge and split ──")
    async with Session() as db:
        await me.create_adjustment(mk(player_id=str(p_dup), season_id=str(s2019), goals=8),
                                   current_user=user, club=club, db=db)
        await me.create_adjustment(mk(player_id=str(p_dup), games_played=5),
                                   current_user=user, club=club, db=db)

    async with Session() as db:
        out = await mg._merge_players_core(db, p_ruck, p_dup, org_id, user)
        check("a merge reports the adjustments it moved", out["adjustments_moved"], 2)
    async with Session() as db:
        moved = (await db.execute(text(
            "SELECT COUNT(*) FROM afl_manual_adjustments WHERE player_id = :p"
        ), {"p": str(p_ruck)})).scalar()
        left = (await db.execute(text(
            "SELECT COUNT(*) FROM afl_manual_adjustments WHERE player_id = :p"
        ), {"p": str(p_dup)})).scalar()
        # The kept player's own career-only row plus the two carried across —
        # the FK cascades, so without the move these would have been deleted
        # outright with the removed player rather than orphaned.
        check("  ... they land on the kept player", moved, 3)
        check("  ... and none are left on the removed one", left, 0)
        merge_log = (await db.execute(text(
            "SELECT id FROM afl_merge_logs WHERE org_id = :o ORDER BY id DESC LIMIT 1"
        ), {"o": str(org_id)})).scalar()

    async with Session() as db:
        await mg.undo_merge_players(mg.UndoMergePlayersRequest(merge_log_id=merge_log),
                                    club=club, current_user=user, db=db)
    async with Session() as db:
        back = (await db.execute(text(
            "SELECT COUNT(*) FROM afl_manual_adjustments WHERE player_id = :p"
        ), {"p": str(p_dup)})).scalar()
        check("undoing the merge hands them back", back, 2)

    async with Session() as db:
        preview = await mg.get_split_preview(p_dup, club=club, _=user, db=db)
        check("the split preview counts a career-only row as unattributable",
              preview["unattributed_imported_rows"], 1)
        check("  ... and shows the season's own figures", preview["seasons"][0]["goals"], 8)

    async with Session() as db:
        out = await mg.split_player(
            mg.SplitPlayerRequest(player_id=str(p_dup), season_ids=[str(s2019)], new_name="Ruck, Ron Jnr"),
            club=club, current_user=user, db=db)
        check("a split moves the season's adjustment", out["adjustments_moved"], 1)
    async with Session() as db:
        left = (await db.execute(text(
            "SELECT COUNT(*) FROM afl_manual_adjustments WHERE player_id = :p AND season_id IS NULL"
        ), {"p": str(p_dup)})).scalar()
        check("  ... and leaves the career-only one behind", left, 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  ! {f}")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
