"""Put a recent game's stored figures right once Cricket Australia calls its card COMPLETED.

Sync stores a game's batting, bowling and fielding rows the first time it reads the card, whatever
CA's status is then. A two-day game (played over two Saturdays and dated on the first) is read by the
Sunday 01:00 run while it is still in play, so Sushruth Menon is stored on 1 not out and Shubham on one
wicket. A later read took the `our_appearances_done` branch, and `participant_relink.reread_stored_game`
only ADDS a row that is not there, so the figure he finished on never arrived. The season totals feed
is right, so a profile agrees with PlayCricket; Fantasy reads these rows, and scored the game as it was
in play.

This is the missing half: for a game CA now calls COMPLETED, replace a stored figure the card
disagrees with, in place. Rules:

* Only a card CA calls COMPLETED is believed, unless the caller says the game is being followed live
  (`in_play_ok`, used only by the Fantasy live pass). A card still in play plans nothing by default, so a
  later read of an unfinished game can never overwrite a finished figure; the live pass only reads games
  CA has not called COMPLETED, and the pass that sees the COMPLETED card puts the final figure right.
* Only the club's own players (the roster of the club's team on the card), matched on the game,
  player and innings the way sync stores them. A shared fixture's other club is never touched.
* Figures only: a row is UPDATED where it is, so its id, its merge history and anything that points at
  it stay. A batting or bowling row the card has and the game lacks is `participant_relink.attach`'s
  to add, and nothing here deletes a row. A fielding row is added only where the player already holds
  one for the game, because a second innings fielded is its own row (see `fantasy_engine`).
* A figure that already matches is not written, so a second run changes nothing.

Not rebuilt: fall of wickets, partnerships, `bowler_wickets` and `games.innings_totals`, which are
written once. A Full Rebuild still rewrites those.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import dismissal
from app.services.game_status import NOT_PLAYED_STATUSES
from app.services.boundary_counts import clean as _bounds
from app.services.sync import _GR_DISMISSAL_SHORT, _caught_by_keeper, _innings_keeper_names

logger = logging.getLogger(__name__)

Resolve = Callable[[str], Optional[uuid.UUID]]

BATTING_FIELDS = ("runs", "balls", "fours", "sixes", "not_out", "dismissal_type", "caught_behind",
                  "batting_position", "did_not_bat")
BOWLING_FIELDS = ("overs", "maidens", "runs", "wickets", "wides", "no_balls", "economy")
FIELDING_FIELDS = ("catches", "catches_wk", "run_outs", "stumpings")


def is_final(scorecard: Optional[dict]) -> bool:
    """CA calls this card COMPLETED. Nothing else is believed over a stored figure."""
    return bool(scorecard) and str(scorecard.get("status") or "").strip().upper() == "COMPLETED"


def is_in_play(scorecard: Optional[dict]) -> bool:
    """A card that has been started and not called off: LIVE, or whatever CA calls a game between
    its two days. COMPLETED is `is_final`; a called-off or not-yet-started card has no figures."""
    if not scorecard:
        return False
    status = str(scorecard.get("status") or "").strip().upper()
    return bool(status) and status not in ("COMPLETED", "UPCOMING") and status not in NOT_PLAYED_STATUSES


def _our_team(scorecard: dict, org_id) -> Optional[dict]:
    return next((t for t in (scorecard.get("teams") or [])
                 if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == str(org_id).lower()), None)


def _same(field: str, old, new) -> bool:
    """Whether a stored value already equals what the card says, by the column's own type."""
    if field in ("overs", "economy"):
        if old is None or new is None:
            return old is None and new is None
        tol = 0.05 if field == "overs" else 0.005
        return abs(float(old) - float(new)) < tol
    if field in ("not_out", "caught_behind", "did_not_bat"):
        return bool(old) == bool(new)
    return old == new


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _shown(v):
    return float(v) if isinstance(v, Decimal) else v


