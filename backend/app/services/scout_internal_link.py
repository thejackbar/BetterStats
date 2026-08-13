"""BetterScout — tap real BetterCricket club data directly, instead of
re-deriving everything from Cricket Australia's public API.

``services/iq_scout.py`` exists to scout a club we hold NO data on — its
whole reason to exist is fetching season aggregates from CA's public feed,
which is the right (and only) tool for that job. But when the club a scout
is browsing is ALREADY an onboarded BetterCricket club, we hold a richer
copy ourselves: per-GAME batting/bowling/fielding rows, not just season
totals — exact rather than aggregate, free to read (no external call, no
CA-proxy politeness budget spent), and dateable to a real match rather than
only a season. That last part is what makes Milestones' "MATCH DATED"
badge the normal case for a BetterCricket club instead of a rare one.

This module is the one place that decision gets made and the one place the
internal build lives. ``scout_discovery.py`` calls in here first; a club
that doesn't resolve (not one of ours, inactive, archived) falls through to
the existing ``iq_scout`` public-API path unchanged.

Read-only, and deliberately NOT a foreign-key relationship: BetterScout's
own tables carry zero FKs to club data (see ``models/scout.py``'s
docstring) and stay that way. Every id this module hands back into a
``scout_*`` row (``internal_org_id`` / ``internal_player_id`` on
``ScoutedPlayer``) is a plain UUID string copied at build time, not an ORM
relationship — a club later deleting a player cannot break anything on the
BetterScout side, it just means the next refresh no longer resolves.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services.iq_opponent import _balls_to_overs

# Independent of iq_scout.CAREER_VERSION on purpose — this module's payload
# shape (internal_player_id, per-game grade attribution, exact match dates)
# is its own contract, not a coincidence of reusing iq_scout's fetch code.
# Bump whenever build_internal_career's or internal_match_log's shape changes.
INTERNAL_SCHEMA_VERSION = 1


async def resolve_internal_org(session: AsyncSession, org_guid: str) -> Organisation | None:
    """Is this Cricket Australia org GUID a real, active BetterCricket club?
    organisations.id IS the CA org GUID (see the Sync Architecture notes),
    so this is a straight primary-key lookup, never a search or a name
    match — a false positive here would misattribute a scout org's roster
    build to the wrong club's private data."""
    if not org_guid:
        return None
    try:
        org = await session.get(Organisation, org_guid)
    except Exception:
        # Not a well-formed UUID — can't be one of ours.
        return None
    if not org or not org.is_active or org.archived_at is not None:
        return None
    return org


async def resolve_internal_player(session: AsyncSession, org: Organisation, grassroots_participant_id: str) -> str | None:
    """The org-scoped players.id this CA participant GUID resolves to, or
    None. Same two-step scheme sync.py uses: grassroots_id first (the raw
    GUID, which is what a per-club derived id is minted FROM on a
    cross-club collision), falling back to a legacy row whose primary key
    IS the raw GUID (single-club orgs never got a derived id)."""
    if not grassroots_participant_id:
        return None
    row = (await session.execute(text("""
        SELECT id FROM players
        WHERE organisation_id = :org_id
          AND (grassroots_id = :guid OR id::text = :guid)
        LIMIT 1
    """), {"org_id": str(org.id), "guid": grassroots_participant_id})).first()
    return str(row[0]) if row else None


def _best_figures(fig: str | None) -> tuple[int, int] | None:
    if not fig or "-" not in fig:
        return None
    try:
        w, r = fig.split("-", 1)
        return int(w), int(r)
    except ValueError:
        return None


