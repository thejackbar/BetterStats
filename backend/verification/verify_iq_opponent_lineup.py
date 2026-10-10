"""BetterIQ pulls the opposition's named XI for a fixture and matches it to the
players IQ has already scouted.

Runs the SHIPPED `opposition_lineup` route body (and `apply_grade_scope`) over a
real Postgres, the real `v_effective_*` views and the real dossier build. Only the
Cricket Australia client is stubbed: `get_match_detail` returns a scripted match
record shaped like the live `/scores/matches/{id}` route (`teams[].players[]`
with `participantId`, `name`, `roles`).

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_iq_dossier_scope \\
      python -m verification.verify_iq_opponent_lineup

Control run: against the previous commit there is no `iq_lineup` and no
`/iq/opposition/lineup`; the file reports that and fails every check.
"""
from __future__ import annotations

import asyncio
import copy
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select, text  # noqa: E402

import verify_iq_dossier_scope as base  # noqa: E402  (schema, seed, constants, check())
from app.models.db import Organisation  # noqa: E402
from app.routers import iq as iq_router  # noqa: E402
from app.services import grassroots_scores_client as gr_client  # noqa: E402

check = base.check
MATCH_ID = str(uuid.uuid4())
QUENTIN = uuid.uuid4()          # a second "Q Quick": makes an initial ambiguous
DETAIL: dict | None = None


def person(guid, name, roles=None):
    return {"participantId": str(guid), "name": name, "shortName": name, "roles": roles or []}


def record(their_players, *, with_ours=True, their_name="Swanbourne CC 3rd XI", their_org=None, their_club="Swanbourne CC"):
    teams = []
    if with_ours:
        teams.append({"id": "t-us", "displayName": "Home CC 3rd XI",
                      "owningOrganisation": {"id": str(base.US), "name": "Home CC"}, "players": []})
    teams.append({"id": "t-them", "displayName": their_name,
                  "owningOrganisation": {"id": str(their_org or base.THEM), "name": their_club},
                  "players": their_players,
                  "nonPlayingMembers": [{"name": "Coach Carter", "roles": ["Coach"]}]})
    return {"id": MATCH_ID, "status": "UPCOMING", "teams": teams,
            "matchSchedule": [{"startDateTime": "2026-10-17T13:00:00Z"}],
            "grade": {"name": "3rd Grade"}}


async def _detail(match_id, *, force=False):
    return copy.deepcopy(DETAIL)


async def lineup(*, fixture, categories="senior", formats="two_day", **kw) -> dict:
    """The shipped route under the shipped scope dependency, polled until nothing is pending."""
    async with base.Session() as s:
        club = (await s.execute(select(Organisation).where(Organisation.id == base.US))).scalar_one()
        gen = iq_router.apply_grade_scope(categories=categories, formats=formats,
                                          competitions=None, db=s, club=club)
        await gen.__anext__()
        try:
            res: dict = {}
            for _ in range(200):
                res = await iq_router.opposition_lineup(
                    fixture_id=str(fixture) if fixture else None, opponent=None, team=None,
                    grade=None, name=None, refresh=False, db=s, club=club)
                if res.get("status") != "building" and not res.get("pending"):
                    break
                await asyncio.sleep(0.2)
            return res
        finally:
            await gen.aclose()


def by_name(res: dict) -> dict:
    return {p["name"]: p for p in (res.get("players") or [])}


