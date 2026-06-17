"""BetterFantasyCricket salary-cap squads — validation and round scoring.

Two jobs:
  - ``validate_squad``      check a manager's 12 against the role quota, budget
                            and captain rules before it is saved
  - ``score_squads_for_round`` turn the per-player round scores into each squad's
                            best-11 round total (captain doubled before the cut),
                            and roll the season ladder totals

The per-player points come from ``fantasy_engine.settle_round``; this layer adds
the squad rules on top. Transfer hits and the triple-captain chip integrate when
the transfer/chip endpoints land (a later phase); until then a squad's round
points are the best-11 with the ordinary captain double. Full design:
docs/betterfantasycricket.md.
"""
from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    FantasySquad, FantasySquadPlayer, FantasyPlayerRoundScore, FANTASY_ROLES,
)
from app.services.fantasy_scoring import DEFAULT_RULES, DEFAULT_SCORING, apply_captain


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_squad(picks: list[dict], pool: dict[str, dict], rules: dict, budget: float | None = None) -> list[str]:
    """Return a list of human-readable problems with a proposed squad (empty =
    valid). ``picks`` is ``[{player_id, is_captain, is_vice_captain}, ...]``;
    ``pool`` maps player_id -> {role, current_price, is_available}. The role of a
    pick is taken from the pool, not chosen, so composition is a property of who
    you pick."""
    errors: list[str] = []
    rules = rules or DEFAULT_RULES
    size = rules.get("squad_size", 12)
    quota = rules.get("role_quota", DEFAULT_RULES["role_quota"])
    budget = rules.get("budget", DEFAULT_RULES["budget"]) if budget is None else budget

    ids = [str(p["player_id"]) for p in picks]
    if len(ids) != size:
        errors.append(f"Pick exactly {size} players (you have {len(ids)}).")
    if len(set(ids)) != len(ids):
        errors.append("A player can't be picked twice.")

    unknown = [pid for pid in ids if pid not in pool]
    if unknown:
        errors.append("Some picks aren't in the pool.")
    unavailable = [pid for pid in ids if pid in pool and not pool[pid].get("is_available", True)]
    if unavailable:
        errors.append("Some picks aren't available this season.")

    by_role: dict[str, int] = defaultdict(int)
    for pid in ids:
        if pid in pool:
            by_role[pool[pid]["role"]] += 1
    for role in FANTASY_ROLES:
        want = quota.get(role, 0)
        if by_role.get(role, 0) != want:
            errors.append(f"Need {want} {role}(s), have {by_role.get(role, 0)}.")

    total = sum(float(pool[pid]["current_price"]) for pid in ids if pid in pool)
    if total > budget + 1e-6:
        errors.append(f"Over budget: {total:.1f} of {budget:.1f}.")

    caps = [p for p in picks if p.get("is_captain")]
    vices = [p for p in picks if p.get("is_vice_captain")]
    if len(caps) != 1:
        errors.append("Name exactly one captain.")
    if len(vices) > 1:
        errors.append("Name at most one vice-captain.")
    if caps and vices and str(caps[0]["player_id"]) == str(vices[0]["player_id"]):
        errors.append("Captain and vice-captain must be different players.")
    return errors


# ── Round scoring ────────────────────────────────────────────────────────────

def score_squad_round(picks, score_by_player: dict[str, tuple[float, int]], best_n: int, scoring: dict, is_triple: bool = False) -> dict:
    """Score one squad for a round. ``picks`` are its FantasySquadPlayer rows;
    ``score_by_player`` maps player_id -> (round_points, games_counted). The
    captain's points are doubled (tripled if the triple-captain chip is on, and
    the vice-captain inherits the multiplier if the captain didn't play), then
    the best ``best_n`` of the squad count."""
    scoring = scoring or DEFAULT_SCORING
    cap = next((p for p in picks if p.is_captain), None)
    vice = next((p for p in picks if p.is_vice_captain), None)
    cap_played = bool(cap) and score_by_player.get(str(cap.player_id), (0.0, 0))[1] > 0
    eff_captain_id = str(cap.player_id) if cap_played else (str(vice.player_id) if vice else None)

    entries = []
    for p in picks:
        pid = str(p.player_id)
        pts, _games = score_by_player.get(pid, (0.0, 0))
        is_cap = pid == eff_captain_id
        entries.append({
            "player_id": pid, "role": p.role, "points": round(pts, 2),
            "eff_points": apply_captain(pts, is_cap, is_triple, scoring),
            "is_captain": bool(p.is_captain), "is_vice": bool(p.is_vice_captain),
            "captained": is_cap,
        })

    entries.sort(key=lambda e: e["eff_points"], reverse=True)
    counted, dropped = entries[:best_n], entries[best_n:]
    for e in counted:
        e["counted"] = True
    for e in dropped:
        e["counted"] = False
    raw = round(sum(e["eff_points"] for e in counted), 2)
    # Preserve pick order in the stored snapshot for a stable display.
    entries.sort(key=lambda e: (e["role"], e["player_id"]))
    return {
        "raw_points": raw, "points": raw,
        "captain_id": eff_captain_id,
        "dropped_id": dropped[0]["player_id"] if dropped else None,
        "lineup": entries,
    }


