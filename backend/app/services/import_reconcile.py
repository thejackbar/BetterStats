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


def assemble_club_inputs(items) -> tuple:
    """Group a player's import rows into (club_totals, import_seasons).

    Each item: {"scope", "season_id", "is_prior_bucket", "metrics"}. Shared by
    the commit-time reconciler and the read-only preview so they agree exactly.
    A prior-bucket row (or a 'season' row with no matched season) is additive
    disjoint truth → it counts toward the club total but emits no season delta.
    """
    season_rows: dict = {}
    detail_sum: Optional[dict] = None
    career_metrics: Optional[dict] = None
    for it in items:
        m = it["metrics"]
        if it.get("is_prior_bucket"):
            detail_sum = accumulate(detail_sum, m)
        elif it.get("scope") == "season" and it.get("season_id") is not None:
            sid = it["season_id"]
            season_rows[sid] = accumulate(season_rows.get(sid), m)
            detail_sum = accumulate(detail_sum, m)
        elif it.get("scope") == "career":
            career_metrics = accumulate(career_metrics, m)
        else:
            detail_sum = accumulate(detail_sum, m)
    club = resolve_club_totals(career_metrics, detail_sum)
    return club, list(season_rows.items())


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


def summarize(club: dict, gr: dict, import_seasons, gr_season_ids) -> dict:
    """Read-only preview of what a commit would produce — powers the wizard's
    "GR + residual = final" review without writing anything.

    Returns the season deltas, the career residual, and the effective career
    total the view would show (``final`` = GR + emitted + residual). A
    ``gr_exceeds`` flag marks where GR already holds more than the club's book
    (residual clamps to 0, GR wins, final > club).
    """
    season_deltas, career = reconcile_player(club, gr, import_seasons, gr_season_ids)
    emitted = {k: sum((m.get(k, 0) or 0) for _s, m in season_deltas) for k in COUNT_METRICS}
    final = {k: (gr.get(k, 0) or 0) + emitted[k] + ((career or {}).get(k, 0) or 0) for k in COUNT_METRICS}
    gr_exceeds = any((gr.get(k, 0) or 0) > (club.get(k, 0) or 0) for k in _MEANINGFUL)
    return {
        "gr": {k: (gr.get(k, 0) or 0) for k in COUNT_METRICS},
        "emitted": emitted,
        "residual": career,
        "final": final,
        "season_delta_count": len(season_deltas),
        "gr_exceeds": gr_exceeds,
    }


async def fetch_gr_by_player(session, org_uuid, pids) -> dict:
    """Per-player GR coverage for an org: {pid: {"season_ids": set, "totals": dict}}.

    Scoped exactly like the effective view's ``api`` branch (player's org ==
    season's org, or a NULL-org player), so the preview and the commit agree
    with what the profile actually reads. Used for ungraded uploads (no
    ``grade_label``) — reconciled against the player's whole GR history across
    every grade, same as always.
    """
    from sqlalchemy import select, or_
    from app.models.db import Player, Season, PlayerSeasonStats

    if not pids:
        return {}
    rows = (
        await session.execute(
            select(PlayerSeasonStats)
            .join(Season, Season.id == PlayerSeasonStats.season_id)
            .join(Player, Player.id == PlayerSeasonStats.player_id)
            .where(Season.organisation_id == org_uuid)
            .where(or_(Player.organisation_id.is_(None), Player.organisation_id == Season.organisation_id))
            .where(PlayerSeasonStats.player_id.in_(list(pids)))
        )
    ).scalars().all()
    out: dict = {}
    for pss in rows:
        g = out.setdefault(pss.player_id, {"season_ids": set(), "totals": None})
        g["season_ids"].add(pss.season_id)
        g["totals"] = accumulate(g["totals"], pss_to_metrics(pss))
    return out


def _psgs_to_metrics(row) -> dict:
    """PlayerSeasonGradeStats ORM row -> canonical metric dict.

    The per-grade aggregate carries a narrower column set than the season
    (all-grades) aggregate — no fifties/hundreds/ducks/balls/fours/sixes/
    maidens/five-fors/wides/no-balls/catches_wk breakdown, since CA's
    per-grade endpoints don't return them. Those metrics are filled in
    separately from per-game scorecards (``_scorecard_narrow_metrics``) — see
    the caller, ``fetch_gr_by_player_for_grade``. Leaving them at 0 here (as
    an earlier version of this function did) double-counted: the leaderboard
    computes fifties/hundreds/etc directly from the same scorecards, so a
    residual calculated against a false "GR has zero of this" baseline added
    the club's full figure on top of what the scorecards already show.
    """
    m = _blank()
    m["matches"] = row.matches or 0
    m["batting_innings"] = row.batting_innings or 0
    m["runs"] = row.runs or 0
    m["not_outs"] = row.not_outs or 0
    m["high_score"] = row.high_score
    m["bowling_innings"] = row.bowling_innings or 0
    m["wickets"] = row.wickets or 0
    m["runs_conceded"] = row.runs_conceded or 0
    m["catches"] = row.catches or 0
    m["run_outs"] = row.run_outs or 0
    m["stumpings"] = row.stumpings or 0
    return m


