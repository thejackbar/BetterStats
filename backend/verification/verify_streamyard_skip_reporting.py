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

    # ---- migration 301 over a table that already has rows in it ----------
    # Built in RAW SQL without the two columns, because the shipped list would
    # create them — a pre-301 table has to be a pre-301 table for the ALTERs to
    # have anything to do.
    print("Migration 301 over a populated pre-301 table")
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS webinar_registrations"))
        await conn.execute(text("""
            CREATE TABLE webinar_registrations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                event_key TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
                club TEXT NOT NULL, phone TEXT, role TEXT,
                utm_source TEXT, utm_medium TEXT, utm_campaign TEXT,
                utm_content TEXT, utm_term TEXT, click_id TEXT, click_source TEXT,
                attribution JSONB, referrer TEXT, landing_path TEXT,
                visitor_id TEXT, user_agent TEXT,
                email_sent BOOLEAN NOT NULL DEFAULT FALSE, email_error TEXT,
                reminder_sent_at TIMESTAMPTZ, reminder_error TEXT,
                streamyard_id TEXT, streamyard_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            INSERT INTO webinar_registrations (event_key, name, email, club)
            VALUES ('legacy', 'Already Here', 'already@example.test', 'Old CC')
        """))
        # Three times, because the lifespan re-runs the whole list on every boot.
        for _ in range(3):
            for statement in webinar_ddl.STATEMENTS:
                await conn.execute(text(statement))
        cols = (await conn.execute(text("""
            SELECT column_name, is_nullable FROM information_schema.columns
             WHERE table_name = 'webinar_registrations'
               AND column_name IN ('first_name', 'last_name')
             ORDER BY column_name
        """))).all()
        # Presence-checked, or a control build without the columns dies here
        # and says nothing about the sixty checks below it.
        has_halves = len(cols) == 2
        kept = (await conn.execute(text(
            "SELECT name" + (", first_name, last_name" if has_halves else "")
            + " FROM webinar_registrations"
        ))).mappings().all()

    check("both columns are added", [c[0] for c in cols], ["first_name", "last_name"])
    check("both are nullable, so a pre-301 row reads as having only one string",
          sorted({c[1] for c in cols}), ["YES"])
    check("the row that was already there survives", len(kept), 1)
    check("with its whole name untouched", kept[0]["name"], "Already Here")
    if has_halves:
        check("and no invented halves",
              (kept[0]["first_name"], kept[0]["last_name"]), (None, None))
    else:
        absent("and no invented halves", "the two columns are absent")

    # The downgrade drops the two COLUMNS, never the table — 296 owns that, and
    # copying its downgrade would destroy every registration over two columns.
    import pathlib
    mig = pathlib.Path(__file__).resolve().parents[1] / "alembic/versions/301_webinar_name_halves.py"
    if not mig.exists():
        absent("the downgrade drops the columns, not the table", "migration 301 is absent")
    else:
        body = mig.read_text()
        after = body.split("def downgrade")[-1]
        check("the downgrade drops first_name", "DROP COLUMN IF EXISTS first_name" in after, True)
        check("the downgrade drops last_name", "DROP COLUMN IF EXISTS last_name" in after, True)
        check("and never the table", "DROP TABLE" in after, False)

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
    sent: list[tuple] = []

    # ONE stub, used by every section, so it cannot disagree with itself about
    # what reaches StreamYard. It mirrors the SHIPPED precedence — the stored
    # halves first, the split only as a fallback — and the SHIPPED refusal (a
    # blank surname is a 400 at their end, re-verified live), rather than
    # retyping either rule.
    async def fake_push(*, watch_url, name, email, phone=None,
                        first_name=None, last_name=None,
                        time_zone="Australia/Perth"):
        calls.append(email)
        sent.append((name, first_name, last_name, phone))
        # The shipped rule when it exists, its predecessor when it does not —
        # the stub must work against a control build too, or the run dies here
        # and reports nothing.
        resolve = getattr(streamyard, "resolve_push_name", None)
        if resolve is not None:
            first, last = resolve(name, first_name, last_name)
        else:
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
                fixed_row = (await db.execute(text(
                    "SELECT streamyard_id"
                    + (", first_name, last_name" if has_halves else "")
                    + "  FROM webinar_registrations WHERE id = CAST(:id AS uuid)"
                ), {"id": ids["mono"]})).mappings().one()
            check("and it carries a StreamYard id now",
                  fixed_row["streamyard_id"], "sy-mono@example.test")
            # The halves have to move with a correction, or the row would keep
            # pushing the old name — `push_to_streamyard` prefers them.
            if has_halves:
                check("the correction sets the halves too",
                      (fixed_row["first_name"], fixed_row["last_name"]),
                      ("Elton", "Rodriguez"))
            else:
                absent("the correction sets the halves too",
                       "the two columns are absent")

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

        # ---- the form asks for both halves, so nothing has to be guessed ---
        print("\nThe form asks for both halves (migration 301)")
        if not (hasattr(webinar, "resolve_name") and has_halves
                and hasattr(streamyard, "resolve_push_name")):
            for label in ("both halves are kept", "the whole name is joined from them",
                          "one half alone is not a pair", "a bare name still registers",
                          "the halves reach the row", "a resubmission keeps a stored pair",
                          "a two-word first name survives", "the split is only a fallback"):
                absent(label, "the two-half name is not present")
        else:
            check("both halves are kept",
                  webinar.resolve_name(name="", first_name="Mary Jane", last_name="Smith"),
                  ("Mary Jane Smith", "Mary Jane", "Smith"))
            check("the whole name is joined from them",
                  webinar.resolve_name(name="ignored", first_name="Elton", last_name="Baker")[0],
                  "Elton Baker")
            check("surrounding space is trimmed off each",
                  webinar.resolve_name(name="", first_name="  Elton ", last_name=" Baker  "),
                  ("Elton Baker", "Elton", "Baker"))
            # A surname box left empty IS the mononym case and has to read as
            # one — storing a half as though it were a pair would push a blank
            # surname, which their API refuses outright.
            check("a first name alone is not a pair",
                  webinar.resolve_name(name="", first_name="Prince", last_name=""),
                  ("Prince", None, None))
            check("a surname alone is not a pair",
                  webinar.resolve_name(name="", first_name="", last_name="Prince"),
                  ("Prince", None, None))
            # A browser served an older bundle mid-deploy posts one field.
            check("a bare name still registers, with no guessed pair",
                  webinar.resolve_name(name="Elton Baker", first_name="", last_name=""),
                  ("Elton Baker", None, None))
            check("and a bare single word still registers",
                  webinar.resolve_name(name="Prince", first_name=None, last_name=None),
                  ("Prince", None, None))

            print("\nThe halves reach the row, and the push uses them")
            async with Session() as db:
                await db.execute(text("DELETE FROM webinar_registrations"))
                await db.commit()
                out = await webinar.register(
                    db, name="", first_name="Mary Jane", last_name="Smith",
                    email="halves@example.test", club="Test CC",
                    phone="0412 345 678", event=event)
            check("a two-field registration is created", out.get("created"), True)

            async with Session() as db:
                stored = (await db.execute(text("""
                    SELECT name, first_name, last_name, phone
                      FROM webinar_registrations WHERE email = 'halves@example.test'
                """))).mappings().one()
            check("the whole name is stored for every reader",
                  stored["name"], "Mary Jane Smith")
            check("and both halves are stored beside it",
                  (stored["first_name"], stored["last_name"]), ("Mary Jane", "Smith"))

            sent.clear()
            async with Session() as db:
                pushed_out = await webinar.sync_streamyard(db, event=event)
            check("it pushes", pushed_out.get("pushed"), 1)
            check("a two-word first name is sent whole, not split at the space",
                  sent[0][1:3], ("Mary Jane", "Smith"))
            check("the phone rides along with it", sent[0][3], "0412 345 678")

            print("\nA resubmission from an older bundle keeps the stored pair")
            async with Session() as db:
                await webinar.register(
                    db, name="Mary Jane Smith", email="halves@example.test",
                    club="Test CC Renamed", event=event)
                kept = (await db.execute(text("""
                    SELECT first_name, last_name, club
                      FROM webinar_registrations WHERE email = 'halves@example.test'
                """))).mappings().one()
            check("the halves are not blanked by a one-field submission",
                  (kept["first_name"], kept["last_name"]), ("Mary Jane", "Smith"))
            check("while the club it did carry is still corrected",
                  kept["club"], "Test CC Renamed")

            print("\nA row written before the form did that still pushes")
            async with Session() as db:
                legacy = str(uuid.uuid4())
                await db.execute(text("""
                    INSERT INTO webinar_registrations (id, event_key, name, email, club)
                    VALUES (CAST(:id AS uuid), :k, 'Elton Baker', 'legacy@example.test', 'Test CC')
                """), {"id": legacy, "k": event.key})
                await db.commit()
                sent.clear()
                legacy_out = await webinar.sync_streamyard(db, event=event)
            check("the split is still the fallback for it", legacy_out.get("pushed"), 1)
            # The row genuinely carries no halves, so what the caller passes is
            # nothing — the split happens inside the shipped function.
            check("the row passes no halves, because it has none",
                  sent[0][1:3], (None, None))
            rule = getattr(streamyard, "resolve_push_name", None)
            if rule is None:
                for label in ("and the shipped rule splits its one string",
                              "the halves beat the split when both are there",
                              "one half alone falls back to the split",
                              "a mononym with no halves yields no pair at all"):
                    absent(label, "streamyard.resolve_push_name is absent")
            else:
                check("and the shipped rule splits its one string",
                      rule("Elton Baker"), ("Elton", "Baker"))
                check("the halves beat the split when both are there",
                      rule("Wrong Name", "Mary Jane", "Smith"), ("Mary Jane", "Smith"))
                check("one half alone falls back to the split",
                      rule("Elton Baker", "Elton", ""), ("Elton", "Baker"))
                check("a mononym with no halves yields no pair at all",
                      rule("Prince"), ("Prince", ""))

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
