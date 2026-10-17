"""Verification: a player's own page as a dashboard of club-chosen modules, and
BetterSelect Fines, against a real Postgres.

Asked for: on the page a player opens with the last 4 digits of their mobile, add
modules (their team's ladder, fees owing, a small season overview) so it works as
a little dashboard. And "Fines": after a game a side runs a fines session and the
money goes into a pot. It is switched on per side, tracks what each player owes
week on week, says how to pay (PayID, bank transfer), sits under BetterSelect and
shows on the player's own page.

Drives the SHIPPED route bodies (`routers/fines`, `public_availability.get_my_profile`
and `get_my_ladder`, `availability.update_self_service`) and the shipped merge
carry, never a re-implementation.

CONTROL MODE: against the previous commit `app.routers.fines` and
`app.services.player_dashboard` do not exist; they are imported inside a guard
and every read is presence-safe, so the control FAILS the checks instead of
crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_dashboard_and_fines.py
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import (
    FeeMember, FeeMemberSeason, FeePayment, FeeSchedule, Grade, Organisation, Player,
    PlayerSeasonStats, Season, Team, User,
)

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


def guarded(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


async def main():
    await base.build_schema()
    ddl = guarded("app.services.fines_ddl")
    async with engine.begin() as conn:
        for _ in range(2):  # the lifespan re-runs the list on every boot
            for stmt in (ddl.STATEMENTS if ddl else []):
                await conn.execute(text(stmt))
        for mod in ("selection_lock_ddl", "team_sides_ddl", "fixture_side_ddl", "fixture_pin_ddl", "audit_ddl", "availability_maybe_ddl"):
            m = guarded(f"app.services.{mod}")
            for stmt in (m.STATEMENTS if m else []):
                await conn.execute(text(stmt))
    fr = guarded("app.routers.fines")
    pd = guarded("app.services.player_dashboard")
    import app.routers.availability as av
    import app.routers.public_availability as pa
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from app.config.settings import settings
    import app.services.grassroots_scores_client as gr

    org, other_org, uid, season, grade, t1, t2 = (uuid.uuid4() for _ in range(7))
    ids = {n: uuid.uuid4() for n in ("sam", "ann", "fill", "idle", "bob", "stranger")}
    token = "tok-" + uuid.uuid4().hex
    fee_season = season

    async with Session() as db:
        db.add(Organisation(id=org, name="Dash CC", slug=f"dash-{org.hex[:8]}", module_overrides=["select", "fees"],
                            availability_link_token=token, availability_self_service_enabled=True))
        db.add(Organisation(id=other_org, name="Elsewhere CC", slug=f"els-{other_org.hex[:8]}", module_overrides=["select"]))
        db.add(User(id=uid, username=f"u{uid.hex[:8]}", email=f"{uid.hex[:6]}@x.com", password_hash="x", display_name="Fi Fines"))
        db.add(Season(id=season, organisation_id=org, name="Summer 26/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st Grade", grassroots_id=str(grade)))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="1st XI", sequence=1, grade_id=grade))
        db.add(Team(id=t2, organisation_id=org, name="2nd XI", sequence=2))
        await db.flush()
        names = {"sam": "Sam Sledge", "ann": "Ann Anchor", "fill": "Fiona Fillin", "idle": "Ian Idle", "bob": "Bob Rival"}
        for k, nm in names.items():
            db.add(Player(id=ids[k], organisation_id=org, name=nm, gender="male", is_player=True, status="active",
                          phone=f"04000000{list(names).index(k)}{list(names).index(k)}{list(names).index(k)}{list(names).index(k)}"))
        db.add(Player(id=ids["stranger"], organisation_id=other_org, name="Sid Elsewhere", gender="male", is_player=True, status="active"))
        await db.flush()
        for k in ("sam", "ann", "idle"):
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t, :p, :o)"),
                             {"t": t1, "p": ids[k], "o": org})
        await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t, :p, :o)"),
                         {"t": t2, "p": ids["bob"], "o": org})
        db.add(PlayerSeasonStats(player_id=ids["sam"], season_id=season, matches=11, batting_innings=10, runs=412,
                                 not_outs=2, balls_faced=500, high_score=87, wickets=9, runs_conceded=240, catches=6))
        await db.commit()

    class _Req:
        pass

    def req_for(pid):
        c = jose_jwt.encode({"club": str(org), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

    async def admin(fn, *args, club_id=org, **kw):
        """Call a shipped admin route body as the club's selector. Returns (result, HTTPException)."""
        async with Session() as db:
            club = await db.get(Organisation, club_id)
            user = await db.get(User, uid)
            try:
                return await fn(*args, db=db, club=club, **{k: v for k, v in kw.items()}, _=user) if "_" in fn.__code__.co_varnames[:fn.__code__.co_argcount + fn.__code__.co_kwonlyargcount] \
                    else await fn(*args, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e

    async def profile(pid):
        async with Session() as db:
            return await pa.get_my_profile(token, req_for(pid), None, db)

    async def sql(q, **p):
        async with Session() as db:
            return (await db.execute(text(q), p)).fetchall()

    if fr is None or pd is None:
        print("\n# CONTROL: the fines router / dashboard service do not exist in this commit")
        check("app.routers.fines exists", fr is not None)
        check("app.services.player_dashboard exists", pd is not None)
        check("the fine tables exist", len(await sql("SELECT 1 FROM information_schema.tables WHERE table_name = 'fine_entries'")) > 0)
        prof = await profile(ids["sam"])
        check("the profile lists its modules", "modules" in prof)
        print(f"\n{base.PASS} passed, {base.FAIL} failed")
        await engine.dispose()
        sys.exit(1 if base.FAIL else 0)

    print("\n# A. The DDL is idempotent and the tables are there")
    check("all four fine tables exist", len(await sql(
        "SELECT 1 FROM information_schema.tables WHERE table_name IN ('fine_settings','fine_types','fine_entries','fine_payments')")), 4)

    print("\n# B. Squads and switching Fines on")
    res, err = await admin(fr.list_squads)
    sq = {s["name"]: s for s in (res or {}).get("squads", [])}
    check("both squads are listed, Fines off, nothing owed", (sorted(sq), [s["enabled"] for s in sq.values()], [s["owing"] for s in sq.values()]),
          (["1st XI", "2nd XI"], [False, False], [0.0, 0.0]))
    t1s = str(t1)
    res, err = await admin(fr.patch_settings, t1s, fr.SettingsPatch(enabled=True, payid="pay@dashcc.org", payid_name="Dash CC Fines",
                                                                      bsb="063-000", account_number="1234 5678", account_name="Dash CC"))
    check("switched on with how to pay", (res or {}).get("settings", {}).get("enabled"), True)
    res, _ = await admin(fr.patch_settings, t1s, fr.SettingsPatch(reference_hint="Your name"))
    s = res["settings"]
    check("a PATCH that doesn't send a field leaves it alone", (s["enabled"], s["payid"], s["bsb"], s["reference_hint"]),
          (True, "pay@dashcc.org", "063-000", "Your name"))
    res, _ = await admin(fr.patch_settings, t1s, fr.SettingsPatch(bsb=""))
    check("an explicit empty string clears one", (res["settings"]["bsb"], res["settings"]["payid"]), ("", "pay@dashcc.org"))
    res, _ = await admin(fr.patch_settings, t1s, fr.SettingsPatch(bsb="063-000"))
    _, err = await admin(fr.patch_settings, str(uuid.uuid4()), fr.SettingsPatch(enabled=True))
    check("an unknown squad is a 404", err.status_code if err else None, 404)
    _, err = await admin(fr.patch_settings, t1s, fr.SettingsPatch(enabled=True), club_id=other_org)
    check("another club cannot touch this squad", err.status_code if err else None, 404)

    print("\n# C. The fine list")
    res, _ = await admin(fr.create_type, t1s, fr.TypeIn(name="Dropped catch", amount=5))
    drop = res["id"]
    res, _ = await admin(fr.create_type, t1s, fr.TypeIn(name="Late to training", amount="10.50"))
    late = res["id"]
    _, err = await admin(fr.create_type, t1s, fr.TypeIn(name="dropped CATCH", amount=5))
    check("a duplicate name is refused", err.status_code if err else None, 409)
    _, err = await admin(fr.create_type, t1s, fr.TypeIn(name="Bad", amount=-3))
    check("a negative amount is refused", err.status_code if err else None, 422)
    _, err = await admin(fr.create_type, t1s, fr.TypeIn(name="Bad", amount="abc"))
    check("a junk amount is refused", err.status_code if err else None, 422)

    print("\n# D. A fines session")
    d1 = date.today() - timedelta(days=7)
    d2 = date.today()
    body = fr.EntriesIn(fined_on=d1, items=[
        fr.FineItem(player_id=str(ids["sam"]), fine_type_id=drop, quantity=2),
        fr.FineItem(player_id=str(ids["ann"]), reason="Sunglasses at night", amount=20),
        fr.FineItem(player_id=str(ids["fill"]), fine_type_id=late),
    ])
    res, err = await admin(fr.add_entries, t1s, body)
    check("a session of four fines (two catches) totals 10 + 20 + 10.50", (res or {}).get("created"), 4)
    check("total", (res or {}).get("total"), 40.5)
    rows = await sql("SELECT count(*) FROM fine_entries WHERE team_id = :t", t=t1)
    before = rows[0][0]
    _, err = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=d1, items=[
        fr.FineItem(player_id=str(ids["sam"]), reason="x", amount=1), fr.FineItem(player_id=str(ids["stranger"]), reason="x", amount=1)]))
    check("a player from another club is refused", err.status_code if err else None, 404)
    check("and the session wrote nothing (all or nothing)", (await sql("SELECT count(*) FROM fine_entries WHERE team_id = :t", t=t1))[0][0], before)
    _, err = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=d1, items=[fr.FineItem(player_id=str(ids["sam"]), reason="x", amount=0)]))
    check("a zero fine is refused", err.status_code if err else None, 422)
    _, err = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=d1, items=[fr.FineItem(player_id=str(ids["sam"]))]))
    check("a line with no reason and no fine is refused", err.status_code if err else None, 422)
    _, err = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=date.today() + timedelta(days=30), items=[fr.FineItem(player_id=str(ids["sam"]), reason="x", amount=1)]))
    check("a fine dated next month is refused", err.status_code if err else None, 422)
    res, _ = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=d2, items=[fr.FineItem(player_id=str(ids["sam"]), reason="Chirping the umpire", amount=7)]))

    print("\n# E. The tracker: week on week, derived balances")
    res, _ = await admin(fr.get_squad, t1s)
    pl = {p["name"]: p for p in res["players"]}
    check("sam owes 17 (10 last week + 7 this week)", pl["Sam Sledge"]["owing"], 17.0)
    check("sam's fines by date", pl["Sam Sledge"]["by_date"], {d1.isoformat(): 10.0, d2.isoformat(): 7.0})
    check("a fill-in who was fined is listed, marked outside the squad", (pl["Fiona Fillin"]["in_squad"], pl["Fiona Fillin"]["owing"]), (False, 10.5))
    check("a squad member with no fines is still listed at zero", (pl["Ian Idle"]["in_squad"], pl["Ian Idle"]["owing"]), (True, 0.0))
    check("the 2nd XI player is not in the 1st XI tracker", "Bob Rival" in pl, False)
    check("the two fine dates are the columns, newest first", res["dates"], [d2.isoformat(), d1.isoformat()])
    check("totals", res["totals"], {"fined": 47.5, "paid": 0.0, "owing": 47.5})
    check("candidates are the other active players, not squad members or other clubs",
          sorted(c["name"] for c in res["candidates"]), ["Bob Rival"])
    check("the fine list carries both fines", sorted(t["name"] for t in res["types"]), ["Dropped catch", "Late to training"])

    print("\n# F. Payments into the pot")
    res, _ = await admin(fr.add_payment, t1s, fr.PaymentIn(player_id=str(ids["sam"]), amount=10, method="PayID"))
    pay_sam = res["id"]
    res, _ = await admin(fr.add_payment, t1s, fr.PaymentIn(player_id=str(ids["ann"]), amount=25, method="Cash"))
    res, _ = await admin(fr.get_squad, t1s)
    pl = {p["name"]: p for p in res["players"]}
    check("sam owes 7 after paying 10", pl["Sam Sledge"]["owing"], 7.0)
    check("paying more than owed shows as credit (negative owing)", pl["Ann Anchor"]["owing"], -5.0)
    check("the pot holds 35", res["totals"]["paid"], 35.0)
    _, err = await admin(fr.add_payment, t1s, fr.PaymentIn(player_id=str(ids["sam"]), amount=0))
    check("a zero payment is refused", err.status_code if err else None, 422)
    _, err = await admin(fr.add_payment, t1s, fr.PaymentIn(player_id=str(ids["stranger"]), amount=5))
    check("a payment for another club's player is refused", err.status_code if err else None, 404)

    print("\n# G. Nothing is deleted: void and restore")
    sam_entry = (await sql("SELECT id FROM fine_entries WHERE player_id = :p AND reason = 'Chirping the umpire'", p=ids["sam"]))[0][0]
    await admin(fr.void_entry, str(sam_entry))
    res, _ = await admin(fr.get_squad, t1s)
    check("a voided fine drops out of the balance", {p["name"]: p["owing"] for p in res["players"]}["Sam Sledge"], 0.0)
    check("but the row is still there", (await sql("SELECT voided_at IS NOT NULL FROM fine_entries WHERE id = :i", i=sam_entry))[0][0], True)
    led, _ = await admin(fr.player_ledger, t1s, str(ids["sam"]))
    check("the ledger still lists it, marked voided", [e["voided"] for e in led["entries"] if e["reason"] == "Chirping the umpire"], [True])
    await admin(fr.restore_entry, str(sam_entry))
    await admin(fr.void_payment, str(pay_sam))
    res, _ = await admin(fr.get_squad, t1s)
    check("restoring a fine and voiding a payment moves the balance both ways", {p["name"]: p["owing"] for p in res["players"]}["Sam Sledge"], 17.0)
    await admin(fr.restore_payment, str(pay_sam))
    _, err = await admin(fr.void_entry, str(sam_entry), club_id=other_org)
    check("another club cannot void this club's fine", err.status_code if err else None, 404)

    print("\n# H. Editing the fine list never rewrites history")
    await admin(fr.patch_type, drop, fr.TypePatch(amount=50))
    res, _ = await admin(fr.get_squad, t1s)
    check("repricing a fine leaves what was handed out alone", {p["name"]: p["owing"] for p in res["players"]}["Sam Sledge"], 7.0)
    await admin(fr.patch_type, drop, fr.TypePatch(archived=True))
    res, _ = await admin(fr.get_squad, t1s)
    check("an archived fine leaves the quick list, and is kept", ([t["name"] for t in res["types"]], [t["name"] for t in res["archived_types"]]),
          (["Late to training"], ["Dropped catch"]))
    _, err = await admin(fr.add_entries, t1s, fr.EntriesIn(fined_on=d2, items=[fr.FineItem(player_id=str(ids["sam"]), fine_type_id=drop)]))
    check("an archived fine can't be handed out", err.status_code if err else None, 422)
    await admin(fr.patch_type, drop, fr.TypePatch(archived=False, amount=5))

    print("\n# I. The player's page: the club's modules")
    prof = await profile(ids["sam"])
    check("a club that never chose gets the original page, plus Fines for a squad that has it on (Show squad is off, so the squad section carries a note)", prof["modules"], ["availability", "squad", "selected", "training", "fines"])
    check("a module that is off is never queried", (prof["season"], prof["fees"]), (None, None))

    res, _ = await admin(av.update_self_service, av.SelfServiceUpdate(dashboard_modules=["bogus", "season", "fines", "season", "fees", "ladder"]))
    check("unknown and repeated keys are dropped, order kept", [m["key"] for m in res["dashboard_modules"] if m["enabled"]], ["season", "fines", "fees", "ladder"])
    cat = {m["key"]: m for m in res["dashboard_modules"]}
    check("fees is flagged when the PIN is the only guard", cat["fees"]["blocked"], None)
    check("ladder says it needs Show squad", bool(cat["ladder"]["blocked"]), True)
    check("squad does not (it explains itself instead)", cat["squad"]["blocked"], None)
    res, _ = await admin(av.update_self_service, av.SelfServiceUpdate(allow_maybe=True))
    check("a POST that doesn't send dashboard_modules leaves the choice alone", [m["key"] for m in res["dashboard_modules"] if m["enabled"]], ["season", "fines", "fees", "ladder"])

    print("\n# J. Fines on the player's page")
    prof = await profile(ids["sam"])
    check("Sam sees Fines, in the club's order, the ladder held back without Show squad", prof["modules"], ["season", "fines", "fees"])
    fn = (prof["fines"] or [{}])[0]
    check("Sam owes 7 in the 1st XI", (fn.get("squad"), fn.get("owing"), fn.get("fined"), fn.get("paid")), ("1st XI", 7.0, 17.0, 10.0))
    check("week on week, newest first", [(w["date"], w["total"]) for w in fn.get("weeks", [])], [(d2.isoformat(), 7.0), (d1.isoformat(), 10.0)])
    check("how to pay is shown, empty fields left out", fn.get("how_to_pay"),
          {"payid": "pay@dashcc.org", "payid_name": "Dash CC Fines", "account_name": "Dash CC", "bsb": "063-000", "account_number": "1234 5678", "reference_hint": "Your name"})
    check("the pot total is the squad's", fn.get("pot"), 35.0)
    blob = json.dumps(prof)
    check("nobody else's name or id is in Sam's page", any(n in blob for n in ("Ann Anchor", "Fiona", "Ian Idle", "Bob Rival", str(ids["ann"]))), False)
    prof_fill = await profile(ids["fill"])
    check("a fill-in who was fined sees what they owe", ((prof_fill["fines"] or [{}])[0].get("owing"), "fines" in prof_fill["modules"]), (10.5, True))
    prof_idle = await profile(ids["idle"])
    check("a squad member with no fines sees a zero balance, not nothing", ((prof_idle["fines"] or [{}])[0].get("owing"), "fines" in prof_idle["modules"]), (0.0, True))
    prof_bob = await profile(ids["bob"])
    check("a player in a squad without Fines sees no Fines module", ("fines" in prof_bob["modules"], prof_bob["fines"]), (False, []))
    await admin(fr.patch_settings, t1s, fr.SettingsPatch(enabled=False))
    prof = await profile(ids["sam"])
    check("switching Fines off removes it from the page", "fines" in prof["modules"], False)
    res, _ = await admin(fr.get_squad, t1s)
    check("and keeps every fine", res["totals"]["fined"], 47.5)
    await admin(fr.patch_settings, t1s, fr.SettingsPatch(enabled=True))

    print("\n# K. Season overview")
    prof = await profile(ids["sam"])
    se = prof["season"] or {}
    check("the most recent season in a small block", (se.get("season"), se.get("matches"), se.get("runs"), se.get("high_score"), se.get("wickets"), se.get("catches")),
          ("Summer 26/27", 11, 412, 87, 9, 6))
    prof_ann = await profile(ids["ann"])
    check("a player with no games gets an empty block, not zeroes", prof_ann["season"], None)

    print("\n# L. Fees owing: the club's fees module, and only with the PIN on")
    async with Session() as db:
        sched = FeeSchedule(id=uuid.uuid4(), organisation_id=org, season_id=fee_season, name="Senior", membership_amount=100, match_day_rate=0)
        db.add(sched)
        fm = FeeMember(id=uuid.uuid4(), organisation_id=org, player_id=ids["sam"], full_name="Sam Sledge")
        db.add(fm)
        await db.flush()
        ms = FeeMemberSeason(id=uuid.uuid4(), member_id=fm.id, season_id=fee_season, organisation_id=org, fee_schedule_id=sched.id)
        db.add(ms)
        await db.flush()
        db.add(FeePayment(id=uuid.uuid4(), member_season_id=ms.id, organisation_id=org, amount=40, paid_at=date.today(), kind="membership"))
        await db.commit()
    prof = await profile(ids["sam"])
    fe = prof["fees"] or {}
    check("Sam owes 60 of 100 after paying 40", (fe.get("on_record"), fe.get("total_outstanding"), fe.get("membership_outstanding")), (True, 60.0, 60.0))
    prof_ann = await profile(ids["ann"])
    check("a player with no fee record is told so, never shown $0", prof_ann["fees"], {"on_record": False})
    await admin(av.update_self_service, av.SelfServiceUpdate(require_pin=False))
    prof = await profile(ids["sam"])
    check("with the PIN off, fees are not served at all (fail closed)", ("fees" in prof["modules"], prof["fees"]), (False, None))
    res, _ = await admin(av.update_self_service, av.SelfServiceUpdate())
    check("and the admin list says why", bool({m["key"]: m for m in res["dashboard_modules"]}["fees"]["blocked"]), True)
    await admin(av.update_self_service, av.SelfServiceUpdate(require_pin=True))
    async with Session() as db:
        o = await db.get(Organisation, org)
        o.module_overrides = ["select"]
        await db.commit()
    prof = await profile(ids["sam"])
    check("a club without the fees module never gets the Fees module", ("fees" in prof["modules"], prof["fees"]), (False, None))
    async with Session() as db:
        o = await db.get(Organisation, org)
        o.module_overrides = ["select", "fees"]
        await db.commit()

    print("\n# M. Ladder")
    async def ladder_as(pid):
        async with Session() as db:
            try:
                return await pa.get_my_ladder(token, req_for(pid), db), None
            except HTTPException as e:
                return None, e
    _, err = await ladder_as(ids["sam"])
    check("the ladder is refused while Show squad is off", err.status_code if err else None, 404)
    await admin(av.update_self_service, av.SelfServiceUpdate(show_squad=True))
    canned = {"ladders": [{"name": "Overall", "columns": [{"id": "played", "heading": "P"}, {"id": "won", "heading": "W"},
                                                          {"id": "lost", "heading": "L"}, {"id": "competitionPoints", "heading": "PTS"},
                                                          {"id": "netRunRate", "heading": "NRR"}],
                           "pools": [{"teams": [
                               {"id": "a", "displayName": "Rovers", "rank": 1, "owningOrganisation": {"id": "zzz", "name": "Rovers"},
                                "ladderData": [{"id": "played", "val": 5}, {"id": "won", "val": 4}, {"id": "lost", "val": 1}, {"id": "competitionPoints", "val": 40}, {"id": "netRunRate", "val": 1.2}]},
                               {"id": "b", "displayName": "Dash CC 1st XI", "rank": 2, "owningOrganisation": {"id": str(org), "name": "Dash CC"},
                                "ladderData": [{"id": "played", "val": 5}, {"id": "won", "val": 3}, {"id": "lost", "val": 2}, {"id": "competitionPoints", "val": 30}]}]}]}]}
    calls = []
    async def fake_ladder(gid):
        calls.append(gid)
        return canned
    gr.get_grade_ladder = fake_ladder
    res, err = await ladder_as(ids["sam"])
    lad = ((res or {}).get("ladders") or [{}])[0]
    check("Sam gets the ladder for his squad only", ((res or {}).get("ladders") and len(res["ladders"])), 1)
    check("with the club's row marked and the ladder trimmed to P W L PTS", ([r["team_name"] for r in lad.get("rows", []) if r["is_club"]], [c["id"] for c in lad.get("columns", [])]),
          (["Dash CC 1st XI"], ["played", "won", "lost", "competitionPoints"]))
    check("only the player's squad was fetched, not every team", len(calls), 1)
    res, _ = await ladder_as(ids["idle"])
    check("a squad member with a grade gets it too", len(res["ladders"]), 1)
    res, _ = await ladder_as(ids["bob"])
    check("a squad with no linked grade has no ladder (empty, not an error)", res, {"ladders": []})
    await admin(av.update_self_service, av.SelfServiceUpdate(dashboard_modules=[]))
    _, err = await ladder_as(ids["sam"])
    check("with the module off the ladder route is a 404", err.status_code if err else None, 404)
    prof = await profile(ids["sam"])
    check("an explicit empty choice means every module is off (not the default page)", (prof["modules"], prof["selected"], prof["training"]["upcoming"]), ([], [], []))

    print("\n# N. Merging two player records carries their fines")
    keep, drop_p = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Player(id=keep, organisation_id=org, name="Keeper", is_player=True, status="active"))
        db.add(Player(id=drop_p, organisation_id=org, name="Dupe", is_player=True, status="active"))
        await db.flush()
        await db.execute(text("INSERT INTO fine_entries (organisation_id, team_id, player_id, reason, amount, fined_on) VALUES (:o,:t,:p,'x',9,:d)"),
                         {"o": org, "t": t1, "p": drop_p, "d": d1})
        await db.execute(text("INSERT INTO fine_payments (organisation_id, team_id, player_id, amount, paid_on) VALUES (:o,:t,:p,4,:d)"),
                         {"o": org, "t": t1, "p": drop_p, "d": d1})
        from app.services import merge_carry
        moved = await merge_carry.carry_rows(db, keep, drop_p, org)
        await db.commit()
    check("the merge reports moving both ledgers", sorted(k for k in moved if k.startswith("fine_")), ["fine_entries.player_id", "fine_payments.player_id"])
    check("the fines now belong to the keeper", (await sql("SELECT count(*) FROM fine_entries WHERE player_id = :p", p=keep))[0][0], 1)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