async def _scorecard_narrow_metrics(session, org_uuid, pids, grade_label: str) -> dict:
    """Per-player {fifties, hundreds, ducks, fours, sixes, balls_faced, bowling_balls,
    maidens, five_wicket_innings, wides, no_balls, catches_wk}, computed straight
    from per-game scorecards for the grade — the exact same source and formula
    the grade-filtered leaderboard itself uses (aggregations.py's ``qualifying``
    CTEs), so reconciling against this can never double-count what's already on
    screen there. player_season_grade_stats has no columns for these metrics at
    all (see ``_psgs_to_metrics``), so there is no aggregate-API alternative.
    """
    from sqlalchemy import text
    from app.services.aggregations import _GRADE_MATCH

    if not pids or not grade_label:
        return {}
    params = {"org_id": str(org_uuid), "pids": [str(p) for p in pids], "grade_name": grade_label}

    bat_rows = (
        await session.execute(
            text(f"""
                SELECT bi.player_id,
                    COALESCE(SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END), 0) AS fifties,
                    COALESCE(SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END), 0) AS hundreds,
                    COALESCE(SUM(CASE WHEN bi.runs = 0 AND NOT bi.not_out THEN 1 ELSE 0 END), 0) AS ducks,
                    COALESCE(SUM(bi.fours), 0) AS fours,
                    COALESCE(SUM(bi.sixes), 0) AS sixes,
                    COALESCE(SUM(bi.balls), 0) AS balls_faced
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND bi.player_id = ANY(CAST(:pids AS uuid[]))
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                  AND {_GRADE_MATCH}
                GROUP BY bi.player_id
            """),
            params,
        )
    ).mappings().all()

    bowl_rows = (
        await session.execute(
            text(f"""
                SELECT bs.player_id,
                    COALESCE(SUM(FLOOR(bs.overs)::integer * 6
                                 + ROUND((bs.overs - FLOOR(bs.overs)) * 10)::integer), 0) AS bowling_balls,
                    COALESCE(SUM(bs.maidens), 0) AS maidens,
                    COALESCE(SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_wicket_innings,
                    COALESCE(SUM(bs.wides), 0) AS wides,
                    COALESCE(SUM(bs.no_balls), 0) AS no_balls
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND bs.player_id = ANY(CAST(:pids AS uuid[]))
                  AND {_GRADE_MATCH}
                GROUP BY bs.player_id
            """),
            params,
        )
    ).mappings().all()

    field_rows = (
        await session.execute(
            text(f"""
                SELECT fs.player_id, COALESCE(SUM(fs.catches_wk), 0) AS catches_wk
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND fs.player_id = ANY(CAST(:pids AS uuid[]))
                  AND {_GRADE_MATCH}
                GROUP BY fs.player_id
            """),
            params,
        )
    ).mappings().all()

    out: dict = {}
    for row in bat_rows:
        d = out.setdefault(row["player_id"], {})
        d.update({k: row[k] for k in ("fifties", "hundreds", "ducks", "fours", "sixes", "balls_faced")})
    for row in bowl_rows:
        d = out.setdefault(row["player_id"], {})
        d.update({k: row[k] for k in ("bowling_balls", "maidens", "five_wicket_innings", "wides", "no_balls")})
    for row in field_rows:
        out.setdefault(row["player_id"], {})["catches_wk"] = row["catches_wk"]
    return out


