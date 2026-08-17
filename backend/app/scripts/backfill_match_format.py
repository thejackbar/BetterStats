"""Fill in ``games.match_format`` from Cricket Australia's own fixture list.

WHY THIS EXISTS
---------------
``games.match_format`` is what BetterFees charges a match day from:
``services.fees.derive_fee_format`` maps "Two Day" to two days and everything
else — including a blank — to one. The Grassroots sync never wrote the column,
so every synced game carried NULL and every two-day fixture was billed as a
single day. A club running turf grades was under-charging half its season.

The sync writes it now, for new fixtures and (via the bulk pass beside
``is_final``) for the games each run rediscovers. This script is the
retroactive half: it covers every season the club holds, not just the window
an incremental run happens to scan, so a club's history corrects without a
Full Rebuild.

WHY THE FIXTURE AND NOT THE GRADE
---------------------------------
A grade is not one format. Applecross 5th Grade in 2025/26 is 32 one-day
fixtures and 26 two-day ones, and CA reports the format per MATCH. That is why
the grade-level ``fee_format`` override cannot answer this: setting a mixed
grade to two_day would charge its one-day fixtures double. Leave those
overrides for what they are for — telling a women's grade apart from a men's
one, and excluding a grade from fees entirely.

WHAT IT TOUCHES
---------------
``games.match_format`` only, for games under the named club's own grades, and
only where CA actually reports a format. It never edits a fee row directly —
pass ``--recompute`` (or press "Sync Match Days" on the Accounts page) to have
``services.fees.recompute_fee_match_days`` re-derive the match days, which
leaves an admin-overridden or already-paid row alone by its own rules.

USAGE
-----
    python -m app.scripts.backfill_match_format <org-id-or-slug>              # dry run
    python -m app.scripts.backfill_match_format <org-id-or-slug> --apply
    python -m app.scripts.backfill_match_format <org-id-or-slug> --apply --recompute
    python -m app.scripts.backfill_match_format <org-id-or-slug> --apply --season 2025
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr


async def run(org_ref: str, apply: bool, recompute: bool, season_year: int | None) -> int:
    async with async_session_maker() as db:
        try:
            org_id = str(uuid.UUID(org_ref))
            org_where, param = "id = CAST(:ref AS UUID)", org_id
        except ValueError:
            org_where, param = "LOWER(slug) = LOWER(:ref)", org_ref
        org = (await db.execute(
            text(f"SELECT id, name FROM organisations WHERE {org_where}"),
            {"ref": param},
        )).mappings().first()
        if not org:
            print(f"No club found for {org_ref!r} (pass an organisation id or public slug).")
            return 1

        print(f"Club: {org['name']} ({org['id']})")

        # COALESCE(grassroots_id, id) is the raw CA grade GUID — the per-club
        # uuid5 id minted on a cross-club grade collision is ours alone and
        # means nothing to /scores/grades/{id}/matches.
        season_clause = "AND s.year = :yr" if season_year is not None else ""
        grades = (await db.execute(
            text(f"""
                SELECT g.id AS grade_id,
                       COALESCE(g.grassroots_id, CAST(g.id AS TEXT)) AS guid,
                       g.name AS grade_name,
                       s.name AS season_name
                  FROM grades g
                  JOIN seasons s ON s.id = g.season_id
                 WHERE s.organisation_id = CAST(:org AS UUID) {season_clause}
                 ORDER BY s.year DESC NULLS LAST, g.name
            """),
            {"org": str(org["id"]), "yr": season_year},
        )).mappings().all()

        if not grades:
            print("No grades found for that club (or that season).")
            return 1

        print(f"Scanning {len(grades)} grade(s) …\n")

        # match id → format, gathered across every grade before a single write:
        # two clubs in one grade share a match row, and one fixture can be
        # reached through more than one of our grades.
        wanted: dict[str, str] = {}
        no_format_grades: list[str] = []
        for gd in grades:
            try:
                matches = await gr.get_grade_matches(gd["guid"])
            except Exception as e:  # a grade CA no longer serves is not fatal
                print(f"  ! {gd['season_name']} / {gd['grade_name']}: {e}")
                continue
            found = 0
            for m in matches:
                mid, fmt = m.get("id"), (m.get("matchType") or "").strip()
                # "BYE" is not a format — see the same guard in services/sync.py.
                if mid and fmt and fmt.upper() != "BYE":
                    wanted[mid] = fmt
                    found += 1
            if not found:
                no_format_grades.append(f"{gd['season_name']} / {gd['grade_name']}")

        if not wanted:
            print("CA reported no match formats at all — nothing to do.")
            return 1

        # Restrict to games we actually hold, under THIS club's grades. A grade
        # match list is competition-wide, so it names plenty of fixtures that
        # are not ours and that we must not touch.
        ids = []
        for mid in wanted:
            try:
                ids.append(uuid.UUID(mid))
            except ValueError:
                pass

        ours = (await db.execute(
            text("""
                SELECT gm.id, gm.match_format
                  FROM games gm
                  JOIN grades g ON g.id = gm.grade_id
                  JOIN seasons s ON s.id = g.season_id
                 WHERE s.organisation_id = CAST(:org AS UUID)
                   AND gm.id = ANY(:ids)
            """),
            {"org": str(org["id"]), "ids": ids},
        )).mappings().all()

        changes: dict[str, list[uuid.UUID]] = {}
        before = Counter()
        unchanged = 0
        for row in ours:
            fmt = wanted.get(str(row["id"]))
            before[row["match_format"] or "(blank)"] += 1
            if fmt and row["match_format"] != fmt:
                changes.setdefault(fmt, []).append(row["id"])
            else:
                unchanged += 1

        print(f"Games held under this club's grades: {len(ours)}")
        print("  currently stored as: " + ", ".join(f"{k}×{v}" for k, v in before.most_common()))
        if no_format_grades:
            print(f"  ({len(no_format_grades)} grade(s) returned no format — left alone)")
        if not changes:
            print("\nEvery game already matches CA. Nothing to change.")
            return 0

        total = sum(len(v) for v in changes)
        print(f"\n{'Updating' if apply else 'Would update'} {total} game(s):")
        for fmt, gids in sorted(changes.items(), key=lambda kv: -len(kv[1])):
            print(f"  → {fmt}: {len(gids)}")
        print(f"  (unchanged: {unchanged})")

        if not apply:
            print("\nDry run — re-run with --apply to write these.")
            return 0

        for fmt, gids in changes.items():
            await db.execute(
                text("UPDATE games SET match_format = :fmt WHERE id = ANY(:ids)"),
                {"fmt": fmt, "ids": gids},
            )
        await db.commit()
        print("\nWritten.")

        if not recompute:
            print("Now press \"Sync Match Days\" on the Accounts page for each affected "
                  "season (or re-run with --recompute) to re-derive the fee rows.")
            return 0

    # Fees recompute opens its own session per season, so it sits outside the
    # block above rather than nesting a second session inside it.
    from app.services.fees import recompute_fee_match_days

    async with async_session_maker() as db:
        seasons = (await db.execute(
            text("""
                SELECT DISTINCT s.id, s.name
                  FROM seasons s
                  JOIN grades g ON g.season_id = s.id
                  JOIN games gm ON gm.grade_id = g.id
                 WHERE s.organisation_id = CAST(:org AS UUID)
                   AND gm.id = ANY(:ids)
                 ORDER BY s.name
            """),
            {"org": str(org["id"]), "ids": [i for v in changes.values() for i in v]},
        )).mappings().all()

    for s in seasons:
        res = await recompute_fee_match_days(org["id"], s["id"])
        print(f"  {s['name']}: {res['entries_upserted']} fee row(s) updated, "
              f"{res['entries_deleted']} stale removed")
    print("\nDone.")
    return 0


def main() -> None:
    args = [a for a in sys.argv[1:]]
    apply = "--apply" in args
    recompute = "--recompute" in args
    season_year = None
    if "--season" in args:
        i = args.index("--season")
        if i + 1 >= len(args):
            print("--season needs a year, e.g. --season 2025")
            raise SystemExit(2)
        try:
            season_year = int(args[i + 1])
        except ValueError:
            print(f"--season wants a 4-digit year, got {args[i + 1]!r}")
            raise SystemExit(2)
        del args[i:i + 2]
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(run(positional[0], apply, recompute, season_year)))


if __name__ == "__main__":
    main()
