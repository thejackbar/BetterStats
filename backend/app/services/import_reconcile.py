"""BetterImport reconciler — derive the non-GR remainder of a club's upload.

A club uploads its own historical summaries (``imported_stats``). Those overlap
with the Grassroots (GR) data we already hold, so we must never simply add them.
This module derives, per player, only the part of the club's figures that GR
does NOT already provide, and writes it to ``import_effective_deltas`` (read by
the effective view's ``'import'`` branch).

The rule the user chose: **GR wins per season, a career-level residual catches
the gap.**

  * For each season the club gives: if GR already has that (player, season), the
    imported season is dropped (GR's richer per-game detail wins). Otherwise it's
    emitted as a season delta.
  * One career residual per player = ``max(0, club_total − GR − emitted)``.

Because the only thing ever added to GR is ``max(0, club − GR)``, the career sum
is pinned to the club's stated total and can't exceed it (Wayne Giles → 473, not
698). ``reconcile_imported_totals`` runs on commit AND as the final pass of every
org sync, so the residual auto-shrinks as GR coverage grows — no re-import.

The arithmetic core (``reconcile_player`` and friends) is pure and DB-free so it
can be exercised headless — see ``scripts/verify_import_reconcile.py``.
"""

from decimal import Decimal
from typing import Optional


# Count metrics reconciled by ``max(0, club − gr − emitted)``. High score and
# best bowling are carried (not summed) so the view's MAX() surfaces them;
# averages/SR/economy are derived on read and never stored here.
COUNT_METRICS = (
    "matches", "batting_innings", "runs", "not_outs", "balls_faced",
    "fifties", "hundreds", "ducks", "fours", "sixes",
    "bowling_innings", "wickets", "bowling_balls", "runs_conceded", "maidens",
    "five_wicket_innings", "wides", "no_balls",
    "catches", "catches_wk", "run_outs", "stumpings",
)

# A career residual is only worth emitting if one of these is positive.
_MEANINGFUL = ("matches", "runs", "batting_innings", "wickets", "bowling_innings", "catches")


# ── pure arithmetic core (no DB) ─────────────────────────────────────────────


def balls_to_overs(balls) -> Decimal:
    """62 balls → Decimal('10.2') (cricket notation: 10 overs, 2 balls)."""
    balls = max(0, int(balls or 0))
    o, b = divmod(balls, 6)
    return Decimal(f"{o}.{b}")


