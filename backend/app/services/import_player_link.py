"""Join the players a spreadsheet import created to the synced player they are.

A club's old scorebook holds a player as "Milne, SA"; Cricket Australia's feed
holds the same man as "Milne, Solomon". The importer matches names exactly, so
it finds nothing and mints a second record. The club then has the person twice,
each with part of a career, and the scorecard pairing (which compares player
ids) can never see that a spreadsheet match and a synced match are the same
game.

Nobody can tell from a name that "Milne, SA" is "Milne, Solomon". A paired match
can: the import's innings sits next to the synced one, and the batter on the
synced card with the same surname, the same first initial, the same runs and the
same batting position is the same man. So this joins on that evidence and on
nothing else.

WHEN A PAIR IS SAFE. Wrong merges put one man's career on another, so every one
of these has to hold. Anything else is reported and left for the merge screen:

* the record to remove was created by an import: no Cricket Australia id, no
  PlayHQ id, no login, not claimed, and a name that is surname and bare initials;
* the record to keep is synced (has a Cricket Australia id) and is not itself a
  candidate to remove;
* across the club's paired matches, the removed record's performances line up with
  exactly ONE synced player: same surname and first initial, and either the same runs
  and batting position or the same bowling figures (overs, runs, wickets) where those
  figures are unique on both cards (``min_evidence`` matches or more);
* no other player of the club shares that surname and first initial, unless that
  other player is a record this same pass is joining to the same synced player
  (the "Westley, R" and "Westley, RHJ" of one man). Two synced records with the
  one name is a question for a person, and the report says so;
* the pair is not one the club chose to keep apart (``merge_pair_ignores``).

Nothing here reads another club's players. The merge is the club's own
(`routers/admin._merge_players_core`): it moves records and never deletes them,
every table in `merge_carry.CARRIED` follows the person, and it is in the merge
log, where it can be undone. The synced record is the one kept.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# surname, then 1 to 3 bare letters ("Milne, SA"). Anything with a real given
# name is not an initial-only record.
_INITIALS = re.compile(r"^\s*([^,]+?)\s*,\s*([A-Za-z]{1,3})\.?\s*$")

# Why a record is reported and not merged.
NO_EVIDENCE = "no paired match shows this player alongside a synced one"
MANY_CANDIDATES = "its innings line up with more than one synced player"
SHARED_NAME = "another player of the club has the same surname and first initial"
TOO_FEW = "fewer paired matches agree than were asked for"


def parse_name(name: Optional[str]) -> tuple[str, str]:
    """(surname, given) lower case. "Milne, SA" and "Milne, Solomon" both read
    surname first; a name with no comma reads given first and surname last."""
    n = re.sub(r"\s+", " ", (name or "").strip())
    if "," in n:
        sur, given = n.split(",", 1)
        return sur.strip().lower(), given.strip().lower()
    words = n.split(" ")
    return (words[-1].lower(), " ".join(words[:-1]).lower()) if len(words) > 1 else (n.lower(), "")


def initial_only(name: Optional[str]) -> bool:
    return bool(_INITIALS.match(name or ""))


def label(name: Optional[str]) -> Optional[tuple[str, str]]:
    """(surname, first initial), or None where either is missing."""
    sur, given = parse_name(name)
    return (sur, given[0]) if sur and given else None


def same_label(a: Optional[str], b: Optional[str]) -> bool:
    """Same surname and the same first initial."""
    la = label(a)
    return la is not None and la == label(b)


_PLAYERS_SQL = """
    SELECT p.id::text AS id,
           COALESCE(NULLIF(p.display_name_override, ''), p.name) AS name,
           (p.grassroots_id IS NULL AND p.playhq_id IS NULL
            AND p.user_id IS NULL AND COALESCE(p.claimed, FALSE) = FALSE) AS removable,
           (p.grassroots_id IS NOT NULL) AS synced
      FROM players p
     WHERE p.organisation_id = CAST(:org AS UUID) AND p.is_player IS NOT FALSE
