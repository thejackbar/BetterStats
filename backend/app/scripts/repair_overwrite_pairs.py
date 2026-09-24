"""Pair the matches an overwrite import missed, for a club already imported.

The CSV import's duplicate check used to recognise a synced twin on its date
and opponent alone, indexed from the club's own season — so a fixture the
OTHER club synced first, an opponent the two sources spell with no word in
common, or a two-day match each side dates differently all landed as a NEW
manual game beside the synced one, and that match counted twice. The import
takes a second look on the scorecards now (`manual_entries._match_unmatched_by_scores`);
this is the same second look, run after the fact over what an earlier import
left unpaired.

Only matches an IMPORT created are considered — read off the import's own
audit rows — never a game somebody typed in by hand, and only in a season the
club re-sourced. A pair it writes is exactly what the import would have
written: locked, the import's copy preferred, the synced game stepping aside
on read. Nothing is deleted, and undoing the import still takes the pair with
it because the row is the import's own.

Dry run by default. A match it cannot pair is left counted on its own, which
is visible, rather than paired to the wrong fixture, which is not.

    python -m app.scripts.repair_overwrite_pairs                 # every club, dry run
    python -m app.scripts.repair_overwrite_pairs <org|all> --apply
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import match_pairing as mp

_ORGS_SQL = """
    SELECT DISTINCT s.organisation_id, o.name
      FROM seasons s
      JOIN organisations o ON o.id = s.organisation_id
     WHERE s.import_authoritative
     ORDER BY o.name
"""

_ONE_ORG_SQL = """
    SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o
"""

# The manual games an import created, still unpaired, in a re-sourced season.
# `manual_edit_logs.after_json->'created_game_ids'` is the import's own record
# of what it wrote; a hand-typed game is never in it.
_CANDIDATES_SQL = """
    WITH imported AS (
        SELECT DISTINCT (jsonb_array_elements_text(l.after_json->'created_game_ids'))::uuid AS id
          FROM manual_edit_logs l
         WHERE l.organisation_id = :org
           AND l.action = 'import'
           AND l.target_table = 'manual_games'
           AND l.undone_at IS NULL
    )
    SELECT mg.id::text AS id, mg.played_at,
           COALESCE(mg.opposition, '') AS opposition,
           COALESCE(mg.home_team, '') AS home_team,
           COALESCE(mg.away_team, '') AS away_team,
           s.name AS season_name
      FROM manual_games mg
      JOIN imported i ON i.id = mg.id
      JOIN seasons s ON s.id = mg.season_id
     WHERE mg.organisation_id = :org
       AND s.import_authoritative
       AND mg.superseded_by_game_id IS NULL
       AND mg.cricketstatz_import_id IS NULL
"""

_PAIR_SQL = """
    UPDATE manual_games
       SET superseded_by_game_id = CAST(:game AS UUID),
           pair_prefers_import = TRUE,
           pairing_locked = TRUE
     WHERE id = CAST(:mg AS UUID) AND organisation_id = :org
       AND superseded_by_game_id IS NULL
"""


async def repair_org(db, org_id, *, apply: bool) -> dict:
    org = str(org_id)
    club_tokens = mp.team_tokens((await db.execute(
        text(mp._CLUB_NAME_SQL), {"org": org})).scalar() or "")
    rows = (await db.execute(text(_CANDIDATES_SQL), {"org": org})).mappings().all()
    if not rows:
        return {"candidates": 0, "paired": 0, "pairs": []}
    cards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": [r["id"] for r in rows]})
    imported: list[mp.MatchRow] = []
    by_id: dict = {}
    for r in rows:
        ours, opp = mp.split_sides(r["home_team"], r["away_team"], r["opposition"], club_tokens)
        m = mp.MatchRow(r["id"], r["played_at"], opp, frozenset(cards.get(r["id"], ())), ours)
        imported.append(m)
        by_id[r["id"]] = r
    dates = [m.played_at for m in imported if m.played_at is not None]
    from_day = to_day = None
    if dates:
        span = timedelta(days=mp.WINDOW_DAYS)
        from_day, to_day = min(dates) - span, max(dates) + span
    synced = await mp.load_synced(db, org_id, club_tokens=club_tokens,
                                  from_day=from_day, to_day=to_day,
                                  exclude_twinned=True)
    syn_by_id = {m.id: m for m in synced}
    pairs = []
    for mg_id, (game_id, _prefer) in mp.assign(imported, synced).items():
        imp, syn, r = next(m for m in imported if m.id == mg_id), syn_by_id[game_id], by_id[mg_id]
        pairs.append({
            "manual_game_id": mg_id, "game_id": game_id,
            "season": r["season_name"],
            "import_date": imp.played_at, "synced_date": syn.played_at,
            "import_opp": imp.opposition, "synced_opp": syn.opposition,
            "shared_scores": len(imp.signature & syn.signature),
        })
        if apply:
            await db.execute(text(_PAIR_SQL),
                             {"game": game_id, "mg": mg_id, "org": org})
    if apply:
        await db.commit()
    return {"candidates": len(rows), "paired": len(pairs), "pairs": pairs}


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    which = args[0] if args else "all"

    async with async_session_maker() as db:
        if which == "all":
            orgs = (await db.execute(text(_ORGS_SQL))).all()
        else:
            orgs = (await db.execute(text(_ONE_ORG_SQL), {"o": which})).all()
            if not orgs:
                raise SystemExit(f"no club matches {which!r}")
    if not orgs:
        print("No club has re-sourced a season from an import.")
        return

    print("DRY RUN — nothing written (pass --apply to pair)" if not apply else "APPLYING")
    for org_id, name in orgs:
        try:
            async with async_session_maker() as db:
                res = await repair_org(db, org_id, apply=apply)
        except Exception as exc:  # one club is never the whole run
            print(f"  {name}: FAILED — {type(exc).__name__}: {exc}")
            continue
        print(f"  {name}: {res['candidates']} unpaired imported match(es) in "
              f"re-sourced seasons, {res['paired']} now pair to a synced game")
        for p in sorted(res["pairs"], key=lambda x: (x["season"], str(x["import_date"]))):
            print(f"      {p['season']}: import {p['import_date']} v {p['import_opp'] or '?'}"
                  f"  <->  synced {p['synced_date']} v {p['synced_opp'] or '?'}"
                  f"  ({p['shared_scores']} shared scores)")


if __name__ == "__main__":
    asyncio.run(main())
