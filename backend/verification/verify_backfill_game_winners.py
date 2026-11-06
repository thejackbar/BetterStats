"""`app.scripts.backfill_game_winners`: dry run, apply, audit entry and restore. Real Postgres.

Same reported shape as verify_game_winner (a finished game holding the other club's LOSS and no winner), plus a
game whose card spells the winner differently from either stored side, which must be left alone.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/winner_verify?host=/tmp&port=5439 \\
  python verification/verify_backfill_game_winners.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_game_winner as v       # its seed and card; main() is guarded
import verify_reread_incomplete_game as h
from app.services import grassroots_scores_client as gr

check, Session = h.check, h.Session
G_MISSPELT = uuid.uuid4()


async def audit_rows(action):
    async with Session() as s:
        return (await s.execute(text("SELECT id, details FROM audit_logs WHERE action = :a ORDER BY id"),
                                {"a": action})).all()


def args(**kw):
    base = dict(org=str(h.ORG), apply=False, expect=None, by=None, restore=None, max_games=100, pace=0.0,
                list=40, timeout=60)
    base.update(kw)
    return SimpleNamespace(**base)


async def main() -> None:
    from app.scripts import backfill_game_winners as script
    await h.build_schema()
    async with h.engine.begin() as conn:
        # The lifespan's own raw-SQL table (app/main.py), column for column.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
                action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
    await v.seed()
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, result, winning_team, status, "
            " home_org_id, away_org_id) VALUES (:i, :g, :d, 'Odd Name', 'Other Name', 'LOSS', NULL, 'COMPLETED', :ho, :ao)"),
            {"i": G_MISSPELT, "g": v.THEIR_GRADE, "d": h.TODAY - timedelta(days=90), "ho": h.ORG, "ao": h.OPP_ORG})
        await s.commit()

    cards = {str(g): v.card(g) for g in (v.G_OLD, v.G_RECENT, v.G_NAMED, v.G_DRAW, v.G_STRANGER)}
    cards[str(G_MISSPELT)] = v.card(v.G_OLD)       # CA names "SBCC Ladies B Grade"; the stored sides read otherwise
    cards[str(G_MISSPELT)]["id"] = str(G_MISSPELT)
    fetched: list[str] = []

    async def fake_card(match_id, *a, **k):
        fetched.append(str(match_id))
        return cards.get(str(match_id))

    gr.get_match_scorecard = fake_card

    print("\n-- DRY RUN --")
    rows, left = await script.plan(str(h.ORG), args(), [100])
    ids = {r["game_id"] for r in rows}
    check("plans the two games with a LOSS and no winner that CA now names",
          ids == {str(v.G_OLD), str(v.G_RECENT)}, str(ids))
    check("every planned winner is the side CA names", {r["winner"] for r in rows} == {v.US})
    check("a card whose winner matches neither stored side is left and counted",
          sum(left.values()) == 1 and "spelled" in next(iter(left)), str(dict(left)))
    check("a game with its winner, a draw and another pair's game are not read",
          not ({str(v.G_NAMED), str(v.G_DRAW), str(v.G_STRANGER)} & set(fetched)), str(fetched))
    check("the dry run writes nothing", await v.winner_of(v.G_OLD) is None and await audit_rows(script.ACTION) == [])

    print("\n-- APPLY --")
    for label, kw, why in (("a wrong --expect", dict(expect=5, by="t"), "expect"),
                           ("a missing --by", dict(expect=len(rows)), "by")):
        try:
            await script.apply(str(h.ORG), rows, kw.get("expect"), kw.get("by"))
            refused = False
        except SystemExit:
            refused = True
        check(f"refuses {label}", refused and await v.winner_of(v.G_OLD) is None)
    await script.apply(str(h.ORG), rows, len(rows), "tester")
    check("the winners are written", await v.winner_of(v.G_OLD) == v.US and await v.winner_of(v.G_RECENT) == v.US)
    check("a game with its winner is untouched", await v.winner_of(v.G_NAMED) == v.THEM)
    check("the misspelt one is untouched", await v.winner_of(G_MISSPELT) is None)
    check("the scorecard now reads the Grand Final as a win", await v.scorecard_result(v.G_OLD) == "WIN")
    audits = await audit_rows(script.ACTION)
    check("one audit entry holds every row written",
          len(audits) == 1 and len(audits[0][1]["changes"]) == 2 and audits[0][1]["by"] == "tester", str(audits))

    print("\n-- A SECOND DRY RUN --")
    rows2, _ = await script.plan(str(h.ORG), args(), [100])
    check("has nothing left to plan", rows2 == [], str(rows2))

    print("\n-- RESTORE --")
    await script.restore(audits[0][0], "tester")
    check("puts both winners back to empty", await v.winner_of(v.G_OLD) is None and await v.winner_of(v.G_RECENT) is None)
    check("and leaves the stored winner it did not write", await v.winner_of(v.G_NAMED) == v.THEM)
    check("the restore is itself logged", len(await audit_rows(script.RESTORE_ACTION)) == 1)
    try:
        await script.restore(audits[0][0], "tester")
        again = False
    except SystemExit:
        again = True
    check("an entry restores once", again)
    check("and the original audit entry was never edited", (await audit_rows(script.ACTION))[0][1] == audits[0][1])

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
