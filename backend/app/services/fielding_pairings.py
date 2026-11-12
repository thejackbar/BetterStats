"""Who a fielder took each catch and stumping off.

A scorecard names the fielder and the bowler on every caught and stumped
dismissal. ``bowler_wickets`` (and its hand-entered twin ``manual_bowler_wickets``,
unioned by ``v_effective_bowler_wickets``) keeps one row per such wicket with
both ids, so a player's fielding can be listed wicket by wicket and summed by
the bowler it came off.

What this can and cannot say, so the screen can say it too:

* Only wickets with a bowler are here. A run out credits no bowler, so it is not
  a pairing and is never listed.
* Caught-and-bowled has no separate fielder (the bowler is the catcher), so it
  is not listed against anyone.
* ``fielder_id`` is NULL when the scorecard's fielder could not be matched to a
  player (a fill-in, a redacted junior), and nothing is held at all for a game
  with no scorecard. The season totals above the list come from CA's own
  aggregates, so the list can hold fewer than the headline. The caller compares
  the two and says so; this module only reports what it holds.
* ``caught_behind`` NULL (an older synced row, or a hand-entered card) reads as
  a plain catch, the same rule every other reader of the column follows.

Read the same lens as the fielding headline: the club's own games
(``_club_game_clause``), the page's grade and match-type scope, and the season.
Both people on a row are ours: a shared both-synced fixture carries the other
club's rows on the same game, so the bowler is scoped to the fielder's club.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_sides import sides_sql
from app.services.grade_scope import GradeScope

KIND_CATCH = "catch"
KIND_CAUGHT_BEHIND = "caught_behind"
KIND_STUMPING = "stumping"
KINDS = (KIND_CATCH, KIND_CAUGHT_BEHIND, KIND_STUMPING)

# One group for every bowler the viewer may not be shown, so a stumping off a
# hidden junior still counts for the keeper without naming anyone.
HIDDEN_BOWLER_KEY = "hidden"


def kind_of(dismissal_type: Optional[str], caught_behind: Optional[bool]) -> Optional[str]:
    """The fielding kind of one wicket, or None when it is not a pairing we list."""
    dt = (dismissal_type or "").strip().lower()
    if dt == "stumped":
        return KIND_STUMPING
    if dt == "caught":
        return KIND_CAUGHT_BEHIND if caught_behind is True else KIND_CATCH
    return None


def mask_hidden_bowlers(rows: list[dict], hidden_ids: Iterable[str]) -> list[dict]:
    """Rows with any hidden bowler unnamed. The row stays: the fielder did take it."""
    hidden = {str(h).lower() for h in (hidden_ids or ())}
    if not hidden:
        return rows
    out = []
    for r in rows:
        if r.get("bowler_id") and str(r["bowler_id"]).lower() in hidden:
            r = {**r, "bowler_id": None, "bowler_name": None, "bowler_hidden": True}
        out.append(r)
    return out


def count_kinds(rows: Iterable[dict]) -> dict:
    counts = {k: 0 for k in KINDS}
    for r in rows:
        if r.get("kind") in counts:
            counts[r["kind"]] += 1
    counts["total"] = sum(counts[k] for k in KINDS)
    return counts


def by_bowler(rows: Iterable[dict]) -> list[dict]:
    """One line per bowler: what the fielder took off them, first and last date.

    Most dismissals first, then the most recent, then the name, so the order is
    stable. A bowler who is hidden from this viewer is one shared line.
    """
    groups: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") not in KINDS:
            continue
        key = HIDDEN_BOWLER_KEY if r.get("bowler_hidden") else str(r.get("bowler_id") or "")
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "bowler_id": None if key == HIDDEN_BOWLER_KEY else r.get("bowler_id"),
                "bowler_name": None if key == HIDDEN_BOWLER_KEY else r.get("bowler_name"),
                "bowler_hidden": key == HIDDEN_BOWLER_KEY,
                **{k: 0 for k in KINDS},
                "total": 0,
                "first_played_at": None,
                "last_played_at": None,
            }
        g[r["kind"]] += 1
        g["total"] += 1
        d = r.get("played_at")
        if d:
            if g["first_played_at"] is None or d < g["first_played_at"]:
                g["first_played_at"] = d
            if g["last_played_at"] is None or d > g["last_played_at"]:
                g["last_played_at"] = d
    # Stable passes, least important key first: name, then most recent, then count.
    # An undated line sorts as "" so it falls last under reverse=True.
    out = list(groups.values())
    out.sort(key=lambda g: (g["bowler_name"] or "~").lower())
    out.sort(key=lambda g: g["last_played_at"] or "", reverse=True)
    out.sort(key=lambda g: g["total"], reverse=True)
    return out


async def fielder_dismissals(
    session: AsyncSession,
    player_id: str,
    *,
    scope: Optional[GradeScope] = None,
    season_id: Optional[str] = None,
    hidden_ids: Iterable[str] = (),
) -> dict:
    """Every caught and stumped wicket this player took, oldest first, plus the sums."""
    # Imported here, not at the top: aggregations imports a lot and the route
    # module already holds it, so this stays cheap to import from a script.
    from app.services.aggregations import _club_game_clause, _game_season_clause, _scoped

    params: dict = {"pid": player_id}
    club = await _club_game_clause(session, player_id, params)
    season = await _game_season_clause(session, season_id, params)
    scope_sql = ""
    if _scoped(scope):
        scope.bind(params)
        scope_sql = scope.clause("g.grade_id")

    sides = sides_sql("g", "SELECT o.name FROM organisations o WHERE o.id = CAST(:club_org AS UUID)")
    result = await session.execute(
        text(f"""
            SELECT
                bw.id AS wicket_id,
                g.id::text AS game_id,
                g.played_at::text AS played_at,
                {sides},
                COALESCE(gr.display_name_override, gr.name) AS grade_name,
                s.name AS season_name,
                bw.innings_number,
                bw.dismissal_type,
                bw.caught_behind,
                bw.batter_name,
                bw.batter_runs,
                bw.bowler_id::text AS bowler_id,
                COALESCE(bp.display_name_override, bp.name) AS bowler_name,
                bw.source
            FROM v_effective_bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id
            JOIN players bp ON bp.id = bw.bowler_id
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            WHERE bw.fielder_id = CAST(:pid AS UUID)
              AND LOWER(bw.dismissal_type) IN ('caught', 'stumped')
              -- The bowler is the fielder's own club's player: a shared fixture
              -- carries the other club's wickets on the same game row.
              AND (CAST(:club_org AS UUID) IS NULL OR bp.organisation_id = CAST(:club_org AS UUID))
              {club}{season}{scope_sql}
            ORDER BY g.played_at ASC NULLS LAST, g.id, bw.innings_number, bw.id
        """),
        params,
    )
    rows = []
    for r in result.mappings():
        d = dict(r)
        d["kind"] = kind_of(d.pop("dismissal_type", None), d.pop("caught_behind", None))
        if d["kind"] is None:
            continue
        d["bowler_hidden"] = False
        rows.append(d)

    rows = mask_hidden_bowlers(rows, hidden_ids)
    return {
        "player_id": player_id,
        "rows": rows,
        "counts": count_kinds(rows),
        "by_bowler": by_bowler(rows),
    }
