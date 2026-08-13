"""Tidy a club's season list into the uniform "Summer YYYY/YY" form.

WHY THESE EXIST
---------------
A club whose history was loaded through BetterImport (or hand-created via
Manual Entries) often ends up with two season rows per real-world season:
the synced "Summer 1968/69" (grassroots_id set, year set) and a bare
"1968/69" the import created (grassroots_id NULL, no year). Older eras the
sync never covered exist only as the bare form. The seasons page then reads
as an unsorted mix of the two spellings — reported for Yarraville.

WHAT IT DOES
------------
Only manually-created seasons (grassroots_id IS NULL — every synced season
carries the raw CA GUID there) are ever touched. A synced season is never
renamed, re-yeared, merged or otherwise written. For each manual season
whose name carries a recognisable season token ("1968/69", "1968-69",
"1968/1969"):

- A synced season for the same year exists  ->  MERGE: the manual season is
  aliased into it via the club's own Merge Seasons machinery
  (season_aliases), so the pair display and aggregate as one season. Fully
  reversible from Admin -> Seasons -> merge history, or the season-merges
  undo endpoint.
- No synced season for that year  ->  RENAME to "Summer YYYY/YY" and set
  the year column, so it sorts and reads like the rest.
- Two manual seasons for one year with no synced sibling  ->  the better
  named (or fuller) one becomes the canonical and the other is aliased
  into it.

A manual season whose name doesn't parse as a season token is reported and
left alone — the script must never guess at what a hand-named season means.

USAGE
-----
    python -m app.scripts.cleanup_seasons <org-id-or-slug>           # dry run
    python -m app.scripts.cleanup_seasons <org-id-or-slug> --apply
"""
from __future__ import annotations

import asyncio
import re
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.season_aliases import load_reverse_alias_map

# "1968/69", "1968-69", "1968/1969" — anywhere in the name, so the synced
# "Summer 1968/69" parses too (grouping needs both sides of a pair).
_TOKEN = re.compile(r"(\d{4})\s*[/\-–]\s*(\d{2}|\d{4})")


def season_start_year(name: str) -> int | None:
    """The starting year of the season a name refers to, or None.

    Only accepts a consecutive pair ("1968/69", "1968/1969") — a name like
    "1968/72" is somebody's own labelling, not a season token we understand.
    """
    m = _TOKEN.search(name or "")
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    expected = (start + 1) % 100 if len(end_raw) == 2 else start + 1
    return start if int(end_raw) == expected else None


def canonical_name(start: int) -> str:
    return f"Summer {start}/{(start + 1) % 100:02d}"


def _data_note(s) -> str:
    bits = []
    if s["stat_rows"]:
        bits.append(f"{s['stat_rows']} stat row(s)")
    if s["grade_rows"]:
        bits.append(f"{s['grade_rows']} grade(s)")
    if s["manual_game_rows"]:
        bits.append(f"{s['manual_game_rows']} manual game(s)")
    return ", ".join(bits) if bits else "empty"


