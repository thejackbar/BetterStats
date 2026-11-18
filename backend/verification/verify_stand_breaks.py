"""Retired and unbroken partnerships a club types for a synced match. Real Postgres.

Reported by a new club (Piara Waters):
  * an unbroken last partnership could not be recorded against the match, so the club typed it as a
    hand-typed record that cannot open the scorecard;
  * women's games retire batters, a retirement ends a partnership without a wicket, and nothing could
    record that, so those stands were typed by hand too.

Drives the SHIPPED route bodies (`routers/game_fow.py`), `fow_overrides`, `stand_breaks`,
`participant_relink.attach_innings_detail`, the scorecard partnerships read and the records route:

  * the unbroken tick adds the stand between the two batters still in, scored off the card's total,
    marked unbroken on the scorecard and the records board (with its match);
  * a women's card (Cricket Australia records the retirement as a fall-of-wicket row, so the innings
    gives NO stands today) opens with the retirement split out, and saving gives every stand,
    including the one the retirement ended and the retired batter's return;
  * refusals 422 and leave the stored rows exactly as they were;
  * a Full Rebuild re-applies the typed retirements; Reset removes them.

Control run: against the previous commit the extra fields are ignored, the 7th stand and the women's
stands never appear, and the suite fails on exactly those checks.

Run:  DATABASE_URL=postgresql+asyncpg://root@/standbreaks?host=/var/run/postgresql \
      python verification/verify_stand_breaks.py
"""
from __future__ import annotations

import asyncio
import copy
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fow_overrides as F   # its seed, card, helpers and schema; main() is guarded
from app.models.db import Organisation

base, check = F.base, F.check
GUIDS, NAMES = F.GUIDS, F.NAMES
GAME_W = uuid.uuid4()

# The men's card of the FOW suite, with its total: 412 for 6, Ito and Lee not out.
CARD = copy.deepcopy(F.CARD)
CARD["innings"][0]["runsScored"] = 412


def women_card() -> dict:
    """A women's innings: Bivens retired not out at 140 after one wicket and came back at the end."""
    spec = [  # name, runs, dismissal
        ("Payne", 40, "Bowled"), ("Hall", 33, "Caught"), ("Bivens", 50, "Retired Not Out"),
        ("Sweet", 30, "Bowled"), ("Cox", 25, "LBW"), ("Menezes", 10, "Not Out"),
        ("Ito", None, "Did Not Bat"), ("Lee", None, "Did Not Bat"),
    ]
    ids = {"Bowled": 3, "Caught": 2, "LBW": 4, "Not Out": 1, "Retired Not Out": 12, "Did Not Bat": 0}
    bat = [{"participantId": str(GUIDS[n]), "batOrder": i, "runsScored": r,
            "dismissalTypeId": ids[d], "dismissalType": d, "playerShortName": f"{n[0]} {n}"}
           for i, (n, r, d) in enumerate(spec, 1)]
    c = copy.deepcopy(F.CARD)
    c["innings"][0]["batting"] = bat
    c["innings"][0]["runsScored"] = 245
    # Cricket Australia's own rows: the retirement is written as wicket 2.
    c["innings"][0]["fallOfWickets"] = [
        {"order": o, "runs": r, "participantId": str(GUIDS[n]), "playerShortName": f"{n[0]} {n}"}
        for o, r, n in [(1, 60, "Payne"), (2, 140, "Bivens"), (3, 150, "Hall"), (4, 190, "Sweet"), (5, 220, "Cox")]]
    return c


WCARD = women_card()


def opener_card() -> dict:
    """An opener (Payne) retires at 30 with no wicket down, comes back at the end and is caught. Cricket
    Australia writes her twice in the fall of wickets: the retirement as wicket 1 and her real wicket last."""
    spec = [("Payne", 45, "Caught"), ("Hall", 20, "Bowled"), ("Bivens", 25, "Caught"), ("Sweet", 10, "Not Out"),
            ("Cox", None, "Did Not Bat"), ("Menezes", None, "Did Not Bat"), ("Ito", None, "Did Not Bat"),
            ("Lee", None, "Did Not Bat")]
    ids = {"Bowled": 3, "Caught": 2, "Not Out": 1, "Did Not Bat": 0}
    c = copy.deepcopy(F.CARD)
    c["innings"][0]["batting"] = [
        {"participantId": str(GUIDS[n]), "batOrder": i, "runsScored": r, "dismissalTypeId": ids[d],
         "dismissalType": d, "playerShortName": f"{n[0]} {n}"} for i, (n, r, d) in enumerate(spec, 1)]
    c["innings"][0]["runsScored"] = 120
    c["innings"][0]["fallOfWickets"] = [
        {"order": o, "runs": r, "participantId": str(GUIDS[n]), "playerShortName": f"{n[0]} {n}"}
        for o, r, n in [(1, 30, "Payne"), (2, 50, "Hall"), (3, 80, "Bivens"), (4, 110, "Payne")]]
    return c


