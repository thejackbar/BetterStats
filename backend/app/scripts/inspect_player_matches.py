"""Every copy of a player's matches on given dates, from every source, and whether each one counts.

Read-only. No write, no upstream call.

Reported off a live club: a player listed the same matches twice on his profile, once under the
Two Day tab and once under the One Day tab. Nothing readable from outside says WHAT the second
copy is: another club scorecard, a synced Cricket Australia game, a card linked to one of those, or
the same line counted twice from one game. This prints each row that holds the player on or near a
date, with how it is stored and whether the effective views serve it (`counts`), so the shape of the
double is known before anything is changed.

    python -m app.scripts.inspect_player_matches <org-id-or-slug> "<player name>" <YYYY-MM-DD> [...] [--window DAYS]

The name is matched the way Card review matches it (every word, or a close fit, so "richie" finds
"Ritchie"). `--window` is how many days either side to look (default 3: a two-day match is dated by
a different day in each source). Run it through compose:

    cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
    docker compose exec betterstats-backend python -m app.scripts.inspect_player_matches shoalwater-bay "peter ritchie" 2006-02-04 2007-01-13
"""
import asyncio
import sys
from datetime import date, timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import card_review_find as fnd

_SYNCED = """
    SELECT g.id::text AS id, g.played_at, g.match_format, g.home_team, g.away_team, g.opp_club_name,
           g.home_org_id::text AS home_org, g.away_org_id::text AS away_org,
           COALESCE(gr.display_name_override, gr.name) AS grade, s.name AS season,
           (SELECT tw.id::text FROM manual_games tw WHERE tw.superseded_by_game_id = g.id LIMIT 1) AS twin,
           (SELECT tw.pair_prefers_import FROM manual_games tw WHERE tw.superseded_by_game_id = g.id LIMIT 1) AS twin_shows,
           EXISTS (SELECT 1 FROM v_effective_games v WHERE v.id = g.id) AS counts
      FROM games g
      LEFT JOIN grades gr ON gr.id = g.grade_id
      LEFT JOIN seasons s ON s.id = gr.season_id
     WHERE g.played_at BETWEEN :lo AND :hi
       AND (EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = g.id AND b.player_id = ANY(CAST(:p AS UUID[])))
         OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = g.id AND w.player_id = ANY(CAST(:p AS UUID[]))))
     ORDER BY g.played_at, g.id
"""
_MANUAL = """
    SELECT m.id::text AS id, m.played_at, m.match_format, m.opposition, m.home_team, m.away_team,
           m.superseded_by_game_id::text AS linked_to, m.pair_prefers_import, m.pairing_locked,
           m.cricketstatz_import_id IS NOT NULL AS cricketstatz, m.extracted_payload IS NOT NULL AS photo,
           COALESCE(gr.display_name_override, gr.name) AS grade, s.name AS season,
           (SELECT l.after_json->>'filename' FROM manual_edit_logs l
             WHERE l.organisation_id = m.organisation_id AND l.action = 'import' AND l.undone_at IS NULL
               AND l.after_json->'created_game_ids' ? m.id::text ORDER BY l.created_at DESC LIMIT 1) AS file,
           EXISTS (SELECT 1 FROM v_effective_games v WHERE v.id = m.id) AS counts
      FROM manual_games m
      LEFT JOIN grades gr ON gr.id = m.grade_id
      LEFT JOIN seasons s ON s.id = m.season_id
     WHERE m.organisation_id = CAST(:org AS UUID) AND m.played_at BETWEEN :lo AND :hi
       AND (EXISTS (SELECT 1 FROM manual_batting_innings b WHERE b.manual_game_id = m.id AND b.player_id = ANY(CAST(:p AS UUID[])))
         OR EXISTS (SELECT 1 FROM manual_bowling_spells w WHERE w.manual_game_id = m.id AND w.player_id = ANY(CAST(:p AS UUID[]))))
     ORDER BY m.played_at, m.id
"""
_LINES = {
    "synced": ("SELECT innings_number, runs, dismissal_type, not_out FROM batting_innings WHERE game_id = CAST(:i AS UUID) AND player_id = ANY(CAST(:p AS UUID[])) ORDER BY innings_number",
               "SELECT innings_number, overs, runs, wickets FROM bowling_spells WHERE game_id = CAST(:i AS UUID) AND player_id = ANY(CAST(:p AS UUID[])) ORDER BY innings_number"),
    "manual": ("SELECT innings_number, runs, dismissal_type, not_out FROM manual_batting_innings WHERE manual_game_id = CAST(:i AS UUID) AND player_id = ANY(CAST(:p AS UUID[])) ORDER BY innings_number",
               "SELECT innings_number, overs, runs, wickets FROM manual_bowling_spells WHERE manual_game_id = CAST(:i AS UUID) AND player_id = ANY(CAST(:p AS UUID[])) ORDER BY innings_number"),
}


