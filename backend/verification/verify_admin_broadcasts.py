"""Super-admin messages on the club admin dashboard (migration 312).

Runs the SHIPPED route bodies (imported, nothing retyped) against a real
Postgres: who a message reaches, when it shows, what makes it go away, the
super admin's preview leaving no trace, and every refusal.

    python -m verification.verify_admin_broadcasts
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_admin_broadcasts",
)
os.environ["DATABASE_URL"] = DB_URL

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, ClubMembership, Organisation, User  # noqa: E402

try:
    from app.routers import admin_broadcasts as ab  # noqa: E402
    from app.services import admin_broadcast_ddl as ddl  # noqa: E402
    HAVE = True
except Exception as exc:  # pragma: no cover - control run
    print(f"!! the feature is not importable: {exc}")
    ab = ddl = None
    HAVE = False

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


NOW = lambda: dt.datetime.now(dt.timezone.utc)  # noqa: E731


async def main() -> int:
    if not HAVE:
        check("the feature exists", False, "import failed")
        return 1

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for _ in range(3):
            for st in ddl.STATEMENTS:
                await conn.execute(text(st))
    check("the DDL applies three times over", True)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        def club(label, archived=False):
            return Organisation(id=uuid.uuid4(), name=f"{label} CC", slug=label.lower(),
                                archived_at=NOW() if archived else None)

        A, B, C = club("Alpha"), club("Bravo"), club("Charlie", archived=True)
        db.add_all([A, B, C])
        await db.flush()

        people = {}

        def person(key, org, role, primary=False, active=None):
            u = User(id=uuid.uuid4(), username=key, display_name=key.title(),
                     email=f"{key}@x.test", active_club_id=active)
            db.add(u)
            people[key] = (u, org, role, primary)
            return u

        person("a_primary", A, "club_admin", True)
        person("a_admin", A, "club_admin")
        person("a_member", A, "club_member")
        person("b_primary", B, "club_admin", True)
        person("c_admin", C, "club_admin", True)
        person("staff", A, "super_admin", active=A.id)
        await db.flush()
        for key, (u, org, role, primary) in people.items():
            db.add(ClubMembership(club_id=org.id, user_id=u.id, role=role, is_primary_admin=primary))
        await db.commit()

        def U(k):
            return people[k][0]

        def O(k):
            return people[k][1]

        staff = U("staff")

        async def sees(key):
            res = await ab.my_broadcasts(user=U(key), club=O(key), db=db)
            return {i["message"] for i in res["items"]}, res

        async def make(**kw):
            kw.setdefault("message", "hello")
            return await ab.create_broadcast(ab.BroadcastIn(**kw), user=staff, db=db)

        async def refused(coro, status=422):
            try:
                await coro
            except HTTPException as e:
                return e.status_code == status
            return False

        # ── audience ─────────────────────────────────────────────────────
        m_all = await make(message="to everyone")
        m_b = await make(message="to bravo", audience="clubs", org_ids=[str(B.id)])
        m_primary = await make(message="to primaries", audience_roles="primary")
        m_admins = await make(message="to club admins", audience_roles="club_admins")
        m_user = await make(message="to the member", audience="users", user_ids=[str(U("a_member").id)])

        s_ap, _ = await sees("a_primary")
        s_aa, _ = await sees("a_admin")
        s_am, _ = await sees("a_member")
        s_bp, _ = await sees("b_primary")
        check("every club reaches every admin-app user",
              all("to everyone" in s for s in (s_ap, s_aa, s_am, s_bp)))
        check("a chosen club reaches only that club", "to bravo" in s_bp and "to bravo" not in s_ap)
        check("primary-only reaches only primary admins",
              "to primaries" in s_ap and "to primaries" in s_bp and "to primaries" not in s_aa
              and "to primaries" not in s_am)
        check("club-admins-only leaves the club member out",
              "to club admins" in s_aa and "to club admins" not in s_am)
        check("a named user reaches only that user",
              "to the member" in s_am and "to the member" not in s_aa and "to the member" not in s_bp)

        lst = {i["message"]: i for i in (await ab.list_broadcasts(_=staff, db=db))["items"]}
        check("the reach excludes the archived club (4 people at 2 clubs)",
              lst["to everyone"]["recipients"] == 4 and lst["to everyone"]["clubs"] == 2,
              f"{lst['to everyone']['recipients']} / {lst['to everyone']['clubs']}")
        check("primary-only counts two", lst["to primaries"]["recipients"] == 2)
        check("the named user is named in the list", lst["to the member"]["user_names"] == ["A_Member"],
              str(lst["to the member"]["user_names"]))
        check("the chosen club is named", lst["to bravo"]["club_names"] == ["Bravo CC"])
        for m in (m_all, m_b, m_primary, m_admins, m_user):
            await ab.delete_broadcast(m["id"], _=staff, db=db)

        # ── until cleared ────────────────────────────────────────────────
        keep = await make(message="stays")
        check("an until-cleared message is not dismissible",
              await refused(ab.dismiss(keep["id"], user=U("a_admin"), club=A, db=db), 409))
        await ab.mark_seen(ab.SeenBody(ids=[keep["id"]]), user=U("a_admin"), club=A, db=db)
        check("seeing it does not remove it", "stays" in (await sees("a_admin"))[0])
        await ab.clear_broadcast(keep["id"], user=staff, db=db)
        check("clearing it removes it everywhere",
              "stays" not in (await sees("a_admin"))[0] and "stays" not in (await sees("b_primary"))[0])
        st = (await ab.restore_broadcast(keep["id"], _=staff, db=db))["status"]
        check("restoring it brings it back", "stays" in (await sees("a_admin"))[0] and st == "live", st)
        await ab.delete_broadcast(keep["id"], _=staff, db=db)

        # ── dismissible ──────────────────────────────────────────────────
        dm = await make(message="dismiss me", persistence="dismissible")
        r = await ab.dismiss(dm["id"], user=U("a_admin"), club=A, db=db)
        check("a recipient can dismiss it", r["dismissed"] is True)
        check("dismissed for that user", "dismiss me" not in (await sees("a_admin"))[0])
        check("still there for everyone else", "dismiss me" in (await sees("a_primary"))[0])
        check("dismissing a message you can no longer see is a 404",
              await refused(ab.dismiss(dm["id"], user=U("a_admin"), club=A, db=db), 404))
        await ab.delete_broadcast(dm["id"], _=staff, db=db)

        # ── view once each ───────────────────────────────────────────────
        vo = await make(message="once each", persistence="view_once_user")
        before, _ = await sees("a_admin")
        await ab.mark_seen(ab.SeenBody(ids=[vo["id"]]), user=U("a_admin"), club=A, db=db)
        after, _ = await sees("a_admin")
        check("view-once shows on the first view", "once each" in before)
        check("and not on the next", "once each" not in after)
        check("another admin still gets their one view", "once each" in (await sees("a_primary"))[0])

        # super admin preview leaves no trace
        prev, raw = await sees("staff")
        check("a super admin acting as the club sees it as a preview",
              "once each" in prev and raw["preview"] is True)
        rec = await ab.mark_seen(ab.SeenBody(ids=[vo["id"]]), user=staff, club=A, db=db)
        check("and records nothing", rec["recorded"] == 0)
        n = (await db.execute(text("SELECT COUNT(*) FROM admin_broadcast_receipts WHERE user_id = :u"),
                              {"u": staff.id})).scalar()
        check("no receipt for staff", n == 0)
        pd = await ab.dismiss(vo["id"], user=staff, club=A, db=db)
        check("a staff dismissal is screen-only", pd.get("preview") is True and pd["dismissed"] is False)
        check("the member still gets their view after the preview", "once each" in (await sees("a_member"))[0])

        lst = {i["message"]: i for i in (await ab.list_broadcasts(_=staff, db=db))["items"]}
        check("the list counts one view", lst["once each"]["seen"] == 1, str(lst["once each"]["seen"]))
        recips = (await ab.broadcast_recipients(vo["id"], _=staff, db=db))["items"]
        seen_by = {i["name"] for i in recips if i["seen_at"]}
        check("recipients show who has seen it", seen_by == {"A_Admin"} and len(recips) == 4,
              f"{seen_by} / {len(recips)}")
        for k in ("a_primary", "a_member", "b_primary"):
            await ab.mark_seen(ab.SeenBody(ids=[vo["id"]]), user=U(k), club=O(k), db=db)
        lst = {i["message"]: i for i in (await ab.list_broadcasts(_=staff, db=db))["items"]}
        check("once everybody has seen it, it reads complete", lst["once each"]["status"] == "complete",
              lst["once each"]["status"])
        await ab.reset_views(vo["id"], _=staff, db=db)
        check("resetting views shows it again", "once each" in (await sees("a_admin"))[0])
        await ab.delete_broadcast(vo["id"], _=staff, db=db)

        # ── view once per club ───────────────────────────────────────────
        vc = await make(message="once per club", persistence="view_once_club")
        await ab.mark_seen(ab.SeenBody(ids=[vc["id"]]), user=U("a_member"), club=A, db=db)
        check("one view at the club clears it for the whole club",
              "once per club" not in (await sees("a_primary"))[0])
        check("another club still sees it", "once per club" in (await sees("b_primary"))[0])
        await ab.delete_broadcast(vc["id"], _=staff, db=db)

        # ── time ─────────────────────────────────────────────────────────
        later = await make(message="later", starts_at=NOW() + dt.timedelta(days=1))
        check("a scheduled message does not show yet", "later" not in (await sees("a_admin"))[0])
        check("and reads scheduled", later["status"] == "scheduled")
        timed = await make(message="timed", expires_at=NOW() + dt.timedelta(hours=1))
        check("a message with an expiry shows until it expires", "timed" in (await sees("a_admin"))[0])
        await db.execute(text("UPDATE admin_broadcasts SET starts_at = NOW() - interval '2 hours', "
                              "expires_at = NOW() - interval '1 minute' WHERE id = CAST(:i AS uuid)"),
                         {"i": timed["id"]})
        await db.commit()
        check("and not after", "timed" not in (await sees("a_admin"))[0])
        lst = {i["message"]: i for i in (await ab.list_broadcasts(_=staff, db=db))["items"]}
        check("it reads expired", lst["timed"]["status"] == "expired")
        cleared_exp = await ab.update_broadcast(timed["id"], ab.BroadcastIn(expires_at=None), _=staff, db=db)
        check("clearing the expiry puts it back", "timed" in (await sees("a_admin"))[0]
              and cleared_exp["expires_at"] is None)
        edited = await ab.update_broadcast(timed["id"], ab.BroadcastIn(message="timed, edited"), _=staff, db=db)
        check("an edit changes only what was sent", edited["message"] == "timed, edited"
              and edited["audience"] == "all" and edited["persistence"] == "until_cleared")
        await ab.delete_broadcast(timed["id"], _=staff, db=db)
        await ab.delete_broadcast(later["id"], _=staff, db=db)

        # ── link, tone, order ────────────────────────────────────────────
        await make(message="info one", tone="info")
        await make(message="critical one", tone="critical", link_url="/admin/account", link_label="Plans")
        items = (await ab.my_broadcasts(user=U("a_admin"), club=A, db=db))["items"]
        check("the most urgent message comes first", items[0]["message"] == "critical one",
              str([i["message"] for i in items]))
        check("the link rides along", items[0]["link_url"] == "/admin/account" and items[0]["link_label"] == "Plans")
        rec = await ab.mark_seen(ab.SeenBody(ids=[str(uuid.uuid4())]), user=U("a_admin"), club=A, db=db)
        check("an id the user cannot see records nothing", rec["recorded"] == 0)

        # ── refusals ─────────────────────────────────────────────────────
        refusals = [
            ("an empty message", dict(message="   ")),
            ("an over-long message", dict(message="x" * 501)),
            ("an unknown tone", dict(tone="loud")),
            ("a link that is not http or a path", dict(link_url="javascript:alert(1)")),
            ("a label with no link", dict(link_label="Go")),
            ("clubs with none picked", dict(audience="clubs")),
            ("an archived club", dict(audience="clubs", org_ids=[str(C.id)])),
            ("an unknown club id", dict(audience="clubs", org_ids=[str(uuid.uuid4())])),
            ("users with none picked", dict(audience="users")),
            ("a super admin as a named user", dict(audience="users", user_ids=[str(staff.id)])),
            ("a junk id", dict(audience="users", user_ids=["nope"])),
            ("an expiry before the start", dict(expires_at=NOW() - dt.timedelta(days=1))),
            ("an unknown rule", dict(persistence="forever-ish")),
        ]
        for label, kw in refusals:
            check(f"refuses {label}", await refused(make(**kw)))

        # ── downgrade ────────────────────────────────────────────────────
    async with engine.begin() as conn:
        for st in ddl.DOWNGRADE:
            await conn.execute(text(st))
        gone = (await conn.execute(text("SELECT to_regclass('admin_broadcasts')"))).scalar()
    check("the downgrade drops both tables", gone is None)
    await engine.dispose()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