def _rollup(rows: list[dict]) -> dict:
    """Fold a player's per-season v_effective_player_season_stats rows into
    one summary (a year, or a career) — same field names and the same
    sum-then-recompute-rates philosophy as iq_scout._rollup, so a scout
    profile reads identically whether the club resolved internally or
    externally. High score has no reliable not-out flag across a summed set
    of season rows, so (unlike iq_scout's single-season parse) this never
    appends the "*" — a minor fidelity loss, not worth a second query."""
    m = inns = no = runs = balls = f50 = f100 = ducks = 0
    hs = None
    w = bballs = bruns = maid = fiw = 0
    best: tuple[int, int] | None = None
    ct = ctwk = st = ro = 0
    for r in rows:
        m += r.get("matches") or 0
        inns += r.get("batting_innings") or 0
        runs += r.get("runs") or 0
        no += r.get("not_outs") or 0
        balls += r.get("balls_faced") or 0
        f50 += r.get("fifties") or 0
        f100 += r.get("hundreds") or 0
        ducks += r.get("ducks") or 0
        h = r.get("high_score")
        if h is not None and (hs is None or h > hs):
            hs = h
        w += r.get("wickets") or 0
        bballs += r.get("bowling_balls") or 0
        bruns += r.get("runs_conceded") or 0
        maid += r.get("maidens") or 0
        fiw += r.get("five_wicket_innings") or 0
        bp = _best_figures(r.get("best_bowling_figures"))
        if bp and (best is None or bp[0] > best[0] or (bp[0] == best[0] and bp[1] < best[1])):
            best = bp
        ct += r.get("catches") or 0
        ctwk += r.get("catches_wk") or 0
        st += r.get("stumpings") or 0
        ro += r.get("run_outs") or 0
    outs = max(inns - no, 0)
    return {
        "matches": m,
        "innings": inns,
        "runs": runs,
        "not_outs": no,
        "balls_faced": balls,
        "average": round(runs / outs, 2) if outs else None,
        "strike_rate": round(100 * runs / balls, 2) if balls else None,
        "high_score": str(hs) if hs is not None else None,
        "fifties": f50,
        "hundreds": f100,
        "ducks": ducks,
        "wickets": w,
        "overs": _balls_to_overs(bballs),
        "bowling_balls": bballs,
        "runs_conceded": bruns,
        "maidens": maid,
        "five_fors": fiw,
        "bowling_average": round(bruns / w, 2) if w else None,
        "economy": round(bruns / (bballs / 6), 2) if bballs else None,
        "best": f"{best[0]}/{best[1]}" if best else None,
        "catches": ct,
        "catches_wk": ctwk,
        "stumpings": st,
        "run_outs": ro,
    }


def _has_activity(t: dict) -> bool:
    return bool(t["matches"] or t["innings"] or t["runs"] or t["wickets"] or t["catches"])