def _max_opt(a, b):
    """Larger of two optionals, ignoring None."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _blank():
    acc = {k: 0 for k in COUNT_METRICS}
    acc["high_score"] = None
    acc["is_hs_not_out"] = False
    acc["best_bowling_wickets"] = None
    acc["best_bowling_figures"] = None
    return acc


def accumulate(acc: Optional[dict], m: dict) -> dict:
    """Sum count metrics; keep the max high-score / best-bowling (with its flag).

    The 'club total' for a player is the accumulation of all their import rows;
    GR totals accumulate the player's GR season rows the same way.
    """
    if acc is None:
        acc = _blank()
    for k in COUNT_METRICS:
        acc[k] = (acc.get(k, 0) or 0) + (m.get(k, 0) or 0)
    hs = m.get("high_score")
    if hs is not None and (acc["high_score"] is None or hs > acc["high_score"]):
        acc["high_score"] = hs
        acc["is_hs_not_out"] = bool(m.get("is_hs_not_out") or False)
    bw = m.get("best_bowling_wickets")
    if bw is not None and (acc["best_bowling_wickets"] is None or bw > acc["best_bowling_wickets"]):
        acc["best_bowling_wickets"] = bw
        acc["best_bowling_figures"] = m.get("best_bowling_figures")
    return acc


def resolve_club_totals(career_metrics: Optional[dict], detail_sum: Optional[dict]) -> dict:
    """The club's authoritative career totals.

    ``career_metrics`` = an explicit whole-career total the club gave (or None).
    ``detail_sum`` = the sum of their per-season rows + any explicit "Prior"
    bucket. If both are present we take the per-metric **larger** (reconcile to
    the more complete figure — the conflict is flagged to the admin at import).
    """
    if career_metrics is None:
        return detail_sum if detail_sum is not None else _blank()
    if detail_sum is None:
        return career_metrics
    out = _blank()
    for k in COUNT_METRICS:
        out[k] = max(career_metrics.get(k, 0) or 0, detail_sum.get(k, 0) or 0)
    if (career_metrics.get("high_score") or -1) >= (detail_sum.get("high_score") or -1):
        out["high_score"] = career_metrics.get("high_score")
        out["is_hs_not_out"] = career_metrics.get("is_hs_not_out", False)
    else:
        out["high_score"] = detail_sum.get("high_score")
        out["is_hs_not_out"] = detail_sum.get("is_hs_not_out", False)
    if (career_metrics.get("best_bowling_wickets") or -1) >= (detail_sum.get("best_bowling_wickets") or -1):
        out["best_bowling_wickets"] = career_metrics.get("best_bowling_wickets")
        out["best_bowling_figures"] = career_metrics.get("best_bowling_figures")
    else:
        out["best_bowling_wickets"] = detail_sum.get("best_bowling_wickets")
        out["best_bowling_figures"] = detail_sum.get("best_bowling_figures")
    return out


def reconcile_player(club: dict, gr: dict, import_seasons, gr_season_ids) -> tuple:
    """The core of the guarantee. Returns (season_deltas, career_residual).

    ``club`` — the player's authoritative career totals (from resolve_club_totals).
    ``gr``   — the sum of the player's GR (player_season_stats) rows for this org.
    ``import_seasons`` — list of (season_id, metrics) the club gave per season.
    ``gr_season_ids``  — the set of season_ids GR already covers for this player.

    season_deltas: list of (season_id, metrics) to add (GR-missing seasons only).
    career_residual: metrics dict for the single career catch-all, or None.
    """
    emitted = {k: 0 for k in COUNT_METRICS}
    season_deltas = []
    for season_id, metrics in import_seasons:
        if season_id is None or season_id in gr_season_ids:
            # GR wins (or the season couldn't be matched). It still counts toward
            # the club total, so the residual below absorbs it — never dropped.
            continue
        season_deltas.append((season_id, metrics))
        for k in COUNT_METRICS:
            emitted[k] += metrics.get(k, 0) or 0

    residual = {
        k: max(0, (club.get(k, 0) or 0) - (gr.get(k, 0) or 0) - emitted[k])
        for k in COUNT_METRICS
    }
    career = None
    if any(residual[k] > 0 for k in _MEANINGFUL):
        career = dict(residual)
        # Carry the club's career-best so the view's MAX() can surface them even
        # though the residual has no per-innings detail of its own.
        career["high_score"] = club.get("high_score")
        career["is_hs_not_out"] = club.get("is_hs_not_out", False)
        career["best_bowling_wickets"] = club.get("best_bowling_wickets")
        career["best_bowling_figures"] = club.get("best_bowling_figures")
    return season_deltas, career


# ── column maps between the stored tables and the canonical metric dict ───────

# imported_stats (truth) column  →  canonical metric key
_IMPORTED_COUNTS = {
    "games_played": "matches",
    "batting_innings": "batting_innings",
    "batting_runs": "runs",
    "batting_not_outs": "not_outs",
    "batting_balls": "balls_faced",
    "batting_fifties": "fifties",
    "batting_hundreds": "hundreds",
    "batting_ducks": "ducks",
    "batting_fours": "fours",
    "batting_sixes": "sixes",
    "bowling_innings": "bowling_innings",
    "bowling_wickets": "wickets",
    "bowling_balls": "bowling_balls",
    "bowling_runs": "runs_conceded",
    "bowling_maidens": "maidens",
    "bowling_five_wicket_innings": "five_wicket_innings",
    "bowling_wides": "wides",
    "bowling_no_balls": "no_balls",
    "fielding_catches": "catches",
    "fielding_catches_wk": "catches_wk",
    "fielding_run_outs": "run_outs",
    "fielding_stumpings": "stumpings",
}


def imported_to_metrics(row) -> dict:
    """ImportedStat ORM row → canonical metric dict."""
    m = {canon: getattr(row, col) or 0 for col, canon in _IMPORTED_COUNTS.items()}
    m["high_score"] = row.batting_high_score
    m["is_hs_not_out"] = bool(row.batting_high_score_not_out)
    m["best_bowling_wickets"] = row.bowling_best_wickets
    m["best_bowling_figures"] = row.bowling_best_figures
    return m


def pss_to_metrics(row) -> dict:
    """PlayerSeasonStats ORM row → canonical metric dict (names already match)."""
    m = {k: (getattr(row, k, 0) or 0) for k in COUNT_METRICS}
    m["high_score"] = row.high_score
    m["is_hs_not_out"] = bool(row.is_hs_not_out)
    m["best_bowling_wickets"] = row.best_bowling_wickets
    m["best_bowling_figures"] = row.best_bowling_figures
    return m


def delta_kwargs(m: dict) -> dict:
    """Canonical metric dict → ImportEffectiveDelta column kwargs."""
    balls = max(0, int(m.get("bowling_balls", 0) or 0))
    out = {k: (m.get(k, 0) or 0) for k in COUNT_METRICS}
    out["bowling_balls"] = balls
    out["overs"] = balls_to_overs(balls)
    out["high_score"] = m.get("high_score")
    out["is_hs_not_out"] = bool(m.get("is_hs_not_out") or False)
    out["best_bowling_wickets"] = m.get("best_bowling_wickets")
    out["best_bowling_figures"] = m.get("best_bowling_figures")
    return out


# ── DB orchestrator ──────────────────────────────────────────────────────────


async def reconcile_imported_totals(org_id_str: str) -> int:
    """Regenerate ``import_effective_deltas`` for an org from ``imported_stats``.

    Idempotent and self-healing: wipes the org's derived rows and recomputes them
    against current GR coverage. A no-op (returns 0) for orgs with no imports, so
    it's safe to call unconditionally at the end of every sync. Returns the number
    of delta rows written.
    """
    import uuid as _uuid

    from sqlalchemy import select, delete, or_
    from app.models.db import (
        Player, Season, PlayerSeasonStats,
        ImportedStat, ImportEffectiveDelta, async_session_maker,
    )

    try:
        org_uuid = _uuid.UUID(str(org_id_str))
    except (ValueError, TypeError, AttributeError):
        return 0

    async with async_session_maker() as session:
        # Load this org's uploaded truth, grouped by player.
        truth_rows = (
            await session.execute(
                select(ImportedStat).where(ImportedStat.organisation_id == org_uuid)
            )
        ).scalars().all()

        # Always clear the org's derived deltas first (so undoing the last import
        # leaves a clean slate).
        await session.execute(
            delete(ImportEffectiveDelta).where(ImportEffectiveDelta.organisation_id == org_uuid)
        )

        if not truth_rows:
            await session.commit()
            return 0

        by_player: dict = {}
        for r in truth_rows:
            by_player.setdefault(r.player_id, []).append(r)

        pids = list(by_player.keys())

        # GR coverage for these players, scoped exactly like the view's api
        # branch (player's org == season's org, or NULL-org player).
        gr_rows = (
            await session.execute(
                select(PlayerSeasonStats)
                .join(Season, Season.id == PlayerSeasonStats.season_id)
                .join(Player, Player.id == PlayerSeasonStats.player_id)
                .where(Season.organisation_id == org_uuid)
                .where(or_(Player.organisation_id.is_(None), Player.organisation_id == Season.organisation_id))
                .where(PlayerSeasonStats.player_id.in_(pids))
            )
        ).scalars().all()

        gr_by_player: dict = {}
        for pss in gr_rows:
            g = gr_by_player.setdefault(pss.player_id, {"season_ids": set(), "totals": None})
            g["season_ids"].add(pss.season_id)
            g["totals"] = accumulate(g["totals"], pss_to_metrics(pss))

        written = 0
        for pid, rows in by_player.items():
            season_rows: dict = {}     # season_id -> accumulated metrics
            detail_sum: Optional[dict] = None
            career_metrics: Optional[dict] = None

            for r in rows:
                m = imported_to_metrics(r)
                if r.is_prior_bucket:
                    # Explicit pre-GR / adjustments lump: additive disjoint truth.
                    detail_sum = accumulate(detail_sum, m)
                elif r.scope == "season" and r.season_id is not None:
                    season_rows[r.season_id] = accumulate(season_rows.get(r.season_id), m)
                    detail_sum = accumulate(detail_sum, m)
                elif r.scope == "career":
                    career_metrics = accumulate(career_metrics, m)
                else:
                    # season scope but unmatched season → fold into the residual.
                    detail_sum = accumulate(detail_sum, m)

            club = resolve_club_totals(career_metrics, detail_sum)
            gr = gr_by_player.get(pid, {"season_ids": set(), "totals": None})
            gr_totals = gr["totals"] if gr["totals"] is not None else _blank()

            season_deltas, career = reconcile_player(
                club, gr_totals, list(season_rows.items()), gr["season_ids"]
            )

            for season_id, metrics in season_deltas:
                session.add(ImportEffectiveDelta(
                    organisation_id=org_uuid, player_id=pid,
                    scope="season", season_id=season_id, grade_id=None,
                    **delta_kwargs(metrics),
                ))
                written += 1

            if career is not None:
                session.add(ImportEffectiveDelta(
                    organisation_id=org_uuid, player_id=pid,
                    scope="career", season_id=None, grade_id=None,
                    **delta_kwargs(career),
                ))
                written += 1

        await session.commit()
        return written