async def plan_game(db: AsyncSession, org_id, game_id, scorecard: Optional[dict], resolve: Resolve,
                    in_play_ok: bool = False) -> list[dict]:
    """The figure changes a COMPLETED card asks for in one stored game. Read only.
    With ``in_play_ok`` a card still in play is believed too (the running score of a live game).

    Each change is ``{op, table, id, game_id, player_id, innings, field, old, new}`` where ``op`` is
    ``update`` (``id`` is the stored row) or ``insert`` (a fielding row, ``field`` is ``row``).
    An empty list means the game is as the card says, or the card is not final."""
    if not (is_final(scorecard) or (in_play_ok and is_in_play(scorecard))):
        return []
    team = _our_team(scorecard, org_id)
    if not team:
        return []
    gid = game_id if isinstance(game_id, uuid.UUID) else uuid.UUID(str(game_id))

    ours: set = set()
    for p in team.get("players") or []:
        pid = resolve(p.get("participantId") or "") if p.get("participantId") else None
        if pid is not None:
            ours.add(pid)
    if not ours:
        return []
    pids = [str(p) for p in ours]

    stored_bat = {(r["player_id"], r["innings_number"]): r for r in (await db.execute(text(
        "SELECT id, player_id, innings_number, runs, balls, fours, sixes, not_out, dismissal_type, "
        "caught_behind, batting_position, did_not_bat FROM batting_innings "
        "WHERE game_id = :g AND player_id = ANY(CAST(:p AS uuid[]))"), {"g": gid, "p": pids})).mappings().all()}
    stored_bowl = {(r["player_id"], r["innings_number"]): r for r in (await db.execute(text(
        "SELECT id, player_id, innings_number, overs, maidens, runs, wickets, wides, no_balls, economy "
        "FROM bowling_spells WHERE game_id = :g AND player_id = ANY(CAST(:p AS uuid[]))"),
        {"g": gid, "p": pids})).mappings().all()}
    stored_field: dict = {}
    for r in (await db.execute(text(
            "SELECT id, player_id, catches, catches_wk, run_outs, stumpings FROM fielding_stats "
            "WHERE game_id = :g AND player_id = ANY(CAST(:p AS uuid[])) ORDER BY id"),
            {"g": gid, "p": pids})).mappings().all():
        stored_field.setdefault(r["player_id"], []).append(r)

    changes: list[dict] = []

    def diff(table, row, new: dict, fields, pid, inn):
        for f in fields:
            if f in new and not _same(f, row[f], new[f]):
                changes.append({"op": "update", "table": table, "id": row["id"], "game_id": gid,
                                "player_id": pid, "innings": inn, "field": f,
                                "old": _shown(row[f]), "new": new[f]})

    card_field: dict = {}
    for inn in scorecard.get("innings") or []:
        inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
        keeper_names = _innings_keeper_names(inn.get("fielding") or [])

        for row in inn.get("batting") or []:
            pid = resolve(row.get("participantId") or "") if row.get("participantId") else None
            if pid is None or pid not in ours:
                continue
            dt_id = row.get("dismissalTypeId") or 0
            dt_long = row.get("dismissalType") or ""
            if dt_id == 0 or dt_long.lower() in ("absent", "did not bat", "dnb"):
                continue   # a did-not-bat line carries no figure to correct
            stored = stored_bat.get((pid, inn_num))
            if stored is None:
                continue   # a missing row is `participant_relink.attach`'s to add
            bounds = _bounds(row.get("runsScored") or 0, row.get("foursScored"), row.get("sixesScored"))
            new = {
                "runs": row.get("runsScored") or 0, "balls": row.get("ballsFaced"),
                "fours": bounds[0], "sixes": bounds[1],
                "not_out": dismissal.is_not_out(dt_id, dt_long),
                "dismissal_type": (_GR_DISMISSAL_SHORT.get(dt_long, dt_long.lower()) or None),
                "caught_behind": (dt_long == "Caught"
                                  and _caught_by_keeper(row.get("dismissalText") or "", keeper_names)),
                "batting_position": row.get("batOrder"), "did_not_bat": False,
            }
            # A stored `caught_behind` of NULL was never judged (old rows, manual entries): leave it unless
            # the card now says it was a keeper's catch.
            fields = [f for f in BATTING_FIELDS if not (f == "caught_behind" and stored["caught_behind"] is None
                                                       and not new["caught_behind"])]
            diff("batting_innings", stored, new, fields, pid, inn_num)

        for row in inn.get("bowling") or []:
            pid = resolve(row.get("participantId") or "") if row.get("participantId") else None
            if pid is None or pid not in ours:
                continue
            stored = stored_bowl.get((pid, inn_num))
            if stored is None:
                continue
            new = {
                "overs": _num(row.get("oversBowled")), "maidens": row.get("maidensBowled"),
                "runs": row.get("runsConceded"), "wickets": row.get("wicketsTaken"),
                "wides": row.get("wideBalls"), "no_balls": row.get("noBalls"),
                "economy": _num(row.get("economy")),
            }
            diff("bowling_spells", stored, new, BOWLING_FIELDS, pid, inn_num)

        for row in inn.get("fielding") or []:
            pid = resolve(row.get("participantId") or "") if row.get("participantId") else None
            if pid is None or pid not in ours:
                continue
            wk = row.get("wicketKeeperCatches") or 0
            total = row.get("totalCatches")
            if total is None:
                total = (row.get("catches") or 0) + wk
            card_field.setdefault(pid, []).append({
                "catches": total or 0, "catches_wk": wk, "run_outs": row.get("runOuts") or 0,
                "stumpings": row.get("stumpings") or 0})

    # A player's fielding is one row per innings fielded, with no innings number on it, so the card's
    # rows and the stored ones are lined up in order, and only where the totals differ.
    for pid, rows in card_field.items():
        have = stored_field.get(pid) or []
        if not have:
            continue   # no row at all: `participant_relink.attach` adds it (and any orphan it names)
        if all(sum(r[f] or 0 for r in have) == sum(c[f] for c in rows) for f in FIELDING_FIELDS):
            continue
        for stored, new in zip(have, rows):
            diff("fielding_stats", stored, new, FIELDING_FIELDS, pid, None)
        for new in rows[len(have):]:
            changes.append({"op": "insert", "table": "fielding_stats", "id": None, "game_id": gid,
                            "player_id": pid, "innings": None, "field": "row", "old": None, "new": new})
    return changes


