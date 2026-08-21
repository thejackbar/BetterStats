"""AFL read-side aggregation helpers shared by the public routers.

Everything is org-scoped through grades→seasons (the games table has no
organisation column of its own) and reads only synced data — no live PlayHQ
calls on any public request path.
"""
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from . import grade_labels, milestone_rules

# Reading order for the per-team results split when the club has NOT set its
# own: the senior program first, juniors last. Anything unclassified sorts
# after the lot. A club-set display_order always wins over this — see
# grade_sort_key.
_TEAM_ORDER = {"senior": 0, "womens": 1, "masters": 2, "integrated": 3, "colts": 4}


def grade_sort_key(row: dict):
    """The one reading order for a club's own grades, used by every surface
    that lists them (the public grade filters, the results-by-team split, a
    player's by-grade cards, the admin grade list).

    A club's own ``display_order`` comes first — Seniors 1, Reserves 2, Under
    19s 3 is an ordering only the club can know, and no amount of category
    guessing reproduces it. A grade with no order set sorts AFTER every
    ordered one (not interleaved at position 0, which is what a plain
    ``COALESCE(display_order, 0)`` would do and would put the club's careful
    ordering underneath the grades it never touched), falling back to the
    category order and then the name.

    Takes the row's already-resolved display label under whichever key the
    caller uses, so the same function serves rows shaped as ``team`` (results
    breakdown), ``grade`` (player breakdown) or ``name``/``display_name``
    (grade lists).
    """
    order = row.get("display_order")
    label = (row.get("display_name") or row.get("display_name_override")
             or row.get("team") or row.get("grade") or row.get("name") or "")
    return (
        order is None,            # ordered grades first
        order if order is not None else 0,
        _TEAM_ORDER.get(row.get("category"), 9),
        str(label).lower(),
    )


async def career_totals(db: AsyncSession, org_id: uuid.UUID,
                        player_ids: Optional[list[uuid.UUID]] = None) -> list[dict]:
    """Career totals per player, combining the synced whole-season rollup
    (grade_id IS NULL so per-grade rows don't double count) with imported
    (Import Stats upload) rows — sync wins per season, imported only fills a
    genuine gap, same rule the leaderboard/dashboard/records use. A LEFT JOIN
    to seasons (not INNER) so an imported row with no resolved season still
    counts toward the totals — it just can't move first_year/last_year."""
    where_player_s = "AND s.player_id = ANY(:pids)" if player_ids else ""
    where_player_i = "AND i.player_id = ANY(:pids)" if player_ids else ""
    params: dict = {"org": str(org_id)}
    if player_ids:
        params["pids"] = [str(p) for p in player_ids]
    res = await db.execute(text(f"""
        WITH combined AS (
            SELECT s.player_id, s.season_id, s.games, s.goals, s.behinds, s.bog_count, s.captain_games
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.grade_id IS NULL {where_player_s}
            UNION ALL
            SELECT i.player_id, i.season_id, i.games_played AS games, i.goals, i.behinds, i.bog_count, i.captain_games
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {where_player_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id,
               p.name,
               p.display_name_override,
               p.photo_url,
               COUNT(DISTINCT c.season_id)                AS seasons,
               COALESCE(SUM(c.games), 0)                  AS games,
               COALESCE(SUM(c.goals), 0)                  AS goals,
               COALESCE(SUM(c.behinds), 0)                AS behinds,
               COALESCE(SUM(c.bog_count), 0)               AS bogs,
               COALESCE(SUM(c.captain_games), 0)          AS captain_games,
               MIN(s.year)                                AS first_year,
               MAX(s.year)                                AS last_year
        FROM combined c
        JOIN players p ON p.id = c.player_id
        LEFT JOIN seasons s ON s.id = c.season_id
        GROUP BY c.player_id, p.name, p.display_name_override, p.photo_url
        ORDER BY games DESC, goals DESC
    """), params)
    return [dict(r._mapping) for r in res]


