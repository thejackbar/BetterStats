"""Remove season-totals import rows a club has decided it does not want. Dry run unless --apply.

Written for Hamilton Veterans (Nov 2026). It reads the club's answers from either of two CSVs:

  * `ops/diagnostics/import_only_games.sql`, games only the sheet holds, with a "Keep? (Y/N)" column.
    Rows marked N are removed; Y or blank is kept.
  * `ops/diagnostics/sheet_vs_cards_decide.sql`, where the sheet and the typed scorecards disagree, with a
    "Which is right? (Cards or Sheet)" column. Rows marked Cards have the sheet's rows removed, so the season
    shows the cards alone. Sheet or blank removes nothing (a wrong scorecard is the club's to correct).

  * It removes only `imported_stats` rows, by id, and only rows that belong to the club and sit in a
    batch that has not been undone. An id that is not the club's, or is already gone, is listed and
    skipped, never guessed at.
  * Every row it removes goes, whole, into one `audit_logs` entry in the same transaction.
    `--restore AUDIT_ID` puts exactly those rows back with their original ids, skipping any that are
    already back. An entry restores once.
  * The club's derived totals are rebuilt straight after (`reconcile_imported_totals`), both ways.
  * Dry run by default. `--apply` needs `--expect N` (the number of rows the plan removes) and
    `--by "name"`. One club per run. Database only.

Usage, from the server (the CSV has to be inside the container, for example `docker compose cp`):
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose cp hamilton_marked.csv betterstats-backend:/tmp/hamilton_marked.csv
  docker compose exec -T betterstats-backend python -u -m app.scripts.drop_import_rows <org_id_or_slug> --csv /tmp/hamilton_marked.csv
  docker compose exec -T betterstats-backend python -u -m app.scripts.drop_import_rows <org> --csv /tmp/hamilton_marked.csv --apply --expect N --by "your name"
  docker compose exec -T betterstats-backend python -u -m app.scripts.drop_import_rows <org> --restore AUDIT_ID --by "your name"
A few rows by hand instead of a CSV: --ids "12 15 31".
"""
import argparse
import asyncio
import csv
import json

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts.audit_twelfth_man import _resolve_org, say

ACTION = "drop_import_rows"
RESTORE_ACTION = "drop_import_rows_restore"
KEEP_COLUMN = "Keep? (Y/N)"
DECIDE_COLUMN = "Which is right? (Cards or Sheet)"
IDS_COLUMN = "Sheet row ids (leave)"


def ids_from_csv(path: str) -> list[int]:
    """The sheet row ids of every row the club decided should go. A mark that is not one of the words
    the column asks for is refused, naming the line, so a typo is never read as "keep"."""
    out: list[int] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        if IDS_COLUMN not in fields:
            raise SystemExit(f"The file has no '{IDS_COLUMN}' column. It must be a list from import_only_games.sql "
                             f"or sheet_vs_cards_decide.sql.")
        if DECIDE_COLUMN in fields:
            column, remove, keep = DECIDE_COLUMN, ("cards", "card", "typed", "cards are right"), \
                ("", "sheet", "sheet is right")
            words = "Cards or Sheet"
        elif KEEP_COLUMN in fields:
            column, remove, keep = KEEP_COLUMN, ("n", "no", "drop", "remove"), ("", "y", "yes", "keep")
            words = "Y or N"
        else:
            raise SystemExit(f"The file has neither a '{KEEP_COLUMN}' nor a '{DECIDE_COLUMN}' column.")
        for n, row in enumerate(reader, start=2):
            mark = (row.get(column) or "").strip().lower()
            if mark in keep:
                continue
            if mark not in remove:
                raise SystemExit(f"Line {n}: '{row.get(column)}' is not {words}. Fix it and run again.")
            try:
                out += [int(x) for x in (row.get(IDS_COLUMN) or "").split()]
            except ValueError:
                raise SystemExit(f"Line {n}: the row ids are not numbers: {row.get(IDS_COLUMN)!r}")
    return out


async def plan(org: str, ids: list[int]) -> tuple[list[dict], list[int]]:
    """(rows that would be removed, ids that cannot be)."""
    async with async_session_maker() as s:
        rows = (await s.execute(text("""
            SELECT i.id, to_jsonb(i) AS row, COALESCE(p.display_name_override, p.name) AS player,
                   COALESCE(se.name, i.season_label) AS season, i.grade_label, i.games_played,
                   i.batting_runs, i.bowling_wickets, b.filename
              FROM imported_stats i
              JOIN import_batches b ON b.id = i.import_batch_id AND b.undone_at IS NULL
              JOIN players p ON p.id = i.player_id
              LEFT JOIN seasons se ON se.id = i.season_id
             WHERE i.organisation_id = CAST(:o AS UUID) AND i.id = ANY(CAST(:ids AS int[]))
             ORDER BY se.year, p.name, i.id"""), {"o": org, "ids": sorted(set(ids))})).mappings().all()
    found = {r["id"] for r in rows}
    return [dict(r) for r in rows], sorted(set(ids) - found)


