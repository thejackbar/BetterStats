"""Verification: merging a Fantasy player must not delete them from the teams that
picked them, and an admin can put a team right and type in scores. Real Postgres.

Reported (Leederville): a player was added by hand before he had played, so
managers could pick him. When he was merged into his real record, he disappeared
from every team that had picked him. Every Fantasy table that points at a player is
`ON DELETE CASCADE` or `SET NULL`, and none was on `merge_carry.CARRIED`.

Runs the SHIPPED `admin._merge_players_core` and `undo_merge`, the shipped
`routers/fantasy` admin route bodies, and `fantasy_engine`.

CONTROL (`--control`): the same merge with `merge_carry` as it was before the fix
(`CONTROL_REV`). It
must lose the pick on exactly the reported behaviour.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_player_merge.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException
from sqlalchemy import text

import verify_fantasy_unsettle as base
from verify_merge_carry import EXTRA_DDL, FakeUser
from app.models.db import Organisation, Player, BattingInnings, GameAppearance, FantasySeason
from app.routers import admin as admin_router
from app.routers import fantasy as fr
from app.routers.admin import _merge_players_core, undo_merge, UndoMergeRequest

Session, check = base.Session, base.check
ORG, SQ_X, SQ_Y, R1, R2, FS_ID = base.ORG, base.SQ_X, base.SQ_Y, base.R1, base.R2, base.FS_ID
A, B = base.A, base.B
M, K, N, Z, M2, K2, M3, K3, M4, K4, M5, K5, M6, K6, BT, BT2 = (uuid.uuid4() for _ in range(16))     # M manual Raja, K his real record, N a new player, Z another club's player
REPO = Path(__file__).resolve().parent.parent.parent
# `merge_carry` as it was before this fix (the parent of the commit that added the
# Fantasy tables). A moving rev such as HEAD would stop reproducing the bug the day
# the fix is committed.
CONTROL_REV = "853bfe9"
USER = type("U", (), {"id": uuid.uuid4()})()


async def q(sql, **p):
    async with Session() as s:
        return (await s.execute(text(sql), p)).all()


async def picks(squad) -> set:
    return {str(r[0]) for r in await q("SELECT player_id FROM fantasy_squad_players WHERE squad_id=:s", s=squad)}


async def club():
    async with Session() as s:
        return await s.get(Organisation, ORG)


async def setup() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
    await base.seed()
    async with Session() as s:
        s.add_all([
            Player(id=M, name="Raja Pannu", organisation_id=ORG),                       # added by hand, no games
            Player(id=K, name="Raja Pannu", organisation_id=ORG, grassroots_id="raja-ca"),   # the real record
            Player(id=N, name="Nina New", organisation_id=ORG),
        ])
        await s.flush()
        gid = (await s.execute(text("SELECT id FROM games ORDER BY played_at LIMIT 1"))).scalar()   # the round 1 game
        s.add(GameAppearance(game_id=gid, player_id=K, team_name="Alpha"))
        s.add(BattingInnings(game_id=gid, player_id=K, innings_number=1, runs=40, balls=30, fours=0, sixes=0,
                             dismissal_type="bowled", not_out=False))
        for p in (M, K, N):
            s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                         base_price=5, current_price=5))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=M, role="batter", purchase_price=5, added_round=1))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=M, role="batter", purchase_price=5, added_round=1))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=K, role="batter", purchase_price=5, added_round=2))  # Y holds BOTH records
        await s.commit()
        await s.execute(text("""INSERT INTO fantasy_transactions (squad_id, type, player_id, detail)
                                VALUES (:s, 'transfer_in', :p, '{}')"""), {"s": SQ_X, "p": M})
        await s.commit()
    org = await club()
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)     # round 1 scored, M in the lineups


async def merge(control=False, keep=None, remove=None) -> dict:
    keep, remove = keep or K, remove or M
    if control:
        src = subprocess.check_output(["git", "show", f"{CONTROL_REV}:backend/app/services/merge_carry.py"], cwd=REPO, text=True)
        tmp = Path(__file__).resolve().parent / "_merge_carry_control.py"
        tmp.write_text(src)
        try:
            spec = importlib.util.spec_from_file_location("merge_carry_control", tmp)
            old = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old)
            saved, admin_router.merge_carry = admin_router.merge_carry, old
            try:
                async with Session() as s:
                    return await _merge_players_core(s, keep, remove, ORG, FakeUser())
            finally:
                admin_router.merge_carry = saved
        finally:
            tmp.unlink(missing_ok=True)
    async with Session() as s:
        return await _merge_players_core(s, keep, remove, ORG, FakeUser())


async def main_checks() -> None:
    org = await club()
    print("1. Merge the hand-added player into his real record")
    x_before = await picks(SQ_X)
    check("he is in X's and Y's teams to start with", str(M) in x_before and str(M) in await picks(SQ_Y))
    res = await merge()
    px, py = await picks(SQ_X), await picks(SQ_Y)
    check("X still has him, now under his real record", str(K) in px and str(M) not in px, repr(px))
    check("X's other picks are untouched", {str(A), str(B)} <= px and len(px) == 3, repr(px))
    check("Y held both records: one pick, no clash", str(K) in py and str(M) not in py and len(py) == 2, repr(py))
    pool = {str(r[0]) for r in await q("SELECT player_id FROM fantasy_pool_players WHERE fantasy_season_id=:f", f=FS_ID)}
    check("his pool entry moved to the real record", str(K) in pool and str(M) not in pool, repr(pool))
    tx = [str(r[0]) for r in await q("SELECT player_id FROM fantasy_transactions WHERE squad_id=:s", s=SQ_X)]
    check("the audit log row follows him", tx == [str(K)], repr(tx))
    snap = (await q("SELECT lineup::text FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_X, r=R1))[0][0]
    check("round 1's stored lineup names the real record", str(K) in snap and str(M) not in snap)
    check("the merge reports what it carried", (res.get("carried") or {}).get("fantasy_squad_players") == 1, repr(res.get("carried")))

    print("2. Settling again counts him")
    before = float((await q("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_X, r=R1))[0][0])
    ft_before = (await q("SELECT free_transfers FROM fantasy_squads WHERE id=:s", s=SQ_X))[0][0]
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)
    after = float((await q("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_X, r=R1))[0][0])
    ft_after = (await q("SELECT free_transfers FROM fantasy_squads WHERE id=:s", s=SQ_X))[0][0]
    check("X's round 1 score now includes his real games", after > before, repr((before, after)))
    check("re-settling a scored round banks no second free transfer", ft_after == ft_before, repr((ft_before, ft_after)))

    print("3. Undo hands the picks back to the hand-added record")
    async with Session() as s:
        log = (await s.execute(text("SELECT id FROM merge_logs WHERE org_id=:o ORDER BY id DESC LIMIT 1"), {"o": str(ORG)})).scalar()
        await undo_merge(UndoMergeRequest(merge_log_id=log, org_id=str(ORG)), db=s, current_user=FakeUser())
    ux = await picks(SQ_X)
    check("X has the hand-added record again and not the real one", str(M) in ux and str(K) not in ux, repr(ux))
    async with Session() as s:   # merge again so the rest runs on the merged state
        await _merge_players_core(s, K, M, ORG, FakeUser())

    print("4. Putting a team right by hand")
    async with Session() as s:
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id=:s AND player_id=:p"), {"s": SQ_X, "p": K})
        await s.commit()          # the damage as it is in production: X lost him
    async with Session() as s:
        out = await fr.add_squad_player(str(SQ_X), fr.SquadPickBody(player_id=str(K), from_round=1), club=org, db=s, _=None)
    check("he is back in X's team", str(K) in await picks(SQ_X))
    check("round 1 was scored again", out["rescored"]["settled"] >= 1, repr(out))
    check("a short team is warned about, not refused", any("players" in w for w in out["warnings"]), repr(out["warnings"]))
    try:
        async with Session() as s:
            await fr.add_squad_player(str(SQ_X), fr.SquadPickBody(player_id=str(K)), club=org, db=s, _=None)
        check("adding someone already in the team is refused", False, "no error")
    except HTTPException as e:
        check("adding someone already in the team is refused", e.status_code == 409, str(e.status_code))
    async with Session() as s:
        s.add(Organisation(id=uuid.uuid4(), name="Other CC", slug="other", is_active=True))
        await s.commit()
        other = (await s.execute(text("SELECT id FROM organisations WHERE slug='other'"))).scalar()
    other_org = type("O", (), {"id": other})()
    try:
        async with Session() as s:
            await fr.add_squad_player(str(SQ_X), fr.SquadPickBody(player_id=str(N)), club=other_org, db=s, _=None)
        check("another club's admin cannot edit this team", False, "no error")
    except HTTPException as e:
        check("another club's admin cannot edit this team", e.status_code == 404, str(e.status_code))
    async with Session() as s:
        await fr.add_squad_player(str(SQ_X), fr.SquadPickBody(player_id=str(N), replace_player_id=str(K)), club=org, db=s, _=None)
    check("a swap replaces the pick", await picks(SQ_X) >= {str(N)} and str(K) not in await picks(SQ_X))
    async with Session() as s:
        await fr.remove_squad_player(str(SQ_X), str(N), 1, club=org, db=s, _=None)
    check("a removal takes him out", str(N) not in await picks(SQ_X))
    async with Session() as s:
        await fr.add_squad_player(str(SQ_X), fr.SquadPickBody(player_id=str(K)), club=org, db=s, _=None)

    print("5. Typed-in scores")
    async with Session() as s:
        await fr.add_squad_player(str(SQ_Y), fr.SquadPickBody(player_id=str(N)), club=org, db=s, _=None)
    y0 = float((await q("SELECT raw_points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_Y, r=R1))[0][0])
    async with Session() as s:
        await fr.set_manual_score(str(R1), str(N), fr.ManualScoreBody(points=25, note="42 off 30"), club=org, user=USER, db=s, _=None)
    y1 = float((await q("SELECT raw_points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_Y, r=R1))[0][0])
    check("a team's round score includes the typed-in points", y1 > y0, repr((y0, y1)))
    for label, action in (("a settle", lambda s: fr.settle_round(str(R1), club=org, db=s, _=None)),
                          ("the live refresh", lambda s: fr.settle_due(str(FS_ID), club=org, _=None, db=s))):
        async with Session() as s:
            await action(s)
        v = (await q("SELECT total_points FROM fantasy_player_round_scores WHERE round_id=:r AND player_id=:p", r=R1, p=N))[0][0]
        check(f"{label} leaves the typed-in score alone", float(v) == 25.0, repr(v))
    async with Session() as s:
        await fr.unsettle_round(str(R1), club=org, db=s, _=None)
    n = (await q("SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id=:r AND player_id=:p", r=R1, p=N))[0][0]
    check("unsettling a round keeps what was typed in", n == 1, str(n))
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)
    async with Session() as s:
        lst = await fr.list_manual_scores(str(FS_ID), club=org, db=s, _=None)
    check("the list shows it with its note", [(r["name"], r["points"], r["note"]) for r in lst["scores"]] == [("Nina New", 25.0, "42 off 30")], repr(lst))
    async with Session() as s:
        await fr.clear_manual_score(str(R1), str(N), club=org, db=s, _=None)
    n = (await q("SELECT COUNT(*) FROM fantasy_player_round_scores WHERE round_id=:r AND player_id=:p", r=R1, p=N))[0][0]
    y2 = float((await q("SELECT raw_points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=SQ_Y, r=R1))[0][0])
    check("removing it hands the round back to the scorecards", n == 0 and y2 == y0, repr((n, y2, y0)))
    try:
        async with Session() as s:
            await fr.set_manual_score(str(R1), str(Z), fr.ManualScoreBody(points=5), club=org, user=USER, db=s, _=None)
        check("a player outside the pool is refused", False, "no error")
    except HTTPException as e:
        check("a player outside the pool is refused", e.status_code == 404, str(e.status_code))

    print("6. Teams already hit by the old merge are put back")
    from app.services import fantasy_merge_repair as repair
    async with Session() as s:
        s.add_all([Player(id=M2, name="Sam Hand", organisation_id=ORG), Player(id=K2, name="Sam Hand", organisation_id=ORG, grassroots_id="sam-ca")])
        await s.flush()
        s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=M2, role="allrounder", base_price=6, current_price=6))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=M2, role="allrounder", purchase_price=6, added_round=1, is_captain=False))
        await s.commit()
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)         # round 1's lineup snapshots now name M2 in X's team
    await asyncio.sleep(1.1)                                           # the merge happens after the round was scored
    await merge(control=True, keep=K2, remove=M2)                      # the OLD merge: deletes the pick
    check("(damage reproduced) X lost him in the old merge", str(M2) not in await picks(SQ_X) and str(K2) not in await picks(SQ_X))
    async with Session() as s:
        found = await repair.find_lost_picks(s, ORG)
    mine = [f for f in found if f["removed_id"] == str(M2)]
    check("the repair finds exactly the team that held him", [f["squad_id"] for f in mine] == [str(SQ_X)], repr(found))
    check("it takes his role from the stored lineup", mine and mine[0]["role"] == "allrounder", repr(mine))
    check("a dry run changed nothing", str(K2) not in await picks(SQ_X))
    n_before = len(await picks(SQ_X))
    async with Session() as s:
        n = await repair.restore(s, ORG, mine, USER.id)
        await s.commit()
    px = await picks(SQ_X)
    check("applied: he is back in X's team under his real record", n == 1 and str(K2) in px and len(px) == n_before + 1, repr(px))
    pool_row = await q("SELECT role FROM fantasy_pool_players WHERE fantasy_season_id=:f AND player_id=:p", f=FS_ID, p=K2)
    check("and in the pool, with the role the team knew him by", [r[0] for r in pool_row] == ["allrounder"], repr(pool_row))
    aud = await q("SELECT action FROM audit_logs WHERE target_id=:s AND action='fantasy_restore_merged_pick'", s=str(SQ_X))
    check("it writes an audit entry", len(aud) == 1, repr(aud))
    async with Session() as s:
        again = [f for f in await repair.find_lost_picks(s, ORG) if f["removed_id"] == str(M2)]
    check("running it again finds nothing more to do", not again, repr(again))
    async with Session() as s:
        shorts = await repair.find_short_squads(s, ORG, set())
    check("teams short of players with no evidence are listed, not guessed at", all("team_name" in r for r in shorts) and len(shorts) >= 1, repr(shorts))

    print("7. Who is missing, from a backup taken before the merge")
    import os
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    live_url = os.environ["DATABASE_URL"]
    bk_url = live_url.replace("/fantasy_test", "/backup_test")
    admin = create_async_engine(live_url.replace("/fantasy_test", "/postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text("DROP DATABASE IF EXISTS backup_test"))
        await c.execute(text("CREATE DATABASE backup_test"))
    await admin.dispose()
    async with Session() as s:
        s.add_all([Player(id=M3, name="Tom Hand", organisation_id=ORG), Player(id=K3, name="Tom Hand", organisation_id=ORG, grassroots_id="tom-ca")])
        await s.flush()
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=M3, role="bowler", purchase_price=5, added_round=1, is_captain=False))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=M3, role="bowler", purchase_price=5, added_round=1, is_vice_captain=False))
        await s.commit()
    bk = create_async_engine(bk_url)
    async with bk.begin() as c:                                        # the backup: the two tables the repair reads
        await c.execute(text("CREATE TABLE fantasy_squads (id uuid, team_name text, fantasy_season_id uuid, organisation_id uuid)"))
        await c.execute(text("""CREATE TABLE fantasy_squad_players (squad_id uuid, player_id uuid, role text,
                                is_captain boolean, is_vice_captain boolean, added_round int)"""))
        for r in await q("SELECT id, team_name, fantasy_season_id, organisation_id FROM fantasy_squads"):
            await c.execute(text("INSERT INTO fantasy_squads VALUES (:a,:b,:c,:d)"), dict(a=r[0], b=r[1], c=r[2], d=r[3]))
        for r in await q("SELECT squad_id, player_id, role, is_captain, is_vice_captain, added_round FROM fantasy_squad_players"):
            await c.execute(text("INSERT INTO fantasy_squad_players VALUES (:a,:b,:c,:d,:e,:f)"), dict(a=r[0], b=r[1], c=r[2], d=r[3], e=r[4], f=r[5]))
    await merge(control=True, keep=K3, remove=M3)                      # the old merge, after the backup
    async with Session() as s:
        listed = await repair.merged_since_fantasy_began(s, ORG)
    check("the merged players are listed as candidates", "Tom Hand" in [m["removed"] for m in listed], repr(listed))
    async with Session() as s, AsyncSession(bk) as b:
        found = await repair.find_lost_picks_from_backup(s, b, ORG)
    mine = [f for f in found if f["removed_id"] == str(M3)]
    check("the backup names exactly the two teams that held him", sorted(f["squad_id"] for f in mine) == sorted([str(SQ_X), str(SQ_Y)]), repr(found))
    check("and only him: a pick that is still live is not touched", all(f["removed_id"] == str(M3) for f in found), repr([f["player_name"] for f in found]))
    check("he is resolved to his real record, with his role", all(f["keep_id"] == str(K3) and f["role"] == "bowler" for f in mine), repr(mine))
    async with Session() as s:
        await repair.restore(s, ORG, mine, USER.id)
        await s.commit()
    check("applied: both teams have him back", str(K3) in await picks(SQ_X) and str(K3) in await picks(SQ_Y))
    async with Session() as s, AsyncSession(bk) as b:
        again = await repair.find_lost_picks_from_backup(s, b, ORG)
    check("running it again finds nothing", not [f for f in again if f["removed_id"] == str(M3)], repr(again))
    await bk.dispose()

    print("8. Pool players with no stats, and who holds them (the Scarborough report)")
    from app.services import fantasy_pool_check as pc
    AT, AT2, CH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as s:
        s.add_all([Player(id=AT, name="Ashton Taylor", organisation_id=ORG),                          # added by hand
                   Player(id=AT2, name="Taylor, Ashton", organisation_id=ORG, grassroots_id="at-ca"),   # the synced twin
                   Player(id=CH, name="Chris Hansberry", organisation_id=ORG)])                        # added by hand, no twin
        await s.flush()
        gid = (await s.execute(text("SELECT id FROM games ORDER BY played_at DESC LIMIT 1"))).scalar()
        s.add(GameAppearance(game_id=gid, player_id=AT2, team_name="Alpha"))
        s.add(BattingInnings(game_id=gid, player_id=AT2, innings_number=1, runs=22, balls=20, fours=0, sixes=0,
                             dismissal_type="bowled", not_out=False))
        for p in (AT, CH):
            s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="batter",
                                         role_source="admin", base_price=5, current_price=5))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=AT, role="batter", purchase_price=5))
        await s.commit()
    async with Session() as s:
        rows = {r["name"]: r for r in await pc.zero_stat_pool_players(s, ORG)}
    check("a hand-added player with no games is listed, with the profile that holds his stats",
          [t["player_id"] for t in rows.get("Ashton Taylor", {}).get("twins", [])] == [str(AT2)], repr(rows.get("Ashton Taylor")))
    check("the twin's name is matched however it is written ('Taylor, Ashton')", rows.get("Ashton Taylor", {}).get("twins", [{}])[0].get("games") == 1)
    check("it says how many teams picked him", rows.get("Ashton Taylor", {}).get("picked_by") == 1)
    check("a hand-added player with no twin is listed on his own", rows.get("Chris Hansberry", {}).get("twins") == [], repr(rows.get("Chris Hansberry")))
    check("a pool player who has games is not listed", "Ann Ace" not in rows and "Taylor, Ashton" not in rows, repr(list(rows)))
    res = await merge(keep=AT2, remove=AT)
    async with Session() as s:
        rows2 = {r["name"] for r in await pc.zero_stat_pool_players(s, ORG)}
    check("after merging the pair, he is gone from the list", "Ashton Taylor" not in rows2, repr(rows2))
    check("and the team that picked him still has him, under the synced profile", str(AT2) in await picks(SQ_X))

    print("9. Merged, then undone (Raja Pannu): back as himself, but out of the teams")
    async with Session() as s:
        s.add_all([Player(id=M4, name="Raja Pannu", organisation_id=ORG), Player(id=K4, name="Raja Pannu", organisation_id=ORG, grassroots_id="raja2-ca")])
        await s.flush()
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=M4, role="batter", purchase_price=5, added_round=1, is_captain=False))
        await s.commit()
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)       # the lineup snapshot names him
    await asyncio.sleep(1.1)
    bk2 = create_async_engine(bk_url)
    async with bk2.begin() as c:                                      # a second backup, taken while he was in the team
        await c.execute(text("DELETE FROM fantasy_squad_players"))
        for r in await q("SELECT squad_id, player_id, role, is_captain, is_vice_captain, added_round FROM fantasy_squad_players"):
            await c.execute(text("INSERT INTO fantasy_squad_players VALUES (:a,:b,:c,:d,:e,:f)"), dict(a=r[0], b=r[1], c=r[2], d=r[3], e=r[4], f=r[5]))
    await merge(control=True, keep=K4, remove=M4)                      # the old merge deletes his pick
    async with Session() as s:
        log = (await s.execute(text("SELECT id FROM merge_logs WHERE org_id=:o AND removed_player_id=:p"), {"o": str(ORG), "p": str(M4)})).scalar()
        await undo_merge(UndoMergeRequest(merge_log_id=log, org_id=str(ORG)), db=s, current_user=FakeUser())
    check("(reproduced) he exists again but is in no team", str(M4) not in await picks(SQ_X) and bool(await q("SELECT 1 FROM players WHERE id=:p", p=M4)))
    async with Session() as s:
        listed = await repair.merged_since_fantasy_began(s, ORG)
    check("the merged list still shows the undone merge, marked", any(m["removed"] == "Raja Pannu" and m["undone"] for m in listed), repr(listed))
    async with Session() as s:
        by_snapshot = [f for f in await repair.find_lost_picks(s, ORG) if f["removed_id"] == str(M4)]
    check("the lineup snapshots find him, to be restored as himself", [(f["squad_id"], f["keep_id"]) for f in by_snapshot] == [(str(SQ_X), str(M4))], repr(by_snapshot))
    async with Session() as s, AsyncSession(bk2) as b:
        by_backup = [f for f in await repair.find_lost_picks_from_backup(s, b, ORG) if f["removed_id"] == str(M4)]
    check("a backup finds him too", [(f["squad_id"], f["keep_id"]) for f in by_backup] == [(str(SQ_X), str(M4))], repr(by_backup))
    async with Session() as s:
        await repair.restore(s, ORG, by_backup, USER.id)
        await s.commit()
    check("applied: he is back in the team under his own id, and in the pool", str(M4) in await picks(SQ_X)
          and bool(await q("SELECT 1 FROM fantasy_pool_players WHERE player_id=:p", p=M4)))
    async with Session() as s, AsyncSession(bk2) as b:
        again = [f for f in await repair.find_lost_picks_from_backup(s, b, ORG) if f["removed_id"] == str(M4)]
    check("and a second run finds nothing", not again)
    await bk2.dispose()

    print("10. No backup and no key: read the deleted picks still on disk")
    async with Session() as s:
        await s.execute(text("ALTER TABLE fantasy_squad_players SET (autovacuum_enabled = false)"))   # as at the club: not yet vacuumed
        s.add_all([Player(id=M5, name="Dead Row", organisation_id=ORG), Player(id=K5, name="Dead Row", organisation_id=ORG, grassroots_id="dr-ca")])
        await s.flush()
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=M5, role="keeper", is_captain=True, purchase_price=5, added_round=1))
        await s.commit()
    await merge(control=True, keep=K5, remove=M5)                      # the old merge: the row is deleted
    check("(reproduced) the pick is gone from the live table", str(M5) not in await picks(SQ_Y) and str(K5) not in await picks(SQ_Y))
    async with Session() as s:
        found = [f for f in await repair.find_lost_picks_from_dead_rows(s, ORG) if f["removed_id"] == str(M5)]
        await s.rollback()
    check("the deleted row is still on disk, and is matched to his real record", [(f["squad_id"], f["keep_id"]) for f in found] == [(str(SQ_Y), str(K5))], repr(found))
    check("with his role and the captain's armband read back from the page", found and found[0]["role"] == "keeper" and found[0]["was_captain"] is True, repr(found))
    ext = await q("SELECT 1 FROM pg_extension WHERE extname='pageinspect'")
    check("the dry run leaves nothing installed behind", not ext, repr(ext))
    async with Session() as s:
        every = await repair.read_deleted_picks(s)
        await s.rollback()
    pairs = {(str(r["squad_id"]), str(r["player_id"])) for r in every}
    check("it reads deleted versions (the merged picks are there)", (str(SQ_Y), str(M5)) in pairs and (str(SQ_X), str(M3)) in pairs, repr(len(pairs)))
    check("and never a pick that was not deleted (X's own A and B were only ever inserted)",
          (str(SQ_X), str(A)) not in pairs and (str(SQ_X), str(B)) not in pairs, repr(sorted(pairs)[:3]))
    async with Session() as s:
        await repair.restore(s, ORG, found, USER.id)
        await s.commit()
    row = await q("SELECT role, is_captain FROM fantasy_squad_players WHERE squad_id=:s AND player_id=:p", s=SQ_Y, p=K5)
    caps = (await q("SELECT COUNT(*) FROM fantasy_squad_players WHERE squad_id=:s AND is_captain", s=SQ_Y))[0][0]
    check("applied: he is back with his role", [r[0] for r in row] == ["keeper"], repr(row))
    check("and the team keeps its one captain (it already had one, so no second armband)", caps == 1 and [r[1] for r in row] == [False], repr((caps, row)))
    async with Session() as s:
        again = [f for f in await repair.find_lost_picks_from_dead_rows(s, ORG) if f["removed_id"] == str(M5)]
        await s.rollback()
    check("and a second run finds nothing", not again, repr(again))

    print("11. Fill short teams with the top scorers")
    from app.services import fantasy_fill_short as ff
    P1, P2, P3, P4 = (uuid.uuid4() for _ in range(4))
    async with Session() as s:
        s.add_all([Player(id=P1, name="Top Keeper", organisation_id=ORG), Player(id=P2, name="Second Keeper", organisation_id=ORG),
                   Player(id=P3, name="Top Bowler", organisation_id=ORG), Player(id=P4, name="Zero Bowler", organisation_id=ORG)])
        await s.flush()
        for pid, role, pts, price in ((P1, "keeper", 90, 9), (P2, "keeper", 50, 6), (P3, "bowler", 70, 7), (P4, "bowler", 0, 15)):
            s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=pid, role=role,
                                         base_price=price, current_price=price, total_points=pts))
        # rules: 3 picks, 1 keeper + 2 bowlers. X holds one batter (so is short two), Y holds a keeper and a bowler (short one).
        await s.execute(text("UPDATE fantasy_seasons SET rules = CAST(:r AS JSONB) WHERE id=:f"),
                        {"r": '{"squad_size": 3, "role_quota": {"keeper": 1, "batter": 0, "allrounder": 0, "bowler": 2}}', "f": FS_ID})
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id IN (:x, :y)"), {"x": SQ_X, "y": SQ_Y})
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=A, role="batter"))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=P1, role="keeper"))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=P3, role="bowler"))
        await s.commit()
    async with Session() as s:
        plans = {p["team_name"]: p for p in await ff.plan_fill(s, ORG)}
        await s.rollback()
    check("both short teams are planned, whole teams are not", set(plans) == {"X Team", "Y Team"}, repr(list(plans)))
    check("Y holds a keeper and one bowler and wants a second bowler: the only other one is Zero Bowler",
          [c["name"] for c in plans["Y Team"]["adds"]] == ["Zero Bowler"], repr(plans["Y Team"]["adds"]))
    check("X (short two, wants a keeper and two bowlers) gets the top keeper and the top-scoring bowler, not the priciest",
          {c["name"] for c in plans["X Team"]["adds"]} == {"Top Keeper", "Top Bowler"}, repr([c["name"] for c in plans["X Team"]["adds"]]))
    check("each takes the role it is short of, so the quota is met",
          sorted(c["role"] for c in plans["X Team"]["adds"]) == ["bowler", "keeper"], repr(plans["X Team"]["adds"]))
    check("a dry run changed nothing", len(await picks(SQ_X)) == 1)
    async with Session() as s:
        n = await ff.apply_fill(s, ORG, await ff.plan_fill(s, ORG), USER.id)
        await s.commit()
    check("applied: the right number of players were added", n == 3, str(n))
    for sq in (SQ_X, SQ_Y):
        check(f"team now has 3 players, no duplicates ({'X' if sq == SQ_X else 'Y'})", len(await picks(sq)) == 3)
    aud = await q("SELECT COUNT(*) FROM audit_logs WHERE action='fantasy_fill_short_team'")
    check("an audit entry per team", aud[0][0] == 2, repr(aud))
    async with Session() as s:
        again = await ff.plan_fill(s, ORG)
        await s.rollback()
    check("a second run has nothing to do", again == [], repr(again))

    print("12. Only players who were merged")
    from datetime import datetime, timezone, timedelta
    async with Session() as s:
        merged_ids = await ff.merged_player_ids(s, ORG)
        await s.rollback()
    check("the eligible set is the live records of merged players (kept profiles, and undone ones)",
          str(K3) in merged_ids and str(K5) in merged_ids and str(M4) in merged_ids and str(M3) not in merged_ids and str(P1) not in merged_ids, repr(len(merged_ids)))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_pool_players SET total_points = 1 WHERE player_id = ANY(CAST(:ids AS uuid[]))"), {"ids": [str(K3)]})
        await s.execute(text("UPDATE fantasy_pool_players SET total_points = 5 WHERE player_id = ANY(CAST(:ids AS uuid[]))"), {"ids": [str(K5)]})
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id = :y AND player_id IN (:a, :b)"), {"y": SQ_Y, "a": P1, "b": P3})
        await s.commit()
    async with Session() as s:
        every = {p["team_name"]: p for p in await ff.plan_fill(s, ORG)}
        merged_only = {p["team_name"]: p for p in await ff.plan_fill(s, ORG, only_merged=True)}
        await s.rollback()
    check("without the restriction Y takes a top scorer from the whole pool",
          {c["name"] for c in every["Y Team"]["adds"]} & {"Top Keeper", "Top Bowler"}, repr([c["name"] for c in every["Y Team"]["adds"]]))
    chosen = [c for c in merged_only["Y Team"]["adds"]]
    check("with it, every player added is a merged player", chosen and all(str(c["player_id"]) in merged_ids for c in chosen), repr([c["name"] for c in chosen]))
    check("and it is the highest scorer among the merged players the team does not hold",
          chosen[0]["name"] == "Dead Row" and float(chosen[0]["total_points"]) == 5.0, repr([(c["name"], float(c["total_points"])) for c in chosen]))
    future = datetime.now(timezone.utc) + timedelta(days=1)
    async with Session() as s:
        nothing = await ff.merged_player_ids(s, ORG, since=future)
        await s.rollback()
    check("merged-since a later date leaves no one eligible, so nothing is added from the whole pool", nothing == set(), repr(nothing))

    print("13. Nothing is lost: a hand-added player in EVERY Fantasy table that can point at a player")
    from app.services import merge_carry
    async with Session() as s:
        fks = [(r[0], r[1]) for r in (await s.execute(text("""
            SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'f' AND c.confrelid = 'players'::regclass AND c.conrelid::regclass::text LIKE 'fantasy%'
            ORDER BY 1, 2"""))).all()]
        await s.rollback()
    carried = {(t, c) for t, c, _i, _u in merge_carry.CARRIED}
    check("every Fantasy column that points at a player is on the merge's carry list (so a new table fails here)",
          set(fks) <= carried and len(fks) >= 11, repr(sorted(set(fks) - carried)))
    async with Session() as s:
        s.add_all([Player(id=M6, name="Everywhere Man", organisation_id=ORG), Player(id=K6, name="Everywhere Man", organisation_id=ORG, grassroots_id="ev-ca")])
        await s.flush()
        s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=M6, role="batter", base_price=5, current_price=5))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=M6, role="batter", purchase_price=5))
        await s.commit()
        mgr = (await s.execute(text("SELECT id FROM fantasy_managers WHERE organisation_id=:o LIMIT 1"), {"o": ORG})).scalar()
        lg = (await s.execute(text("""INSERT INTO fantasy_leagues (fantasy_season_id, organisation_id, kind, name)
                                      VALUES (:f, :o, 'draft', 'Draft') RETURNING id"""), {"f": FS_ID, "o": ORG})).scalar()
        dr = (await s.execute(text("""INSERT INTO fantasy_drafts (league_id, organisation_id, lot_player_id)
                                      VALUES (:l, :o, :p) RETURNING id"""), {"l": lg, "o": ORG, "p": M6})).scalar()
        await s.execute(text("INSERT INTO fantasy_draft_picks (draft_id, pick_index, round_no, manager_id, player_id) VALUES (:d, 1, 1, :m, :p)"), {"d": dr, "m": mgr, "p": M6})
        await s.execute(text("""INSERT INTO fantasy_waiver_claims (league_id, organisation_id, manager_id, add_player_id, drop_player_id)
                                VALUES (:l, :o, :m, :p, :x), (:l, :o, :m, :x, :p)"""), {"l": lg, "o": ORG, "m": mgr, "p": M6, "x": A})
        await s.execute(text("INSERT INTO fantasy_transactions (squad_id, type, player_id, detail) VALUES (:s, 'transfer_in', :p, '{}')"), {"s": SQ_X, "p": M6})
        await s.execute(text("""UPDATE fantasy_squad_round_scores SET captain_player_id=:p, vice_captain_player_id=:p, dropped_player_id=:p
                                WHERE squad_id=:s AND round_id=:r"""), {"p": M6, "s": SQ_X, "r": R1})
        await s.execute(text("""INSERT INTO fantasy_player_round_scores (fantasy_season_id, round_id, player_id, total_points, base_points, breakdown, games_counted)
                                VALUES (:f, :r, :p, 7, 7, '{}', 1)"""), {"f": FS_ID, "r": R1, "p": M6})
        await s.commit()

    async def refs(who):
        out = {}
        async with Session() as s:
            for t, c in fks:
                out[(t, c)] = (await s.execute(text(f"SELECT COUNT(*) FROM {t} WHERE {c} = :p"), {"p": who})).scalar()
        return out
    before = await refs(M6)
    check("the seed puts him in every one of those tables (so the check below is not vacuous)", all(n >= 1 for n in before.values()),
          repr({k: n for k, n in before.items() if n < 1}))
    await merge(keep=K6, remove=M6)
    after_m, after_k = await refs(M6), await refs(K6)
    check("nothing is left pointing at the merged-away record, in any Fantasy table", all(n == 0 for n in after_m.values()),
          repr({k: n for k, n in after_m.items() if n}))
    check("and every row he had is now on the real record, none lost, none duplicated", after_k == before,
          repr({k: (before[k], after_k[k]) for k in before if before[k] != after_k[k]}))

    print("14. The Merge button")
    async with Session() as s:
        s.add_all([Player(id=BT, name="Bryce Test", organisation_id=ORG), Player(id=BT2, name="Test, Bryce", organisation_id=ORG, grassroots_id="bt-ca")])
        await s.flush()
        gid = (await s.execute(text("SELECT id FROM games ORDER BY played_at DESC LIMIT 1"))).scalar()
        s.add(GameAppearance(game_id=gid, player_id=BT2, team_name="Alpha"))
        s.add(BattingInnings(game_id=gid, player_id=BT2, innings_number=1, runs=31, balls=25, fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=BT, role="batter", role_source="admin", base_price=5, current_price=5))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=BT, role="batter", purchase_price=5))
        await s.commit()
    async with Session() as s:
        lst = await fr.unmatched_players(str(FS_ID), club=org, db=s, _=None)
    mine = [p for p in lst["pairs"] if p["player_id"] == str(BT)]
    check("the list offers the pair, with the games on the real profile", mine and mine[0]["twins"][0]["player_id"] == str(BT2) and mine[0]["twins"][0]["games"] == 1, repr(mine))
    for label, keep, remove in (("a pair that is not on the list", str(N), str(BT)), ("the pair reversed", str(BT), str(BT2))):
        try:
            async with Session() as s:
                await fr.merge_pool_player(str(FS_ID), fr.MergePoolPlayerBody(keep_player_id=keep, remove_player_id=remove), club=org, user=FakeUser(), db=s, _=None)
            check(f"{label} is refused", False, "no error")
        except HTTPException as e:
            check(f"{label} is refused", e.status_code == 409, str(e.status_code))
    check("and nothing changed", str(BT) in await picks(SQ_X))
    async with Session() as s:
        res = await fr.merge_pool_player(str(FS_ID), fr.MergePoolPlayerBody(keep_player_id=str(BT2), remove_player_id=str(BT)), club=org, user=FakeUser(), db=s, _=None)
    check("merging the listed pair works and reports what it carried and re-scored",
          res.get("status") == "merged" and "rescored" in res and (res.get("carried") or {}).get("fantasy_squad_players") == 1, repr(res))
    check("the team that picked him still has him, under the real profile", str(BT2) in await picks(SQ_X) and str(BT) not in await picks(SQ_X))
    pts = await q("SELECT r.round_number, prs.total_points FROM fantasy_player_round_scores prs JOIN fantasy_rounds r ON r.id = prs.round_id WHERE prs.player_id=:p", p=BT2)
    check("his stats now count: the round his game was in was scored again with him", pts and all(float(p[1]) > 0 for p in pts), repr(pts))
    check("and the team's score for that round includes him", float((await q("SELECT COALESCE(SUM(points),0) FROM fantasy_squad_round_scores WHERE squad_id=:s", s=SQ_X))[0][0]) > 0)
    async with Session() as s:
        gone = await fr.unmatched_players(str(FS_ID), club=org, db=s, _=None)
    check("he is off the list", all(p["player_id"] != str(BT) for p in gone["pairs"]))
    import inspect
    check("the endpoint is gated by the merge permission as well as the Fantasy one",
          "require_cap(MANAGE_MERGES)" in inspect.getsource(fr).split("async def merge_pool_player")[1].split("\n\n")[0] + inspect.getsource(fr).split("async def merge_pool_player")[1][:400])


async def run_control() -> int:
    await setup()
    await merge(control=True)
    px = await picks(SQ_X)
    check("(control) X still has him after the merge, under the real record", str(K) in px, f"X's picks: {len(px)} players, lost him")
    check("(control) X's team is still the size it was", len(px) == 3, str(len(px)))
    return base.FAIL


async def main() -> int:
    if "--control" in sys.argv:
        return await run_control()
    await setup()
    await main_checks()
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
