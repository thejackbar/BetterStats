"""The club teaser page (slices 1 and 2): what a snapshot holds, what a page leads
with, and the public routes behind /preview/{token}.

Runs the SHIPPED pull_club, presentation rules, route bodies and share-card
builder against a real Postgres, with scripted stand-ins for Cricket Australia
(no live call).

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_page.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

MISSING: list[str] = []
try:
    from fastapi import HTTPException
    from app.services import club_teaser as ct
    from app.services.club_teaser_ddl import STATEMENTS, DOWNGRADE
    from app.services import club_teaser_report as rep
    from app.routers import public_teaser as pt
    from app.routers import og_preview as og
    for name in ("presentation", "short_grade", "ordinal", "MIN_SEASON_MATCHES"):
        if not hasattr(ct, name):
            MISSING.append(f"club_teaser.{name} is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ct = pt = og = rep = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]
if "verify" not in (make_url(DB).database or "").lower():
    print("REFUSING to run: not a verification database. These checks delete and drop tables.")
    sys.exit(2)
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


def bat(n, runs, hs=80, hundreds=0):
    return [{"id": f"p{i}", "name": f"Batter {i}", "statistics": {
        "battingAggregate": runs - i * 10, "battingInnings": 12, "battingNotOuts": 1,
        "battingHighScore": hs, "batting50s": 2, "batting100s": hundreds}} for i in range(n)]


def bowl(n, wk):
    return [{"id": f"w{i}", "name": f"Bowler {i}", "statistics": {
        "bowlingWickets": wk - i, "bowlingRuns": 300, "bowlingBalls": 400, "bowlingBestInnings": "5/20"}}
        for i in range(n)]


def ladder_json(rank, played, won, lost, teams=8, org="ORG"):
    return {"ladders": [{"name": "Overall", "pools": [{"teams": [
        {"rank": rank, "displayName": "Us", "owningOrganisation": {"id": org},
         "ladderData": [{"id": "played", "val": played}, {"id": "won", "val": won},
                        {"id": "lost", "val": lost}, {"id": "competitionPoints", "val": 20}]},
        *[{"rank": r, "displayName": f"T{r}", "owningOrganisation": {"id": f"x{r}"}, "ladderData": []}
          for r in range(1, teams + 1) if r != rank]]}]}]}


class API:
    """seasons: list of (id, name, start, played) newest first; a season with
    played=None has no batting rows."""

    def __init__(self, seasons, grade="A Grade", resolve=None):
        self._seasons, self.grade, self.calls = seasons, grade, 0
        self._resolve = resolve

    async def resolve_org(self, club, guid):
        self.calls += 1
        return self._resolve or guid

    async def _s(self, sid):
        return next(s for s in self._seasons if s[0] == sid)

    async def seasons(self, org):
        self.calls += 1
        return [{"id": s[0], "name": s[1], "startDate": s[2]} for s in self._seasons]

    async def batting(self, org, sid, grades=None):
        self.calls += 1
        s = await self._s(sid)
        return bat(5, 400) if s[3] is not None else []

    async def bowling(self, org, sid, grades=None):
        self.calls += 1
        return bowl(5, 20)

    async def fielding(self, org, sid, grades=None):
        self.calls += 1
        return [{"id": "f", "name": "Field Er", "statistics": {"fieldingTotalCatches": 6}}]

    async def teams(self, org, sid):
        self.calls += 1
        self._org = org
        return [{"id": "T", "grades": [{"id": f"G-{sid}", "name": self.grade}]}]

    async def ladder(self, gid):
        self.calls += 1
        sid = gid.replace("G-", "")
        s = await self._s(sid)
        return ladder_json(2, s[3] or 0, (s[3] or 0) // 2, (s[3] or 0) // 2, org=self._org)


async def main() -> None:
    if MISSING:
        check("the teaser page backend is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    print("grade names")
    check("the part before the dash names the division",
          ct.short_grade("O60 Div 1 - Geoff Dymock Shield") == "O60 Div 1")
    check("a leading part that says nothing is kept, and clipped to fit",
          ct.short_grade("North East - Georgie McElligott Shield Women's Social T20").endswith("…")
          and ct.short_grade("North East - Georgie McElligott Shield Women's Social T20").startswith("North East"))
    check("a plain name is untouched", ct.short_grade("A Grade") == "A Grade")
    check("ordinals read right (1st 2nd 3rd 4th 11th 12th 13th 21st 22nd)",
          [ct.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"])

    print("the pull")
    full = API([("S1", "Summer 2025/26", "2025-10-01", 16), ("S0", "Summer 2024/25", "2024-10-01", 14)],
               resolve="CAORG")
    r = await ct.pull_club(full, "DIRGUID", {"name": "Full CC", "state": "VIC", "suburb": "X"})
    snap = r["snapshot"] or {}
    check("a full season is used as it is, with no fallback", r["status"] == "ok"
          and snap["season"]["name"] == "Summer 2025/26" and not r["season_pending"])
    check("the snapshot is schema 2", snap.get("schema") == 2 == ct.SCHEMA_VERSION)
    check("there is no 'draws' figure (played minus won minus lost is not draws)",
          "draws" not in snap["totals"], str(snap["totals"]))
    check("the club carries CA's own org id, not the directory's", snap["club"]["ca_org_id"] == "CAORG")
    check("ladder rows carry a short grade name", snap["ladders"][0]["grade_short"] == "A Grade")

    thin = API([("S1", "Summer 2026/27", "2026-10-01", 1), ("S0", "Summer 2025/26", "2025-10-01", 16)])
    r = await ct.pull_club(thin, "G", {"name": "New Season CC"})
    check("a season with one match falls back to the last full one",
          r["status"] == "ok" and r["snapshot"]["season"]["name"] == "Summer 2025/26"
          and r["snapshot"]["totals"]["matches"] == 16, str(r["snapshot"] and r["snapshot"]["season"]))
    check("and reads as season_pending, so the new season is noticed within a week", r["season_pending"] is True)
    thin2 = API([("S1", "Summer 2026/27", "2026-10-01", 1), ("S0", "Summer 2025/26", "2025-10-01", 3)])
    r = await ct.pull_club(thin2, "G", {"name": "Small CC"})
    check("when the older season is thin too the newest is kept (nothing fuller to use)",
          r["snapshot"]["season"]["name"] == "Summer 2026/27" and r["snapshot"]["totals"]["matches"] == 1)
    thin3 = API([("S1", "Summer 2026/27", "2026-10-01", 1)])
    r = await ct.pull_club(thin3, "G", {"name": "Only CC"})
    check("a thin only season is kept rather than turned into an empty club", r["status"] == "ok"
          and r["snapshot"]["totals"]["matches"] == 1)
    check("and the review says it is not enough for a piece",
          not rep.review_snapshot(r["snapshot"], this_year=2026)["ready"]
          and any("enough matches" in m for m in rep.review_snapshot(r["snapshot"], this_year=2026)["missing"]))
    check("the fallback costs calls only for a thin season (the full club made fewer)", full.calls < thin.calls,
          f"{full.calls} vs {thin.calls}")

    print("what a page leads with")
    flem = {"club": {"name": "Flemington CC", "state": "VIC", "suburb": "Ascot Vale"},
            "season": {"name": "Summer 2025/26", "year": 2025},
            "totals": {"matches": 61, "wins": 11, "losses": 40, "win_rate": 18},
            "ladders": [
                {"grade": "A Grade", "grade_short": "A Grade", "rank": 8, "teams": 8, "played": 16, "won": 4, "lost": 12, "points": 26},
                {"grade": "A Reserve", "grade_short": "A Reserve", "rank": 8, "teams": 8, "played": 17, "won": 1, "lost": 12, "points": 8},
                {"grade": "D Sunday", "grade_short": "D Sunday", "rank": 6, "teams": 8, "played": 16, "won": 5, "lost": 7, "points": 33}],
            "batting": [{"name": "K. Parekh", "runs": 565, "innings": 12, "average": 56.5, "high_score": 100, "hs_not_out": True,
                         "fifties": 5, "hundreds": 1}],
            "bowling": [{"name": "S. Parekh", "wickets": 20, "average": 16.7, "best": "6-11", "economy": 4.43}],
            "history": {"seasons_listed": 20, "first_year": 2005}}
    v = ct.presentation(flem)
    check("a batter's 565 runs beats 20 wickets as the lead", v["hero"]["kind"] == "runs" and v["hero"]["value"] == 565
          and v["hero"]["player"] == "K. Parekh")
    check("the lead's detail carries the average, the highest score (not out) and the hundred",
          "average 56.5" in v["hero"]["detail"] and "highest score 100*" in v["hero"]["detail"]
          and "1 hundred" in v["hero"]["detail"], v["hero"]["detail"])
    check("an 18% win rate is NOT shown as the record", v["record"] is None)
    check("no ladder position is shown when every grade is in the bottom half", v["ladders_shown"] == [])
    check("the main side is the grade with the most games", v["lead"]["grade"] == "A Reserve" and v["teams"] == 3)
    bris = {"club": {"name": "Brisbane Masters"}, "season": {"name": "Winter 2026"},
            "totals": {"matches": 69, "wins": 33, "losses": 21, "win_rate": 48},
            "ladders": [{"grade_short": "O60 Div 1", "rank": 2, "teams": 8, "played": 8, "won": 6, "lost": 1},
                        {"grade_short": "O60 Div 3 A", "rank": 3, "teams": 6, "played": 8, "won": 5, "lost": 2},
                        {"grade_short": "O60 Div 3 B", "rank": 5, "teams": 6, "played": 8, "won": 2, "lost": 4},
                        {"grade_short": "O50 Div 1", "rank": 2, "teams": 10, "played": 9, "won": 5, "lost": 1}],
            "batting": [{"name": "A. Watson", "runs": 300, "innings": 10, "average": 37.5, "high_score": 53, "hs_not_out": True,
                         "fifties": 1, "hundreds": 0}],
            "bowling": [{"name": "P. Matthews", "wickets": 26, "average": 14.77, "best": "4-28", "economy": 4.31}],
            "history": {}}
    v = ct.presentation(bris)
    check("26 wickets beats 300 runs as the lead", v["hero"]["kind"] == "wickets" and v["hero"]["player"] == "P. Matthews")
    check("a 48% win rate is shown as the record", v["record"] and v["record"]["won"] == 33 and v["record"]["played"] == 69)
    check("only grades in the top half of their ladder are shown, best rank first (then most games)",
          [l["grade"] for l in v["ladders_shown"]] == ["O50 Div 1", "O60 Div 1", "O60 Div 3 A"]
          and v["ladders_shown"][0]["place"] == "2nd", str(v["ladders_shown"]))
    check("a club with no batting and no bowling has no lead rather than a broken one",
          ct.presentation({**bris, "batting": [], "bowling": []})["hero"] is None)
    check("a thin season shows no record however well it went",
          ct.presentation({**bris, "totals": {"matches": 2, "wins": 2, "losses": 0, "win_rate": 100}})["record"] is None)

    # ------------------------------------------------------------------
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in DOWNGRADE:
            await c.execute(text(s))
    async with engine.begin() as c:
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots")); await s.execute(text("DELETE FROM marketing_clubs")); await s.commit()

    print("older snapshots are re-pulled")
    async with Session() as s:
        async def mk(name):
            cid = g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested,
                trial_modules, status, source) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '[]'::jsonb, 'new', 'grassroots_api')"""),
                {"id": cid, "g": g(), "n": name})
            return cid

        async def snapshot(cid, status, schema, token=None, snap=None):
            body = snap if snap is not None else ({"schema": schema, "club": {"name": "x"}} if status == "ok" else None)
            import json as _j
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot,
                version, next_pull_at) VALUES (CAST(:c AS uuid), :g, :t, :st, CAST(:sn AS jsonb), 3, now() + interval '30 days')"""),
                {"c": cid, "g": g(), "t": token or g().replace("-", "")[:22], "st": status,
                 "sn": _j.dumps(body) if body is not None else None})
        a, b, c_, d = await mk("Old CC"), await mk("Current CC"), await mk("Empty CC"), await mk("Page CC")
        await snapshot(a, "ok", 1)
        await snapshot(b, "ok", ct.SCHEMA_VERSION)
        await snapshot(c_, "empty", 0)
        await s.commit()
        due = await ct.due_clubs(s, 100, type_modes={})
        names = {x["name"] for x in due}
        check("a schema-1 snapshot is due even though its next pull is a month away", "Old CC" in names, str(names))
        check("a current one is not, and an empty club is not re-pulled for its schema",
              "Current CC" not in names and "Empty CC" not in names)
        p = await ct.teaser_progress(s, type_modes={})
        check("the panel's due count is the count of clubs the worker would pull (Page CC never pulled + Old CC)",
              p["due"] == len(due) == 2, f"{p['due']} vs {len(due)}")

    print("the public routes")
    tok = "TokenForPageClub0001"
    good = {**bris, "schema": 2, "club": {"name": "Brisbane Masters", "suburb": "Chermside West", "state": "QLD",
                                           "association": "Queensland Veterans", "ca_org_id": "CA-ORG-1"},
            "fielding": [{"name": "S. Rees", "catches": 8, "run_outs": 1, "stumpings": 6}],
            "records": [{"label": "Best Bowling Figures", "value": "5-3", "player": "D. Khan"}]}
    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots WHERE marketing_club_id = CAST(:c AS uuid)"), {"c": d})
        import json as _j
        await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version)
            VALUES (CAST(:c AS uuid), 'g', :t, 'ok', CAST(:sn AS jsonb), 7)"""), {"c": d, "t": tok, "sn": _j.dumps(good)})
        await s.commit()

    class Req:
        headers = {"user-agent": "verify"}
        client = type("C", (), {"host": "10.0.0.1"})()
    async with Session() as s:
        out = await pt.get_teaser(tok, Req(), s)
        check("a good token returns the page: lead, record, ladders and the leaders lists",
              out["hero"]["player"] == "P. Matthews" and out["record"] and out["ladders_shown"]
              and out["batting"] and out["bowling"] and out["fielding"] and out["records"] and out["version"] == 7)
        check("and the claim block carries CA's org id and the club's name",
              out["claim"] == {"ca_org_id": "CA-ORG-1", "name": "Brisbane Masters"})
        check("an unregistered club is not marked registered", out["registered"] is None)
        check("the response does not expose the directory's internals",
              not any(k in out for k in ("club_id", "marketing_club_id", "existing_org_id", "snapshot", "token")))

        async def status_of(t):
            try:
                await pt.get_teaser(t, Req(), s)
                return 200
            except HTTPException as e:
                return e.status_code
        check("an unknown token is a 404", await status_of("NoSuchTokenAtAll12345") == 404)
        check("a malformed token is a 404, not an error", await status_of("../../etc/passwd") == 404 and await status_of("x") == 404)
        await s.execute(text("UPDATE club_teaser_snapshots SET status = 'junior_only' WHERE token = :t"), {"t": tok}); await s.commit()
        check("a club whose snapshot is not ok gets no page (404, saying nothing about why)", await status_of(tok) == 404)
        await s.execute(text("UPDATE club_teaser_snapshots SET status = 'ok' WHERE token = :t"), {"t": tok}); await s.commit()

        oid = g()
        await s.execute(text("""INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Brisbane Masters CC', 'brisbane-masters', true)"""), {"i": oid})
        await s.execute(text("UPDATE marketing_clubs SET existing_org_id = :o WHERE id = CAST(:c AS uuid)"), {"o": oid, "c": d})
        await s.commit()
        out = await pt.get_teaser(tok, Req(), s)
        check("a club already on BetterCricket is sent to its own site", out["registered"] == {"slug": "brisbane-masters"}, str(out["registered"]))
        await s.execute(text("UPDATE organisations SET archived_at = now() WHERE id = :o"), {"o": oid}); await s.commit()
        check("an archived club is not treated as registered", (await pt.get_teaser(tok, Req(), s))["registered"] is None)

    print("events")
    seen = []
    pt.record_event_bg = lambda **kw: seen.append(kw)
    async with Session() as s:
        r = await pt.teaser_event(tok, pt.TeaserEvent(kind="tile", section="batting", visitor_id="v1"), Req(), s)
        check("a tile tap is recorded against the club, with its section",
              r == {"ok": True} and seen and seen[0]["route"] == "tile" and seen[0]["metadata"]["section"] == "batting"
              and seen[0]["metadata"]["marketing_club_id"] == d and seen[0]["visitor_id"] == "v1", str(seen))
        for kind in ("view", "claim_open", "claim_go"):
            await pt.teaser_event(tok, pt.TeaserEvent(kind=kind), Req(), s)
        check("view, claim_open and claim_go are all accepted", [x["route"] for x in seen[1:]] == ["view", "claim_open", "claim_go"])
        try:
            await pt.teaser_event(tok, pt.TeaserEvent(kind="anything else"), Req(), s); bad = False
        except HTTPException as e:
            bad = e.status_code == 422
        check("an unknown event kind is refused (an allowlist, not free text)", bad)
        try:
            await pt.teaser_event("NoSuchTokenAtAll12345", pt.TeaserEvent(kind="view"), Req(), s); nf = False
        except HTTPException as e:
            nf = e.status_code == 404
        check("an event for an unknown token is a 404 and records nothing", nf and len(seen) == 4)

    print("the share card and the routes")
    async with Session() as s:
        html = await og._teaser_html(tok, f"https://betterat.cricket/preview/{tok}", "https://betterat.cricket", s)
        check("the card names the club and season and is noindex",
              html and "Brisbane Masters: your Winter 2026" in html and 'content="noindex, nofollow"' in html, (html or "")[:200])
        check("the card leads with the player", html and "P. Matthews: 26 wickets" in html)
        check("an unknown token gets no teaser card", await og._teaser_html("NoSuchTokenAtAll12345", "u", "b", s) is None)
    check("/preview/<token> is parsed as a teaser page", og._parse_route(f"/preview/{tok}") == {"type": "teaser", "token": tok})
    check("'preview' is a reserved root segment, so it is never read as a club slug", "preview" in og.RESERVED_ROOT_SEGMENTS
          and og._parse_route("/preview") is None)
    check("an ordinary page's card is NOT noindex",
          "noindex" not in og._html("t", "d", None, "https://betterat.cricket/x"))

    print("wiring")
    root = Path(__file__).resolve().parent.parent
    main_src = (root / "app/main.py").read_text()
    check("the router is included by the app", "app.include_router(public_teaser.router)" in main_src and "public_teaser" in main_src.split("import")[1] + main_src[:6000])
    async with engine.begin() as c:
        for s in DOWNGRADE:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'brisbane-masters'"))
        await c.execute(text("DELETE FROM marketing_clubs"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


asyncio.run(main())
