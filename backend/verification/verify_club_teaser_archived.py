"""A club whose BetterCricket club is ARCHIVED is a prospect again.

A test club, an abandoned trial or a club that left can have its directory row
still linked to an archived organisation, and a club whose trial expired without
a subscription is a lapsed prospect. Their admins may come back and start a
trial, so each must be pulled, drawn, found and sent like any other club. Only a
LIVE customer (paying, or on a trial that is still running) is left out.

Runs the shipped crawl target query, progress counts, picture drawer, linkage
lookups, ad pack selection and public page against a real Postgres.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_archived.py
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
TMP = tempfile.mkdtemp(prefix="archived-")
os.environ["TEASER_IMAGE_DIR"] = TMP
os.environ["PUBLIC_BASE_URL"] = "https://site.test"

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

MISSING: list[str] = []
try:
    from starlette.requests import Request
    from app.services import club_teaser as ct, club_teaser_images as ti, club_teaser_link as link
    from app.services import club_teaser_adpack as ap
    from app.services.club_teaser_ddl import STATEMENTS
    from app.routers import marketing, public_teaser as pt
    for name in ("NOT_A_CUSTOMER_SQL", "LIVE_CUSTOMER_SQL", "ARCHIVED_ORG_SQL"):
        if not hasattr(link, name):
            MISSING.append(f"club_teaser_link.{name} is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ct = None
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


def png(w: int, h: int) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


def req(ip="10.7.7.7"):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1)})


async def main() -> None:
    if MISSING:
        check("the archived-club handling is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug LIKE 'arch-%'"))

    live_org, arch_org, arch_org2 = g(), g(), g()
    K: dict[str, dict] = {}
    async with Session() as s:
        for oid, slug, archived in ((live_org, "arch-live", False), (arch_org, "arch-gone", True), (arch_org2, "arch-gone2", True)):
            await s.execute(text("INSERT INTO organisations (id, name, slug, is_active, archived_at) "
                                 "VALUES (CAST(:i AS uuid), :n, :s, true, CASE WHEN :a THEN now() ELSE NULL END)"),
                            {"i": oid, "n": slug, "s": slug, "a": archived})

        async def club(key, name, *, org=None, trial=False, snapshot=False, utm=None):
            cid, tok, ca, guid = g(), "tk" + uuid.uuid4().hex[:14], g(), g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules,
                status, source, existing_org_id, utm_code) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, CAST(:tm AS jsonb),
                'new', 'grassroots_api', CAST(:org AS uuid), :u)"""),
                {"id": cid, "g": guid, "n": name, "tm": json.dumps(["select"] if trial else []), "org": org, "u": utm})
            if snapshot:
                body = {"schema": ct.SCHEMA_VERSION, "club": {"name": name, "ca_org_id": ca}, "season": {"name": "S"},
                        "totals": {"matches": 12}, "batting": [{"name": "A. Bat", "runs": 100}], "bowling": [{"name": "B. Bowl", "wickets": 9}]}
                await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version, image_version,
                    next_pull_at) VALUES (CAST(:id AS uuid), :g, :t, 'ok', CAST(:sn AS jsonb), 1, 1, now() + interval '30 days')"""),
                    {"id": cid, "g": guid, "t": tok, "sn": json.dumps(body)})
                for fmt, f in ti.FORMATS.items():
                    p = ti.image_path(tok, fmt)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(png(f["width"], f["height"]))
            K[key] = {"id": cid, "token": tok, "ca": ca, "guid": guid, "name": name, "utm": utm}

        await club("plain", "Plain Prospect CC")                                           # nobody's customer
        await club("live", "Live Customer CC", org=live_org, snapshot=True, utm="live-customer")
        await club("arch_new", "Archived Never Pulled CC", org=arch_org, trial=True)       # archived, the old test trial still on its row
        await club("arch_ok", "Archived Pulled CC", org=arch_org2, snapshot=True, utm="archived-pulled")
        await club("trialist", "Trialist CC", trial=True)                                  # on a trial now, no org
        await s.commit()

    # --------------------------------------------------------------- the crawl
    print("the crawl's targets")
    async with Session() as s:
        due = {d["name"] for d in await ct.due_clubs(s, 100, type_modes={})}
        due_trial = {d["name"] for d in await ct.due_clubs(s, 100, include_trialists=True, type_modes={})}
        prog = await ct.teaser_progress(s, now=datetime.now(timezone.utc), type_modes={})
    check("a club that was never pulled and has no BetterCricket club is due (the baseline)", "Plain Prospect CC" in due)
    check("a club linked to an ARCHIVED BetterCricket club is due, even though its row still shows an old trial",
          "Archived Never Pulled CC" in due, str(due))
    check("a club linked to a LIVE BetterCricket club is not", "Live Customer CC" not in due)
    check("a club on a trial now (no archived club behind it) is still held back unless asked for",
          "Trialist CC" not in due and "Trialist CC" in due_trial, f"{due} / {due_trial}")
    check("the progress counts include the archived club as a target and leave the live customer out",
          prog["targets"] == 3 and prog["never_pulled"] == 2, str(prog))   # plain, arch_new, arch_ok (pulled)

    # ------------------------------------------------- pictures and lookups
    print("pictures and lookups")
    async with Session() as s:
        await s.execute(text("UPDATE club_teaser_snapshots SET image_version = NULL WHERE token = ANY(:t)"),
                        {"t": [K["live"]["token"], K["arch_ok"]["token"]]})
        await s.commit()
        due_img = {d["name"] for d in await ti.due_clubs(s, 100)}
        prog_img = await ti.images_progress(s)
        t_ca = await link.token_for_ca_org(s, [K["arch_ok"]["ca"]])
        t_guid = await link.token_for_ca_org(s, [K["arch_ok"]["guid"]])
        t_utm = await link.token_for_utm(s, "archived-pulled")
        live_ca = await link.token_for_ca_org(s, [K["live"]["ca"]])
        live_utm = await link.token_for_utm(s, "live-customer")
        health = await link.link_health(s)
        info_arch = await link.club_for_token(s, K["arch_ok"]["token"])
        info_live = await link.club_for_token(s, K["live"]["token"])
        found = await pt.teaser_for_club(req(), [K["arch_ok"]["ca"]], s)
        gone = await pt.teaser_for_club(req("10.7.7.8"), [K["live"]["ca"]], s)
    check("an archived club's picture is due to be drawn; a live customer's is not", due_img == {"Archived Pulled CC"}, str(due_img))
    check("the picture counts agree (1 to draw)", prog_img["pending"] == 1 and prog_img["ready"] == 0, str(prog_img))
    check("an archived club is found by its Cricket Australia id, its directory id and its UTM code",
          t_ca == t_guid == t_utm == K["arch_ok"]["token"], f"{t_ca} {t_guid} {t_utm}")
    check("a live customer is found by none of them", live_ca is None and live_utm is None)
    check("the coverage report counts the archived club and not the live one", health["total"] == 1, str(health))
    check("the token still names each club, and says which is a live customer",
          info_arch["live_customer"] is False and info_arch["slug"] is None
          and info_live["live_customer"] is True and info_live["slug"] == "arch-live", f"{info_arch} {info_live}")
    check("/trial's lookup finds the archived club's page and not the live customer's",
          found == {"found": True, "token": K["arch_ok"]["token"]} and gone == {"found": False}, f"{found} {gone}")

    # -------------------------------------------------------------- the page
    print("the page and the ad pack")
    async with Session() as s:
        page_arch = await pt.get_teaser(K["arch_ok"]["token"], req("10.7.7.9"), s)
        page_live = await pt.get_teaser(K["live"]["token"], req("10.7.7.10"), s)
        await s.execute(text("UPDATE club_teaser_snapshots SET image_version = 1 WHERE token = ANY(:t)"),
                        {"t": [K["live"]["token"], K["arch_ok"]["token"]]})
        await s.commit()
        sel = await ap.select_clubs(s, marketing._filter_kwargs(None, None, None, None, None, None, None), limit=100)
    check("the page of an archived club is an ordinary teaser page (no redirect to a club site)", page_arch["registered"] is None)
    check("the page of a live customer still points to its own site", page_live["registered"] == {"slug": "arch-live"}, str(page_live["registered"]))
    names = {c["name"] for c in sel["clubs"]}
    check("the ad pack includes an archived club (a prospect again) and leaves the live customer out",
          names == {"Archived Pulled CC"}, str(names))

    # ----------------------------------------------- and it flips both ways
    print("and it follows the club's state")
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET archived_at = NULL WHERE id = CAST(:o AS uuid)"), {"o": arch_org2})
        await s.execute(text("UPDATE organisations SET archived_at = now() WHERE id = CAST(:o AS uuid)"), {"o": live_org})
        await s.commit()
        t_back = await link.token_for_ca_org(s, [K["arch_ok"]["ca"]])
        t_now = await link.token_for_ca_org(s, [K["live"]["ca"]])
        due2 = {d["name"] for d in await ct.due_clubs(s, 100, type_modes={})}
    check("un-archiving the club makes it a customer again: no longer found", t_back is None)
    check("archiving a customer makes it a prospect: its page is now found", t_now == K["live"]["token"], str(t_now))
    check("the crawl follows the same flip (the un-archived club leaves the targets, the archived one joins)",
          "Archived Pulled CC" not in due2, str(due2))


    # ------------------------------------------------------- lapsed trials
    print("clubs whose trial has expired and who do not subscribe")
    day = "interval '1 day'"
    ORGS = {}
    async with Session() as s:
        async def org(key, *, rows, stripe=False):
            oid = g()
            await s.execute(text("INSERT INTO organisations (id, name, slug, is_active, stripe_subscription_id) VALUES (CAST(:i AS uuid), :n, :sl, true, :st)"),
                            {"i": oid, "n": key, "sl": f"arch-{key}", "st": "sub_123" if stripe else None})
            for i, (status, ends) in enumerate(rows):
                await s.execute(text(f"INSERT INTO org_module_subscriptions (id, organisation_id, module_key, status, trial_ends_at) "
                                     f"VALUES (gen_random_uuid(), CAST(:o AS uuid), :m, :st, "
                                     f"{'NULL' if ends is None else 'now() + (' + str(ends) + ' * ' + day + ')'})"),
                                {"o": oid, "m": f"mod{i}", "st": status})
            ORGS[key] = oid
            return oid

        await org("lapsed", rows=[("trial", -10), ("trial", -3)])              # every trial ended, nothing paid
        await org("trialling", rows=[("trial", 5)])                            # a trial still running
        await org("open", rows=[("trial", None)])                              # an open-ended trial never lapses
        await org("paying", rows=[("active", None)])                           # a subscriber
        await org("pastdue", rows=[("past_due", None), ("trial", -10)])        # paying but behind, plus an old trial
        await org("mixed", rows=[("trial", -10), ("active", None)])            # one module lapsed, another paid
        await org("stripe", rows=[("trial", -10)], stripe=True)                # a Stripe subscription, trial row expired
        await org("norows", rows=[])                                           # linked club we cannot tell about
        await org("cancelled", rows=[("trial", -10), ("cancelled", None)])     # lapsed, then cancelled: still not a subscriber
        await s.commit()

        async def club2(key, name, org_key, *, snapshot=True):
            cid, tok, ca, guid = g(), "tk" + uuid.uuid4().hex[:14], g(), g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded, not_interested, trial_modules,
                status, source, existing_org_id) VALUES (CAST(:id AS uuid), :g, :n, 'club', false, false, '["select"]'::jsonb,
                'new', 'grassroots_api', CAST(:org AS uuid))"""), {"id": cid, "g": guid, "n": name, "org": ORGS[org_key]})
            if snapshot:
                body = {"schema": ct.SCHEMA_VERSION, "club": {"name": name, "ca_org_id": ca}, "season": {"name": "S"},
                        "totals": {"matches": 12}, "batting": [{"name": "A. Bat", "runs": 100}], "bowling": [{"name": "B. Bowl", "wickets": 9}]}
                await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version,
                    next_pull_at) VALUES (CAST(:id AS uuid), :g, :t, 'ok', CAST(:sn AS jsonb), 1, now() + interval '30 days')"""),
                    {"id": cid, "g": guid, "t": tok, "sn": json.dumps(body)})
            K[key] = {"id": cid, "token": tok, "ca": ca, "guid": guid, "name": name}

        for k in ORGS:
            await club2("l_" + k, f"L {k} CC", k, snapshot=False)
        await s.commit()
    async with Session() as s:
        due3 = {d["name"] for d in await ct.due_clubs(s, 500, type_modes={})}
    want_in = {"L lapsed CC", "L cancelled CC"}
    want_out = {"L trialling CC", "L open CC", "L paying CC", "L pastdue CC", "L mixed CC", "L stripe CC", "L norows CC"}
    check("a club whose every trial has expired and who does not subscribe is pulled",
          "L lapsed CC" in due3, str(sorted(due3)))
    check("so is one that lapsed and then cancelled (it is not a subscriber now)", "L cancelled CC" in due3)
    check("a club on a trial that is still running is not (it is in the product now)", "L trialling CC" not in due3)
    check("an open-ended trial never counts as lapsed", "L open CC" not in due3)
    check("a paying club is not, nor one that is behind on payment (past due still pays)",
          not ({"L paying CC", "L pastdue CC"} & due3))
    check("a club with one lapsed module and another paid is a subscriber, so it is not", "L mixed CC" not in due3)
    check("a club with a Stripe subscription is not, even with an expired trial row", "L stripe CC" not in due3)
    check("a linked club we cannot tell about (no subscription rows) is left alone", "L norows CC" not in due3)
    check("the old trial still recorded on the directory row does not hold a lapsed club back (all of them show a trial)",
          want_in <= due3 and not (want_out & due3))

    # snapshots for pages: lapsed / trialling / paying
    async with Session() as s:
        for key in ("l_lapsed", "l_trialling", "l_paying", "l_stripe"):
            body = {"schema": ct.SCHEMA_VERSION, "club": {"name": K[key]["name"], "ca_org_id": K[key]["ca"]}, "season": {"name": "S"},
                    "totals": {"matches": 12}, "batting": [{"name": "A. Bat", "runs": 100}], "bowling": [{"name": "B. Bowl", "wickets": 9}]}
            await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, snapshot, version,
                next_pull_at) VALUES (CAST(:id AS uuid), :g, :t, 'ok', CAST(:sn AS jsonb), 1, now() + interval '30 days')"""),
                {"id": K[key]["id"], "g": K[key]["guid"], "t": K[key]["token"], "sn": json.dumps(body)})
        await s.commit()
        f_lapsed = await pt.teaser_for_club(req("10.8.8.1"), [K["l_lapsed"]["ca"]], s)
        f_trial = await pt.teaser_for_club(req("10.8.8.2"), [K["l_trialling"]["ca"]], s)
        f_paying = await pt.teaser_for_club(req("10.8.8.3"), [K["l_paying"]["ca"]], s)
        f_stripe = await pt.teaser_for_club(req("10.8.8.4"), [K["l_stripe"]["ca"]], s)
        p_lapsed = await pt.get_teaser(K["l_lapsed"]["token"], req("10.8.8.5"), s)
        p_paying = await pt.get_teaser(K["l_paying"]["token"], req("10.8.8.6"), s)
        p_trial = await pt.get_teaser(K["l_trialling"]["token"], req("10.8.8.7"), s)
        due_img3 = {d["name"] for d in await ti.due_clubs(s, 500)}
    check("/trial's lookup finds a lapsed club's page, and not a trialling, paying or Stripe-subscribed club's",
          f_lapsed == {"found": True, "token": K["l_lapsed"]["token"]} and f_trial == f_paying == f_stripe == {"found": False},
          f"{f_lapsed} {f_trial} {f_paying} {f_stripe}")
    check("a lapsed club's page is a teaser page, not a redirect to its (paused) club site", p_lapsed["registered"] is None)
    check("a paying club's and a still-trialling club's page still point to their own site",
          p_paying["registered"] == {"slug": "arch-paying"} and p_trial["registered"] == {"slug": "arch-trialling"},
          f"{p_paying['registered']} {p_trial['registered']}")
    check("the lapsed club's pictures are due to be drawn; the others' are not", "L lapsed CC" in due_img3
          and not ({"L trialling CC", "L paying CC", "L stripe CC"} & due_img3), str(due_img3))


    # ------------------------------------- re-crawling just these clubs
    print("re-crawling only the archived and lapsed clubs")
    async with Session() as s:
        # put the two clubs the flip test changed back as they started
        await s.execute(text("UPDATE organisations SET archived_at = now() WHERE id = CAST(:o AS uuid)"), {"o": arch_org2})
        await s.execute(text("UPDATE organisations SET archived_at = NULL WHERE id = CAST(:o AS uuid)"), {"o": live_org})
        await s.commit()
        grp = await ct.due_clubs(s, 500, returning_only=True, force=True, type_modes={})
        due_only = await ct.due_clubs(s, 500, returning_only=True, type_modes={})
        everyone = {d["name"] for d in await ct.due_clubs(s, 500, force=True, type_modes={})}
    why = {d["name"]: d["why"] for d in grp}
    check("the group is exactly the archived clubs and the lapsed-trial clubs, labelled",
          why == {"Archived Never Pulled CC": "archived", "Archived Pulled CC": "archived",
                  "L lapsed CC": "lapsed", "L cancelled CC": "lapsed"}, str(why))
    check("a club never linked to BetterCricket, a live customer, a trialling club and a paying club are not in it",
          not ({"Plain Prospect CC", "Live Customer CC", "Trialist CC", "L trialling CC", "L paying CC", "L stripe CC", "L norows CC"} & set(why)))
    check("and the force option on its own does reach other clubs (so the group filter is what narrows it)",
          {"Plain Prospect CC", "Archived Pulled CC"} <= everyone and "Live Customer CC" not in everyone, str(sorted(everyone)))
    check("due-only keeps just the group's clubs that are due now (never pulled), not the ones with a current snapshot",
          {d["name"] for d in due_only} == {"Archived Never Pulled CC", "L cancelled CC"}, str({d["name"] for d in due_only}))
    check("never-pulled clubs come first", [d["name"] for d in grp][:2] and set(d["name"] for d in grp[:2]) == {"Archived Never Pulled CC", "L cancelled CC"},
          str([d["name"] for d in grp]))

    class StubAPI:
        pulls: list = []
        calls = 0

        def __init__(self, pacer=None):
            pass

        async def seasons(self, org):
            StubAPI.pulls.append(org)
            StubAPI.calls += 1
            return [{"id": "S1", "name": "Summer 2025/26", "startDate": "2025-10-01"}]

        async def batting(self, org, sid, grades=None):
            return [{"id": f"p{i}", "name": f"Batter {i}", "statistics": {"battingAggregate": 400 - i * 10, "battingInnings": 12,
                     "battingNotOuts": 1, "battingHighScore": 80, "batting50s": 2, "batting100s": 0}} for i in range(5)]

        async def bowling(self, org, sid, grades=None):
            return [{"id": f"w{i}", "name": f"Bowler {i}", "statistics": {"bowlingWickets": 20 - i, "bowlingRuns": 300,
                     "bowlingBalls": 400, "bowlingBestInnings": "5/20"}} for i in range(5)]

        async def fielding(self, org, sid, grades=None):
            return []

        async def teams(self, org, sid):
            self._org = org
            return [{"id": "T", "grades": [{"id": "G1", "name": "A Grade"}]}]

        async def ladder(self, gid):
            return {"ladders": [{"name": "Overall", "pools": [{"teams": [
                {"rank": 2, "displayName": "Us", "owningOrganisation": {"id": self._org},
                 "ladderData": [{"id": "played", "val": 14}, {"id": "won", "val": 9}, {"id": "lost", "val": 5}, {"id": "competitionPoints", "val": 30}]},
                {"rank": 1, "displayName": "T1", "owningOrganisation": {"id": "x"}, "ladderData": []}]}]}]}

    async with Session() as s:
        before = {r[0]: r[1] for r in (await s.execute(text(
            "SELECT mc.name, t.pulled_at FROM marketing_clubs mc LEFT JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id"))).all()}
    out = await ct.run_batch(100, session_maker=Session, api_factory=StubAPI, type_modes={}, returning_only=True, force=True)
    async with Session() as s:
        after = {r[0]: r[1] for r in (await s.execute(text(
            "SELECT mc.name, t.pulled_at FROM marketing_clubs mc LEFT JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id"))).all()}
    touched = {n for n in after if after[n] != before.get(n)}
    check("a forced run re-pulls every club in the group, including ones with a current snapshot, and no other club",
          out["due"] == 4 and touched == {"Archived Never Pulled CC", "Archived Pulled CC", "L lapsed CC", "L cancelled CC"}, f"{out['due']} {sorted(touched)}")
    check("the run reports what it found per status and its calls", out["ok"] + out["empty"] + out["junior_only"] + out["error"] == 4 and out["calls"] > 0, str(out))
    check("the clubs it labelled carry their reason through to the run's detail",
          {d["name"]: d["why"] for d in out["detail"]}["L lapsed CC"] == "lapsed")

    # the script itself, with the live Cricket Australia client swapped for the stub
    import contextlib
    from app.scripts import pull_returning_club_teasers as script
    from app.services import club_teaser as ct_mod
    real = ct_mod.LiveAPI
    ct_mod.LiveAPI = StubAPI
    async with engine.begin() as c:
        await c.execute(text("CREATE TABLE IF NOT EXISTS marketing_crawl_control (id SMALLINT PRIMARY KEY, paused BOOLEAN NOT NULL DEFAULT FALSE, "
                             "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))
        await c.execute(text("INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) ON CONFLICT (id) DO UPDATE SET paused = FALSE"))
    try:
        async def run(argv):
            buf = io.StringIO()
            StubAPI.pulls.clear()
            with contextlib.redirect_stdout(buf):
                rc = await script.main(argv)
            return rc, buf.getvalue()
        rc, dry = await run(["--no-type-filter"])
        check("the script's dry run says how many are in the group and makes no call at all",
              rc == 0 and "clubs in the group: 4 (2 archived, 2 with an expired trial" in dry and StubAPI.pulls == [] and "Dry run" in dry, dry[:400])
        check("it lists the clubs with their reason", "Archived Never Pulled CC" in dry and "archived" in dry and "lapsed" in dry)
        rc, applied = await run(["--no-type-filter", "--apply", "--rate", "10", "--pause", "0"])
        check("--apply pulls the group and says so", rc == 0 and len(set(StubAPI.pulls)) == 4 and "paced at 10 calls/s" in applied, applied[:500])
        rc, sample = await run(["--no-type-filter", "--apply", "--rate", "10", "--pause", "0", "--limit", "1"])
        check("--limit takes just the first club (never-pulled clubs first)", len(StubAPI.pulls) == 1, str(StubAPI.pulls))
        async with engine.begin() as c:
            await c.execute(text("UPDATE marketing_crawl_control SET paused = TRUE WHERE id = 1"))
        rc, stopped = await run(["--no-type-filter", "--apply", "--rate", "10", "--pause", "0"])
        check("the operator's Stop switch halts it before any club is pulled", StubAPI.pulls == [] and "Stopped by the operator" in stopped, stopped[-300:])
        async with engine.begin() as c:
            await c.execute(text("UPDATE marketing_crawl_control SET paused = FALSE WHERE id = 1"))
        try:
            await script.main(["--rate", "50"])
            bad_rate = False
        except SystemExit:
            bad_rate = True
        check("a rate above the allowed maximum is refused", bad_rate)
    finally:
        ct_mod.LiveAPI = real

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM org_module_subscriptions WHERE organisation_id IN (SELECT id FROM organisations WHERE slug LIKE 'arch-%')"))
        await c.execute(text("DELETE FROM club_teaser_snapshots"))
        await c.execute(text("DELETE FROM marketing_clubs"))
        await c.execute(text("DELETE FROM organisations WHERE slug LIKE 'arch-%'"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