async def build_internal_career(org: Organisation, session: AsyncSession) -> dict:
    """Every player at this club, season-by-season — same payload shape as
    iq_scout._build_career (org/window/players[]/grades[]/schema_v/built_at)
    so scout_discovery's roster cache and every downstream reader (Discover,
    Profile, Overview) work unchanged whichever path built it. Two things an
    external build can't give: internal_player_id per player (a real
    players.id, not just the CA participant GUID) and a real per-season
    grade name derived from games actually played, not a guess."""
    built_at = datetime.now(timezone.utc).isoformat()
    org_id = str(org.id)

    season_rows = (await session.execute(text("""
        SELECT pss.player_id, pss.season_id, s.year AS season_year,
               pss.matches, pss.batting_innings, pss.runs, pss.not_outs, pss.balls_faced,
               pss.fifties, pss.hundreds, pss.ducks, pss.high_score,
               pss.wickets, pss.bowling_balls, pss.runs_conceded, pss.maidens,
               pss.five_wicket_innings, pss.best_bowling_figures,
               pss.catches, pss.catches_wk, pss.stumpings, pss.run_outs,
               COALESCE(pl.display_name_override, pl.name) AS player_name,
               pl.grassroots_id
        FROM v_effective_player_season_stats pss
        JOIN players pl ON pl.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE pl.organisation_id = :org_id AND s.organisation_id = :org_id
          AND pss.season_id IS NOT NULL
    """), {"org_id": org_id})).mappings().all()

    if not season_rows:
        return {
            "org": {"id": org_id, "name": org.name},
            "window": None, "players": [], "grades": [],
            "schema_v": INTERNAL_SCHEMA_VERSION, "built_at": built_at, "source": "internal",
        }

    # Primary grade per (player, season) — the grade they played the most
    # games in that season, from real per-game appearances. A player who
    # turned out for two grades in one season (a fill-in call-up) gets the
    # one they played more of; Discover/Profile show one grade per season
    # row, same as the external payload's per-season display.
    grade_rows = (await session.execute(text("""
        WITH counts AS (
            SELECT ga.player_id, s.id AS season_id, gr.name AS grade_name, COUNT(*) AS n,
                   ROW_NUMBER() OVER (PARTITION BY ga.player_id, s.id ORDER BY COUNT(*) DESC) AS rn
            FROM game_appearances ga
            JOIN players pl ON pl.id = ga.player_id
            JOIN games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE pl.organisation_id = :org_id AND s.organisation_id = :org_id
            GROUP BY ga.player_id, s.id, gr.name
        )
        SELECT player_id, season_id, grade_name FROM counts WHERE rn = 1
    """), {"org_id": org_id})).mappings().all()
    grade_of: dict[tuple[str, str], str] = {
        (str(r["player_id"]), str(r["season_id"])): r["grade_name"] for r in grade_rows
    }

    # Every grade the club has fielded, with the years it ran — the same
    # shape iq_scout._build_career's "grades" list has, for Discover's chip
    # row and "grades played" summary.
    club_grade_rows = (await session.execute(text("""
        SELECT gr.id AS grade_id, gr.name AS grade_name, s.year
        FROM grades gr JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org_id AND gr.name IS NOT NULL
    """), {"org_id": org_id})).mappings().all()
    grades_by_name: dict[str, dict] = {}
    for r in club_grade_rows:
        gname = (r["grade_name"] or "").strip()
        if not gname:
            continue
        g = grades_by_name.setdefault(gname.lower(), {
            "grade_id": str(r["grade_id"]), "grade_name": gname, "team_name": gname, "years": set(),
        })
        if r["year"] is not None:
            g["years"].add(r["year"])
    grades = sorted(
        ({**g, "years": sorted(g["years"], reverse=True)} for g in grades_by_name.values()),
        key=lambda d: d["grade_name"],
    )

    by_player: dict[str, dict] = {}
    for r in season_rows:
        pid = str(r["player_id"])
        e = by_player.setdefault(pid, {
            "name": r["player_name"] or "Unknown",
            "grassroots_id": r["grassroots_id"],
            "by_year": defaultdict(list),
        })
        yr = r["season_year"]
        if yr is None:
            continue
        e["by_year"][yr].append(dict(r) | {"grade": grade_of.get((pid, str(r["season_id"])))})

    years_seen = sorted({yr for e in by_player.values() for yr in e["by_year"]}, reverse=True)
    window = {"from_year": years_seen[-1], "to_year": years_seen[0]} if years_seen else None

    players = []
    for internal_pid, e in by_player.items():
        seasons = []
        for yr in sorted(e["by_year"], reverse=True):
            rows = e["by_year"][yr]
            grade = next((row["grade"] for row in rows if row.get("grade")), None)
            seasons.append({"year": yr, "grade": grade, **_rollup(rows)})
        all_rows = [row for rows in e["by_year"].values() for row in rows]
        totals = _rollup(all_rows)
        if not _has_activity(totals):
            continue
        # External-facing id stays the raw CA participant GUID (what
        # ScoutedPlayer.grassroots_participant_id keys on) so a player added
        # while this club resolved internally is still findable if the club
        # is ever archived and a later refresh falls back to the public path.
        external_pid = e["grassroots_id"] or internal_pid
        players.append({
            "player_id": external_pid,
            "internal_player_id": internal_pid,
            "name": e["name"],
            "season_refs": [{"id": internal_pid, "year": yr} for yr in sorted(e["by_year"], reverse=True)],
            "seasons": seasons,
            "totals": totals,
        })
    players.sort(key=lambda p: (p["totals"]["runs"] or 0, p["totals"]["wickets"] or 0), reverse=True)

    return {
        "org": {"id": org_id, "name": org.name},
        "window": window,
        "players": players,
        "grades": grades,
        "schema_v": INTERNAL_SCHEMA_VERSION,
        "built_at": built_at,
        "source": "internal",
    }


async def internal_match_log(session: AsyncSession, org: Organisation, internal_player_id: str) -> list[dict]:
    """Every game this player has a batting or bowling row for at this club,
    oldest first, with the real match date and grade — what Milestones needs
    to say exactly which match crossed a threshold ("MATCH DATED") instead
    of only which season ("SEASON ONLY"). Org-scoped through the player
    (games are shared between both sides of a fixture — see the shared-game
    rule — so this must never be scoped by game/grade alone)."""
    rows = (await session.execute(text("""
        SELECT g.id AS game_id, g.played_at, gr.name AS grade_name, s.id AS season_id, s.year,
               bi.runs AS bat_runs, bi.not_out,
               bo.wickets AS bowl_wickets,
               fs.catches AS fielding_catches
        FROM game_appearances ga
        JOIN players pl ON pl.id = ga.player_id AND pl.organisation_id = :org_id
        JOIN games g ON g.id = ga.game_id
        LEFT JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN seasons s ON s.id = gr.season_id AND s.organisation_id = :org_id
        LEFT JOIN batting_innings bi ON bi.game_id = g.id AND bi.player_id = ga.player_id
        LEFT JOIN bowling_spells bo ON bo.game_id = g.id AND bo.player_id = ga.player_id
        LEFT JOIN fielding_stats fs ON fs.game_id = g.id AND fs.player_id = ga.player_id
        WHERE ga.player_id = :pid
        ORDER BY g.played_at NULLS LAST, g.id
    """), {"org_id": str(org.id), "pid": internal_player_id})).mappings().all()
    return [dict(r) for r in rows]
