"""Choosing the club's card for a match moves every total, not just the scorecard.

Reported by Hamilton Veterans (Oct 2026): PlayHQ credited a match's bowling (6-1-1-11) to Ken
Baker when it was David Spencer's (Geelong Blue, 14 Dec). Card review already lets a club type
the correct card, link it to the PlayHQ game and choose the club's version, and every PER-MATCH
read follows that choice. Season and career totals did not: Cricket Australia's season total has
no per-match granularity, so it kept counting PlayHQ's card, and the profile printed a total that
disagreed with the match page. A season only stepped aside for a card when it had been
re-sourced (`seasons.import_authoritative`), which only an overwrite CSV import sets.

Now a season counts match by match as soon as a person chose the club's card for any match in
it (`v_club_sourced_seasons`, derived on read). Runs the SHIPPED `card_review_actions.set_choice`
and the shipped readers over the app's own view DDL (`superseded_ddl.STATEMENTS`).

The headline check is a consistency one that needs no expected number: a player's season total
must equal the sum of the per-match rows beneath it.

THE CONTROL RUN is this file against the previous commit. It must FAIL on exactly the reported
behaviour (Baker keeps the wicket, Spencer never gets it, the totals disagree with the match
rows) and not crash: `v_club_sourced_seasons` is read inside try/except.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_card_choice_totals.py
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

from sqlalchemy import text

import verify_records_timing as base
from app.routers.records import get_records
from app.services import aggregations as agg
from app.services import card_review_actions as act
from app.services import card_review_ddl
from app.services import superseded_ddl

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


ORG = uuid.UUID("d1000000-0000-0000-0000-000000000001")
OPP = uuid.UUID("d1000000-0000-0000-0000-000000000002")
S1, S2 = uuid.UUID("d2000000-0000-0000-0000-000000000001"), uuid.UUID("d2000000-0000-0000-0000-000000000002")
G1, G2 = uuid.UUID("d3000000-0000-0000-0000-000000000001"), uuid.UUID("d3000000-0000-0000-0000-000000000002")
BAKER, SPENCER, ZED = (uuid.UUID(f"d4000000-0000-0000-0000-00000000000{n}") for n in (1, 2, 3))
USER = uuid.UUID("d5000000-0000-0000-0000-000000000001")
GEELONG = uuid.UUID("d6000000-0000-0000-0000-000000000001")   # the synced game PlayHQ got wrong
MANUAL = uuid.UUID("d7000000-0000-0000-0000-000000000001")    # the club's own card for it
AUTO_SYNCED = uuid.UUID("d6000000-0000-0000-0000-000000000009")
AUTO_MANUAL = uuid.UUID("d7000000-0000-0000-0000-000000000009")


async def ex(session, sql, **kw):
    await session.execute(text(sql), kw)


async def seed(session) -> None:
    await ex(session, "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Hamilton Veterans Cricket Club', 'hvcc', true)", i=ORG)
    await ex(session, "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Geelong Blue', 'geelong', true)", i=OPP)
    await ex(session, "INSERT INTO users (id, username, password_hash, failed_login_count) VALUES (:i, 'boss', 'x', 0)", i=USER)
    for sid, nm, yr in ((S1, "Summer 2025/26", 2025), (S2, "Summer 2024/25", 2024)):
        await ex(session, "INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)", i=sid, o=ORG, n=nm, y=yr)
    for gid, sid in ((G1, S1), (G2, S2)):
        await ex(session, "INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                          "VALUES (:i, :s, 'Over 60s', :g, 'senior', ARRAY['senior'])", i=gid, s=sid, g=str(gid))
    for pid, nm in ((BAKER, "Baker, Ken"), (SPENCER, "Spencer, David"), (ZED, "Zed, Zac")):
        await ex(session, "INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                          "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

    async def synced(gid, grade, day):
        await ex(session, "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                          " match_format, status, home_team, away_team) "
                          "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED', 'Hamilton', 'Geelong Blue')",
                 i=gid, g=grade, d=day, o=ORG, x=OPP)

    await synced(GEELONG, G1, date(2025, 12, 14))
    extra = []
    for n in (2, 3):
        gid = uuid.UUID(f"d6000000-0000-0000-0000-00000000010{n}")
        await synced(gid, G1, date(2025, 12, 14 + 7 * (n - 1)))
        extra.append(gid)
    # PlayHQ's cards: every game both batted 20 and 15; in Geelong the bowling is credited to BAKER.
    for gid in [GEELONG] + extra:
        for pid, r in ((BAKER, 20), (SPENCER, 15)):
            await ex(session, "INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, did_not_bat, batting_position) "
                              "VALUES (:g, :p, :r, 25, false, false, 3)", g=gid, p=pid, r=r)
    await ex(session, "INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                      "VALUES (:g, :p, 6.0, 1, 11, 1)", g=GEELONG, p=BAKER)
    # Cricket Australia's season rows are the sum of those cards.
    for pid, runs, bowl in ((BAKER, 60, True), (SPENCER, 45, False)):
        await ex(session, "INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, "
                          " bowling_innings, overs, bowling_balls, runs_conceded, wickets, maidens, source) "
                          "VALUES (:p, :s, 3, 3, :r, 0, :bi, :ov, :bb, :rc, :w, :m, 'api')",
                 p=pid, s=S1, r=runs, bi=1 if bowl else 0, ov=6.0 if bowl else 0, bb=36 if bowl else 0,
                 rc=11 if bowl else 0, w=1 if bowl else 0, m=1 if bowl else 0)

    # The club's own card for Geelong: bowling credited to SPENCER, where it belongs.
    await ex(session, "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, match_format, "
                      " superseded_by_game_id, pair_prefers_import) "
                      "VALUES (:i, :o, :s, :g, DATE '2025-12-14', 'Geelong Blue', 'One Day', :game, false)",
             i=MANUAL, o=ORG, s=S1, g=G1, game=GEELONG)
    for pid, r in ((BAKER, 20), (SPENCER, 15)):
        await ex(session, "INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls, not_out, did_not_bat) "
                          "VALUES (:g, :p, 1, 3, :r, 25, false, false)", g=MANUAL, p=pid, r=r)
    await ex(session, "INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                      "VALUES (:g, :p, 2, 6.0, 1, 11, 1)", g=MANUAL, p=SPENCER)

    # A SECOND SEASON with an automatic pair nobody decided (what a CricketStatz match completing a
    # PlayHQ one is): it must keep the rule the views always had, so this changes for nobody.
    await ex(session, "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                      "VALUES (:i, :g, DATE '2025-01-11', 'WIN', :o, :x, 'One Day', 'COMPLETED')", i=AUTO_SYNCED, g=G2, o=ORG, x=OPP)
    await ex(session, "INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, did_not_bat, batting_position) "
                      "VALUES (:g, :p, 30, 25, false, false, 3)", g=AUTO_SYNCED, p=ZED)
    await ex(session, "INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, source) "
                      "VALUES (:p, :s, 1, 1, 30, 0, 'api')", p=ZED, s=S2)
    await ex(session, "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, match_format, "
                      " superseded_by_game_id, pair_prefers_import) "
                      "VALUES (:i, :o, :s, :g, DATE '2025-01-11', 'Geelong Blue', 'One Day', :game, true)",
             i=AUTO_MANUAL, o=ORG, s=S2, g=G2, game=AUTO_SYNCED)
    await ex(session, "INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls, not_out, did_not_bat) "
                      "VALUES (:g, :p, 1, 3, 30, 25, false, false)", g=AUTO_MANUAL, p=ZED)
    await session.commit()


async def season_totals(pid, season) -> dict:
    async with base.Session() as s:
        r = (await s.execute(text(
            "SELECT COALESCE(SUM(matches),0) m, COALESCE(SUM(runs),0) r, COALESCE(SUM(wickets),0) w, "
            "       COALESCE(SUM(overs),0) o FROM v_effective_player_season_stats "
            "WHERE player_id = :p AND season_id = :s"), {"p": pid, "s": season})).mappings().one()
    return {k: float(v) for k, v in r.items()}


async def per_match(pid, season) -> dict:
    """What the match rows beneath that season add up to."""
    async with base.Session() as s:
        b = (await s.execute(text(
            "SELECT COALESCE(SUM(bi.runs),0) FROM v_effective_batting_innings bi JOIN v_effective_games g ON g.id = bi.game_id "
            "WHERE bi.player_id = :p AND g.season_id = :s AND NOT COALESCE(bi.did_not_bat, false)"), {"p": pid, "s": season})).scalar()
        w = (await s.execute(text(
            "SELECT COALESCE(SUM(bs.wickets),0), COALESCE(SUM(bs.overs),0) FROM v_effective_bowling_spells bs "
            "JOIN v_effective_games g ON g.id = bs.game_id WHERE bs.player_id = :p AND g.season_id = :s"),
            {"p": pid, "s": season})).one()
    return {"r": float(b), "w": float(w[0]), "o": float(w[1])}


async def club_sourced() -> set:
    try:
        async with base.Session() as s:
            return {r[0] for r in (await s.execute(text("SELECT season_id FROM v_club_sourced_seasons"))).all()}
    except Exception:
        return {"ABSENT"}


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
        # The audit table Card review writes to is lifespan DDL, so it is taken from there.
        for stmt in card_review_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as session:
        await seed(session)

    print("\n-- linked to the PlayHQ game, nobody has chosen the club's card yet --")
    b, sp = await season_totals(BAKER, S1), await season_totals(SPENCER, S1)
    check("Baker carries PlayHQ's wicket", b["w"] == 1 and b["o"] == 6, f"{b}")
    check("Spencer has none", sp["w"] == 0, f"{sp}")
    check("the season is still counted from Cricket Australia's total", S1 not in await club_sourced(),
          f"{await club_sourced()}")

    print("\n-- the club chooses its own card --")
    async with base.Session() as s:
        res = await act.set_choice(s, ORG, MANUAL, "club", USER, do_recompute=False)
    check("the choice is recorded", res.get("to") == "club", f"{res}")
    b, sp = await season_totals(BAKER, S1), await season_totals(SPENCER, S1)
    check("Baker no longer has Spencer's wicket", b["w"] == 0 and b["o"] == 0, f"{b}")
    check("Spencer has it: 1 wicket and 6 overs", sp["w"] == 1 and sp["o"] == 6, f"{sp}")
    check("nobody loses a match", b["m"] == 3 and sp["m"] == 3, f"{b} {sp}")
    check("nor a run: 60 and 45", b["r"] == 60 and sp["r"] == 45, f"{b} {sp}")
    check("the season is now counted match by match", S1 in await club_sourced(), f"{await club_sourced()}")
    basis_fn = getattr(act, "season_basis", None)
    async with base.Session() as s:
        basis = await basis_fn(s, ORG, MANUAL) if basis_fn else {}
    check("the page that made the choice is told the season now counts by match",
          basis.get("by_match") is True and basis.get("season") == "Summer 2025/26", f"{basis}")

    print("\n-- every total agrees with the match rows beneath it --")
    for name, pid in (("Baker", BAKER), ("Spencer", SPENCER)):
        t, m = await season_totals(pid, S1), await per_match(pid, S1)
        check(f"{name}: season wickets equal the match rows' ({m['w']:.0f})", t["w"] == m["w"], f"season {t['w']} vs matches {m['w']}")
        check(f"{name}: season overs equal the match rows' ({m['o']:.0f})", t["o"] == m["o"], f"season {t['o']} vs matches {m['o']}")
        check(f"{name}: season runs equal the match rows' ({m['r']:.0f})", t["r"] == m["r"], f"season {t['r']} vs matches {m['r']}")

    print("\n-- the readers a profile and the boards use --")
    async with base.Session() as s:
        cb = await agg.get_career_bowling(s, str(BAKER)) or {}
        cs = await agg.get_career_bowling(s, str(SPENCER)) or {}
        sbs = await agg.get_season_by_season(s, str(SPENCER)) or []
    check("Baker's career bowling has no wicket", cb.get("total_wickets") == 0, f"{cb.get('total_wickets')!r}")
    check("Spencer's career bowling has it", cs.get("total_wickets") == 1, f"{cs.get('total_wickets')!r}")
    row = next((r for r in sbs if str(r.get("season_id")) == str(S1)), {})
    check("Spencer's season row has it", row.get("total_wickets") == 1, f"{row.get('total_wickets')!r}")
    check("and the 6 overs", float(row.get("total_overs") or 0) == 6, f"{row.get('total_overs')!r}")

    print("\n-- the record books --")
    async with base.Session() as s:
        recs = await get_records(
            str(ORG), db=s, season_id=None, grade_id=None, grade_name=None, finals_only=False, captain_only=False,
            gender=None, categories=None, formats=None, competitions=None, debug_timing=False, viewer=None)
    boards = (recs or {}).get("bowling") or {}
    wk = {r.get("name"): r.get("wickets") for r in boards.get("top_career_wickets") or []}
    check("Most career wickets lists Spencer with the wicket", wk.get("Spencer, David") == 1, f"{wk}")
    check("and does not list Baker, who no longer has one", "Baker, Ken" not in wk, f"{wk}")
    best = [r.get("name") for r in boards.get("best_innings_figures") or []]
    check("Best innings figures name Spencer, not Baker", best == ["Spencer, David"], f"{best}")

    print("\n-- an automatic pair nobody decided is untouched --")
    z = await season_totals(ZED, S2)
    check("Zed's season is still Cricket Australia's total, counted once (1 match, 30 runs)",
          z["m"] == 1 and z["r"] == 30, f"{z}")
    check("and is not a club-sourced season", S2 not in await club_sourced(), f"{await club_sourced()}")

    print("\n-- the choice is put back --")
    async with base.Session() as s:
        await act.set_choice(s, ORG, MANUAL, "ca", USER, do_recompute=False)
    b, sp = await season_totals(BAKER, S1), await season_totals(SPENCER, S1)
    check("Baker has PlayHQ's wicket again", b["w"] == 1, f"{b}")
    check("Spencer has none again", sp["w"] == 0, f"{sp}")
    check("and nothing is left behind: the season is not club-sourced", S1 not in await club_sourced(),
          f"{await club_sourced()}")
    async with base.Session() as s:
        basis = await basis_fn(s, ORG, MANUAL) if basis_fn else {}
    check("and the page is told it is back", basis.get("by_match") is False, f"{basis}")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
