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
* ``fielder_id`` is NULL when the scorecard's dismissal text names nobody (CA
  sometimes sends ``st:  b: `` with both names blank), so no pairing row can be
  built. The scorecard's per-game fielding row still credits the player, so the
  shortfall between that row and the pairings held is added back as rows with
  no bowler (``bowler_unknown``). That is what makes the list agree with the
  headline for every scorecard we hold. Nothing is held at all for a game with
  no scorecard, and the season totals above the list come from CA's own
  aggregates, so the list can still hold fewer than the headline. The caller
  compares the two and says so.
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
# One group for every row with no bowler recorded, for the same reason.
UNKNOWN_BOWLER_KEY = "unknown"


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


def unpaired_rows(game_gaps: Iterable[dict], paired: Iterable[dict]) -> list[dict]:
    """Rows for the catches and stumpings a game's fielding row credits that no pairing holds.

    ``game_gaps`` is one dict per game with the fielder's own counts from the scorecard's fielding
    row (``stumpings``, ``catches`` including the keeper's, ``catches_wk``) and
    ``own_caught_bowled``, the player's own caught-and-bowled that game. ``paired`` is the rows
    already built from the pairing table. Never negative: a game with more pairings than the
    fielding row says adds nothing. A caught-and-bowled is the bowler's own catch, so it is taken
    off the plain-catch shortfall rather than shown as a catch with no bowler.
    """
    have: dict[tuple, int] = {}
    for r in paired:
        k = (r["game_id"], r["kind"])
        have[k] = have.get(k, 0) + 1
    out = []
    for g in game_gaps:
        gid = g["game_id"]
        wk = int(g.get("catches_wk") or 0)
        want = {
            KIND_STUMPING: int(g.get("stumpings") or 0),
            KIND_CAUGHT_BEHIND: wk,
            KIND_CATCH: max(int(g.get("catches") or 0) - wk - int(g.get("own_caught_bowled") or 0), 0),
        }
        for kind, n in want.items():
            for _ in range(max(n - have.get((gid, kind), 0), 0)):
                out.append({
                    "wicket_id": None, "game_id": gid, "played_at": g.get("played_at"),
                    "home_team": g.get("home_team"), "away_team": g.get("away_team"),
                    "home_away_known": g.get("home_away_known"),
                    "grade_name": g.get("grade_name"), "season_name": g.get("season_name"),
                    "innings_number": None, "batter_name": None, "batter_runs": None,
                    "bowler_id": None, "bowler_name": None, "bowler_hidden": False,
                    "bowler_unknown": True, "source": "fielding", "kind": kind,
                })
    return out


def by_bowler(rows: Iterable[dict]) -> list[dict]:
    """One line per bowler: what the fielder took off them, first and last date.

    Most dismissals first, then the most recent, then the name, so the order is
    stable. A bowler who is hidden from this viewer is one shared line.
    """
    groups: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") not in KINDS:
            continue
        if r.get("bowler_hidden"):
            key = HIDDEN_BOWLER_KEY
        elif r.get("bowler_unknown"):
            key = UNKNOWN_BOWLER_KEY
        else:
            key = str(r.get("bowler_id") or "")
        special = key in (HIDDEN_BOWLER_KEY, UNKNOWN_BOWLER_KEY)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "bowler_id": None if special else r.get("bowler_id"),
                "bowler_name": None if special else r.get("bowler_name"),
                "bowler_hidden": key == HIDDEN_BOWLER_KEY,
                "bowler_unknown": key == UNKNOWN_BOWLER_KEY,
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
    # People first: the hidden and not-recorded lines are not bowlers, so they close the table.
    out.sort(key=lambda g: g["bowler_hidden"] or g["bowler_unknown"])
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

    # The scorecard's own fielding row per game, against the pairings just read. The same game, season
    # and scope clauses, so it is the same lens. Aggregated per game first so the join is one row each.
    gaps = await session.execute(
        text(f"""
            SELECT
                g.id::text AS game_id,
                g.played_at::text AS played_at,
                {sides},
                COALESCE(gr.display_name_override, gr.name) AS grade_name,
                s.name AS season_name,
                fs.stumpings, fs.catches, fs.catches_wk,
                COALESCE((
                    SELECT COUNT(*) FROM v_effective_bowler_wickets cb
                    WHERE cb.game_id = g.id AND cb.bowler_id = CAST(:pid AS UUID)
                      AND LOWER(cb.dismissal_type) = 'caught and bowled'
                ), 0) AS own_caught_bowled
            FROM (
                SELECT f.game_id,
                       COALESCE(SUM(f.stumpings), 0) AS stumpings,
                       COALESCE(SUM(f.catches), 0) AS catches,
                       COALESCE(SUM(f.catches_wk), 0) AS catches_wk
                FROM v_effective_fielding_stats f
                WHERE f.player_id = CAST(:pid AS UUID)
                GROUP BY f.game_id
            ) fs
            JOIN v_effective_games g ON g.id = fs.game_id
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = g.season_id
            WHERE fs.stumpings + fs.catches > 0
              {club}{season}{scope_sql}
        """),
        params,
    )
    extra = unpaired_rows([dict(r) for r in gaps.mappings()], rows)
    if extra:
        # Same order as the query: dated oldest first, undated last, a game's own rows together.
        rows = sorted(rows + extra, key=lambda r: (r["played_at"] is None, r["played_at"] or "", r["game_id"],
                                                   r["innings_number"] if r["innings_number"] is not None else 99))

    rows = mask_hidden_bowlers(rows, hidden_ids)
    counts = count_kinds(rows)
    counts["unpaired"] = sum(1 for r in rows if r.get("bowler_unknown"))
    return {
        "player_id": player_id,
        "rows": rows,
        "counts": counts,
        "by_bowler": by_bowler(rows),
    }