async def lines(db, kind, gid, pids):
    bat = [f"{r.runs}{'*' if r.not_out else ''} (inn {r.innings_number})" for r in
           (await db.execute(text(_LINES[kind][0]), {"i": gid, "p": pids})).all()]
    bowl = [f"{r.wickets}/{r.runs} off {r.overs} (inn {r.innings_number})" for r in
            (await db.execute(text(_LINES[kind][1]), {"i": gid, "p": pids})).all()]
    return "bat " + (", ".join(bat) or "-") + " | bowl " + (", ".join(bowl) or "-")


async def main(org: str, name: str, dates: list, window: int) -> None:
    async with async_session_maker() as db:
        org_id = (await db.execute(text("SELECT id::text FROM organisations WHERE id::text = :o OR slug = :o"),
                                   {"o": org})).scalar()
        if not org_id:
            print(f"No club '{org}'.")
            return
        who = await fnd.resolve_players(db, org_id, name)
        if not who["ids"]:
            print(f"No player at this club matches '{name}'.")
            return
        print(f"Player: {', '.join(who['names'])}{'  (closest match to ' + repr(name) + ')' if who['fuzzy'] else ''}"
              f"  [{len(who['ids'])} record(s)]")
        for d in dates:
            lo, hi = d - timedelta(days=window), d + timedelta(days=window)
            print(f"\n=== {d} (+/- {window} days)")
            counted = 0
            for r in (await db.execute(text(_SYNCED), {"lo": lo, "hi": hi, "p": who["ids"]})).mappings():
                counted += bool(r["counts"])
                opp = r["opp_club_name"] or f"{r['home_team']} v {r['away_team']}"
                twin = (f"club card {r['twin'][:8]} linked; site shows {'the club card' if r['twin_shows'] else 'this one'}"
                        if r["twin"] else "no club card linked")
                print(f"  SYNCED  {r['id'][:8]}  {r['played_at']}  {r['season']} / {r['grade']}  v {opp}  [{r['match_format'] or 'no format'}]"
                      f"  counts={'yes' if r['counts'] else 'no'}  ({twin})")
                print(f"          {await lines(db, 'synced', r['id'], who['ids'])}")
            for r in (await db.execute(text(_MANUAL), {"org": org_id, "lo": lo, "hi": hi, "p": who["ids"]})).mappings():
                counted += bool(r["counts"])
                src = "CricketStatz" if r["cricketstatz"] else f"file {r['file']}" if r["file"] else "photo" if r["photo"] else "typed in"
                link = (f"linked to game {r['linked_to'][:8]}, site shows {'the club card' if r['pair_prefers_import'] else 'Cricket Australia'}"
                        f"{', locked' if r['pairing_locked'] else ''}" if r["linked_to"] else "NOT linked")
                print(f"  CLUB    {r['id'][:8]}  {r['played_at']}  {r['season']} / {r['grade']}  v {r['opposition']}  [{r['match_format'] or 'no format'}]"
                      f"  counts={'yes' if r['counts'] else 'no'}  ({src}; {link})")
                print(f"          {await lines(db, 'manual', r['id'], who['ids'])}")
            print(f"  -> {counted} cop{'y' if counted == 1 else 'ies'} counted in the effective record")


if __name__ == "__main__":
    args = sys.argv[1:]
    window = 3
    if "--window" in args:
        i = args.index("--window")
        window = int(args[i + 1])
        del args[i:i + 2]
    if len(args) < 3:
        print(__doc__)
        sys.exit(2)
    asyncio.run(main(args[0], args[1], [date.fromisoformat(a) for a in args[2:]], window))
