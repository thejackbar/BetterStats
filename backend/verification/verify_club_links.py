"""Linked clubs (migration 322): a Super Admin links clubs, a Club Admin switches.

Runs the SHIPPED code (imported, nothing retyped) against a real Postgres:
`auth._build_me`, `auth.switch_club`, `auth.get_current_club`, the
`require_module` gate, `committee.is_club_admin`, StatLab's report gate and the
Super Admin router bodies. New keys and functions are read through presence-safe
accessors, so a control run against the commit BEFORE the feature reports each
missing behaviour as a failure instead of crashing.

    python -m verification.verify_club_links
"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_club_links",
)
os.environ["DATABASE_URL"] = DB_URL

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.models.db import Base, ClubMembership, Organisation, User  # noqa: E402
from app.routers import auth  # noqa: E402

try:
    from app.services import club_link_ddl  # noqa: E402
    DDL = list(club_link_ddl.STATEMENTS)
except Exception:  # control run: the feature does not exist yet
    club_link_ddl = None
    # Only so the behaviour checks below can still run and fail on behaviour.
    DDL = [
        "CREATE TABLE IF NOT EXISTS club_links (organisation_id UUID PRIMARY KEY REFERENCES "
        "organisations(id) ON DELETE CASCADE, group_id UUID NOT NULL, linked_by_user_id UUID "
        "REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
    ]

try:
    from app.services import club_links as svc  # noqa: E402
except Exception:
    svc = None
try:
    from app.routers import club_links as links_router  # noqa: E402
except Exception:
    links_router = None
from app.services import committee  # noqa: E402
from app.routers import statlab  # noqa: E402
from app.auth import modules as modules_mod  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


AUDIT_DDL = """CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
    user_id UUID, action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(AUDIT_DDL))
        for _ in range(3):
            for st in DDL:
                await conn.execute(text(st))
    check("the DDL applies three times over", True)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        def club(label, active=True, archived=False, modules=None):
            from datetime import datetime, timezone
            return Organisation(
                id=uuid.uuid4(), name=f"{label} CC", slug=label.lower(), is_active=active,
                archived_at=datetime.now(timezone.utc) if archived else None,
                module_overrides=modules or [],
            )

        A = club("Alpha")                       # home of the main admin, no add-ons
        B = club("Bravo", modules=["fees"])     # linked to A, holds BetterAdmin fees
        C = club("Charlie")                     # linked later
        D = club("Delta")                       # never linked
        E = club("Echo", active=False)          # linked but inactive
        F = club("Foxtrot", archived=True)      # archived
        db.add_all([A, B, C, D, E, F])
        await db.flush()
        IA, IB, IC, ID, IE, IF = A.id, B.id, C.id, D.id, E.id, F.id

        people: dict[str, tuple] = {}

        def person(key, org, role, primary=False):
            u = User(id=uuid.uuid4(), username=key, display_name=key.title(), email=f"{key}@x.test")
            db.add(u)
            people[key] = (u, org, role, primary)

        person("a_admin", A, "club_admin", True)
        person("a_second", A, "club_admin")
        person("a_member", A, "club_member")
        person("b_admin", B, "club_admin", True)
        person("d_admin", D, "club_admin", True)
        person("staff", A, "super_admin")
        await db.flush()
        for key, (u, org, role, primary) in people.items():
            db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role, is_primary_admin=primary))
        await db.commit()

        U = lambda k: people[k][0]  # noqa: E731
        UID = {k: v[0].id for k, v in people.items()}

        async def fresh(key):
            """The user, reloaded: a rollback (a refusal) expires every loaded object."""
            u = await db.get(User, UID[key])
            await db.refresh(u)
            return u

        async def reload_user(key):
            return await fresh(key)

        async def me(key):
            await db.commit()
            return await auth._build_me(await fresh(key), db)

        async def swc(key, club_id):
            """POST /auth/switch-club as `key`. Returns (me | None, http status | None)."""
            try:
                body = auth.SwitchClubRequest(club_id=str(club_id) if club_id else None)
                return await auth.switch_club(body, current_user=await fresh(key), db=db), None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

        async def scoped_club(key):
            await db.commit()
            return await auth.get_current_club(current_user=await fresh(key), db=db)

        async def link(a, b):
            if links_router is None:
                return None, "feature missing"
            try:
                return await links_router.link(links_router.LinkRequest(club_a_id=str(a), club_b_id=str(b)),
                                               current_user=await fresh("staff"), db=db), None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

        async def unlink(org):
            if links_router is None:
                return None, "feature missing"
            try:
                return await links_router.unlink(str(org), current_user=await fresh("staff"), db=db), None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

        def ids(me_payload):
            return [c["id"] for c in (me_payload.get("linked_clubs") or [])]

        # ── 1. nothing linked yet: the switcher is not offered ────────────
        m = await me("a_admin")
        check("an unlinked club's admin has no linked clubs", m.get("linked_clubs") in ([], None)
              and not m.get("can_switch_linked_clubs"), str(m.get("linked_clubs")))

        # ── 2. Super Admin links ─────────────────────────────────────────
        res, err = await link(IA, IB)
        check("a Super Admin can link two clubs", err is None and res and res.get("group"), str(err))
        check("the group lists both clubs",
              bool(res) and {c["name"] for c in res["group"]["clubs"]} == {"Alpha CC", "Bravo CC"})

        _, e = await link(IA, IA)
        check("a club cannot be linked to itself (422)", e == 422, str(e))
        _, e = await link(IA, IB)
        check("linking an already-linked pair is refused (409)", e == 409, str(e))
        _, e = await link(IA, uuid.uuid4())
        check("an unknown club is refused (404)", e == 404, str(e))
        _, e = await link(IA, IF)
        check("an archived club cannot be linked (409)", e == 409, str(e))
        # two clubs each already in a different group must not be merged silently
        await link(ID, IC)
        _, e = await link(IA, ID)
        check("two clubs already in different groups are refused (409)", e == 409, str(e))
        if links_router is not None:
            await unlink(IC)  # dissolves the D-C pair
            rows = (await db.execute(text("SELECT count(*) FROM club_links WHERE organisation_id = ANY(:ids)"),
                                     {"ids": [ID, IC]})).scalar()
            check("unlinking one of a pair dissolves the pair", rows == 0, str(rows))

        # ── 3. what a Club Admin sees ────────────────────────────────────
        m = await me("a_admin")
        check("a linked club's admin sees the group, home club first",
              ids(m) == [str(IA), str(IB)], str(ids(m)))
        check("the switcher flag is on", bool(m.get("can_switch_linked_clubs")))
        check("the current club is marked", [c["id"] for c in m.get("linked_clubs", []) if c.get("is_current")] == [str(IA)])
        m_b = await me("b_admin")
        check("the other club's admin sees the same group", ids(m_b) == [str(IB), str(IA)], str(ids(m_b)))
        check("an unrelated club's admin still sees nothing",
              (await me("d_admin")).get("linked_clubs") in ([], None))
        check("a club member does not get the switcher", (await me("a_member")).get("linked_clubs") in ([], None))
        check("a Super Admin keeps the full switcher, not the linked list",
              (await me("staff")).get("can_switch_clubs") is True and (await me("staff")).get("linked_clubs") in ([], None))

        # ── 4. switching ─────────────────────────────────────────────────
        out, st = await swc("a_admin", IB)
        check("a Club Admin can switch into a linked club", st is None and out is not None, f"status {st}")
        m = await me("a_admin")
        check("/auth/me now scopes to the linked club", m.get("club_id") == str(IB) and m.get("club_name") == "Bravo CC",
              f"{m.get('club_id')}")
        check("it says they are in a linked club, and not 'acting as super admin'",
              m.get("acting_as_linked_club") is True and m.get("acting_as_club") is False)
        check("their home club is still reported", m.get("home_club_id") == str(IA))
        check("the current club flag follows the switch",
              [c["id"] for c in m.get("linked_clubs", []) if c.get("is_current")] == [str(IB)])
        sc = await scoped_club("a_admin")
        check("club-scoped requests (get_current_club) now resolve to the linked club", sc.id == IB, sc.slug)
        check("the other account in the home club is unaffected", (await scoped_club("a_second")).id == IA)

        # module gate: Bravo holds fees, Alpha does not
        async def gate(key, module):
            await db.commit()
            u = await fresh(key)
            try:
                dep = modules_mod.require_module(module)
                got = await dep(current_user=u, db=db)
                return got.id
            except HTTPException as e:
                await db.rollback()
                return e.status_code
        g = await gate("a_admin", "fees")
        check("the module gate uses the club being worked in (Bravo has fees)", g == IB, str(g))
        await swc("a_admin", None)
        g = await gate("a_admin", "fees")
        check("back home the gate uses the home club (Alpha has no fees, 402)", g == 402, str(g))
        await swc("a_admin", IB)

        check("committee admin rights follow the link",
              await committee.is_club_admin(db, IB, await reload_user("a_admin")) is True)
        check("...and do not reach an unlinked club",
              await committee.is_club_admin(db, ID, await reload_user("a_admin")) is False)
        check("...nor a club member", await committee.is_club_admin(db, IB, await reload_user("a_member")) is False)
        try:
            can = await statlab._user_can_manage_reports(db, await reload_user("a_admin"), await db.get(Organisation, IB))
        except Exception as ex:  # the old code raised AttributeError here
            can = f"raised {type(ex).__name__}"
        check("StatLab's report gate accepts a linked club admin", can is True, str(can))
        try:
            can = await statlab._user_can_manage_reports(db, await reload_user("d_admin"), await db.get(Organisation, IB))
        except Exception as ex:
            can = f"raised {type(ex).__name__}"
        check("...and still refuses an unlinked club admin", can is False, str(can))

        # ── 5. refusals ──────────────────────────────────────────────────
        before = (await reload_user("d_admin")).active_club_id
        _, st = await swc("d_admin", IB)
        check("an unlinked club's admin cannot switch into someone else's club (403)", st == 403, str(st))
        check("...and nothing was stored", (await reload_user("d_admin")).active_club_id == before)
        _, st = await swc("a_admin", ID)
        check("a linked admin cannot reach an unlinked club (403)", st == 403, str(st))
        _, st = await swc("a_member", IB)
        check("a club member cannot switch (403)", st == 403, str(st))
        _, st = await swc("a_admin", uuid.uuid4())
        check("a made-up club answers the same as an unlinked one (403)", st == 403, str(st))
        _, st = await swc("a_admin", "not-a-uuid")
        check("a malformed id is refused (422)", st == 422, str(st))

        # forged column: a stale / hand-set active_club_id never widens reach
        d = await reload_user("d_admin")
        d.active_club_id = IB
        await db.commit()
        check("a forged active_club_id for an unlinked admin is ignored (get_current_club)",
              (await scoped_club("d_admin")).id == ID)
        check("...and by /auth/me", (await me("d_admin")).get("club_id") == str(ID))
        check("...and by the module gate", await gate("d_admin", "fees") == 402)
        d = await reload_user("d_admin")
        d.active_club_id = None
        await db.commit()

        # ── 6. inactive / archived targets ───────────────────────────────
        await link(IA, IE)
        m = await me("a_admin")
        check("an inactive linked club is not offered", str(IE) not in ids(m), str(ids(m)))
        _, st = await swc("a_admin", IE)
        check("...and cannot be switched into (403)", st == 403, str(st))

        # ── 7. a third club joins the group ──────────────────────────────
        res, err = await link(IC, IA)
        check("a third club joins the existing group", err is None and res
              and len(res["group"]["clubs"]) == 4, str(err or (res and len(res["group"]["clubs"]))))
        m = await me("a_admin")
        check("every club in the group is offered", set(ids(m)) == {str(IA), str(IB), str(IC)}, str(ids(m)))
        m = await me("b_admin")
        check("Bravo's admin can reach Charlie through the group", str(IC) in ids(m))

        # ── 8. archiving the club being worked in ────────────────────────
        await swc("a_admin", IC)
        c = await db.get(Organisation, IC)
        from datetime import datetime, timezone
        c.archived_at = datetime.now(timezone.utc)
        await db.commit()
        check("an archived linked club drops the admin back home", (await scoped_club("a_admin")).id == IA)
        check("...and out of the list", str(IC) not in ids(await me("a_admin")))
        c = await db.get(Organisation, IC)
        c.archived_at = None
        await db.commit()
        await swc("a_admin", None)

        # ── 9. unlinking ends the switch at once ─────────────────────────
        await swc("a_admin", IB)
        out, err = await unlink(IB)
        check("a Super Admin can unlink a club", err is None, str(err))
        check("the admin working in it is back home on the very next request",
              (await scoped_club("a_admin")).id == IA)
        check("the stale switch was cleared from the user row",
              (await reload_user("a_admin")).active_club_id is None)
        check("the unlinked club's admin no longer sees the group",
              (await me("b_admin")).get("linked_clubs") in ([], None))
        _, st = await swc("a_admin", IB)
        check("switching into it is now refused (403)", st == 403, str(st))
        _, err = await unlink(IB)
        check("unlinking a club that is not linked is refused (404)", err == 404, str(err))

        # remaining group A + E + C: unlink C and E -> group falls to one club and goes away
        await unlink(IC)
        await unlink(IE)
        left = (await db.execute(text("SELECT count(*) FROM club_links"))).scalar()
        check("a group reduced to one club is dissolved", left == 0, str(left))
        check("the home club's admin has no switcher again", (await me("a_admin")).get("linked_clubs") in ([], None))

        # ── 10. Super Admin behaviour is unchanged ───────────────────────
        out, st = await swc("staff", ID)
        check("a Super Admin still switches to any club", st is None
              and (await me("staff")).get("club_id") == str(ID) and (await me("staff")).get("acting_as_club") is True)
        if svc is not None:
            await svc.clear_stale_switches(db)
            await db.commit()
        check("tidying stale switches never touches a Super Admin",
              (await reload_user("staff")).active_club_id == ID)
        await swc("staff", None)

        # ── 10b. each club keeps its OWN trial and subscription ──────────
        # A switched-in admin is bound by the club they are working in, never by
        # their home club's plan and never by the best of the group.
        from datetime import datetime, timedelta, timezone
        from app.models.db import OrgModuleSubscription
        now = datetime.now(timezone.utc)

        def plan(label, status="active", modules=None, subs=None):
            o = club(label, modules=modules)
            o.subscription_status = status
            return o, subs or []

        H, h_subs = plan("Home", modules=["comms"], subs=[("core", "active", None), ("comms", "active", None)])
        T1, t1_subs = plan("Trialing", modules=["fees"], subs=[("core", "active", None), ("fees", "trial", now + timedelta(days=5))])
        T2, t2_subs = plan("Lapsed", modules=["fees"], subs=[("core", "active", None), ("fees", "trial", now - timedelta(days=1))])
        T3, t3_subs = plan("Paused", status="paused", modules=["fees"], subs=[("core", "active", None), ("fees", "active", None)])
        T4, t4_subs = plan("Corelapsed", modules=["fees"], subs=[("core", "trial", now - timedelta(days=2)), ("fees", "active", None)])
        T5, t5_subs = plan("Subscribed", modules=["fees"], subs=[("core", "active", None), ("fees", "active", None)])
        # The junior-club case: Core only, no add-on at all, while the home club holds BetterSocials.
        T6, t6_subs = plan("Coreonly", modules=[], subs=[("core", "active", None)])
        H.module_overrides = ["comms", "socials"]
        h_subs = [("core", "active", None), ("comms", "active", None), ("socials", "active", None)]
        planned = [(H, h_subs), (T1, t1_subs), (T2, t2_subs), (T3, t3_subs), (T4, t4_subs), (T5, t5_subs), (T6, t6_subs)]
        for o, _ in planned:
            db.add(o)
        await db.flush()
        for o, subs in planned:
            for key, st, ends in subs:
                db.add(OrgModuleSubscription(organisation_id=o.id, module_key=key, status=st, trial_ends_at=ends))
        pid = {o.slug: o.id for o, _ in planned}
        hu = User(id=uuid.uuid4(), username="h_admin", display_name="H", email="h@x.test")
        db.add(hu)
        await db.flush()
        db.add(ClubMembership(club_id=pid["home"], user_id=hu.id, role="club_admin", is_primary_admin=True))
        people["h_admin"] = (hu, H, "club_admin", True)
        UID["h_admin"] = hu.id
        await db.commit()
        # A real request opens a fresh session, so the club is loaded WITH its
        # subscription rows (get_current_club / require_module eager-load them).
        # These objects were created in this session, so detach them or db.get
        # would hand back the cached copy with the rows unloaded.
        for o, _ in planned:
            db.expunge(o)
        for o, _ in planned[1:]:
            if svc is not None or links_router is not None:
                await link(pid["home"], o.id)

        async def ent(key):
            m = await me(key)
            return m.get("entitlements") or {}

        async def switch_and_gate(target):
            await swc("h_admin", target)
            return {mod: await gate("h_admin", mod) for mod in ("fees", "comms")}, await ent("h_admin")

        def allowed(g, mod, org_id):
            return g[mod] == org_id

        g, e = await switch_and_gate(None)
        check("at home the admin holds the home club's module, not the others'",
              allowed(g, "comms", pid["home"]) and g["fees"] == 402, str(g))
        check("/auth/me entitlements are the home club's",
              e.get("modules") == ["comms", "socials"] and e.get("core_live") is True, str(e.get("modules")))

        g, e = await switch_and_gate(pid["trialing"])
        check("in a club on a live trial, that trial's module opens and the home club's does not",
              allowed(g, "fees", pid["trialing"]) and g["comms"] == 402, str(g))
        check("...and /auth/me shows that club's entitlements", e.get("modules") == ["fees"], str(e.get("modules")))

        g, e = await switch_and_gate(pid["lapsed"])
        check("in a club whose trial has ended the module is closed (402), whatever the stale cache says",
              g["fees"] == 402 and g["comms"] == 402, str(g))
        check("...and /auth/me does not list it", "fees" not in (e.get("modules") or []), str(e.get("modules")))

        g, e = await switch_and_gate(pid["paused"])
        check("in a paused club every add-on is closed",
              g["fees"] == 402 and g["comms"] == 402, str(g))
        check("...and Core reads as not live, with the paused status",
              e.get("core_live") is False and e.get("status") == "paused", f"{e.get('core_live')} {e.get('status')}")

        g, e = await switch_and_gate(pid["corelapsed"])
        check("in a club whose Core trial has ended nothing is open, even a subscribed add-on",
              g["fees"] == 402 and e.get("core_live") is False, f"{g} core_live={e.get('core_live')}")

        # A Core-only club: BetterSocials (held by the home club) must NOT carry over.
        async def gate_socials(target):
            await swc("h_admin", target)
            return await gate("h_admin", "socials"), await ent("h_admin")
        gs, e = await gate_socials(None)
        check("at the home club BetterSocials is open", gs == pid["home"], str(gs))
        gs, e = await gate_socials(pid["coreonly"])
        check("in a Core-only linked club BetterSocials is refused (402) even though the home club holds it",
              gs == 402, str(gs))
        check("...and /auth/me lists no add-on, Core still live",
              (e.get("modules") or []) == [] and e.get("core_live") is True, f"{e.get('modules')} {e.get('core_live')}")
        await swc("h_admin", None)

        g, e = await switch_and_gate(pid["subscribed"])
        check("in a subscribed club its modules are open", allowed(g, "fees", pid["subscribed"]), str(g))
        g, e = await switch_and_gate(None)
        check("coming home brings the home club's limits straight back (the other club's module closes again)",
              allowed(g, "comms", pid["home"]) and g["fees"] == 402 and e.get("core_live") is True, str(g))

        # The same restrictions hold for the club's own admin, so a linked admin
        # sees exactly what that club's own admin sees.
        sub_admin = User(id=uuid.uuid4(), username="s_admin", display_name="S", email="s@x.test")
        db.add(sub_admin)
        await db.flush()
        db.add(ClubMembership(club_id=pid["lapsed"], user_id=sub_admin.id, role="club_admin", is_primary_admin=True))
        people["s_admin"] = (sub_admin, T2, "club_admin", True)
        UID["s_admin"] = sub_admin.id
        await db.commit()
        await swc("h_admin", pid["lapsed"])
        own = await ent("s_admin")
        linked_view = await ent("h_admin")
        check("a linked admin sees the same entitlements as that club's own admin",
              own.get("modules") == linked_view.get("modules") and own.get("core_live") == linked_view.get("core_live")
              and own.get("status") == linked_view.get("status"), f"{own.get('modules')} vs {linked_view.get('modules')}")
        await swc("h_admin", None)

        # Plan, trial and payment changes need the club's OWN admin: being linked
        # does not let a switched-in admin start a trial, buy or change how it pays.
        await swc("h_admin", pid["trialing"])
        from app.routers import billing as billing_router, club_admin as club_admin_router
        club_t1 = await scoped_club("h_admin")
        async def refused403(coro):
            try:
                await coro
                return False
            except HTTPException as ex:
                await db.rollback()
                return ex.status_code == 403
            except Exception:  # control run: the call got further than a refusal
                await db.rollback()
                return False
        check("a switched-in admin cannot start a trial for the linked club",
              await refused403(club_admin_router.start_own_module_trial(
                  "select", current_user=await fresh("h_admin"), club=await scoped_club("h_admin"), db=db)))
        check("...cannot manage its payment methods",
              await refused403(billing_router._require_primary_or_super_admin(db, await fresh("h_admin"), await scoped_club("h_admin"))))
        check("...cannot decide how it pays",
              await refused403(billing_router._require_club_admin_or_super(db, await fresh("h_admin"), await scoped_club("h_admin"))))
        await swc("h_admin", None)
        check("the same calls are allowed at the admin's own club",
              (await billing_router._require_club_admin_or_super(db, await fresh("h_admin"), await scoped_club("h_admin"))) is False)

        # ── 11. audit + auth ─────────────────────────────────────────────
        n = (await db.execute(text("SELECT count(*) FROM audit_logs WHERE action IN ('link_club','unlink_club')"))).scalar()
        check("links and unlinks are in the activity log", n >= 6, str(n))
        if links_router is not None:
            try:
                await auth.require_super_admin(current_user=await fresh("a_admin"), db=db)
                denied = False
            except HTTPException as e:
                denied = e.status_code == 403
            check("the link endpoints sit behind require_super_admin", denied)
            deps = [getattr(d.call, "__name__", "") for r in links_router.router.routes for d in r.dependant.dependencies]
            check("every route declares it", deps.count("require_super_admin") == len(links_router.router.routes), str(deps))
        else:
            check("the Super Admin router exists", False, "missing")

        # ── 12. wiring ───────────────────────────────────────────────────
        from app.services.afl import cricket_schema_mirror as mirror
        check("the football schema mirror carries the table",
              ("app.services.club_link_ddl", "STATEMENTS") in mirror.SHARED_DDL_MODULES)
        revs = {}
        for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "alembic", "versions", "*.py")):
            src = open(f).read()
            mm = re.search(r'^revision\s*=\s*"(\w+)"', src, re.M)
            if mm:
                revs.setdefault(mm.group(1), []).append(os.path.basename(f))
        dup = {k: v for k, v in revs.items() if len(v) > 1}
        check("no two migrations share a revision id", not dup, str(dup))
        check("migration 322 exists and chains from 321", "322" in revs and "321" in revs)
        main_src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py")).read()
        check("main.py's lifespan runs the shared DDL", "club_link_ddl" in main_src)
        check("main.py mounts the router", "club_links_router.router" in main_src)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
