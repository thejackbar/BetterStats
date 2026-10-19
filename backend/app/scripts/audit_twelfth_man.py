"""Audit: is a player who is only NAMED in a side a 12th man CA does not count? Read only.

Reported by Applecross: Jack Barendse reads 214 matches, CA reads 213. The one game is the
2017 8th Grade Grand Final, where he was 12th man: named on the team sheet, never on the
batting card, no bowling, no catch. CA's own match list shows the game, and CA's season total
(12) leaves it out. Nothing in the scorecard says "substitute": a player record is only
`participantId`, `name`, `shortName`, `roles`. So the only evidence is the shape of the card.

The rule this audit tests, all five at once (TWELFTH_MAN):
  1. the game was played (`appearance_counts_as_match`, so washouts never get here)
  2. the player's side has a batting card, meaning it batted
  3. the player is not on that card at all, not even as "Did Not Bat"
  4. the player has no bowling or fielding row in the game
  5. the player sits beyond slot 11 on the team sheet

Every OTHER way of being named-only is classified too, so each is visible as a game the rule
leaves alone:
  ON_CARD_DNB        on the batting card as Did Not Bat (CA counts these).
  SIDE_DID_NOT_BAT   the side never batted (rain, forfeit): there is no card to be missing from.
  INSIDE_XI          the side batted and the player is off the card, but sits in slots 1 to 11.
  HAS_STATS          the card carries a row for the player that our tables do not (drift).
  NOT_ON_SHEET       neither the player nor an id merged into them is on the sheet.
  NO_CARD            CA returned nothing for the game (a PlayHQ-only match), or the card names nobody.

The check is CA's own season total (`player_season_stats.matches`, source 'api'). For each
player and season holding at least one named-only game, held games (what the profile grid
counts) are set against CA's total:
  EXPLAINED   held minus CA equals the games flagged: the rule accounts for the whole gap.
  OVER_FLAGS  the rule would take the player below CA's own figure: CA counted a game the rule
              flags. Either the rule is wrong or CA counted a substitute (the club can say).
  CA_ABOVE_HELD  CA counts more than we hold, so the flagged game cannot be tested.
  PARTLY      the rule explains some of the gap and not all of it.
  MISSED      CA is lower than held and nothing was flagged: another cause.
  AGREES      CA already counts every named-only game: supports leaving those alone.

Writes nothing. Upstream cost: one scorecard request per named-only game (the client caches),
paced, and bounded by --max-games. Ctrl-C stops it.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.audit_twelfth_man <org_id_or_slug_or_all> \\
      [--max-games 200] [--pace 0.5] [--year 2016] [--list 40] [--csv /tmp/twelfth.csv] [--timeout 120]
"""
import argparse
import asyncio
import csv
import uuid
from collections import Counter, defaultdict

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services.club_grades import club_game_sql
from app.services.game_status import appearance_counts_as_match, not_played_game_sql
from app.services.reserve_players import CODES, TWELFTH_MAN, XI, classify  # noqa: F401  (re-exported for the suite)

def verdict(held: int, ca: int | None, flagged: int) -> str:
    """How the rule sits against CA's own season total for one player and season."""
    if ca is None:
        return "NO_CA_TOTAL"
    gap = held - ca
    if flagged == 0:
        return "MISSED" if gap > 0 else "AGREES"
    if gap < 0:
        # CA counts more games than we hold, so a game we are missing could be the one CA
        # counted in place of the flagged one. Nothing can be said either way.
        return "CA_ABOVE_HELD"
    if gap == flagged:
        return "EXPLAINED"
    return "OVER_FLAGS" if gap < flagged else "PARTLY"


async def _resolve_org(org_ref: str) -> str:
    try:
        return str(uuid.UUID(org_ref))
    except ValueError:
        pass
    async with async_session_maker() as session:
        found = (await session.execute(
            text("SELECT id::text FROM organisations WHERE slug = :s"), {"s": org_ref})).scalar()
    if not found:
        raise SystemExit(f"No club with slug {org_ref!r}")
    return found


