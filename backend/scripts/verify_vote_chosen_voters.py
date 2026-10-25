"""Verification for a team voted by a chosen group of people (migrations 347 and
362) against a real Postgres.

Runs the SHIPPED statements, service functions and route bodies. New keys and
functions are read through presence-safe accessors, so the same script run
against the previous commit reports FAIL lines instead of crashing (the control
run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_chosen_voters.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


PLAYED = date.today() - timedelta(days=1)

ORG, OTHER_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, G_FIRSTS, G_COLTS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FX_FIRSTS, FX_COLTS = uuid.uuid4(), uuid.uuid4()
CAPTAIN, JOE, SAM, HELPER, SUPPORTER, OUTSIDER, DAVE, PAT = (uuid.uuid4() for _ in range(8))
GAME_F, GAME_C = uuid.uuid4(), uuid.uuid4()


async def seed(db) -> None:
    from app.models.db import (
        Fixture, Game, GameAppearance, Grade, Organisation, Player, Season,
    )

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    db.add(Organisation(id=OTHER_ORG, name="Melville CC", short_name="MCC", slug="melville", module_overrides=["select"]))
    await db.flush()
    year = PLAYED.year if PLAYED.month >= 7 else PLAYED.year - 1
    db.add(Season(id=SEASON, organisation_id=ORG, name="Current", year=year))
    await db.flush()
    db.add(Grade(id=G_FIRSTS, season_id=SEASON, name="1st Grade"))
    db.add(Grade(id=G_COLTS, season_id=SEASON, name="Colts"))
    for pid, nm, org, is_player in (
        (CAPTAIN, "Captain Cook", ORG, True), (JOE, "Regular Joe", ORG, True), (SAM, "Sam Side", ORG, True),
        # Not in either side: the captain's helper.
        (HELPER, "Helen Helper", ORG, True),
        # Club person who is not a player (a supporter record).
        (SUPPORTER, "Sue Supporter", ORG, False),
        (OUTSIDER, "Olly Outsider", OTHER_ORG, True),
        (DAVE, "Dave Deep", ORG, True),
        # A second helper, not in either side.
        (PAT, "Pat Panel", ORG, True),
    ):
        db.add(Player(id=pid, organisation_id=org, name=nm, email=f"{nm[:3].lower()}@example.com",
                      is_player=is_player))
    await db.flush()
    for gid, grade in ((GAME_F, G_FIRSTS), (GAME_C, G_COLTS)):
        db.add(Game(id=gid, grade_id=grade))
    await db.flush()
    for pid, cap in ((CAPTAIN, True), (JOE, False), (SAM, False), (DAVE, False)):
        db.add(GameAppearance(game_id=GAME_F, player_id=pid, is_captain=cap))
        db.add(GameAppearance(game_id=GAME_C, player_id=pid, is_captain=cap))
    for fid, grade, game, opp in ((FX_FIRSTS, G_FIRSTS, GAME_F, "Melville"), (FX_COLTS, G_COLTS, GAME_C, "Melville Colts")):
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round="5",
                       played_on=PLAYED, end_on=PLAYED, home_away="H", grade_id=grade, playhq_id=str(game)))
    await db.commit()


def request(player_id=None, club_id=ORG) -> Request:
    from app.config.settings import settings
    from app.routers.public_votes import COOKIE_NAME

    headers = []
    if player_id is not None:
        tok = jwt.encode(
            {"club": str(club_id), "pid": str(player_id), "typ": "vote",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.secret_key, algorithm=settings.algorithm,
        )
        headers.append((b"cookie", f"{COOKIE_NAME}={tok}".encode()))
    return Request({"type": "http", "headers": headers, "method": "GET", "path": "/", "query_string": b"",
                    "client": ("1.2.3.4", 1234)})


async def attempt(coro):
    """('ok', value) or ('http', status, detail) or ('err', repr)."""
    try:
        return ("ok", await coro)
    except HTTPException as e:
        return ("http", e.status_code, e.detail)
    except Exception as e:  # control run: the feature does not exist
        return ("err", f"{type(e).__name__}: {e}")


async def main() -> None:
    from app.models.db import Base, Fixture, Organisation, Player, VoteBallot, VoteMedal
    from app.routers import public_availability as pa
    from app.routers import public_votes as pv
    from app.routers import votes as vr
    from app.services import votes as vs
    from app.services import vote_medal_ddl as ddl

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stmts = getattr(ddl, "VOTE_GRADE_COUNTER_STATEMENTS", None)
    convert = getattr(ddl, "VOTE_CHOSEN_VOTER_STATEMENTS", None)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    # ── Migration 347: the column ──
    if stmts:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE vote_medals DROP COLUMN IF EXISTS grade_vote_counters"))
            for _ in range(3):
                for stmt in stmts:
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            col = (await conn.execute(text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name='vote_medals' AND column_name='grade_vote_counters'"))).first()
        check("347 adds grade_vote_counters, NOT NULL, default empty, safe to re-run",
              col is not None and col[1] == "NO" and "{}" in (col[0] or ""), str(col))
    else:
        check("347 adds grade_vote_counters", False, "no VOTE_GRADE_COUNTER_STATEMENTS")

    # ── Migration 362: single ids from the first release become lists on 'chosen' ──
    legacy_org = uuid.uuid4()
    async with Session() as seed_db:
        seed_db.add(Organisation(id=legacy_org, name="Legacy CC", short_name="LCC", slug="legacy"))
        await seed_db.commit()
    rows = {
        # captain-only by its own setting, one id: becomes chosen + a list
        "A": ("players", {"1st": "captain"}, {"1st": str(HELPER)}),
        # medal default captain, team has no setting of its own: also chosen
        "B": ("captain", {}, {"2nd": str(HELPER)}),
        # an all-players team that holds an id: list shape only, mode untouched
        "C": ("players", {"3rd": "players"}, {"3rd": str(HELPER)}),
        # already the new shape: left exactly as it is
        "D": ("captain", {"4th": "captain"}, {"4th": [str(HELPER), str(PAT)]}),
    }
    async with Session() as seed_db:
        for pos, (tag, (mode, modes, counters)) in enumerate(rows.items()):
            seed_db.add(VoteMedal(organisation_id=legacy_org, name=tag, position=pos, voter_mode=mode,
                                  grade_voter_modes=modes, grade_vote_counters=counters))
        await seed_db.commit()

    async def read(tag):
        async with engine.connect() as conn:
            r = (await conn.execute(text(
                "SELECT grade_voter_modes, grade_vote_counters FROM vote_medals WHERE organisation_id=:o AND name=:n"),
                {"o": legacy_org, "n": tag})).first()
        return r[0], r[1]

    if convert:
        for _ in range(3):
            async with engine.begin() as conn:
                for stmt in convert:
                    await conn.execute(text(stmt))
        a = await read("A")
        check("362: a captain-only team's single id becomes a list on 'chosen'",
              a == ({"1st": "chosen"}, {"1st": [str(HELPER)]}), str(a))
        b = await read("B")
        check("362: a team that followed a captain-only default also moves to 'chosen'",
              b == ({"2nd": "chosen"}, {"2nd": [str(HELPER)]}), str(b))
        c = await read("C")
        check("362: an all-players team keeps its mode and only changes shape",
              c == ({"3rd": "players"}, {"3rd": [str(HELPER)]}), str(c))
        d = await read("D")
        check("362: a row already in the new shape is untouched by three runs",
              d == ({"4th": "captain"}, {"4th": [str(HELPER), str(PAT)]}), str(d))
    else:
        check("362: single ids become lists", False, "no VOTE_CHOSEN_VOTER_STATEMENTS")
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM vote_medals WHERE organisation_id = :o"), {"o": legacy_org})
        await conn.execute(text("DELETE FROM organisations WHERE id = :o"), {"o": legacy_org})

    # ── The cleaner ──
    clean = getattr(vs, "clean_grade_vote_counters", None)
    got = clean({"1st": [str(HELPER), str(HELPER), "junk", str(PAT)], "Old": str(JOE), " ": [str(JOE)], "Empty": []}) if clean else None
    check("the cleaner drops repeats, junk, blank teams and empty teams; reads a bare id as one",
          got == {"1st": [str(HELPER), str(PAT)], "Old": [str(JOE)]}, str(got))
    many = clean({"1st": [str(uuid.uuid4()) for _ in range(30)]}) if clean else {}
    check("the cleaner caps a team's list", len(many.get("1st", [])) == getattr(vs, "MAX_CHOSEN_VOTERS", -1), str(len(many.get("1st", []))))

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)

        medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True,
                          link_token="tok-cc", voter_mode="players",
                          grade_voter_modes={"1st Grade": "captain"})
        db.add(medal)
        await db.commit()
        mid = str(medal.id)
        Body = vr.MedalUpdate

        async def patch(**kw):
            async def run():
                # Built inside the attempt: the previous commit's request model rejects the new shapes.
                return await vr.update_medal(mid, Body(**kw), db=db, club=club, user=None)
            return await attempt(run())

        eligible = [
            {"id": str(CAPTAIN), "name": "Captain Cook", "is_captain": True},
            {"id": str(JOE), "name": "Regular Joe", "is_captain": False},
            {"id": str(SAM), "name": "Sam Side", "is_captain": False},
            {"id": str(DAVE), "name": "Dave Deep", "is_captain": False},
        ]
        helper = await db.get(Player, HELPER)
        pat = await db.get(Player, PAT)
        joe = await db.get(Player, JOE)
        sam = await db.get(Player, SAM)
        cook = await db.get(Player, CAPTAIN)
        fx_firsts = await db.get(Fixture, FX_FIRSTS)
        fx_colts = await db.get(Fixture, FX_COLTS)

        # ── Control: on Captain only, before anyone is chosen, nothing changed ──
        await db.refresh(medal)
        cfg0 = await vs.cfg_for_fixture(db, vs.effective_config(medal), fx_firsts)
        check("captain only: the captain votes", pv._voter_role(cfg0, cook, eligible)[0] == "player")
        check("captain only: a player is told it is captain only",
              pv._voter_role(cfg0, joe, eligible) == ("none", "captain_only"))
        check("captain only: someone outside the side cannot vote",
              pv._voter_role(cfg0, helper, eligible) == ("none", "did_not_play"))
        landing0 = await pv.get_landing("tok-cc", request(HELPER), db)
        check("captain only: a helper who did not play is offered no games", landing0["fixtures"] == [])

        # ── Choose through the shipped PATCH: a mode, and a list of people ──
        r = await patch(grade_voter_modes={"1st Grade": "chosen"},
                        grade_vote_counters={"1st Grade": [str(HELPER), str(PAT), str(JOE)]})
        saved = r[1].get("grade_vote_counters") if r[0] == "ok" else r
        check("PATCH stores a list of people per team",
              saved == {"1st Grade": [str(HELPER), str(PAT), str(JOE)]}, str(saved))
        check("PATCH accepts the 'chosen' mode for a team",
              r[0] == "ok" and r[1].get("grade_voter_modes") == {"1st Grade": "chosen"}, str(r)[:200])
        names = r[1].get("vote_chosen") if r[0] == "ok" else None
        check("the payload names each chosen person, in the order chosen",
              names == {"1st Grade": [{"id": str(HELPER), "name": "Helen Helper"},
                                      {"id": str(PAT), "name": "Pat Panel"},
                                      {"id": str(JOE), "name": "Regular Joe"}]}, str(names))
        r2 = await patch(name="Club Champion")
        check("a PATCH that does not send the lists leaves them alone",
              r2[0] == "ok" and len(r2[1].get("grade_vote_counters", {}).get("1st Grade", [])) == 3, str(r2)[:200])

        # ── Refused ──
        bad = await patch(grade_voter_modes={"1st Grade": "everyone"})
        check("an unknown mode is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad))
        for label, who in (("another club's player", OUTSIDER), ("a record that is not a player", SUPPORTER),
                           ("an unknown id", uuid.uuid4())):
            bad = await patch(grade_vote_counters={"1st Grade": [str(HELPER), str(who)]})
            check(f"{label} in the list is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad))
        bad = await patch(grade_vote_counters={"1st Grade": ["not-a-uuid"]})
        check("a malformed id is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad))
        bad = await patch(grade_vote_counters={"1st Grade": [str(uuid.uuid4()) for _ in range(13)]})
        check("more than 12 people for one team is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad)[:120])
        r3 = await patch(name="Club Champion")
        check("a refused PATCH changed nothing",
              r3[0] == "ok" and r3[1].get("grade_vote_counters") == {"1st Grade": [str(HELPER), str(PAT), str(JOE)]}, str(r3)[:200])
        legacy = await patch(grade_vote_counters={"1st Grade": str(HELPER)})
        check("a bare id (the first release's shape) is still accepted as a list of one",
              legacy[0] == "ok" and legacy[1].get("grade_vote_counters") == {"1st Grade": [str(HELPER)]}, str(legacy)[:200])
        await patch(grade_vote_counters={"1st Grade": [str(HELPER), str(PAT), str(JOE)]})

        # ── Resolution ──
        await db.refresh(medal)
        cfg = vs.effective_config(medal)
        cfg_f = await vs.cfg_for_fixture(db, cfg, fx_firsts)
        check("the chosen team resolves to its list",
              cfg_f.get("voter_mode") == "chosen" and cfg_f.get("vote_chosen") == [str(HELPER), str(PAT), str(JOE)],
              str((cfg_f.get("voter_mode"), cfg_f.get("vote_chosen"))))
        cfg_c = await vs.cfg_for_fixture(db, cfg, fx_colts)
        check("a team that is not on 'chosen' has nobody chosen", not cfg_c.get("vote_chosen"))

        # ── The voting rule ──
        role = lambda who, c=cfg_f: pv._voter_role(c, who, eligible)
        check("a chosen person outside the side may vote", role(helper) == ("player", None), str(role(helper)))
        check("a second chosen person outside the side may vote", role(pat) == ("player", None))
        check("a chosen person who is in the side may vote", role(joe) == ("player", None))
        check("the captain is not chosen, so does not vote", role(cook) == ("none", "chosen_only"), str(role(cook)))
        check("a player in the side who is not chosen does not vote", role(sam) == ("none", "chosen_only"))
        check("a visitor with no name yet is sent to pick one (verify_required)",
              pv._voter_role(cfg_f, None, eligible) == ("none", "verify_required"),
              str(pv._voter_role(cfg_f, None, eligible)))
        check("Colts (all players) is unaffected: a player votes", pv._voter_role(cfg_c, joe, eligible)[0] == "player")

        # fails closed with nobody chosen
        empty = await patch(grade_vote_counters={})
        await db.refresh(medal)
        cfg_e = await vs.cfg_for_fixture(db, vs.effective_config(medal), fx_firsts)
        check("a chosen team with nobody chosen lets nobody vote (fails closed)",
              all(pv._voter_role(cfg_e, who, eligible) == ("none", "no_voters_chosen") for who in (cook, joe, sam, helper)),
              str([pv._voter_role(cfg_e, who, eligible) for who in (cook, joe, helper)]))
        await patch(grade_vote_counters={"1st Grade": [str(HELPER), str(PAT), str(JOE)]})
        await db.refresh(medal)
        cfg = vs.effective_config(medal)

        # ── Landing list and the player's reminder ──
        for who, label in ((HELPER, "helper"), (PAT, "second helper")):
            landing = await pv.get_landing("tok-cc", request(who), db)
            ids = [f["id"] for f in landing["fixtures"]]
            check(f"the {label} is offered that team's game", ids == [str(FX_FIRSTS)], str(ids))
        due, _ = await pa._votes_for_player(db, club, helper)
        check("the helper's page lists the vote as due", [d["fixture_id"] for d in due] == [str(FX_FIRSTS)], str(due))
        due_p, _ = await pa._votes_for_player(db, club, pat)
        check("the second helper's page lists it too", [d["fixture_id"] for d in due_p] == [str(FX_FIRSTS)], str(due_p))
        due_s, _ = await pa._votes_for_player(db, club, sam)
        check("a player who is not chosen has no vote due for that team",
              all(d["fixture_id"] != str(FX_FIRSTS) for d in due_s), str(due_s))

        # ── Public ballot page and submit ──
        page = await attempt(pv.fixture_state("tok-cc", str(FX_FIRSTS), request(HELPER), db))
        ok = page[0] == "ok"
        check("ballot page: a chosen person may vote and is told so",
              ok and page[1]["role"] == "player" and page[1].get("is_chosen") is True, str(page)[:200])
        check("ballot page: they are handed the team list", ok and len(page[1]["players"]) == 4)
        page_cook = await pv.fixture_state("tok-cc", str(FX_FIRSTS), request(CAPTAIN), db)
        check("ballot page: the captain is told the votes are submitted by the chosen people",
              page_cook["role"] == "none" and page_cook["reason"] == "chosen_only" and page_cook["players"] == [],
              str((page_cook["role"], page_cook["reason"])))

        BallotBody = pv.BallotBody
        by_helper = [str(CAPTAIN), str(JOE), str(SAM)]       # 3, 2, 1
        by_joe = [str(CAPTAIN), str(SAM), str(DAVE)]         # 3, 2, 1 (cannot vote for himself)
        refused = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=by_helper), request(CAPTAIN), db))
        check("the captain's own submit is refused (403)", refused[0] == "http" and refused[1] == 403, str(refused))
        outside = await attempt(pv.submit_ballot(
            "tok-cc", str(FX_FIRSTS), BallotBody(picks=[str(HELPER), str(JOE), str(SAM)]), request(HELPER), db))
        check("a chosen person outside the side cannot be voted for (they did not play)",
              outside[0] == "http" and outside[1] == 400, str(outside))
        d1 = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=by_helper), request(HELPER), db))
        d2 = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=by_joe), request(JOE), db))
        check("two chosen people each submit a ballot", d1[0] == "ok" and d2[0] == "ok", str((d1, d2)))
        rows = (await db.execute(select(VoteBallot).where(VoteBallot.fixture_id == FX_FIRSTS))).scalars().all()
        check("two ballots, both recorded as player ballots",
              len(rows) == 2 and all(r.voter_kind == "player" for r in rows)
              and {r.voter_player_id for r in rows} == {HELPER, JOE}, str([(r.voter_player_id, r.voter_kind) for r in rows]))
        d1b = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=by_helper), request(HELPER), db))
        rows = (await db.execute(select(VoteBallot).where(VoteBallot.fixture_id == FX_FIRSTS))).scalars().all()
        check("a chosen person voting again replaces their ballot, not adds one", d1b[0] == "ok" and len(rows) == 2)
        due2, cast2 = await pa._votes_for_player(db, club, helper)
        check("after voting it is no longer due and shows in their own votes",
              due2 == [] and [c["fixture_id"] for c in cast2] == [str(FX_FIRSTS)], str((due2, cast2)))

        # ── The existing count turns their ballots into one result for the game ──
        detail = await attempt(vr.fixture_detail(str(FX_FIRSTS), medal_id=mid, db=db, club=club, user=None))
        res = detail[1]["results"] if detail[0] == "ok" else []
        top = [(r["name"], r["raw"], r["points"]) for r in res]
        check("two ballots add up and convert to the game's 3-2-1 (raw 6/3/2/1 becomes 3/2/1)",
              top[:3] == [("Captain Cook", 6, 3), ("Sam Side", 3, 2), ("Regular Joe", 2, 1)], str(top))
        check("admin game detail lists the people chosen for the game's team, in order",
              detail[0] == "ok" and [c["name"] for c in detail[1]["settings"].get("vote_chosen", [])]
              == ["Helen Helper", "Pat Panel", "Regular Joe"], str(detail[1]["settings"].get("vote_chosen")) if detail[0] == "ok" else str(detail))
        check("voters expected is the people chosen, not the side",
              detail[0] == "ok" and detail[1]["fixture"]["voters_expected"] == 3,
              str(detail[1]["fixture"].get("voters_expected")) if detail[0] == "ok" else str(detail))
        out_names = [o["name"] for o in detail[1]["outstanding"]] if detail[0] == "ok" else []
        check("only the chosen person who has not voted is outstanding", out_names == ["Pat Panel"], str(out_names))
        detail_c = await vr.fixture_detail(str(FX_COLTS), medal_id=mid, db=db, club=club, user=None)
        check("another team is untouched: nobody chosen, the whole side expected",
              detail_c["settings"].get("vote_chosen") == [] and detail_c["fixture"]["voters_expected"] == 4)

        listing = await attempt(vr.list_vote_fixtures(
            year=None, grade_id=None, round_key=None, q=None, medal_id=mid, db=db, club=club, user=None))
        rowf = next((f for f in listing[1]["fixtures"] if f["id"] == str(FX_FIRSTS)), {}) if listing[0] == "ok" else {}
        check("the Games list expects a ballot from each chosen person (3), not the side",
              rowf.get("voters_expected") == 3, str(rowf.get("voters_expected", listing)))

        # Paper ballot entered for a chosen person outside the side is a player ballot.
        entered = await attempt(vr.admin_enter_ballot(
            str(FX_FIRSTS), vr.AdminBallot(voter_player_id=str(PAT), picks=by_helper),
            medal_id=mid, db=db, club=club, user=type("U", (), {"id": None})()))
        rows = (await db.execute(select(VoteBallot).where(VoteBallot.fixture_id == FX_FIRSTS))).scalars().all()
        pat_row = [r for r in rows if r.voter_player_id == PAT]
        check("admin entry for a chosen person is a player ballot",
              entered[0] == "ok" and len(pat_row) == 1 and pat_row[0].voter_kind == "player", str(entered))

        # ── Roster for the picker ──
        voter_options = getattr(vr, "voter_options", None)
        opts = await attempt(voter_options(db=db, club=club, user=None)) if voter_options else ("err", "no voter_options route")
        got = {p["id"] for p in opts[1]["players"]} if opts[0] == "ok" else set()
        check("picker offers people who are not in any side", {str(HELPER), str(PAT)} <= got, str(opts)[:200])
        check("picker never offers another club's player", str(OUTSIDER) not in got)

        # ── Switching a team away from 'chosen' ──
        away = await patch(grade_voter_modes={"1st Grade": "players"})
        await db.refresh(medal)
        cfg_p = await vs.cfg_for_fixture(db, vs.effective_config(medal), fx_firsts)
        check("a team switched to All players ignores the list: the side votes, the helper does not",
              away[0] == "ok" and not cfg_p.get("vote_chosen") and pv._voter_role(cfg_p, sam, eligible)[0] == "player"
              and pv._voter_role(cfg_p, helper, eligible)[0] == "none", str(away)[:150])
        back = await patch(grade_voter_modes={"1st Grade": "chosen"})
        check("switching back to 'chosen' finds the list still there",
              back[0] == "ok" and len(back[1].get("grade_vote_counters", {}).get("1st Grade", [])) == 3, str(back)[:150])

        # ── Clearing ──
        r4 = await patch(grade_vote_counters={"1st Grade": None})
        check("null removes that team's list", r4[0] == "ok" and r4[1].get("grade_vote_counters") == {}, str(r4)[:150])
        await patch(grade_vote_counters={"1st Grade": [str(HELPER)]})
        r5 = await patch(grade_vote_counters={})
        check("an explicit empty map clears every list", r5[0] == "ok" and r5[1].get("grade_vote_counters") == {}, str(r5)[:150])

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