async def apply_changes(db: AsyncSession, changes: list[dict]) -> int:
    """Write what ``plan_game`` returned. Returns the number of rows touched (updated or added)."""
    by_row: dict = {}
    for c in changes:
        if c["op"] == "update":
            by_row.setdefault((c["table"], c["id"]), {})[c["field"]] = c["new"]
    for (table, rid), cols in by_row.items():
        sets = ", ".join(f"{col} = :v_{col}" for col in cols)
        await db.execute(text(f"UPDATE {table} SET {sets} WHERE id = :id"),
                         {"id": rid, **{f"v_{col}": v for col, v in cols.items()}})
    inserted = 0
    for c in changes:
        if c["op"] == "insert":
            n = c["new"]
            # The new row's id is kept on the change, so a caller that audits can take it back out.
            c["inserted_id"] = (await db.execute(text(
                "INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                "VALUES (:g, :p, :c, :cw, :ro, :st) RETURNING id"),
                {"g": c["game_id"], "p": c["player_id"], "c": n["catches"], "cw": n["catches_wk"],
                 "ro": n["run_outs"], "st": n["stumpings"]})).scalar()
            inserted += 1
    return len(by_row) + inserted


async def refresh_stored_figures(db: AsyncSession, org_id, game_id, scorecard: Optional[dict],
                                 resolve: Resolve, in_play_ok: bool = False) -> list[dict]:
    """Plan and write one game's figure changes, and commit. Returns the changes (empty when the game
    already matches its card, or the card is not COMPLETED and ``in_play_ok`` is off). The caller
    catches anything this raises: a refresh must never fail a sync."""
    changes = await plan_game(db, org_id, game_id, scorecard, resolve, in_play_ok=in_play_ok)
    if not changes:
        return []
    await apply_changes(db, changes)
    await db.commit()
    logger.info("GR-sync: refreshed %s from its %s card: %d change(s)", game_id,
                "COMPLETED" if is_final(scorecard) else "in-play", len(changes))
    return changes


__all__ = ["is_final", "is_in_play", "plan_game", "apply_changes", "refresh_stored_figures"]
