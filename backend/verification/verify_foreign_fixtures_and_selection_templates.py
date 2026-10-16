"""Verification: other clubs' fixtures on a club's list, and selection emails written from a template.

Reported by North Perth (which shares a first word with North Beach):

  1. North Beach fixtures still on North Perth's Fixtures list.
     v9.111.0 stopped NEW syncs pulling another club's games in, but a game CA
     still lists in the shared grade never looks stale, so a row stored before
     that fix was never cleared. The Sync now removes it (or, when an XI or votes
     sit on it, keeps it and marks it CANCELLED).

  2. Selection emails can be written in Admin: a BetterComms template linked to
     the captain's email and to the players' email, filled in from the match.

Drives the SHIPPED route bodies and services against a real Postgres. CONTROL
MODE: against the commit before this change, new names are read with getattr and
report failed checks rather than crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_foreign_fixtures_and_selection_templates.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, User, Player, Team, Grade, Season, Fixture, FixtureLineup, Game, GameAppearance, CommsTemplate,
)
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def _create_stmt(table):
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", MAIN.read_text())
    return m.group(1) if m else None


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        for mod in ("junior_hiding_ddl", "player_privacy_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for mod in ("selection_draft_ddl", "selection_notice_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass


class Recorder:
    """An email provider that records instead of sending."""
    name = "recorder"

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        from app.services import email_service
        self.sent.append(msg)
        return email_service.SendResult(ok=True, message_id="rec")


async def _missing(*_a, **_kw):
    """Control mode: the route does not exist yet, so it answers with nothing."""
    return {}


async def main():
    await build_schema()
    import time
    from app.services import club_match, email_service, grassroots_scores_client as gr
    import app.routers.fixtures as fxr

    NP, NB, BAY, SCAR = (uuid.uuid4() for _ in range(4))
    user_id = uuid.uuid4()
    np_season, g_np = uuid.uuid4(), uuid.uuid4()
    GUID = str(uuid.uuid4())
    day = (date.today() + timedelta(days=9)).isoformat()

    def match(mid, home, home_org, away, away_org, status="UPCOMING", status_id=0, no_ids=False):
        def team(name, org, is_home):
            t = {"isHome": is_home, "displayName": name}
            if not no_ids:
                t["owningOrganisation"] = {"id": str(org)}
            return t
        return {"id": mid, "status": status, "statusId": status_id,
                "matchSchedule": [{"startDateTime": f"{day}T12:00:00"}],
                "round": {"name": "Round 5"}, "venue": {"name": "Main Oval"},
                "teams": [team(home, home_org, True), team(away, away_org, False)]}

    ca_matches = [
        match("m-ours", "Fieldmasters 1st Grade", NP, "Bayswater 1sts", BAY),
        match("m-nb-scar", "North Beach 1sts", NB, "Scarborough 1sts", SCAR),
        match("m-nb-work", "North Beach 2nds", NB, "Bayswater 2nds", BAY),
    ]
    no_ids = match("m-noids", "North Beach 3rds", None, "Scarborough 3rds", None, no_ids=True)

    async def fake_grade_matches(grade_id, *, force=False):
        gr._grade_matches_cache[grade_id] = (time.time(), ca_matches)
        return ca_matches
    gr.get_grade_matches = fake_grade_matches

    print("\n[1] Other clubs' games in a shared grade")
    np_club_ns = SimpleNamespace(id=NP, name="North Perth Cricket Club", short_name=None, playhq_id=None)
    between = getattr(club_match, "fixture_is_between_others", None)
    sides = getattr(gr, "match_sides", None)
    check("a game between two other named clubs is not ours",
          bool(between and sides and between(np_club_ns, sides(ca_matches[1]))), True)
    check("...but our own, sponsor-named side is ours",
          bool(between and sides and between(np_club_ns, sides(ca_matches[0]))), False)
    check("...and a payload with no organisation ids is never called foreign (name alone cannot prove it)",
          bool(between and sides and between(np_club_ns, sides(no_ids))), False)

    async with Session() as db:
        db.add(Organisation(id=NP, name="North Perth Cricket Club", slug=f"northperth-{NP.hex[:6]}",
                            module_overrides=["select", "comms"], subscription_status="active"))
        db.add(Organisation(id=NB, name="North Beach Cricket Club", slug=f"northbeach-{NB.hex[:6]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=np_season, organisation_id=NP, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_np, season_id=np_season, name="1st Grade", grassroots_id=GUID))
        await db.flush()
        stored = {}
        def fx(key, **kw):
            stored[key] = uuid.uuid4()
            db.add(Fixture(id=stored[key], organisation_id=NP, grade_id=g_np, status="UPCOMING",
                           played_on=date.today() + timedelta(days=9), **kw))
        # as an older sync stored them: other clubs' games on North Perth's list
        fx("ours", source="grassroots", playhq_id="m-ours", home_team="Fieldmasters 1st Grade", away_team="Bayswater 1sts",
           home_away="HOME", opponent_name="Bayswater 1sts")
        fx("nb", source="grassroots", playhq_id="m-nb-scar", home_team="North Beach 1sts", away_team="Scarborough 1sts",
           home_away="HOME", opponent_name="Scarborough 1sts")
        fx("nb_work", source="grassroots", playhq_id="m-nb-work", home_team="North Beach 2nds", away_team="Bayswater 2nds",
           home_away="HOME", opponent_name="Bayswater 2nds")
        fx("manual", source="manual", label="Friendly v Alumni", opponent_name="Alumni")
        await db.commit()
    async with engine.begin() as conn:
        # somebody picked a side on one of North Beach's games
        pid = uuid.uuid4()
        await conn.execute(text("INSERT INTO players (id, organisation_id, name, status, is_player) "
                                "VALUES (:i, :o, 'Pick Ed', 'active', TRUE)"), {"i": pid, "o": NP})
        await conn.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id, batting_order) "
                                "VALUES (:f, :p, :o, 1)"), {"f": stored["nb_work"], "p": pid, "o": NP})

    async def state():
        async with Session() as db:
            rows = (await db.execute(text("SELECT id, playhq_id, source, status FROM fixtures WHERE organisation_id = :o"),
                                     {"o": NP})).all()
        by_id = {r.id: r for r in rows}
        return {k: (by_id[v].status if v in by_id else None) for k, v in stored.items()}, rows

    async with Session() as db:
        club = await db.get(Organisation, NP)
        res = await fxr.sync_fixtures(db=db, club=club, _user=None)
    st, rows = await state()
    check("Sync: the one game that is ours is synced", res["synced"], 1)
    check("Sync: North Beach v Scarborough (nothing picked on it) is gone from North Perth's list", st["nb"], None)
    check("Sync: a North Beach game with a side picked on it is kept, marked CANCELLED, not deleted",
          st["nb_work"], "CANCELLED")
    check("Sync: North Perth's own game is untouched", st["ours"], "UPCOMING")
    check("Sync: a hand-made fixture is untouched", st["manual"], "UPCOMING")
    check("Sync: the list holds our game, the kept one and the manual one only",
          sorted((r.playhq_id or r.source) for r in rows), sorted(["m-ours", "m-nb-work", "manual"]))
    check("Sync: the response says what happened", ("Removed 1" in res["detail"], res["cancelled"]), (True, 1))
    async with engine.connect() as conn:
        n = await conn.scalar(text("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id = :f"), {"f": stored["nb_work"]})
    check("...its picked side was not deleted", n, 1)

    async with Session() as db:
        club = await db.get(Organisation, NP)
        res2 = await fxr.sync_fixtures(db=db, club=club, _user=None)
    check("A second Sync changes nothing more (not re-cancelled, not re-removed)",
          (res2["removed"], res2["cancelled"], res2["synced"]), (0, 0, 1))

    async with Session() as db:
        club = await db.get(Organisation, NP)
        listed = await fxr.list_fixtures(upcoming_only=True, db=db, club=club)
    check("The Fixtures list no longer shows North Beach v Scarborough",
          [f["playhq_id"] for f in listed if f["playhq_id"] and f["status"] != "CANCELLED"], ["m-ours"])

    # ── 2: selection emails from a template ──────────────────────────────────
    print("\n[2] Selection emails written from a template")
    from app.services import selection_notify as notify, selection_rules as rules
    import app.routers.selection_rules as srr
    from fastapi import HTTPException

    cfg_keys = ("captain_email_template_id", "player_email_template_id")
    check("the club settings carry the two template links",
          all(k in rules.club_config(SimpleNamespace(selection_rules_config=None)) for k in cfg_keys), True)

    rec = Recorder()
    email_service.get_email_provider = lambda: rec
    email_service.email_is_live = lambda: True

    P = [uuid.uuid4() for _ in range(4)]
    people = [("Cara Captain", "cara@np.test", "0411 111 111"), ("Sam Smith", "sam@np.test", "0422 222 222"),
              ("Pat Phone", "pat@np.test", "0433 333 333"), ("Jess <b>Odd</b>", "jess@np.test", "0444 444 444")]
    async with engine.begin() as conn:
        for pid, (n, e, ph) in zip(P, people):
            await conn.execute(text("INSERT INTO players (id, organisation_id, name, email, phone, status, is_player) "
                                    "VALUES (:i, :o, :n, :e, :ph, 'active', TRUE)"),
                               {"i": pid, "o": NP, "n": n, "e": e, "ph": ph})
    fx_id = uuid.uuid4()
    async with Session() as db:
        t_cap = CommsTemplate(organisation_id=NP, name="Captain sheet",
                              subject="Skip: {{match}} on {{date}}",
                              html="<h2>Hello {{first_name}}</h2><p>{{club}} v {{opponent}} at {{venue}}, {{when}}. Home or away: {{home_away}}.</p>{{team_sheet}}<p>Side: {{side}}</p><p>{{nonsense}}</p>")
        t_pl = CommsTemplate(organisation_id=NP, name="Player welcome", subject="",
                             html="<p>Hi {{first_name}}, you're in v {{opponent}}. Captain: {{captain}}.</p>{{note}}{{team_sheet}}<p>{{side}}</p>")
        t_sales = CommsTemplate(organisation_id=NP, name="Sales one", subject="x", html="<p>sales</p>", sales_template_key="trial_information")
        db.add_all([t_cap, t_pl, t_sales])
        db.add(Fixture(id=fx_id, organisation_id=NP, source="manual", played_on=date.today() + timedelta(days=5),
                       status="UPCOMING", label="x", opponent_name="Scarborough", venue="Hamer Park",
                       start_time="12:00", round="Round 7", home_away="AWAY"))
        await db.commit()
        for i, pid in enumerate(P):
            db.add(FixtureLineup(fixture_id=fx_id, player_id=pid, organisation_id=NP, batting_order=i + 1,
                                 is_captain=(i == 1), is_wicket_keeper=(i == 2)))
        await db.commit()
        cap_id, pl_id, sales_id = t_cap.id, t_pl.id, t_sales.id

    # standard wording when nothing is linked
    async with Session() as db:
        club = await db.get(Organisation, NP)
        r0 = await notify.send_to_captain(db, club, fx_id, user_id=user_id)
    std = rec.sent[-1]
    check("nothing linked: the standard captain email goes", (r0["status"], std.subject.startswith("Team sheet:")), ("sent", True))

    # the settings route: link, validate, clear
    async def patch(**kw):
        async with Session() as db:
            club = await db.get(Organisation, NP)
            try:
                out = await srr.patch_settings(srr.SettingsBody(**kw), db=db, club=club, _=None)
                return out, None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code
    out, err = await patch(captain_email_template_id=str(cap_id), player_email_template_id=str(pl_id))
    check("a club can link both emails to its own templates",
          (err, (out or {}).get("captain_email_template_id"), (out or {}).get("player_email_template_id")), (None, str(cap_id), str(pl_id)))
    _, err = await patch(captain_email_template_id=str(sales_id))
    check("the Sales Workspace's templates cannot be linked", err, 404)
    _, err = await patch(captain_email_template_id=str(uuid.uuid4()))
    check("another club's (or an unknown) template cannot be linked", err, 404)
    _, err = await patch(captain_email_template_id="not-a-uuid")
    check("a garbled id is refused", err, 400)
    out, _ = await patch(notify_captain_on_confirm=True)
    check("a PATCH that does not mention the links leaves them alone",
          ((out or {}).get("captain_email_template_id"), (out or {}).get("player_email_template_id")), (str(cap_id), str(pl_id)))

    async with Session() as db:
        club = await db.get(Organisation, NP)
        listing = await getattr(srr, "email_templates", _missing)(db=db, club=club, _=None)
    check("the picker lists the club's templates, not the Sales Workspace's",
          sorted(t["name"] for t in listing.get("templates", [])), ["Captain sheet", "Player welcome"])
    check("...says BetterComms is available and lists the variables",
          (listing.get("comms_available"), any(v["name"] == "team_sheet" for v in listing.get("variables", []))), (True, True))

    # the captain's email now comes from the template
    async with Session() as db:
        club = await db.get(Organisation, NP)
        r1 = await notify.send_to_captain(db, club, fx_id, user_id=user_id)
    m = rec.sent[-1]
    check("captain: sent to the captain", (r1["status"], m.to_email, r1.get("template")), ("sent", "sam@np.test", "Captain sheet"))
    check("captain: subject carries the match and date, not braces",
          ("Scarborough" in m.subject and "{{" not in m.subject and m.subject.startswith("Skip: ")), True)
    check("captain: the body is the club's wording, filled in",
          ("Hello Sam" in m.html and "Hamer Park" in m.html and "Away" in m.html and "North Perth Cricket Club v Scarborough" in m.html), True)
    check("captain: the team sheet block carries every mobile",
          all(ph in m.html and ph in m.text for _n, _e, ph in people), True)
    check("captain: an unknown token comes out blank, never as braces", "{{" not in m.html and "{{" not in m.text, True)
    check("captain: names are escaped in html", "Jess &lt;b&gt;Odd&lt;/b&gt;" in m.html and "<b>Odd</b>" not in m.html, True)
    check("captain: the plain text part has no markup and no stylesheet", ("<" not in m.text.replace("<b>", "")) or "<table" not in m.text, True)
    check("captain: a fragment is wrapped in the club's shell, with no unsubscribe line",
          ("<!doctype html>" in m.html and "unsubscribe" not in m.html.lower()), True)

    async with Session() as db:
        club = await db.get(Organisation, NP)
        rp = await notify.send_to_players(db, club, fx_id, user_id=user_id, message="Be there at 11.")
    pmsgs = [x for x in rec.sent if x.to_email in ("cara@np.test", "pat@np.test", "jess@np.test") and "Hi " in x.html]
    check("players: each selected player is emailed from the template", (rp["sent"], rp.get("template")), (4, "Player welcome"))
    pm = next(x for x in rec.sent if x.to_email == "pat@np.test")
    check("players: filled in per player, with the captain's name and the selector's note",
          ("Hi Pat" in pm.html and "Captain: Sam Smith" in pm.html and "Be there at 11." in pm.html), True)
    check("players: a template with no subject keeps the standard subject", pm.subject.startswith("Selected:"), True)
    check("players: a phone number pasted into a player's template comes out blank",
          not any(ph in pm.html or ph in pm.text for _n, _e, ph in people), True)
    check("players: the side is there, names only", ("Cara Captain" in pm.html and "Sam Smith" in pm.html), True)

    # a deleted template falls back, with a note, and still sends
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM comms_templates WHERE id = :i"), {"i": cap_id})
    before = len(rec.sent)
    async with Session() as db:
        club = await db.get(Organisation, NP)
        r2 = await notify.send_to_captain(db, club, fx_id, user_id=user_id)
    check("a deleted template: the standard email still goes, with a note the selector can read",
          (r2["status"], len(rec.sent) - before, rec.sent[-1].subject.startswith("Team sheet:"), bool(r2.get("template_note"))),
          ("sent", 1, True, True))

    # without BetterComms the template is not used
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE organisations SET module_overrides = CAST(:m AS jsonb) WHERE id = :o"), {"m": '["select"]', "o": NP})
    async with Session() as db:
        club = await db.get(Organisation, NP)
        before = len(rec.sent)
        r3 = await notify.send_to_players(db, club, fx_id, user_id=user_id)
        listing = await getattr(srr, "email_templates", _missing)(db=db, club=club, _=None)
    check("without BetterComms: players get the standard email and are told why",
          (r3["sent"], rec.sent[-1].subject.startswith("Selected:"), bool(r3.get("template_note"))), (4, True, True))
    check("...and the picker says BetterComms is not on", (listing.get("comms_available"), listing.get("templates", [])), (False, []))
    _, err = await patch(captain_email_template_id=str(pl_id))
    check("...and a template cannot be linked", err, 402)
    out, err = await patch(captain_email_template_id="", player_email_template_id=None)
    check("an explicit clear goes back to the standard wording",
          (err, (out or {}).get("captain_email_template_id"), (out or {}).get("player_email_template_id")), (None, None, None))

    # preview with sample data
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE organisations SET module_overrides = CAST(:m AS jsonb) WHERE id = :o"), {"m": '["select", "comms"]', "o": NP})
    async with Session() as db:
        club = await db.get(Organisation, NP)
        pv = await getattr(srr, "preview_email_template", _missing)(
            getattr(srr, "TemplatePreviewBody", lambda **k: None)(template_id=str(pl_id), to="players"),
            db=db, club=club, _=None)
    check("preview: shows the template filled in with a made-up match, sends nothing",
          ("Sample Opponents CC" in pv.get("html", "") and "Meet at the ground" in pv.get("html", "")), True)
    async with Session() as db:
        club = await db.get(Organisation, NP)
        try:
            await srr.preview_email_template(srr.TemplatePreviewBody(template_id=str(uuid.uuid4()), to="players"),
                                             db=db, club=club, _=None)
            check("preview: an unknown template is a 404", False)
        except AttributeError:
            check("preview: an unknown template is a 404", False)
        except HTTPException as e:
            check("preview: an unknown template is a 404", e.status_code, 404)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
