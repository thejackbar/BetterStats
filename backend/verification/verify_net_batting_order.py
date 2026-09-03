"""Verification for the net batting order's two flags (migration 284), against
a real Postgres.

Exercises the SHIPPED route bodies and helpers — never a re-implementation of
their logic — the way the rest of this repo's verification suites do.

The two questions worth the harness, because neither can be read off the code:

  * PADDING UP IS SPENT BY A ROTATION, at both ends. The group coming out have
    batted and the group going in have walked to the nets, so a mark that
    survived either would slowly turn the strip on the fence into a list of
    everyone the coach has ever spoken to. Somebody further down the queue must
    keep theirs through the same rotation, or the flag couldn't be set ahead.

  * PRIORITY DOES NOT MOVE ANYBODY. It is a fact about a player's night, not a
    position, and the queue must read exactly the same after ticking it — the
    screen asks the coach whether to move them, and this is what proves the
    tick alone does not.

Run:  DATABASE_URL=postgresql+asyncpg://... python verify_net_batting_order.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, NetAttendance, NetSession, Organisation, Player, User

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


# ── The migration's own statements, and the lifespan's copy of them ──────────
MIGRATION = Path(__file__).resolve().parent.parent / "alembic/versions/284_net_batting_order_flags.py"
MAIN = Path(__file__).resolve().parent.parent / "app/main.py"


def _statements(source: str) -> list[str]:
    """Every `ALTER TABLE net_attendance … padding_up|priority` in a file.

    Read out of the real source rather than retyped here, so a suite that
    passes is evidence about what actually ships. Adjacent string literals are
    joined first — both copies wrap the statement across two lines.
    """
    joined = re.sub(r'"\s*\n\s*"', "", source)
    return re.findall(
        r"ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS (?:padding_up|priority)[^\"]*",
        joined,
    )


async def build_pre_284():
    """The schema as it stood BEFORE 284, with the two columns removed again.

    `create_all` builds them from the model, so the migration would have
    nothing to do; dropping them is what gives it something — and what lets the
    populated-table checks below mean anything.
    """
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE net_attendance DROP COLUMN IF EXISTS padding_up"))
        await conn.execute(text("ALTER TABLE net_attendance DROP COLUMN IF EXISTS priority"))


async def seed():
    """A club with BetterSelect, one live session, and six players checked in."""
    async with Session() as db:
        club = Organisation(
            id=uuid.uuid4(), name="Applecross Cricket Club", slug="applecross-bo",
            short_name="ACC", module_overrides=["select"], subscription_status="active",
            net_settings={"nets": 2, "duration_seconds": 600},
        )
        other = Organisation(
            id=uuid.uuid4(), name="High Wycombe CC", slug="high-wycombe-bo",
            module_overrides=["select"], subscription_status="active",
        )
        db.add_all([club, other])
        await db.flush()

        user = User(id=uuid.uuid4(), username="coach-bo", email="c@b.com", password_hash="x")
        db.add(user)

        players = []
        for nm in ["Barendse, Jack", "Mant, Brad", "Cole, Graeme",
                   "Sawatzky, Cameron", "Watt, Matthew", "Gill, Amardeep"]:
            p = Player(id=uuid.uuid4(), organisation_id=club.id, name=nm,
                       status="active", is_player=True)
            players.append(p)
        db.add_all(players)

        s = NetSession(
            id=uuid.uuid4(), organisation_id=club.id,
            session_date=datetime.now(timezone.utc).date(),
            label="Thursday senior nets", status="active", version=0,
            settings={"nets": 2, "duration_seconds": 600, "auto_roll": False,
                      "sound": True, "alerts": []},
        )
        foreign = NetSession(
            id=uuid.uuid4(), organisation_id=other.id,
            session_date=datetime.now(timezone.utc).date(),
            label="Their nets", status="active", version=0,
        )
        db.add_all([s, foreign])
        await db.commit()
        return {"club": club.id, "other": other.id, "user": user.id,
                "session": s.id, "foreign": foreign.id,
                "players": [p.id for p in players]}


def by_name(payload, name):
    for a in payload["attendees"]:
        if a["name"] == name:
            return a
    return {}


def flag(payload, name, key):
    """One attendee's flag, or None when the payload doesn't carry it at all.

    Read through `.get` on purpose: with the change absent the key is simply
    missing, and a suite that died on the first KeyError would say nothing
    about the other forty checks. A control run has to report.
    """
    return by_name(payload, name).get(key)


def order(payload):
    """The batting order as names — everyone still waiting, in queue order."""
    return [a["name"] for a in payload["attendees"] if not a["batted"] and a["bats"]]


async def main():
    import app.routers.net_manager as nm

    print("\n── Migration 284, applied to a populated pre-284 table ──")
    await build_pre_284()
    ids = await seed()

    stmts = _statements(MIGRATION.read_text())
    check("the migration carries both ALTERs", len(stmts), 2)
    mirror = _statements(MAIN.read_text())
    check("the lifespan mirrors the same two", sorted(mirror), sorted(stmts))

    async with engine.begin() as conn:
        # Rows that predate the columns, so the backfill has real data under it.
        for i in range(3):
            await conn.execute(text(
                "INSERT INTO net_attendance (id, session_id, organisation_id, guest_name,"
                " batted, bats, position, source) VALUES"
                " (gen_random_uuid(), :s, :o, :g, false, true, :p, 'admin')"
            ), {"s": ids["session"], "o": ids["club"], "g": f"Pre-284 guest {i}", "p": i})

    for run in range(1, 4):
        async with engine.begin() as conn:
            for st in stmts:
                await conn.execute(text(st))
        async with engine.begin() as conn:
            cols = (await conn.execute(text(
                "SELECT column_name, is_nullable, column_default FROM information_schema.columns"
                " WHERE table_name='net_attendance' AND column_name IN ('padding_up','priority')"
                " ORDER BY column_name"
            ))).fetchall()
        check(f"run {run}: both columns exist, NOT NULL, defaulting false",
              [(c[0], c[1], (c[2] or "").split("::")[0]) for c in cols],
              [("padding_up", "NO", "false"), ("priority", "NO", "false")])

    async with engine.begin() as conn:
        check("every pre-284 row reads false for both", (await conn.execute(text(
            "SELECT count(*) FROM net_attendance WHERE padding_up OR priority"))).scalar(), 0)
        check("and none of them were lost", (await conn.execute(text(
            "SELECT count(*) FROM net_attendance"))).scalar(), 3)
        await conn.execute(text("DELETE FROM net_attendance"))

    print("\n── Applying the lifespan's copy lands on the same schema ──")
    async with engine.begin() as conn:
        before = (await conn.execute(text(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns"
            " WHERE table_name='net_attendance' ORDER BY column_name"))).fetchall()
        for st in mirror:
            await conn.execute(text(st))
        after = (await conn.execute(text(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns"
            " WHERE table_name='net_attendance' ORDER BY column_name"))).fetchall()
    check("the mirror is a no-op over the migration's schema", after, before)

    # ── The shipped route bodies from here on ────────────────────────────────
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        other = await db.get(Organisation, ids["other"])
        user = await db.get(User, ids["user"])
        sid = str(ids["session"])
        names = ["Barendse, Jack", "Mant, Brad", "Cole, Graeme",
                 "Sawatzky, Cameron", "Watt, Matthew", "Gill, Amardeep"]

        print("\n── Checking six players in ──")
        payload = None
        for pid in ids["players"]:
            payload = await nm.add_attendee(
                sid, nm.AttendeeAdd(player_id=str(pid)), db=db, club=club, user=user)
        check("all six are in the order", order(payload), names)
        check("nobody arrives padding up", [a.get("padding_up") for a in payload["attendees"]], [False] * 6)
        check("nobody arrives as priority", [a.get("priority") for a in payload["attendees"]], [False] * 6)

        aid = {a["name"]: a["id"] for a in payload["attendees"]}

        print("\n── Padding up ──")
        payload = await nm.patch_attendee(sid, aid["Cole, Graeme"],
                                          nm.AttendeePatch(padding_up=True),
                                          db=db, club=club, user=user)
        check("the flag lands on the payload", flag(payload, "Cole, Graeme", "padding_up"), True)
        check("and reaches nobody else", sum(1 for a in payload["attendees"] if a.get("padding_up")), 1)
        check("flagging moves nobody", order(payload), names)

        payload = await nm.patch_attendee(sid, aid["Cole, Graeme"],
                                          nm.AttendeePatch(note="pads on"),
                                          db=db, club=club, user=user)
        check("an unrelated edit leaves it alone", flag(payload, "Cole, Graeme", "padding_up"), True)

        # Marked as batted: the mark was about the turn to come, and that turn
        # has now happened for them.
        payload = await nm.patch_attendee(sid, aid["Cole, Graeme"],
                                          nm.AttendeePatch(batted=True),
                                          db=db, club=club, user=user)
        check("marking them batted clears it", flag(payload, "Cole, Graeme", "padding_up"), False)
        payload = await nm.patch_attendee(sid, aid["Cole, Graeme"],
                                          nm.AttendeePatch(batted=False),
                                          db=db, club=club, user=user)
        check("and putting them back doesn't resurrect it",
              flag(payload, "Cole, Graeme", "padding_up"), False)

        payload = await nm.patch_attendee(sid, aid["Watt, Matthew"],
                                          nm.AttendeePatch(padding_up=True),
                                          db=db, club=club, user=user)
        payload = await nm.patch_attendee(sid, aid["Watt, Matthew"],
                                          nm.AttendeePatch(bats=False),
                                          db=db, club=club, user=user)
        check("dropping out of the rotation clears it",
              flag(payload, "Watt, Matthew", "padding_up"), False)
        payload = await nm.patch_attendee(sid, aid["Watt, Matthew"],
                                          nm.AttendeePatch(bats=True),
                                          db=db, club=club, user=user)
        check("and coming back doesn't resurrect it either",
              flag(payload, "Watt, Matthew", "padding_up"), False)

        print("\n── A rotation spends the flag at both ends ──")
        # Coming back in put Watt at the back, so the order is now:
        #   Jack, Brad, Cole(back), Cameron, Amardeep, Matthew   (2 nets)
        current = order(payload)
        check("the order after those moves", len(current), 6)
        in_nets, next_two, later = current[:2], current[2:4], current[4:]

        for nm_ in in_nets + next_two + later[:1]:
            payload = await nm.patch_attendee(sid, aid[nm_], nm.AttendeePatch(padding_up=True),
                                              db=db, club=club, user=user)
        check("five are flagged before the rotation",
              sum(1 for a in payload["attendees"] if a.get("padding_up")), 5)

        payload = await nm.rotate_group(sid, nm.RotateBody(autostart=False),
                                        db=db, club=club, user=user)
        check("the group that batted lose it",
              [flag(payload, x, "padding_up") for x in in_nets], [False, False])
        check("the group that walked in lose it",
              [flag(payload, x, "padding_up") for x in next_two], [False, False])
        check("somebody further down KEEPS theirs",
              flag(payload, later[0], "padding_up"), True)
        check("so exactly one flag survives",
              sum(1 for a in payload["attendees"] if a.get("padding_up")), 1)
        check("and the two who batted are recorded as such",
              [by_name(payload, x).get("batted") for x in in_nets], [True, True])

        print("\n── Priority ──")
        before_order = order(payload)
        target = before_order[-1]
        payload = await nm.patch_attendee(
            sid, aid[target], nm.AttendeePatch(priority=True, note="leaving at 7"),
            db=db, club=club, user=user)
        check("the flag lands", flag(payload, target, "priority"), True)
        check("the reason is stored on the note", by_name(payload, target).get("note"), "leaving at 7")
        # The load-bearing one: a tick is a fact, not a move.
        check("TICKING IT MOVES NOBODY", order(payload), before_order)

        payload = await nm.patch_attendee(sid, aid[target], nm.AttendeePatch(batted=True),
                                          db=db, club=club, user=user)
        check("it survives their turn", flag(payload, target, "priority"), True)
        payload = await nm.patch_attendee(sid, aid[target], nm.AttendeePatch(batted=False),
                                          db=db, club=club, user=user)
        payload = await nm.patch_attendee(sid, aid[target], nm.AttendeePatch(bats=False),
                                          db=db, club=club, user=user)
        check("and it survives sitting out", flag(payload, target, "priority"), True)
        payload = await nm.patch_attendee(sid, aid[target], nm.AttendeePatch(bats=True),
                                          db=db, club=club, user=user)

        payload = await nm.patch_attendee(sid, aid[target], nm.AttendeePatch(priority=False),
                                          db=db, club=club, user=user)
        check("un-ticking clears it", flag(payload, target, "priority"), False)
        check("and leaves the reason where it was", by_name(payload, target).get("note"), "leaving at 7")

        payload = await nm.patch_attendee(
            sid, aid[target], nm.AttendeePatch(priority=True, note="x" * 400),
            db=db, club=club, user=user)
        check("an over-long reason is capped, not refused",
              len(by_name(payload, target).get("note")), 120)

        print("\n── The order the drag writes ──")
        rows = order(payload)
        flipped = list(reversed(rows))
        payload = await nm.reorder_queue(
            sid, nm.QueueOrder(ids=[aid[x] for x in flipped]), db=db, club=club, user=user)
        check("a whole new order lands", order(payload), flipped)

        # Dropping someone into a net spot is the same write, so it gets the
        # same guarantees: this is what a drag from the bottom of the list to
        # net 1 sends.
        moved = [flipped[-1]] + flipped[:-1]
        payload = await nm.reorder_queue(
            sid, nm.QueueOrder(ids=[aid[x] for x in moved]), db=db, club=club, user=user)
        check("the last name dragged into net 1 lands there", order(payload)[0], flipped[-1])

        # A name this device never knew about — checked in from the phone by the
        # nets a second ago — keeps its place rather than being dropped.
        fresh = await nm.add_attendee(sid, nm.AttendeeAdd(guest_name="Late trialist"),
                                      db=db, club=club, user=user)
        stale = [aid[x] for x in moved]
        payload = await nm.reorder_queue(sid, nm.QueueOrder(ids=stale),
                                         db=db, club=club, user=user)
        check("a name the sending device didn't know about survives",
              "Late trialist" in order(payload), True)
        check("and it sits at the back", order(payload)[-1], "Late trialist")

        # An id from somewhere else is ignored rather than trusted — and, the
        # half that matters, ignoring it must not quietly drop anybody either.
        before_ids = sorted(order(payload))
        payload = await nm.reorder_queue(
            sid, nm.QueueOrder(ids=[str(uuid.uuid4()), aid[moved[-1]]]),
            db=db, club=club, user=user)
        check("a foreign id is ignored, and nobody is lost", sorted(order(payload)), before_ids)
        check("while the real id in the same request is honoured", order(payload)[0], moved[-1])

        print("\n── Another club can't touch it ──")
        for label, fn in [
            ("patch", lambda: nm.patch_attendee(sid, aid[moved[0]],
                                                nm.AttendeePatch(priority=True),
                                                db=db, club=other, user=user)),
            ("rotate", lambda: nm.rotate_group(sid, nm.RotateBody(), db=db, club=other, user=user)),
            ("reorder", lambda: nm.reorder_queue(sid, nm.QueueOrder(ids=[]),
                                                 db=db, club=other, user=user)),
        ]:
            try:
                await fn()
                check(f"a {label} from another club is refused", False)
            except Exception as e:
                check(f"a {label} from another club → 404", getattr(e, "status_code", None), 404)

        print("\n── Every device sees the change ──")
        v = payload["version"]
        after = await nm.patch_attendee(sid, aid[moved[0]], nm.AttendeePatch(padding_up=True),
                                        db=db, club=club, user=user)
        check("a flag bumps the version other devices poll on", after["version"] > v, True)
        same = await nm.live_session(sid, since=after["version"], db=db, club=club)
        check("a poll at that version is told nothing changed", same.get("unchanged"), True)
        moved_on = await nm.live_session(sid, since=v, db=db, club=club)
        check("and a poll behind it gets the flag", flag(moved_on, moved[0], "padding_up"), True)

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
