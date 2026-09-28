"""Milestones measured against the figure the player's profile shows.

Reported off Shoalwater Bay's Milestones page (Sep 2026), four players whose
milestone figure disagreed with their own profile:

    S Hetel    87 short of 6,000 runs    profile 5,924
    A Godfrey   3 short of 200 wickets   profile 478
    P Ritchie   2 short of 200 catches   profile 201
    J Hind     18 short of 3,000 runs    "that is both senior and junior games"

The scan summed the base `player_season_stats` table, which holds none of a
club's imported or hand-entered matches, while the profile reads the effective
view and, under the club's grade default, the scorecards. And the stored
"achieved" milestones only ever grew, so a total over-counted for a day kept
its milestones for ever.

Asserted here, through the SHIPPED functions:

- every player's milestone figures EQUAL the profile's `get_career_*` figures,
  player by player, under a club default that leaves juniors out AND one that
  counts everything;
- a player with junior and open-age records carries BOTH figures, a
  Girls-Under-16 grade counting as junior, and a milestone only the other
  figure is close to arrives as its own entry, in the page payload and the
  notification alike;
- the stored milestones are reconciled: a threshold no longer reached goes, one
  still reached keeps its original date, a dry run writes nothing;
- the sync recomputes them after the scorecards land, and only reconciles when
  the match pull succeeded.

Run on its own database — suites that share one collide on stub tables:
  DATABASE_URL=postgresql+asyncpg://.../verify_milestones python verification/verify_milestone_figures.py
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import aggregations, grade_scope, milestone_scan
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL

MISSING: list[str] = []
try:
    from app.services import milestone_totals
except ImportError as exc:  # pragma: no cover - control run only
    milestone_totals = None
    MISSING.append(str(exc))

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


YEAR = date.today().year
ORG = uuid.uuid4()
S_NOW, S_OLD = uuid.uuid4(), uuid.uuid4()
GR_SENIOR, GR_JUNIOR, GR_GIRLS, GR_WOMENS, GR_OLD = (uuid.uuid4() for _ in range(5))

P_HETEL = uuid.uuid4()     # CA totals 5,913 + one imported match of 11 = 5,924
P_GODFREY = uuid.uuid4()   # CA 197 wickets + imported 281 = 478
P_RITCHIE = uuid.uuid4()   # CA 198 catches + imported 3 = 201
P_HIND = uuid.uuid4()      # 2,271 senior + 711 junior = 2,982
P_JUNIOR = uuid.uuid4()    # junior-only, 480 runs
P_GIRL = uuid.uuid4()      # Girls U16 100 + Women's 395 = 495
P_DORMANT = uuid.uuid4()   # last played 2015
EVERYONE = [P_HETEL, P_GODFREY, P_RITCHIE, P_HIND, P_JUNIOR, P_GIRL, P_DORMANT]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, 'Shoalwater Test', 'swt', true)", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES "
                 "(:a, :o, :na, :ya), (:b, :o, 'Summer 2015/16', 2015)",
                 a=S_NOW, b=S_OLD, o=ORG, na=f"Summer {YEAR}/{str(YEAR + 1)[2:]}", ya=YEAR)
        for gid, sid, name, cats in (
            (GR_SENIOR, S_NOW, "A Grade", ["senior"]),
            (GR_JUNIOR, S_NOW, "Under 17s", ["junior"]),
            (GR_GIRLS, S_NOW, "Girls Under 16", ["junior", "womens"]),
            (GR_WOMENS, S_NOW, "Women's Premier", ["womens"]),
            (GR_OLD, S_OLD, "A Grade", ["senior"]),
        ):
            await ex("INSERT INTO grades (id, season_id, name, category, categories) "
                     "VALUES (:i, :s, :n, :c, :cs)", i=gid, s=sid, n=name, c=cats[0], cs=cats)
        for pid, name in ((P_HETEL, "Hetel, S"), (P_GODFREY, "Godfrey, A"),
                          (P_RITCHIE, "Ritchie, P"), (P_HIND, "Hind, J"),
                          (P_JUNIOR, "Young, K"), (P_GIRL, "Smith, G"),
                          (P_DORMANT, "Gone, D")):
            await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                     "VALUES (:i, :o, :n, true, 'active')", i=pid, o=ORG, n=name)

        async def pss(pid, sid, **kw):
            cols = {"matches": 0, "runs": 0, "wickets": 0, "catches": 0, "batting_innings": 0}
            cols.update(kw)
            await ex(f"""INSERT INTO player_season_stats (player_id, season_id, {', '.join(cols)})
                         VALUES (:p, :s, {', '.join(':' + k for k in cols)})""",
                     p=pid, s=sid, **cols)

        # CA season totals — the `api` branch.
        await pss(P_HETEL, S_OLD, matches=90, runs=5013, batting_innings=90)
        await pss(P_HETEL, S_NOW, matches=10, runs=900, batting_innings=10)
        await pss(P_GODFREY, S_NOW, matches=40, wickets=197)
        await pss(P_RITCHIE, S_NOW, matches=40, catches=198)
        await pss(P_HIND, S_NOW, matches=20, runs=2982, batting_innings=20)
        await pss(P_JUNIOR, S_NOW, matches=8, runs=480, batting_innings=8)
        await pss(P_GIRL, S_NOW, matches=10, runs=495, batting_innings=10)
        await pss(P_DORMANT, S_OLD, matches=40, runs=499, batting_innings=40)

        # Synced scorecards for this season, one game per grade.
        games = {}
        for gid in (GR_SENIOR, GR_JUNIOR, GR_GIRLS, GR_WOMENS):
            g = uuid.uuid4()
            games[gid] = g
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team) "
                     "VALUES (:i, :g, :d, 'Us', 'Them')",
                     i=g, g=gid, d=date(YEAR, 1, 10))

        async def bat(pid, gid, runs, inn=1):
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, "
                     "not_out, did_not_bat) VALUES (:g, :p, :n, :r, false, false)",
                     g=games[gid], p=pid, n=inn, r=runs)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p) "
                     "ON CONFLICT DO NOTHING", g=games[gid], p=pid)

        await bat(P_HETEL, GR_SENIOR, 900)
        await bat(P_HIND, GR_SENIOR, 2271)
        await bat(P_HIND, GR_JUNIOR, 711)
        await bat(P_JUNIOR, GR_JUNIOR, 480)
        await bat(P_GIRL, GR_GIRLS, 100)
        await bat(P_GIRL, GR_WOMENS, 395)
        await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, "
                 "runs, wickets, maidens) VALUES (:g, :p, 2, 10, 40, 197, 0)",
                 g=games[GR_SENIOR], p=P_GODFREY)
        await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, "
                 "run_outs, stumpings) VALUES (:g, :p, 198, 0, 0, 0)",
                 g=games[GR_SENIOR], p=P_RITCHIE)
        for pid in (P_GODFREY, P_RITCHIE):
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p) "
                     "ON CONFLICT DO NOTHING", g=games[GR_SENIOR], p=pid)

        # One imported (manual) match in 2015 — the `manual_game` branch.
        mg = uuid.uuid4()
        await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
                 "opposition) VALUES (:i, :o, :s, :g, :d, 'Mandurah')",
                 i=mg, o=ORG, s=S_OLD, g=GR_OLD, d=date(2015, 11, 7))
        await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
                 "runs, not_out, did_not_bat) VALUES (:m, :p, 1, 11, false, false)",
                 m=mg, p=P_HETEL)
        await ex("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
                 "overs, runs, wickets, maidens) VALUES (:m, :p, 2, 30, 90, 281, 0)",
                 m=mg, p=P_GODFREY)
        await ex("INSERT INTO manual_fielding_stats (manual_game_id, player_id, catches, "
                 "catches_wk, run_outs, stumpings) VALUES (:m, :p, 3, 0, 0, 0)",
                 m=mg, p=P_RITCHIE)

        # The stored milestones, including the ones minted on 10 Sep 2026.
        for pid, mt, v, d in (
            (P_GODFREY, "wickets", 400, date(2024, 3, 1)),
            (P_GODFREY, "wickets", 500, date(2026, 9, 10)),
            (P_RITCHIE, "catches", 200, date(2025, 2, 1)),
            (P_HIND, "runs", 3000, date(2026, 9, 10)),
        ):
            await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, "
                     "achieved_at) VALUES (:p, :t, :v, :d)", p=pid, t=mt, v=v, d=d)
        await s.commit()


async def set_default(categories) -> None:
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET stats_grade_categories = CAST(:c AS jsonb) "
                             "WHERE id = :o"),
                        {"c": None if categories is None else __import__("json").dumps(categories),
                         "o": ORG})
        await s.commit()


async def profile_figures(s, pid, scope):
    b = await aggregations.get_career_batting(s, str(pid), scope=scope) or {}
    w = await aggregations.get_career_bowling(s, str(pid), scope=scope) or {}
    f = await aggregations.get_career_fielding(s, str(pid), scope=scope) or {}
    return {"runs": int(b.get("total_runs") or 0), "wickets": int(w.get("total_wickets") or 0),
            "matches": int(b.get("games") or 0), "catches": int(f.get("total_catches") or 0)}


HAVE_JP = "judge_primary" in inspect.signature(grade_scope.resolve_scope).parameters


async def old_scan_figures(s) -> dict:
    """The previous build's figures, so a control run REPORTS the gap."""
    rows = await milestone_scan.active_player_totals(s, str(ORG))
    out = {}
    for r in rows:
        out[str(r["player_id"])] = {"totals": {
            "runs": int(r["total_runs"]), "wickets": int(r["total_wickets"]),
            "matches": int(r["total_matches"]), "catches": int(r["total_catches"])},
            "split": r.get("split"), "counts": r.get("counts")}
    return out