def show(rows: list[dict], missing: list[int]) -> None:
    say(f"\n{len(rows)} sheet row(s) would be removed:")
    for r in rows:
        say(f"  #{r['id']:<6} {r['player']:<26} {str(r['season']):<16} {str(r['grade_label'] or '-'):<18} "
            f"{r['games_played']} games, {r['batting_runs']} runs, {r['bowling_wickets']} wkts   ({r['filename']})")
    if missing:
        say(f"\nSkipped, not this club's or already gone: {missing}")


async def _rebuild(org: str) -> None:
    from app.services.import_reconcile import reconcile_imported_totals
    say(f"Totals rebuilt: {await reconcile_imported_totals(org)} import row(s) derived.")


async def apply(org: str, rows: list[dict], expect: int | None, by: str | None) -> int:
    if expect != len(rows):
        raise SystemExit(f"\nRefusing: --expect {expect} but the plan removes {len(rows)} rows. Re-read the plan.")
    if not by:
        raise SystemExit('\nRefusing: --by "your name" is required, it goes in the audit entry.')
    async with async_session_maker() as s:
        audit_id = (await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB)) RETURNING id"),
            {"o": org, "a": ACTION, "d": json.dumps({"by": by, "rows": [r["row"] for r in rows]}, default=str)})).scalar()
        await s.execute(text("DELETE FROM imported_stats WHERE organisation_id = CAST(:o AS UUID) AND id = ANY(CAST(:ids AS int[]))"),
                        {"o": org, "ids": [r["id"] for r in rows]})
        await s.commit()
    say(f"\nREMOVED {len(rows)} row(s). Audit entry {audit_id}. To undo: --restore {audit_id} --by \"your name\"")
    await _rebuild(org)
    return audit_id


async def restore(audit_id: int, by: str | None) -> int:
    if not by:
        raise SystemExit('Refusing: --by "your name" is required.')
    async with async_session_maker() as s:
        entry = (await s.execute(text(
            "SELECT org_id::text AS org, details, action FROM audit_logs WHERE id = :i"), {"i": audit_id})).mappings().first()
        if not entry or entry["action"] != ACTION:
            raise SystemExit(f"Audit entry {audit_id} is not a {ACTION} entry.")
        details = entry["details"] if isinstance(entry["details"], dict) else json.loads(entry["details"])
        again = (await s.execute(text(
            "SELECT created_at::text FROM audit_logs WHERE action = :a AND details->>'from_audit' = :i"),
            {"a": RESTORE_ACTION, "i": str(audit_id)})).scalar()
        if again:
            raise SystemExit(f"Audit entry {audit_id} was already restored ({again}).")
        back = 0
        for r in details["rows"]:
            res = await s.execute(text(
                "INSERT INTO imported_stats SELECT * FROM jsonb_populate_record(NULL::imported_stats, CAST(:r AS JSONB)) "
                "ON CONFLICT (id) DO NOTHING"), {"r": json.dumps(r)})
            back += res.rowcount
        await s.execute(text(
            "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
            "VALUES (CAST(:o AS UUID), NULL, :a, 'organisation', :o, CAST(:d AS JSONB))"),
            {"o": entry["org"], "a": RESTORE_ACTION, "d": json.dumps({"by": by, "from_audit": audit_id, "rows": back})})
        await s.commit()
    say(f"RESTORED {back} row(s) from audit entry {audit_id}.")
    await _rebuild(entry["org"])
    return back


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug")
    ap.add_argument("--csv", help="a list from import_only_games.sql (Y/N) or sheet_vs_cards_decide.sql (Cards/Sheet), with the club's marks")
    ap.add_argument("--ids", help="sheet row ids, space separated, instead of a CSV")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--by")
    ap.add_argument("--restore", type=int, metavar="AUDIT_ID")
    a = ap.parse_args()
    org = await _resolve_org(a.org)
    if a.restore:
        await restore(a.restore, a.by)
        return
    if bool(a.csv) == bool(a.ids):
        raise SystemExit("Give exactly one of --csv or --ids.")
    ids = ids_from_csv(a.csv) if a.csv else [int(x) for x in a.ids.split()]
    if not ids:
        raise SystemExit("Nothing is marked for removal (N, or Cards): nothing to remove.")
    rows, missing = await plan(org, ids)
    show(rows, missing)
    if not a.apply:
        say("\nDry run. Nothing was changed. Add --apply --expect N --by \"your name\" to remove these.")
        return
    await apply(org, rows, a.expect, a.by)


if __name__ == "__main__":
    asyncio.run(main())