async def score_squads_for_round(session: AsyncSession, fs, rnd) -> int:
    """Score every squad in the season for a round and roll the ladder totals.
    Idempotent on (squad, round). Returns the number of squads scored."""
    squads = (await session.execute(
        select(FantasySquad).where(FantasySquad.fantasy_season_id == fs.id)
    )).scalars().all()
    if not squads:
        return 0
    squad_ids = [s.id for s in squads]

    sp_rows = (await session.execute(
        select(FantasySquadPlayer).where(FantasySquadPlayer.squad_id.in_(squad_ids))
    )).scalars().all()
    picks_by_squad: dict = defaultdict(list)
    for sp in sp_rows:
        picks_by_squad[sp.squad_id].append(sp)

    score_rows = (await session.execute(
        select(
            FantasyPlayerRoundScore.player_id,
            FantasyPlayerRoundScore.total_points,
            FantasyPlayerRoundScore.games_counted,
        ).where(FantasyPlayerRoundScore.round_id == rnd.id)
    )).all()
    score_by_player = {str(pid): (float(tp), gc) for pid, tp, gc in score_rows}

    # Which squads played the triple-captain chip this round (set by the chip
    # endpoint, which pre-creates the round-score row).
    chip_rows = (await session.execute(
        text("SELECT squad_id, chip_used FROM fantasy_squad_round_scores WHERE round_id = CAST(:rid AS UUID)"),
        {"rid": str(rnd.id)},
    )).all()
    triple_squads = {str(sid) for sid, chip in chip_rows if chip == "triple_captain"}

    rules = fs.rules or DEFAULT_RULES
    scoring = fs.scoring or DEFAULT_SCORING
    best_n = rules.get("count_best_n", 11)

    for sq in squads:
        res = score_squad_round(picks_by_squad.get(sq.id, []), score_by_player, best_n, scoring,
                                is_triple=str(sq.id) in triple_squads)
        await session.execute(
            text("""
                INSERT INTO fantasy_squad_round_scores
                    (squad_id, round_id, points, raw_points, captain_player_id, dropped_player_id, lineup, created_at)
                VALUES (CAST(:sid AS UUID), CAST(:rid AS UUID), :points, :raw,
                        CAST(:cap AS UUID), CAST(:drop AS UUID), CAST(:lineup AS JSONB), NOW())
                ON CONFLICT (squad_id, round_id) DO UPDATE SET
                    points = EXCLUDED.raw_points - fantasy_squad_round_scores.transfer_hit,
                    raw_points = EXCLUDED.raw_points,
                    captain_player_id = EXCLUDED.captain_player_id,
                    dropped_player_id = EXCLUDED.dropped_player_id,
                    lineup = EXCLUDED.lineup
            """),
            {
                "sid": str(sq.id), "rid": str(rnd.id),
                "points": res["points"], "raw": res["raw_points"],
                "cap": res["captain_id"], "drop": res["dropped_id"],
                "lineup": json.dumps(res["lineup"]),
            },
        )

    # Roll each squad's season total from its round scores.
    await session.execute(
        text("""
            UPDATE fantasy_squads sq SET total_points = COALESCE(t.total, 0), updated_at = NOW()
            FROM (
                SELECT srs.squad_id, SUM(srs.points) AS total
                FROM fantasy_squad_round_scores srs
                JOIN fantasy_rounds r ON r.id = srs.round_id
                WHERE r.fantasy_season_id = CAST(:fs AS UUID)
                GROUP BY srs.squad_id
            ) t
            WHERE sq.id = t.squad_id AND sq.fantasy_season_id = CAST(:fs AS UUID)
        """),
        {"fs": str(fs.id)},
    )

    # Rollover: settling this round grants the next round's free transfer, banked
    # up to the cap. This also resets a wildcard's unlimited window to normal.
    per = int(rules.get("free_transfers_per_round", 1))
    cap = per + int(rules.get("max_banked_transfers", 2))
    await session.execute(
        text("UPDATE fantasy_squads SET free_transfers = LEAST(free_transfers + :per, :cap) "
             "WHERE fantasy_season_id = CAST(:fs AS UUID)"),
        {"per": per, "cap": cap, "fs": str(fs.id)},
    )
    return len(squads)
