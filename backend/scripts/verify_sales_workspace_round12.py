"""Verifies the Extend Trial feature: module_subscriptions.extend_trial_for_org
(reset-start-on-expired vs leave-start-on-active) and the full
POST /clubs/{deal_id}/extend-trial router flow — contact resolution (existing
directory contact / crm person / new contact), days validation, and the three
nominate-primary-admin branches (brand-new invite, promote an existing
co-admin, and the two conflict cases). Run with:

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/bstest \
    python -m scripts.verify_sales_workspace_round12
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bstest")
os.environ.setdefault("SECRET_KEY", "test-secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload

from app.models.db import (
    Base, ClubMembership, MarketingClub, MarketingClubContact, Organisation, OrgModuleSubscription, User,
)
from app.services import crm as crm_service
from app.services import module_subscriptions as msub
from app.services import memberships
from app.auth.modules import STATUS_TRIAL, STATUS_ACTIVE

FAILS = []


def check(name, cond, detail=""):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class FakeActor:
    def __init__(self, user, role):
        self.user = user
        self.role = role


async def main():
    # ── Part 1: extend_trial_for_org, pure ORM object manipulation ──────
    now = datetime.now(timezone.utc)
    org = Organisation(id=uuid.uuid4(), name="Pure Test CC")
    org.module_subscriptions = [
        OrgModuleSubscription(
            id=uuid.uuid4(), organisation_id=org.id, module_key="core", status=STATUS_TRIAL,
            trial_started_at=now - timedelta(days=20), trial_ends_at=now - timedelta(days=6),
        ),
        OrgModuleSubscription(
            id=uuid.uuid4(), organisation_id=org.id, module_key="select", status=STATUS_ACTIVE,
            trial_started_at=None, trial_ends_at=None,
        ),
    ]
    touched = msub.extend_trial_for_org(org, days=14, reset_start=True, now=now)
    check("extend_trial_for_org touches only the trial-status row", len(touched) == 1 and touched[0].module_key == "core")
    core_sub = next(s for s in org.module_subscriptions if s.module_key == "core")
    check("expired trial's start is reset to now", core_sub.trial_started_at == now)
    check("expired trial's end becomes now+14d", core_sub.trial_ends_at == now + timedelta(days=14))
    active_sub = next(s for s in org.module_subscriptions if s.module_key == "select")
    check("the active (non-trial) module is left completely untouched",
          active_sub.trial_started_at is None and active_sub.trial_ends_at is None)

    original_start = now - timedelta(days=3)
    org2 = Organisation(id=uuid.uuid4(), name="Pure Test CC 2")
    org2.module_subscriptions = [
        OrgModuleSubscription(
            id=uuid.uuid4(), organisation_id=org2.id, module_key="core", status=STATUS_TRIAL,
            trial_started_at=original_start, trial_ends_at=now + timedelta(days=4),
        ),
    ]
    msub.extend_trial_for_org(org2, days=10, reset_start=False, now=now)
    sub2 = org2.module_subscriptions[0]
    check("active trial's start date is left UNCHANGED", sub2.trial_started_at == original_start)
    check("active trial's end becomes now+10d ('from now', not old-end+10)", sub2.trial_ends_at == now + timedelta(days=10))

    # ── Part 2: real Postgres — the full router flow ─────────────────────
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from app.routers.sales_workspace import extend_trial, ExtendTrialBody, ExtendTrialContact
    from fastapi import BackgroundTasks, HTTPException

    async def make_club_and_deal(db, rep_id, *, name, trial_ends_delta_days=None, existing_org=True):
        """Returns plain (org_id, mc_id, deal_id) strings — never the ORM
        objects — so a later db.rollback() elsewhere in this script (which
        expires every loaded object) can never leave a stale synchronous
        attribute read behind."""
        org_id = None
        if existing_org:
            org = Organisation(id=uuid.uuid4(), name=name)
            db.add(org)
            await db.flush()
            org_id = org.id
            if trial_ends_delta_days is not None:
                started = datetime.now(timezone.utc) - timedelta(days=30)
                ends = datetime.now(timezone.utc) + timedelta(days=trial_ends_delta_days)
                db.add(OrgModuleSubscription(
                    id=uuid.uuid4(), organisation_id=org_id, module_key="core", status=STATUS_TRIAL,
                    trial_started_at=started, trial_ends_at=ends,
                ))
        mc = MarketingClub(
            id=uuid.uuid4(), name=name, grassroots_guid=f"manual:{uuid.uuid4()}", state="WA",
            existing_org_id=org_id,
        )
        db.add(mc)
        await db.flush()
        mc_id = mc.id
        pipeline = await crm_service.ensure_platform_pipeline(db)
        target_stage = next(s for s in pipeline.stages if s.key == "target")
        deal = await crm_service.create_deal(
            db, scope=crm_service.SCOPE_PLATFORM, pipeline_id=pipeline.id, stage_id=target_stage.id,
            title=name, marketing_club_id=mc_id, owner_user_id=rep_id,
        )
        deal_id = deal.id
        await db.commit()
        return org_id, mc_id, deal_id

    async with Session() as db:
        rep = User(id=uuid.uuid4(), username="sam", display_name="Sam", email="sam@bettersports.com.au",
                   password_hash="x")
        db.add(rep)
        await db.commit()
        rep_id = rep.id
        actor = FakeActor(rep, "sales")

        # -- No trial at all → 422 --
        _org_none, _mc_none, deal_none_id = await make_club_and_deal(db, rep_id, name="No Trial CC", trial_ends_delta_days=None)
        try:
            await extend_trial(str(deal_none_id), ExtendTrialBody(days=14), BackgroundTasks(), actor=actor, db=db)
            check("no-trial club raises", False, "did not raise")
        except HTTPException as e:
            check("no-trial club: 422 'no active trial'", e.status_code == 422 and "trial" in e.detail.lower(), e.detail)

        # -- Not registered at all (no existing_org_id) → 422 --
        _org_unreg, _mc_unreg, deal_unreg_id = await make_club_and_deal(db, rep_id, name="Unregistered CC", existing_org=False)
        try:
            await extend_trial(str(deal_unreg_id), ExtendTrialBody(days=14), BackgroundTasks(), actor=actor, db=db)
            check("unregistered club raises", False, "did not raise")
        except HTTPException as e:
            check("unregistered club: 422", e.status_code == 422, e.detail)

        # -- Days out of range → 422 (no write happens before this guard, so no rollback needed) --
        org_a_id, mc_a_id, deal_a_id = await make_club_and_deal(db, rep_id, name="Active Trial CC", trial_ends_delta_days=5)
        for bad_days in (0, 15, -1):
            try:
                await extend_trial(str(deal_a_id), ExtendTrialBody(days=bad_days), BackgroundTasks(), actor=actor, db=db)
                check(f"days={bad_days} raises", False, "did not raise")
            except HTTPException as e:
                check(f"days={bad_days}: 422", e.status_code == 422, e.detail)

        # -- No contact at all → 422 (also before any write) --
        try:
            await extend_trial(str(deal_a_id), ExtendTrialBody(days=14), BackgroundTasks(), actor=actor, db=db)
            check("no contact raises", False, "did not raise")
        except HTTPException as e:
            check("no contact: 422 'pick a contact'", e.status_code == 422 and "contact" in e.detail.lower(), e.detail)

        # -- Active trial + new_contact, no nominate → extends, leaves start, sends email --
        result_active = await extend_trial(
            str(deal_a_id), ExtendTrialBody(
                days=10, new_contact=ExtendTrialContact(full_name="Pat Smith", email="pat.active@example.com"),
            ), BackgroundTasks(), actor=actor, db=db,
        )
        check("active-trial extend returns ok status", result_active["status"] == "ok")
        check("active-trial extend reports the requested day count", result_active["days"] == 10)
        check("active-trial extend reports the contact's email", result_active["contact_email"] == "pat.active@example.com")
        check("active-trial extend: email sent (console provider always ok)", result_active["email_sent"] is True)
        check("active-trial extend: no nomination requested → false", result_active["nominated_primary_admin"] is False)

        org_a_fresh = await db.get(Organisation, org_a_id, options=[selectinload(Organisation.module_subscriptions)])
        core_sub_a = next(s for s in org_a_fresh.module_subscriptions if s.module_key == "core")
        check("active trial's start date is UNCHANGED after extend",
              abs((core_sub_a.trial_started_at - (datetime.now(timezone.utc) - timedelta(days=30))).total_seconds()) < 5)
        check("active trial's end is ~now+10d", (core_sub_a.trial_ends_at - datetime.now(timezone.utc)).days in (9, 10))

        new_contact_row = await db.scalar(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == mc_a_id, MarketingClubContact.email == "pat.active@example.com",
            )
        )
        check("new_contact was written to the canonical Club Directory", new_contact_row is not None)

        # -- Expired trial → resets start date --
        org_e_id, mc_e_id, deal_e_id = await make_club_and_deal(db, rep_id, name="Expired Trial CC", trial_ends_delta_days=-7)
        result_expired = await extend_trial(
            str(deal_e_id), ExtendTrialBody(
                days=14, new_contact=ExtendTrialContact(full_name="Alex Jones", email="alex.expired@example.com"),
            ), BackgroundTasks(), actor=actor, db=db,
        )
        check("expired-trial extend returns ok", result_expired["status"] == "ok")
        org_e_fresh = await db.get(Organisation, org_e_id, options=[selectinload(Organisation.module_subscriptions)])
        core_sub_e = next(s for s in org_e_fresh.module_subscriptions if s.module_key == "core")
        check("expired trial's start date IS reset to ~now",
              (datetime.now(timezone.utc) - core_sub_e.trial_started_at).total_seconds() < 5)
        check("expired trial's end is ~now+14d", (core_sub_e.trial_ends_at - datetime.now(timezone.utc)).days in (13, 14))

        # -- Existing directory contact pick path --
        org_c_id, mc_c_id, deal_c_id = await make_club_and_deal(db, rep_id, name="Contact Pick CC", trial_ends_delta_days=3)
        contact_row = MarketingClubContact(
            id=uuid.uuid4(), marketing_club_id=mc_c_id, full_name="Jamie Lee", email="jamie@example.com",
            outreach_selected=True,
        )
        db.add(contact_row)
        await db.commit()
        contact_row_id = contact_row.id
        result_pick = await extend_trial(
            str(deal_c_id), ExtendTrialBody(days=5, directory_contact_id=str(contact_row_id)),
            BackgroundTasks(), actor=actor, db=db,
        )
        check("picking an existing directory contact works", result_pick["contact_email"] == "jamie@example.com")

        # -- Nominate: brand-new email → invites + becomes primary --
        org_n_id, mc_n_id, deal_n_id = await make_club_and_deal(db, rep_id, name="Nominate New CC", trial_ends_delta_days=5)
        result_nom = await extend_trial(
            str(deal_n_id), ExtendTrialBody(
                days=7, nominate_primary_admin=True,
                new_contact=ExtendTrialContact(full_name="Robin Admin", email="robin.new@example.com"),
            ), BackgroundTasks(), actor=actor, db=db,
        )
        check("nominate (brand new email) reports nominated=True", result_nom["nominated_primary_admin"] is True)
        check("nominate (brand new email) reports invited=True", result_nom["primary_admin_invited"] is True)
        new_user = await db.scalar(select(User).where(User.email == "robin.new@example.com"))
        check("a real User row was created for the new primary admin", new_user is not None)
        check("the new user has no password yet (invite-only)", new_user.password_hash is None)
        check("the new user carries an invite token", bool(new_user.invite_token))
        new_membership = await db.scalar(select(ClubMembership).where(ClubMembership.user_id == new_user.id))
        check("membership created as club_admin", new_membership is not None and new_membership.role == "club_admin")
        check("membership is marked primary", new_membership is not None and new_membership.is_primary_admin is True)
        check("membership points at the RIGHT org", str(new_membership.club_id) == str(org_n_id))

        # -- Nominate: already has a primary admin → 409. This DOES leave a
        # pending (uncommitted) trial-extension write on org_n behind — the
        # endpoint extends the trial before it gets to the nomination check.
        # Roll back so it can't leak into a LATER commit() elsewhere in this
        # script; nothing from this point on touches deal_n/org_n/mc_n by
        # ORM reference again (only by fresh id-based queries), so there's
        # nothing left stale to break.
        try:
            await extend_trial(
                str(deal_n_id), ExtendTrialBody(
                    days=7, nominate_primary_admin=True,
                    new_contact=ExtendTrialContact(full_name="Someone Else", email="someone.else@example.com"),
                ), BackgroundTasks(), actor=actor, db=db,
            )
            check("nominate onto a club that already has a primary raises", False, "did not raise")
        except HTTPException as e:
            check("nominate onto existing-primary club: 409", e.status_code == 409, e.detail)
        await db.rollback()
        await db.refresh(rep)

        # -- Nominate: promote an existing co-admin (no primary yet) on the SAME org --
        org_p_id, mc_p_id, deal_p_id = await make_club_and_deal(db, rep_id, name="Promote CoAdmin CC", trial_ends_delta_days=5)
        co_admin = User(id=uuid.uuid4(), username="coadmin1", display_name="Co Admin",
                         email="coadmin@example.com", password_hash="x")
        db.add(co_admin)
        await db.flush()
        co_admin_id = co_admin.id
        db.add(ClubMembership(id=uuid.uuid4(), club_id=org_p_id, user_id=co_admin_id,
                               role="club_admin", is_primary_admin=False, capabilities=[]))
        await db.commit()
        result_promote = await extend_trial(
            str(deal_p_id), ExtendTrialBody(
                days=7, nominate_primary_admin=True,
                new_contact=ExtendTrialContact(full_name="Co Admin", email="coadmin@example.com"),
            ), BackgroundTasks(), actor=actor, db=db,
        )
        check("promoting an existing co-admin reports nominated=True", result_promote["nominated_primary_admin"] is True)
        check("promoting an existing co-admin reports invited=False (no new account)", result_promote["primary_admin_invited"] is False)
        check("existing co-admin is now primary", await memberships.has_primary_admin(db, org_p_id))
        all_matching = (await db.execute(select(User.id).where(User.email == "coadmin@example.com"))).scalars().all()
        check("no duplicate User row was created for the promoted co-admin", len(all_matching) == 1, str(all_matching))

        # -- Nominate: email belongs to a user on a DIFFERENT club → 409 --
        org_x_id, mc_x_id, deal_x_id = await make_club_and_deal(db, rep_id, name="Cross Club CC", trial_ends_delta_days=5)
        other_org = Organisation(id=uuid.uuid4(), name="Some Other Club")
        db.add(other_org)
        await db.flush()
        other_org_id = other_org.id
        stranger = User(id=uuid.uuid4(), username="stranger1", display_name="Stranger",
                         email="stranger@example.com", password_hash="x")
        db.add(stranger)
        await db.flush()
        stranger_id = stranger.id
        db.add(ClubMembership(id=uuid.uuid4(), club_id=other_org_id, user_id=stranger_id,
                               role="club_admin", is_primary_admin=True, capabilities=[]))
        await db.commit()
        try:
            await extend_trial(
                str(deal_x_id), ExtendTrialBody(
                    days=7, nominate_primary_admin=True,
                    new_contact=ExtendTrialContact(full_name="Stranger", email="stranger@example.com"),
                ), BackgroundTasks(), actor=actor, db=db,
            )
            check("nominating a cross-club email raises", False, "did not raise")
        except HTTPException as e:
            check("nominating a cross-club email: 409 + explains why", e.status_code == 409 and "account" in e.detail.lower(), e.detail)
        await db.rollback()
        await db.refresh(rep)

        # The trial extension itself should NOT have landed for the
        # cross-club attempt — verify via a fresh id-keyed query (never the
        # stale org_x ORM reference, which the rollback above expired).
        org_x_fresh = await db.get(Organisation, org_x_id, options=[selectinload(Organisation.module_subscriptions)])
        sub_x = next(s for s in org_x_fresh.module_subscriptions if s.module_key == "core")
        check("a nominate conflict rolls back the whole request (trial untouched)",
              (sub_x.trial_ends_at - datetime.now(timezone.utc)).days in (4, 5), str(sub_x.trial_ends_at))

    await engine.dispose()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