"""

# One row per (imported player, synced player) with the number of paired
# matches in which their performances agree. A paired match is a manual game that
# supersedes its synced twin. Both players are scoped to this club: a shared
# fixture carries the other club's players on the synced side too.
#
# Two kinds of performance count, and a match counts once however many agree:
#
# * a batting line: same runs and same batting position (a position is held by one
#   batter, so this needs no further guard);
# * a bowling spell: same overs, runs conceded and wickets. Two bowlers can share a
#   figure (4-0-20-1 twice in a match), so a spell only counts when its figures are
#   unique among our bowlers on BOTH cards. This is what joins a player who only ever
#   bowled in the paired matches, whom a batting line can never prove.
_EVIDENCE_SQL = """
    WITH hits AS (
        SELECT mg.id AS mg_id, mbi.player_id AS x_id, bi.player_id AS y_id
          FROM manual_games mg
          JOIN manual_batting_innings mbi
               ON mbi.manual_game_id = mg.id AND NOT COALESCE(mbi.did_not_bat, FALSE)
          JOIN batting_innings bi
               ON bi.game_id = mg.superseded_by_game_id
              AND NOT COALESCE(bi.did_not_bat, FALSE)
              AND bi.runs = mbi.runs
              AND bi.batting_position IS NOT DISTINCT FROM mbi.batting_position
          JOIN players px ON px.id = mbi.player_id AND px.organisation_id = CAST(:org AS UUID)
          JOIN players py ON py.id = bi.player_id AND py.organisation_id = CAST(:org AS UUID)
         WHERE mg.organisation_id = CAST(:org AS UUID)
           AND mg.superseded_by_game_id IS NOT NULL
           AND mbi.player_id <> bi.player_id
        UNION ALL
        SELECT mg.id, msp.player_id, bs.player_id
          FROM manual_games mg
          JOIN manual_bowling_spells msp ON msp.manual_game_id = mg.id
          JOIN bowling_spells bs
               ON bs.game_id = mg.superseded_by_game_id
              AND bs.overs = msp.overs AND bs.runs = msp.runs AND bs.wickets = msp.wickets
          JOIN players px ON px.id = msp.player_id AND px.organisation_id = CAST(:org AS UUID)
          JOIN players py ON py.id = bs.player_id AND py.organisation_id = CAST(:org AS UUID)
         WHERE mg.organisation_id = CAST(:org AS UUID)
           AND mg.superseded_by_game_id IS NOT NULL
           AND msp.player_id <> bs.player_id
           AND msp.overs IS NOT NULL AND msp.overs > 0
           AND (SELECT COUNT(*) FROM manual_bowling_spells m2
                 WHERE m2.manual_game_id = mg.id AND m2.overs = msp.overs
                   AND m2.runs = msp.runs AND m2.wickets = msp.wickets) = 1
           AND (SELECT COUNT(*) FROM bowling_spells b2
                  JOIN players p2 ON p2.id = b2.player_id
                       AND p2.organisation_id = CAST(:org AS UUID)
                 WHERE b2.game_id = bs.game_id AND b2.overs = bs.overs
                   AND b2.runs = bs.runs AND b2.wickets = bs.wickets) = 1
    )
    SELECT x_id::text AS x_id, y_id::text AS y_id, COUNT(DISTINCT mg_id) AS matches
      FROM hits GROUP BY x_id, y_id
"""

_IGNORES_SQL = """
    SELECT player_a_id::text, player_b_id::text FROM merge_pair_ignores
     WHERE org_id = CAST(:org AS UUID)
"""

_MANUAL_GAMES_SQL = """
    SELECT player_id::text AS id, COUNT(DISTINCT manual_game_id) AS games
      FROM manual_batting_innings
     WHERE player_id = ANY(CAST(:ids AS uuid[]))
     GROUP BY player_id