async def season_by_season(db: AsyncSession, org_id: uuid.UUID,
                           player_id: uuid.UUID) -> list[dict]:
    """Combines synced (afl_player_season_stats) with imported (Import Stats
    upload) rows, same sync-wins-per-season rule as career_totals. An
    imported row is inherently per-grade shaped (one row per uploaded sheet
    row) — there's no separate "whole season" aggregate row the way a synced
    season has (grade_id NULL alongside its own per-grade breakdown rows).
    So for any season covered ONLY by import, a whole-season total row is
    synthesised in Python by summing that season's per-grade rows, mirroring
    what the sync's own rollup would have produced. compare_players()
    filters this list down to grade_id IS NULL rows only, so without this
    synthesis an import-only season would silently vanish from Compare too.

    Club/competition B&F votes ride along on every row, read on their own
    terms — see the vote query below for why they can't go through the
    sync-wins union with the rest.
    """
    res = await db.execute(text("""
        SELECT pss.season_id, s.name AS season_name, s.year,
               pss.grade_id, gr.name AS grade_name,
               pss.games, pss.goals, pss.behinds, pss.bog_count AS bogs,
               pss.captain_games
        FROM afl_player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        LEFT JOIN grades gr ON gr.id = pss.grade_id
        WHERE pss.organisation_id = :org AND pss.player_id = :pid
        UNION ALL
        SELECT i.season_id, s.name AS season_name, s.year,
               i.grade_id, gr.name AS grade_name,
               i.games_played AS games, i.goals, i.behinds, i.bog_count AS bogs,
               i.captain_games
        FROM afl_imported_stats i
        LEFT JOIN seasons s ON s.id = i.season_id
        LEFT JOIN grades gr ON gr.id = i.grade_id
        WHERE i.organisation_id = :org AND i.player_id = :pid
          AND NOT EXISTS (
            SELECT 1 FROM afl_player_season_stats s2
            WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
              AND s2.grade_id IS NULL AND s2.games > 0
          )
    """), {"org": str(org_id), "pid": str(player_id)})
    rows = [dict(r._mapping) for r in res]
    for r in rows:
        r["club_bf_votes"] = 0
        r["comp_bf_votes"] = 0

    # Club/competition B&F votes are read SEPARATELY, and deliberately not
    # through the sync-wins union above. They only ever come from an Import
    # Stats upload — PlayHQ has no concept of club-internal B&F voting, so
    # afl_player_season_stats never carries them (see afl_main.py's note on
    # why the columns live on afl_imported_stats alone). Putting them in the
    # union would mean a season that was BOTH synced and imported loses its
    # votes to the NOT EXISTS gate: the imported row is dropped because sync
    # has better games/goals for that season, and the votes go with it. So
    # this is a straight sum of every imported row, exactly what the
    # leaderboard's own vote path and the admin Players list already do.
    vres = await db.execute(text("""
        SELECT i.season_id, s.name AS season_name, s.year,
               i.grade_id, gr.name AS grade_name,
               COALESCE(SUM(i.club_bf_votes), 0) AS club_bf_votes,
               COALESCE(SUM(i.comp_bf_votes), 0) AS comp_bf_votes
        FROM afl_imported_stats i
        LEFT JOIN seasons s ON s.id = i.season_id
        LEFT JOIN grades gr ON gr.id = i.grade_id
        WHERE i.organisation_id = :org AND i.player_id = :pid
        GROUP BY i.season_id, s.name, s.year, i.grade_id, gr.name
        HAVING COALESCE(SUM(i.club_bf_votes), 0) > 0
            OR COALESCE(SUM(i.comp_bf_votes), 0) > 0
    """), {"org": str(org_id), "pid": str(player_id)})
    vote_rows = [dict(r._mapping) for r in vres]

    # Fold the per-grade rows by merge group and stamp each with the club's
    # own label + reading order, so two spellings of one competition are one
    # row (and one column, on the profile's season table) rather than two.
    gmap = await grade_display_map(db, org_id)
    folded: dict[tuple, dict] = {}
    passthrough: list[dict] = []
    for r in rows:
        info = gmap.get(r["grade_name"]) if r["grade_name"] else None
        if r["grade_id"] is None or info is None:
            r["grade_key"] = None
            r["grade_order"] = None
            passthrough.append(r)
            continue
        key = (r["season_id"], info["key"])
        slot = folded.get(key)
        if slot is None:
            folded[key] = {**r,
                           "grade_name": info["label"],
                           "grade_key": info["key"],
                           "grade_order": info["display_order"]}
            continue
        for f in ("games", "goals", "behinds", "bogs", "captain_games"):
            slot[f] = (slot[f] or 0) + (r[f] or 0)
    rows = passthrough + list(folded.values())

    # Votes onto the per-grade cells, folded through the same merge map so a
    # vote recorded under one spelling of a competition lands in the column
    # the club actually reads. The cell key mirrors the profile table's own
    # (grade_key, falling back to the raw name for a grade the merge map
    # can't place), so a vote can never land in a column nothing looks at.
    by_cell: dict[tuple, dict] = {}
    votes_by_season: dict = {}
    for v in vote_rows:
        club_v = v["club_bf_votes"] or 0
        comp_v = v["comp_bf_votes"] or 0
        season_slot = votes_by_season.setdefault(
            v["season_id"], {"club_bf_votes": 0, "comp_bf_votes": 0})
        season_slot["club_bf_votes"] += club_v
        season_slot["comp_bf_votes"] += comp_v
        if v["grade_id"] is None:
            continue
        info = gmap.get(v["grade_name"]) if v["grade_name"] else None
        key = info["key"] if info else v["grade_name"]
        slot = by_cell.setdefault((v["season_id"], key), {
            "season_id": v["season_id"], "season_name": v["season_name"], "year": v["year"],
            "grade_id": v["grade_id"],
            "grade_name": info["label"] if info else v["grade_name"],
            "grade_key": info["key"] if info else None,
            "grade_order": info["display_order"] if info else None,
            # Nulls, not zeros: this row only exists where the union above
            # had no cell for that (season, grade) — a season carrying BOTH
            # synced figures and an imported sheet — and "didn't play there"
            # must not read as "played and scored nothing".
            "games": None, "goals": None, "behinds": None, "bogs": None,
            "captain_games": None,
            "club_bf_votes": 0, "comp_bf_votes": 0,
        })
        slot["club_bf_votes"] += club_v
        slot["comp_bf_votes"] += comp_v

    for r in rows:
        if r["grade_id"] is None:
            continue
        cell = by_cell.pop((r["season_id"], r["grade_key"] or r["grade_name"]), None)
        if cell:
            r["club_bf_votes"] = cell["club_bf_votes"]
            r["comp_bf_votes"] = cell["comp_bf_votes"]
    rows.extend(by_cell.values())

    have_total = {r["season_id"] for r in rows if r["grade_id"] is None and r["season_id"] is not None}
    synthesised: dict = {}
    for r in rows:
        sid = r["season_id"]
        if sid is None or sid in have_total:
            continue
        t = synthesised.setdefault(sid, {
            "season_id": sid, "season_name": r["season_name"], "year": r["year"],
            "grade_id": None, "grade_name": None,
            "grade_key": None, "grade_order": None,
            "games": 0, "goals": 0, "behinds": 0, "bogs": 0, "captain_games": 0,
            "club_bf_votes": 0, "comp_bf_votes": 0,
        })
        for f in ("games", "goals", "behinds", "bogs", "captain_games"):
            t[f] += r[f] or 0
    rows.extend(synthesised.values())

    # A season's own vote total, NOT the sum of its grade cells — a sheet
    # that recorded votes without naming a grade has no column to sit in,
    # and re-adding the cells would quietly lose it. Same rule the season
    # table's Total column already follows for games and goals, and it keeps
    # a player's season line agreeing with the leaderboard, which sums every
    # imported row for the club regardless of grade.
    # Stamped onto the FIRST whole-season row for a season only. A season can
    # legitimately end up with two of them (a synced rollup recording no games
    # at all doesn't displace the imported row beside it), and giving both the
    # season's full tally would double it in the profile's career line.
    stamped: set = set()
    for r in rows:
        if r["grade_id"] is not None or r["season_id"] in stamped:
            continue
        stamped.add(r["season_id"])
        totals = votes_by_season.get(r["season_id"])
        if totals:
            r["club_bf_votes"] = totals["club_bf_votes"]
            r["comp_bf_votes"] = totals["comp_bf_votes"]

    # Four stable sorts, least-significant first (Python's sort is stable, so
    # each later pass only breaks ties the previous pass left standing) —
    # mirrors the original "year DESC NULLS LAST, name DESC, grade_id NULLS
    # FIRST" ordering (whole-season row before its own per-grade breakdown),
    # with the club's own grade order deciding the per-grade rows within a
    # season. NULL order sorts after every ordered grade, same rule as
    # grade_sort_key.
    rows.sort(key=lambda r: (r["grade_order"] is None,
                             r["grade_order"] if r["grade_order"] is not None else 0,
                             (r["grade_name"] or "").lower()))
    rows.sort(key=lambda r: r["grade_id"] is not None)
    rows.sort(key=lambda r: r["season_name"] or "", reverse=True)
    rows.sort(key=lambda r: (r["year"] is None, -(r["year"] or 0)))
    return rows