async def equality_pass(label: str) -> dict:
    """Milestone figures vs the profile's, for every player. Returns the batch."""
    async with Session() as s:
        got = (await milestone_totals.profile_totals(s, ORG, EVERYONE)
               if milestone_totals else await old_scan_figures(s))
        got = {**{str(p): {"totals": None, "split": None, "counts": None} for p in EVERYONE}, **got}
        for pid in EVERYONE:
            scope, _ = await grade_scope.resolve_scope_for_player(s, ORG, str(pid))
            want = await profile_figures(s, pid, scope)
            have = (got.get(str(pid)) or {}).get("totals")
            check(f"[{label}] milestone figures equal the profile's for {pid.hex[:6]}",
                  have == want, f"milestone={have} profile={want}")
        # the two split figures equal the profile under those two selections
        allcats = await grade_scope.resolve_scope(s, ORG, list(grade_scope.GRADE_CATEGORIES))
        nojun = await grade_scope.resolve_scope(s, ORG, list(grade_scope.DEFAULT_CATEGORIES),
                                                **({"judge_primary": True} if HAVE_JP else {}))
        for pid in (P_HIND, P_GIRL):
            sp = (got.get(str(pid)) or {}).get("split") or {}
            check(f"[{label}] {pid.hex[:6]} 'including junior' equals the all-categories profile",
                  sp.get("with_junior") == await profile_figures(s, pid, allcats), str(sp))
            check(f"[{label}] {pid.hex[:6]} 'excluding junior' equals the no-junior profile",
                  sp.get("without_junior") == await profile_figures(s, pid, nojun), str(sp))
    return got


