"""Verification: two same-name records with games on the same date are not offered as safe to merge. Real Postgres.

Reported: Mulgrave's adult Luke Bennett (first grade) and a junior Luke Bennett (U11 competition) were
merged on 23 July by Bulk Approve, which treats two records with an identical name as an "exact"
duplicate. The adult record then held 16 junior games, and on many dates both had a game.

Rule (`services/merge_safety`): one person is not in two different games on one date, so two records
that each have a game on the same date are very likely two people. The candidates list flags such a
pair (`same_day_clash`) and the screen keeps it out of Bulk Approve; the merge route refuses it
(HTTP 409, code `same_day_clash`) until the request carries `confirm_same_day_clash`.

Runs the SHIPPED `routers/admin.get_merge_candidates` and `merge_players` route bodies. CONTROL: run
this file with `services/merge_safety.py` and the admin router from before this change (git stash): the
namesake pair merges with no confirmation and no flag is reported, which fails exactly the checks below.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/betterstats_verify \
  python verification/verify_merge_same_day_safeguard.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_repair_misattributed_games as h          # schema + views, copied from the lifespan
from app.routers import admin

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
h.engine, h.Session = engine, Session

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE_SEN, GRADE_JNR = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ADULT, JUNIOR = uuid.uuid4(), uuid.uuid4()                    # the two Luke Bennetts
SAM_OLD, SAM_NEW = uuid.uuid4(), uuid.uuid4()                 # one Sam Jones under two ids
KIM_A, KIM_B = uuid.uuid4(), uuid.uuid4()                     # two records in the SAME game only
USER = SimpleNamespace(id=None)


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Test CC', 'test', true)", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
        for gid, nm, cat in ((GRADE_SEN, "1st Grade", "senior"), (GRADE_JNR, "U11", "junior")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, :c, ARRAY[CAST(:c AS TEXT)])", i=gid, s=SEASON, n=nm, g=str(gid), c=cat)
        for pid, nm in ((ADULT, "Bennett, Luke"), (JUNIOR, "Luke Bennett"), (SAM_OLD, "Jones, Sam"), (SAM_NEW, "Sam Jones"),
                        (KIM_A, "Lee, Kim"), (KIM_B, "Kim Lee")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=nm, g=str(pid))

        async def game(grade, d, players):
            gid = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                     "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')", i=gid, g=grade, d=d, o=ORG, x=OPP)
            for p in players:
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=p)

        # The namesakes: the same Saturday, different games, twice; plus games on other days.
        await game(GRADE_SEN, date(2025, 11, 15), [ADULT])
        await game(GRADE_JNR, date(2025, 11, 15), [JUNIOR])
        await game(GRADE_SEN, date(2025, 11, 22), [ADULT])
        await game(GRADE_JNR, date(2025, 11, 22), [JUNIOR])
        await game(GRADE_JNR, date(2025, 12, 6), [JUNIOR])
        # One person under two ids: the old id ends in 2023, the new one starts in 2025. Never the same day.
        await game(GRADE_SEN, date(2023, 3, 4), [SAM_OLD])
        await game(GRADE_SEN, date(2025, 11, 1), [SAM_NEW])
        # Two records in the SAME game (a shared id can do this for one person): not a same-day clash.
        await game(GRADE_SEN, date(2025, 11, 8), [KIM_A, KIM_B])
        await s.commit()


async def alive(pid) -> bool:
    async with Session() as s:
        return bool((await s.execute(text("SELECT 1 FROM players WHERE id = :p"), {"p": pid})).scalar())


def pair_of(cands, a, b):
    for c in cands:
        if {c["player_a"]["id"], c["player_b"]["id"]} == {str(a), str(b)}:
            return c
    return None


async def main() -> int:
    await h.build_schema()
    async with engine.begin() as conn:
        # Lifespan DDL (main.py) the merge screen reads, column for column.
        # The later ALTERs on merge_logs (main.py), which the real merge writes.
        await conn.execute(text("ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS imported_stat_ids JSONB DEFAULT '[]'"))
        await conn.execute(text("ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS carried_row_ids JSONB DEFAULT '{}'"))
        await conn.execute(text("ALTER TABLE merge_logs ADD COLUMN IF NOT EXISTS removed_cricketstatz_player_id TEXT"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_pair_ignores (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_a_id UUID NOT NULL, player_b_id UUID NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE (org_id, player_a_id, player_b_id))"""))
    await seed()

    print("\n-- the candidates list --")
    async with Session() as s:
        cands = await admin.get_merge_candidates(org_id=str(ORG), db=s, _=USER)
    luke, sam, kim = pair_of(cands, ADULT, JUNIOR), pair_of(cands, SAM_OLD, SAM_NEW), pair_of(cands, KIM_A, KIM_B)
    check("the two Luke Bennetts are listed as an exact pair", luke is not None and luke["kind"] == "exact")
    check("...flagged with the two dates they clash on", bool(luke) and luke.get("same_day_clash") == 2, str(luke and luke.get("same_day_clash")))
    check("...with a plain message for the screen", bool(luke) and "different people" in (luke.get("same_day_clash_message") or ""))
    check("one Sam Jones under two ids is listed and NOT flagged", sam is not None and sam.get("same_day_clash") == 0, str(sam and sam.get("same_day_clash")))
    check("two records in the same game only are NOT flagged", kim is not None and kim.get("same_day_clash") == 0, str(kim and kim.get("same_day_clash")))

    print("\n-- the merge route --")
    refused = None
    async with Session() as s:
        try:
            await admin.merge_players(admin.MergeRequest(keep_player_id=str(ADULT), remove_player_id=str(JUNIOR), org_id=str(ORG)), s, USER)
        except HTTPException as e:
            refused = e
    check("merging the namesakes without confirmation is refused with 409", refused is not None and refused.status_code == 409,
          "it merged" if refused is None else str(refused.detail))
    check("...with a code the screen can act on",
          refused is not None and isinstance(refused.detail, dict) and refused.detail.get("code") == "same_day_clash", str(refused and refused.detail))
    check("...and nothing was merged", await alive(ADULT) and await alive(JUNIOR))

    async with Session() as s:
        await admin.merge_players(admin.MergeRequest(keep_player_id=str(SAM_NEW), remove_player_id=str(SAM_OLD), org_id=str(ORG)), s, USER)
    check("one person under two ids merges with no confirmation", not await alive(SAM_OLD) and await alive(SAM_NEW))
    async with Session() as s:
        await admin.merge_players(admin.MergeRequest(keep_player_id=str(KIM_A), remove_player_id=str(KIM_B), org_id=str(ORG)), s, USER)
    check("a pair that only shares one game merges with no confirmation", not await alive(KIM_B) and await alive(KIM_A))

    err = None
    async with Session() as s:
        try:
            await admin.merge_players(admin.MergeRequest(keep_player_id=str(ADULT), remove_player_id=str(JUNIOR), org_id=str(ORG),
                                                         confirm_same_day_clash=True), s, USER)
        except HTTPException as e:          # presence-safe: the control run has already merged them
            err = e
    check("an admin who confirms can still merge them", err is None and not await alive(JUNIOR) and await alive(ADULT),
          str(err.detail) if err else "")

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
