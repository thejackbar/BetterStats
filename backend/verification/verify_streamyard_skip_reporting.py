"""Why a StreamYard push was skipped has to be SAID, and a skip has to be fixable.

Reported live: pressing "Push to StreamYard" answered "0 pushed, 2 skipped" and
nothing anywhere said why. Nothing was broken — StreamYard's own registration
form has firstName and lastName as separate REQUIRED fields and refuses a blank
surname (a 400, re-verified against the live endpoint), so a registrant who
typed a single word could not be pushed. The reason was recorded on the row and
shown only on a hover tooltip, and the button's own message carried a bare
count. That is the same failure this codebase already records for a disabled
Rediscover button: a figure that is correctly zero still has to explain itself.

Three things are checked here, through the SHIPPED service and route bodies:

  1. `sync_streamyard` reports the reasons alongside the counts.
  2. A skipped row is retried on the next press, so a corrected name lands.
  3. `patch_webinar_registration` can correct the name, and refuses the things
     that would separate our row from the registration StreamYard already holds.

NO LIVE CALL IS MADE. `streamyard.push_registration` is stubbed — a verification
run must never create real registrations in somebody's StreamYard account, and
their API has no public DELETE to undo one with.

Run: DATABASE_URL=... python -m verification.verify_streamyard_skip_reporting
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DB = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://postgres@/syskip?host=/tmp&port=5439"

PASS = 0
FAIL = 0
MISSING = 0


def check(label: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}\n         got  {got!r}\n         want {want!r}")


def absent(label: str, why: str) -> None:
    """A control run must REPORT a missing part, never die on the first
    AttributeError and say nothing about the checks below it."""
    global MISSING
    MISSING += 1
    print(f"  ??   {label} - {why}")


async def main() -> int:
    engine = create_async_engine(DB, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        from app.services import webinar, webinar_ddl
    except Exception as exc:  # noqa: BLE001
        print(f"the webinar service is not present: {exc}")
        return 1

    async with engine.begin() as conn:
        for statement in webinar_ddl.STATEMENTS:
            await conn.execute(text(statement))

    event = webinar.EVENT

    # ---- the fixture: one full name, two single-word names ----------------
    ids = {"full": str(uuid.uuid4()), "mono": str(uuid.uuid4()), "mono2": str(uuid.uuid4())}
    async with Session() as db:
        await db.execute(text("DELETE FROM webinar_registrations"))
        for key, name, email in (
            ("full", "Elton Baker", "full@example.test"),
            ("mono", "Elton", "mono@example.test"),
            ("mono2", "Prince", "mono2@example.test"),
        ):
            await db.execute(text("""
                INSERT INTO webinar_registrations (id, event_key, name, email, club)
                VALUES (CAST(:id AS uuid), :k, :n, :e, 'Test CC')
            """), {"id": ids[key], "k": event.key, "n": name, "e": email})
        await db.commit()

    # ---- the push is stubbed: no live call, ever --------------------------
    from app.services import streamyard

    real_push = streamyard.push_registration
    calls: list[str] = []

    async def fake_push(*, watch_url, name, email, phone=None, time_zone="Australia/Perth"):
        calls.append(email)
        # The SHIPPED split and the SHIPPED refusal rule, not a retyped copy.
        first, last = streamyard.split_name(name)
        if not first or not last:
            return {"ok": False, "id": None, "error": None,
                    "skipped": "no surname to send (their form requires one)"}
        return {"ok": True, "id": f"sy-{email}", "error": None, "skipped": None}

    streamyard.push_registration = fake_push
    try:
        print("\nThe reported run: one pushes, two are skipped")
        async with Session() as db:
            result = await webinar.sync_streamyard(db, event=event)

        check("all three rows are considered", result.get("considered"), 3)
        check("the full name is pushed", result.get("pushed"), 1)
        check("the two single-word names are skipped", result.get("skipped"), 2)
        check("nothing failed", result.get("failed"), 0)

        reasons = result.get("reasons")
        if reasons is None:
            absent("the run reports WHY", "sync_streamyard returns no `reasons`")
            absent("the reason is the missing surname", "no `reasons` to read")
        else:
            check("exactly one distinct reason is reported", len(reasons), 1)
            check("both skips are counted against it", sum(reasons.values()), 2)
            check("the reason names the missing surname",
                  "surname" in "".join(reasons.keys()), True)

        print("\nThe reason lands on the row, not only in the response")
        async with Session() as db:
            rows = (await db.execute(text("""
                SELECT name, streamyard_id, streamyard_error
                  FROM webinar_registrations ORDER BY name
            """))).mappings().all()
        by_name = {r["name"]: r for r in rows}
        check("the pushed row carries its StreamYard id",
              by_name["Elton Baker"]["streamyard_id"], "sy-full@example.test")
        check("the pushed row records no reason",
              by_name["Elton Baker"]["streamyard_error"], None)
        check("a skipped row has no id", by_name["Elton"]["streamyard_id"], None)
        check("a skipped row carries the reason",
              "surname" in (by_name["Elton"]["streamyard_error"] or ""), True)

        print("\nA second press retries only what is still missing")
        calls.clear()
        async with Session() as db:
            again = await webinar.sync_streamyard(db, event=event)
        check("the row already pushed is not considered again", again.get("considered"), 2)
        check("no request is made for it", "full@example.test" in calls, False)
        check("nobody is registered twice", again.get("pushed"), 0)
        check("the two are retried", sorted(calls),
              ["mono2@example.test", "mono@example.test"])

        # ---- correcting the name is what makes the skip fixable -----------
        print("\nCorrecting the name, through the shipped route body")
        try:
            from app.routers import club_admin
            patch = club_admin.patch_webinar_registration
            Patch = club_admin.WebinarRegistrationPatch
        except Exception as exc:  # noqa: BLE001
            absent("the name can be corrected", f"no patch route: {exc}")
            patch = Patch = None

        if patch is None:
            for label in ("a corrected name is stored", "the corrected row then pushes",
                          "a blank name is refused", "an unknown id is a 404",
                          "a malformed id is a 404", "the email is not editable"):
                absent(label, "no patch route")
        else:
            from fastapi import HTTPException

            async with Session() as db:
                out = await patch(ids["mono"], Patch(name="  Elton Rodriguez  "), None, db)
            check("the route reports the stored name", out.get("name"), "Elton Rodriguez")

            async with Session() as db:
                stored = (await db.execute(text(
                    "SELECT name FROM webinar_registrations WHERE id = CAST(:id AS uuid)"
                ), {"id": ids["mono"]})).scalar_one()
            check("the corrected name is stored trimmed", stored, "Elton Rodriguez")

            calls.clear()
            async with Session() as db:
                fixed = await webinar.sync_streamyard(db, event=event)
            check("the corrected row now pushes", fixed.get("pushed"), 1)
            check("the one still short of a surname is still skipped",
                  fixed.get("skipped"), 1)
            check("only one reason is left", len(fixed.get("reasons") or {}), 1)

            async with Session() as db:
                sid = (await db.execute(text(
                    "SELECT streamyard_id FROM webinar_registrations WHERE id = CAST(:id AS uuid)"
                ), {"id": ids["mono"]})).scalar_one()
            check("and it carries a StreamYard id now", sid, "sy-mono@example.test")

            print("\nWhat the route refuses")
            for label, name, want in (
                ("a blank name is refused", "   ", 422),
                ("an empty name is refused", "", 422),
            ):
                try:
                    async with Session() as db:
                        await patch(ids["mono2"], Patch(name=name), None, db)
                    check(label, "accepted", want)
                except HTTPException as exc:
                    check(label, exc.status_code, want)

            try:
                async with Session() as db:
                    await patch(ids["mono2"], Patch(), None, db)
                check("a body changing nothing is refused", "accepted", 422)
            except HTTPException as exc:
                check("a body changing nothing is refused", exc.status_code, 422)

            try:
                async with Session() as db:
                    await patch(str(uuid.uuid4()), Patch(name="Someone Else"), None, db)
                check("an unknown id is a 404", "accepted", 404)
            except HTTPException as exc:
                check("an unknown id is a 404", exc.status_code, 404)

            try:
                async with Session() as db:
                    await patch("not-a-uuid", Patch(name="Someone Else"), None, db)
                check("a malformed id is a 404, never a 500", "accepted", 404)
            except HTTPException as exc:
                check("a malformed id is a 404, never a 500", exc.status_code, 404)

            # The email is the identity these rows fold on AND what StreamYard's
            # own idempotency keys on, so it must not be editable here.
            check("the patch model carries no email field",
                  "email" in Patch.model_fields, False)

            async with Session() as db:
                untouched = (await db.execute(text(
                    "SELECT name, email FROM webinar_registrations WHERE id = CAST(:id AS uuid)"
                ), {"id": ids["mono2"]})).mappings().one()
            check("a refused patch leaves the row exactly as it was",
                  dict(untouched), {"name": "Prince", "email": "mono2@example.test"})

        # ---- the skip rule itself, on the shipped splitter -----------------
        print("\nThe rule a skip comes from")
        if not hasattr(streamyard, "split_name"):
            absent("the name split", "streamyard.split_name is absent")
        else:
            check("a single word yields no surname",
                  streamyard.split_name("Elton"), ("Elton", ""))
            check("two words split at the space",
                  streamyard.split_name("Elton Baker"), ("Elton", "Baker"))
            check("three words keep the surname whole",
                  streamyard.split_name("Elton van der Baker"),
                  ("Elton", "van der Baker"))
            check("a blank name yields nothing",
                  streamyard.split_name("   "), ("", ""))
    finally:
        streamyard.push_registration = real_push
        await engine.dispose()

    print(f"\n{PASS} passed, {FAIL} failed, {MISSING} missing")
    return 1 if (FAIL or MISSING) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
