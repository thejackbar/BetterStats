"""Copy balls faced from the synced card onto the import match that replaced it.

An overwrite import hides a synced match behind the club's own card and keeps only what
the club's file carried. The scorebook (CSFW) has no balls faced, so every replaced
match lost them even where PlayHQ had recorded them (43% of Payneham's replaced batting
lines, nearly all since 2019). The synced rows are still there, so this reads them back.

A line is filled only when ALL of these hold, so a figure is never put on the wrong man:

* the match is one an import wrote (read off the import's own audit rows) and is paired
  to its synced twin, never a hand-typed game;
* the import line has no balls faced yet (NULL), and is not a did-not-bat;
* the synced twin has a line for the SAME player (one record per person, thanks to
  `link_import_players`) with the SAME runs and the SAME batting position;
* that synced line records balls faced above zero (PlayHQ stores 0 for "not recorded",
  and a batter who faced no ball is not a thing a scorer records as a figure);
* exactly one synced line fits (a player twice in one match with the same runs and
  position would be a coin toss).

Nothing is overwritten and nothing is deleted. Each run records the filled row ids in
the audit log, and `undo` puts them back to NULL.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

# The import-made, paired games. `manual_edit_logs` is the import's own record.
_IMPORTED_PAIRED = """
    WITH imported AS (
        SELECT DISTINCT (jsonb_array_elements_text(l.after_json->'created_game_ids'))::uuid AS id
          FROM manual_edit_logs l
         WHERE l.organisation_id = :org
           AND l.action = 'import'
           AND l.target_table = 'manual_games'
           AND l.undone_at IS NULL
    )
"""

# One row per fillable import line, with the balls to put on it. `n` counts how many
# synced lines fit, and only n = 1 is used.
_CANDIDATES = _IMPORTED_PAIRED + """
    SELECT mbi.id AS row_id, MIN(bi.balls) AS balls, COUNT(*) AS n,
           s.name AS season_name, mg.id AS game_id
      FROM manual_games mg
      JOIN imported i ON i.id = mg.id
      JOIN seasons s ON s.id = mg.season_id
      JOIN manual_batting_innings mbi ON mbi.manual_game_id = mg.id
      JOIN batting_innings bi
           ON bi.game_id = mg.superseded_by_game_id
          AND bi.player_id = mbi.player_id
          AND bi.runs = mbi.runs
          AND bi.batting_position IS NOT DISTINCT FROM mbi.batting_position
     WHERE mg.organisation_id = CAST(:org AS UUID)
       AND mg.superseded_by_game_id IS NOT NULL
       AND mg.cricketstatz_import_id IS NULL
       AND mbi.balls IS NULL
       AND NOT COALESCE(mbi.did_not_bat, FALSE)
       AND NOT COALESCE(bi.did_not_bat, FALSE)
       AND bi.balls IS NOT NULL AND bi.balls > 0
     GROUP BY mbi.id, s.name, mg.id
"""

_FILL = """
    UPDATE manual_batting_innings
       SET balls = v.balls
      FROM (SELECT unnest(CAST(:ids AS INT[])) AS id,
                   unnest(CAST(:balls AS INT[])) AS balls) v
     WHERE manual_batting_innings.id = v.id AND manual_batting_innings.balls IS NULL
"""

# Only a line still holding exactly the figure this run put there: one a person has
# since corrected is theirs.
_UNDO = """
    UPDATE manual_batting_innings
       SET balls = NULL
      FROM (SELECT unnest(CAST(:ids AS INT[])) AS id,
                   unnest(CAST(:balls AS INT[])) AS balls) v
     WHERE manual_batting_innings.id = v.id AND manual_batting_innings.balls = v.balls
"""


async def find_fills(db, org_id) -> dict:
    rows = (await db.execute(text(_CANDIDATES), {"org": str(org_id)})).mappings().all()
    fill = [r for r in rows if r["n"] == 1]
    ambiguous = [r for r in rows if r["n"] != 1]
    by_season: dict[str, dict] = {}
    for r in fill:
        s = by_season.setdefault(r["season_name"], {"lines": 0, "games": set()})
        s["lines"] += 1
        s["games"].add(r["game_id"])
    return {
        "lines": [(r["row_id"], r["balls"]) for r in fill],
        "ambiguous": len(ambiguous),
        "games": len({r["game_id"] for r in fill}),
        "by_season": {k: {"lines": v["lines"], "games": len(v["games"])}
                      for k, v in sorted(by_season.items())},
    }


async def enrich_org(db, org_id, *, apply: bool = False, limit: Optional[int] = None) -> dict:
    res = await find_fills(db, org_id)
    lines = res["lines"][:limit] if limit else res["lines"]
    res["filled"] = 0
    if apply and lines:
        import json

        ids, balls = [r[0] for r in lines], [r[1] for r in lines]
        await db.execute(text(_FILL), {"ids": ids, "balls": balls})
        # Written here, not through `log_activity`, which swallows a failure: a fill
        # with no audit entry could not be undone, so the two go together or not at all.
        audit_id = (await db.execute(text(
            "INSERT INTO audit_logs (org_id, action, target_type, target_id, details) "
            "VALUES (:org, 'enrich_import_balls', 'manual_batting_innings', :tid, "
            "CAST(:details AS JSONB)) RETURNING id"),
            {"org": str(org_id), "tid": str(ids[0]),
             "details": json.dumps({
                 "why": "Balls faced copied from the synced card an import replaced, where "
                        "the same player had the same runs and batting position.",
                 "count": len(ids), "row_ids": ids, "balls": balls})})).scalar()
        await db.commit()
        res["filled"], res["audit_id"] = len(ids), audit_id
    return res


async def undo_org(db, org_id, *, audit_id: int) -> int:
    """Put a run's filled lines back to NULL, from its audit entry."""
    row = (await db.execute(text(
        "SELECT details FROM audit_logs WHERE id = :i AND org_id = CAST(:o AS UUID) "
        "AND action = 'enrich_import_balls'"), {"i": audit_id, "o": str(org_id)})).first()
    if not row:
        return 0
    details = row[0] or {}
    ids, balls = details.get("row_ids", []), details.get("balls", [])
    if not ids or len(ids) != len(balls):
        return 0
    res = await db.execute(text(_UNDO), {"ids": ids, "balls": balls})
    await db.commit()
    return res.rowcount
