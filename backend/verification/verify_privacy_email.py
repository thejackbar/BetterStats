"""Verification that a person who asked to be removed is never emailed (migration 316).

Runs the SHIPPED `services/player_privacy.py`, `services/privacy_email.py`,
`services/email_suppression.py`, `services/comms_segments.sendable_where`,
`services/comms_contacts.upsert_contact` and `services/email_service.get_email_provider`
against a real Postgres.

The club: TRENT (removed) with an address on his player record, a different one
on his fee record, a sign-in email on a claimed account and a BetterComms contact
for each; TOM, a relative with the same surname, PAT, and a committee address.

Every "is blocked" check is paired with a check that the same path lets a normal
recipient through, so a gate that blocks everything cannot pass (rule 21).

CONTROL MODE. The same suite runs against the commit BEFORE this change, where
`services/privacy_email.py` does not exist. "Removed" is then reproduced the only
way the old code allowed (`is_public = false`), and the missing pieces read as
failed checks instead of a crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/email_test?host=/var/run/postgresql \
      python verification/verify_privacy_email.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, CommsContact, FeeMember, Organisation, Player, User
import app.models.scout  # noqa: F401  (registers scouted_players on Base)
from app.services import comms_segments, email_suppression
from app.services.email_service import EmailMessage, EmailProvider, SendResult, get_email_provider

HAVE = importlib.util.find_spec("app.services.privacy_email") is not None
if HAVE:
    from app.services import player_privacy, privacy_email
    from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL
    from app.services.email_service import PrivacyGuardedProvider
    from app.services.comms_contacts import upsert_contact
else:
    player_privacy = privacy_email = PrivacyGuardedProvider = None
    PRIVACY_DDL = []
    from app.services.comms_contacts import upsert_contact

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
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
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


ORG = uuid.uuid4()
TRENT, TOM, PAT, ACCT = (uuid.uuid4() for _ in range(4))
FM_TRENT, FM_TOM = uuid.uuid4(), uuid.uuid4()
T_PLAYER, T_FEE, T_ACCT = "trent@club.test", "trent.fee@club.test", "trent.acct@club.test"
TOM_MAIL, PAT_MAIL, COMMITTEE = "tom@club.test", "pat@club.test", "committee@club.test"
ALL_TRENT = {T_PLAYER, T_FEE, T_ACCT}


class Recorder(EmailProvider):
    name = "recorder"

    def __init__(self):
        self.sent: list[str] = []

    async def send(self, msg: EmailMessage) -> SendResult:
        self.sent.append(msg.to_email.lower())
        return SendResult(ok=True, message_id="m")


def msg(to: str) -> EmailMessage:
    return EmailMessage(to_email=to, subject="Hello", html="<p>Hi</p>")


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Applecross", is_active=True))
        s.add(User(id=ACCT, username="trent", email=T_ACCT))
        await s.flush()
        for pid, nm, em, uid_ in ((TRENT, "Trent Steenholdt", T_PLAYER, ACCT), (TOM, "Tom Steenholdt", TOM_MAIL, None),
                                  (PAT, "Pat Plain", PAT_MAIL, None)):
            s.add(Player(id=pid, name=nm, organisation_id=ORG, grassroots_id=str(pid), email=em, user_id=uid_))
        await s.flush()
        s.add(FeeMember(id=FM_TRENT, organisation_id=ORG, player_id=TRENT, full_name="Trent Steenholdt", email=T_FEE))
        s.add(FeeMember(id=FM_TOM, organisation_id=ORG, player_id=TOM, full_name="Tom Steenholdt", email=TOM_MAIL))
        await s.flush()
        for em, nm, pid, mid in ((T_PLAYER, "Trent", TRENT, None), (T_FEE, "Trent", None, FM_TRENT),
                                 (T_ACCT, "Trent", None, None), (TOM_MAIL, "Tom", TOM, None),
                                 (PAT_MAIL, "Pat", PAT, None), (COMMITTEE, "Committee", None, None)):
            s.add(CommsContact(organisation_id=ORG, email=em, name=nm, source="player", player_id=pid, member_id=mid))
        await s.commit()
    if HAVE:
        privacy_email.forget()


async def audience() -> set[str]:
    async with Session() as s:
        rows = (await s.execute(select(CommsContact.email).where(*comms_segments.sendable_where(ORG)))).scalars().all()
    return {r.lower() for r in rows}


async def remove_trent() -> dict | None:
    async with Session() as s:
        pl = await s.get(Player, TRENT)
        if HAVE:
            out = await player_privacy.hide_at_request(s, pl, by="Jack", reason="asked by email")
            await s.commit()
            return out
        pl.is_public = False       # the control: all the old code could do
        await s.commit()
        return None


async def main() -> int:
    await seed()
    print("before: everybody is reachable")
    before = await audience()
    check("every contact is in the audience before", {T_PLAYER, T_FEE, T_ACCT, TOM_MAIL, PAT_MAIL, COMMITTEE} <= before, str(before))
    rec = Recorder()
    guarded = PrivacyGuardedProvider(rec) if HAVE else rec
    for a in sorted(ALL_TRENT):
        await guarded.send(msg(a))
    check("before removal his addresses are emailed (the gate is not blanket)", set(rec.sent) == ALL_TRENT, str(rec.sent))

    print("asking to be removed")
    out = await remove_trent()
    if HAVE:
        check("all three of his addresses were found", set(out["emails"]["addresses"]) == ALL_TRENT, str(out["emails"]))
    aud = await audience()
    check("his player address is out of the audience", T_PLAYER not in aud, str(aud))
    check("his FEE-RECORD address is out of the audience", T_FEE not in aud)
    check("his sign-in address is out of the audience", T_ACCT not in aud)
    check("Tom (a relative), Pat and the committee are still in it", {TOM_MAIL, PAT_MAIL, COMMITTEE} <= aud, str(aud))

    async with Session() as s:
        for cat in ("campaign", "transactional", "fees"):
            ok, why = await email_suppression.deliverable(s, email=T_PLAYER, organisation_id=ORG, category=cat)
            check(f"the send gate refuses him for category {cat!r}", not ok, f"{ok} {why}")
        ok, _ = await email_suppression.deliverable(s, email=TOM_MAIL, organisation_id=ORG, category="campaign")
        check("...and still lets Tom through", ok)

    print("the provider guard (every module sends through get_email_provider)")
    rec2 = Recorder()
    gp = PrivacyGuardedProvider(rec2) if HAVE else rec2
    results = {a: await gp.send(msg(a)) for a in sorted(ALL_TRENT) + [TOM_MAIL, PAT_MAIL, COMMITTEE]}
    check("every one of his addresses is refused and nothing is sent to him",
          all(not results[a].ok for a in ALL_TRENT) and not (set(rec2.sent) & ALL_TRENT), str(rec2.sent))
    check("the refusal says so (a failure a person can read, not a silent success)",
          all("removed" in (results[a].error or "") for a in ALL_TRENT) if HAVE else False)
    check("Tom, Pat and the committee are sent to", {TOM_MAIL, PAT_MAIL, COMMITTEE} <= set(rec2.sent), str(rec2.sent))
    real = get_email_provider()
    r = await real.send(msg(T_PLAYER))
    check("the REAL get_email_provider() refuses him", not r.ok, str(r))
    r = await real.send(msg(PAT_MAIL))
    check("...and sends to Pat (console provider)", r.ok, str(r))

    print("an address or contact added AFTER the removal")
    async with Session() as s:
        await s.execute(text("UPDATE players SET email = 'trent.new@club.test' WHERE id = :i"), {"i": TRENT})
        await s.commit()
    if HAVE:
        privacy_email.forget()
    r = await real.send(msg("trent.new@club.test"))
    check("a NEW address on his record is refused with nobody re-running anything", not r.ok, str(r))
    async with Session() as s:
        outcome = await upsert_contact(s, ORG, "trent.new@club.test", "Trent", "player", player_id=TRENT)
        await s.commit()
    async with Session() as s:
        c = (await s.execute(select(CommsContact).where(CommsContact.email == "trent.new@club.test"))).scalar_one()
    check("a contact re-created for him from the Directory is born excluded", c.excluded is True)
    async with Session() as s:
        s.add(CommsContact(organisation_id=ORG, email="odd@elsewhere.test", name="Trent", source="manual", player_id=TRENT))
        await s.commit()
    if HAVE:
        privacy_email.forget()
    check("a contact LINKED to him under any address is out of the audience", "odd@elsewhere.test" not in await audience())
    r = await real.send(msg("odd@elsewhere.test"))
    check("...and its address is refused by the guard", not r.ok, str(r))

    print("the club cannot lift it")
    async with Session() as s:
        n = await email_suppression.remove_suppression(s, T_PLAYER)
        await s.commit()
    still = await audience()
    check("un-suppressing his address removes nothing", n == 0 and T_PLAYER not in still, str(n))
    async with Session() as s:
        await email_suppression.add_suppression(s, "bounced@club.test", "hard_bounce", source="ses")
        await s.commit()
    async with Session() as s:
        n = await email_suppression.remove_suppression(s, "bounced@club.test")
        await s.commit()
    check("control: an ordinary bounce is still removable", n == 1, str(n))

    print("restore")
    if HAVE:
        async with Session() as s:
            pl = await s.get(Player, TRENT)
            await player_privacy.restore_public(s, pl, by="Jack")
            await s.execute(text("UPDATE players SET email = :e WHERE id = :i"), {"e": T_PLAYER, "i": TRENT})
            await s.commit()
        privacy_email.forget()
        async with Session() as s:
            left = (await s.execute(text("SELECT COUNT(*) FROM email_suppressions WHERE source='privacy_request'"))).scalar()
        check("restore lifts the suppressions this removal recorded", left == 0, str(left))
        r = await real.send(msg(T_PLAYER))
        check("...and his address can be emailed again", r.ok, str(r))
        async with Session() as s:
            ex = (await s.execute(select(CommsContact.excluded).where(CommsContact.email == T_PLAYER))).scalar()
        check("...but his contact STAYS excluded: restoring never re-emails by itself", ex is True)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
