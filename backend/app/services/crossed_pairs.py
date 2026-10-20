"""Put right the imported matches an override paired with the wrong synced game.

An overwrite import pairs a sheet match to a synced one on date and opposition. A
club that plays several grades against one opposition on the same day (a junior
club's Saturday: Under 9 Red, Under 9 Blue and Under 11 Knights all against
Hectorville) gives that rule nothing to tell them apart, so it takes the first it
finds. The pairs come out crosswise: the Under 13 sheet match hides the Under 11
synced match and the other way round. Nothing is counted twice and every total is
right, but the wrong card sits behind each match, so a comparison reads "differs",
and copying balls faced from the synced side onto the sheet side would land on the
wrong match.

The scorecards settle it. Now that the club's players are one record each, the
batters on a sheet match are the batters on its synced twin, with the same runs. So
this takes the club's import-made pairs, works out the best one-to-one pairing
between those sheet matches and those same synced games (the matcher's own rules,
`match_pairing.assign`), and moves a pair only where the scorecard says so.

WHEN A PAIR MOVES. All of these hold, or it is left and reported:

* the new synced game shares MORE scores with the sheet match than its current one;
* the move is a closed swap or cycle: every synced game given up is taken by another
  sheet match that also moves, so the set of hidden synced games never changes and
  no match is ever counted twice or dropped;
* the synced game is one of this club's import-made pairs, never a free one (a free
  synced game is `repair_overwrite_pairs`' business).

Nothing is deleted. The pair columns are exactly what the import wrote.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

from sqlalchemy import text

from app.services import match_pairing as mp

# The matches an import created, still paired. Read off the import's own audit
# rows, so a hand-typed game is never touched.
_PAIRED_SQL = """
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
           mg.superseded_by_game_id::text AS game_id,
           s.name AS season_name
      FROM manual_games mg
      JOIN imported i ON i.id = mg.id
      JOIN seasons s ON s.id = mg.season_id
     WHERE mg.organisation_id = :org
       AND mg.superseded_by_game_id IS NOT NULL
       AND mg.cricketstatz_import_id IS NULL
"""

_GAMES_SQL = """
    SELECT g.id::text AS id, g.played_at,
           COALESCE(g.opp_club_name, '') AS opposition,
           COALESCE(g.home_team, '') AS home_team,
           COALESCE(g.away_team, '') AS away_team
      FROM games g
     WHERE g.id = ANY(CAST(:ids AS UUID[]))
"""

_CLEAR_SQL = """
    UPDATE manual_games SET superseded_by_game_id = NULL
     WHERE id = ANY(CAST(:ids AS UUID[])) AND organisation_id = CAST(:org AS UUID)
"""

_SET_SQL = """
    UPDATE manual_games SET superseded_by_game_id = CAST(:game AS UUID)
     WHERE id = CAST(:mg AS UUID) AND organisation_id = CAST(:org AS UUID)