"""


def plan_from(players: list[dict], evidence: list[dict], ignored: set,
              *, min_evidence: int = 1) -> dict:
    """Decide every pair from plain rows, with no database.

    ``players``: id, name, removable, synced.  ``evidence``: x_id, y_id,
    matches.  Returns ``{"merge": [...], "held": [...]}``; each merge is
    ``{remove, keep, matches}`` and each held row ``{remove, why, candidates}``.
    """
    by_id = {p["id"]: p for p in players}
    candidates = {p["id"] for p in players if p["removable"] and initial_only(p["name"])}

    # (1) who each candidate lines up with, name-compatible only
    seen: dict[str, dict[str, int]] = defaultdict(dict)
    for e in evidence:
        x, y = by_id.get(e["x_id"]), by_id.get(e["y_id"])
        if not x or not y or x["id"] not in candidates:
            continue
        if not y["synced"] or y["id"] in candidates:
            continue
        if not same_label(x["name"], y["name"]):
            continue
        seen[x["id"]][y["id"]] = seen[x["id"]].get(y["id"], 0) + int(e["matches"])

    # `single` is everyone who lines up with exactly one synced player, however
    # thin the evidence: a sibling label ("Ansell, C", one match) joining the same
    # man must not block the stronger one ("Ansell, CI", ninety-three). Whether the
    # evidence is enough to merge on is decided separately, below.
    single: dict[str, tuple[str, int]] = {}
    held: list[dict] = []
    for x_id in sorted(candidates, key=lambda i: by_id[i]["name"].lower()):
        ys = seen.get(x_id, {})
        if not ys:
            held.append({"remove": x_id, "why": NO_EVIDENCE, "candidates": []})
        elif len(ys) > 1:
            held.append({"remove": x_id, "why": MANY_CANDIDATES, "candidates": sorted(ys)})
        else:
            ((y_id, n),) = ys.items()
            single[x_id] = (y_id, n)

    # (2) the label must be this man's alone: nobody else of the club with the
    # same surname and initial, unless they are joining the same synced player
    by_label: dict[tuple, list] = defaultdict(list)
    for p in players:
        lb = label(p["name"])
        if lb:
            by_label[lb].append(p)
    merge = []
    for x_id, (y_id, n) in single.items():
        x = by_id[x_id]
        if n < min_evidence:
            held.append({"remove": x_id, "why": TOO_FEW, "candidates": [y_id]})
            continue
        clash = [p for p in by_label.get(label(x["name"]), [])
                 if p["id"] not in (x_id, y_id)
                 and single.get(p["id"], (None,))[0] != y_id]
        if clash:
            held.append({"remove": x_id, "why": SHARED_NAME,
                         "candidates": [y_id] + sorted(p["id"] for p in clash)})
            continue
        if frozenset((x_id, y_id)) in ignored:
            continue
        merge.append({"remove": x_id, "keep": y_id, "matches": n})
    return {"merge": merge, "held": held}


async def find_pairs(db: AsyncSession, org_id, *, min_evidence: int = 1) -> dict:
    """The plan for one club: ``{"merge": [...], "held": [...], "initial_only": n}``
    with each row carrying the names and how many games the removed record has."""
    org = str(org_id)
    players = [dict(r) for r in (await db.execute(text(_PLAYERS_SQL), {"org": org})).mappings().all()]
    evidence = [dict(r) for r in (await db.execute(text(_EVIDENCE_SQL), {"org": org})).mappings().all()]
    ignored = {frozenset((a, b)) for a, b in (await db.execute(text(_IGNORES_SQL), {"org": org})).all()}
    plan = plan_from(players, evidence, ignored, min_evidence=min_evidence)
    by_id = {p["id"]: p for p in players}
    ids = [m["remove"] for m in plan["merge"]] + [h["remove"] for h in plan["held"]]
    games = ({r[0]: r[1] for r in (await db.execute(text(_MANUAL_GAMES_SQL), {"ids": ids})).all()}
             if ids else {})
    for row in plan["merge"]:
        row.update(remove_name=by_id[row["remove"]]["name"], keep_name=by_id[row["keep"]]["name"],
                   games=games.get(row["remove"], 0))
    for row in plan["held"]:
        row.update(remove_name=by_id[row["remove"]]["name"], games=games.get(row["remove"], 0),
                   candidate_names=[by_id[c]["name"] for c in row["candidates"] if c in by_id])
    plan["initial_only"] = sum(1 for p in players if p["removable"] and initial_only(p["name"]))
    return plan


async def _merge_one(org_id, pair: dict) -> None:
    import uuid

    from app.models.db import FantasySeason, async_session_maker
    from app.routers.admin import _merge_players_core
    from app.services import fantasy_engine
    from app.services.audit_log import log_activity

    keep_id, remove_id = uuid.UUID(pair["keep"]), uuid.UUID(pair["remove"])
    async with async_session_maker() as db:
        fantasy_ids = [r[0] for r in (await db.execute(text(
            "SELECT DISTINCT fantasy_season_id FROM fantasy_pool_players WHERE player_id = :p"),
            {"p": remove_id})).all()]
        await _merge_players_core(db, keep_id, remove_id, org_id, SimpleNamespace(id=None))
        await log_activity(
            db, org_id=org_id, user_id=None, action="auto_merge_import_player",
            target_type="player", target_id=str(keep_id),
            details={"kept_player": {"id": str(keep_id), "name": pair["keep_name"]},
                     "removed_player": {"id": str(remove_id), "name": pair["remove_name"]},
                     "why": f"Created by an import as an initial-only name; in {pair['matches']} "
                            "paired match(es) it has the same surname, first initial, runs and "
                            "batting position as this synced player, and nobody else has the "
                            "label. Undo it from the merge log."},
            commit=True)
        for fs_id in fantasy_ids:
            try:
                fs = await db.get(FantasySeason, fs_id)
                if fs is not None:
                    await fantasy_engine.rescore_from_round(db, fs, 1)
                    await db.commit()
            except Exception as e:  # noqa: BLE001 - the merge itself is already committed
                await db.rollback()
                logger.warning("Fantasy re-score after import-player merge failed for season %s: %s", fs_id, e)


async def link_players(org_id, *, apply: bool = False, min_evidence: int = 1,
                       limit: Optional[int] = None) -> dict:
    """Find the pairs for one club and, with ``apply``, merge them.

    One session and transaction per pair, so a merge the core refuses leaves the
    others, and itself, untouched. Dry run unless ``apply``.
    """
    import uuid

    from app.models.db import async_session_maker

    org_id = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
    async with async_session_maker() as db:
        plan = await find_pairs(db, org_id, min_evidence=min_evidence)
    pairs = plan["merge"][:limit] if limit else plan["merge"]
    summary = {"initial_only": plan["initial_only"], "found": len(plan["merge"]),
               "merged": 0, "failed": 0, "pairs": pairs, "held": plan["held"]}
    if not apply:
        return summary
    for pr in pairs:
        try:
            await _merge_one(org_id, pr)
            pr["merged"] = True
            summary["merged"] += 1
        except Exception as e:  # noqa: BLE001 - one pair is never the whole run
            summary["failed"] += 1
            pr["error"] = str(getattr(e, "detail", None) or e)
            logger.warning("merge of import player %s into %s failed: %s",
                           pr["remove"], pr["keep"], pr["error"])
    return summary