async def grade_breakdown(db: AsyncSession, org_id: uuid.UUID,
                          player_id: uuid.UUID) -> list[dict]:
    """Career games/goals split by the grade turned out in — Seniors,
    Reserves, Colts, Under 18s and so on.

    Reads the per-grade rows only (grade_id IS NOT NULL), so it never double
    counts against the whole-season rollup rows sitting beside them, and
    combines synced with imported under the same sync-wins-per-season rule
    the rest of this module uses. Rows are folded together by merge group
    (grade_merge_logs), the same way the public grade filter in
    routers/afl/clubs.py folds them — otherwise a club that merged "Senior
    Men's" into "Seniors" gets two cards for one competition.

    A season with no grade resolved at all (an Import Stats upload that never
    named one) contributes to a player's career totals but to no grade here,
    so the sum of these rows can legitimately fall short of the career total.
    The caller shows that gap rather than this function inventing a bucket
    for it.
    """
    res = await db.execute(text("""
        WITH combined AS (
            SELECT s.grade_id, s.games, s.goals
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.player_id = :pid
              AND s.grade_id IS NOT NULL
            UNION ALL
            SELECT i.grade_id, i.games_played AS games, i.goals
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org AND i.player_id = :pid
              AND i.grade_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT gr.name AS name,
               MAX(gr.display_name_override) AS display_name_override,
               MAX(gr.category) AS category,
               MIN(gr.display_order) AS display_order,
               COALESCE(SUM(c.games), 0) AS games,
               COALESCE(SUM(c.goals), 0) AS goals
        FROM combined c
        JOIN grades gr ON gr.id = c.grade_id
        GROUP BY gr.name
    """), {"org": str(org_id), "pid": str(player_id)})
    rows = [dict(r._mapping) for r in res]
    if not rows:
        return []

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    buckets: dict[str, dict] = {}
    for row in rows:
        canonical = _resolve_canonical_grade(chain, row["name"])
        slot = buckets.setdefault(canonical, {
            "grade": canonical, "games": 0, "goals": 0, "_override": None,
            "_order": None, "_category": None,
        })
        # The canonical grade's own rename wins; an alias's only fills a gap.
        if row["display_name_override"] and (slot["_override"] is None or row["name"] == canonical):
            slot["_override"] = row["display_name_override"]
        if row["display_order"] is not None and (
                slot["_order"] is None or row["display_order"] < slot["_order"]):
            slot["_order"] = row["display_order"]
        if slot["_category"] is None:
            slot["_category"] = (grade_labels.normalise_category(row["category"])
                                 or grade_labels.suggest_category(row["name"]))
        slot["games"] += int(row["games"] or 0)
        slot["goals"] += int(row["goals"] or 0)

    out = [{
        "grade": b["_override"] or b["grade"],
        "grade_key": b["grade"],  # the canonical RAW name — a stable join key
        "category": b["_category"],
        "display_order": b["_order"],
        "games": b["games"],
        "goals": b["goals"],
    } for b in buckets.values()]
    # The club's own reading order, so a player's Seniors card sits where the
    # club puts Seniors rather than wherever he happened to play most games.
    out.sort(key=grade_sort_key)
    return out


