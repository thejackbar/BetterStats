"""Verification that scrubbing a removed player never damages a relative.

The case: Toby Marlowe asked to be removed. The club also has Tom Marlowe
(same first initial) and Sam Marlowe (different initial). A scorecard line
"c T Marlowe b J Smith" or "c Marlowe b J Smith" could be any of them.

The rule being proved:
  * a form is scrubbed SITE-WIDE only when it can only mean the removed person;
  * on one match scorecard, an ambiguous form is scrubbed only when the card
    shows the removed person played and no other player in that card could be
    meant by it;
  * Tom's and Sam's own rows, names and ids are never touched.

Every "left alone" check is paired with a check that the same form IS scrubbed
where it is unambiguous, so a filter that scrubs nothing cannot pass (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://root@/scrub_test?host=/var/run/postgresql \
      python verification/verify_privacy_scrub_surnames.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, Player
from app.services import privacy_scrub

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []
STARS = privacy_scrub.REMOVED_NAME


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


ORG = uuid.uuid4()
TOBY, TOM, SAM, PAT = (uuid.uuid4() for _ in range(4))


async def seed(trent_name: str = "Toby Marlowe", others: bool = True) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in (
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_at TIMESTAMPTZ",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_by TEXT",
            "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_reason TEXT",
        ):
            await conn.execute(text(stmt))
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Applecross", is_active=True))
        await s.flush()
        rows = [(TOBY, trent_name)]
        if others:
            rows += [(TOM, "Tom Marlowe"), (SAM, "Sam Marlowe")]
        rows += [(PAT, "Pat Plain")]
        for pid, nm in rows:
            s.add(Player(id=pid, name=nm, organisation_id=ORG, grassroots_id=str(pid)))
        await s.commit()
        await s.execute(text("UPDATE players SET privacy_hidden_at = NOW(), privacy_hidden_by='t' WHERE id = :i"),
                        {"i": TOBY})
        await s.commit()
    privacy_scrub.forget()


def card(*, trent_in: bool, tom_in: bool, sam_in: bool, lines: list[str]) -> dict:
    """A scorecard shaped like /games/{id}/scorecard: our rows plus opposition lines."""
    batting = [{"player_id": str(PAT), "player_name": "Pat Plain", "dismissal_type": lines[0] if lines else None}]
    for pid, nm, present in ((TOBY, "Toby Marlowe", trent_in), (TOM, "Tom Marlowe", tom_in),
                             (SAM, "Sam Marlowe", sam_in)):
        if present:
            batting.append({"player_id": str(pid), "player_name": nm, "dismissal_type": "not out"})
    opposition = [{"player_name": f"Opp {i}", "dismissal_type": ln} for i, ln in enumerate(lines)]
    return {"batting": batting, "opposition_batting": opposition}


async def main() -> int:
    # ------------------------------------------------------------ site-wide
    print("site-wide: Toby removed, Tom (same initial) and Sam (other initial) at the club")
    await seed()
    sc = await privacy_scrub.get_scrubber()
    check("a scrubber exists", sc is not None)

    out = sc.scrub("Toby Marlowe and Marlowe, Toby")
    check("his FULL name is scrubbed (no other Toby)", "Toby" not in out and STARS in out, out)
    out = sc.scrub("c T Marlowe b J Smith")
    check("'T Marlowe' is NOT scrubbed site-wide (Tom has the same initial)",
          out == "c T Marlowe b J Smith", out)
    check("'S Marlowe' (Sam) is untouched", sc.scrub("c S Marlowe b J Smith") == "c S Marlowe b J Smith")
    out = sc.scrub("c Marlowe b J Smith")
    check("a bare 'Marlowe' is NOT scrubbed (three people could be meant)",
          out == "c Marlowe b J Smith", out)
    check("Tom's and Sam's full names are untouched",
          sc.scrub("Tom Marlowe, Sam Marlowe") == "Tom Marlowe, Sam Marlowe")
    check("his id is replaced and nobody else's is",
          str(TOBY) not in sc.scrub(f"{TOBY} {TOM}") and str(TOM) in sc.scrub(f"{TOBY} {TOM}"))

    # --------------------------------------------------- initial differs: scrubbed
    print("an initial that is only his")
    await seed()
    async with Session() as s:
        await s.execute(text("DELETE FROM players WHERE id=:i"), {"i": TOM})
        await s.commit()
    privacy_scrub.forget()
    sc = await privacy_scrub.get_scrubber()
    out = sc.scrub("c T Marlowe b J Smith")
    check("with only Sam (S) at the club, 'T Marlowe' can only be Toby: scrubbed", out == f"c {STARS} b J Smith", out)
    check("...and 'S Marlowe' (Sam) is still untouched", sc.scrub("c S Marlowe b J Smith") == "c S Marlowe b J Smith")
    check("a bare 'Marlowe' is still NOT scrubbed (Sam shares it)",
          sc.scrub("c Marlowe b J Smith") == "c Marlowe b J Smith")

    # ---------------------------------------------------------- one scorecard
    print("one match scorecard (Toby, Tom and Sam all exist at the club)")
    await seed()
    sc = await privacy_scrub.get_scrubber()

    # Toby played, Tom and Sam did not: the lines can only mean Toby.
    c = card(trent_in=True, tom_in=False, sam_in=False,
             lines=["c T Marlowe b J Smith", "st †Marlowe b J Smith", "run out (Marlowe/Jones)"])
    out = sc.scrub_card(c)
    txt = str(out)
    check("Toby in the match, no other Marlowe: 'T Marlowe' is scrubbed", "T Marlowe" not in txt, txt[:200])
    check("...and the keeper's bare '†Marlowe' too", "†Marlowe" not in txt)
    check("...and a bare surname in a run-out", "(Marlowe/" not in txt)

    # Toby and Tom both played: 'T Marlowe' could be either.
    c = card(trent_in=True, tom_in=True, sam_in=False, lines=["c T Marlowe b J Smith"])
    out = sc.scrub_card(c)
    check("Toby AND Tom in the match: 'c T Marlowe' is LEFT ALONE (could be Tom)",
          out["opposition_batting"][0]["dismissal_type"] == "c T Marlowe b J Smith",
          out["opposition_batting"][0]["dismissal_type"])

    # Toby and Sam played: initial T is only Toby, but a bare surname could be Sam.
    c = card(trent_in=True, tom_in=False, sam_in=True,
             lines=["c T Marlowe b J Smith", "c Marlowe b J Smith", "c S Marlowe b J Smith"])
    out = sc.scrub_card(c)
    lines = [r["dismissal_type"] for r in out["opposition_batting"]]
    check("Toby and Sam in the match: 'T Marlowe' is Toby: scrubbed", lines[0] == f"c {STARS} b J Smith", lines[0])
    check("...a bare 'Marlowe' could be Sam: left alone", lines[1] == "c Marlowe b J Smith", lines[1])
    check("...'S Marlowe' is Sam: untouched", lines[2] == "c S Marlowe b J Smith", lines[2])

    # Toby did not play: an ambiguous line is somebody else's.
    c = card(trent_in=False, tom_in=True, sam_in=False, lines=["c T Marlowe b J Smith"])
    out = sc.scrub_card(c)
    check("Toby NOT in the match (Tom is): 'c T Marlowe' is Tom's, left alone",
          out["opposition_batting"][0]["dismissal_type"] == "c T Marlowe b J Smith")
    check("...and Tom's own row is untouched",
          any(b["player_name"] == "Tom Marlowe" for b in out["batting"]))

    # --------------------------------------------- through the real middleware
    print("through the middleware on /games/{id}/scorecard")
    app = FastAPI()
    app.add_middleware(privacy_scrub.PrivacyScrubMiddleware)
    current = {"card": None}

    @app.get("/games/{gid}/scorecard")
    async def _sc(gid: str):
        return JSONResponse(current["card"])

    @app.get("/games/{gid}/other")
    async def _other(gid: str):
        return JSONResponse(current["card"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://m") as c_:
        current["card"] = card(trent_in=True, tom_in=False, sam_in=False, lines=["c T Marlowe b J Smith"])
        r = await c_.get("/games/1/scorecard")
        j = r.json()
        check("scorecard route: the resolvable line is scrubbed",
              j["opposition_batting"][0]["dismissal_type"] == f"c {STARS} b J Smith", str(j["opposition_batting"][0]))
        check("scorecard route: his own row's id and name are gone",
              str(TOBY) not in r.text and "Toby Marlowe" not in r.text)
        check("scorecard route: Pat's row is intact", any(b["player_name"] == "Pat Plain" for b in j["batting"]))
        r = await c_.get("/games/1/other")
        check("any OTHER route keeps the site-wide rule: the ambiguous line is left alone there",
              "c T Marlowe b J Smith" in r.text, r.text[:160])
        current["card"] = card(trent_in=True, tom_in=True, sam_in=False, lines=["c T Marlowe b J Smith"])
        r = await c_.get("/games/1/scorecard")
        check("scorecard route: with Tom also in the match the line is left alone",
              "c T Marlowe b J Smith" in r.text and "Tom Marlowe" in r.text)

    # ------------------------------------------------ BetterSocials / publishing
    print("publishing: BetterSocials reads, with relatives at the club and a signed-in admin")
    await seed()
    from jose import jwt
    from app.config.settings import settings
    from app.routers.auth import COOKIE_NAME
    tok = jwt.encode({"sub": str(PAT)}, settings.secret_key, algorithm=settings.algorithm)
    signed_in = {"Cookie": f"{COOKIE_NAME}={tok}"}
    publishing = {**signed_in, "X-Publishing": "1"}

    def row(pid, first, last, short):
        return {"first": first, "last": last, "short": short, "pid": str(pid), "guid": str(pid), "points": 10}

    ranked = {"match": {"opponent": "WEMBLEY"}, "players": [
        row(TOBY, "Toby", "Marlowe", "T. MARLOWE"),
        row(TOM, "Tom", "Marlowe", "T. MARLOWE"),
        row(SAM, "Sam", "Marlowe", "S. MARLOWE"),
        row(PAT, "Pat", "Plain", "P. PLAIN"),
    ]}
    sc_card = {"batting": [row(TOBY, "Toby", "Marlowe", "T. MARLOWE"),
                           row(TOM, "Tom", "Marlowe", "T. MARLOWE")],
               "opposition_batting": [{"player_name": "Opp", "dismissal_type": "c T Marlowe b J Smith"}]}
    roster = [{"id": str(TOBY), "name": "Toby Marlowe"}, {"id": str(TOM), "name": "Tom Marlowe"},
              {"id": str(PAT), "name": "Pat Plain"}]
    store = {"potm": ranked, "scorecard": sc_card, "roster": roster}
    pub_app = FastAPI()
    pub_app.add_middleware(privacy_scrub.PrivacyScrubMiddleware)

    @pub_app.get("/admin/social/potm/{m}")
    async def _potm(m: str):
        return JSONResponse(store["potm"])

    @pub_app.get("/admin/social/totw")
    async def _totw():
        return JSONResponse(store["potm"])

    @pub_app.get("/admin/social/scorecard/{m}")
    async def _scard(m: str):
        return JSONResponse(store["scorecard"])

    @pub_app.get("/club-admin/players")
    async def _roster():
        return JSONResponse(store["roster"])

    @pub_app.get("/selection/overview")
    async def _sel():
        return JSONResponse(store["roster"])

    @pub_app.get("/players/{pid}/profile")
    async def _profile(pid: str):
        return JSONResponse({"id": pid, "name": "Toby Marlowe"})

    @pub_app.get("/iq/opponent/{x}")
    async def _iq(x: str):
        return JSONResponse(store["roster"])

    @pub_app.get("/scout/players")
    async def _scout():
        return JSONResponse(store["roster"])

    transport = httpx.ASGITransport(app=pub_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://m") as c_:
        sc = await privacy_scrub.get_scrubber()
        for path in ("/iq/opponent/1", "/scout/players"):
            j = (await c_.get(path, headers=signed_in)).json()
            check(f"{path} (shows OTHER clubs' players) is scrubbed even with a valid session",
                  all(r["id"] != str(TOBY) and r["name"] != "Toby Marlowe" for r in j), str(j))
        # Player of the match shortlist: he must not be nominable.
        j = (await c_.get("/admin/social/potm/1", headers=signed_in)).json()
        names = [(p["first"], p["last"]) for p in j["players"]]
        check("BetterSocials POTM (signed-in admin): he is NOT on the shortlist",
              ("Toby", "Marlowe") not in names and all(str(TOBY) not in str(p) for p in j["players"]), str(names))
        check("...Tom, Sam and Pat are all still on it (a relative is never dropped)",
              {("Tom", "Marlowe"), ("Sam", "Marlowe"), ("Pat", "Plain")} <= set(names), str(names))
        j = (await c_.get("/admin/social/totw", headers=signed_in)).json()
        check("BetterSocials Team of the Week: he is not in the pool",
              all(p["first"] != "Toby" for p in j["players"]) and len(j["players"]) == 3)
        # The full scorecard keeps his row so the totals add up, masked.
        j = (await c_.get("/admin/social/scorecard/1", headers=signed_in)).json()
        b = j["batting"][0]
        check("BetterSocials scorecard: his row is KEPT but masked (first, last and short all gone)",
              b["first"] == "" and b["last"] == STARS and b["short"] == STARS and b["pid"] != str(TOBY) and b["guid"] != str(TOBY),
              str(b))
        check("...Tom's row beside it is untouched", j["batting"][1]["first"] == "Tom" and j["batting"][1]["short"] == "T. MARLOWE")
        check("...and the ambiguous dismissal line is resolved from who played (Tom also played: left alone)",
              j["opposition_batting"][0]["dismissal_type"] == "c T Marlowe b J Smith")
        # Same route without any session: still scrubbed (control for the sign-in logic).
        j = (await c_.get("/admin/social/scorecard/1")).json()
        check("the same scorecard with no session is masked too", j["batting"][0]["last"] == STARS)
        # A roster read for a publishing screen, via the header, drops him...
        j = (await c_.get("/club-admin/players", headers=publishing)).json()
        check("the roster read by a publishing screen (X-Publishing) omits him",
              [r["name"] for r in j] == ["Tom Marlowe", "Pat Plain"], str(j))
        j = (await c_.get("/selection/overview", headers=publishing)).json()
        check("...and so does the selection read by a publishing screen", all(str(TOBY) not in str(r) for r in j))
        # ...but the club's own Players screen (no header, valid session) still has him to manage.
        j = (await c_.get("/club-admin/players", headers=signed_in)).json()
        check("the club's own Players screen (session, no publishing header) still lists him to manage",
              [r["name"] for r in j][0] == "Toby Marlowe" and j[0]["id"] == str(TOBY), str(j))
        j = (await c_.get(f"/players/{TOBY}/profile", headers=signed_in)).json()
        check("the admin profile editor route is the club's record: real name and id",
              j["name"] == "Toby Marlowe" and j["id"] == str(TOBY))
        j = (await c_.get(f"/players/{TOBY}/profile")).json()
        check("the same profile route with no session is scrubbed", j["name"] != "Toby Marlowe")

    # ----------------------------------------------- no relatives: scrub it all
    print("no other Marlowe at the club")
    await seed(others=False)
    sc = await privacy_scrub.get_scrubber()
    for line in ("c T Marlowe b J Smith", "c Marlowe b J Smith", "st †Marlowe b J Smith"):
        out = sc.scrub(line)
        check(f"{line!r}: nobody else could be meant, scrubbed site-wide", "Marlowe" not in out, out)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
