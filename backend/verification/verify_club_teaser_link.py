"""The linkage between a teaser token and a club: token to club, UTM code to
token, and the id /trial's club picker returns to token.

Runs the SHIPPED service against a real Postgres. The rules under test: every
identifier answers from the one club row; an identifier two clubs share answers
nothing (never the wrong club's season); only good, unregistered snapshots are
reachable by identifier; a malformed value is refused before it reaches SQL.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_link.py
"""
from __future__ import annotations

import asyncio
import json
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
    from app.services import club_teaser_link as link
    from app.services.club_teaser_ddl import STATEMENTS
    for name in ("club_for_token", "token_for_utm", "token_for_ca_org", "link_health", "unlinked_clubs"):
        if not hasattr(link, name):
            MISSING.append(f"club_teaser_link.{name} is missing")
except ImportError as exc:  # pragma: no cover - control run only
    link = None
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


async def main() -> None:
    if MISSING:
        check("the linkage service is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'lnk-customer'"))

    cust_org = g()
    K: dict[str, dict] = {}
    async with Session() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (CAST(:i AS uuid), 'Cust', 'lnk-customer', true)"),
                        {"i": cust_org})

        async def club(key, name, *, utm="", status="ok", ca=None, guid=None, registered=False):
            cid, tok = g(), "tk" + uuid.uuid4().hex[:14]
            guid = guid or g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules,
                status, source, utm_code, existing_org_id) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '[]'::jsonb,
                'new', 'grassroots_api', :u, CAST(:org AS uuid))"""),
                {"id": cid, "g": guid, "n": name, "u": utm or None, "org": cust_org if registered else None})
            body = {"schema": 2, "club": {"name": name, "ca_org_id": ca}} if status == "ok" else None
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version)
                VALUES (CAST(:id AS uuid), :g, :t, :st, CAST(:sn AS jsonb), 1)"""),
                {"id": cid, "g": guid, "t": tok, "st": status, "sn": json.dumps(body) if body else None})
            K[key] = {"id": cid, "token": tok, "guid": guid, "ca": ca, "utm": utm}

        CA = lambda: g()  # noqa: E731
        await club("alpha", "Alpha CC", utm="alpha-cricket-club", ca=CA())
        await club("bravo", "Bravo CC", utm="bravo-cricket-club", ca=CA())
        await club("twin1", "Northern CC", utm="northern-cricket-club", ca=CA())     # two clubs share a UTM code
        await club("twin2", "Northern CC", utm="northern-cricket-club", ca=CA())
        await club("noutm", "Delta CC", utm="", ca=CA())                               # no UTM code at all
        await club("junior", "Echo CC", utm="echo-cricket-club", status="junior_only")
        await club("empty", "Foxtrot CC", utm="foxtrot-cricket-club", status="empty")
        await club("cust", "Golf CC", utm="golf-cricket-club", ca=CA(), registered=True)
        shared_ca = CA()
        await club("dup1", "Hotel CC", utm="hotel-cricket-club", ca=shared_ca)         # two snapshots claim one CA id
        await club("dup2", "Hotel CC Two", utm="hotel-two-cricket-club", ca=shared_ca)
        await club("noca", "India CC", utm="india-cricket-club", ca=None)               # older snapshot, no CA id
        await s.commit()

    # ------------------------------------------------------- token to club
    print("token to club")
    async with Session() as s:
        a = await link.club_for_token(s, K["alpha"]["token"])
        j = await link.club_for_token(s, K["junior"]["token"])
        cu = await link.club_for_token(s, K["cust"]["token"])
        by_id = await link.link_for_club(s, K["alpha"]["id"])
        bad = [await link.club_for_token(s, t) for t in ("", None, "short", "../../etc/passwd", "x" * 80, "tk" + "z" * 14)]
    check("a token gives the club with every identifier it is known by",
          a and str(a["club_id"]) == K["alpha"]["id"] and a["name"] == "Alpha CC"
          and a["utm_code"] == "alpha-cricket-club" and a["grassroots_guid"] == K["alpha"]["guid"]
          and a["ca_org_id"] == K["alpha"]["ca"].lower(), str(a))
    check("the club's directory id gives the same record", by_id and by_id["token"] == K["alpha"]["token"])
    check("a token answers for any snapshot status (junior-only still names its club)", j and j["status"] == "junior_only" and j["name"] == "Echo CC")
    check("a registered club's token still names it, and carries its site slug", cu and cu["slug"] == "lnk-customer" and cu["existing_org_id"])
    check("a malformed, empty, unknown or path-shaped token is None and never reaches the database", all(b is None for b in bad), str(bad))

    # ------------------------------------------------------------- UTM to token
    print("UTM code to token")
    async with Session() as s:
        r = {k: await link.token_for_utm(s, K[k]["utm"]) for k in ("alpha", "bravo", "twin1", "junior", "empty", "cust", "noutm")}
        upper = await link.token_for_utm(s, "  ALPHA-Cricket-CLUB ")
        junk = [await link.token_for_utm(s, v) for v in ("", None, "   ", "no-such-code", "alpha' OR '1'='1")]
    check("a UTM code that names one club gives that club's token", r["alpha"] == K["alpha"]["token"] and r["bravo"] == K["bravo"]["token"])
    check("the code is matched without case or stray spaces", upper == K["alpha"]["token"])
    check("a code two clubs share gives nothing (never the wrong club's season)", r["twin1"] is None)
    check("a club with no good snapshot (junior-only, empty) gives nothing", r["junior"] is None and r["empty"] is None)
    check("a registered club gives nothing (no teaser to show a customer)", r["cust"] is None)
    check("an empty, blank, unknown or hostile code gives nothing", all(x is None for x in junk), str(junk))
    check("a club with no UTM code cannot be reached this way, and says so", r["noutm"] is None)

    # --------------------------------------------------- CA id / guid to token
    print("the /trial picker's id to token")
    async with Session() as s:
        by_ca = await link.token_for_ca_org(s, [K["alpha"]["ca"]])
        by_ca_up = await link.token_for_ca_org(s, [K["alpha"]["ca"].upper()])
        by_guid = await link.token_for_ca_org(s, [K["bravo"]["guid"]])
        both = await link.token_for_ca_org(s, [K["alpha"]["ca"], g(), K["alpha"]["guid"]])
        wrongpair = await link.token_for_ca_org(s, [K["alpha"]["ca"], K["bravo"]["guid"]])
        shared = await link.token_for_ca_org(s, [shared_ca])
        cust = await link.token_for_ca_org(s, [K["cust"]["ca"], K["cust"]["guid"]])
        junior = await link.token_for_ca_org(s, [K["junior"]["guid"]])
        none = [await link.token_for_ca_org(s, v) for v in ([], [None, ""], ["nope"], ["' OR 1=1 --"], [g()])]
        many = await link.token_for_ca_org(s, [g() for _ in range(40)] + [K["alpha"]["ca"]])
    check("CA's organisation id gives the club's token", by_ca == K["alpha"]["token"] and by_ca_up == K["alpha"]["token"])
    check("PlayHQ's own id (the directory guid) gives it too, for a club whose CA id is not recorded",
          by_guid == K["bravo"]["token"])
    check("several ids for the same club still give one token", both == K["alpha"]["token"])
    check("when the ids point at two different clubs the CA id wins over the guid", wrongpair == K["alpha"]["token"])
    check("a CA id two snapshots claim gives nothing", shared is None)
    check("a registered club and a junior-only club give nothing", cust is None and junior is None)
    check("no ids, blank ids, an unknown id and a hostile id give nothing", all(x is None for x in none), str(none))
    check("only the first few ids are used, so a pile of them is not a way to probe", many is None)

    # ------------------------------------------------------------------ health
    print("how well the identifiers pin a club down")
    async with Session() as s:
        h = await link.link_health(s)
        un_utm = await link.unlinked_clubs(s, "utm", 50)
        un_ca = await link.unlinked_clubs(s, "ca", 50)
    # ok, unregistered: alpha bravo twin1 twin2 noutm dup1 dup2 noca = 8
    check("the count is the good, unregistered snapshots only", h["total"] == 8, str(h))
    check("UTM: reachable, missing and shared add up to the total", h["utm_ok"] == 5 and h["no_utm"] == 1 and h["shared_utm"] == 2
          and h["utm_ok"] + h["no_utm"] + h["shared_utm"] == h["total"], str(h))
    check("CA id: reachable, missing and shared add up to the total", h["ca_ok"] == 5 and h["no_ca"] == 1 and h["shared_ca"] == 2
          and h["ca_ok"] + h["no_ca"] + h["shared_ca"] == h["total"], str(h))
    names = {r["name"]: r["why"] for r in un_utm}
    check("the clubs the UTM lookup cannot reach are listed with why",
          names.get("Delta CC") == "missing" and names.get("Northern CC") == "shared by 2" and len(un_utm) == 3, str(un_utm))
    check("and so are the ones the CA-id lookup cannot reach", {r["name"] for r in un_ca} == {"India CC", "Hotel CC", "Hotel CC Two"}, str(un_ca))
    async with Session() as s:
        agree = [await link.token_for_utm(s, K[k]["utm"]) for k in ("twin1", "twin2")] + [await link.token_for_utm(s, K["noutm"]["utm"])]
        reach = [await link.token_for_utm(s, K[k]["utm"]) for k in ("alpha", "bravo")]
    check("the report and the lookup agree: what it calls unreachable is None, what it calls reachable is not",
          all(x is None for x in agree) and all(x is not None for x in reach))

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug = 'lnk-customer'"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
