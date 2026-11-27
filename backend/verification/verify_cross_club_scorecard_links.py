"""Verification: a match between two BetterCricket clubs links BOTH sides' players.

Asked for on a live match page: when the opposition is also a BetterCricket club,
its players have profiles of their own, so their names on the scorecard should
link through to them (and the side's name to that club's page), letting people
jump between the two clubs.

Before this change only the viewing club's side was ever resolved to `players`
rows; every opposition row came back `player_id: None` whoever the opposition
was.

Covers:
  A. Read from club A's side, club B's batters, bowlers and did-not-bat players
     link to B's own player rows (by GUID, by uuid5 collision id, by name).
  B. A participant B does not hold stays unlinked; A's own side is unchanged.
  C. A player B hides from the public (is_public FALSE) stays unlinked.
  D. `innings_totals[n].club_slug` names each side's club page.
  E. Read from B's side (?org=B), A's players link on the other card.
  F. B with its public site off (inactive, or behind a PIN) gets no links and
     no club_slug, and neither does a side whose club we do not hold.

Drives the SHIPPED route body with the Grassroots fetch stubbed. CONTROL MODE:
against the commit before this change every opposition link reads None and the
club_slug key is absent; checks read through .get so they fail, not crash
(rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_cross_club_scorecard_links.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

# Schema builder shared with the North Perth suite (copied by exec of its
# preamble, so the two never drift apart). The preamble stops before that
# suite's own main().
_np_src = (Path(__file__).resolve().parent / "verify_north_perth_report.py").read_text()
_ns: dict = {"__file__": str(Path(__file__).resolve().parent / "verify_north_perth_report.py")}
exec(compile(_np_src.split("class Recorder")[0], "verify_north_perth_report_preamble", "exec"), _ns)
build_schema, engine, Session = _ns["build_schema"], _ns["engine"], _ns["Session"]

from app.models.db import Organisation, Player, Grade, Season, Game  # noqa: E402

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


def _bat(pid, name, runs, out=True, dnb=False):
    if dnb:
        return {"participantId": pid, "playerShortName": name, "dismissalTypeId": 0, "dismissalType": "Did Not Bat"}
    return {"participantId": pid, "playerShortName": name, "batOrder": 1, "runsScored": runs, "ballsFaced": runs + 3,
            "foursScored": 0, "sixesScored": 0, "dismissalTypeId": 2 if out else 1,
            "dismissalType": "Bowled" if out else "Not Out", "dismissalText": "b X" if out else "not out"}


def _bowl(pid, name, wkts):
    return {"participantId": pid, "playerShortName": name, "oversBowled": 4, "maidensBowled": 0,
            "runsConceded": 20, "wicketsTaken": wkts, "wideBalls": 0, "noBalls": 0}


def _main_py_table(name: str) -> str:
    """A lifespan CREATE TABLE copied verbatim from app/main.py (rule 24)."""
    import re
    src = (Path(__file__).resolve().parent.parent / "app/main.py").read_text()
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + name + r" \([\s\S]*?\n\s*\))", src)
    return m.group(1)


async def main():
    await build_schema()
    async with engine.begin() as conn:
        # Read by the link resolver for both clubs (merged-away ids).
        await conn.execute(text(_main_py_table("merge_logs")))
        await conn.execute(text("ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS undone_at TIMESTAMPTZ"))
    import app.routers.games as games
    from app.services import grassroots_scores_client

    A, B = uuid.uuid4(), uuid.uuid4()
    UNKNOWN_CLUB = uuid.uuid4()
    a_season, b_season, g_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    game_id = uuid.uuid4()
    other_game = uuid.uuid4()
    TA, TB = "team-a-" + A.hex[:6], "team-b-" + B.hex[:6]

    # Raw CA participant GUIDs on the team sheet.
    g = {k: str(uuid.uuid4()) for k in (
        "a1", "a2", "b_guid", "b_collide", "b_name", "b_dnb", "b_hidden", "b_stranger", "b_bowler")}
    # Player rows: A holds its own two. B holds one by raw GUID, one under the
    # uuid5(org, guid) id (A happened to hold that GUID first), one matched by
    # name only (a different GUID stored), a DNB player, a hidden player, a bowler.
    pa1, pa2 = uuid.UUID(g["a1"]), uuid.UUID(g["a2"])
    pb_guid = uuid.UUID(g["b_guid"])
    pb_collide = uuid.uuid5(B, g["b_collide"])
    pb_name, pb_dnb, pb_hidden, pb_bowler = (uuid.uuid4() for _ in range(4))

    async with Session() as db:
        db.add(Organisation(id=A, name="Alpha Cricket Club", slug=f"alpha-{A.hex[:6]}", is_active=True))
        db.add(Organisation(id=B, name="Bravo Cricket Club", slug=f"bravo-{B.hex[:6]}", is_active=True))
        db.add(Season(id=a_season, organisation_id=A, name="Summer", year=2026))
        db.add(Season(id=b_season, organisation_id=B, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_a, season_id=a_season, name="1st Grade"))
        await db.flush()
        for pid, org, name, guid in (
            (pa1, A, "Adam Archer", g["a1"]), (pa2, A, "Alan Apple", g["a2"]),
            (pb_guid, B, "Ben Baker", g["b_guid"]),
            (pb_collide, B, "Bill Collins", g["b_collide"]),
            (pb_name, B, "Brad Nash", str(uuid.uuid4())),       # stored under another GUID
            (pb_dnb, B, "Bob Dunn", g["b_dnb"]),
            (pb_hidden, B, "Barry Hyde", g["b_hidden"]),
            (pb_bowler, B, "Bert Bowles", g["b_bowler"]),
        ):
            db.add(Player(id=pid, organisation_id=org, name=name, grassroots_id=guid,
                          gender="male", is_player=True, status="active"))
        await db.flush()
        db.add(Game(id=game_id, grade_id=g_a, played_at=date.today() - timedelta(days=2),
                    home_team="Alpha 1sts", away_team="Bravo 1sts", winning_team="Alpha 1sts",
                    result="WIN", home_org_id=A, away_org_id=B))
        db.add(Game(id=other_game, grade_id=g_a, played_at=date.today() - timedelta(days=5),
                    home_team="Alpha 1sts", away_team="Unknown 1sts", winning_team="Alpha 1sts",
                    result="WIN", home_org_id=A, away_org_id=None))
        await db.commit()
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE players SET is_public = FALSE WHERE id = :p"), {"p": pb_hidden})

    def payload(opp_owner):
        return {
            "teams": [
                {"id": TA, "displayName": "Alpha 1sts", "isHome": True,
                 "owningOrganisation": {"id": str(A)},
                 "players": [{"participantId": g["a1"], "playerShortName": "A Archer"},
                             {"participantId": g["a2"], "playerShortName": "A Apple"}]},
                {"id": TB, "displayName": "Bravo 1sts", "isHome": False,
                 "owningOrganisation": {"id": str(opp_owner)},
                 "players": [{"participantId": g[k], "playerShortName": n} for k, n in (
                     ("b_guid", "B Baker"), ("b_collide", "B Collins"), ("b_name", "Brad Nash"),
                     ("b_dnb", "B Dunn"), ("b_hidden", "B Hyde"), ("b_stranger", "Z Stranger"),
                     ("b_bowler", "B Bowles"))]},
            ],
            "matchSummary": {"teams": [{"displayName": "Alpha 1sts", "isHome": True},
                                       {"displayName": "Bravo 1sts", "isHome": False}]},
            "innings": [
                {"inningsOrder": 1, "battingTeamId": TA, "numberOfWicketsFallen": 1, "totalExtras": 2,
                 "batting": [_bat(g["a1"], "A Archer", 40), _bat(g["a2"], "A Apple", 12, out=False)],
                 "bowling": [_bowl(g["b_bowler"], "B Bowles", 1), _bowl(g["b_stranger"], "Z Stranger", 0)]},
                {"inningsOrder": 2, "battingTeamId": TB, "numberOfWicketsFallen": 4, "totalExtras": 1,
                 "batting": [_bat(g["b_guid"], "B Baker", 20), _bat(g["b_collide"], "B Collins", 5),
                             _bat(g["b_name"], "B Nash", 7), _bat(g["b_hidden"], "B Hyde", 3),
                             _bat(g["b_stranger"], "Z Stranger", 0)],
                 "bowling": [_bowl(g["a1"], "A Archer", 3)]},
            ],
        }

    state = {"owner": B}

    async def fake_scorecard(*a, **k):
        return payload(state["owner"])
    grassroots_scores_client.get_match_scorecard = fake_scorecard

    async def card(gid=game_id, **kw):
        async with Session() as db:
            return await games.get_scorecard(str(gid), db=db, viewer=None, **kw)

    def by_name(rows, name):
        return next((r for r in rows if r.get("player_name") == name), {})

    def bat_link(c, shown):
        return by_name(c["opp_batting"], shown).get("player_id")

    # ── A, B, C, D ────────────────────────────────────────────────────────────
    print("\n[A-D] Read from Alpha's side, Bravo is a BetterCricket club")
    c = await card(org_param=str(A))
    check("Alpha's page", c["organisation_id"], str(A))
    check("Bravo batter held by raw GUID links to Bravo's player", bat_link(c, "Ben Baker"), str(pb_guid))
    check("Bravo batter held under uuid5(org, guid) links", bat_link(c, "Bill Collins"), str(pb_collide))
    check("Bravo batter matched by full team-sheet name links", bat_link(c, "Brad Nash"), str(pb_name))
    check("Bravo did-not-bat player links", bat_link(c, "Bob Dunn"), str(pb_dnb))
    check("Bravo bowler links", by_name(c["opp_bowling"], "Bert Bowles").get("player_id"), str(pb_bowler))
    check("a Bravo participant Bravo does not hold stays unlinked",
          [r.get("player_id") for r in c["opp_batting"] + c["opp_bowling"] if r.get("player_name") == "Z Stranger"],
          [None, None])
    check("a Bravo player hidden from the public stays unlinked", bat_link(c, "B Hyde"), None)
    check("...and shows the team-sheet name, not the stored one",
          any(r.get("player_name") == "Barry Hyde" for r in c["opp_batting"]), False)
    check("Alpha's own batters still link to Alpha's players",
          sorted(r["player_id"] for r in c["batting"] if r.get("player_id")), sorted([str(pa1), str(pa2)]))
    check("Alpha's own bowler still links", by_name(c["bowling"], "Adam Archer").get("player_id"), str(pa1))
    check("no Bravo id leaks onto Alpha's card",
          any(r.get("player_id") in {str(pb_guid), str(pb_bowler)} for r in c["batting"] + c["bowling"]), False)
    check("innings 1 (Alpha batting) links to Alpha's page", c["innings_totals"][1].get("club_slug"), f"alpha-{A.hex[:6]}")
    check("innings 2 (Bravo batting) links to Bravo's page", c["innings_totals"][2].get("club_slug"), f"bravo-{B.hex[:6]}")
    check("figures are untouched (Bravo innings runs)", c["innings_totals"][2]["runs"], 35)

    # ── E ─────────────────────────────────────────────────────────────────────
    print("\n[E] Read from Bravo's side")
    cb = await card(org_param=str(B))
    check("Bravo's page", cb["organisation_id"], str(B))
    check("Bravo's own batters are now 'ours' and link",
          by_name(cb["batting"], "Ben Baker").get("player_id"), str(pb_guid))
    check("Alpha's batter links on the other card",
          by_name(cb["opp_batting"], "Adam Archer").get("player_id"), str(pa1))
    check("Alpha's bowler links on the other card",
          by_name(cb["opp_bowling"], "Adam Archer").get("player_id"), str(pa1))
    check("Bravo's own hidden player is not touched by this change (ours side, as before)",
          by_name(cb["batting"], "Barry Hyde").get("player_id"), str(pb_hidden))

    # ── F ─────────────────────────────────────────────────────────────────────
    print("\n[F] No live public site, or a club we do not hold: no links")
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE organisations SET is_active = FALSE WHERE id = :b"), {"b": B})
    c = await card(org_param=str(A))
    check("Bravo inactive: its batter is unlinked", bat_link(c, "B Baker"), None)
    check("...and its side has no club page", c["innings_totals"][2].get("club_slug"), None)
    check("...while Alpha's still links", c["innings_totals"][1].get("club_slug"), f"alpha-{A.hex[:6]}")
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE organisations SET is_active = TRUE, password_protected = TRUE WHERE id = :b"),
                           {"b": B})
    c = await card(org_param=str(A))
    check("Bravo behind a PIN: unlinked", bat_link(c, "B Baker"), None)
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE organisations SET password_protected = FALSE WHERE id = :b"), {"b": B})
    c = await card(org_param=str(A))
    check("Bravo back on: links again (the off states were the only cause)", bat_link(c, "Ben Baker"), str(pb_guid))

    state["owner"] = UNKNOWN_CLUB
    c = await card(gid=other_game, org_param=str(A))
    check("opposition owned by a club we do not hold: unlinked", bat_link(c, "B Baker"), None)
    check("...and no club page for that side", c["innings_totals"][2].get("club_slug"), None)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
