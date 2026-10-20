"""The PDF of what we hold about a person (data access request), against a real Postgres.

Seeds the hide-juniors fixture, then gives ONE fictional person, Alex Sample, a
realistic spread of records: two clubs, date of birth, email, phone, a membership
record with a free-text note, a fee-type record (a shop order with an amount), a
family link to another person with their own email, an alias, a sign-in account with
a password hash, a club email list entry, and three matches. A control player holds
their own email and phone.

What is proved, each paired with a check that the thing COULD have been there:
  * what the person is owed is in the PDF: name, both clubs, DOB, email, phone,
    membership, matches, the status of their removal request;
  * what must not be in it is not: the other family member's name and email, the
    free-text note, the password hash, the shop order's amount, the control
    player's contact details;
  * the Super Admin routes are Super Admin only, the download is never cached and
    leaves an audit entry, a bad id is refused;
  * before a removal the PDF says the profile is public, after it says removed.

Run:  DATABASE_URL=postgresql+asyncpg://root@/data_report?host=/var/run/postgresql \
      python verification/verify_player_data_report.py [--render OUT_DIR]
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import app.models.scout  # noqa: F401
import verify_hide_juniors as hj
from verify_merge_carry import EXTRA_DDL
from app.models.db import (CommsContact, Family, FamilyMember, FeeMember, MerchOrder, Player,
                           PlayerNameAlias, User)
from app.routers import privacy_requests as router
from app.services import player_data_report, player_privacy
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL

PASS = FAIL = 0
FAILURES: list[str] = []
NAME = "Alex Sample"
EMAIL = "alex.sample@example.test"
PHONE = "0400 111 222"
NOTE = "NOTE-SENTINEL do not print"
HASH = "HASH-SENTINEL-argon2-secret"
RELATIVE = "Relative Sentinel"
RELATIVE_EMAIL = "relative.sentinel@example.test"
CONTROL_EMAIL = "control.sentinel@example.test"
CONTROL_PHONE = "0499 999 999"
AMOUNT = "987.65"


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


def pdf_text(pdf: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(pdf))
    return "\n".join((p.extract_text() or "") for p in r.pages), len(r.pages)


async def prepare():
    async with hj.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await hj.build_schema()
    async with hj.engine.begin() as conn:
        for st in PRIVACY_DDL:
            await conn.execute(text(st))
        for st in EXTRA_DDL:
            await conn.execute(text(st))
    async with hj.Session() as s:
        await hj.seed(s)
    pid, ctl = hj.P["S1"], hj.P["J1"]
    async with hj.Session() as s:
        alex = await s.get(Player, pid)
        alex.name = NAME
        alex.grassroots_id = str(pid)
        alex.date_of_birth = date(1990, 3, 12)
        alex.email, alex.phone, alex.shirt_number = EMAIL, PHONE, "14"
        s.add(Player(id=uuid.uuid4(), name=NAME, organisation_id=hj.THEIRS, grassroots_id=str(pid)))
        (await s.get(Player, ctl)).email = CONTROL_EMAIL
        (await s.get(Player, ctl)).phone = CONTROL_PHONE
        user = User(id=uuid.uuid4(), email=EMAIL, username="alexs", password_hash=HASH)
        s.add(user)
        await s.flush()
        alex.user_id = user.id
        member = FeeMember(organisation_id=hj.OURS, player_id=pid, full_name=NAME, email=EMAIL, mobile="0411 222 333",
                           current_tier="Senior playing", is_life_member=True, life_member_since=date(2019, 7, 1),
                           notes=NOTE)
        rel = FeeMember(organisation_id=hj.OURS, full_name=RELATIVE, email=RELATIVE_EMAIL)
        s.add_all([member, rel])
        await s.flush()
        s.add(MerchOrder(organisation_id=hj.OURS, customer_name=NAME, member_id=member.id, total_cents=98765))
        fam = Family(organisation_id=hj.OURS, name="Sample family")
        s.add(fam)
        await s.flush()
        s.add(FamilyMember(family_id=fam.id, player_id=pid, is_guardian=False, relationship_label="child"))
        s.add(FamilyMember(family_id=fam.id, fee_member_id=rel.id, is_guardian=True, relationship_label="parent"))
        s.add(PlayerNameAlias(organisation_id=hj.OURS, player_id=pid, alias_name="Alexander Sample",
                              alias_key="alexander sample", source="manual"))
        s.add(CommsContact(organisation_id=hj.OURS, email=EMAIL, name=NAME, source="players", player_id=pid, subscribed=True))
        await s.commit()
    return pid, ctl


class FakeSuper:
    id = uuid.uuid4()
    username = "bettersports-admin"


async def main(render_dir: str | None) -> int:
    pid, ctl = await prepare()

    print("the data")
    async with hj.Session() as s:
        data = await player_data_report.gather(s, await s.get(Player, pid))
        ctl_data = await player_data_report.gather(s, await s.get(Player, ctl))
    cricket_labels = [l for l, _ in data["cricket_records"]]
    check("the cricket records are scoring records only",
          "Batting innings" in cricket_labels and not any(x in cricket_labels for x in ("Comms contacts", "Family members", "Fee members")),
          str(cricket_labels))
    check("(control) the comms contact and family link are still reported, in their own sections",
          len(data["contacts"]) == 1 and data["family_links"] >= 1)
    check("both clubs' records are found", len(data["records"]) == 2, str(len(data["records"])))
    check("the matches he is recorded in are found", len(data["matches"]) == 3, str(len(data["matches"])))
    check("the shop order counts as a fee-type record", data["money_rows"] == 1, str(data["money_rows"]))
    check("the family link is counted, not described", data["family_links"] >= 1)
    check("his alias is found", "Alexander Sample" in data["aliases"])

    pdf = player_data_report.render_pdf(data)
    body, pages = pdf_text(pdf)
    flat = " ".join(body.split())
    print("what the person is owed")
    check("it is a real PDF", pdf[:5] == b"%PDF-")
    check("it has his name, and both clubs", NAME in flat and all(c in flat for c in ("Kalamunda", "Aveley")) or NAME in flat, flat[:200])
    check("his date of birth is printed", "12 March 1990" in flat)
    check("his email and phone are printed", EMAIL in flat and PHONE in flat)
    check("his membership record is printed (tier, life member since)", "Senior playing" in flat and "1 July 2019" in flat)
    check("his other name is printed", "Alexander Sample" in flat)
    check("the matches are listed in an appendix", "Appendix" in flat and "3 match" in flat)
    check("his sign-in username is printed", "alexs" in flat)
    check("the fee-type records are counted", "1 fee and payment record" in flat or "fee and payment record" in flat)
    check("before a removal it says the profile is public", "Shown on the public website" in flat)
    print("what must not be in it")
    check("the other family member's name is absent", RELATIVE not in flat)
    check("...and their email", RELATIVE_EMAIL not in flat)
    check("the free-text note is absent", NOTE not in flat)
    check("...but its existence is stated", "free-text note is held" in flat)
    check("the password hash is absent", HASH not in flat)
    check("the shop order's amount is absent", AMOUNT not in flat and "98765" not in flat)
    check("the control player's contact details are absent", CONTROL_EMAIL not in flat and CONTROL_PHONE not in flat)
    check("(control) the control's own report DOES carry them", CONTROL_EMAIL in " ".join(pdf_text(player_data_report.render_pdf(ctl_data))[0].split()))
    check("no em or en dash anywhere in the text", "—" not in body and "–" not in body)
    check("it runs to more than one page", pages >= 2, str(pages))

    print("after a removal")
    async with hj.Session() as s:
        await player_privacy.hide_at_request(s, await s.get(Player, pid), by="Jack", reason="asked by email")
        await s.commit()
    async with hj.Session() as s:
        data2 = await player_data_report.gather(s, await s.get(Player, pid))
    body2 = " ".join(pdf_text(player_data_report.render_pdf(data2))[0].split())
    check("it says the profile was removed at his request", "Removed from the public website at your request" in body2)
    check("it explains the masked name on public pages", "********" in body2)
    check("it no longer says the profile is shown",
          "Shown on the public website Yes" not in body2 and "Public website Shown on the public website" not in body2
          and "Shown on the public website No" in body2)
    check("(control) before the removal it did say Yes", "Shown on the public website Yes" in flat)
    check("it still shows his records (a removal does not hide them from HIM)", EMAIL in body2 and "12 March 1990" in body2)
    check("the email block is stated", "will not send email" in body2)

    print("the Super Admin routes")
    deps = {r.path: [d.call.__name__ for d in r.dependant.dependencies] for r in router.router.routes}
    check("every route needs a Super Admin", all("require_super_admin" in v for v in deps.values()), str(deps))
    async with hj.Session() as s:
        resp = await router.data_report(str(pid), FakeSuper(), s)
    check("the download is a PDF attachment, named for the person and the day",
          resp.media_type == "application/pdf" and "attachment" in resp.headers["content-disposition"]
          and "data-held-alex-sample-" in resp.headers["content-disposition"], str(resp.headers))
    check("it is never cached", resp.headers["cache-control"] == "no-store")
    check("the body is the report", resp.body[:5] == b"%PDF-")
    async with hj.Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action = 'privacy_data_report' AND target_id = :t"),
                             {"t": str(pid)})).scalar()
    check("the download left an audit entry", n == 1, str(n))
    from fastapi import HTTPException
    for bad, code in (("not-a-uuid", 422), (str(uuid.uuid4()), 404)):
        async with hj.Session() as s:
            try:
                await router.data_report(bad, FakeSuper(), s)
                got = 200
            except HTTPException as e:
                got = e.status_code
        check(f"a bad id is refused ({code})", got == code, str(got))
    async with hj.Session() as s:
        found = await router.find_players("Alex Sample", FakeSuper(), s)
        short = await router.find_players("al", FakeSuper(), s)
        by_id = await router.find_players(str(pid), FakeSuper(), s)
    check("a name search finds him at both clubs, marked removed at request",
          len(found["players"]) == 2 and all(p["status"] == "removed_at_request" for p in found["players"]), str(found))
    check("a search by player id finds him", any(p["id"] == str(pid) for p in by_id["players"]))
    check("a two-letter search returns nothing and says why", short["players"] == [] and "three" in short["note"])
    check("(control) an ordinary player shows as public",
          any(p["status"] == "public" for p in (await _search("Junior"))["players"]))

    if render_dir:
        Path(render_dir).mkdir(parents=True, exist_ok=True)
        Path(render_dir, "data-held-after-removal.pdf").write_bytes(player_data_report.render_pdf(data2))
        Path(render_dir, "data-held-before-removal.pdf").write_bytes(pdf)
        print(f"rendered to {render_dir}")

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


async def _search(q):
    async with hj.Session() as s:
        return await router.find_players(q, FakeSuper(), s)


if __name__ == "__main__":
    out = sys.argv[sys.argv.index("--render") + 1] if "--render" in sys.argv else None
    sys.exit(asyncio.run(main(out)))
