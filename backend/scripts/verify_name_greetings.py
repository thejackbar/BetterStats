"""Verification: people are greeted by FIRST name in emails, and names printed in
the selection email follow the club's name format.

The bug: a club stores players "Last, First", and several email builders took the
first word (``name.split(" ")[0]``), so "You've been selected, Oliphant," went out.

Runs the SHIPPED load_sheet (real Postgres), the shipped email builders and the
template renderer, plus the shared name helpers.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... python scripts/verify_name_greetings.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + str(detail)) if detail and not cond else ''}")


ORG, FX = uuid.uuid4(), uuid.uuid4()
IAIN, SAM, JACK = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def main() -> None:
    from app.models.db import Base, Fixture, FixtureLineup, Organisation, Player
    from app.services import name_format as nf, selection_notify as sn

    # Presence-safe, so a run against the code before this change reports FAILs, not a crash.
    if not hasattr(nf, "format_player_name"):
        nf.format_player_name = lambda n, f: n
        nf.natural_name = lambda n: n
    if not hasattr(sn, "_shown"):
        sn._shown = lambda p: p["name"]

    # ── the shared helpers ──
    check("first_name of Last, First", nf.first_name("Oliphant, Iain") == "Iain")
    check("first_name of First Last", nf.first_name("Iain Oliphant") == "Iain")
    check("format first_last", nf.format_player_name("Oliphant, Iain", "first_last") == "Iain Oliphant")
    check("format first_initial_last", nf.format_player_name("Oliphant, Iain", "first_initial_last") == "I. Oliphant")
    check("format last_first_initial", nf.format_player_name("Oliphant, Iain", "last_first_initial") == "Oliphant, I.")
    check("format default and unknown stay Last, First",
          nf.format_player_name("Oliphant, Iain", None) == "Oliphant, Iain" == nf.format_player_name("Oliphant, Iain", "bogus"))
    check("a typed two word name is canonical under last_first, not lost under first_last",
          nf.format_player_name("Sam Taylor", "first_last") == "Sam Taylor")
    check("natural_name turns a stored name round but leaves a typed one alone",
          nf.natural_name("Oliphant, Iain") == "Iain Oliphant" and nf.natural_name("Sam Taylor") == "Sam Taylor")

    engine = create_async_engine(DSN)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
    played = date.today() + timedelta(days=3)
    async with Session() as db:
        db.add(Organisation(id=ORG, name="North Perth CC", short_name="NPCC", slug="npcc", player_name_format="first_last"))
        db.add(Player(id=IAIN, organisation_id=ORG, name="Oliphant, Iain", email="iain@example.com", phone="0400000001"))
        db.add(Player(id=SAM, organisation_id=ORG, name="Taylor, Sam", email="sam@example.com", phone="0400000002"))
        db.add(Player(id=JACK, organisation_id=ORG, name="Barendse, Jack", display_name_override="Barendse, Jack",
                      email="jack@example.com", phone=None))
        await db.flush()
        db.add(Fixture(id=FX, organisation_id=ORG, opponent_name="Kalamunda 4th XI", round="9", played_on=played,
                       end_on=played, home_away="AWAY", venue="Kostera Oval", start_time="12:30"))
        await db.flush()
        for order, (pid, cap) in enumerate(((IAIN, True), (SAM, False), (JACK, False)), 1):
            db.add(FixtureLineup(fixture_id=FX, player_id=pid, organisation_id=ORG, batting_order=order, is_captain=cap))
        await db.commit()

    async with Session() as db:
        club = await db.get(Organisation, ORG)
        sheet = await sn.load_sheet(db, club, FX)
        players = {p["player_id"]: p for p in sheet["players"]}
        iain, sam = players[IAIN], players[SAM]

        subj, html_p, text_p = sn.player_email(club, sheet, iain, sn._shown(iain), None)
        check("player email greets by first name (was the surname)", "Hi Iain," in html_p and "Hi Oliphant" not in html_p, html_p[:80])
        check("player email text part greets by first name", text_p.startswith("Hi Iain,"), text_p[:40])
        check("the captain is named in the club's format", "<strong>Iain Oliphant</strong>" in html_p, html_p)
        check("no surname-first name left in the player email", "Oliphant, Iain" not in html_p + text_p)

        subj, html_c, text_c = sn.captain_email(club, sheet, iain)
        check("captain email greets by first name", "Hi Iain," in html_c and text_c.startswith("Hi Iain,"), html_c[:60])
        check("team sheet rows use the club format", "Sam Taylor" in html_c and "Taylor, Sam" not in html_c + text_c)
        check("the 'no mobile on file' list uses the club format", "Jack Barendse" in html_c and "Barendse, Jack" not in html_c, html_c[-200:])

        tpl = {"id": None, "name": "t", "subject": "Selected: {{match}}",
               "html": "<h1>You've been selected, {{first_name}}</h1><p>Captain: {{captain}}</p><p>{{side}}</p>"}
        _s, html_t, text_t = sn.render_template(club, tpl, sheet, to="players", recipient=iain,
                                                captain_name=sn._shown(iain), default_subject="x")
        check("a linked template's {{first_name}} is the first name", "You've been selected, Iain" in html_t, html_t[:120])
        check("{{captain}} and {{side}} follow the club format", "Captain: Iain Oliphant" in html_t and "Sam Taylor" in html_t and "Taylor, Sam" not in html_t, html_t)

        # A club on the default format still gets the first name, and the stored shape in lists.
        club.player_name_format = None
        sheet2 = await sn.load_sheet(db, club, FX)
        i2 = next(p for p in sheet2["players"] if p["player_id"] == IAIN)
        _s, html_d, _t = sn.player_email(club, sheet2, i2, sn._shown(i2), None)
        check("default format: still greeted by first name", "Hi Iain," in html_d)
        check("default format: names stay Last, First", "Oliphant, Iain" in html_d)

        # The sample sheet used to preview a template has no 'shown' and typed names.
        sample = sn.sample_sheet()
        _s, html_s, _t = sn.player_email(club, sample, sample["players"][0], sn._shown(sample["players"][0]), None)
        check("the sample sheet still renders", "Hi Sam," in html_s)

    # Other greetings, through the shipped builders that need no database.
    from app.services import user_invite, sales_email, votes as vs
    check("invite greeting uses the first name", user_invite._greeting("Oliphant, Iain") == "Hi Iain,", user_invite._greeting("Oliphant, Iain"))
    check("sales greeting from a stored name", sales_email._greeting("Oliphant, Iain") == "Hi Iain,", sales_email._greeting("Oliphant, Iain"))
    check("sales greeting from a typed name", sales_email._greeting("Iain Oliphant") == "Hi Iain,")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