async def _all_orgs() -> list[tuple[str, str]]:
    async with async_session_maker() as session:
        rows = (await session.execute(text("""
            SELECT o.id::text AS id, o.name FROM organisations o
            WHERE o.archived_at IS NULL AND o.is_active
              AND EXISTS (SELECT 1 FROM players p WHERE p.organisation_id = o.id)
            ORDER BY o.name"""))).all()
    return [(r.id, r.name) for r in rows]


CHUNK = 100  # players per query: a bound array this size is pushed into the views (rule 11)


def say(msg: str = "") -> None:
    """Progress goes out at once. A stage that takes a while must not look like a hang."""
    print(msg, flush=True)


async def _candidates(session, org: str, year: int | None) -> list[dict]:
    """Named-only appearances: a team-sheet entry that counts as a match and no row of ours in it.

    The `v_effective_*` views are read per chunk of players with `player_id = ANY(:pids)`, never
    probed per appearance. Probing them once per row (`WHERE x.game_id = ga.game_id AND
    x.player_id = ga.player_id`) cannot be pushed into the views' joins and took 38s on 40,000
    appearances against the production views, against 0.4s on the plain ones.

    For a player with no row of their own, `appearance_counts_as_match` reduces to "the game was
    played", so that is what is tested here, on the raw `games` row.
    """
    pids = [r[0] for r in (await session.execute(text(
        "SELECT id::text FROM players WHERE organisation_id = CAST(:org AS UUID) ORDER BY id"),
        {"org": org})).all()]
    out: list[dict] = []
    for i in range(0, len(pids), CHUNK):
        chunk = pids[i:i + CHUNK]
        have = {(r[0], r[1]) for r in (await session.execute(text("""
            SELECT player_id::text, game_id::text FROM v_effective_batting_innings
              WHERE player_id = ANY(CAST(:pids AS uuid[]))
            UNION SELECT player_id::text, game_id::text FROM v_effective_bowling_spells
              WHERE player_id = ANY(CAST(:pids AS uuid[]))
            UNION SELECT player_id::text, game_id::text FROM v_effective_fielding_stats
              WHERE player_id = ANY(CAST(:pids AS uuid[]))"""), {"pids": chunk})).all()}
        rows = (await session.execute(text(f"""
            SELECT ga.game_id::text AS game_id, ga.player_id::text AS player_id,
                   COALESCE(p.grassroots_id, p.id::text) AS raw_guid,
                   COALESCE(p.display_name_override, p.name) AS player_name,
                   g.played_at, se.year, se.name AS season, gr.name AS grade,
                   ga.is_reserve AS stored_reserve
            FROM game_appearances ga
            JOIN games gm ON gm.id = ga.game_id
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN players p ON p.id = ga.player_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons se ON se.id = g.season_id
            WHERE ga.player_id = ANY(CAST(:pids AS uuid[]))
              AND {club_game_sql('g', 'org')}
              AND NOT {not_played_game_sql('gm')}
              AND (CAST(:year AS INTEGER) IS NULL OR se.year = CAST(:year AS INTEGER))"""),
            {"pids": chunk, "org": org, "year": year})).mappings().all()
        out += [dict(r) for r in rows if (r["player_id"], r["game_id"]) not in have]
        if (i // CHUNK) % 5 == 4 or i + CHUNK >= len(pids):
            say(f"  read {min(i + CHUNK, len(pids))} of {len(pids)} players, "
                f"{len(out)} named-only appearances so far")
    out.sort(key=lambda c: (str(c["played_at"]), c["game_id"]), reverse=True)
    return out


async def _merged_guids(session, player_ids: list[str]) -> dict[str, set[str]]:
    """Ids merged into each player (not undone): a card keeps the id the person had on the day."""
    if not player_ids:
        return {}
    exists = (await session.execute(text("SELECT to_regclass('public.merge_logs') IS NOT NULL"))).scalar()
    if not exists:
        return {}
    rows = (await session.execute(text("""
        SELECT keep_player_id::text AS keep, removed_player_id::text AS removed
        FROM merge_logs
        WHERE keep_player_id = ANY(CAST(:ids AS uuid[])) AND undone_at IS NULL"""),
        {"ids": player_ids})).all()
    out: dict[str, set[str]] = defaultdict(set)
    for keep, removed in rows:
        out[keep].add(str(removed).lower())
    return out


async def _held_and_ca(session, org: str, player_ids: list[str]) -> tuple[dict, dict]:
    """Per (player, season year, season name): games held, and CA's own stored total.

    Both sides are keyed by the season's year and name, not its id: a fixture shared with
    another club can hang off that club's season row, which carries the same name and year.
    Read in chunks of players, each a bound array the views can take a filter from.
    """
    held: dict = {}
    ca: dict = {}
    for i in range(0, len(player_ids), CHUNK):
        chunk = player_ids[i:i + CHUNK]
        for r in (await session.execute(text(f"""
            WITH held AS (
                SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
                  WHERE bi.player_id = ANY(CAST(:pids AS uuid[]))
                UNION SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
                  WHERE bs.player_id = ANY(CAST(:pids AS uuid[]))
                UNION SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
                  WHERE fs.player_id = ANY(CAST(:pids AS uuid[]))
                UNION SELECT ga.player_id, ga.game_id FROM game_appearances ga
                  WHERE ga.player_id = ANY(CAST(:pids AS uuid[])) AND {appearance_counts_as_match('ga')}
            )
            SELECT h.player_id::text AS pid, se.year, se.name AS season, COUNT(DISTINCT g.id) AS held
            FROM held h
            JOIN v_effective_games g ON g.id = h.game_id
            JOIN seasons se ON se.id = g.season_id
            WHERE {club_game_sql('g', 'org')}
            GROUP BY h.player_id, se.year, se.name"""), {"pids": chunk, "org": org})).all():
            held[(r.pid, r.year, r.season)] = int(r.held)
        for r in (await session.execute(text("""
            SELECT pss.player_id::text AS pid, se.year, se.name AS season, SUM(pss.matches) AS ca
            FROM player_season_stats pss
            JOIN seasons se ON se.id = pss.season_id
            WHERE pss.player_id = ANY(CAST(:pids AS uuid[])) AND pss.source = 'api'
            GROUP BY pss.player_id, se.year, se.name"""), {"pids": chunk})).all():
            ca[(r.pid, r.year, r.season)] = int(r.ca)
    return held, ca


async def audit_club(org: str, label: str, args, budget: list[int]) -> list[dict]:
    """One club. `budget` is a one-item list so the fetch allowance is shared across `all`."""
    say(f"\n######## {label} ({org})")
    say("reading each player's named-only appearances from the database (no upstream calls yet)...")
    timeout_s = int(getattr(args, "timeout", 120))
    async with async_session_maker() as session:
        # Read only by construction, and no single statement may run past --timeout seconds: a
        # query that is too slow ends here with a message instead of holding the database.
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await session.execute(text(f"SET LOCAL statement_timeout = {timeout_s * 1000}"))
        try:
            cands = await _candidates(session, org, args.year)
            pids = sorted({c["player_id"] for c in cands})
            merged = await _merged_guids(session, pids)
            say(f"reading CA's season totals for {len(pids)} players...")
            held, ca = await _held_and_ca(session, org, pids)
        except DBAPIError as exc:
            if "statement timeout" in str(exc):
                raise SystemExit(f"A query ran past {timeout_s}s and was stopped (nothing was written). "
                                 "Re-run with --year for one season, or raise --timeout.") from exc
            raise

    say(f"named-only appearances: {len(cands)} across {len({c['game_id'] for c in cands})} games, "
        f"{len(pids)} players")

    cards: dict[str, dict | None] = {}
    skipped = 0
    for c in cands:
        gid = c["game_id"]
        if gid not in cards:
            if budget[0] <= 0:
                skipped += 1
                c["code"] = None
                continue
            budget[0] -= 1
            cards[gid] = await gr.get_match_scorecard(gid)
            await asyncio.sleep(args.pace)
        guids = {str(c["raw_guid"]).lower(), str(c["player_id"]).lower()} | merged.get(c["player_id"], set())
        c.update(classify(cards[gid], guids))

    judged = [c for c in cands if c.get("code")]
    if skipped:
        print(f"  {skipped} appearance(s) not judged: the --max-games allowance ran out")
    if not judged:
        return []

    print("\n-- how each named-only appearance reads on CA's card")
    counts = Counter(c["code"] for c in judged)
    for code in CODES:
        if counts.get(code):
            print(f"  {code:<18} {counts[code]}")

    flagged_by = Counter()
    for c in judged:
        if c["code"] == TWELFTH_MAN:
            flagged_by[(c["player_id"], c["year"], c["season"])] += 1
    seasons: dict[tuple, list[dict]] = defaultdict(list)
    for c in judged:
        seasons[(c["player_id"], c["year"], c["season"])].append(c)

    print("\n-- the rule against CA's own season total (one line per player and season)")
    verdicts = Counter()
    lines = []
    for key, rows in seasons.items():
        h, a, f = held.get(key, 0), ca.get(key), flagged_by.get(key, 0)
        v = verdict(h, a, f)
        verdicts[v] += 1
        for r in rows:
            r["verdict"] = v
        lines.append((v, rows[0]["player_name"], key[2], h, a, f, Counter(r["code"] for r in rows)))
    for v in ("EXPLAINED", "OVER_FLAGS", "CA_ABOVE_HELD", "PARTLY", "MISSED", "AGREES", "NO_CA_TOTAL"):
        if verdicts.get(v):
            print(f"  {v:<12} {verdicts[v]}")

    def show(title, want, limit):
        rows = [l for l in lines if l[0] in want]
        if not rows:
            return
        print(f"\n-- {title}")
        for v, name, season, h, a, f, mix in sorted(rows, key=lambda l: (l[0], l[1]))[:limit]:
            mixtxt = ", ".join(f"{k}={n}" for k, n in sorted(mix.items()))
            print(f"  {v:<10} {name:<26} {season:<16} held={h} CA={a} flagged={f}   [{mixtxt}]")
        if len(rows) > limit:
            print(f"  ... {len(rows) - limit} more (raise --list)")

    show("where the rule and CA disagree, the evidence against it", {"OVER_FLAGS"}, args.list)
    show("where the rule explains only part of the gap", {"PARTLY"}, args.list)
    show("where CA is lower than held and the rule flags nothing", {"MISSED"}, args.list)

    flagged = [c for c in judged if c["code"] == TWELFTH_MAN]
    if flagged:
        print(f"\n-- every game the rule flags ({len(flagged)})")
        for c in sorted(flagged, key=lambda c: (str(c["played_at"]), c["player_name"]))[:args.list]:
            print(f"  {str(c['played_at'])[:10]}  {c['player_name']:<26} slot {c['slot']}/{c['sheet']:<3}"
                  f" {c['grade']:<18} {c['game_id']}  [{c['verdict']}]")
        if len(flagged) > args.list:
            print(f"  ... {len(flagged) - args.list} more (raise --list or use --csv)")
    for c in judged:
        c["org"] = org
    return judged


async def main(args) -> None:
    budget = [args.max_games]
    if args.org == "all":
        orgs = await _all_orgs()
    else:
        orgs = [(await _resolve_org(args.org), args.org)]
    rows: list[dict] = []
    for org, label in orgs:
        if budget[0] <= 0:
            print(f"\n--max-games allowance used up; {label} and later clubs were not read")
            break
        rows += await audit_club(org, label, args, budget)

    if len(orgs) > 1 and rows:
        print("\n######## ALL CLUBS READ")
        print("  appearances by class:", dict(Counter(r["code"] for r in rows)))
        print("  player-seasons by verdict:",
              dict(Counter(v for v in {(r["org"], r["player_id"], r["year"], r["season"]): r["verdict"]
                                        for r in rows}.values())))
    if args.csv and rows:
        cols = ["org", "game_id", "player_id", "player_name", "played_at", "year", "season", "grade",
                "code", "slot", "sheet", "verdict"]
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {len(rows)} rows to {args.csv}")
    print(f"\nscorecards requested: {args.max_games - budget[0]} of {args.max_games} allowed. Nothing was written.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("org", help="org id, club slug, or 'all'")
    ap.add_argument("--max-games", type=int, default=200, help="most scorecards to request in the whole run")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds to wait after each scorecard request")
    ap.add_argument("--year", type=int, default=None, help="only seasons with this year")
    ap.add_argument("--list", type=int, default=40, help="rows to print in each detail list")
    ap.add_argument("--csv", default=None, help="write every judged appearance to this file")
    ap.add_argument("--timeout", type=int, default=120, help="seconds any one database statement may run")
    asyncio.run(main(ap.parse_args()))
