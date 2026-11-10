"""Club block list: a blocked club cannot register, sign in or keep a session.

Real Postgres, the shipped service and the shipped route bodies
(`self_serve_trial.prepare_club` / `send_verification_code` / `submit`,
`auth.get_current_user`). Nothing external is called: the Cricket Australia
lookup and the email send are replaced by stubs, and each stub is also the proof
that an UNBLOCKED request still gets through (a check that "X is refused" is
paired with one that X could have been let through).

    DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/verify_block \
        python -m verification.verify_club_block

Control run: against the commit before this change the same file must FAIL on
exactly the blocked cases (the service module does not exist there, so every
read of it is presence-safe and reports absence rather than crashing).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:pw@127.0.0.1:5432/verify_block")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.models.db import async_session_maker, engine  # noqa: E402
from app.routers import auth  # noqa: E402
from app.routers import self_serve_trial as sst  # noqa: E402
from app.services import playhq_client, rate_limit  # noqa: E402

try:  # presence-safe: the control commit has neither of these
    from app.services import registration_blocks as rb  # noqa: E402
    from app.services.registration_block_ddl import STATEMENTS as DDL  # noqa: E402
except Exception:  # pragma: no cover
    rb, DDL = None, []

PASS = FAIL = 0


def check(label: str, ok: bool, extra: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {extra}")


async def status_of(coro) -> tuple[int | None, str]:
    """(HTTP status or None when it returned normally, detail text)."""
    try:
        await coro
        return None, ""
    except HTTPException as e:
        return e.status_code, str(e.detail)


def request_with_cookie(token: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(b"cookie", f"{auth.COOKIE_NAME}={token}".encode())],
    })


async def main() -> int:
    blocked_org = uuid.uuid4()
    other_org = uuid.uuid4()
    ca_blocked = str(uuid.uuid4())
    ca_ok = str(uuid.uuid4())
    u_blocked, u_super, u_other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async with engine.begin() as c:
        for stmt in DDL:
            await c.execute(text(stmt))
        await c.execute(text("DELETE FROM club_memberships"))
        await c.execute(text("DELETE FROM users"))
        await c.execute(text("DELETE FROM organisations"))
        for oid, nm, slug in ((blocked_org, "Seed One Cricket Club", "sm"),
                              (other_org, "Seed Two Cricket Club", "ac")):
            await c.execute(text(
                "INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, TRUE)"),
                {"i": oid, "n": nm, "s": slug})
        for uid, un in ((u_blocked, "blocked_admin"), (u_super, "super"), (u_other, "other_admin")):
            await c.execute(text("INSERT INTO users (id, username, failed_login_count) VALUES (:i, :u, 0)"), {"i": uid, "u": un})
        for uid, oid, role in ((u_blocked, blocked_org, "club_admin"),
                               (u_super, blocked_org, "super_admin"),
                               (u_other, other_org, "club_admin")):
            await c.execute(text(
                "INSERT INTO club_memberships (id, club_id, user_id, role) VALUES (gen_random_uuid(), :c, :u, :r)"),
                {"c": oid, "u": uid, "r": role})
        if rb is not None:
            await c.execute(text("DELETE FROM registration_blocks"))

    # Stubs for the two outside calls, so an unblocked request has somewhere to go.
    calls = {"ca": 0, "mail": 0}

    async def fake_get_org(_id):
        calls["ca"] += 1
        return None  # unblocked prepare ends in the 404 "not found in CA"

    async def fake_start(_db, _email):
        calls["mail"] += 1

    playhq_client.get_organisation = fake_get_org
    sst.verification.start_verification = fake_start
    rate_limit.enforce = lambda *a, **k: None

    def prepare(org_id, name):
        async def run():
            async with async_session_maker() as db:
                return await sst.prepare_club(sst.PrepareClubRequest(org_id=str(org_id), name=name), db)
        return status_of(run())

    def send(email):
        async def run():
            async with async_session_maker() as db:
                return await sst.send_verification_code(sst.SendCodeRequest(email=email), db)
        return status_of(run())

    def submit(org_id, name, email):
        async def run():
            async with async_session_maker() as db:
                bt = type("BT", (), {"add_task": lambda *a, **k: None})()
                return await sst.submit(sst.SubmitRequest(
                    idempotency_key=str(uuid.uuid4()), org_id=str(org_id), name=name, email=email,
                    first_name="A", last_name="B", display_name="A B", username="ab",
                    mobile_number="0400000000", password="x", confirm_password="x"), bt, db)
        return status_of(run())

    def whoami(user_id):
        token = auth.create_session_token(str(user_id))

        async def run():
            async with async_session_maker() as db:
                return await auth.get_current_user(request_with_cookie(token), db)
        return status_of(run())

    # ── Before any block: everything passes the gate (the "could be present" half).
    print("before the block")
    st, _ = await prepare(ca_blocked, "Subiaco Marist Cricket Club")
    check("an unblocked prepare reaches the Cricket Australia lookup (404, not 403)", st == 404, f"got {st}")
    st, _ = await send("a@example.com")
    check("an unblocked email gets its code", st is None and calls["mail"] == 1, f"got {st}")
    st, _ = await whoami(u_blocked)
    check("a member of the club-to-be-blocked has a working session", st is None, f"got {st}")

    # ── Add the blocks, the way the script does (through the shipped service).
    if rb is not None:
        async with async_session_maker() as db:
            for kind, val in (("org_id", str(blocked_org)), ("ca_org_id", ca_blocked.upper()),
                              ("club_name", "Subiaco-Marist CC"), ("email_domain", "@Rival.example")):
                await db.execute(text(
                    "INSERT INTO registration_blocks (kind, value, reason, created_by) VALUES (:k, :v, 'test', 'test')"),
                    {"k": kind, "v": rb.normalise_value(kind, val)})
            await db.commit()
        rb.invalidate_cache()

    print("after the block")
    for label, coro in (
        ("prepare by Cricket Australia id", prepare(ca_blocked, "Anything At All")),
        ("prepare by name, another spelling", prepare(ca_ok, "SUBIACO MARIST cricket club")),
        ("prepare by name, punctuation and abbreviation", prepare(ca_ok, "Subiaco-Marist C.C.")),
        ("send a code to an address at the blocked domain", send("Owner@RIVAL.example")),
        ("submit by id", submit(ca_blocked, "X", "z@example.com")),
        ("submit by name", submit(ca_ok, "Subiaco Marist Cricket Club", "z@example.com")),
        ("submit by email domain", submit(ca_ok, "Some Club", "z@rival.example")),
    ):
        st, detail = await coro
        check(f"{label} is refused with 403", st == 403, f"got {st} {detail!r}")
        check(f"{label}: the refusal gives no reason",
              st == 403 and "rival" not in detail.lower() and "compet" not in detail.lower() and "block" not in detail.lower(),
              detail)

    st, _ = await prepare(ca_ok, "Unrelated Cricket Club")
    check("an unrelated club still passes the gate", st == 404, f"got {st}")
    st, _ = await send("fine@example.com")
    check("an unrelated email still gets its code", st is None, f"got {st}")

    st, _ = await whoami(u_blocked)
    check("a member of the blocked club loses an open session (401)", st == 401, f"got {st}")
    st, _ = await whoami(u_super)
    check("a super admin in that club is never blocked", st is None, f"got {st}")
    st, _ = await whoami(u_other)
    check("a member of another club is untouched", st is None, f"got {st}")

    # ── Lifting: a lifted block stops counting, and the row stays.
    if rb is not None:
        async with async_session_maker() as db:
            await db.execute(text("UPDATE registration_blocks SET lifted_at = NOW()"))
            await db.commit()
            kept = (await db.execute(text("SELECT count(*) FROM registration_blocks"))).scalar()
        rb.invalidate_cache()
        check("lifting keeps the rows", kept == 4, f"kept {kept}")
        st, _ = await prepare(ca_blocked, "Subiaco Marist Cricket Club")
        check("after lifting, prepare passes the gate again", st == 404, f"got {st}")
        st, _ = await whoami(u_blocked)
        check("after lifting, the member's session works again", st is None, f"got {st}")
    else:
        check("the block list exists in this commit", False, "(control: service module absent)")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
