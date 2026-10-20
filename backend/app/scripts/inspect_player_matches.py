"""Every copy of a player's matches on given dates, from every source, and whether each one counts.

Read-only. No write, no upstream call.

Reported off a live club: a player listed the same matches twice on his profile, once under the
Two Day tab and once under the One Day tab. Nothing readable from outside says WHAT the second
copy is: another club scorecard, a synced Cricket Australia game, a card linked to one of those, or
the same line counted twice from one game. This prints each row that holds the player on or near a
date, with how it is stored and whether the effective views serve it (`counts`), so the shape of the
double is known before anything is changed.

    python -m app.scripts.inspect_player_matches <org-id-or-slug> "<player name>" <YYYY-MM-DD> [...] [--window DAYS]

After each date it EXPLAINS the Possible doubles scan for every club card shown: the card's own flags
(a link confirmed or decided by hand is never second-guessed, a "different matches" answer hides a
pair), how many of its batters are on the game it is linked to, how it compares with every synced game
nobody has linked, and whether the scan lists it now.

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
from app.services import card_review as cr
from app.services import card_review_doubles as dbl
from app.services import card_review_find as fnd
from app.services import match_pairing as mp

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


_FLAGS = """
    SELECT m.id::text AS id, m.review_pair_ok, m.review_source, m.review_choice, m.superseded_by_game_id::text AS linked_to,
           m.played_at, COALESCE(m.opposition, '') AS opposition, COALESCE(m.home_team, '') AS home_team,
           COALESCE(m.away_team, '') AS away_team,
           (SELECT count(*) FROM card_review_log l WHERE l.manual_game_id = m.id AND l.action = 'not_double'
               AND l.undone_at IS NULL) AS dismissals
      FROM manual_games m WHERE m.id = ANY(CAST(:ids AS UUID[]))
"""


def _pct(a, b):
    return f"{a} of {b}"


async def explain(db, org_id: str, club_ids: list, lo, hi, found: dict) -> None:
    """Why the scan does or does not offer each club card shown above."""
    if not club_ids:
        return
    club_tokens = mp.team_tokens((await db.execute(text(mp._CLUB_NAME_SQL), {"org": org_id})).scalar() or "")
    flags = {r["id"]: r for r in (await db.execute(text(_FLAGS), {"ids": club_ids})).mappings()}
    cards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": club_ids})
    games = await mp.load_synced(db, org_id, club_tokens=club_tokens, from_day=lo - timedelta(days=7),
                                 to_day=hi + timedelta(days=7), exclude_twinned=True)
    print("  --- why the scan does or does not offer each club card")
    for cid in club_ids:
        f = flags[cid]
        sig = frozenset(cards.get(cid, ()))
        ours, opp = mp.split_sides(f["home_team"], f["away_team"], f["opposition"], club_tokens)
        me = mp.MatchRow(cid, f["played_at"], opp, sig, ours)
        print(f"  card {cid[:8]}: {len(sig)} batters; pair confirmed by a person={bool(f['review_pair_ok'])}; "
              f"decided by={f['review_source'] or 'nobody'}; 'different matches' answers={f['dismissals']}")
        if f["linked_to"]:
            cur = frozenset((await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org_id, "ids": [f["linked_to"]]})).get(f["linked_to"], ()))
            ok = cr.confirms_pair(set(sig), set(cur))
            print(f"    linked game {f['linked_to'][:8]} holds {len(cur)} batters, {len(sig & cur)} in common -> "
                  f"{'the link matches the card (not a wrong link)' if ok else 'the link does NOT match the card'}")
        for g in sorted(games, key=lambda x: str(x.played_at)):
            if g.id == f["linked_to"]:
                continue
            ev = dbl._evidence(me, g)
            if ev["gap_days"] is not None and ev["gap_days"] > 7:
                continue
            strength = dbl.strength_of(ev)
            score = mp.score_pair(me, g)
            why = (f"offered as {strength}" if strength and score is not None else
                   "rejected: both cards have batters and too few agree" if ev["both_cards"] else "rejected by the pairing rules")
            print(f"    unlinked game {g.id[:8]} {g.played_at}: {len(g.signature)} batters, {ev['shared']} in common, "
                  f"{ev['gap_days']} days apart, opposition {'agrees' if ev['opposition_agrees'] else 'differs'} -> {why}")
        hit = [r for r in found["rows"] if cid in (r["a"]["id"], r["b"]["id"])]
        print("    the scan lists it now as: " + (", ".join(f"{r['kind']} ({r['strength']}) with {(r['b'] if r['a']['id'] == cid else r['a'])['id'][:8]}" for r in hit)
                                                 if hit else "NOT LISTED"))


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
        found = None
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
            club_ids = [r["id"] for r in (await db.execute(text(_MANUAL), {"org": org_id, "lo": lo, "hi": hi, "p": who["ids"]})).mappings()]
            if club_ids:
                if found is None:
                    found = await dbl.find_doubles(db, org_id)
                await explain(db, org_id, club_ids, lo, hi, found)


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