"""


def plan_moves(current: dict[str, str], new: dict[str, str], shared) -> tuple[dict, list]:
    """Which pairs to move, as ``({sheet match: new synced game}, held)``.

    ``current`` is every sheet match's present synced game, ``new`` the fresh
    one-to-one assignment (a sheet match it left out keeps its own), and
    ``shared(m, g)`` the number of scores a sheet match and a synced game have in
    common. A move needs a strictly better card; then the set shrinks until it is a
    closed swap (see the module docstring), and what falls out is returned as held.
    """
    move = {m: g for m, g in new.items()
            if g != current.get(m) and shared(m, g) > shared(m, current[m])}
    held: list[tuple[str, str, str]] = []
    changed = True
    while changed:
        changed = False
        owner = {g: m for m, g in current.items()}
        for m in sorted(move):
            g = move[m]
            holder = owner.get(g)
            # taken by a sheet match that stays put, or by none of the club's pairs
            if holder is None or holder not in move:
                held.append((m, current[m], g))
                del move[m]
                changed = True
                break
    return move, held


async def find_moves(db, org_id) -> dict:
    org = str(org_id)
    rows = (await db.execute(text(_PAIRED_SQL), {"org": org})).mappings().all()
    if not rows:
        return {"paired": 0, "moves": [], "held": []}
    club_tokens = mp.team_tokens((await db.execute(
        text(mp._CLUB_NAME_SQL), {"org": org})).scalar() or "")
    by_id = {r["id"]: r for r in rows}
    game_ids = sorted({r["game_id"] for r in rows})
    games = {g["id"]: g for g in (await db.execute(
        text(_GAMES_SQL), {"ids": game_ids})).mappings().all()}
    imp_cards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": list(by_id)})
    syn_cards = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org, "ids": game_ids})

    imported, synced = [], []
    for r in rows:
        ours, opp = mp.split_sides(r["home_team"], r["away_team"], r["opposition"], club_tokens)
        imported.append(mp.MatchRow(r["id"], r["played_at"], opp,
                                    frozenset(imp_cards.get(r["id"], ())), ours))
    for gid in game_ids:
        g = games.get(gid)
        if g is None:
            continue
        ours, opp = mp.split_sides(g["home_team"], g["away_team"], g["opposition"], club_tokens)
        synced.append(mp.MatchRow(gid, g["played_at"], opp,
                                  frozenset(syn_cards.get(gid, ())), ours))
    imp_by = {m.id: m for m in imported}
    syn_by = {m.id: m for m in synced}
    current = {r["id"]: r["game_id"] for r in rows if r["game_id"] in syn_by}

    fresh = await asyncio.to_thread(mp.assign, imported, synced)
    new = {m: g for m, (g, _prefer) in fresh.items() if m in current}

    def shared(m, g):
        return len(imp_by[m].signature & syn_by[g].signature)

    move, held = plan_moves(current, new, shared)

    def describe(m, g_from, g_to):
        r, a, b = by_id[m], syn_by[g_from], syn_by[g_to]
        return {"manual_game_id": m, "season": r["season_name"],
                "import_date": imp_by[m].played_at, "import_opp": imp_by[m].opposition,
                "from_game": g_from, "from_date": a.played_at, "from_opp": a.opposition,
                "from_shared": shared(m, g_from),
                "to_game": g_to, "to_date": b.played_at, "to_opp": b.opposition,
                "to_shared": shared(m, g_to)}

    return {"paired": len(rows),
            "moves": [describe(m, current[m], g) for m, g in sorted(move.items())],
            "held": [describe(m, f, t) for m, f, t in held]}


async def repair_org(db, org_id, *, apply: bool = False, skip=()) -> dict:
    """The moves for one club and, with ``apply``, make them in one transaction.

    The unique index on `superseded_by_game_id` forbids two sheet matches holding
    one synced game even for an instant, so every moving pair is cleared first and
    then set.
    """
    res = await find_moves(db, org_id)
    skipped = [m for m in res["moves"] if _skipped(m["manual_game_id"], skip)]
    moves = [m for m in res["moves"] if m not in skipped]
    # a skipped member of a swap leaves its partner without a taker: hold the
    # rest of that cycle too, by the same closure rule
    if skipped and moves:
        cur = {m["manual_game_id"]: m["from_game"] for m in moves}
        new = {m["manual_game_id"]: m["to_game"] for m in moves}
        owner = {g: m for m, g in cur.items()}
        keep = dict(new)
        stable = False
        while not stable:
            stable = True
            for m in sorted(keep):
                holder = owner.get(keep[m])
                if holder is None or holder not in keep:
                    del keep[m]
                    stable = False
                    break
        dropped = [m for m in moves if m["manual_game_id"] not in keep]
        res["held"].extend(dropped)
        moves = [m for m in moves if m["manual_game_id"] in keep]
    res["moves"], res["skipped"] = moves, skipped
    if apply and moves:
        ids = [m["manual_game_id"] for m in moves]
        await db.execute(text(_CLEAR_SQL), {"ids": ids, "org": str(org_id)})
        for m in moves:
            await db.execute(text(_SET_SQL), {"game": m["to_game"], "mg": m["manual_game_id"],
                                              "org": str(org_id)})
        from app.services.audit_log import log_activity
        await log_activity(
            db, org_id=org_id, user_id=None, action="repair_crossed_pairs",
            target_type="manual_games", target_id=ids[0],
            details={"why": "Import matches paired to the wrong synced game (several grades "
                            "against one club on one day) were moved to the synced game "
                            "their scorecard shares more scores with.",
                     "moves": [{"manual_game_id": m["manual_game_id"], "from_game": m["from_game"],
                                "to_game": m["to_game"]} for m in moves]})
        await db.commit()
    return res


def _skipped(mg_id: str, skip) -> bool:
    return any(mg_id == s or (len(s) >= 6 and mg_id.startswith(s)) for s in skip)