async def player_game_log(db: AsyncSession, org_id: uuid.UUID,
                          player_id: uuid.UUID, limit: int = 200) -> list[dict]:
    res = await db.execute(text("""
        SELECT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               g.result, g.is_final, gr.name AS grade_name,
               s.name AS season_name, s.year,
               d.round_name, d.round_abbrev, d.status,
               d.home_score, d.away_score, d.our_side,
               l.goals, l.behinds, l.bog_ranking, l.is_captain, l.jumper_number
        FROM afl_player_game_lines l
        JOIN games g ON g.id = l.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE l.player_id = :pid AND s.organisation_id = :org
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim
    """), {"org": str(org_id), "pid": str(player_id), "lim": limit})
    return [dict(r._mapping) for r in res]


def _resolve_canonical_grade(chain: dict[str, str], name: str, _seen: Optional[set] = None) -> str:
    """Follow a grade_merge_logs alias chain to its root, guarding a cycle."""
    seen = _seen or set()
    if name in seen:
        return name
    seen.add(name)
    nxt = chain.get(name)
    if nxt is None:
        return name
    return _resolve_canonical_grade(chain, nxt, seen)


async def grade_display_map(db: AsyncSession, org_id: uuid.UUID) -> dict[str, dict]:
    """Every grade RAW name in the club mapped to how it should be shown:
    ``{"key": canonical raw name, "label": what to print, "display_order":
    the club's own order, "category": ...}``.

    One place that resolves the three things a grade name goes through — the
    merge group it belongs to, the club's rename of it, and the club's reading
    order — so a surface that lists grades folded by name (a player's season
    breakdown) agrees with one that lists them folded by merge group (the
    grade filter, the results split). Without it a merged grade shows as two
    columns on one screen and one card on the next.
    """
    rows = await db.execute(text("""
        SELECT gr.name,
               MAX(gr.display_name_override) AS display_name_override,
               MAX(gr.category) AS category,
               MIN(gr.display_order) AS display_order
        FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org
        GROUP BY gr.name
    """), {"org": str(org_id)})
    per_name = {r["name"]: dict(r) for r in rows.mappings().all()}

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    out: dict[str, dict] = {}
    for name, row in per_name.items():
        canonical = _resolve_canonical_grade(chain, name)
        head = per_name.get(canonical, row)
        # The canonical grade's own rename/order wins; an alias's only fills a
        # gap it left, same precedence grade_breakdown applies.
        order = head.get("display_order")
        if order is None:
            order = row.get("display_order")
        out[name] = {
            "key": canonical,
            "label": head.get("display_name_override") or canonical,
            "display_order": order,
            "category": (grade_labels.normalise_category(head.get("category"))
                         or grade_labels.suggest_category(canonical)),
        }
    return out


