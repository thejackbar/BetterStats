"""Club teaser snapshots (migration 314, services/club_teaser.py).

Runs the SHIPPED builder, persistence, selection and batch runner against a
real Postgres, with a scripted stand-in for Cricket Australia so no live call
is made.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

# A control run against the previous commit must REPORT the feature missing
# rather than die on an ImportError before a single check runs.
MISSING: list[str] = []
try:
    from app.services import club_teaser as ct
    from app.services.club_teaser_ddl import STATEMENTS, DOWNGRADE
except ImportError as exc:  # pragma: no cover - control run only
    ct, STATEMENTS, DOWNGRADE = None, [], []
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


def g() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------
# The stand-in for Cricket Australia
# --------------------------------------------------------------------------
def bat_row(pid, name, runs, inns=10, no=1, hs=80, hs_no=False):
    return {"id": pid, "name": name, "statistics": {
        "battingAggregate": runs, "battingInnings": inns, "battingNotOuts": no,
        "battingHighScore": hs, "isBattingHSNotOut": hs_no, "batting50s": 2, "batting100s": 0}}


def bowl_row(pid, name, wk, runs=200, balls=300, best="4-20"):
    return {"id": pid, "name": name, "statistics": {
        "bowlingWickets": wk, "bowlingRuns": runs, "bowlingBalls": balls, "bowlingBestInnings": best}}


def field_row(pid, name, c=3, ro=1, st=0):
    return {"id": pid, "name": name, "statistics": {
        "fieldingTotalCatches": c, "fieldingRunOuts": ro, "fieldingStumpings": st}}


def ladder(org, rows):
    """rows: [(rank, name, org_id, played, won, lost)]"""
    return {"ladders": [{"name": "Overall", "pools": [{"teams": [
        {"rank": r, "displayName": n, "owningOrganisation": {"id": o},
         "ladderData": [{"id": "played", "val": p}, {"id": "won", "val": w}, {"id": "lost", "val": l},
                        {"id": "competitionPoints", "val": w * 4}]}
        for (r, n, o, p, w, l) in rows]}]}]}


class FakeAPI:
    """Scripted CA. ``world`` maps: seasons -> list, teams[season] -> teams,
    stats[(kind, season, grade|None)] -> rows, ladders[grade] -> payload."""

    def __init__(self, world, fail=False):
        self.w, self.calls, self.fail, self.log = world, 0, fail, []

    def _hit(self, *a):
        self.calls += 1
        self.log.append(a)
        if self.fail:
            raise RuntimeError("upstream exploded")

    async def seasons(self, org):
        self._hit("seasons"); return self.w.get("seasons", [])

    async def teams(self, org, season):
        self._hit("teams", season); return self.w.get("teams", {}).get(season, [])

    async def _stats(self, kind, season, grade):
        self._hit(kind, season, grade)
        return self.w.get("stats", {}).get((kind, season, grade), [])

    async def batting(self, org, season, grade=None): return await self._stats("bat", season, grade)
    async def bowling(self, org, season, grade=None): return await self._stats("bowl", season, grade)
    async def fielding(self, org, season, grade=None): return await self._stats("field", season, grade)

    async def ladder(self, grade):
        self._hit("ladder", grade); return self.w.get("ladders", {}).get(grade)


ORG = g()
S_NEW, S_CUR, S_OLD = g(), g(), g()
G_A, G_B, G_U14 = g(), g(), g()


def team(grade_id, grade_name):
    return {"id": g(), "grades": [{"id": grade_id, "name": grade_name}]}


def world_plain():
    """A club with no junior grades whose NEWEST season has no stats yet."""
    return {
        "seasons": [
            {"id": S_OLD, "name": "Summer 2024/25", "startDate": "2024-10-01"},
            {"id": S_NEW, "name": "Summer 2026/27", "startDate": "2026-10-01"},
            {"id": S_CUR, "name": "Summer 2025/26", "startDate": "2025-10-01"},
        ],
        "teams": {S_CUR: [team(G_A, "A Grade"), team(G_B, "B Grade")],
                  S_OLD: [team(G_A, "A Grade")], S_NEW: [team(G_A, "A Grade")]},
        "stats": {
            ("bat", S_CUR, None): [bat_row("p1", "John Smith", 432), bat_row("p2", "McDonald, Lee", 389),
                                   bat_row("p3", "********", 999), bat_row("p4", "Tom Kelly", 362, hs=101, hs_no=True)],
            ("bowl", S_CUR, None): [bowl_row("p5", "Alan Parkinson", 28, best="5-32"), bowl_row("p1", "John Smith", 24)],
            ("field", S_CUR, None): [field_row("p1", "John Smith", 12, 3, 2), field_row("p2", "Lee McDonald", 11, 1, 0)],
        },
        "ladders": {
            G_A: ladder(ORG, [(1, "Other", g(), 20, 15, 5), (3, "Us A", ORG, 20, 12, 6)]),
            G_B: ladder(ORG, [(2, "Us B", ORG, 18, 10, 7)]),
        },
    }


def world_prev_ladders(w):
    w["ladders"][G_A] = ladder(ORG, [(3, "Us A", ORG, 20, 12, 6)])
    return w


async def main() -> None:
    if MISSING:
        check("club teaser service is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed"); return

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in DOWNGRADE: await c.execute(text(s))
    async with engine.begin() as c:
        for _ in range(3):
            for s in STATEMENTS: await c.execute(text(s))
    check("the DDL applies three times over", True)
    async with engine.begin() as c:
        cols = {r[0] for r in (await c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='club_teaser_snapshots'"))).all()}
    check("the table carries version, hash, token and the re-pull date",
          {"version", "data_hash", "token", "next_pull_at", "image_version"} <= cols, str(cols))
    main_src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    alembic_src = (Path(__file__).resolve().parent.parent / "alembic/versions/314_club_teaser_snapshots.py").read_text()
    check("alembic and the lifespan run the same statement list",
          "club_teaser_ddl import STATEMENTS" in main_src and "club_teaser_ddl import STATEMENTS" in alembic_src)

    # ---------------- pure helpers ----------------
    check("'Smith, John' and 'John Smith' both read J. Smith",
          ct.display_name("Smith, John") == "J. Smith" == ct.display_name("John Smith"))
    check("a single token name is kept, not initialled", ct.display_name("Madonna") == "Madonna")
    check("a redacted junior name is recognised", ct.is_redacted("********") and ct.is_redacted("")
          and not ct.is_redacted("Tom Kelly"))
    check("an under-age grade reads junior and a senior one does not",
          ct.is_junior_grade("Under 14") and ct.is_junior_grade("U16 Girls") and not ct.is_junior_grade("A Grade"))
    merged = ct.merge_rows([[bat_row("x", "Ann Lee", 100, 5, 1, hs=60)], [bat_row("x", "Ann Lee", 50, 4, 0, hs=90)]])
    ms = merged[0]["statistics"]
    check("one player's rows across grades add up, and the best score is kept",
          len(merged) == 1 and ms["battingAggregate"] == 150 and ms["battingInnings"] == 9 and ms["battingHighScore"] == 90, str(ms))
    mb = ct.merge_rows([[bowl_row("y", "Bo Ling", 3, best="3-20")], [bowl_row("y", "Bo Ling", 4, best="4-50")]])
    check("a best-bowling figure keeps the better of the two, not the larger string",
          mb[0]["statistics"]["bowlingBestInnings"] == "4-50", mb[0]["statistics"]["bowlingBestInnings"])
    check("more wickets beats fewer runs conceded", ct._better_bowling("5-90", "4-10") and not ct._better_bowling("2-1", "3-40"))
    lad = ct.our_ladder_row(ladder(ORG, [(1, "Other", g(), 10, 9, 1), (4, "Us", ORG.upper(), 10, 5, 5)]), ORG)
    check("our ladder row is found on the OWNING ORGANISATION, case-insensitively",
          lad and lad["rank"] == 4 and lad["teams"] == 2, str(lad))
    check("a ladder we are not on gives no row", ct.our_ladder_row(ladder(ORG, [(1, "X", g(), 1, 1, 0)]), ORG) is None
          and ct.our_ladder_row(None, ORG) is None)
    t = ct.ladder_totals([{"played": 20, "won": 12, "lost": 6}, {"played": 18, "won": 10, "lost": 7}])
    check("ladder totals: 38 played, 22 won, 13 lost, 3 draws, 58%",
          (t["matches"], t["wins"], t["losses"], t["draws"], t["win_rate"]) == (38, 22, 13, 3, 58), str(t))
    h1 = ct.content_hash({"a": 1, "b": [1, 2]}); h2 = ct.content_hash({"b": [1, 2], "a": 1})
    check("the content hash ignores key order and moves with content",
          h1 == h2 and h1 != ct.content_hash({"a": 2, "b": [1, 2]}))

    today = date(2026, 9, 29)
    d = lambda **k: ct.next_pull_delay("ok", today=today, guid="x", **k)
    check("a season in play is re-read in about a week",
          timedelta(days=7) <= d(season_start_=date(2026, 7, 1)) <= timedelta(days=7 * 1.2 + 0.01))
    check("an old season settles to about 45 days", d(season_start_=date(2024, 10, 1)) >= timedelta(days=45))
    check("an old season with a NEWER one listed is watched weekly, not every 45 days",
          d(season_start_=date(2024, 10, 1), season_pending=True) < timedelta(days=9))
    errs = [ct.next_pull_delay("error", attempts=n, guid="x", today=today) for n in (1, 2, 3, 4, 5, 6, 99)]
    check("errors back off 1 -> 3 -> 7 -> 14 -> 30 days and then stop growing",
          errs[0] < errs[1] < errs[2] < errs[3] < errs[4] and errs[5] == errs[4] == errs[6]
          and errs[0] >= timedelta(days=1) and errs[4] >= timedelta(days=30))
    check("the per-club jitter is stable and never more than 20%",
          ct.next_pull_delay("empty", guid="abc", today=today) == ct.next_pull_delay("empty", guid="abc", today=today)
          and all(ct.next_pull_delay("empty", guid=str(i), today=today) <= timedelta(days=14 * 1.2 + 0.01) for i in range(200)))
    check("clubs are spread by the jitter rather than all coming due on one night",
          len({ct.next_pull_delay("empty", guid=str(i), today=today) for i in range(200)}) > 50)

    # ---------------- pulling ----------------
    api = FakeAPI(world_prev_ladders(world_plain()))
    r = await ct.pull_club(api, ORG, {"name": "Applecross CC", "state": "WA"})
    s = r["snapshot"]
    check("a plain club pulls to status ok", r["status"] == "ok" and s is not None, str(r.get("error")))
    check("the newest season has no stats yet so the snapshot uses the previous one and says a newer one is coming",
          s["season"]["name"] == "Summer 2025/26" and r["season_pending"] is True)
    check("seasons are ordered by date, not by the order CA listed them",
          [x["id"] for x in ct.order_seasons(api.w["seasons"])] == [S_NEW, S_CUR, S_OLD])
    check("history says how many seasons and the first year", s["history"] == {"seasons_listed": 3, "first_year": 2024}, str(s["history"]))
    check("batting leads with the top scorer and skips the redacted 999",
          [p["name"] for p in s["batting"]] == ["J. Smith", "L. McDonald", "T. Kelly"]
          and all(p["runs"] != 999 for p in s["batting"]), str(s["batting"]))
    check("the average is runs over dismissals", s["batting"][0]["average"] == round(432 / 9, 2), str(s["batting"][0]))
    check("bowling leads with the most wickets and carries economy", s["bowling"][0]["name"] == "A. Parkinson"
          and s["bowling"][0]["wickets"] == 28 and s["bowling"][0]["economy"] == 4.0, str(s["bowling"][0]))
    check("fielding ranks by dismissals", s["fielding"][0]["name"] == "J. Smith" and s["fielding"][0]["catches"] == 12)
    recs = {x["label"]: x for x in s["records"]}
    check("season records: the top score keeps its not-out star and the best figures come through",
          recs["Most Individual Runs"]["value"] == "101*" and recs["Best Bowling Figures"]["value"] == "5-32", str(recs))
    check("the ladder rows come from our own team in each grade",
          {(x["grade"], x["rank"]) for x in s["ladders"]} == {("A Grade", 3), ("B Grade", 2)}, str(s["ladders"]))
    check("totals add the grades (38 played, 22 won)", s["totals"]["matches"] == 38 and s["totals"]["wins"] == 22)
    check("the previous season is compared", s["totals"]["prev"] and s["totals"]["prev"]["matches"] == 20
          and s["totals"]["matches_vs_prev_pct"] == 90, str(s["totals"]))
    check("the call count is recorded and is nothing like a sync", 0 < r["calls"] <= 30, str(r["calls"]))
    check("no junior-only fetch was made for a club with no junior grades",
          all(a[2] is None for a in api.log if a[0] in ("bat", "bowl", "field") and a[1] == S_CUR))

    # juniors
    wj = world_plain()
    wj["teams"][S_CUR] = [team(G_A, "A Grade"), team(G_U14, "Under 14")]
    wj["stats"] = {
        ("bat", S_CUR, None): [bat_row("p1", "John Smith", 432), bat_row("kid", "Jimmy Junior", 900)],
        ("bat", S_CUR, G_A): [bat_row("p1", "John Smith", 432)],
        ("bat", S_CUR, G_U14): [bat_row("kid", "Jimmy Junior", 900)],
        ("bowl", S_CUR, G_A): [bowl_row("p5", "Alan Parkinson", 28)],
        ("bowl", S_CUR, G_U14): [bowl_row("kid", "Jimmy Junior", 40)],
        ("field", S_CUR, G_A): [field_row("p1", "John Smith")],
    }
    apij = FakeAPI(wj)
    rj = await ct.pull_club(apij, ORG, {})
    sj = rj["snapshot"]
    names = {p["name"] for k in ("batting", "bowling", "fielding") for p in sj[k]}
    check("a club with junior grades shows senior players only", rj["status"] == "ok" and "J. Junior" not in names
          and "J. Smith" in names, str(names))
    check("junior stats are never fetched for the tables, only the senior grade's",
          not any(a[0] in ("bowl", "field") and a[2] == G_U14 for a in apij.log))
    check("junior grades' ladders are left out of the totals", all(x["grade"] != "Under 14" for x in sj["ladders"]))

    wo = world_plain()
    wo["teams"][S_CUR] = [team(G_U14, "Under 14"), team(g(), "Under 12 Girls")]
    ro = await ct.pull_club(FakeAPI(wo), ORG, {})
    check("a junior-only club is skipped and no snapshot is built", ro["status"] == "junior_only" and ro["snapshot"] is None)

    re_ = await ct.pull_club(FakeAPI({"seasons": []}), ORG, {})
    check("a club with no seasons is 'empty'", re_["status"] == "empty" and re_["snapshot"] is None)
    ws = world_plain(); ws["stats"] = {}
    check("a club whose seasons all have no stats is 'empty'", (await ct.pull_club(FakeAPI(ws), ORG, {}))["status"] == "empty")
    apip = FakeAPI(ws)
    await ct.pull_club(apip, ORG, {})
    check("the search for a season with stats is bounded",
          sum(1 for a in apip.log if a[0] == "bat") <= ct.MAX_SEASON_PROBES)
    rx = await ct.pull_club(FakeAPI(world_plain(), fail=True), ORG, {})
    check("an upstream failure is a result, never an exception",
          rx["status"] == "error" and "upstream exploded" in (rx["error"] or ""))

    # ---------------- persistence ----------------
    async with Session() as s_:
        await s_.execute(text("DELETE FROM club_teaser_snapshots"))
        await s_.execute(text("DELETE FROM marketing_clubs"))
        await s_.commit()

    async def mk(name, **kw):
        cid = str(uuid.uuid4())
        vals = {"id": cid, "guid": kw.pop("guid", g()), "name": name, "kind": "club", "excluded": False,
                "ni": False, "trial": "[]", "existing": None}
        vals.update(kw)
        async with Session() as s_:
            if vals["existing"]:
                await s_.execute(text("INSERT INTO organisations (id, name, is_active) VALUES (CAST(:i AS uuid), :n, true)"),
                                 {"i": vals["existing"], "n": name})
            await s_.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested,
                trial_modules, existing_org_id, status, source)
                VALUES (CAST(:id AS uuid), :guid, :name, :kind, :excluded, :ni, CAST(:trial AS jsonb),
                        CAST(:existing AS uuid), 'new', 'grassroots_api')"""), vals)
            await s_.commit()
        return {"id": cid, "guid": vals["guid"], "name": name}

    club1 = await mk("Applecross CC", guid=ORG)
    now = datetime.now(timezone.utc)
    async with Session() as s_:
        out1 = await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(world_prev_ladders(world_plain())), ORG, club1), now=now)
    async with Session() as s_:
        row = (await s_.execute(text("SELECT * FROM club_teaser_snapshots"))).mappings().one()
    tok = row["token"]
    check("the first pull writes the snapshot at version 1 with a token",
          row["status"] == "ok" and row["version"] == 1 and out1["changed"] and len(tok) >= 16)
    check("the next pull date is set", row["next_pull_at"] and row["next_pull_at"] > now)
    check("the snapshot is stored as queryable JSON", row["snapshot"]["batting"][0]["name"] == "J. Smith")

    later = now + timedelta(days=8)
    async with Session() as s_:
        out2 = await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(world_prev_ladders(world_plain())), ORG, club1), now=later)
        row2 = (await s_.execute(text("SELECT * FROM club_teaser_snapshots"))).mappings().one()
    check("re-pulling identical data does NOT move the version (so no image re-render)",
          out2["changed"] is False and row2["version"] == 1 and row2["changed_at"] == row["changed_at"]
          and row2["pulled_at"] > row["pulled_at"])
    check("the preview token survives a refresh (links already sent must keep working)", row2["token"] == tok)

    w3 = world_prev_ladders(world_plain())
    w3["stats"][("bat", S_CUR, None)].append(bat_row("p9", "New Guy", 1000))
    async with Session() as s_:
        out3 = await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(w3), ORG, club1), now=later + timedelta(days=8))
        row3 = (await s_.execute(text("SELECT * FROM club_teaser_snapshots"))).mappings().one()
    check("changed data moves the version and replaces the snapshot",
          out3["changed"] and row3["version"] == 2 and row3["snapshot"]["batting"][0]["name"] == "N. Guy")

    async with Session() as s_:
        oute = await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(w3, fail=True), ORG, club1), now=later + timedelta(days=20))
        rowe = (await s_.execute(text("SELECT * FROM club_teaser_snapshots"))).mappings().one()
    check("a failed pull keeps the last good snapshot", rowe["snapshot"]["batting"][0]["name"] == "N. Guy"
          and rowe["status"] == "ok" and rowe["version"] == 2)
    check("a failed pull records the error, counts the attempt and backs off",
          rowe["attempts"] == 1 and "exploded" in (rowe["last_error"] or "")
          and rowe["next_pull_at"] < later + timedelta(days=20) + timedelta(days=1.3))
    async with Session() as s_:
        await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(w3, fail=True), ORG, club1), now=later + timedelta(days=22))
        rowe2 = (await s_.execute(text("SELECT attempts, next_pull_at FROM club_teaser_snapshots"))).mappings().one()
    check("the second failure backs off further", rowe2["attempts"] == 2 and rowe2["next_pull_at"] > later + timedelta(days=22) + timedelta(days=3))
    async with Session() as s_:
        await ct.save_result(s_, club1, await ct.pull_club(FakeAPI(w3), ORG, club1), now=later + timedelta(days=30))
        rowr = (await s_.execute(text("SELECT attempts, last_error FROM club_teaser_snapshots"))).mappings().one()
    check("a good pull after failures clears the attempt count and the error", rowr["attempts"] == 0 and rowr["last_error"] is None)

    # ---------------- who is due ----------------
    async with Session() as s_:
        await s_.execute(text("DELETE FROM club_teaser_snapshots")); await s_.commit()
    fresh = await mk("Never Pulled CC")
    customer = await mk("Customer CC", existing=str(uuid.uuid4()))
    excluded = await mk("Excluded CC", excluded=True)
    dontcall = await mk("Not Interested CC", ni=True)
    manual = await mk("Manual CC", guid="manual:abc")
    trialing = await mk("Trialing CC", trial='["select"]')
    emailable = await mk("Emailable CC")
    async with Session() as s_:
        await s_.execute(text("INSERT INTO marketing_club_contacts (id, marketing_club_id, email, subscribed, source) "
                              "VALUES (gen_random_uuid(), CAST(:c AS uuid), 'sec@x.com', true, 'api')"), {"c": emailable["id"]})
        await s_.commit()
    async with Session() as s_:
        due = await ct.due_clubs(s_, 100)
    names_due = [c["name"] for c in due]
    check("a customer, an excluded club, a do-not-contact club and a manual placeholder are never targets",
          not ({"Customer CC", "Excluded CC", "Not Interested CC", "Manual CC"} & set(names_due)), str(names_due))
    check("a club already in a sales trial is left out by default", "Trialing CC" not in names_due)
    async with Session() as s_:
        with_t = [c["name"] for c in await ct.due_clubs(s_, 100, include_trialists=True)]
    check("...and included when asked for", "Trialing CC" in with_t)
    check("a club with an emailable contact is pulled ahead of one with none", names_due.index("Emailable CC") < names_due.index("Never Pulled CC"), str(names_due))
    async with Session() as s_:
        check("the limit is honoured", len(await ct.due_clubs(s_, 1)) == 1)

    # ---------------- the Directory's type filters ----------------
    junior = await mk("Northside Junior CC")
    school = await mk("Hillcrest School Cricket")
    carn = await mk("Echuca Carnival XI")
    rep = await mk("Metro Representative Cricket")
    plain = await mk("Plain Suburban CC")
    async with Session() as s_:
        tn = [c["name"] for c in await ct.due_clubs(s_, 100, type_modes=ct.DEFAULT_TYPE_MODES)]
        no_filter = [c["name"] for c in await ct.due_clubs(s_, 100)]
        only_jr = [c["name"] for c in await ct.due_clubs(s_, 100, type_modes={"junior": "include"})]
        junk = [c["name"] for c in await ct.due_clubs(s_, 100, type_modes={"nonsense": "exclude", "junior": "bogus"})]
    check("the default type filters leave out juniors, schools, carnivals and rep orgs",
          not ({"Northside Junior CC", "Hillcrest School Cricket", "Echuca Carnival XI",
                "Metro Representative Cricket"} & set(tn)) and "Plain Suburban CC" in tn, str(tn))
    check("with no type filter they are all targets again",
          {"Northside Junior CC", "Hillcrest School Cricket", "Plain Suburban CC"} <= set(no_filter))
    check("include narrows to just that type", only_jr == ["Northside Junior CC"], str(only_jr))
    check("unknown keys and modes are ignored, not treated as a filter", set(junk) == set(no_filter))
    check("excluded clubs stay out under any filter", "Excluded CC" not in no_filter and "Excluded CC" not in tn)
    dry_t = await ct.run_batch(100, session_maker=Session, api_factory=FakeAPI, dry_run=True,
                               type_modes=ct.DEFAULT_TYPE_MODES)
    check("a dry run reports per-club detail for the sample", len(dry_t["detail"]) == dry_t["due"]
          and all("name" in d for d in dry_t["detail"]))
    async with Session() as s_:
        await s_.execute(text("DELETE FROM marketing_clubs WHERE id = ANY(CAST(:ids AS uuid[]))"),
                         {"ids": [c["id"] for c in (junior, school, carn, rep, plain)]})
        await s_.commit()

    # ---------------- the segment field ----------------
    from app.services import comms_segments as cs
    check("the segment field exists and is directory-only",
          "teaser_snapshot" in cs.DIRECTORY_FIELDS and "teaser_snapshot" in cs.DIR_MULTI_FIELDS)
    check("an all-unknown selection drops the rule rather than widening it silently",
          cs._teaser_clause(["bogus"]) is None and cs._teaser_clause([]) is None)
    sql = str(cs._teaser_clause(["OK", "none"]).compile(compile_kwargs={"literal_binds": True}))
    check("states are matched case-insensitively and 'none' means no snapshot row",
          "club_teaser_snapshots" in sql and "NOT (EXISTS" in sql.upper().replace("  ", " "), sql)

    # ---------------- the batch ----------------
    worlds = {}
    def factory():
        return FakeAPI(world_prev_ladders(world_plain()))
    class BoomAPI(FakeAPI):
        async def seasons(self, org): raise RuntimeError("boom")
    calls = {"n": 0}
    def mixed():
        calls["n"] += 1
        return BoomAPI({}) if calls["n"] == 2 else factory()
    dry = await ct.run_batch(100, session_maker=Session, api_factory=factory, dry_run=True)
    async with Session() as s_:
        n0 = await s_.scalar(text("SELECT count(*) FROM club_teaser_snapshots"))
    check("a dry run reports what is due and writes nothing", dry["due"] == 3 and n0 == 0, str(dry))

    sm = await ct.run_batch(100, session_maker=Session, api_factory=mixed, club_concurrency=1)
    check("one club failing does not stop the others", sm["error"] == 1 and sm["ok"] == 2 and sm["due"] == 3, str(sm))
    from app.services import club_teaser_report as rep
    timed = [d for d in sm["detail"] if d.get("status")]
    check("each pulled club carries the seconds it took, for the work report",
          len(timed) == 3 and all(isinstance(d.get("secs"), float) and d["secs"] >= 0 for d in timed),
          str(sm["detail"]))
    check("the work report counts what was pulled and projects the rest",
          any("clubs pulled   3" in ln for ln in rep.report_lines(sm["detail"], 12.0, total_due=300))
          and any("projection for 300" in ln for ln in rep.report_lines(sm["detail"], 12.0, total_due=300)))
    fake = [{"name": f"c{i}", "status": "ok", "calls": 20, "secs": 8.0} for i in range(6)]
    pr = rep.projection(fake, 100, pause_seconds=0.5)
    row5 = {r["limit"]: r for r in pr["table"]}[5]
    check("the projection is per-club latency times clubs, split by the scheduled concurrency",
          pr["calls"] == 2000 and abs(pr["serial_secs"] - 850) < 1e-9
          and abs(pr["scheduled_secs"] - 425) < 1e-9 and row5["runs"] == 20
          and abs(row5["run_secs"] - 25.5) < 1e-9, str(pr))
    check("a run longer than the tightest 5 minute gap is flagged as losing slots",
          not {r["limit"]: r for r in rep.projection(fake, 3500, pause_seconds=40)["table"]}[20]["fits"])
    check("a dry run, with nothing pulled, reports nothing to time",
          rep.report_lines([{"name": "x", "status": None, "calls": 0, "secs": 0.0}], 1.0, total_due=5)[0]
          .startswith("work done: nothing pulled"))
    sm2 = await ct.run_batch(100, session_maker=Session, api_factory=factory, club_concurrency=1)
    check("a second run pulls only what is left (the failed club is backed off, not retried tonight)", sm2["due"] == 0, str(sm2))

    async with Session() as s_:
        await s_.execute(text("UPDATE club_teaser_snapshots SET next_pull_at = now() - interval '1 hour'")); await s_.commit()
    seen = {"n": 0}
    async def stop_after_one(_s):
        seen["n"] += 1
        return seen["n"] > 1
    sst = await ct.run_batch(100, session_maker=Session, api_factory=factory, should_stop=stop_after_one, club_concurrency=1)
    check("the operator's Stop switch halts the batch between clubs", sst["stopped"] is True and (sst["ok"] + sst["error"]) == 1, str(sst))

    async with Session() as s_:
        await s_.execute(text("UPDATE club_teaser_snapshots SET next_pull_at = now() + interval '3 days'")); await s_.commit()
    sq = await ct.run_batch(100, session_maker=Session, api_factory=factory)
    check("a settled directory has nothing due", sq["due"] == 0, str(sq))

    # ---------------- wiring ----------------
    import app.jobs.scheduler as sched
    sched_src = Path(sched.__file__).read_text()
    check("the pull job exists and is registered", hasattr(sched, "pull_club_teasers")
          and "nightly_club_teasers" in sched_src)
    reg = sched_src[sched_src.index("pull_club_teasers,\n        trigger"):][:400]
    check("the pull runs 06:00-21:59 Perth at 10 and 5 minute steps, never overnight",
          'hour="6-8,21", minute="*/10"' in reg and 'hour="9-20", minute="*/5"' in reg
          and "hour=3" not in reg, reg)
    check("the job applies the Directory type filters", "get_club_teaser_type_modes" in sched_src)
    ps_src = (Path(__file__).resolve().parent.parent / "app/services/platform_settings.py").read_text()
    check("the nightly limit is a General Settings key that defaults to OFF",
          '"club_teaser_nightly_limit"' in ps_src and "UNSET MEANS 0" in ps_src)
    script = (Path(__file__).resolve().parent.parent / "app/scripts/pull_club_teasers.py").read_text()
    check("the operator script is a dry run unless told to apply", "dry_run=not a.apply" in script)
    check("the script prints the work report after an apply", "report_lines(" in script and "time.monotonic()" in script)
    check("the script and the job both honour the Stop switch", "is_crawl_paused" in script
          and "is_crawl_paused" in Path(sched.__file__).read_text())

    async with engine.begin() as c:
        for s in DOWNGRADE: await c.execute(text(s))
    async with engine.begin() as c:
        gone = await c.scalar(text("SELECT to_regclass('club_teaser_snapshots')"))
    check("the downgrade drops the table", gone is None)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


asyncio.run(main())
