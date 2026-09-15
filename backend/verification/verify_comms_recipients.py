"""A campaign's recipient drill-down carries each contact's club and when they
were last emailed, and offers a per-club view.

Reported on BetterComms → Emails: the recipient list under a sent campaign
(Unsubscribed/spam, Bounced, All recipients) named a person and their event but
said nothing about which club they belong to or how recently they were emailed.
The Super Admin outreach screen also wanted a searchable Clubs filter so a send
could be read one club at a time. Both are served by the ONE shipped
`campaign_recipients` body (used by club-admin and outreach alike via
`get_current_club`): a `club` (blank for a club's own member) and a
cross-campaign `last_emailed_at` on every recipient.

Runs the SHIPPED route body against a real Postgres.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/verify_recipients \
        python -m verification.verify_comms_recipients
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/verify_recipients",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, CommsCampaign, CommsContact, CommsRecipient, EmailEvent,
    MarketingClub, Organisation, User,
)
from app.routers.comms import campaign_recipients  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def instant(s):
    """Parse an isoformat back to an aware instant, so a timestamptz round-trip
    (which may come back UTC or in the session tz) is compared as a moment, not
    as a string. Returns None for a None/absent value so a control run — where
    the key is missing entirely — reports rather than crashing."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


async def recipients(db, staff, club, campaign_id, only=None):
    return await campaign_recipients(
        campaign_id=str(campaign_id), only=only, _=staff, club=club, db=db)


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket",
                                slug="bettercricket", is_marketing_outreach=True)
        own = Organisation(id=uuid.uuid4(), name="Applecross CC", slug="applecross-cc")
        db.add_all([outreach, own])
        await db.flush()
        staff = User(id=uuid.uuid4(), username="staff", email="staff@example.com")
        db.add(staff)
        await db.flush()

        # Two prospect clubs.
        alpha = MarketingClub(id=uuid.uuid4(), name="Alpha CC",
                              grassroots_guid="g-alpha", utm_code="alpha", state="WA")
        beta = MarketingClub(id=uuid.uuid4(), name="Beta CC",
                             grassroots_guid="g-beta", utm_code="beta", state="WA")
        db.add_all([alpha, beta])
        await db.flush()

        def contact(email, mc=None, org=None, source="directory", merge_vars=None):
            cc = CommsContact(id=uuid.uuid4(), organisation_id=(org or outreach).id,
                              email=email, source=source,
                              marketing_club_id=(mc.id if mc else None),
                              merge_vars=merge_vars or {})
            db.add(cc)
            return cc

        c_alice = contact("alice@example.com", alpha)
        c_bob = contact("bob@example.com", beta)
        # A contact whose merge_vars override names the club, over the linked one.
        c_carol = contact("carol@example.com", alpha,
                          merge_vars={"club": "Carol's Own Club"})
        # A directory contact with no club at all.
        c_dave = contact("dave@example.com", None)
        await db.flush()

        T1 = datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)   # older send
        T2 = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)   # newer send

        def campaign(name, org=None):
            c = CommsCampaign(id=uuid.uuid4(), organisation_id=(org or outreach).id,
                              name=name, subject=name, status="sent")
            db.add(c)
            return c

        c1 = campaign("January outreach")
        c2 = campaign("March outreach")
        await db.flush()

        def recip(camp, cc, email, when, status="sent", org=None):
            db.add(CommsRecipient(id=uuid.uuid4(), campaign_id=camp.id,
                                  organisation_id=(org or outreach).id,
                                  contact_id=(cc.id if cc else None), email=email,
                                  name=None, status=status, sent_at=when))

        # January (C1): everyone emailed at T1.
        recip(c1, c_alice, "alice@example.com", T1)
        recip(c1, c_bob, "bob@example.com", T1)
        recip(c1, c_carol, "carol@example.com", T1)
        recip(c1, c_dave, "dave@example.com", T1)
        # March (C2): alice re-emailed at T2 (later). bob NOT in this campaign.
        recip(c2, c_alice, "alice@example.com", T2)
        await db.flush()

        # An EmailEvent whose recipient row was cleaned up (no CommsRecipient in
        # THIS campaign for that address) — surfaced as an events-only row.
        db.add(EmailEvent(id=uuid.uuid4(), organisation_id=outreach.id,
                          campaign_id=c1.id, email="ghost@example.com",
                          event_type="bounce", event_subtype="Permanent",
                          created_at=T1))
        # A bounce for bob on C1, so the drill-down has a problem row.
        db.add(EmailEvent(id=uuid.uuid4(), organisation_id=outreach.id,
                          campaign_id=c1.id, recipient_id=None,
                          contact_id=c_bob.id, email="bob@example.com",
                          event_type="bounce", event_subtype="Permanent",
                          created_at=T1))
        await db.commit()

        print("\n── Club name on each recipient (outreach) ─────────────────────")
        res = await recipients(db, staff, outreach, c1.id)
        by_email = {r["email"]: r for r in res["recipients"]}
        check("alice's row names her linked club",
              by_email.get("alice@example.com", {}).get("club") == "Alpha CC",
              by_email.get("alice@example.com", {}).get("club"))
        check("bob's row names his linked club",
              by_email.get("bob@example.com", {}).get("club") == "Beta CC",
              by_email.get("bob@example.com", {}).get("club"))
        check("a merge_vars club override wins over the linked club",
              by_email.get("carol@example.com", {}).get("club") == "Carol's Own Club",
              by_email.get("carol@example.com", {}).get("club"))
        check("a directory contact with no club shows no club",
              by_email.get("dave@example.com", {}).get("club") is None,
              by_email.get("dave@example.com", {}).get("club"))

        print("\n── Last emailed is cross-campaign, not this campaign ──────────")
        # alice's C1 row must report her LATER (C2) send, not C1's own.
        alice = by_email.get("alice@example.com", {})
        check("alice's last-emailed is the later (March) send, not this campaign's",
              instant(alice.get("last_emailed_at")) == T2, alice.get("last_emailed_at"))
        check("...and specifically NOT the January send she is being listed under",
              instant(alice.get("last_emailed_at")) != T1, alice.get("last_emailed_at"))
        # bob was only ever emailed in C1, so his last-emailed IS T1.
        bob = by_email.get("bob@example.com", {})
        check("bob, emailed once, reports that one send",
              instant(bob.get("last_emailed_at")) == T1, bob.get("last_emailed_at"))

        print("\n── The events-only row, and problem flags ─────────────────────")
        ghost = by_email.get("ghost@example.com")
        check("an event whose recipient row is gone still appears",
              ghost is not None and ghost.get("bounced") is True, ghost)
        check("the events-only row has no club and no last-emailed",
              ghost is not None and ghost.get("club") is None
              and ghost.get("last_emailed_at") is None, ghost)
        check("bob's bounce event flags him bounced",
              by_email.get("bob@example.com", {}).get("bounced") is True)

        print("\n── The 'only' filters still narrow, unchanged ─────────────────")
        bounced = await recipients(db, staff, outreach, c1.id, only="bounced")
        b_emails = {r["email"] for r in bounced["recipients"]}
        check("bounced filter keeps only the bounced (bob + ghost)",
              b_emails == {"bob@example.com", "ghost@example.com"}, b_emails)
        check("...and those rows still carry the club and last-emailed",
              any(r["email"] == "bob@example.com"
                  and r.get("club") == "Beta CC"
                  and instant(r.get("last_emailed_at")) == T1
                  for r in bounced["recipients"]))

        print("\n── A club's own member: last-emailed, but no club ─────────────")
        m_ed = contact("ed@example.com", None, org=own, source="player")
        await db.flush()
        c_own = campaign("Club newsletter", org=own)
        await db.flush()
        TO = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
        recip(c_own, m_ed, "ed@example.com", TO, org=own)
        await db.commit()
        own_res = await recipients(db, staff, own, c_own.id)
        ed = next((r for r in own_res["recipients"] if r["email"] == "ed@example.com"), {})
        check("a club member's recipient row still reports when last emailed",
              instant(ed.get("last_emailed_at")) == TO, ed.get("last_emailed_at"))
        check("...but carries no club (marketing_club_id is NULL for a member)",
              ed.get("club") is None, ed.get("club"))
        check("the member's send is scoped to the club, not the outreach org",
              instant(by_email.get("alice@example.com", {}).get("last_emailed_at")) == T2,
              "outreach recency unchanged by the other org's send")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
