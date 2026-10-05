"""A player typed in by hand is merged into their synced record when they play,
and only when that is unambiguous. Real Postgres, the shipped service and merge.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_hand_added_merge.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def u():
    return uuid.uuid4()


async def main():
    from app.models.db import (
        Base, Game, GameAppearance, Grade, Organisation, Player, PlayerSeasonStats, Season,
        FeeMember, engine, async_session_maker,
    )
    from app.services import hand_added_merge
    from app.routers.admin import undo_merge, UndoMergeRequest
    from verify_merge_carry import EXTRA_DDL
    if os.environ.get("CONTROL"):
        # The behaviour before this change: nothing merged a hand-added player on its own.
        async def _nothing(org_id, *, apply=True, pairs=None):
            return {"found": 0, "merged": 0, "failed": 0, "pairs": []}
        hand_added_merge.merge_pairs = _nothing

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_pair_ignores (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_a_id UUID NOT NULL,
            player_b_id UUID NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (org_id, player_a_id, player_b_id))"""))

    org, other = u(), u()
    s26, s25, g26, game = u(), u(), u(), u()
    ids = {k: u() for k in (
        "hA", "tA", "hB", "tB", "hC", "tC1", "tC2", "hD", "tD", "hE", "tE", "hF", "tF",
        "hG", "tG", "hH", "tH", "hI", "tI")}
    P = ids
    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Applecross", slug="apple-h", is_active=True),
                    Organisation(id=other, name="Elsewhere", slug="else-h", is_active=True),
                    Season(id=s26, organisation_id=org, name="Summer 2026/27", year=2026),
                    Season(id=s25, organisation_id=org, name="Summer 2025/26", year=2025)])
        await db.flush()
        db.add(Grade(id=g26, season_id=s26, name="1st XI"))
        await db.flush()
        db.add(Game(id=game, grade_id=g26, played_at=date(2026, 10, 3), home_team="A", away_team="B",
                    status="COMPLETED"))
        hand = lambda k, n, **kw: Player(id=P[k], organisation_id=org, name=n, **kw)
        synced = lambda k, n, **kw: Player(id=P[k], organisation_id=org, name=n, grassroots_id=str(P[k]), **kw)
        db.add_all([
            hand("hA", "Casey Newman"), synced("tA", "Newman, Casey"),                    # merges
            hand("hB", "Sam Veteran"), synced("tB", "Sam Veteran"),                        # twin played last year
            hand("hC", "Jo Double"), synced("tC1", "Jo Double"), synced("tC2", "Jo Double"),  # ambiguous
            hand("hD", "Dee History"), synced("tD", "Dee History"),                        # hand has history
            hand("hE", "Ewan Ignored"), synced("tE", "Ewan Ignored"),                      # club said keep apart
            hand("hF", "J Smith"), synced("tF", "J Smith"),                                # only an initial
            hand("hG", "Gus Claimed", claimed=True), synced("tG", "Gus Claimed"),          # claimed by a login
            hand("hI", "Ian Imported", cricketstatz_player_id="cs-1"), synced("tI", "Ian Imported"),
            hand("hH", "Otto Elsewhere"),
        ])
        db.add(Player(id=P["tH"], organisation_id=other, name="Otto Elsewhere", grassroots_id=str(P["tH"])))
        await db.flush()
        for k in ("tA", "tC1", "tC2", "tD", "tE", "tF", "tG", "tI"):
            db.add(GameAppearance(game_id=game, player_id=P[k]))
            db.add(PlayerSeasonStats(player_id=P[k], season_id=s26, matches=1))
        db.add(PlayerSeasonStats(player_id=P["tB"], season_id=s26, matches=1))
        db.add(PlayerSeasonStats(player_id=P["tB"], season_id=s25, matches=9))
        db.add(PlayerSeasonStats(player_id=P["hD"], season_id=s25, matches=3))
        db.add(GameAppearance(game_id=game, player_id=P["tH"]))
        db.add(FeeMember(id=u(), organisation_id=org, player_id=P["hA"], full_name="Casey Newman"))
        await db.commit()
        await db.execute(text("INSERT INTO merge_pair_ignores (org_id, player_a_id, player_b_id) "
                              "VALUES (:o, :a, :b)"), {"o": org, "a": P["hE"], "b": P["tE"]})
        await db.commit()

    async with async_session_maker() as db:
        pairs = await hand_added_merge.find_pairs(db, org)
    found = {(p["remove"]["id"], p["keep"]["id"]) for p in pairs}
    check("the new hand-added player is paired with their synced twin", (P["hA"], P["tA"]) in found)
    check("only that one pair is found", len(found), 1)

    dry = await hand_added_merge.merge_pairs(org, apply=False)
    async with async_session_maker() as db:
        still = (await db.execute(text("SELECT count(*) FROM players WHERE id = :p"), {"p": P["hA"]})).scalar()
    check("a dry run changes nothing", (dry["found"], dry["merged"], still), (1, 0, 1))

    res = await hand_added_merge.merge_pairs(org, apply=True)
    check("apply merges the one pair", (res["merged"], res["failed"]), (1, 0))

    async def one(sql, **kw):
        async with async_session_maker() as db:
            return (await db.execute(text(sql), kw)).scalar()

    check("the hand-added record is gone, the synced one kept",
          (await one("SELECT count(*) FROM players WHERE id = :p", p=P["hA"]),
           await one("SELECT count(*) FROM players WHERE id = :p", p=P["tA"])), (0, 1))
    check("their fee line followed the person onto the kept record",
          await one("SELECT player_id FROM fee_members WHERE organisation_id = :o AND full_name = 'Casey Newman'",
                    o=org), P["tA"])
    check("the merge is in the merge log, not undone",
          await one("SELECT count(*) FROM merge_logs WHERE org_id = :o AND removed_player_id = :r AND undone_at IS NULL",
                    o=org, r=P["hA"]), 1)
    check("an audit entry says it was automatic",
          await one("SELECT count(*) FROM audit_logs WHERE org_id = :o AND action = 'auto_merge_hand_added'", o=org), 1)

    for k, why in (("hB", "a twin who played last season is a different Sam"),
                   ("hC", "two synced players share the name"),
                   ("hD", "the hand-added record has history of its own"),
                   ("hE", "the club said these two are different people"),
                   ("hF", "a bare initial is not an identity"),
                   ("hG", "the hand-added record is claimed by a login"),
                   ("hI", "an imported record is a person with a past"),
                   ("hH", "the only twin belongs to another club")):
        check(f"left alone: {why}", await one("SELECT count(*) FROM players WHERE id = :p", p=P[k]), 1)

    again = await hand_added_merge.merge_pairs(org, apply=True)
    check("a second run finds nothing", (again["found"], again["merged"]), (0, 0))

    # Undoable from the same place a manual merge is.
    log_id = await one("SELECT id FROM merge_logs WHERE org_id = :o AND removed_player_id = :r", o=org, r=P["hA"])
    if log_id is not None:
        async with async_session_maker() as db:
            class _U:
                id = uuid.uuid4()
                username = "verifier"
            await undo_merge(UndoMergeRequest(merge_log_id=log_id, org_id=str(org)), db, _U())
    check("there is a merge to undo", log_id is not None)
    check("undo brings the hand-added record back",
          await one("SELECT count(*) FROM players WHERE id = :p", p=P["hA"]), 1)
    check("undo puts their fee line back on it",
          await one("SELECT player_id FROM fee_members WHERE organisation_id = :o AND full_name = 'Casey Newman'",
                    o=org), P["hA"])

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