OCARD = opener_card()
GAME_O = uuid.uuid4()


def edit(rows, retirements=(), unbroken=False, unbroken_score=None):
    kw = {"rows": [F.game_fow.FowRowIn(wicket_number=w, score_at_fall=sc,
                                       participant_id=str(GUIDS[n]) if n else None) for w, sc, n in rows]}
    extra = {"retirements": [{"participant_id": str(GUIDS[n]) if n else None, "score": sc, "after_wicket": a}
                             for n, sc, a in retirements],
             "unbroken": unbroken, "unbroken_score": unbroken_score}
    # Through model_validate, so a control run on the previous commit ignores the fields it does not know.
    return F.game_fow.FowEditIn.model_validate({**{"rows": [r.model_dump() for r in kw["rows"]]}, **extra})


async def stands(game) -> list[tuple]:
    rows = await F.rows(
        "SELECT * FROM partnerships WHERE game_id = :g AND innings_number = 1 ORDER BY wicket_number, id", g=game)
    return [(r.wicket_number, r.runs, bool(getattr(r, "is_unbroken", None))) for r in rows]


async def pairs(game) -> list[tuple]:
    rows = await F.rows("""
        SELECT pt.wicket_number, p1.name AS a, p2.name AS b FROM partnerships pt
          LEFT JOIN players p1 ON p1.id = pt.batter1_id LEFT JOIN players p2 ON p2.id = pt.batter2_id
         WHERE pt.game_id = :g AND pt.innings_number = 1 ORDER BY pt.wicket_number, pt.id""", g=game)
    return [(r.wicket_number, frozenset({r.a, r.b})) for r in rows]


async def breaks_count(game):
    """Typed retirements stored for a game, or None where the table does not exist (a control run)."""
    try:
        return (await F.rows("SELECT count(*) FROM fow_override_breaks WHERE game_id = :g", g=game))[0][0]
    except Exception:
        return None


