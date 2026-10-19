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
  OVER_FLAGS  the rule would take the player below CA's own figure: evidence AGAINST the rule.
  PARTLY      the rule explains some of the gap and not all of it.
  MISSED      CA is lower than held and nothing was flagged: another cause.
  AGREES      CA already counts every named-only game: supports leaving those alone.

Writes nothing. Upstream cost: one scorecard request per named-only game (the client caches),
paced, and bounded by --max-games. Ctrl-C stops it.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.audit_twelfth_man <org_id_or_slug_or_all> \\
      [--max-games 200] [--pace 0.5] [--year 2016] [--list 40] [--csv /tmp/twelfth.csv]
"""
import argparse
import asyncio
import csv
import uuid
from collections import Counter, defaultdict

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services.club_grades import club_game_sql
from app.services.game_status import appearance_counts_as_match

XI = 11  # the side is 11; a name past this slot is a reserve

TWELFTH_MAN = "TWELFTH_MAN"
CODES = (TWELFTH_MAN, "ON_CARD_DNB", "SIDE_DID_NOT_BAT", "INSIDE_XI", "HAS_STATS", "NOT_ON_SHEET", "NO_CARD")
_DNB_TEXT = {"did not bat", "dnb", "absent"}


def classify(card: dict | None, guids: set[str]) -> dict:
    """Judge one named-only appearance from CA's scorecard. Pure: no I/O, no database.

    `guids` is every participant id the player can carry on a card (their own raw GUID plus
    any merged into them). Returns {code, slot, sheet}: slot is 1-based, sheet is the size of
    the player's team list.
    """
    out = {"code": "NO_CARD", "slot": None, "sheet": None}
    if not card or not card.get("teams"):
        return out
    team = None
    for t in card["teams"]:
        for i, p in enumerate(t.get("players") or []):
            if str(p.get("participantId") or "").lower() in guids:
                team, slot = t, i + 1
                pid = str(p["participantId"]).lower()
                break
        if team is not None:
            break
    if team is None:
        out["code"] = "NOT_ON_SHEET"
        return out
    out.update(slot=slot, sheet=len(team.get("players") or []))

    tid = team.get("id")
    side_batted = False
    on_card = None  # the player's own batting row on their side's card
    has_bowl_or_field = False
    for inn in card.get("innings") or []:
        if inn.get("battingTeamId") == tid and inn.get("batting"):
            side_batted = True
            for b in inn["batting"]:
                if str(b.get("participantId") or "").lower() in guids:
                    on_card = b
        for row in (inn.get("bowling") or []) + (inn.get("fielding") or []):
            if str(row.get("participantId") or "").lower() in guids:
                has_bowl_or_field = True

    if has_bowl_or_field:
        out["code"] = "HAS_STATS"
    elif on_card is not None:
        dnb = str(on_card.get("dismissalType") or "").lower() in _DNB_TEXT
        out["code"] = "ON_CARD_DNB" if dnb else "HAS_STATS"
    elif not side_batted:
        out["code"] = "SIDE_DID_NOT_BAT"
    elif slot <= XI:
        out["code"] = "INSIDE_XI"
    else:
        out["code"] = TWELFTH_MAN
    return out


def verdict(held: int, ca: int | None, flagged: int) -> str:
    """How the rule sits against CA's own season total for one player and season."""
    if ca is None:
        return "NO_CA_TOTAL"
    gap = held - ca
    if flagged == 0:
        return "MISSED" if gap > 0 else "AGREES"
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


async def _candidates(session, org: str, year: int | None) -> list[dict]:
    """Named-only appearances: a team-sheet entry that counts as a match and no row of ours in it."""
    rows = (await session.execute(text(f"""
        SELECT ga.game_id::text AS game_id, ga.player_id::text AS player_id,
               COALESCE(p.grassroots_id, p.id::text) AS raw_guid,
               COALESCE(p.display_name_override, p.name) AS player_name,
               g.played_at, se.year, se.name AS season, gr.name AS grade
        FROM game_appearances ga
        JOIN v_effective_games g ON g.id = ga.game_id
        JOIN players p ON p.id = ga.player_id AND p.organisation_id = CAST(:org AS UUID)
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons se ON se.id = g.season_id
        WHERE {club_game_sql('g', 'org')}
          AND {appearance_counts_as_match('ga')}
          AND (CAST(:year AS INTEGER) IS NULL OR se.year = CAST(:year AS INTEGER))
          AND NOT EXISTS (SELECT 1 FROM v_effective_batting_innings x
                          WHERE x.game_id = ga.game_id AND x.player_id = ga.player_id)
          AND NOT EXISTS (SELECT 1 FROM v_effective_bowling_spells x
                          WHERE x.game_id = ga.game_id AND x.player_id = ga.player_id)
          AND NOT EXISTS (SELECT 1 FROM v_effective_fielding_stats x
                          WHERE x.game_id = ga.game_id AND x.player_id = ga.player_id)
        ORDER BY g.played_at DESC, ga.game_id"""), {"org": org, "year": year})).mappings().all()
    return [dict(r) for r in rows]


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
    """
    held = (await session.execute(text(f"""
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
        GROUP BY h.player_id, se.year, se.name"""), {"pids": player_ids, "org": org})).all()
    ca = (await session.execute(text("""
        SELECT pss.player_id::text AS pid, se.year, se.name AS season, SUM(pss.matches) AS ca
        FROM player_season_stats pss
        JOIN seasons se ON se.id = pss.season_id
        WHERE pss.player_id = ANY(CAST(:pids AS uuid[])) AND pss.source = 'api'
        GROUP BY pss.player_id, se.year, se.name"""), {"pids": player_ids})).all()
    return ({(r.pid, r.year, r.season): int(r.held) for r in held},
            {(r.pid, r.year, r.season): int(r.ca) for r in ca})


async def audit_club(org: str, label: str, args, budget: list[int]) -> list[dict]:
    """One club. `budget` is a one-item list so the fetch allowance is shared across `all`."""
    async with async_session_maker() as session:
        cands = await _candidates(session, org, args.year)
        pids = sorted({c["player_id"] for c in cands})
        merged = await _merged_guids(session, pids)
        held, ca = await _held_and_ca(session, org, pids)

    print(f"\n######## {label} ({org})")
    print(f"named-only appearances: {len(cands)} across {len({c['game_id'] for c in cands})} games, "
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
    for v in ("EXPLAINED", "OVER_FLAGS", "PARTLY", "MISSED", "AGREES", "NO_CA_TOTAL"):
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
    asyncio.run(main(ap.parse_args()))