async def main() -> int:
    global DETAIL
    base_main_stubs()
    await base.build_schema()
    await base.seed()
    async with base.Session() as s:
        await s.execute(text("UPDATE fixtures SET playhq_id = :m, source = 'grassroots' WHERE id = :f"),
                        {"m": MATCH_ID, "f": base.FX3})
        # A second Quick, bowling in the T20 game, so "Q Quick" fits two scouted players.
        g1 = (await s.execute(text("SELECT id FROM games WHERE grade_id = :g"), {"g": base.GB_T20})).scalar_one()
        await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                             "VALUES (:i, :o, 'Quick, Quentin', :g, 'active')"),
                        {"i": QUENTIN, "o": base.THEM, "g": str(QUENTIN)})
        await s.execute(text("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                             "VALUES (:g, :p, 3, 0, 20, 1)"), {"g": g1, "p": QUENTIN})
        # Smith also turned out once for the 1st XI in T20 Div 1 (a tie with his one 3rds game).
        await s.execute(text("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, not_out, "
                             " dismissal_type, did_not_bat, batting_position) "
                             "VALUES (:g, :p, 12, 10, 1, 0, false, 'bowled', false, 5)"), {"g": g1, "p": base.SMITH})
        await s.commit()

    if not hasattr(iq_router, "opposition_lineup"):
        check("the lineup route exists (feature present)", False, "iq_router.opposition_lineup is missing")
        print(f"\n{base.PASS} passed, {base.FAIL} failed")
        return 1

    smith, lane, hitter, bowl3, quick = (base.NAMES[p] for p in (base.SMITH, base.LANE, base.HITTER, base.BOWL_3, base.BOWL_T20))
    DETAIL = record([
        person(base.SMITH, "Sam Smith", ["Captain"]),                 # same GUID as scouted
        person(uuid.uuid4(), "Ben Bowler"),                           # different GUID, full name
        person(uuid.uuid4(), "David Lane", ["Wicket Keeper"]),        # their 1st XI T20 danger man
        person(uuid.uuid4(), "H Hitter"),                             # initial only
        person(uuid.uuid4(), "Q Quick"),                              # fits two scouted players
        person(uuid.uuid4(), "********"),                             # a redacted junior
        person(uuid.uuid4(), "Zed Newbie"),                           # nobody scouted him
    ])

    print("\n-- the 3rds fixture: their named XI, matched to the scouted squad --")
    res = await lineup(fixture=base.FX3)
    check("status named, seven players", res.get("status") == "named" and res.get("named_count") == 7,
          f"{res.get('status')} {res.get('named_count')}")
    check("the match id used is the fixture's own", res.get("match_id") == MATCH_ID, str(res.get("match_id")))
    P = by_name(res)
    check("Smith: matched by GUID, from the grade scout, captain flag kept",
          (P.get("Sam Smith") or {}).get("basis") == "id" and P["Sam Smith"].get("pool") == "grade"
          and P["Sam Smith"].get("is_captain") is True, str(P.get("Sam Smith")))
    check("Smith carries his scouted numbers (45 runs)",
          ((P.get("Sam Smith") or {}).get("bat") or {}).get("runs") == 45, str((P.get("Sam Smith") or {}).get("bat")))
    check("Bowler: a different GUID, matched on full name, with his bowling figures",
          (P.get("Ben Bowler") or {}).get("basis") == "name"
          and ((P["Ben Bowler"].get("bowl") or {}).get("wickets") == 3), str(P.get("Ben Bowler")))
    check("Lane: not in the grade scout, found in their other sides and labelled so",
          (P.get("David Lane") or {}).get("pool") == "other_sides" and P["David Lane"].get("matched") is True,
          str(P.get("David Lane")))
    check("Lane keeps his keeper flag and his T20 numbers (79)",
          P["David Lane"].get("is_keeper") is True and ((P["David Lane"].get("bat") or {}).get("runs") == 79),
          str(P.get("David Lane")))
    check("Hitter: matched on surname and initial, flagged as the weaker basis",
          (P.get("H Hitter") or {}).get("basis") == "initial", str(P.get("H Hitter")))
    check("Q Quick fits two scouted players, so it matches neither, and is flagged ambiguous",
          (P.get("Q Quick") or {}).get("matched") is False and P["Q Quick"].get("ambiguous") is True, str(P.get("Q Quick")))
    check("the redacted junior is flagged, not guessed", (P.get("********") or {}).get("redacted") is True
          and P["********"].get("matched") is False, str(P.get("********")))
    check("a stranger is counted as new to us", res.get("new_count") == 1 and res.get("unsure_count") == 1 and not P["Zed Newbie"]["matched"],
          f"new_count={res.get('new_count')} unsure={res.get('unsure_count')}")
    check("counts: 2 from the grade scout, 2 from other sides, 1 redacted",
          (res.get("scouted_count"), res.get("other_sides_count"), res.get("redacted_count")) == (2, 2, 1),
          str((res.get("scouted_count"), res.get("other_sides_count"), res.get("redacted_count"))))
    check("Smith, their scouted danger batter, is named", any(d["name"] == smith for d in res.get("danger_named", [])),
          str(res.get("danger_named")))

    print("\n-- grades they have played, from the whole club --")
    check("Lane usually plays T20 Div 1, not this grade",
          (P.get("David Lane") or {}).get("usual_grade") == "T20 Div 1" and (P.get("David Lane") or {}).get("plays_elsewhere") is True,
          str(((P.get("David Lane") or {}).get("usual_grade"), (P.get("David Lane") or {}).get("plays_elsewhere"))))
    check("Smith has played both, and the tie goes to this grade: not a visitor",
          {g["name"] for g in (P.get("Sam Smith") or {}).get("grades", [])} == {"3rd Grade", "T20 Div 1"}
          and (P.get("Sam Smith") or {}).get("usual_grade") == "3rd Grade" and (P.get("Sam Smith") or {}).get("plays_elsewhere") is False,
          str((P["Sam Smith"].get("grades"), (P.get("Sam Smith") or {}).get("usual_grade"))))
    check("Bowler has only played 3rd Grade", [g["name"] for g in (P.get("Ben Bowler") or {}).get("grades", [])] == ["3rd Grade"],
          str(P["Ben Bowler"].get("grades")))
    check("Smith's figures are still the grade scout's (45), the T20 innings is not blended in",
          ((P["Sam Smith"].get("bat") or {}).get("runs")) == 45, str(P["Sam Smith"].get("bat")))
    check("a stranger has no grade history", not (P.get("Zed Newbie") or {}).get("grades"), str(P["Zed Newbie"].get("grades")))

    print("\n-- the quick read --")
    lines = (res.get("analysis") or {}).get("lines") or []
    text_ = " ".join(lines)
    if os.environ.get("SHOW"):  # eyeball the generated text: SHOW=1 python -m verification.verify_iq_opponent_lineup
        for ln in lines:
            print("       |", ln)
        for r in res.get("players", []):
            print("       |", r["name"], "->", r.get("pool"), r.get("grades"), r.get("usual_grade"))
    check("it opens with how many they named and how many we know", lines[:1] == ["Swanbourne CC 3rd XI have named 7. We have form on 4 of them."], str(lines[:1]))
    check("it names the threat with his numbers", "Threats:" in text_ and "Sam Smith, 45 runs" in text_, text_)
    check("it says Lane usually plays T20 Div 1, with no higher/lower claim across competitions",
          "David Lane usually plays T20 Div 1 (their only game this season)." in text_, text_)
    check("a thin sample is called one, inside one bracket", "79.0 (in T20 Div 1, small sample)" in text_, text_)
    check("it lists who we have never seen, and the junior", "Not scouted before: Zed Newbie and 1 junior with names withheld." in text_, text_)
    check("an ambiguous name is not called new: it says it could not tell",
          "Q Quick" not in text_.partition("Not scouted before:")[2].split(".")[0] and "Could not tell which scouted player Q Quick is" in text_, text_)
    check("no em dashes", "\u2014" not in text_ and "\u2013" not in text_, text_)
    check("nothing is pending once the pool is built", res.get("pending") is False, str(res.get("pending")))

    print("\n-- the danger man is NOT named --")
    DETAIL = record([person(base.BOWL_3, "Ben Bowler"), person(uuid.uuid4(), "Zed Newbie")])
    res = await lineup(fixture=base.FX3)
    check("Smith is listed as missing from the XI", any(d["name"] == smith for d in res.get("danger_missing", [])),
          str(res.get("danger_missing")))
    check("and not as named", not any(d["name"] == smith for d in res.get("danger_named", [])), str(res.get("danger_named")))
    check("the quick read says so", "Not named: Sam Smith" in " ".join((res.get("analysis") or {}).get("lines", [])),
          str((res.get("analysis") or {}).get("lines")))

    print("\n-- the other states --")
    DETAIL = record([])
    res = await lineup(fixture=base.FX3)
    check("no players published: not_named, a normal state, with the team named",
          res.get("status") == "not_named" and res.get("team_name") == "Swanbourne CC 3rd XI", str(res))
    DETAIL = None
    res = await lineup(fixture=base.FX3)
    check("no match record: unavailable", res.get("status") == "unavailable", str(res.get("status")))
    DETAIL = record([person(base.SMITH, "Sam Smith")], with_ours=False, their_name="Third CC", their_org=uuid.uuid4(), their_club="Third CC")
    res = await lineup(fixture=base.FX3)
    check("a record with no side we can call theirs: unavailable, never a guess",
          res.get("status") == "unavailable", str(res.get("status")))
    DETAIL = record([person(base.SMITH, "Sam Smith")], their_name="Some Other Name", their_org=uuid.uuid4(), their_club="Some Other Club")
    res = await lineup(fixture=base.FX3)
    check("but with OUR side in the record, the other side is theirs, even under another name",
          res.get("status") == "named" and res.get("named_count") == 1, str(res.get("status")))
    res = await lineup(fixture=base.FX4)
    check("a hand-added fixture has no match id: no_match", res.get("status") == "no_match", str(res.get("status")))
    res = await lineup(fixture=None)
    check("no fixture at all: no_match", res.get("status") == "no_match", str(res.get("status")))

    print("\n-- Ask IQ: the opponent_lineup tool --")
    from app.services import iq_ask
    check("the tool is registered and offered to the model",
          "opponent_lineup" in iq_ask._DISPATCH and any(t["name"] == "opponent_lineup" for t in iq_ask.TOOLS), "")
    if not hasattr(iq_ask, "_tool_opponent_lineup"):
        check("the Ask IQ tool function exists", False, "iq_ask._tool_opponent_lineup is missing")
        print(f"\n{base.PASS} passed, {base.FAIL} failed")
        return 1
    DETAIL = record([person(base.SMITH, "Sam Smith", ["Captain"]), person(uuid.uuid4(), "David Lane"),
                     person(uuid.uuid4(), "Zed Newbie")])
    out: dict = {}
    async with base.Session() as s:
        club = (await s.execute(select(Organisation).where(Organisation.id == base.US))).scalar_one()
        gen = iq_router.apply_grade_scope(categories="senior", formats="two_day", competitions=None, db=s, club=club)
        await gen.__anext__()
        try:
            for _ in range(200):
                out = await iq_ask._tool_opponent_lineup(s, str(base.US), fixture_id=str(base.FX3))
                if out.get("status") != "building":
                    break
                await asyncio.sleep(0.2)
            err = await iq_ask._tool_opponent_lineup(s, str(base.US))
        finally:
            await gen.aclose()
    PL = {p["name"]: p for p in out.get("players", [])}
    check("it returns the named XI with the analysis sentences",
          out.get("status") == "named" and len(PL) == 3 and bool(out.get("analysis")), str(out)[:200])
    check("Lane carries his usual grade and where his figures came from",
          PL.get("David Lane", {}).get("usual_grade") == "T20 Div 1"
          and PL["David Lane"].get("figures_from") == "their other grades and formats", str(PL.get("David Lane")))
    check("Smith's figures are this grade's", PL.get("Sam Smith", {}).get("figures_from") == "this fixture's grade"
          and PL["Sam Smith"].get("runs") == 45, str(PL.get("Sam Smith")))
    check("a fixture id is required", "error" in err, str(err))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


def base_main_stubs() -> None:
    """The same CA stubs the scope check uses, plus the match record."""
    gr_client.get_grade_matches = base._fake_grade_matches
    gr_client.get_match_scorecard = base._fake_scorecard
    gr_client.get_match_detail = _detail
    from app.services import iq_scout

    async def _no_external_teams(*_a, **_k):
        return []
    iq_scout.external_club_teams = _no_external_teams


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
