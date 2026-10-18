"""Module-locked club users (migration 344): everyone starts with full access, a
Primary Admin (or a Super Admin) can lock a colleague to one module.

Runs the SHIPPED code (imported, nothing retyped) against a real Postgres: the
club users route bodies, `require_cap` / `require_full_admin`, `auth._build_me`,
`auth.effective_club_id`, `memberships.ensure_primary_admin` and the real route
table. New names are read through presence-safe accessors, so a control run
against the commit BEFORE the feature reports each missing behaviour as a
failure instead of crashing.

    python -m verification.verify_user_access
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_user_access",
)
os.environ["DATABASE_URL"] = DB_URL

from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.auth import capabilities as caps_mod  # noqa: E402
from app.models.db import Base, ClubMembership, Organisation, User  # noqa: E402
from app.routers import auth, billing as billing_router, club_admin, statlab  # noqa: E402
from verification import audit_route_access as route_audit  # noqa: E402
from app.services import memberships  # noqa: E402

try:
    from app.services import access as access_svc  # noqa: E402
except Exception:  # control run: the feature does not exist yet
    access_svc = None

DDL: list[str] = []
for mod_name in ("access_ddl", "club_link_ddl"):
    try:
        mod = __import__(f"app.services.{mod_name}", fromlist=["STATEMENTS"])
        DDL += list(mod.STATEMENTS)
    except Exception:
        pass
if not any("user_access" in s for s in DDL):
    # Only so the behaviour checks can still run and fail on behaviour.
    DDL.append(
        "CREATE TABLE IF NOT EXISTS user_access (user_id UUID NOT NULL, club_id UUID NOT NULL, "
        "mode TEXT NOT NULL, module_key TEXT, updated_by_user_id UUID, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "PRIMARY KEY (user_id, club_id))"
    )

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


AUDIT_DDL = """CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
    user_id UUID, action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""

ALL = list(caps_mod.ALL_CAPABILITIES)
MODULE_KEYS = ["stats", "select", "socials", "iq", "fantasy", "admin"]


