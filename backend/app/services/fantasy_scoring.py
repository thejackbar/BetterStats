"""BetterFantasyCricket scoring and role classification — pure logic.

The heart of the module: turn a player's real stats into fantasy points with the
role-weighted, format-independent model from the spec. Everything here is pure
(no DB, no I/O), so it is unit-testable and reused identically by round
settlement, the pricing baseline and any live preview.

Scoring model (defaults; all tunable per season via the JSONB `scoring` blob):
  - batting: +1/run, +1/four, +2/six, +16 at 50, +32 at 100, duck -4
  - bowling: +25/wicket, +8 for a 3-wkt haul, +16 for 5, +8/maiden
  - fielding: +8/catch, +12/stumping, +12/run-out
  - appearance: +4 for taking the field
  - role weighting: a player's output OUTSIDE their specialism is multiplied by
    the off-role multiplier (default 1.5). Outfield fielding, the appearance
    point and the captain multiplier are never role-weighted.

Milestone bonuses and wicket-haul bonuses are NOT cumulative (a hundred scores
the hundred bonus only, a five-for scores the five bonus only) and are applied
per innings, so callers pass per-innings batting/bowling rows.

Captain doubling is applied at squad scoring, not here. Full design:
docs/betterfantasycricket.md.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from app.models.db import FANTASY_ROLES


# ── Default config (seeded into a fantasy_season; editable per club) ───────────

DEFAULT_SCORING: dict = {
    # batting
    "run": 1, "four": 1, "six": 2, "fifty": 16, "hundred": 32, "duck": -4,
    # bowling
    "wicket": 25, "three_wickets": 8, "five_wickets": 16, "maiden": 8,
    # fielding
    "catch": 8, "stumping": 12, "run_out": 12,
    # appearance + multipliers
    "appearance": 4,
    "off_role_multiplier": 1.5,
    "captain_multiplier": 2,
    "triple_captain_multiplier": 3,
}

DEFAULT_RULES: dict = {
    "squad_size": 12,
    "count_best_n": 11,
    "role_quota": {"keeper": 1, "batter": 4, "allrounder": 3, "bowler": 4},
    "budget": 100.0,
    "free_transfers_per_round": 1,
    "max_banked_transfers": 2,
    "transfer_hit": 4,
    "wildcards_per_half": 1,
    "triple_captains_per_half": 1,
    # How many seasons of form (this year + prior ones) feed the price baseline
    # and the pickable pool. Configurable at setup.
    "price_window_years": 3,
}


# ── Role classification ────────────────────────────────────────────────────────
# The saved profile role wins; otherwise we guess from the player's record. The
# admin can override either (stored as role_source on the pool row).

# players.player_role values come from ROLE_OPTS in playerAttributes.js.
_PROFILE_ROLE_MAP = {
    "batter": "batter",
    "batsman": "batter",
    "bowler": "bowler",
    "all rounder": "allrounder",
    "all-rounder": "allrounder",
    "allrounder": "allrounder",
    "wicketkeeper": "keeper",
    "wicket keeper": "keeper",
    "wicketkeeper-batter": "keeper",
    "keeper": "keeper",
}


def classify_role(
    *,
    player_role: str | None = None,
    skill_positions: Sequence[str] | None = None,
    bat_innings: int = 0,
    wickets: int = 0,
    bowl_innings: int = 0,
    keeper_dismissals: int = 0,
) -> tuple[str, str]:
    """Return ``(role, source)`` where role is one of FANTASY_ROLES and source is
    ``'profile'`` (from the saved attributes) or ``'auto'`` (guessed from stats).

    The caller layers an admin override on top (source ``'admin'``).
    """
    # 1. Saved profile — the explicit role, then the skill facets.
    pr = (player_role or "").strip().lower()
    if pr in _PROFILE_ROLE_MAP:
        return _PROFILE_ROLE_MAP[pr], "profile"
    sk = {str(s).upper() for s in (skill_positions or [])}
    if "WKT" in sk:
        return "keeper", "profile"
    if sk == {"ALL"} or sk == {"BAT", "BWL"}:
        return "allrounder", "profile"
    if sk == {"BWL"}:
        return "bowler", "profile"
    if sk == {"BAT"}:
        return "batter", "profile"

    # 2. Stat-derived guess (mirrors BetterIQ's all-rounder floors).
    if keeper_dismissals >= 3:
        return "keeper", "auto"
    if bat_innings >= 8 and wickets >= 8:
        return "allrounder", "auto"
    if wickets >= 8:
        return "bowler", "auto"
    if bowl_innings > 0 and bowl_innings >= bat_innings and wickets >= 3:
        return "bowler", "auto"
    return "batter", "auto"


# ── Per-innings scoring ────────────────────────────────────────────────────────

def score_batting_innings(runs: int, fours: int, sixes: int, out: bool, scoring: Mapping) -> float:
    """Points for one batting innings. Milestone bonus is the highest tier only;
    a duck (dismissed for 0) costs the duck penalty. Callers must exclude
    absent / did-not-bat rows (not innings)."""
    pts = runs * scoring["run"] + fours * scoring["four"] + sixes * scoring["six"]
    if runs >= 100:
        pts += scoring["hundred"]
    elif runs >= 50:
        pts += scoring["fifty"]
    if out and runs == 0:
        pts += scoring["duck"]
    return pts


def score_bowling_innings(wickets: int, maidens: int, scoring: Mapping) -> float:
    """Points for one bowling innings. Haul bonus is the highest tier only."""
    pts = wickets * scoring["wicket"] + maidens * scoring["maiden"]
    if wickets >= 5:
        pts += scoring["five_wickets"]
    elif wickets >= 3:
        pts += scoring["three_wickets"]
    return pts


def _off_role_multipliers(role: str, m: float) -> tuple[float, float, float]:
    """``(batting, bowling, keeping)`` multipliers for a role. Output outside the
    specialism is boosted by ``m``; on-role output is at base (1.0)."""
    if role == "bowler":
        return (m, 1.0, 1.0)      # batting boosted
    if role == "keeper":
        return (m, 1.0, m)        # batting + keeping boosted
    if role == "allrounder":
        return (1.0, 1.0, 1.0)    # both are the job
    return (1.0, m, 1.0)          # batter: bowling boosted


# ── Per-game and per-round scoring ─────────────────────────────────────────────

def score_player_game(
    *,
    batting: Iterable[Mapping] = (),
    bowling: Iterable[Mapping] = (),
    catches_wk: int = 0,
    stumpings: int = 0,
    catches_nonwk: int = 0,
    run_outs: int = 0,
    played: bool = True,
    role: str = "batter",
    scoring: Mapping = DEFAULT_SCORING,
) -> tuple[float, float, dict]:
    """Score one game for one player.

    ``batting`` / ``bowling`` are per-innings rows: batting needs ``runs``,
    ``fours``, ``sixes``, ``out``; bowling needs ``wickets``, ``maidens``.
    Returns ``(base, total, breakdown)`` where base is unweighted and total has
    the role multiplier applied. The captain bonus is applied later at the squad.
    """
    m = float(scoring.get("off_role_multiplier", 1.5))
    bat_mult, bowl_mult, keep_mult = _off_role_multipliers(role, m)

    bat_pts = sum(
        score_batting_innings(b["runs"], b.get("fours", 0) or 0, b.get("sixes", 0) or 0, bool(b.get("out")), scoring)
        for b in batting
    )
    bowl_pts = sum(
        score_bowling_innings(w["wickets"] or 0, w.get("maidens", 0) or 0, scoring)
        for w in bowling
    )
    keep_pts = catches_wk * scoring["catch"] + stumpings * scoring["stumping"]
    field_pts = catches_nonwk * scoring["catch"] + run_outs * scoring["run_out"]
    app_pts = scoring["appearance"] if played else 0

    base = bat_pts + bowl_pts + keep_pts + field_pts + app_pts
    total = bat_pts * bat_mult + bowl_pts * bowl_mult + keep_pts * keep_mult + field_pts + app_pts
    breakdown = {
        "batting": round(bat_pts, 2), "bowling": round(bowl_pts, 2),
        "keeping": round(keep_pts, 2), "fielding": round(field_pts, 2),
        "appearance": app_pts, "role": role, "multiplier": m,
    }
    return round(base, 2), round(total, 2), breakdown


def score_player_round(games: Sequence[Mapping], role: str, scoring: Mapping = DEFAULT_SCORING) -> tuple[float, float, dict]:
    """Sum a player's points across every game they played in a round.

    ``games`` is a list of kwargs dicts for ``score_player_game`` (one per game).
    A player who turned out twice in a round has both games summed.
    """
    base = total = 0.0
    agg = {"batting": 0.0, "bowling": 0.0, "keeping": 0.0, "fielding": 0.0, "appearance": 0.0}
    for g in games:
        b, t, bd = score_player_game(role=role, scoring=scoring, **g)
        base += b
        total += t
        for k in agg:
            agg[k] += bd.get(k, 0) or 0
    agg = {k: round(v, 2) for k, v in agg.items()}
    agg["role"] = role
    agg["games"] = len(games)
    return round(base, 2), round(total, 2), agg


def apply_captain(total: float, is_captain: bool, is_triple: bool, scoring: Mapping = DEFAULT_SCORING) -> float:
    """The captain multiplier on a player's round total, applied at the squad
    before the best-N cut. Triple-captain (a chip) overrides the double."""
    if not is_captain:
        return total
    mult = scoring.get("triple_captain_multiplier", 3) if is_triple else scoring.get("captain_multiplier", 2)
    return round(total * mult, 2)