def upcoming_for(rows, pid, stat):
    return [r for r in rows if r["player_id"] == str(pid) and r["type"] == stat]


async def main() -> None:
    await build_schema()
    await seed()
    check("milestone_totals exists", milestone_totals is not None, "; ".join(MISSING))
    check("resolve_scope can judge an explicit pick on primary categories", HAVE_JP)

    print("\n── club counts everything (Shoalwater's own setting) ──")
    await set_default(list(grade_scope.GRADE_CATEGORIES))
    got = await equality_pass("all categories")
    check("Hetel reads 5,924, the imported match counted",
          (got[str(P_HETEL)]["totals"] or {}).get("runs") == 5924, str(got[str(P_HETEL)]["totals"]))
    check("Godfrey reads 478 wickets", (got[str(P_GODFREY)]["totals"] or {}).get("wickets") == 478)
    check("Ritchie reads 201 catches", (got[str(P_RITCHIE)]["totals"] or {}).get("catches") == 201)
    check("Hind's split is 2,982 with his junior runs and 2,271 without",
          (got[str(P_HIND)]["split"] or {}).get("with_junior", {}).get("runs") == 2982
          and (got[str(P_HIND)]["split"] or {}).get("without_junior", {}).get("runs") == 2271,
          str(got[str(P_HIND)]["split"]))
    check("…and his headline counts his junior runs, because the club does",
          got[str(P_HIND)]["counts"] == "with_junior")
    check("a Girls Under 16 grade is junior: the girl's record splits 495 / 395",
          (got[str(P_GIRL)]["split"] or {}).get("without_junior", {}).get("runs") == 395,
          str(got[str(P_GIRL)]["split"]))
    check("a junior-only player carries no split",
          got[str(P_JUNIOR)]["split"] is None)
    check("a senior-only player carries no split", got[str(P_HETEL)]["split"] is None)

    async with Session() as s:
        up = await milestone_scan.upcoming_career_milestones(s, str(ORG))
    h = upcoming_for(up, P_HETEL, "runs")
    check("Hetel is 76 from 6,000, not 87", len(h) == 1 and h[0]["needed"] == 76, str(h))
    g = upcoming_for(up, P_GODFREY, "wickets")
    check("Godfrey is no longer '3 short of 200' — 22 from 500 is out of reach", g == [], str(g))
    r = upcoming_for(up, P_RITCHIE, "catches")
    check("Ritchie is not '2 short of 200' — he passed it", all(x["target"] != 200 for x in r), str(r))
    j = upcoming_for(up, P_HIND, "runs")
    check("Hind is 18 from 3,000 on his headline figure",
          len(j) == 1 and j[0]["needed"] == 18 and not j[0].get("variant"), str(j))
    check("…and the entry carries both figures",
          j and j[0].get("junior_split") == {"with_junior": 2982, "without_junior": 2271}, str(j))
    check("the dormant player is not listed", not [x for x in up if x["player_id"] == str(P_DORMANT)])

    print("\n── the platform default leaves juniors out ──")
    await set_default(None)
    got = await equality_pass("no juniors")
    check("Hind's headline now excludes his junior runs",
          (got[str(P_HIND)]["totals"] or {}).get("runs") == 2271 and got[str(P_HIND)]["counts"] == "without_junior",
          str(got[str(P_HIND)]))
    check("the junior-only player is widened to his juniors, not zero",
          (got[str(P_JUNIOR)]["totals"] or {}).get("runs") == 480, str(got[str(P_JUNIOR)]))
    async with Session() as s:
        up = await milestone_scan.upcoming_career_milestones(s, str(ORG))
    j = upcoming_for(up, P_HIND, "runs")
    check("Hind's 2,271 is out of reach, so his only runs entry is the variant",
          len(j) == 1 and j[0].get("variant") is True, str(j))
    check("…measured with his junior runs, 18 from 3,000",
          j and j[0].get("counts") == "with_junior" and j[0].get("current") == 2982 and j[0].get("needed") == 18,
          str(j))
    check("the junior-only player is 20 from 500",
          [x["needed"] for x in upcoming_for(up, P_JUNIOR, "runs")] == [20])

    print("\n── the notification carries both figures ──")
    from app.services import notification_scan
    async with Session() as s:
        items = await notification_scan._src_milestone_upcoming(s, ORG, {})
    hind = [i for i in items if i["payload"].get("player_id") == str(P_HIND)
            and i["payload"].get("type") == "runs"]
    check("Hind's milestone is emailed", len(hind) == 1, str(hind))
    if hind:
        check("…the variant's basis is in its dedupe key",
              hind[0]["dedupe_key"].endswith(":with_junior"), hind[0]["dedupe_key"])
        check("…the title says which figure it is",
              "including junior matches" in hind[0]["title"], hind[0]["title"])
        check("…and the body gives both",
              "2,982 including junior matches" in hind[0]["body"]
              and "2,271 excluding them" in hind[0]["body"], hind[0]["body"])

    print("\n── the stored milestones ──")
    await set_default(list(grade_scope.GRADE_CATEGORIES))
    from app.services.sync import _compute_milestones
    params = inspect.signature(_compute_milestones).parameters
    check("the writer can reconcile and dry-run", "reconcile" in params and "dry_run" in params)
    if "reconcile" in params:
        async with Session() as s:
            dry = await _compute_milestones(s, EVERYONE, ORG, reconcile=True, dry_run=True)
        async with Session() as s:
            n500 = (await s.execute(text("SELECT COUNT(*) FROM milestones WHERE player_id = :p "
                                         "AND milestone_value = 500"), {"p": P_GODFREY})).scalar()
        check("a dry run names the phantom 500 wickets",
              (str(P_GODFREY), "wickets", 500) in dry["removed"], str(dry["removed"]))
        check("…and writes nothing", n500 == 1)
        async with Session() as s:
            rep = await _compute_milestones(s, EVERYONE, ORG, reconcile=True)
        async with Session() as s:
            rows = {(str(p), t, v): d for p, t, v, d in (await s.execute(text(
                "SELECT player_id, milestone_type, milestone_value, achieved_at FROM milestones"
            ))).all()}
        check("the phantom 500 wickets is gone", (str(P_GODFREY), "wickets", 500) not in rows)
        check("400 wickets stays, with its original date",
              rows.get((str(P_GODFREY), "wickets", 400)) == date(2024, 3, 1))
        check("Ritchie's real 200 catches stays", (str(P_RITCHIE), "catches", 200) in rows)
        check("Hind's 3,000 was never reached and goes",
              (str(P_HIND), "runs", 3000) not in rows)
        check("Hetel's 5,000 runs is added",
              (str(P_HETEL), "runs", 5000) in rows and (str(P_HETEL), "runs", 5000) in rep["added"])
        async with Session() as s:
            again = await _compute_milestones(s, EVERYONE, ORG, reconcile=True)
        check("a second run changes nothing", again == {"added": [], "removed": []}, str(again))
        async with Session() as s:
            await s.execute(text("INSERT INTO milestones (player_id, milestone_type, milestone_value, "
                                 "achieved_at) VALUES (:p, 'wickets', 500, :d)"),
                            {"p": P_GODFREY, "d": date(2026, 9, 10)})
            await s.commit()
        async with Session() as s:
            add_only = await _compute_milestones(s, EVERYONE, ORG)
        check("without reconcile nothing is removed (a failed match pull only adds)",
              add_only["removed"] == [])

    print("\n── wiring ──")
    src = Path("app/services/sync.py").read_text()
    tail = src.find("Recompute milestones against the figures the profile shows")
    check("the sync has an end-of-run milestone step", tail != -1)
    tail = tail if tail != -1 else 0
    check("the sync recomputes milestones after the game-level pass",
          src.index("gr_stats = await sync_grassroots_game_level_data(") < tail)
    check("…after the import reconcile", src.index("reconcile_imported_totals(org_id_str)") < tail)
    check("…and reconciles only when the match pull did not fail",
          'reconcile=not stats.get("match_pull_failed")' in src)
    check("the aggregate-only branches agree with aggregations'",
          milestone_totals is not None
          and tuple(milestone_totals.RESIDUAL_SOURCES) == tuple(aggregations._RESIDUAL_SOURCES))
    check("the scan no longer reads the base table for its figures",
          not hasattr(milestone_scan, "_TOTALS_SQL"))
    me = Path("app/routers/manual_entries.py").read_text()
    check("manual entries reconcile", "_compute_milestones(db, ids, org_id, reconcile=True)" in me)
    pl = Path("app/routers/players.py").read_text()
    check("the player's own upcoming milestones read the shared figures",
          "milestone_totals.profile_totals(db, player.organisation_id" in pl)

    print("\n── the batched query binds the players ──")
    async with Session() as s:
        plan = "\n".join((await s.execute(text(
            "EXPLAIN SELECT pss.player_id, SUM(pss.runs) FROM v_effective_player_season_stats pss "
            "WHERE pss.player_id = ANY(CAST(:pids AS uuid[])) GROUP BY pss.player_id"),
            {"pids": [str(p) for p in EVERYONE]})).scalars())
    check("the player filter reaches the base table", "player_id = ANY" in plan, plan[:300])
    await finish()


async def finish() -> None:
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