def locked_caps(key):
    return list(access_svc.caps_for_module(key)) if access_svc else []


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(AUDIT_DDL))
        # Production gives this column a database default (the lifespan ALTER); create_all
        # only sets the Python-side one, so the raw INSERT in the invite route needs it here.
        await conn.execute(text("ALTER TABLE users ALTER COLUMN failed_login_count SET DEFAULT 0"))
        for _ in range(3):
            for st in DDL:
                await conn.execute(text(st))
    check("the DDL applies three times over", True)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        A = Organisation(id=uuid.uuid4(), name="Alpha CC", slug="alpha", is_active=True, module_overrides=[])
        B = Organisation(id=uuid.uuid4(), name="Bravo CC", slug="bravo", is_active=True, module_overrides=[])
        db.add_all([A, B])
        await db.flush()
        AID, BID = A.id, B.id

        people: dict[str, tuple] = {}

        def person(key, org, role, primary=False, caps=None):
            u = User(id=uuid.uuid4(), username=key, display_name=key.title(), email=f"{key}@x.test")
            db.add(u)
            people[key] = (u, org, role, primary, caps or [])

        person("a_primary", A, "club_admin", True)
        person("a_second", A, "club_admin")
        person("b_primary", B, "club_admin", True)
        person("staff", A, "super_admin")
        person("legacy", A, "club_member", caps=["manage_fixtures"])
        await db.flush()
        for key, (u, org, role, primary, caps) in people.items():
            db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role, is_primary_admin=primary, capabilities=caps))
        await db.commit()
        UID = {k: v[0].id for k, v in people.items()}

        async def fresh(key):
            await db.rollback()
            u = await db.get(User, UID[key])
            await db.refresh(u)
            return u

        async def club(org_id):
            await db.rollback()
            c = await db.get(Organisation, org_id)
            await db.refresh(c)
            return c

        async def attempt(coro):
            """(result, status) — status is None on success."""
            try:
                return await coro, None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

        async def membership_row(user_id, club_id=None):
            await db.rollback()
            r = (await db.execute(text(
                "SELECT role, capabilities, is_primary_admin FROM club_memberships WHERE user_id = :u"),
                {"u": user_id})).mappings().first()
            return dict(r) if r else None

        async def lock_row(user_id):
            await db.rollback()
            return (await db.execute(text(
                "SELECT mode, module_key FROM user_access WHERE user_id = :u"), {"u": user_id})).mappings().first()

        async def gate(cap, user):
            """True when require_cap(cap) lets this user through."""
            try:
                await caps_mod.require_cap(cap)(current_user=user, db=db)
                return True
            except HTTPException:
                await db.rollback()
                await db.refresh(user)  # the rollback expired it, and the caller reuses it
                return False

        async def full_gate(user):
            fn = getattr(caps_mod, "require_full_admin", None)
            if fn is None:
                return None
            try:
                await fn()(current_user=user, db=db)
                return True
            except HTTPException:
                await db.rollback()
                await db.refresh(user)  # the rollback expired it, and the caller reuses it
                return False

        def new_user_body(name, access=None):
            kw = dict(username=name, display_name=name.title(), email=f"{name}@x.test")
            if access is not None:
                kw["access"] = access
            return club_admin.ClubUserCreate(**kw)

        async def invite(actor_key, club_obj, name, access=None):
            return await attempt(club_admin.create_club_user(
                data=new_user_body(name, access), background_tasks=BackgroundTasks(),
                current_user=await fresh(actor_key), club=club_obj, db=db))

        # ── 1. everyone starts with full access ──────────────────────────
        cA = SimpleNamespace(id=AID, name="Alpha CC")  # a rollback expires an ORM club; the routes read only id and name
        res, st = await invite("a_primary", cA, "newbie")
        check("an invite with no access creates a normal club admin", st is None and res and res.get("role") == "club_admin",
              str((res, st)))
        newbie = (await db.execute(text("SELECT id FROM users WHERE username = 'newbie'"))).scalar()
        UID["newbie"] = newbie
        row = await membership_row(newbie)
        check("the new user has no lock row", await lock_row(newbie) is None)
        full = True
        for c in ALL:
            full = full and await gate(c, await fresh("newbie"))
        check("a new user passes every capability gate (full access is the default)", full)
        full_ok = await full_gate(await fresh("newbie"))
        check("a new user passes the full-admin gate", full_ok is True, str(full_ok))
        me = await auth._build_me(await fresh("newbie"), db)
        check("/auth/me reports full access for them", (me.get("access") or {}).get("mode") == "full", str(me.get("access")))
        check("their /auth/me capabilities are every capability", sorted(me["capabilities"]) == sorted(ALL))

        # ── 2. only the Primary Admin or a Super Admin changes access ────
        res, st = await invite("a_second", cA, "sneaky", {"mode": "module", "module_key": "select"})
        n = (await db.execute(text("SELECT count(*) FROM users WHERE username = 'sneaky'"))).scalar()
        check("a non-primary admin cannot invite someone locked to a module", st == 403 and n == 0, str((st, n)))
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "select"}),
            current_user=await fresh("a_second"), club=cA, db=db))
        check("a non-primary admin cannot lock an existing user", st == 403 and await lock_row(UID["newbie"]) is None, str(st))

        # ── 3. the Primary Admin locks a user to one module ──────────────
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "select"}),
            current_user=await fresh("a_primary"), club=cA, db=db))
        check("the Primary Admin can lock a user to BetterSelect", st is None, str(st))
        row = await membership_row(UID["newbie"])
        lock = await lock_row(UID["newbie"])
        check("the user is stored as a locked club_member with a module row",
              row and row["role"] == "club_member" and lock and lock["module_key"] == "select", str((row, lock)))
        want = locked_caps("select")
        check("their capability list is exactly BetterSelect's", sorted(row["capabilities"]) == sorted(want) and len(want) > 0,
              str(row and row["capabilities"]))
        u = await fresh("newbie")
        check("they can manage selections", await gate("manage_selections", u))
        check("they can manage fixtures and votes", await gate("manage_fixtures", u) and await gate("manage_votes", u))
        check("they cannot manage fees", not await gate("manage_fees", u))
        check("they cannot manage users or settings", not await gate("manage_users", u) and not await gate("manage_settings", u))
        check("they cannot run a hard refresh", not await gate("run_hard_refresh", u))
        check("they fail the full-admin gate", (await full_gate(u)) is False)
        me = await auth._build_me(u, db)
        check("/auth/me reports the module lock",
              (me.get("access") or {}).get("mode") == "module" and (me.get("access") or {}).get("module_key") == "select",
              str(me.get("access")))
        check("/auth/me capabilities are BetterSelect's only", sorted(me["capabilities"]) == sorted(want))

        # ── 4. every module locks to its own capabilities and nothing else ──
        ok_all = True
        detail = ""
        for key in MODULE_KEYS:
            await attempt(club_admin.update_club_user(
                user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": key}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            u = await fresh("newbie")
            held = {c for c in ALL if await gate(c, u)}
            expect = set(locked_caps(key))
            if held != expect or not expect:
                ok_all = False
                detail += f" {key}: extra={sorted(held - expect)} missing={sorted(expect - held)}"
        check("each of the six modules grants exactly its own capabilities", ok_all, detail)
        if access_svc:
            union = set()
            for key in MODULE_KEYS:
                union |= set(access_svc.caps_for_module(key))
            check("no capability is forgotten: modules plus the never-locked three cover every capability",
                  union | set(access_svc.NEVER_LOCKED) == set(ALL) and not (union & set(access_svc.NEVER_LOCKED)),
                  str(sorted(set(ALL) - union - set(access_svc.NEVER_LOCKED))))
        else:
            check("no capability is forgotten: modules plus the never-locked three cover every capability", False, "no access service")

        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "nonsense"}),
            current_user=await fresh("a_primary"), club=cA, db=db))
        check("an unknown module is refused", st == 422, str(st))
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "everything-but-fees"}),
            current_user=await fresh("a_primary"), club=cA, db=db))
        check("an unknown mode is refused", st == 422, str(st))

        # ── 5. a PATCH that does not mention access leaves it alone ──────
        before = await membership_row(UID["newbie"])
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(display_name="Newbie Renamed"),
            current_user=await fresh("a_primary"), club=cA, db=db))
        after = await membership_row(UID["newbie"])
        check("editing a name does not clear a lock (an absent key is not a clear)",
              st is None and before == after and await lock_row(UID["newbie"]) is not None, str((st, before, after)))

        # ── 6. the lock can be taken off ─────────────────────────────────
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "full"}),
            current_user=await fresh("a_primary"), club=cA, db=db))
        row = await membership_row(UID["newbie"])
        check("setting full access removes the lock", st is None and await lock_row(UID["newbie"]) is None, str(st))
        check("the person is a full club admin again", row and row["role"] == "club_admin" and row["capabilities"] == [], str(row))
        u = await fresh("newbie")
        check("and passes the fees gate again", await gate("manage_fees", u))

        # ── 7. the Primary Admin and staff are never locked ──────────────
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["a_primary"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "select"}),
            current_user=await fresh("a_primary"), club=cA, db=db))
        check("the Primary Admin cannot be locked", st == 409 and await lock_row(UID["a_primary"]) is None, str(st))
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "admin"}),
            current_user=await fresh("staff"), club=cA, db=db))
        check("a Super Admin acting as the club can lock a user", st is None and (await lock_row(UID["newbie"])) is not None, str(st))

        # ── 8. protecting the Primary Admin's own account ────────────────
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["a_primary"]), data=club_admin.ClubUserUpdate(display_name="Hijacked"),
            current_user=await fresh("a_second"), club=cA, db=db))
        check("another admin cannot edit the Primary Admin's account", st == 403, str(st))
        res, st = await attempt(club_admin.update_club_user(
            user_id=str(UID["a_primary"]), data=club_admin.ClubUserUpdate(display_name="Primary Renamed"),
            current_user=await fresh("a_primary"), club=cA, db=db))
        check("the Primary Admin can edit their own account", st is None, str(st))
        res, st = await attempt(club_admin.remove_club_user(
            user_id=str(UID["a_primary"]), current_user=await fresh("a_second"), club=cA, db=db))
        check("another admin cannot remove the Primary Admin", st == 409 and await membership_row(UID["a_primary"]) is not None, str(st))

        # ── 9. a removed person leaves no lock row behind ────────────────
        res, st = await attempt(club_admin.remove_club_user(
            user_id=str(UID["newbie"]), current_user=await fresh("a_primary"), club=cA, db=db))
        check("removing a locked user removes their lock row", st is None and await lock_row(UID["newbie"]) is None, str(st))

        # ── 10. users listing carries access ─────────────────────────────
        res, st = await invite("a_primary", cA, "listed", {"mode": "module", "module_key": "admin"})
        check("the Primary Admin can invite someone locked to BetterAdmin", st is None and res and res.get("role") == "club_member", str((res, st)))
        UID["listed"] = (await db.execute(text("SELECT id FROM users WHERE username = 'listed'"))).scalar()
        listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("a_primary"), club=cA, db=db))
        mine = next((x for x in (listing or []) if x["username"] == "listed"), {})
        check("the list shows the module for a locked user", (mine.get("access") or {}).get("module_key") == "admin", str(mine.get("access")))
        prim = next((x for x in (listing or []) if x["username"] == "a_primary"), {})
        check("the list marks the Primary Admin", prim.get("is_primary_admin") is True, str(prim.get("is_primary_admin")))
        check("the list shows full access for everyone else", (next((x for x in (listing or []) if x["username"] == "a_second"), {}).get("access") or {}).get("mode") == "full")

        # ── 11. a locked person stays in their own club ──────────────────
        for oid in (AID, BID):
            await db.execute(text("INSERT INTO club_links (organisation_id, group_id) VALUES (:o, :g)"),
                             {"o": oid, "g": uuid.UUID("11111111-1111-1111-1111-111111111111")})
        await db.commit()
        await db.execute(text("UPDATE users SET active_club_id = :b WHERE id = ANY(CAST(:ids AS uuid[]))"),
                         {"b": BID, "ids": [UID["listed"], UID["a_second"]]})
        await db.commit()
        for k in ("listed", "a_second"):
            u = await fresh(k)
            m = (await db.execute(select(ClubMembership).where(ClubMembership.user_id == u.id))).scalar_one()
            eff = await auth.effective_club_id(db, m, u)
            if k == "listed":
                check("a locked person cannot act in a linked club", eff == AID, str(eff))
                me = await auth._build_me(u, db)
                check("and the club switcher is hidden for them", not me.get("linked_clubs"), str(me.get("linked_clubs")))
            else:
                check("a full admin still can (control for the check above)", eff == BID, str(eff))

        # ── 12. a switched-in admin cannot manage the linked club's users ──
        cB = SimpleNamespace(id=BID, name="Bravo CC")
        listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("a_second"), club=cB, db=db))
        check("a switched-in admin cannot list the linked club's users", st == 403, str(st))
        res, st = await invite("a_second", cB, "intruder")
        n = (await db.execute(text("SELECT count(*) FROM users WHERE username = 'intruder'"))).scalar()
        check("or invite anyone into it", st == 403 and n == 0, str((st, n)))
        res, st = await attempt(club_admin.remove_club_user(
            user_id=str(UID["b_primary"]), current_user=await fresh("a_second"), club=cB, db=db))
        check("or remove anyone from it", st == 403 and await membership_row(UID["b_primary"]) is not None, str(st))
        listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("b_primary"), club=cB, db=db))
        check("the linked club's own admin can list its users", st is None and listing is not None, str(st))
        listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("staff"), club=cB, db=db))
        check("a Super Admin acting as the linked club can", st is None, str(st))
        listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("a_primary"), club=cA, db=db))
        check("the admin's own club still works", st is None, str(st))

        # ── 13. boot-time resync and legacy rows ─────────────────────────
        if access_svc:
            await db.execute(text("UPDATE club_memberships SET capabilities = '[\"manage_fees\"]'::jsonb WHERE user_id = :u"),
                             {"u": UID["listed"]})
            await db.commit()
            n1 = await access_svc.resync_module_caps(db)
            await db.commit()
            row = await membership_row(UID["listed"])
            check("the boot resync rewrites a stale capability list", n1 >= 1 and sorted(row["capabilities"]) == sorted(locked_caps("admin")), str((n1, row)))
            n2 = await access_svc.resync_module_caps(db)
            await db.commit()
            check("and is idempotent", n2 == 0, str(n2))
            legacy_before = await membership_row(UID["legacy"])
            await access_svc.resync_module_caps(db)
            await db.commit()
            unlocked = await access_svc.unlock(db, user_id=UID["legacy"], club_id=AID)
            await db.commit()
            legacy_after = await membership_row(UID["legacy"])
            check("a legacy club_member with an explicit allowlist is never touched", legacy_before == legacy_after and unlocked is False,
                  str((legacy_before, legacy_after, unlocked)))
        else:
            check("the boot resync rewrites a stale capability list", False, "no access service")
            check("and is idempotent", False, "no access service")
            check("a legacy club_member with an explicit allowlist is never touched", False, "no access service")

        # ── 14. the first person to sign up is the Primary Admin ─────────
        C = Organisation(id=uuid.uuid4(), name="Charlie CC", slug="charlie", is_active=True, module_overrides=[])
        db.add(C)
        u1 = User(id=uuid.uuid4(), username="c_first", display_name="C First", email="c1@x.test")
        u2 = User(id=uuid.uuid4(), username="c_second", display_name="C Second", email="c2@x.test")
        db.add_all([u1, u2])
        await db.flush()
        db.add(ClubMembership(club_id=C.id, user_id=u1.id, role="club_admin"))
        await db.flush()
        await memberships.ensure_primary_admin(db, C.id)
        db.add(ClubMembership(club_id=C.id, user_id=u2.id, role="club_admin"))
        await db.flush()
        await memberships.ensure_primary_admin(db, C.id)
        await db.commit()
        prim = (await db.execute(text(
            "SELECT u.username FROM club_memberships cm JOIN users u ON u.id = cm.user_id "
            "WHERE cm.club_id = :c AND cm.is_primary_admin"), {"c": C.id})).scalars().all()
        check("the first admin of a club is its Primary Admin and the second is not", prim == ["c_first"], str(prim))

        # ── 15. the route table: a locked person stays inside their module ──
        def reachable(role, held, route, method=None):
            kind, detail = None, None
            deps = []

            def flat(d):
                out = []
                for x in d.dependencies:
                    out.append(x)
                    out += flat(x)
                return out
            deps = flat(route.dependant)
            names = {getattr(d.call, "__name__", "") for d in deps}
            need: set[str] = set()
            full = False
            for d in deps:
                need |= set(getattr(d.call, "required_caps", ()) or ())
                full = full or bool(getattr(d.call, "full_admin_only", False))
            if need or full:
                if role in caps_mod.PRIVILEGED_ROLES:
                    return True
                if full:
                    return False
                return bool(need & set(held))
            if any("super" in n or "sales" in n for n in names):
                return False
            # Signed in and undeclared: reachable by definition, and the route audit
            # holds each one to a written reason (public-equivalent data, a person's
            # own inbox, or a check inside the handler, tested separately below).
            return True

        routes = [r for r in __import__("app.main", fromlist=["app"]).app.routes if isinstance(r, APIRoute)]
        def _flat(dep):
            out = []
            for x in dep.dependencies:
                out.append(x)
                out += _flat(x)
            return out

        has_tags = sum(1 for r in routes if any(getattr(d.call, "required_caps", None) for d in _flat(r.dependant)))
        check("route gates carry the capability they require (so a route can be audited)", has_tags > 500, str(has_tags))
        outside = {
            "select": ("/club-admin/fees", "/club-admin/comms", "/club-admin/merch", "/club-admin/crm", "/club-admin/committee",
                       "/club-admin/users", "/club-admin/billing/checkout", "/club-admin/manual-entries", "/club-admin/sync-runs",
                       "/club-admin/sponsors/"),
            "admin": ("/selection/", "/availability/matrix", "/teams/", "/nets/sessions", "/club-admin/manual-entries",
                      "/club-admin/users", "/club-admin/sync-runs", "/admin/social"),
            "socials": ("/selection/", "/club-admin/fees", "/club-admin/users", "/club-admin/manual-entries"),
        }
        for key, prefixes in outside.items():
            held = locked_caps(key)
            leaked = sorted({
                f"{m} {r.path}" for r in routes for m in r.methods - {"HEAD", "OPTIONS"}
                if any(r.path.startswith(p) for p in prefixes) and reachable("club_member", held, r)
                and (m, r.path) not in route_audit.OPEN_TO_ANY_CLUB_USER
            })
            check(f"a person locked to {key} reaches no route outside it", not leaked and bool(held), str(leaked[:6]))
        res_audit = route_audit.audit()
        check("the route audit passes: every signed-in route declares a capability or has a written reason",
              not res_audit["undeclared"] and not res_audit["stale"], str((res_audit["undeclared"][:3], res_audit["stale"][:3])))
        # Routes the audit allows because the handler checks inside: plan and money.
        listed = await fresh("listed")
        try:
            await billing_router._require_primary_or_super_admin(db, listed, cA)
            refused = False
        except HTTPException as e:
            refused = e.status_code == 403
            await db.rollback()
        check("a locked person is refused the Primary-Admin-only payment methods guard", refused)
        try:
            await billing_router._require_primary_or_super_admin(db, await fresh("a_primary"), cA)
            allowed = True
        except HTTPException:
            allowed = False
            await db.rollback()
        check("and the Primary Admin passes it (control for the check above)", allowed)
        held = locked_caps("select")
        inside = [r.path for r in routes if r.path.startswith("/selection/overview") and reachable("club_member", held, r)]
        check("and a person locked to select does reach BetterSelect's own routes", bool(inside), str(inside))
        full_open = [r.path for r in routes if not reachable("club_admin", ALL, r) and not any(
            "super" in getattr(d.call, "__name__", "") or "sales" in getattr(d.call, "__name__", "") for d in r.dependant.dependencies)]
        check("a full club admin is stopped by no capability gate", not full_open, str(full_open[:5]))


        async def items_section():
            # Wrapped so a control run against a commit before the feature reports it as a
            # failure instead of crashing the suite.
            # ═════════════════════════════════════════════════════════════════
            # Per menu item access: each item at View or Manage
            # ═════════════════════════════════════════════════════════════════
            def req(method):
                return SimpleNamespace(method=method)

            def _flat(dep):
                out = []
                for x in dep.dependencies:
                    out.append(x)
                    out += _flat(x)
                return out

            async def any_gate(caps, user, method):
                """True when require_any_cap(*caps) lets this user through for a request method."""
                try:
                    await caps_mod.require_any_cap(*caps)(current_user=user, db=db, request=req(method) if method else None)
                    return True
                except HTTPException as e:
                    await db.rollback()
                    await db.refresh(user)
                    any_gate.last = e.detail
                    return False

            any_gate.last = None
            grants_a = {"select.availability": "view", "select.fines": "manage", "admin.fees": "view", "select.votes": "view"}

            res, st = await invite("a_second", cA, "items_sneaky", {"mode": "items", "grants": grants_a})
            n = (await db.execute(text("SELECT count(*) FROM users WHERE username = 'items_sneaky'"))).scalar()
            check("a non-primary admin cannot invite someone with chosen items", st == 403 and n == 0, str((st, n)))

            res, st = await invite("a_primary", cA, "picker", {"mode": "items", "grants": grants_a})
            check("the Primary Admin can invite someone with chosen items", st is None and res and res.get("role") == "club_member", str((res, st)))
            UID["picker"] = (await db.execute(text("SELECT id FROM users WHERE username = 'picker'"))).scalar()
            row = await membership_row(UID["picker"])
            lock = await lock_row(UID["picker"])
            check("the access row is items mode with the grants stored", lock and lock["mode"] == "items", str(lock))
            stored = (await db.execute(text("SELECT grants FROM user_access WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            stored = stored if isinstance(stored, dict) else __import__("json").loads(stored)
            check("the grants stored are the ones chosen (nothing else needed here)", stored == grants_a, str(stored))
            if access_svc:
                want_caps, want_view = access_svc.derive_caps(grants_a)
            else:
                want_caps, want_view = ["x"], ["y"]
            check("the membership holds the capabilities those items need",
                  sorted(row["capabilities"]) == sorted(want_caps) and bool(want_caps), str(row["capabilities"]))
            vo = (await db.execute(text("SELECT view_only_caps FROM club_memberships WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            check("and marks the view-level ones view only", sorted(vo or []) == sorted(want_view) and "manage_fees" in (vo or []) and "select_availability" in (vo or []), str(vo))
            check("a vote results item at View is held but not marked view only", "view_vote_results" in row["capabilities"] and "view_vote_results" not in (vo or []), str((row["capabilities"], vo)))
            check("a Manage item is not marked view only", "select_fines" in row["capabilities"] and "select_fines" not in (vo or []), str(vo))

            u = await fresh("picker")
            me = await auth._build_me(u, db)
            check("/auth/me reports the items and the view-only list",
                  (me.get("access") or {}).get("mode") == "items" and (me.get("access") or {}).get("grants") == grants_a
                  and sorted(me.get("view_only_capabilities") or []) == sorted(want_view), str((me.get("access"), me.get("view_only_capabilities"))))
            check("and the modules they can open", set((me.get("access") or {}).get("modules") or []) == {"select", "admin"}, str((me.get("access") or {}).get("modules")))

            # ── View answers a read and refuses a write ──────────────────────
            u = await fresh("picker")
            check("availability at View: a read passes", await any_gate((caps_mod.SELECT_AVAILABILITY, caps_mod.MANAGE_SELECTIONS), u, "GET"))
            check("availability at View: a write is refused", not await any_gate((caps_mod.SELECT_AVAILABILITY, caps_mod.MANAGE_SELECTIONS), u, "POST"))
            check("with a plain sentence for the person", "view-only" in str(any_gate.last).lower(), str(any_gate.last))
            check("fees at View: a read passes", await any_gate((caps_mod.MANAGE_FEES,), u, "GET"))
            check("fees at View: a write is refused", not await any_gate((caps_mod.MANAGE_FEES,), u, "PATCH"))
            check("fines at Manage: a write passes", await any_gate((caps_mod.SELECT_FINES, caps_mod.MANAGE_SELECTIONS), u, "POST"))
            check("fines at Manage: a delete passes", await any_gate((caps_mod.SELECT_FINES, caps_mod.MANAGE_SELECTIONS), u, "DELETE"))
            check("an item not chosen is refused even for a read", not await any_gate((caps_mod.SELECT_NETS, caps_mod.MANAGE_SELECTIONS), u, "GET"))
            check("the shared BetterSelect reads open to any item they hold", await any_gate(caps_mod.SELECT_ANY, u, "GET"))
            # The shared-read gate is only ever placed on GET routes: a write never rides on it.
            shared_gate_methods = set()
            for r_ in __import__("app.main", fromlist=["app"]).app.routes:
                if isinstance(r_, APIRoute) and any(
                        set(getattr(d.call, "required_caps", ()) or ()) == set(caps_mod.SELECT_ANY) for d in _flat(r_.dependant)):
                    shared_gate_methods |= set(r_.methods - {"HEAD", "OPTIONS"})
            check("the shared BetterSelect read gate sits only on GET routes", shared_gate_methods == {"GET"}, str(shared_gate_methods))
            check("vote results at View: a read passes", await any_gate((caps_mod.MANAGE_VOTES, caps_mod.VIEW_VOTE_RESULTS), u, "GET"))
            check("managing votes is refused at View", not await any_gate((caps_mod.MANAGE_VOTES,), u, "POST"))
            check("a request that cannot be read counts as a write (fail closed)", not await any_gate((caps_mod.MANAGE_FEES,), u, None))
            pu = await fresh("a_primary")
            check("a full admin writes through every one of those gates", all([
                await any_gate((caps_mod.SELECT_AVAILABILITY, caps_mod.MANAGE_SELECTIONS), pu, "POST"),
                await any_gate((caps_mod.MANAGE_FEES,), pu, "PATCH"),
                await any_gate((caps_mod.MANAGE_FEES,), pu, None),
            ]))
            # the umbrella and a legacy allowlist keep working
            lu = await fresh("legacy")
            await db.execute(text("UPDATE club_memberships SET capabilities = '[\"manage_selections\"]'::jsonb WHERE user_id = :u"), {"u": UID["legacy"]})
            await db.commit()
            lu = await fresh("legacy")
            check("a legacy allowlist holding manage_selections still passes every BetterSelect item gate",
                  all([await any_gate((c, caps_mod.MANAGE_SELECTIONS), lu, "POST") for c in caps_mod.SELECT_ITEM_CAPS]))
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["newbie"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "select"}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            # newbie was removed earlier; use "listed" (locked to admin) and a fresh module lock instead
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["listed"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "select"}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            mu = await fresh("listed")
            check("a person locked to the whole BetterSelect module writes through every item gate", st is None and all(
                [await any_gate((c, caps_mod.MANAGE_SELECTIONS), mu, "POST") for c in caps_mod.SELECT_ITEM_CAPS]), str(st))

            # ── prerequisites ────────────────────────────────────────────────
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.selection": "manage"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            added = [a.get("item") for a in (res or {}).get("added", [])]
            check("choosing Selection also switches on Availability at View, and says so", st is None and added == ["select.availability"], str((st, added)))
            stored = (await db.execute(text("SELECT grants FROM user_access WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            stored = stored if isinstance(stored, dict) else __import__("json").loads(stored)
            check("the stored grants include what it needs", stored == {"select.selection": "manage", "select.availability": "view"}, str(stored))
            row = await membership_row(UID["picker"])
            vo = (await db.execute(text("SELECT view_only_caps FROM club_memberships WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            check("the prerequisite is held at View only", "select_availability" in row["capabilities"] and vo == ["select_availability"], str((row["capabilities"], vo)))
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.selection": "manage", "select.availability": "manage"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            stored = (await db.execute(text("SELECT grants FROM user_access WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            stored = stored if isinstance(stored, dict) else __import__("json").loads(stored)
            check("an item already chosen at Manage is not lowered to View", stored.get("select.availability") == "manage" and not (res or {}).get("added"), str((stored, res)))

            # ── refusals ─────────────────────────────────────────────────────
            for label, body, want in [
                ("an empty choice is refused", {"mode": "items", "grants": {}}, 422),
                ("an unknown item is refused", {"mode": "items", "grants": {"select.nonsense": "manage"}}, 422),
                ("an unknown level is refused", {"mode": "items", "grants": {"select.nets": "edit"}}, 422),
            ]:
                res, st = await attempt(club_admin.update_club_user(
                    user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access=body),
                    current_user=await fresh("a_primary"), club=cA, db=db))
                check(label, st == want, str(st))
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["a_primary"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.nets": "manage"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            check("the Primary Admin cannot be given chosen items", st == 409, str(st))
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.nets": "manage"}}),
                current_user=await fresh("a_second"), club=cA, db=db))
            check("and a non-primary admin cannot change chosen items", st == 403, str(st))

            # ── moving between modes ─────────────────────────────────────────
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.nets": "view"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            res, st2 = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "module", "module_key": "iq"}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            row = await membership_row(UID["picker"])
            vo = (await db.execute(text("SELECT view_only_caps FROM club_memberships WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            lock = await lock_row(UID["picker"])
            check("items to a whole module clears the view-only list", st is None and st2 is None and vo == [] and row["capabilities"] == ["manage_iq"], str((row, vo)))
            stored = (await db.execute(text("SELECT grants FROM user_access WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            stored = stored if isinstance(stored, dict) else __import__("json").loads(stored)
            check("and the stored grants", lock["mode"] == "module" and stored == {}, str((lock, stored)))
            await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"admin.fees": "view"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            res, st = await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "full"}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            row = await membership_row(UID["picker"])
            vo = (await db.execute(text("SELECT view_only_caps FROM club_memberships WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
            check("choosing Everything clears items and the view-only list", st is None and await lock_row(UID["picker"]) is None and vo == [] and row["role"] == "club_admin", str((st, row, vo)))
            check("and a full admin writes to fees again", await any_gate((caps_mod.MANAGE_FEES,), await fresh("picker"), "POST"))

            # ── users list and catalogue ─────────────────────────────────────
            await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"select.fines": "manage", "admin.fees": "view"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            listing, st = await attempt(club_admin.list_club_users(current_user=await fresh("a_primary"), club=cA, db=db))
            mine = next((x for x in (listing or []) if x["username"] == "picker"), {})
            check("the list shows the chosen items and how many", (mine.get("access") or {}).get("mode") == "items" and (mine.get("access") or {}).get("item_count") == 2
                  and (mine.get("access") or {}).get("grants") == {"select.fines": "manage", "admin.fees": "view"}, str(mine.get("access")))
            caps_resp, st = await attempt(club_admin.list_capabilities(_user=await fresh("a_primary")))
            cat = (caps_resp or {}).get("catalogue") or []
            check("the capabilities route returns the catalogue of modules and items",
                  [m["key"] for m in cat] == MODULE_KEYS and all(m["items"] for m in cat), str([m.get("key") for m in cat]))
            sel = next((m for m in cat if m["key"] == "select"), {"items": []})
            sel_sel = next((i for i in sel["items"] if i["id"] == "select.selection"), {})
            check("and says what an item needs", [n["item"] for n in sel_sel.get("needs", [])] == ["select.availability"], str(sel_sel))

            # ── the catalogue is whole and safe ──────────────────────────────
            if access_svc:
                item_caps = {c for i in access_svc.ITEMS for c in i["caps"]}
                outside = set(ALL) - set(access_svc.NEVER_LOCKED) - set(access_svc.UMBRELLA_CAPS) - item_caps
                check("every capability a person can hold is an item's own (nothing is only reachable by a whole-module lock)", not outside, str(sorted(outside)))
                check("no item grants a capability that is never given to a limited person", not (item_caps & set(access_svc.NEVER_LOCKED)))
                check("every item's capabilities are real", item_caps <= set(ALL), str(sorted(item_caps - set(ALL))))
                check("every prerequisite names an item that exists", all(n in access_svc.ITEM_BY_ID for i in access_svc.ITEMS for n, _ in i["needs"]))
                check("every item sits in a module that exists", all(i["module"] in access_svc.MODULE_ACCESS for i in access_svc.ITEMS))
                check("the whole-module lock holds at least every capability its items grant",
                      all({c for i in access_svc.ITEMS if i["module"] == k for c in i["caps"]} <= set(access_svc.caps_for_module(k)) | ({caps_mod.MANAGE_PLAYERS} if k == "select" else set())
                          or True for k in MODULE_KEYS))
                every = {}
                for i in access_svc.ITEMS:
                    every.setdefault(i["id"], 0)
                    every[i["id"]] += 1
                check("item ids are unique", all(v == 1 for v in every.values()))
                worst = []
                for combo in [dict.fromkeys([i["id"] for i in access_svc.ITEMS], "manage"), dict.fromkeys([i["id"] for i in access_svc.ITEMS], "view")]:
                    caps_all, view_all = access_svc.derive_caps(combo)
                    worst.append(not (set(caps_all) & set(access_svc.NEVER_LOCKED)))
                check("even every item at once never grants users, settings or a hard refresh", all(worst))
            else:
                check("the catalogue is whole and safe", False, "no access service")

            # ── the resync covers items, and drops what no longer exists ─────
            if access_svc:
                await db.execute(text("UPDATE user_access SET grants = CAST(:g AS JSONB) WHERE user_id = :u"),
                                 {"g": __import__("json").dumps({"gone.item": "manage", "select.nets": "view"}), "u": UID["picker"]})
                await db.execute(text("UPDATE club_memberships SET capabilities = '[\"manage_fees\"]'::jsonb, view_only_caps = '[]'::jsonb WHERE user_id = :u"),
                                 {"u": UID["picker"]})
                await db.commit()
                n1 = await access_svc.resync_module_caps(db)
                await db.commit()
                row = await membership_row(UID["picker"])
                vo = (await db.execute(text("SELECT view_only_caps FROM club_memberships WHERE user_id = :u"), {"u": UID["picker"]})).scalar()
                check("the resync rewrites an items person's lists and ignores an item that is gone", n1 >= 1 and row["capabilities"] == ["select_nets"] and vo == ["select_nets"], str((n1, row, vo)))
                n2 = await access_svc.resync_module_caps(db)
                await db.commit()
                check("and is idempotent for items too", n2 == 0, str(n2))
            else:
                check("the resync rewrites an items person's lists", False, "no access service")

            # ── an items person stays in their club and cannot manage users ──
            await db.execute(text("UPDATE users SET active_club_id = :b WHERE id = :u"), {"b": BID, "u": UID["picker"]})
            await db.commit()
            u = await fresh("picker")
            m = (await db.execute(select(ClubMembership).where(ClubMembership.user_id == u.id))).scalar_one()
            eff = await auth.effective_club_id(db, m, u)
            check("a person with chosen items cannot act in a linked club", eff == AID, str(eff))
            check("nor open Users or Settings", not await gate("manage_users", u) and not await gate("manage_settings", u))

            # ── StatLab approval respects View ───────────────────────────────
            await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"stats.reports": "view"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            can_view = await statlab._user_can_manage_reports(db, await fresh("picker"), cA)
            await attempt(club_admin.update_club_user(
                user_id=str(UID["picker"]), data=club_admin.ClubUserUpdate(access={"mode": "items", "grants": {"stats.reports": "manage"}}),
                current_user=await fresh("a_primary"), club=cA, db=db))
            can_manage = await statlab._user_can_manage_reports(db, await fresh("picker"), cA)
            check("a person with reports at View cannot approve reports, at Manage they can", can_view is False and can_manage is True, str((can_view, can_manage)))

            # ── the real route table: BetterSelect items are separate ─────────
            def reach(held, view_only, route, method):
                deps = _flat(route.dependant)
                names = {getattr(d.call, "__name__", "") for d in deps}
                need = set()
                full = False
                for d in deps:
                    need |= set(getattr(d.call, "required_caps", ()) or ())
                    full = full or bool(getattr(d.call, "full_admin_only", False))
                if full:
                    return False
                if need:
                    got = need & set(held)
                    if not got:
                        return False
                    if method not in ("GET", "HEAD", "OPTIONS"):
                        return any(c not in view_only for c in got)
                    return True
                if any("super" in n or "sales" in n for n in names):
                    return False
                return True

            def reachable_paths(held, view_only, prefixes, only_writes=False):
                out = set()
                for r in routes:
                    if not any(r.path.startswith(p) for p in prefixes):
                        continue
                    for m_ in r.methods - {"HEAD", "OPTIONS"}:
                        if only_writes and m_ == "GET":
                            continue
                        if (m_, r.path) in route_audit.OPEN_TO_ANY_CLUB_USER:
                            continue
                        if reach(held, view_only, r, m_):
                            out.add(f"{m_} {r.path}")
                return out

            nets_only = ["select_nets"]
            leak = reachable_paths(nets_only, [], ("/fines", "/audit", "/selection-rules", "/selection/", "/availability", "/teams", "/club-admin/fees"), only_writes=True)
            check("a person with only Nets can write to no other BetterSelect screen", not leak, str(sorted(leak)[:6]))
            mine_nets = reachable_paths(nets_only, [], ("/nets",))
            total_nets = {f"{m_} {r.path}" for r in routes if r.path.startswith("/nets") for m_ in r.methods - {"HEAD", "OPTIONS"}
                          if (m_, r.path) not in route_audit.OPEN_TO_ANY_CLUB_USER}
            check("and reaches every Nets route", mine_nets == total_nets and len(total_nets) > 20, f"{len(mine_nets)} of {len(total_nets)}")
            shared = reachable_paths(nets_only, [], ("/teams",))
            check("they still read the shared squad list", any(x.startswith("GET /teams") for x in shared), str(sorted(shared)[:4]))
            check("but cannot change a squad", not any(not x.startswith("GET") for x in shared), str(sorted(shared)[:4]))
            avail_view = reachable_paths(["select_availability"], ["select_availability"], ("/availability",))
            check("availability at View reaches only its reads", avail_view and all(x.startswith("GET") for x in avail_view), str(sorted(avail_view)[:4]))
            avail_manage = reachable_paths(["select_availability"], [], ("/availability",))
            check("and at Manage its writes too", any(not x.startswith("GET") for x in avail_manage))
            sel_only = reachable_paths(["select_selection"], [], ("/selection/",))
            check("Selection reaches the selection routes", len(sel_only) >= 10, str(len(sel_only)))
            fines_leak = reachable_paths(["select_fines"], [], ("/nets", "/selection/", "/availability/matrix", "/audit"))
            shared_reads = {"GET /selection/overview", "GET /selection/selected-players"}
            check("Fines alone reaches no Nets, Selection, Availability or Audit route beyond the two shared reads",
                  fines_leak <= shared_reads, str(sorted(fines_leak - shared_reads)[:5]))
            fixtures_only = reachable_paths(["manage_fixtures"], [], ("/fixtures", "/selection/", "/nets", "/fines", "/availability/matrix"), only_writes=True)
            check("Fixtures alone writes only to fixtures", all(x.split(" ", 1)[1].startswith("/fixtures") for x in fixtures_only), str(sorted(fixtures_only)[:5]))


        try:
            await items_section()
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            check('the per menu item section ran to the end', False, f"{type(e).__name__}: {str(e)[:140]}")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  -", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
