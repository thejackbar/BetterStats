"""Targeting the clubs nobody at the club ever ran.

Asked for on BetterCricket's internal BetterComms → Segments: a rule for
whether a club's Primary Club Admin is blank, so the contacts at a club a
super admin created or synced and no real person ever took over — in practice
a test club — can be included or left out of a List or Segment.

Runs the SHIPPED segment engine against a real Postgres.

    python -m verification.verify_primary_admin_segment
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_primary_admin",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, ClubMembership, CommsContact, CrmDeal, CrmPipeline, CrmStage,
    MarketingClub, Organisation, User,
)
from app.services import comms_segments  # noqa: E402
from app.services.trial_engagement import org_has_primary_admin  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
def dt_now():
    return _dt.datetime.now(_dt.timezone.utc)


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


async def emails_for(db, org, value, field="primary_admin") -> set:
    rows = await comms_segments.resolve_contacts(db, org, {"match": "all", "rules": [
        {"field": field, "op": "eq", "value": value}]})
    return {c.email for c in rows}


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        db.add(outreach)
        await db.flush()

        orgs, mcs = {}, {}

        async def club(label, *, onboarded=True, admin=None):
            """admin: None = no membership at all, 'primary', 'plain' (a club
            admin who is not primary), or 'member'."""
            org = None
            if onboarded:
                org = Organisation(id=uuid.uuid4(), name=f"{label} CC", slug=f"{label}-cc")
                db.add(org)
                await db.flush()
                orgs[label] = org
                if admin:
                    u = User(id=uuid.uuid4(), username=f"{label}-user",
                             email=f"{label}-user@example.com")
                    db.add(u)
                    await db.flush()
                    db.add(ClubMembership(
                        club_id=org.id, user_id=u.id,
                        role="club_member" if admin == "member" else "club_admin",
                        is_primary_admin=(admin == "primary")))
                    await db.flush()
            mc = MarketingClub(id=uuid.uuid4(), name=f"{label} CC",
                               grassroots_guid=f"guid-{label}", utm_code=f"{label}-cc",
                               existing_org_id=(org.id if org else None))
            db.add(mc)
            await db.flush()
            mcs[label] = mc
            db.add(CommsContact(id=uuid.uuid4(), organisation_id=outreach.id,
                                email=f"{label}@example.com", source="directory",
                                marketing_club_id=mc.id))
            await db.flush()
            return mc

        # A real, live club: somebody at the club is its primary admin.
        await club("live", admin="primary")
        # The reported case: a super admin made or synced it, nobody ever took
        # it over. On the platform, no primary admin.
        await club("testclub")
        # On the platform with a club_admin who is NOT the primary — still
        # nobody assigned as primary, so it belongs with the test clubs.
        await club("adminonly", admin="plain")
        # A membership that is not a club_admin at all cannot be the primary.
        await club("memberonly", admin="member")
        # An ordinary prospect: no club record on the platform at all. It has no
        # primary admin either, but it is not a test club — the whole reason
        # this is three states.
        await club("prospect", onboarded=False)
        # A contact with no directory club at all (hand-added).
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=outreach.id,
                            email="loose@example.com", source="manual"))
        await db.commit()

        print("\n── The three states ───────────────────────────────────────────")
        got = await emails_for(db, outreach, ["assigned"])
        check("assigned finds the club somebody actually runs",
              got == {"live@example.com"}, sorted(got))

        got = await emails_for(db, outreach, ["unassigned"])
        check("unassigned finds the reported case — on the platform, nobody assigned",
              got == {"testclub@example.com", "adminonly@example.com",
                      "memberonly@example.com"}, sorted(got))
        check("a club_admin who is not the primary still counts as unassigned",
              "adminonly@example.com" in got, sorted(got))
        check("a plain club_member never counts as the primary admin",
              "memberonly@example.com" in got, sorted(got))
        check("...and it does NOT sweep in the prospects",
              "prospect@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, ["not_onboarded"])
        check("not_onboarded finds the ordinary prospect",
              got == {"prospect@example.com"}, sorted(got))

        print("\n── Include and exclude, from one rule ─────────────────────────")
        got = await emails_for(db, outreach, ["assigned", "not_onboarded"])
        check("picking the other two EXCLUDES the test clubs",
              got == {"live@example.com", "prospect@example.com"}, sorted(got))
        every = await emails_for(db, outreach, ["assigned", "unassigned", "not_onboarded"])
        parts = set()
        for v in ("assigned", "unassigned", "not_onboarded"):
            parts |= await emails_for(db, outreach, [v])
        check("the three states partition every directory club — no overlap, no gap",
              every == parts and len(every) == 5, f"{len(every)} vs {len(parts)}")

        print("\n── The awkward cases ──────────────────────────────────────────")
        got = await emails_for(db, outreach, ["assigned", "unassigned", "not_onboarded"])
        check("a contact with no directory club is never matched by any state",
              "loose@example.com" not in got, sorted(got))
        # A selection that resolves to nothing drops the CONDITION, but the rule
        # still joins the directory club — so the audience narrows to
        # directory-linked contacts and no further. That is not special to this
        # field: it is what every _DIR_MC_FIELDS rule already does, and the check
        # is that the new one behaves the same rather than inventing its own rule.
        async def demo_emails(value):
            rows = await comms_segments.resolve_contacts(db, outreach, {
                "match": "all", "rules": [{"field": "had_demo", "op": "eq", "value": value}]})
            return {c.email for c in rows}

        for label, value in [("an empty selection", []), ("an unknown state", ["not-a-state"])]:
            mine = await emails_for(db, outreach, value)
            theirs = await demo_emails(value)
            check(f"{label} filters nobody out, exactly as the existing club rules do",
                  mine == theirs and "loose@example.com" not in mine and len(mine) == 5,
                  f"{sorted(mine)} vs {sorted(theirs)}")

        # A second primary admin at another club must not make THIS club read as
        # assigned — the EXISTS has to correlate on the club, not just exist.
        second = await club("other", admin="primary")
        await db.commit()
        got = await emails_for(db, outreach, ["unassigned"])
        check("another club's primary admin does not make this one read assigned",
              "testclub@example.com" in got and "other@example.com" not in got, sorted(got))

        print("\n── The SQL and the existing Python rule agree ─────────────────")
        # trial_engagement.org_has_primary_admin is the app's existing answer to
        # this question. Asserted row by row rather than assumed.
        assigned = await emails_for(db, outreach, ["assigned"])
        disagreed = []
        for label, org in orgs.items():
            py = await org_has_primary_admin(db, org.id)
            sql = f"{label}@example.com" in assigned
            if py != sql:
                disagreed.append((label, py, sql))
        check("every onboarded club is classified the same way by both",
              not disagreed and len(orgs) == 5, disagreed or len(orgs))

        print("\n── Won, and anything but Won ──────────────────────────────────")
        # BetterCricket's own pipeline, plus a club's own CRM pipeline that must
        # never be mistaken for it.
        platform = CrmPipeline(id=uuid.uuid4(), scope="platform", name="BetterCricket Sales",
                               is_default=True)
        club_own = CrmPipeline(id=uuid.uuid4(), scope="club", organisation_id=orgs["live"].id,
                               name="Applecross sponsors", is_default=True)
        db.add_all([platform, club_own])
        await db.flush()
        stages = {}
        for pipe, key, won, lost in [
            (platform, "target", False, False), (platform, "trial", False, False),
            (platform, "won", True, False), (platform, "lost", False, True),
            (club_own, "won", True, False),
        ]:
            st = CrmStage(id=uuid.uuid4(), pipeline_id=pipe.id, key=key, name=key.title(),
                          is_won=won, is_lost=lost)
            db.add(st)
            await db.flush()
            stages[(pipe.id, key)] = st

        async def deal(mc_label, stage, *, archived=False, status=None, pipe=None):
            mc = mcs[mc_label]
            pipe = pipe or platform
            db.add(CrmDeal(
                id=uuid.uuid4(), scope=pipe.scope, marketing_club_id=mc.id,
                pipeline_id=pipe.id, stage_id=stages[(pipe.id, stage)].id,
                title=f"{mc_label} deal", status=status or "open",
                archived_at=(dt_now() if archived else None)))
            await db.flush()

        await deal("live", "won", status="won")           # bought
        await deal("testclub", "trial")                   # still being worked
        await deal("adminonly", "lost", status="lost")    # went away
        # A won deal on the CLUB'S OWN pipeline — a sponsorship they closed.
        # BetterCricket has not sold them anything.
        await deal("memberonly", "won", status="won", pipe=club_own)
        # A won deal that was archived: off the board, so off this rule too.
        await deal("other", "won", status="won", archived=True)
        # "prospect" is left with no deal at all.
        await db.commit()

        got = await emails_for(db, outreach, "won", field="deal_won")
        check("Won finds the club that actually bought",
              got == {"live@example.com"}, sorted(got))
        check("a club's OWN won deal is not BetterCricket winning them",
              "memberonly@example.com" not in got, sorted(got))
        check("an archived won deal is off the pipeline, so off this rule",
              "other@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, "not_won", field="deal_won")
        check("anything but Won covers an open deal, a lost one and no deal at all",
              got == {"testclub@example.com", "adminonly@example.com",
                      "memberonly@example.com", "other@example.com",
                      "prospect@example.com"}, sorted(got))

        won = await emails_for(db, outreach, "won", field="deal_won")
        not_won = await emails_for(db, outreach, "not_won", field="deal_won")
        check("the two states partition every directory club — no overlap, no gap",
              not (won & not_won) and len(won | not_won) == 6, f"{len(won)}+{len(not_won)}")

        # Won-ness comes from the STAGE, not crm_deals.status. The live data has
        # rows where the two disagree, and the stage is what a reader sees.
        await deal("prospect", "trial", status="won")
        await db.commit()
        got = await emails_for(db, outreach, "won", field="deal_won")
        check("a deal whose status says won but sits in Trial is NOT won",
              "prospect@example.com" not in got, sorted(got))
        await db.execute(text(
            "UPDATE crm_deals SET status = 'open' WHERE title = 'prospect deal'"))
        await db.execute(text(
            "UPDATE crm_deals SET stage_id = :s WHERE title = 'prospect deal'"),
            {"s": stages[(platform.id, "won")].id})
        await db.commit()
        got = await emails_for(db, outreach, "won", field="deal_won")
        # Asserted as the exact set: "is prospect in it" alone passes on code
        # that has dropped the rule and matched everybody.
        check("...and one sitting in Won IS, whatever its status column says",
              got == {"live@example.com", "prospect@example.com"}, sorted(got))

        got = await emails_for(db, outreach, "", field="deal_won")
        check("an unknown value filters nobody out", len(got) == 6, len(got))

        print("\n── Scope and wiring ───────────────────────────────────────────")
        check("the deal rule is a directory field too",
              "deal_won" in comms_segments.DIRECTORY_FIELDS)
        got = await emails_for(db, outreach, "won", field="deal_won")
        check("it composes with the primary-admin rule", bool(got), sorted(got))
        check("it is a directory field, so a club build can never reach it",
              "primary_admin" in comms_segments.DIRECTORY_FIELDS
              and "primary_admin" not in (
                  comms_segments.CONTACT_FIELDS | comms_segments.PLAYER_FIELDS
                  | comms_segments.STAT_FIELDS | comms_segments.SPECIAL_FIELDS))
        own = Organisation(id=uuid.uuid4(), name="A Club", slug="a-club")
        db.add(own)
        await db.flush()
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=own.id,
                            email="member@example.com", source="player"))
        await db.commit()
        got = await emails_for(db, own, ["unassigned"])
        check("a club naming it reaches nobody, per the scope guard", got == set(), sorted(got))

        defs = open(os.path.join(
            REPO, "frontend/src/pages/admin/bettercomms/segmentFields.jsx")).read()
        dir_block = defs.split("export const DIRECTORY_FIELD_DEFS")[1]
        club_block = defs.split("export const CLUB_FIELD_DEFS")[1].split(
            "export const DIRECTORY_FIELD_DEFS")[0]
        check("the picker offers it in the directory field set",
              "  primary_admin:" in dir_block)
        check("...and offers the deal rule too", "  deal_won:" in dir_block)
        deal_entry = (dir_block.split("deal_won:")[1].split("},")[0]
                      if "  deal_won:" in dir_block else "")
        check("won / not won is a single select — a clean partition needs no multi",
              "'select'" in deal_entry and "'multi'" not in deal_entry,
              "the field is not in the picker" if not deal_entry else deal_entry[:60])
        check("both directions are offered",
              "['won'," in deal_entry and "['not_won'," in deal_entry)
        check("the deal rule is not in the club field set", "deal_won" not in club_block)
        check("...and not in the club field set", "primary_admin" not in club_block)
        # Reported as absent rather than crashing the run, so a control run
        # against code without the field still finishes and says which checks fail.
        entry = (dir_block.split("primary_admin:")[1].split("},")[0]
                 if "  primary_admin:" in dir_block else "")
        check("it is a multi-select, which is what makes exclude expressible",
              entry.count("'multi'") == 1, "the field is not in the picker" if not entry else entry[:60])
        check("all three states are offered",
              bool(entry) and all(f"['{k}'," in entry
                                  for k in ("assigned", "unassigned", "not_onboarded")),
              "the field is not in the picker" if not entry else "")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