async def board() -> list[dict]:
    async with F.Session() as s:
        p = await F.get_records(
            str(F.OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    return p["partnerships"]["top_partnerships"]


async def scorecard_stands(game) -> list[dict]:
    from app.services.aggregations import get_game_partnerships
    async with F.Session() as s:
        return await get_game_partnerships(s, str(game), str(F.OURS))


async def main() -> None:
    if F.MISSING:
        check("the fall-of-wickets editor exists", False, F.MISSING[0])
        sys.exit(1)
    await base.build_schema()
    async with F.engine.begin() as conn:
        for stmt in F.FOW_DDL:
            await conn.execute(text(stmt))
        from app.services.audit_ddl import STATEMENTS as AUDIT
        for stmt in AUDIT:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, org_id UUID, keep_player_id UUID, removed_player_id UUID, undone_at TIMESTAMPTZ)"""))
    await F.seed()
    async with F.Session() as s:
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
            " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
            "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
            " 'One Day', false)"), {"i": GAME_W, "g": F.G, "d": date(2026, 1, 10), "ho": F.OURS})
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
            " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
            "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
            " 'One Day', false)"), {"i": GAME_O, "g": F.G, "d": date(2026, 1, 17), "ho": F.OURS})
        await s.commit()
    F.gr.get_match_scorecard = F.fake_fetch({str(F.GAME): CARD, str(GAME_W): WCARD, str(GAME_O): OCARD})
    user = await F.as_scorer()
    kw = dict(current_user=user, club=Organisation(id=F.OURS))

    async def store(game, card):
        async with F.Session() as s:
            by_guid, merged, _ = await F.relink._org_maps(s, F.OURS)
            await F.relink.attach_innings_detail(
                s, F.OURS, game, card, lambda g: F.relink._known(g, by_guid, merged) if g else None)
            await s.commit()

    await store(F.GAME, CARD)
    await store(GAME_W, WCARD)
    ROWS6 = F.ROWS6

    print("1. The unbroken last partnership")
    res, err = await F.call(F.game_fow.save_fow, game_id=str(F.GAME), innings_number=1,
                            data=edit(ROWS6, unbroken=True), **kw)
    check("saves", err is None, str(err and err.detail))
    got = await stands(F.GAME)
    check("all six wicket stands, then a 7th of 12 (412 - 400) marked unbroken",
          got == [(1, 73, False), (2, 77, False), (3, 181, False), (4, 25, False), (5, 25, False),
                  (6, 19, False), (7, 12, True)], str(got))
    check("between the two batters still in, Ito and Lee",
          (await pairs(F.GAME))[-1:] == [(7, frozenset({"I Ito", "L Lee"}))], str((await pairs(F.GAME))[-1:]))
    sc = await scorecard_stands(F.GAME)
    check("the match page reads it as unbroken", [p.get("is_unbroken") for p in sc][-1:] == [True], str(sc[-1:]))
    top = [r for r in await board() if r["runs"] == 12]
    check("it reaches the records board with its match and a not-out mark",
          len(top) == 1 and top[0].get("game_id") == str(F.GAME) and top[0].get("not_out") is True, str(top))
    check("a stand a wicket ended is not marked not out",
          all(r.get("not_out") is False for r in await board() if r["runs"] == 181), str(await board()))
    if res:
        inn = res["innings"]
        check("the editor reopens with the tick on and the end score", inn.get("unbroken") is True
              and inn.get("unbroken_score") == 412, str({k: inn.get(k) for k in ("unbroken", "unbroken_score")}))
        check("the summary says so", "unbroken stand" in (res.get("summary") or ""), res.get("summary"))

    res, err = await F.call(F.game_fow.save_fow, game_id=str(F.GAME), innings_number=1,
                            data=edit(ROWS6, unbroken=True, unbroken_score=430), **kw)
    got = await stands(F.GAME)
    check("a score typed for the end is used over the card's total", got[-1:] == [(7, 30, True)], str(got[-1:]))

    print("2. A women's card with a retirement")
    got = await stands(GAME_W)
    check("Cricket Australia's card (retirement written as a wicket) gives no stands today", got == [], str(got))
    res, err = await F.call(F.game_fow.fow_editor, game_id=str(GAME_W), **kw)
    inn = ((res or {}).get("innings") or [{}])[0]
    check("the editor opens with the four real wickets, numbered 1 to 4",
          [(f["wicket_number"], f["score_at_fall"]) for f in inn.get("fow", [])] == [(1, 60), (2, 150), (3, 190), (4, 220)],
          str(inn.get("fow")))
    check("and offers Cricket Australia's retirement row as a retirement",
          [(r["batter_name"], r["score"], r["after_wicket"]) for r in inn.get("retirements", [])]
          == [("B Bivens", 140, 1)], str(inn.get("retirements")))
    check("the retirement list offers every batter who went in (six), the wickets only the four out",
          len(inn.get("all_batters", [])) == 6 and len(inn.get("batters", [])) == 4,
          str((len(inn.get("all_batters", [])), len(inn.get("batters", [])))))
    check("nothing is stored by opening it",
          await breaks_count(GAME_W) == 0, str(await breaks_count(GAME_W)))

    W4 = [(1, 60, "Payne"), (2, 150, "Hall"), (3, 190, "Sweet"), (4, 220, "Cox")]
    res, err = await F.call(F.game_fow.save_fow, game_id=str(GAME_W), innings_number=1,
                            data=edit(W4, retirements=[("Bivens", 140, 1)], unbroken=True), **kw)
    check("saves the wickets, the retirement and the unbroken stand", err is None, str(err and err.detail))
    got = await stands(GAME_W)
    check("six stands: 60, 80* (ended by the retirement), 10, 40, 30, 25* unbroken",
          got == [(1, 60, False), (2, 80, True), (2, 10, False), (3, 40, False), (4, 30, False), (5, 25, True)],
          str(got))
    pr = await pairs(GAME_W)
    check("the pairs move along at the retirement (Hall with Bivens, then Hall with Sweet)",
          pr[1:3] == [(2, frozenset({"H Hall", "B Bivens"})), (2, frozenset({"H Hall", "S Sweet"}))], str(pr))
    check("and Bivens comes back once everyone else has batted, unbroken with Menezes",
          pr[-1] == (5, frozenset({"M Menezes", "B Bivens"})), str(pr[-1:]))
    check("the save is audited with the retirement",
          (await F.rows("SELECT count(*) FROM audit_events WHERE action = 'fow_edit' "
                        "AND detail::text LIKE '%after_retirements%'"))[0][0] >= 1)

    print("3. Refusals change nothing")
    before = await stands(GAME_W)
    bad = {
        "a batter who did not bat cannot retire": (W4, [("Ito", 100, 1)], False),
        "a batter not at the crease cannot retire (Cox was not in after one wicket)": (W4, [("Cox", 100, 1)], False),
        "a retirement score below an earlier wicket": (W4, [("Bivens", 40, 1)], False),
        "the unbroken stand needs every wicket": (W4[:3], [], True),
        "a retirement needs every wicket": (W4[:3], [("Bivens", 140, 1)], False),
    }
    for label, (rs, rets, ub) in bad.items():
        res, err = await F.call(F.game_fow.save_fow, game_id=str(GAME_W), innings_number=1,
                                data=edit(rs, retirements=rets, unbroken=ub), **kw)
        check(f"{label}: 422", err is not None and err.status_code == 422, str(err and (err.status_code, err.detail)))
    check("the stored stands are exactly as they were", await stands(GAME_W) == before, str(await stands(GAME_W)))

    print("4. A Full Rebuild keeps the club's typing")
    async with F.Session() as s:
        await s.execute(text("DELETE FROM partnerships WHERE game_id = :g"), {"g": GAME_W})
        await s.execute(text("DELETE FROM fall_of_wickets WHERE game_id = :g"), {"g": GAME_W})
        await s.commit()
    await store(GAME_W, WCARD)
    check("stored again from the card alone: no stands", await stands(GAME_W) == [], str(await stands(GAME_W)))
    async with F.Session() as s:
        by_guid, merged, _ = await F.relink._org_maps(s, F.OURS)
        await F.fo.apply_in_sync(s, F.OURS, GAME_W, WCARD, lambda g: F.relink._known(g, by_guid, merged) if g else None)
        await s.commit()
    check("the typed retirement and unbroken stand are applied again", await stands(GAME_W) == before,
          str(await stands(GAME_W)))

    print("5. Reset")
    res, err = await F.call(F.game_fow.reset_fow, game_id=str(GAME_W), innings_number=1, **kw)
    check("resets", err is None, str(err and err.detail))
    check("the typed retirements go too", await breaks_count(GAME_W) == 0, str(await breaks_count(GAME_W)))
    check("Cricket Australia's card is back (no stands)", await stands(GAME_W) == [], str(await stands(GAME_W)))

    print("6. An opener retires before the first wicket, comes back and is out")
    await store(GAME_O, OCARD)
    res, err = await F.call(F.game_fow.fow_editor, game_id=str(GAME_O), **kw)
    inn = ((res or {}).get("innings") or [{}])[0]
    check("the editor opens with her first row as a retirement at 0 wickets down",
          [(r["batter_name"], r["score"], r["after_wicket"]) for r in inn.get("retirements", [])]
          == [("P Payne", 30, 0)], str(inn.get("retirements")))
    check("and her real wicket last, the wickets numbered 1 to 3",
          [(f["wicket_number"], f["score_at_fall"], f["batter_name"]) for f in inn.get("fow", [])]
          == [(1, 50, "H Hall"), (2, 80, "B Bivens"), (3, 110, "P Payne")], str(inn.get("fow")))
    # Saved exactly as the editor would send what it opened on.
    rows = [(f["wicket_number"], f["score_at_fall"], next(n for n in NAMES if str(GUIDS[n]) == f["participant_id"]))
            for f in inn.get("fow", [])]
    rets = [(next(n for n in NAMES if str(GUIDS[n]) == r["participant_id"]), r["score"], r["after_wicket"])
            for r in inn.get("retirements", [])]
    res, err = await F.call(F.game_fow.save_fow, game_id=str(GAME_O), innings_number=1,
                            data=edit(rows, retirements=rets), **kw)
    check("saves", err is None, str(err and err.detail))
    got = await stands(GAME_O)
    check("four stands: 30* (ended by her retirement), 20, 30, and 30 when she came back",
          got == [(1, 30, True), (1, 20, False), (2, 30, False), (3, 30, False)], str(got))
    check("she bats with Hall, then comes back with Sweet",
          (await pairs(GAME_O)) == [(1, frozenset({"P Payne", "H Hall"})), (1, frozenset({"H Hall", "B Bivens"})),
                                    (2, frozenset({"B Bivens", "S Sweet"})), (3, frozenset({"S Sweet", "P Payne"}))],
          str(await pairs(GAME_O)))

    print()
    print(f"{base.PASS} passed, {base.FAIL} failed")
    await F.engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