async def run(org_ref: str, apply: bool) -> int:
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
        org_id = str(org["id"])

        seasons = (await db.execute(
            text("""
                SELECT s.id, s.name, s.year, s.grassroots_id,
                       (SELECT COUNT(*) FROM player_season_stats pss WHERE pss.season_id = s.id) AS stat_rows,
                       (SELECT COUNT(*) FROM grades g WHERE g.season_id = s.id) AS grade_rows,
                       (SELECT COUNT(*) FROM manual_games mg WHERE mg.season_id = s.id) AS manual_game_rows
                FROM seasons s
                WHERE s.organisation_id = CAST(:org AS UUID)
            """),
            {"org": org_id},
        )).mappings().all()
        if not seasons:
            print(f"{org['name']}: no seasons at all. Nothing to do.")
            return 0

        already_aliased = await load_reverse_alias_map(db, org_id)
        names_in_use = {(s["name"] or "").strip().lower() for s in seasons}

        # Group every un-aliased season by the year its name refers to.
        by_year: dict[int, list] = {}
        unrecognised = []
        for s in seasons:
            if str(s["id"]) in already_aliased:
                continue  # already merged into something — leave the history alone
            start = season_start_year(s["name"])
            if start is None:
                if s["grassroots_id"] is None:
                    unrecognised.append(s)
                continue
            by_year.setdefault(start, []).append(s)

        merges = []    # (manual_season, canonical_season)
        renames = []   # (manual_season, new_name, year)
        year_fills = []  # (manual_season, year) — name already right, year missing
        skipped = []   # (season, reason)

        for start in sorted(by_year, reverse=True):
            group = by_year[start]
            canon = canonical_name(start)
            synced = [s for s in group if s["grassroots_id"] is not None]
            manual = [s for s in group if s["grassroots_id"] is None]
            if not manual:
                continue

            target = None
            if synced:
                exact = [s for s in synced if (s["name"] or "").strip().lower() == canon.lower()]
                if exact:
                    target = exact[0]
                elif len(synced) == 1:
                    target = synced[0]
                else:
                    # Several synced seasons share the year (e.g. a masters comp
                    # under its own CA season id) and none is the plain Summer
                    # one — a person should pick the merge target.
                    for s in manual:
                        skipped.append((s, f"{len(synced)} synced seasons for {start} and none named {canon!r}"))
                    continue
            else:
                # No synced sibling: the best manual season becomes canonical.
                target = max(manual, key=lambda s: (
                    (s["name"] or "").strip().lower() == canon.lower(),
                    s["stat_rows"] + s["grade_rows"] + s["manual_game_rows"],
                    str(s["id"]),
                ))
                new_name = canon if (target["name"] or "").strip().lower() != canon.lower() else None
                if new_name and new_name.lower() in names_in_use:
                    skipped.append((target, f"another season already holds the name {new_name!r}"))
                elif new_name:
                    renames.append((target, new_name, start))
                    names_in_use.add(new_name.lower())
                elif target["year"] is None:
                    year_fills.append((target, start))

            for s in manual:
                if s["id"] == target["id"]:
                    continue
                merges.append((s, target))

        print(f"{org['name']} — {len(seasons)} season(s), "
              f"{sum(1 for s in seasons if s['grassroots_id'] is None)} manually created, "
              f"{len(already_aliased)} already merged away\n")

        if merges:
            print(f"{len(merges)} duplicate(s) {'merged' if apply else 'to merge'} into their proper season:")
            for s, target in merges:
                print(f"  {'MERGE' if apply else 'would merge'}  {s['name']!r:<22} -> {target['name']!r}"
                      f"   ({_data_note(s)})")
        if renames:
            print(f"\n{len(renames)} season(s) {'renamed' if apply else 'to rename'} (no synced season for that year):")
            for s, new_name, year in renames:
                print(f"  {'RENAME' if apply else 'would rename'}  {s['name']!r:<22} -> {new_name!r}, year {year}"
                      f"   ({_data_note(s)})")
        if year_fills:
            print(f"\n{len(year_fills)} season(s) already named right, just missing the year:")
            for s, year in year_fills:
                print(f"  {'SET YEAR' if apply else 'would set year'}  {s['name']!r} -> {year}")
        if not merges and not renames and not year_fills:
            print("Nothing to change — the list is already uniform.")

        if skipped:
            print(f"\n{len(skipped)} season(s) left alone (decide these by hand):")
            for s, reason in skipped:
                print(f"  KEPT  {s['name']!r:<22} — {reason}")
        if unrecognised:
            print(f"\n{len(unrecognised)} manually-created season(s) whose name isn't a season token:")
            for s in unrecognised:
                print(f"  KEPT  {s['name']!r:<22} ({_data_note(s)})")

        if not apply:
            if merges or renames or year_fills:
                print("\nDRY RUN — nothing changed. Re-run with --apply to make these changes.")
            return 0

        for s, target in merges:
            # Mirror the Merge Seasons endpoint: if anything was previously
            # merged INTO this season, re-point those aliases at the new
            # canonical so resolution stays single-hop.
            await db.execute(
                text("UPDATE season_aliases SET canonical_season_id = :new "
                     "WHERE org_id = CAST(:org AS UUID) AND canonical_season_id = :old AND undone_at IS NULL"),
                {"new": str(target["id"]), "org": org_id, "old": str(s["id"])},
            )
            await db.execute(
                text("INSERT INTO season_aliases (org_id, canonical_season_id, alias_season_id) "
                     "VALUES (CAST(:org AS UUID), :c, :a)"),
                {"org": org_id, "c": str(target["id"]), "a": str(s["id"])},
            )
        for s, new_name, year in renames:
            await db.execute(
                text("UPDATE seasons SET name = :name, year = :year WHERE id = :id"),
                {"name": new_name, "year": year, "id": str(s["id"])},
            )
        for s, year in year_fills:
            await db.execute(
                text("UPDATE seasons SET year = :year WHERE id = :id"),
                {"year": year, "id": str(s["id"])},
            )
        await db.commit()
        print(f"\nDone: {len(merges)} merged, {len(renames)} renamed, {len(year_fills)} year(s) filled in.")
        print("A merge can be undone from Admin -> Seasons (merge history); renames are plain name edits.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        return 1
    return asyncio.run(run(positional[0], apply))


if __name__ == "__main__":
    raise SystemExit(main())
