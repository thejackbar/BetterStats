"""Remove one player's imported summary rows that were also attached to a namesake.

Reported off Leederville: Paul K Jones showed 512 matches and 4,324 runs where the
club's sheet says 258 and 1,165. His "Prior Seasons & Adjustments" line held the
sheet's figures for Paul G Jones (254 games, 3,159 runs) on top of his own. The two
are different people who share the stored name "Jones, Paul", and a BetterImport
upload had put Paul G's line on both records.

`imported_stats` is what a club uploaded, and the reconciler sums every row it holds
for a player, so a copy of someone else's line adds their career to this one. This
script finds the keeper's rows that are figure-for-figure copies of a row the other
player holds (same scope, season, grade and every count column) and removes only
those. The other player is never touched, nor is any row of the keeper's that is
not a copy. A hand-typed career or season adjustment is never removed by code: if
one of those matches, it is reported so it can be edited in Manual Entries.

Each removed row gets an audit entry holding the whole row, then the club's derived
import figures are rebuilt. The script then reads the keeper's season-less line back
from `v_effective_player_season_stats` so you can see the result. Dry run by default:

    python -m app.scripts.remove_cross_attached_imports <org-id-or-slug> <keeper-player-id> <other-player-id> [--row-id N ...] [--apply]

By default only exact copies of a row the other player holds are removed. When the
other player no longer holds their own copy (Leederville's Paul G did not), name the
keeper's row with `--row-id N`: only a row that belongs to the keeper in this club is
accepted, and the dry run lists what would go.

For Leederville: the keeper is Paul K (5cb1722d-369a-4b96-ac8f-5b2cb951d89d) and the
other player is Paul G (83ae1a5e-1d7e-4dd9-b1e9-a4fadf68d379).
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select, text

from app.models.db import ImportedStat, async_session_maker

# Columns that say nothing about WHAT was uploaded.
_NOT_FIGURES = {"id", "organisation_id", "import_batch_id", "player_id", "created_at", "notes"}
_FIGURE_COLUMNS = [c.name for c in ImportedStat.__table__.columns if c.name not in _NOT_FIGURES]

# A line with none of these is empty, and two empty lines are not a copy of anything.
_MEANINGFUL = ("games_played", "batting_innings", "batting_runs", "bowling_wickets",
               "bowling_runs", "fielding_catches")


def signature(row: dict) -> tuple:
    """Everything an uploaded line says, ignoring who it was filed under."""
    return tuple(str(row.get(c)) for c in _FIGURE_COLUMNS)


def is_meaningful(row: dict) -> bool:
    return any((row.get(c) or 0) > 0 for c in _MEANINGFUL)


def copies_of(keeper_rows: list[dict], other_rows: list[dict]) -> list[dict]:
    """The keeper's rows that duplicate a row the other player holds.

    Each of the other player's rows can explain one keeper row, so a keeper who
    legitimately holds a second, identical line of their own is not emptied.
    """
    pool: dict[tuple, int] = {}
    for r in other_rows:
        if is_meaningful(r):
            pool[signature(r)] = pool.get(signature(r), 0) + 1
    found = []
    for r in keeper_rows:
        sig = signature(r)
        if is_meaningful(r) and pool.get(sig, 0) > 0:
            pool[sig] -= 1
            found.append(r)
    return found


def _row(obj: ImportedStat) -> dict:
    out = {}
    for c in ImportedStat.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v if v is None or isinstance(v, (int, float, bool, str)) else str(v)
    return out


async def _lump(db, pid: uuid.UUID) -> dict:
    res = await db.execute(text("""
        SELECT COALESCE(SUM(matches),0) AS matches,
               COALESCE(SUM(batting_innings),0) AS innings,
               COALESCE(SUM(not_outs),0) AS not_outs,
               COALESCE(SUM(runs),0) AS runs,
               COALESCE(SUM(wickets),0) AS wickets,
               COALESCE(SUM(runs_conceded),0) AS runs_conceded,
               COALESCE(SUM(catches),0) AS catches
        FROM v_effective_player_season_stats
        WHERE player_id = :pid AND season_id IS NULL"""), {"pid": pid})
    return dict(res.mappings().first() or {})


async def run(org: str, keeper: str, other: str, apply: bool, row_ids: list[int] | None = None) -> dict:
    from app.routers.manual_entries import _log_edit
    from app.services import import_reconcile as recon

    kid, oid = uuid.UUID(keeper), uuid.UUID(other)
    async with async_session_maker() as db:
        org_id = (await db.execute(text(
            "SELECT id FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": org})).scalar()
        if org_id is None:
            raise SystemExit(f"no club matches {org!r}")
        names = {}
        for pid in (kid, oid):
            r = (await db.execute(text(
                "SELECT COALESCE(display_name_override, name) FROM players "
                "WHERE id = :p AND organisation_id = :o"), {"p": pid, "o": org_id})).scalar()
            if r is None:
                raise SystemExit(f"player {pid} is not in this club")
            names[pid] = r

        async def rows_for(pid):
            objs = (await db.execute(select(ImportedStat).where(
                ImportedStat.organisation_id == org_id, ImportedStat.player_id == pid)
                .order_by(ImportedStat.id))).scalars().all()
            return objs

        k_objs, o_objs = await rows_for(kid), await rows_for(oid)
        k_rows, o_rows = [_row(x) for x in k_objs], [_row(x) for x in o_objs]
        if row_ids:
            held = {r["id"] for r in k_rows}
            missing = [i for i in row_ids if i not in held]
            if missing:
                raise SystemExit(f"imported_stats row(s) {missing} are not held by {names[kid]} in this club")
            dupes = [r for r in k_rows if r["id"] in set(row_ids)]
        else:
            dupes = copies_of(k_rows, o_rows)
        dupe_ids = {d["id"] for d in dupes}

        before = await _lump(db, kid)
        print(f"Keeper: {names[kid]} ({kid})   other: {names[oid]} ({oid})")
        print(f"Imported rows held: keeper {len(k_rows)}, other {len(o_rows)}")
        print(f"Keeper's season-less line now: {before}")
        for r in k_rows:
            tag = ("REMOVE (named by --row-id)" if row_ids else "COPY of the other player's row") \
                if r["id"] in dupe_ids else "keep"
            print(f"  imported_stats #{r['id']} batch={r['import_batch_id']} scope={r['scope']} "
                  f"season={r['season_label'] or r['season_id']} grade={r['grade_label']} "
                  f"games={r['games_played']} inn={r['batting_innings']} runs={r['batting_runs']} "
                  f"wkts={r['bowling_wickets']} -> {tag}")

        # Hand-typed lines are reported, never removed.
        adj = (await db.execute(text("""
            SELECT a.player_id, a.games_played, a.batting_innings, a.batting_runs,
                   a.bowling_wickets, a.bowling_runs, a.fielding_catches
            FROM manual_career_adjustments a
            WHERE a.organisation_id = :o AND a.player_id = ANY(CAST(:ids AS uuid[]))"""),
            {"o": org_id, "ids": [kid, oid]})).mappings().all()
        for a in adj:
            who = "keeper" if a["player_id"] == kid else "other"
            print(f"  manual career adjustment ({who}): games={a['games_played']} "
                  f"inn={a['batting_innings']} runs={a['batting_runs']} "
                  f"wkts={a['bowling_wickets']} (edit in Manual Entries if wrong; never changed here)")

        if not dupes:
            print("\nNo copied rows found. Nothing to remove. If the lump is still wrong it comes "
                  "from a hand-typed adjustment or one combined row: edit it in Manual Entries.")
            return {"removed": 0, "applied": False}
        if not apply:
            print(f"\nDry run: would remove {len(dupes)} row(s) from {names[kid]}. "
                  "Re-run with --apply.")
            return {"removed": len(dupes), "applied": False}

        for obj in k_objs:
            if obj.id not in dupe_ids:
                continue
            row = _row(obj)
            await _log_edit(
                db, org_id=org_id, user_id=None, action="delete",
                target_table="imported_stats", target_id=str(obj.id),
                summary=(f"Removed imported line for {names[kid]} that was a copy of "
                         f"{names[oid]}'s (games {row['games_played']}, runs {row['batting_runs']})"),
                before=row, after=None)
            await db.delete(obj)
        await db.commit()

    written = await recon.reconcile_imported_totals(str(org_id))
    async with async_session_maker() as db:
        after = await _lump(db, kid)
    print(f"\nRemoved {len(dupes)} row(s); rebuilt {written} import delta rows.")
    print(f"Keeper's season-less line now: {after}")
    return {"removed": len(dupes), "applied": True, "after": after}


def main() -> None:
    argv = sys.argv[1:]
    row_ids: list[int] = []
    args: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--row-id" and i + 1 < len(argv):
            row_ids.append(int(argv[i + 1]))
            i += 2
            continue
        if a.startswith("--row-id="):
            row_ids.append(int(a.split("=", 1)[1]))
        elif not a.startswith("--"):
            args.append(a)
        i += 1
    if len(args) != 3:
        raise SystemExit(__doc__)
    asyncio.run(run(args[0], args[1], args[2], "--apply" in argv, row_ids or None))


if __name__ == "__main__":
    main()