async def fetch_gr_by_player_for_grade(session, org_uuid, pids, grade_label: str) -> dict:
    """Per-player GR coverage scoped to ONE grade **name**, for a grade-scoped upload.

    A CA grade is a per-season row (a new "1st Grade" row is minted every
    season — see the grade-collision-fix era notes), so "GR's 1st Grade
    coverage" isn't one row to join to; it's every grade row across every
    season whose name matches, fuzzy/merge-alias-aware exactly like a
    grade-filtered leaderboard already matches (``aggregations._GRADE_MATCH``).
    Reads ``player_season_grade_stats`` — CA's own per-grade aggregate, synced
    alongside the season totals (``sync.py``'s "per-grade aggregate sync") —
    not per-game scorecards, so a grade with thin scorecard coverage still
    reconciles correctly against CA's real per-grade numbers for the metrics
    it carries. The metrics it doesn't carry (fifties/hundreds/etc — see
    ``_psgs_to_metrics``) are filled in from the scorecards directly
    (``_scorecard_narrow_metrics``) so they can't be double-counted against
    what the grade-filtered leaderboard already shows for those.
    """
    from sqlalchemy import text
    from app.services.aggregations import _GRADE_MATCH

    if not pids or not grade_label:
        return {}
    rows = (
        await session.execute(
            text(f"""
                SELECT psgs.player_id, psgs.season_id, psgs.matches, psgs.batting_innings,
                       psgs.runs, psgs.not_outs, psgs.high_score, psgs.bowling_innings,
                       psgs.wickets, psgs.runs_conceded, psgs.catches, psgs.run_outs, psgs.stumpings
                FROM player_season_grade_stats psgs
                JOIN grades gr ON gr.id = psgs.grade_id
                JOIN seasons s ON s.id = gr.season_id
                JOIN players p ON p.id = psgs.player_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND (p.organisation_id IS NULL OR p.organisation_id = s.organisation_id)
                  AND psgs.player_id = ANY(CAST(:pids AS uuid[]))
                  AND {_GRADE_MATCH}
            """),
            {"org_id": str(org_uuid), "pids": [str(p) for p in pids],
             "grade_name": grade_label},
        )
    ).mappings().all()
    out: dict = {}
    for row in rows:
        pid = row["player_id"]
        g = out.setdefault(pid, {"season_ids": set(), "totals": None})
        g["season_ids"].add(row["season_id"])
        g["totals"] = accumulate(g["totals"], _psgs_to_metrics(row))

    narrow = await _scorecard_narrow_metrics(session, org_uuid, pids, grade_label)
    for pid, narrow_metrics in narrow.items():
        g = out.setdefault(pid, {"season_ids": set(), "totals": None})
        if g["totals"] is None:
            g["totals"] = _blank()
        g["totals"].update(narrow_metrics)
    return out


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


def _grade_key(label) -> Optional[str]:
    """Normalise a row's grade_label to a comparison key, or None (ungraded)."""
    label = (label or "").strip()
    return label or None


async def reconcile_imported_totals(org_id_str: str) -> int:
    """Regenerate ``import_effective_deltas`` for an org from ``imported_stats``.

    Idempotent and self-healing: wipes the org's derived rows and recomputes them
    against current GR coverage. A no-op (returns 0) for orgs with no imports, so
    it's safe to call unconditionally at the end of every sync. Returns the number
    of delta rows written.

    Reconciles **per (player, grade)**, not just per player: a club's upload
    can carry a ``grade_label`` (e.g. every row says "1st Grade"), and that
    portion of the club's book must only be compared against the player's GR
    coverage for that same grade — never diluted by subtracting their GR
    history in other grades the sheet never claimed to cover (see migration
    152). Rows with no grade_label keep the original all-grades comparison
    unchanged, so ungraded imports (every existing club) are unaffected.
    """
    import uuid as _uuid

    from sqlalchemy import select, delete
    from app.models.db import ImportedStat, ImportEffectiveDelta, async_session_maker

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

        # Group by (player, grade_key) — a player may have rows for more than
        # one grade (a future club could upload both a 1sts and a 2nds sheet).
        by_group: dict = {}
        for r in truth_rows:
            key = (r.player_id, _grade_key(r.grade_label))
            by_group.setdefault(key, []).append(r)

        ungraded_pids = [pid for pid, grade in by_group.keys() if grade is None]
        grade_labels = sorted({grade for _pid, grade in by_group.keys() if grade is not None})

        # Ungraded GR fetch (existing all-grades comparison), only for players
        # who actually have an ungraded group.
        gr_by_player = await fetch_gr_by_player(session, org_uuid, ungraded_pids)

        # One grade-scoped GR fetch per distinct grade label, each covering
        # every player that has a row under that label.
        gr_by_grade: dict = {}
        for grade in grade_labels:
            grade_pids = [pid for pid, g in by_group.keys() if g == grade]
            gr_by_grade[grade] = await fetch_gr_by_player_for_grade(
                session, org_uuid, grade_pids, grade
            )

        written = 0
        for (pid, grade), rows in by_group.items():
            club, import_seasons = assemble_club_inputs([
                {"scope": r.scope, "season_id": r.season_id,
                 "is_prior_bucket": r.is_prior_bucket, "metrics": imported_to_metrics(r)}
                for r in rows
            ])
            gr_pool = gr_by_grade[grade] if grade is not None else gr_by_player
            gr = gr_pool.get(pid, {"season_ids": set(), "totals": None})
            gr_totals = gr["totals"] if gr["totals"] is not None else _blank()

            season_deltas, career = reconcile_player(
                club, gr_totals, import_seasons, gr["season_ids"]
            )

            for season_id, metrics in season_deltas:
                session.add(ImportEffectiveDelta(
                    organisation_id=org_uuid, player_id=pid,
                    scope="season", season_id=season_id, grade_id=None,
                    grade_label=grade,
                    **delta_kwargs(metrics),
                ))
                written += 1

            if career is not None:
                session.add(ImportEffectiveDelta(
                    organisation_id=org_uuid, player_id=pid,
                    scope="career", season_id=None, grade_id=None,
                    grade_label=grade,
                    **delta_kwargs(career),
                ))
                written += 1

        await session.commit()
        return written
