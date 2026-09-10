"""Why is a club's career STILL doubled in production, with the fix deployed?

Read-only. No write, no upstream call. Safe to run against production.

The fix for the doubled CricketStatz-plus-Cricket-Australia totals is applied
on READ, in eight effective views, and depends at run time on three separate
things all holding at once:

  (A) the deployed views actually carry the pairing clause,
  (B) the pairing sweep actually ran AND wrote pairs for this club,
  (C) with A and B true, the aggregate view counts each match once.

Any one failing gives silent double-counting. From outside the box you cannot
tell which, so this prints all three for one club and names the failing one,
so a fix targets the real cause rather than the fifth guess.

    python -m app.scripts.diagnose_double_count <club-slug-or-name> [player-name] [year]

Examples:
    python -m app.scripts.diagnose_double_count keon-park
    python -m app.scripts.diagnose_double_count "Keon Park" "Quinsee" 2011
"""
import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import superseded_ddl


async def main(club: str, player: str | None, year: int | None) -> None:
    async with async_session_maker() as db:
        # --- resolve the club (slug first, then a name contains) --------------
        org = (await db.execute(text("""
            SELECT id, name, slug FROM organisations
             WHERE slug = :c OR name ILIKE :like
             ORDER BY (slug = :c) DESC
             LIMIT 1
        """), {"c": club, "like": f"%{club}%"})).mappings().first()
        if not org:
            print(f"!! no club matched {club!r}")
            return
        org_id = org["id"]
        print(f"club: {org['name']}  (slug={org['slug']}  id={org_id})\n")

        # --- (A) do the deployed views carry the pairing clause? --------------
        print("=== (A) effective views, read back from pg_get_viewdef ===")
        views_ok = await superseded_ddl.verify(db)
        for view, ok in views_ok.items():
            print(f"  {'ok ' if ok else 'BAD'}  {view}")
        a_bad = [v for v, ok in views_ok.items() if not ok]
        print()

        # --- (B) is this club's import actually paired? -----------------------
        print("=== (B) is this club's CricketStatz import paired away? ===")
        b = (await db.execute(text("""
            SELECT
              count(*) FILTER (WHERE cricketstatz_import_id IS NOT NULL) AS imported,
              count(*) FILTER (WHERE superseded_by_game_id IS NOT NULL)  AS paired,
              count(*) FILTER (WHERE pair_prefers_import)                AS prefers_import
            FROM manual_games WHERE organisation_id = :o
        """), {"o": org_id})).mappings().first()
        imported, paired = b["imported"], b["paired"]
        print(f"  imported manual games : {imported}")
        print(f"  of those, paired      : {paired}")
        print(f"  prefer the import copy: {b['prefers_import']}")
        # how many synced games are even candidates, for context (games is the
        # synced table; no source filter, which keeps this off any column a
        # create_all-only schema might lack)
        synced = (await db.execute(text("""
            SELECT count(*) FROM games g
              JOIN grades gr ON gr.id = g.grade_id
              JOIN seasons s ON s.id = gr.season_id
             WHERE s.organisation_id = :o
        """), {"o": org_id})).scalar()
        print(f"  (synced games for scale: {synced})")
        print()

        # --- (C) the aggregate split for one player ---------------------------
        if player:
            pl = (await db.execute(text("""
                SELECT id, COALESCE(display_name_override, name) AS nm
                  FROM players
                 WHERE organisation_id = :o
                   AND (name ILIKE :like OR display_name_override ILIKE :like)
                 ORDER BY nm LIMIT 5
            """), {"o": org_id, "like": f"%{player}%"})).mappings().all()
            if not pl:
                print(f"=== (C) no player matched {player!r} at this club ===\n")
            else:
                if len(pl) > 1:
                    print(f"(!) {len(pl)} players matched {player!r}; showing each")
                for p in pl:
                    print(f"=== (C) career header per view branch — {p['nm']} ({str(p['id'])[:8]}) ===")
                    rows = (await db.execute(text("""
                        SELECT source, COUNT(*) AS n,
                               COALESCE(SUM(matches),0) AS m,
                               COALESCE(SUM(batting_innings),0) AS i,
                               COALESCE(SUM(runs),0) AS r,
                               COALESCE(SUM(hundreds),0) AS h
                          FROM v_effective_player_season_stats
                         WHERE player_id = :p GROUP BY source ORDER BY source
                    """), {"p": p["id"]})).mappings().all()
                    tot_m = tot_r = 0
                    for r in rows:
                        print("    %-14s rows=%-4s M=%-5s Inn=%-5s Runs=%-6s 100s=%s"
                              % (r["source"], r["n"], r["m"], r["i"], r["r"], r["h"]))
                        tot_m += r["m"]; tot_r += r["r"]
                    print(f"    TOTAL career: matches={tot_m} runs={tot_r}")
                    print()

        # --- verdict ----------------------------------------------------------
        print("=== verdict ===")
        if a_bad:
            print("  (A) FAILS: these views do NOT carry the pairing clause in this")
            print("      database, so every shared match double-counts regardless of")
            print("      pairing: " + ", ".join(a_bad))
            print("      => something reverted the views AFTER boot applied them.")
            print("         Run superseded_ddl.STATEMENTS (or the hourly repair job),")
            print("         then find the reverter: grep the Postgres log for")
            print("         'CREATE OR REPLACE VIEW v_effective' (log_statement=ddl).")
        elif imported and paired == 0:
            print("  (B) FAILS: this club has an import but NOTHING is paired, so both")
            print("      sources are counted in full. The sweep did not run or matched")
            print("      nothing. Check the boot log for 'Match pairing for <org>' and")
            print("      run:  python -m app.scripts.pair_imported_matches "
                  f"{org['slug'] or org_id} --apply")
        elif imported and paired < imported * 0.5:
            print(f"  (B) SUSPECT: only {paired} of {imported} imported games paired.")
            print("      The matcher is missing this club's records (its fixtures may")
            print("      carry a bare club name on both sides). The unpaired ones still")
            print("      double-count. Re-run the sweep; if still low, the matcher needs")
            print("      work for this club's data shape.")
        elif not imported:
            print("  This club holds no CricketStatz import — double-counting here is")
            print("  NOT the import/sync union. Look elsewhere (shared fixtures, merges).")
        else:
            print(f"  (A) ok and (B) ok ({paired}/{imported} paired). If a career still")
            print("      reads doubled, it is (C): inspect the per-branch split above —")
            print("      if BOTH 'api' and 'manual_game' report the same matches, the")
            print("      aggregate view is still counting a paired import. If only one")
            print("      does, the doubling is a DIFFERENT bug, not this union.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    _player = sys.argv[2] if len(sys.argv) > 2 else None
    _year = int(sys.argv[3]) if len(sys.argv) > 3 else None
    asyncio.run(main(sys.argv[1], _player, _year))