async def matching_grade_ids(db: AsyncSession, org_id: uuid.UUID, grade_id: uuid.UUID) -> list[uuid.UUID]:
    """Every grade_id (any season) that shares a merge group with ``grade_id`` —
    so filtering "this grade" transparently absorbs whatever's been merged
    into (or was merged from) it, the way Merge Grades promises. A grade
    exists once per season it's fielded in (grades.season_id), so "this
    grade across all time" is every row sharing its name/merge-group, not
    just the one row the caller happened to pick."""
    name_row = await db.execute(text("SELECT name FROM grades WHERE id = :gid"), {"gid": str(grade_id)})
    name = name_row.scalar()
    if not name:
        return [grade_id]

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    canonical = _resolve_canonical_grade(chain, name)
    group_names = {canonical} | {a for a in chain if _resolve_canonical_grade(chain, a) == canonical}

    rows = await db.execute(text("""
        SELECT gr.id FROM grades gr JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org AND gr.name = ANY(:names)
    """), {"org": str(org_id), "names": list(group_names)})
    ids = [r.id for r in rows]
    return ids or [grade_id]


async def club_results_summary(db: AsyncSession, org_id: uuid.UUID,
                               season_id: Optional[uuid.UUID] = None,
                               grade_ids: Optional[list] = None,
                               finals_only: bool = False) -> dict:
    """Headline W/L/D across the club (optionally one season).

    grade_ids/finals_only default to off, which is the whole-club number the
    dashboard wants. The results page passes its own filters so the cards
    describe the list underneath them — without that, filtering to one grade
    left the totals sitting on the club-wide figures and reading as if the
    filter had done nothing.

    Reads the games/afl_game_details tables only, unlike the goals/games/BOG
    combines elsewhere in this module — a win/loss/draw is a property of one
    specific MATCH, and a season-total Import Stats upload has no per-match
    data to draw a result from at all, so there's nothing to combine in from
    afl_imported_stats here.

    Import RESULTS uploads (routers/afl/result_imports.py) are a different
    story and need no special handling: they write real games rows carrying a
    real result letter, so they count here the same as a synced game. A bye
    is stored with status 'BYE' and a NULL result, which is what keeps it out
    of both the W/L/D tallies and the played count.

    ``no_result`` is the count of games that WERE played (status 'FINAL') but
    carry no result letter, which is why wins+losses+draws can legitimately
    fall short of ``played``. It is a real state, not a bug: plenty of junior
    competitions publish a completed fixture with no score at all, so PlayHQ
    hands us a finished game with nothing to derive a result from. Reported
    rather than hidden — a club looking at "Played 9, W4 L2" and finding the
    other three nowhere has no way to tell a missing score from a missing
    game."""
    clauses = ["s.organisation_id = :org"]
    params: dict = {"org": str(org_id)}
    if season_id:
        clauses.append("s.id = :season")
        params["season"] = str(season_id)
    if grade_ids:
        clauses.append("gr.id = ANY(:grades)")
        params["grades"] = list(grade_ids)
    if finals_only:
        clauses.append("g.is_final")
    res = await db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE g.result = 'W') AS wins,
               COUNT(*) FILTER (WHERE g.result = 'L') AS losses,
               COUNT(*) FILTER (WHERE g.result = 'D') AS draws,
               COUNT(*) FILTER (WHERE d.status = 'FINAL') AS played,
               COUNT(*) FILTER (WHERE d.status = 'FINAL' AND g.result IS NULL) AS no_result
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE {" AND ".join(clauses)}
    """), params)
    return dict(res.one()._mapping)


async def team_results_breakdown(db: AsyncSession, org_id: uuid.UUID,
                                 season_id: Optional[uuid.UUID] = None,
                                 grade_ids: Optional[list] = None,
                                 finals_only: bool = False) -> list[dict]:
    """The same W/L/D as club_results_summary, split by the team that played —
    League, Reserves, Under 19s and so on.

    Every clause matches club_results_summary exactly (including a bye's
    status='BYE' and NULL result keeping it out of both the tallies and the
    played count), so these rows always add up to the totals shown above
    them. Grades are folded by merge group the same way grade_breakdown and
    the public grade filter fold them, or a club that renamed a competition
    mid-history gets a row per spelling.
    """
    clauses = ["s.organisation_id = :org"]
    params: dict = {"org": str(org_id)}
    if season_id:
        clauses.append("s.id = :season")
        params["season"] = str(season_id)
    if grade_ids:
        clauses.append("gr.id = ANY(:grades)")
        params["grades"] = list(grade_ids)
    if finals_only:
        clauses.append("g.is_final")
    where = " AND ".join(clauses)

    res = await db.execute(text(f"""
        SELECT gr.name AS name,
               MAX(gr.display_name_override) AS display_name_override,
               MAX(gr.category) AS category,
               MIN(gr.display_order) AS display_order,
               COUNT(*) FILTER (WHERE g.result = 'W') AS wins,
               COUNT(*) FILTER (WHERE g.result = 'L') AS losses,
               COUNT(*) FILTER (WHERE g.result = 'D') AS draws,
               COUNT(*) FILTER (WHERE d.status = 'FINAL') AS played,
               COUNT(*) FILTER (WHERE d.status = 'FINAL' AND g.result IS NULL) AS no_result
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE {where}
        GROUP BY gr.name
    """), params)
    rows = [dict(r._mapping) for r in res]
    if not rows:
        return []

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    buckets: dict[str, dict] = {}
    for row in rows:
        canonical = _resolve_canonical_grade(chain, row["name"])
        slot = buckets.setdefault(canonical, {
            "team": canonical, "wins": 0, "losses": 0, "draws": 0, "played": 0,
            "no_result": 0, "_override": None, "_category": None, "_order": None,
        })
        if row["display_name_override"] and (slot["_override"] is None or row["name"] == canonical):
            slot["_override"] = row["display_name_override"]
        if slot["_category"] is None:
            slot["_category"] = (grade_labels.normalise_category(row["category"])
                                 or grade_labels.suggest_category(row["name"]))
        # The lowest order in the merge group wins, so a grade ordered under
        # one of its spellings doesn't fall to the bottom because the alias
        # rows were never ordered.
        if row["display_order"] is not None and (
                slot["_order"] is None or row["display_order"] < slot["_order"]):
            slot["_order"] = row["display_order"]
        for f in ("wins", "losses", "draws", "played", "no_result"):
            slot[f] += int(row[f] or 0)

    out = [{
        "team": b["_override"] or b["team"],
        "category": b["_category"],
        "display_order": b["_order"],
        "wins": b["wins"], "losses": b["losses"], "draws": b["draws"],
        "played": b["played"], "no_result": b["no_result"],
    } for b in buckets.values()]
    # A team with no completed game yet has nothing to report on.
    out = [r for r in out if r["played"] or r["wins"] or r["losses"] or r["draws"]]
    # The club's own reading order where it has set one, else seniors first
    # and juniors last — busiest-team-first would open on the Under 18s
    # whenever they happened to play a game more than the League side.
    out.sort(key=grade_sort_key)
    return out


async def upcoming_milestones(db: AsyncSession, org_id: uuid.UUID, limit: int = 50) -> list[dict]:
    """Live-computed "in reach" milestones — no stored milestones table, same
    approach as Core's get_upcoming_milestones_for_org. Scoped to players
    active in the club's 3 most recent seasons (synced or imported) so a
    decades-retired player's long-crossed totals don't clutter the list —
    career-wide totals, not season-scoped, since a milestone is a lifetime
    tally regardless of which season the dashboard filter has picked."""
    res = await db.execute(text("""
        WITH combined AS (
            SELECT s.player_id, s.season_id, s.games, s.goals
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.grade_id IS NULL
            UNION ALL
            SELECT i.player_id, i.season_id, i.games_played AS games, i.goals
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        ),
        recent_seasons AS (
            SELECT s.id
            FROM seasons s
            JOIN combined c ON c.season_id = s.id
            WHERE s.organisation_id = :org
            GROUP BY s.id, s.year, s.name
            ORDER BY s.year DESC NULLS LAST, s.name DESC
            LIMIT 3
        ),
        active_players AS (
            SELECT DISTINCT c.player_id
            FROM combined c
            WHERE c.season_id IN (SELECT id FROM recent_seasons)
        )
        SELECT p.id AS player_id,
               COALESCE(p.display_name_override, p.name) AS name,
               COALESCE(SUM(c.games), 0) AS career_games,
               COALESCE(SUM(c.goals), 0) AS career_goals
        FROM players p
        JOIN combined c ON c.player_id = p.id
        WHERE p.organisation_id = :org AND p.id IN (SELECT player_id FROM active_players)
        GROUP BY p.id, p.name, p.display_name_override
        HAVING COALESCE(SUM(c.games), 0) > 0 OR COALESCE(SUM(c.goals), 0) > 0
    """), {"org": str(org_id)})
    rows = [dict(r._mapping) for r in res]

    def importance_score(target, needed):
        return (target ** 2) / (needed + 1)

    upcoming = []
    for row in rows:
        totals = {"games": int(row["career_games"] or 0), "goals": int(row["career_goals"] or 0)}
        for stat, current in totals.items():
            target = milestone_rules.next_threshold(stat, current)
            if target is None:
                continue
            needed = target - current
            if needed > milestone_rules.reach_window(stat, target):
                continue
            upcoming.append({
                "player_id": str(row["player_id"]),
                "name": row["name"],
                "type": stat,
                "current": current,
                "target": target,
                "needed": needed,
                "score": importance_score(target, needed),
            })

    upcoming.sort(key=lambda x: x["score"], reverse=True)
    return upcoming[:limit]
