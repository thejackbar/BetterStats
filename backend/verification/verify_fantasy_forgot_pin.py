"""Verification for the Fantasy "Forgot your PIN?" email, against a real Postgres.

Request: a manager who has forgotten their PIN can ask for it by email.

The PIN is stored as a bcrypt hash, so the PIN they chose cannot be read back. The
shipped route makes a NEW 6 digit PIN, emails it, and only then saves it.

Runs the SHIPPED `routers/public_fantasy.forgot_pin` and `login` route bodies and the
shipped `services/fantasy_pin_email` over a real database. Only the outbound provider
is stubbed (`email_service.get_email_provider`), so the real `_deliver` runs and the
console provider is checked for what it is: not a send.

CONTROL (`--control`): the public router at git HEAD. It must fail on the missing route,
read through a presence-safe accessor.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/tmp/pg_fantasy_check/sock \
      python verification/verify_fantasy_forgot_pin.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException, Response
from starlette.requests import Request
from sqlalchemy import text

import verify_fantasy_unsettle as base          # same seed: club ORG, managers X and Y
from app.models.db import Organisation
from app.routers import public_fantasy as pub
from app.services import email_service, fantasy_pin_email, rate_limit

Session, check, ORG, MGR_X, MGR_Y = base.Session, base.check, base.ORG, base.MGR_X, base.MGR_Y
REPO = Path(__file__).resolve().parent.parent.parent
TOKEN = "tok-forgot-pin"
X_EMAIL = "xavier@example.com"
OLD_PIN = "4321"


def req(ip="1.2.3.4") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/public/fantasy/x", "headers": [],
                    "query_string": b"", "server": ("t", 80), "client": (ip, 1), "scheme": "http"})


class FakeProvider:
    """Stands in for the live provider; records what would have gone out."""
    name = "fake"

    def __init__(self, ok=True):
        self.ok = ok
        self.sent: list[email_service.EmailMessage] = []

    async def send(self, msg):
        self.sent.append(msg)
        return email_service.SendResult(ok=self.ok, message_id="m1" if self.ok else None,
                                        error=None if self.ok else "provider said no")


async def hash_of(mid) -> str:
    async with Session() as s:
        return (await s.execute(text("SELECT credential_hash FROM fantasy_managers WHERE id=:i"), {"i": mid})).scalar()


async def post(email, ip="1.2.3.4"):
    async with Session() as s:
        return await pub.forgot_pin(TOKEN, pub.ForgotPinBody(email=email), req(ip), s)


async def status_of(email, ip="1.2.3.4"):
    try:
        return 200, await post(email, ip)
    except HTTPException as e:
        return e.status_code, e.detail


async def try_login(email, pin) -> bool:
    try:
        async with Session() as s:
            await pub.login(TOKEN, pub.LoginBody(email=email, pin=pin), req(), Response(), s)
        return True
    except HTTPException:
        return False


async def checks() -> None:
    pub.org_has_module = lambda *a, **k: True        # entitlement is not under test
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        org.fantasy_link_token = TOKEN
        await s.execute(text("UPDATE fantasy_managers SET email=:e, credential_hash=:h WHERE id=:i"),
                        {"e": X_EMAIL, "h": pub._hash_pin(OLD_PIN), "i": MGR_X})
        await s.commit()

    check("setup: the old PIN signs X in", await try_login(X_EMAIL, OLD_PIN))

    print("1. No live email provider (the console provider is not a send)")
    email_service.get_email_provider = lambda: email_service.ConsoleEmailProvider()
    before = await hash_of(MGR_X)
    code, detail = await status_of(X_EMAIL)
    check("a registered address is refused with a readable reason", code == 503 and "Email isn't set up" in str(detail), f"{code} {detail}")
    code2, detail2 = await status_of("nobody@example.com")
    check("an unknown address gets the same refusal, so nothing leaks", (code2, detail2) == (code, detail), f"{code2} {detail2}")
    check("X's PIN is untouched", await hash_of(MGR_X) == before and await try_login(X_EMAIL, OLD_PIN))
    res = await fantasy_pin_email.send_new_pin_email(email=X_EMAIL, display_name="Xavier", game_name="Alpha Fantasy", pin="111111", link="x")
    check("the console provider reads as a failed send", res.ok is False, repr(res))

    print("2. A registered address gets a new PIN")
    rate_limit._limiter._buckets.clear()
    live = FakeProvider()
    email_service.get_email_provider = lambda: live
    email_service.email_is_live = lambda: True
    code, out = await status_of(X_EMAIL)
    check("the reply is the generic one", code == 200 and out == {"status": "sent"}, f"{code} {out}")
    check("one email went to X", len(live.sent) == 1 and live.sent[0].to_email == X_EMAIL, repr([m.to_email for m in live.sent]))
    body = live.sent[0].text if live.sent else ""
    m = re.search(r"new PIN is (\d{6})", body)
    new_pin = m.group(1) if m else ""
    check("the email holds a 6 digit PIN", bool(new_pin), body[:120])
    check("the PIN is not in the subject", new_pin not in (live.sent[0].subject if live.sent else ""), "")
    check("the old PIN no longer signs X in", not await try_login(X_EMAIL, OLD_PIN))
    check("the emailed PIN signs X in", bool(new_pin) and await try_login(X_EMAIL, new_pin))
    check("the email names the club's game and links to the sign in page",
          bool(live.sent) and "Alpha CC Fantasy Cricket" in live.sent[0].subject + live.sent[0].text and f"/fantasy/{TOKEN}" in live.sent[0].text,
          live.sent[0].subject if live.sent else "")
    other = await hash_of(MGR_Y)
    check("another manager is untouched", other is None, repr(other))

    print("3. An address with no team here")
    rate_limit._limiter._buckets.clear()
    n = len(live.sent)
    code, out = await status_of("nobody@example.com")
    check("gets the same generic reply", code == 200 and out == {"status": "sent"}, f"{code} {out}")
    check("and nothing is emailed", len(live.sent) == n, str(len(live.sent) - n))
    check("an upper case, padded address still finds X", (await status_of(f"  {X_EMAIL.upper()} "))[0] == 200 and len(live.sent) == n + 1)

    print("4. The email fails to go")
    rate_limit._limiter._buckets.clear()
    cur = await hash_of(MGR_X)
    failing = FakeProvider(ok=False)
    email_service.get_email_provider = lambda: failing
    code, detail = await status_of(X_EMAIL)
    check("the manager is told it did not send", code == 502 and "hasn't changed" in str(detail), f"{code} {detail}")
    check("the stored PIN is not replaced", await hash_of(MGR_X) == cur)

    print("5. Limits and input")
    rate_limit._limiter._buckets.clear()
    email_service.get_email_provider = lambda: live
    codes = [(await status_of(X_EMAIL, ip=f"9.9.9.{i}"))[0] for i in range(4)]
    check("a 4th request for one address inside the hour is refused", codes == [200, 200, 200, 429], str(codes))
    rate_limit._limiter._buckets.clear()
    codes = [(await status_of(f"u{i}@example.com", ip="8.8.8.8"))[0] for i in range(11)]
    check("an 11th request from one IP inside the hour is refused", codes[:10] == [200] * 10 and codes[10] == 429, str(codes))
    code, _ = await status_of("   ")
    check("a blank email is refused", code == 400, str(code))

    print("6. Wrong-PIN lockout does not outlast the new PIN")
    rate_limit._limiter._buckets.clear()
    for _ in range(pub.LOGIN_MAX_FAILURES):
        await try_login(X_EMAIL, "000000")
    check("six wrong PINs lock the sign in", not await try_login(X_EMAIL, "000000"))
    await status_of(X_EMAIL)
    new_pin = re.search(r"new PIN is (\d{6})", live.sent[-1].text).group(1)
    check("after a new PIN the same person is let in", await try_login(X_EMAIL, new_pin))


async def run_control() -> int:
    src = subprocess.check_output(["git", "show", "HEAD:backend/app/routers/public_fantasy.py"], cwd=REPO, text=True)
    tmp = Path(__file__).resolve().parent / "_public_fantasy_control.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("public_fantasy_control", tmp)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        check("HEAD has a forgot-PIN route", getattr(old, "forgot_pin", None) is not None, "no forgot_pin in the public router")
        paths = {getattr(r, "path", "") for r in old.router.routes}
        check("HEAD serves /{token}/forgot-pin", "/public/fantasy/{token}/forgot-pin" in paths, "route not registered")
    finally:
        tmp.unlink(missing_ok=True)
    return base.FAIL


async def main() -> int:
    await base.build_schema()
    await base.seed()
    if "--control" in sys.argv:
        return await run_control()
    await checks()
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
