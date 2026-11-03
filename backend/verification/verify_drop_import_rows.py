"""The club decides which sheet-only games to keep, and the decision moves the totals and can be undone.

Hamilton Veterans (Nov 2026): a few dozen games only the season-totals sheet holds. The club is sent
a CSV (`ops/diagnostics/import_only_games.sql`), marks each row Y or N, and
`app.scripts.drop_import_rows` removes the N rows. Runs the SHIPPED script functions over the
Hamilton-shaped data of `verify_import_typed_games`: the list the SQL produces, the CSV reader, the
dry run (changes nothing), apply (totals follow, one audit entry), restore (back exactly), and the
guards (wrong club, a mark that is not Y or N, a wrong --expect).

THE CONTROL RUN is this file against the previous commit: the script does not exist there, so the
first import fails and nothing passes. There is no earlier behaviour to compare, which is the point:
a club had no way to drop one sheet row, only a whole player's rows or the whole batch.

Run (needs the schema verify_import_typed_games builds; run that first, same database):
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_import_typed_games.py && python verification/verify_drop_import_rows.py
"""
from __future__ import annotations

import asyncio
import csv
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts import drop_import_rows as dr

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


ORG = "c1000000-0000-0000-0000-000000000001"
P_SHORT, P_ONLY, P_OUT = (f"c4000000-0000-0000-0000-00000000000{n}" for n in (2, 3, 4))
REPO = Path(__file__).resolve().parents[2]


async def games(pid: str) -> int:
    async with async_session_maker() as s:
        return int((await s.execute(text(
            "SELECT COALESCE(SUM(matches), 0) FROM v_effective_player_season_stats WHERE player_id = CAST(:p AS UUID)"),
            {"p": pid})).scalar())


async def rows_for(pid: str) -> list[int]:
    async with async_session_maker() as s:
        return [r[0] for r in (await s.execute(text(
            "SELECT id FROM imported_stats WHERE player_id = CAST(:p AS UUID) ORDER BY id"), {"p": pid})).all()]


def sql_list() -> list[dict]:
    """The club's list, produced by the shipped SQL file against this database."""
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    out = subprocess.run(["psql", "-q", url, "-v", "club='%Hamilton Veterans%'", "-f", str(REPO / "ops/diagnostics/import_only_games.sql")],
                         capture_output=True, text=True)
    return list(csv.DictReader(out.stdout.splitlines())) if out.returncode == 0 else []


def marked_csv(rows: list[dict], marks: dict) -> str:
    path = tempfile.mktemp(suffix=".csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            r = dict(r)
            r[dr.KEEP_COLUMN] = marks.get(r["Player"], "")
            w.writerow(r)
    return path


async def main() -> None:
    # `audit_logs` is created inline in main.py's lifespan, so it is copied here column for column.
    async with async_session_maker() as s:
        await s.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                user_id UUID, action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}'
            )"""))
        await s.commit()

    print("\n-- the list the club is sent --")
    lst = sql_list()
    names = {r["Player"] for r in lst}
    check("the SQL file produces a list", len(lst) > 0, "no rows (is the import suite's data in this database?)")
    check("it names the three players the sheet alone still holds games for",
          {"Short, Sam", "Only, Olly", "Out, Ozzy"} <= names, f"{sorted(names)}")
    check("and not the one the club's own games already cover", "Full, Fred" not in names)
    only = next((r for r in lst if r["Player"] == "Only, Olly"), {})
    check("a player nothing else holds says so", "Nothing else holds" in only.get("Why it is still counted", ""),
          only.get("Why it is still counted", ""))
    short = next((r for r in lst if r["Player"] == "Short, Sam"), {})
    check("a player the club typed fewer games for says that, with the gap (3 on the sheet, 1 held, 2 only the sheet)",
          short.get("Games on the sheet") == "3" and short.get("Games already held (PlayHQ or typed)") == "1"
          and short.get("Games only the sheet holds") == "2", f"{short}")

    print("\n-- reading the club's marks --")
    path = marked_csv(lst, {"Only, Olly": "N", "Short, Sam": "Y", "Out, Ozzy": ""})
    ids = dr.ids_from_csv(path)
    check("only the row marked N is taken", ids == [int(x) for x in only["Sheet row ids (leave)"].split()], f"{ids}")
    bad = marked_csv(lst, {"Only, Olly": "maybe"})
    try:
        dr.ids_from_csv(bad)
        check("a mark that is not Y or N is refused", False, "accepted")
    except SystemExit as e:
        check("a mark that is not Y or N is refused, naming the line", "not Y or N" in str(e), str(e))

    print("\n-- the dry run changes nothing --")
    before = await games(P_ONLY)
    rows, missing = await dr.plan(ORG, ids)
    check("the plan finds the row", len(rows) == 1 and not missing, f"{rows} {missing}")
    check("and nothing has moved", await games(P_ONLY) == before and await rows_for(P_ONLY) != [], f"{before}")
    other, gone = await dr.plan("11111111-1111-1111-1111-111111111111", ids)
    check("another club's id finds nothing: the row is not theirs to remove", not other and gone == ids, f"{other} {gone}")

    print("\n-- the guards --")
    try:
        await dr.apply(ORG, rows, expect=5, by="test")
        check("a wrong --expect is refused", False, "applied")
    except SystemExit:
        check("a wrong --expect is refused", await rows_for(P_ONLY) != [])
    try:
        await dr.apply(ORG, rows, expect=1, by=None)
        check("no --by is refused", False, "applied")
    except SystemExit:
        check("no --by is refused", await rows_for(P_ONLY) != [])

    print("\n-- apply --")
    others_before = (await games(P_SHORT), await games(P_OUT))
    audit_id = await dr.apply(ORG, rows, expect=1, by="test")
    check("the marked row is gone", await rows_for(P_ONLY) == [], f"{await rows_for(P_ONLY)}")
    check("and the player's total follows: 1 game becomes 0", await games(P_ONLY) == 0, f"{await games(P_ONLY)}")
    check("rows marked Y or left blank are untouched, and so are their totals",
          (await games(P_SHORT), await games(P_OUT)) == others_before and await rows_for(P_SHORT) != [] and await rows_for(P_OUT) != [],
          f"{(await games(P_SHORT), await games(P_OUT))} vs {others_before}")
    after_list = {r["Player"] for r in sql_list()}
    check("the list no longer offers it", "Only, Olly" not in after_list and "Short, Sam" in after_list, f"{sorted(after_list)}")

    print("\n-- restore --")
    back = await dr.restore(audit_id, by="test")
    check("one row comes back", back == 1, f"{back}")
    check("with its original id", await rows_for(P_ONLY) == ids, f"{await rows_for(P_ONLY)} vs {ids}")
    check("and the total is 1 again", await games(P_ONLY) == before, f"{await games(P_ONLY)}")
    try:
        await dr.restore(audit_id, by="test")
        check("an entry restores once", False, "restored twice")
    except SystemExit as e:
        check("an entry restores once", "already restored" in str(e), str(e))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
