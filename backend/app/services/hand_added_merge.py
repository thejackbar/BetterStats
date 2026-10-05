"""Merge a player the club typed in by hand into the synced record that turns up
when they play.

A club adds a new player before their first game: in the roster, the Directory,
Fees, nets, BetterSelect or as a Fantasy "Add new player". Once they play,
Cricket Australia's feed creates a second record for the same person, with the
games and the Cricket Australia id. Until the two are merged, the club's squads,
availability, fee line, family link and Fantasy picks sit on one record and the
games sit on the other, so the person looks like they never played. Merging them
used to be a screen somebody had to open.

This does it as soon as the pair is unambiguous, through the club's own merge
(`routers/admin._merge_players_core`): it moves records and never deletes them,
every table in `merge_carry.CARRIED` follows the person, and it is written to the
merge log, so a club can undo any of it from the same screen it undoes a manual
merge on. The synced record is the one kept.

WHEN A PAIR IS "UNAMBIGUOUS". Wrong merges are worse than none, so every one of
these has to hold, and anything else is left for the merge screen:

* the hand-added record has no Cricket Australia id, no PlayHQ id and no import
  behind it, is a player, and has not been claimed by a login;
* it has no cricket of its own anywhere: no game, innings, spell, catch, season
  total, import or hand-typed adjustment (a record with history is a person with
  a past, not a new roster entry);
* the twin has a Cricket Australia id, no import, has played, and has played ONLY
  in the club's latest season, so a long-standing "Sam Smith" is never taken for
  this year's new "Sam Smith";
* the two share a full name (two words or more, no bare initials or asterisks)
  and no other player of the club has it;
* nobody in the name group asked to be removed (`privacy_hidden_at`);
* the pair is not one the club chose to keep apart (`merge_pair_ignores`).

Nothing here reads another club's players. The one thing the merge does not do
for itself is Fantasy's points, so a merged-away pool player's seasons are scored
again from round 1, the way the Fantasy screen's own merge button does.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.participant_names import full_name_key, looks_full

logger = logging.getLogger(__name__)

# Every table that records cricket a player DID. A hand-added record with a row in
# any of them is a person with history, and is never merged automatically. Tables
# keyed on another column name are listed with it.
_CRICKET_TABLES: tuple[tuple[str, str], ...] = (
    ("game_appearances", "player_id"),
    ("batting_innings", "player_id"),
    ("bowling_spells", "player_id"),
    ("fielding_stats", "player_id"),
    ("player_season_stats", "player_id"),
    ("player_season_grade_stats", "player_id"),
    ("manual_batting_innings", "player_id"),
    ("manual_bowling_spells", "player_id"),
    ("manual_fielding_stats", "player_id"),
    ("manual_season_adjustments", "player_id"),
    ("manual_career_adjustments", "player_id"),
    ("imported_stats", "player_id"),
)


async def _with_cricket(db: AsyncSession, ids: list) -> set:
    """Which of these players hold a row in any cricket table."""
    if not ids:
        return set()
    union = " UNION ".join(
        f"SELECT {col} AS pid FROM {tbl} WHERE {col} = ANY(CAST(:ids AS uuid[]))"
        for tbl, col in _CRICKET_TABLES)
    rows = await db.execute(text(union), {"ids": [str(i) for i in ids]})
    return {r[0] for r in rows.fetchall()}


async def _played_only_this_year(db: AsyncSession, org_id, ids: list) -> dict:
    """``{player id: True}`` for twins that have played at all and have played in no
    season before the club's latest. A twin with nothing recorded, or with an older
    season anywhere, is absent."""
    if not ids:
        return {}
    year = (await db.execute(text(
        "SELECT MAX(year) FROM seasons WHERE organisation_id = CAST(:o AS UUID)"),
        {"o": str(org_id)})).scalar()
    if year is None:
        return {}
    params = {"ids": [str(i) for i in ids], "y": int(year)}
    any_games = {r[0] for r in (await db.execute(text("""
        SELECT player_id FROM (
            SELECT player_id, game_id FROM game_appearances
            UNION ALL SELECT player_id, game_id FROM batting_innings
            UNION ALL SELECT player_id, game_id FROM bowling_spells
            UNION ALL SELECT player_id, game_id FROM fielding_stats
        ) x WHERE player_id = ANY(CAST(:ids AS uuid[])) GROUP BY player_id"""), params)).all()}
    any_season = {r[0] for r in (await db.execute(text("""
        SELECT player_id FROM player_season_stats
         WHERE player_id = ANY(CAST(:ids AS uuid[])) AND matches > 0 GROUP BY player_id"""), params)).all()}
    older = {r[0] for r in (await db.execute(text("""
        SELECT x.player_id FROM (
            SELECT player_id, game_id FROM game_appearances
            UNION ALL SELECT player_id, game_id FROM batting_innings
            UNION ALL SELECT player_id, game_id FROM bowling_spells
            UNION ALL SELECT player_id, game_id FROM fielding_stats
        ) x
        JOIN games g ON g.id = x.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE x.player_id = ANY(CAST(:ids AS uuid[])) AND s.year < :y
        UNION
        SELECT pss.player_id FROM player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        WHERE pss.player_id = ANY(CAST(:ids AS uuid[])) AND s.year < :y"""), params)).all()}
    return {pid: True for pid in (any_games | any_season) if pid not in older}


async def find_pairs(db: AsyncSession, org_id) -> list[dict]:
    """Every hand-added record with exactly one synced twin, as
    ``{"keep": {id, name}, "remove": {id, name}}`` (keep is the synced record)."""
    players = (await db.execute(text("""
        SELECT p.id, COALESCE(NULLIF(p.display_name_override, ''), p.name) AS name,
               (p.grassroots_id IS NULL AND p.playhq_id IS NULL
                AND p.cricketstatz_player_id IS NULL AND p.import_batch_id IS NULL
                AND p.user_id IS NULL AND COALESCE(p.claimed, FALSE) = FALSE) AS hand,
               (p.grassroots_id IS NOT NULL
                AND p.cricketstatz_player_id IS NULL AND p.import_batch_id IS NULL) AS synced,
               (p.privacy_hidden_at IS NOT NULL) AS removed
          FROM players p
         WHERE p.organisation_id = CAST(:o AS UUID) AND p.is_player IS NOT FALSE"""),
        {"o": str(org_id)})).mappings().all()

    by_key: dict[str, list] = {}
    for p in players:
        if looks_full(p["name"]):
            by_key.setdefault(full_name_key(p["name"]), []).append(p)

    candidates = []
    for group in by_key.values():
        # A person who asked to be removed is never merged automatically, from
        # either side: a merge copies columns across and moves records, and could
        # put their cricket on a visible record. It also counts as "somebody else
        # with the name", so the group is left alone. The merge screen is still
        # there for a human who knows why.
        if any(p["removed"] for p in group):
            continue
        hands = [p for p in group if p["hand"]]
        twins = [p for p in group if p["synced"]]
        # Exactly one of each and nobody else with the name: two people called
        # Sam Smith is a question for a human.
        if len(group) == 2 and len(hands) == 1 and len(twins) == 1:
            candidates.append((hands[0], twins[0]))
    if not candidates:
        return []

    has_cricket = await _with_cricket(db, [h["id"] for h, _ in candidates])
    new_twins = await _played_only_this_year(db, org_id, [t["id"] for _, t in candidates])
    ignored = {frozenset((r[0], r[1])) for r in (await db.execute(text(
        "SELECT player_a_id::text, player_b_id::text FROM merge_pair_ignores "
        "WHERE org_id = CAST(:o AS UUID)"), {"o": str(org_id)})).all()}

    out = []
    for h, t in candidates:
        if h["id"] in has_cricket or t["id"] not in new_twins:
            continue
        if frozenset((str(h["id"]), str(t["id"]))) in ignored:
            continue
        out.append({"keep": {"id": t["id"], "name": t["name"]},
                    "remove": {"id": h["id"], "name": h["name"]}})
    return out


async def merge_pairs(org_id, *, apply: bool = True, pairs: Optional[list] = None) -> dict:
    """Find the unambiguous pairs for one club and, with ``apply``, merge them.

    Never raises: it runs after a sync, and a failed merge must not fail the sync.
    Each pair has its own session and transaction, so one that cannot merge (a data
    conflict the merge refuses) leaves the others, and itself, untouched.
    """
    import uuid

    from app.models.db import async_session_maker

    summary = {"found": 0, "merged": 0, "failed": 0, "pairs": []}
    try:
        # Sync hands over the id as a string; the merge compares it with the
        # players' own UUID column and refuses a str as "another club".
        org_id = org_id if isinstance(org_id, uuid.UUID) else uuid.UUID(str(org_id))
        if pairs is None:
            async with async_session_maker() as db:
                pairs = await find_pairs(db, org_id)
        summary["found"] = len(pairs)
        for pr in pairs:
            row = {"keep": str(pr["keep"]["id"]), "remove": str(pr["remove"]["id"]),
                   "name": pr["keep"]["name"], "merged": False}
            summary["pairs"].append(row)
            if not apply:
                continue
            try:
                await _merge_one(org_id, pr)
                row["merged"] = True
                summary["merged"] += 1
            except Exception as e:  # noqa: BLE001 - see docstring
                summary["failed"] += 1
                row["error"] = str(getattr(e, "detail", None) or e)
                logger.warning("auto-merge of hand-added player %s into %s failed: %s",
                               pr["remove"]["id"], pr["keep"]["id"], row["error"])
    except Exception as e:  # noqa: BLE001
        logger.error("hand-added player merge failed for org %s: %s", org_id, e)
    if summary["merged"]:
        logger.info("Merged %d hand-added player(s) into their synced record for org %s",
                    summary["merged"], org_id)
    return summary


async def _merge_one(org_id, pair: dict) -> None:
    from app.models.db import FantasySeason, async_session_maker
    from app.routers.admin import _merge_players_core
    from app.services import fantasy_engine
    from app.services.audit_log import log_activity

    keep_id, remove_id = pair["keep"]["id"], pair["remove"]["id"]
    async with async_session_maker() as db:
        # Read before the merge: the pool entry is gone afterwards.
        fantasy_ids = [r[0] for r in (await db.execute(text(
            "SELECT DISTINCT fantasy_season_id FROM fantasy_pool_players WHERE player_id = :p"),
            {"p": remove_id})).all()]
        # `_merge_players_core` takes the acting user only to name them in the audit
        # entry; there is no one here, so the entry says it was automatic instead.
        await _merge_players_core(db, keep_id, remove_id, org_id, SimpleNamespace(id=None))
        await log_activity(
            db, org_id=org_id, user_id=None, action="auto_merge_hand_added",
            target_type="player", target_id=str(keep_id),
            details={"kept_player": {"id": str(keep_id), "name": pair["keep"]["name"]},
                     "removed_player": {"id": str(remove_id), "name": pair["remove"]["name"]},
                     "why": "Added by hand, then played: same full name, no other player with it, "
                            "no cricket of their own, and the synced record is new this season. "
                            "Undo it from the merge log."},
            commit=True)
        for fs_id in fantasy_ids:
            try:
                fs = await db.get(FantasySeason, fs_id)
                if fs is not None:
                    await fantasy_engine.rescore_from_round(db, fs, 1)
                    await db.commit()
            except Exception as e:  # noqa: BLE001 - the merge itself is already committed
                await db.rollback()
                logger.warning("Fantasy re-score after auto-merge failed for season %s: %s", fs_id, e)
