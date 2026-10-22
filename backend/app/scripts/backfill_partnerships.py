"""Fill in the partnerships of games stored before sync wrote them.

WHY THIS EXISTS
---------------
Sync works a game's partnerships out of its fall of wickets
(`_derive_partnerships_grassroots`; a fall of wickets short of the card's dismissals still gives the
stands its figures settle, see `services/partial_partnerships.py`). A game stored before that was written, or
while Cricket Australia had no fall of wickets for it, keeps no partnership rows,
and a finished game is never read again for them: `repair_stored_game` (older than
14 days) only attaches missing PLAYERS, and the re-read that also fills in fall of
wickets and partnerships (`reread_stored_game`) covers the last 14 days only.

The result is a club whose records page lists no stand at all before 2023, while
the games hold fall of wickets for years. Shoalwater Bay, 2017/18 Grade D: a 204 and
a 153 stand that no board could show.

WHAT IT TOUCHES
---------------
Rows in `partnerships` (and `fall_of_wickets` for an innings that has none), added
through `participant_relink.attach_innings_detail`, which is the same code the
re-read runs: same derivation, same club-innings test. Per innings, rows are written
only where the game has none, so nothing is overwritten or deleted and a second run
adds nothing. It never touches a player's batting, bowling or fielding figures.

It reads games that hold fall of wickets and no partnership rows. The derivation
refuses an innings whose fall of wickets does not match the dismissals on the
batting card (a wrongly paired stand is worse than none), so some games still end
with no stand; each is listed with the reason, and `--explain` prints what the derivation read.

CRICKET AUSTRALIA TRAFFIC
-------------------------
One scorecard request per game, paced (`--pause`, default 0.4 s) and capped per run
(`--limit`, default 100, newest first). Narrow with `--from` / `--to`.

CONTINUING A RUN
----------------
A game that gets stands drops out of the selection, but a game the derivation REFUSES
stays selected, so asking again from the top would fetch the same refused games forever.
A run that stops at its limit therefore prints a `--resume` token (club, date, game):
pass it back and the walk carries on from the next older game. Nothing is asked twice.

ALL CLUBS
---------
`all` walks every active club that has a candidate game, in club-id order, newest game
first within each club, under ONE `--limit` for the whole run (so the traffic is bounded
however many clubs there are). Stop it any time with Ctrl-C and continue with `--resume`.
A fixture between two synced clubs is one game: a club is offered a game until a stand with
ONE OF ITS OWN players exists on it, so the second club's innings is not lost to the first
club's stands.

    python -m app.scripts.backfill_partnerships <org-id-or-slug|all> [--from 2017-07-01] [--to 2018-06-30]
                                                [--limit 100] [--pause 0.4] [--explain] [--resume TOKEN] [--apply]

DRY RUN BY DEFAULT. Without `--apply` it reads, derives, reports and rolls back.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import date
from typing import Awaitable, Callable, Optional

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import grassroots_scores_client as gr
from app.services import participant_relink as relink
from app.services.club_grades import club_game_sql
from app.services.sync import _derive_partnerships_grassroots, _dismissed_pids_grassroots

DEFAULT_LIMIT = 100
DEFAULT_PAUSE = 0.4
BATCH = 200   # games read from the database per query; the Cricket Australia cap is `--limit`

Fetch = Callable[[str], Awaitable[Optional[dict]]]


_NO_BAT = {"absent", "did not bat", "dnb"}


def explain_innings(inn: dict) -> str:
    """Why `_derive_partnerships_grassroots` returns nothing for this innings, in the order it checks.

    "ok" means it derives; the stands may still all be dropped for want of a club batter.
    """
    batting = inn.get("batting") or []
    fow = inn.get("fallOfWickets") or []
    valid = [b for b in batting
             if (b.get("dismissalTypeId") or 0) != 0 and (b.get("dismissalType") or "").lower() not in _NO_BAT]
    if len(valid) < 2:
        return f"{len(valid)} batter(s) with a result on the card"
    dismissed = _dismissed_pids_grassroots(batting)
    if not dismissed:
        return "no dismissals on the batting card"
    if not fow:
        return "no fall of wickets on the card"
    if len(fow) > len(dismissed):
        return f"{len(fow)} fall of wickets v {len(dismissed)} dismissals on the card"
    fow_pids = {f.get("participantId") for f in fow if f.get("participantId")}
    if fow_pids and not fow_pids.issubset(dismissed):
        return "a fall of wicket names a batter who was not dismissed"
    if not _derive_partnerships_grassroots(batting, fow):
        if len(fow) < len(dismissed):
            return (f"{len(fow)} of {len(dismissed)} wickets recorded, and none of the stands can be stated "
                    "from them (a missing wicket's score, a retirement on the card, or a pair that depends on a guess)")
        return "a stand is worth more than its batters scored plus extras, or the score goes backwards"
    return "ok"


def explain_game(card: dict, club_id) -> str:
    """One line per game: what stopped any stand being written."""
    if relink._our_team(card, club_id) is None:
        return "no team on the card is owned by this club"
    parts = []
    for inn in card.get("innings") or []:
        n = inn.get("inningsOrder") or inn.get("inningsNumber") or "?"
        parts.append(f"innings {n}: {explain_innings(inn)}")
    if not parts:
        return "the card has no innings"
    if all(x.endswith(": ok") for x in parts):
        return "stands derive but none has a batter this club holds or rosters"
    return "; ".join(parts)


def dump_card(card: dict) -> None:
    """The fields the derivation reads, compactly, so a refusal can be checked by eye."""
    for inn in card.get("innings") or []:
        print(f"      innings {inn.get('inningsOrder') or inn.get('inningsNumber')}"
              f"  batting team {inn.get('battingTeamId') or inn.get('teamId')}")
        for b in sorted(inn.get("batting") or [], key=lambda r: r.get("batOrder") or 99):
            print(f"        bat {b.get('batOrder')!s:>3}  {str(b.get('participantId'))[:8]}  "
                  f"dt={b.get('dismissalTypeId')!s:<3} {b.get('dismissalType')!s:<16} runs={b.get('runsScored')}")
        for f in sorted(inn.get("fallOfWickets") or [], key=lambda r: r.get("order") or 99):
            print(f"        fow {f.get('order')!s:>3}  {str(f.get('participantId'))[:8]}  score={f.get('runs')}")


_CANDIDATE = """
          g.source = 'api'
          AND g.played_at <= CURRENT_DATE
          AND (CAST(:d_from AS date) IS NULL OR g.played_at::date >= CAST(:d_from AS date))
          AND (CAST(:d_to AS date) IS NULL OR g.played_at::date <= CAST(:d_to AS date))
          AND EXISTS (SELECT 1 FROM fall_of_wickets f WHERE f.game_id = g.id)"""


async def select_games(db, org_id, d_from: Optional[date], d_to: Optional[date], limit: int,
                       after: Optional[tuple] = None) -> list:
    """The club's synced games that hold fall of wickets and no stand with one of the club's own
    players, newest first. `after` is (date, game id): only games older than that, which is how
    a walk avoids asking again for a game it has already tried."""
    c_date, c_id = after if after else (None, None)
    return (await db.execute(text(f"""
        SELECT g.id, g.played_at::date AS played, gr.name AS grade
        FROM v_effective_games g
        LEFT JOIN grades gr ON gr.id = g.grade_id
        WHERE {club_game_sql('g', 'org')}
          AND {_CANDIDATE}
          AND NOT EXISTS (
              SELECT 1 FROM partnerships p JOIN players pl ON pl.id IN (p.batter1_id, p.batter2_id)
              WHERE p.game_id = g.id AND pl.organisation_id = CAST(:org AS UUID))
          AND (CAST(:c_date AS date) IS NULL
               OR (g.played_at::date, g.id) < (CAST(:c_date AS date), CAST(:c_id AS uuid)))
        ORDER BY g.played_at::date DESC, g.id DESC
        LIMIT :lim"""), {"org": str(org_id), "d_from": d_from, "d_to": d_to, "lim": limit,
                         "c_date": c_date, "c_id": str(c_id) if c_id else None})).mappings().all()


async def list_clubs(db, d_from: Optional[date], d_to: Optional[date]) -> list:
    """Active clubs with at least one candidate game, in club-id order (the order `--resume` relies on).

    Over-inclusive on purpose: a club whose only candidates already hold stands of its own is
    listed and then selects nothing, which costs one query."""
    return (await db.execute(text(f"""
        SELECT o.id, o.name FROM organisations o
        WHERE COALESCE(o.is_active, TRUE)
          AND o.id IN (
              SELECT g.organisation_id FROM v_effective_games g WHERE {_CANDIDATE}
              UNION SELECT g.home_org_id FROM v_effective_games g WHERE {_CANDIDATE}
              UNION SELECT g.away_org_id FROM v_effective_games g WHERE {_CANDIDATE})
        ORDER BY o.id"""), {"d_from": d_from, "d_to": d_to})).all()


def parse_resume(token: Optional[str]):
    """`club|date|game` -> (club uuid, date, game uuid). Refuses anything else, loudly."""
    if not token:
        return None
    try:
        club, played, game = token.split("|")
        return uuid.UUID(club), date.fromisoformat(played), uuid.UUID(game)
    except (ValueError, TypeError):
        raise SystemExit(f"--resume wants the token a previous run printed (club|date|game), got {token!r}")


def resume_token(club_id, played, game_id) -> str:
    return f"{club_id}|{played}|{game_id}"


async def backfill_club(club_id, name, *, d_from, d_to, budget: int, pause: float, apply: bool,
                        explain: bool, fetch, after, tally: dict) -> dict:
    """Walk one club's candidate games, newest first, asking Cricket Australia for at most `budget`.

    Returns {"used": games asked, "last": (date, game id) of the last one tried, "done": True when
    the club has no older candidate left}."""
    async def _fetch(match_id: str):
        sc = await (fetch or gr.get_match_scorecard)(match_id)
        if pause:
            await asyncio.sleep(pause)
        return sc

    async with async_session_maker() as db:
        by_guid, merged, _unique = await relink._org_maps(db, club_id)
        await db.rollback()

    def resolve(guid):
        return relink._known(guid, by_guid, merged) if guid else None

    used, last, announced = 0, after, False
    while used < budget:
        async with async_session_maker() as db:
            batch = await select_games(db, club_id, d_from, d_to, min(budget - used, BATCH), last)
            await db.rollback()
        if not batch:
            return {"used": used, "last": last, "done": True}
        if not announced:
            print(f"\n{name}: games with fall of wickets and no stand of the club's own players")
            announced = True
        for g in batch:
            last = (g["played"], g["id"])
            used += 1
            tally["asked"] += 1
            try:
                card = await _fetch(str(g["id"]))
            except Exception as exc:
                tally["failed"] += 1
                print(f"  !! {g['played']}  {g['grade']}  {g['id']}: fetch failed: {exc}")
                continue
            if not card:
                tally["no_data"] += 1
                print(f"  --  {g['played']}  {g['grade']}  {g['id']}: Cricket Australia has no scorecard")
                continue
            async with async_session_maker() as db:
                try:
                    n = await relink.attach_innings_detail(db, club_id, g["id"], card, resolve)
                    if apply and (n["partnerships"] or n["fow"]):
                        await db.commit()
                    else:
                        await db.rollback()
                except Exception as exc:
                    await db.rollback()
                    tally["failed"] += 1
                    print(f"  !! {g['played']}  {g['grade']}  {g['id']}: {exc}")
                    continue
            tally["games"] += 1
            tally["stands_added"] += n["partnerships"]
            tally["fow_added"] += n["fow"]
            if n["partnerships"]:
                verb = "added" if apply else "would add"
                print(f"  ok  {g['played']}  {g['grade']}  {g['id']}: {verb} {n['partnerships']} stand(s)")
            else:
                tally["refused"] += 1
                print(f"  --  {g['played']}  {g['grade']}  {g['id']}: no stand written: {explain_game(card, club_id)}")
                if explain:
                    dump_card(card)
    return {"used": used, "last": last, "done": False}


async def run(org: str, *, d_from: Optional[date] = None, d_to: Optional[date] = None,
              limit: int = DEFAULT_LIMIT, pause: float = DEFAULT_PAUSE, apply: bool = False,
              explain: bool = False, fetch: Optional[Fetch] = None, resume: Optional[str] = None) -> dict:
    """One club, or `all`. Returns the counts (and a `resume` token when the limit stopped the walk),
    so a verification can read them without parsing output."""
    tally = {"asked": 0, "games": 0, "stands_added": 0, "fow_added": 0, "refused": 0, "no_data": 0,
             "failed": 0, "clubs": 0, "resume": None}
    cursor = parse_resume(resume)
    async with async_session_maker() as db:
        if org == "all":
            clubs = [(r[0], r[1]) for r in await list_clubs(db, d_from, d_to)]
        else:
            row = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).first()
            if row is None:
                raise SystemExit(f"no club matches {org!r}")
            clubs = [(row[0], row[1])]
        await db.rollback()
    if cursor:
        clubs = [c for c in clubs if c[0] >= cursor[0]]
        if not clubs or clubs[0][0] != cursor[0]:
            print(f"Note: the club in --resume has no candidate games left; carrying on with the next club.")

    print(f"{len(clubs)} club(s) to walk, at most {limit} game(s) asked of Cricket Australia in this run.")
    if not apply:
        print("DRY RUN: nothing will be written. Add --apply to write the stands.")

    remaining = limit
    for club_id, name in clubs:
        if remaining <= 0:
            break
        after = (cursor[1], cursor[2]) if cursor and cursor[0] == club_id else None
        res = await backfill_club(club_id, name, d_from=d_from, d_to=d_to, budget=remaining, pause=pause,
                                  apply=apply, explain=explain, fetch=fetch, after=after, tally=tally)
        if res["used"]:
            tally["clubs"] += 1
        remaining -= res["used"]
        if not res["done"]:
            tally["resume"] = resume_token(club_id, *res["last"])
            break

    verb = "Added" if apply else "Would add"
    print(f"\n{verb} {tally['stands_added']} stand(s) across {tally['games'] - tally['refused']} game(s) "
          f"in {tally['clubs']} club(s); {tally['refused']} with no stand written, "
          f"{tally['no_data']} with no scorecard, {tally['failed']} failed.")
    if tally["resume"]:
        print(f"Stopped at the limit. Carry on with: --resume '{tally['resume']}'")
    else:
        print("Walked every candidate game. Nothing left to resume.")
    return tally


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("org", help="club id (UUID), club slug, or 'all' for every active club")
    ap.add_argument("--from", dest="d_from", type=date.fromisoformat, default=None)
    ap.add_argument("--to", dest="d_to", type=date.fromisoformat, default=None)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="most games to ask Cricket Australia for in this run, across every club")
    ap.add_argument("--pause", type=float, default=DEFAULT_PAUSE)
    ap.add_argument("--explain", action="store_true",
                    help="for a game that gets no stand, also print the batting and fall of wickets the derivation read")
    ap.add_argument("--resume", default=None, help="the token a previous run printed when it stopped at its limit")
    ap.add_argument("--apply", action="store_true", help="write the stands (default is a dry run)")
    a = ap.parse_args()
    asyncio.run(run(a.org, d_from=a.d_from, d_to=a.d_to, limit=a.limit, pause=a.pause, apply=a.apply,
                    explain=a.explain, resume=a.resume))


if __name__ == "__main__":
    main()
