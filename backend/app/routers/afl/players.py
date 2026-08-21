"""Public players list, player profile, and comparison."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, get_db
from app.services.afl import aggregations
from app.services.afl.manual_stats import manual_branch

router = APIRouter(prefix="/afl-players", tags=["afl-players"])


async def _player_achievements(db: AsyncSession, org_id, player_id, name: str) -> list:
    """This player's honour-board rows, for the profile's Honours section.

    Matched on the player id, and — only for a row that has no id at all —
    on the name. Awards written by Import Awards always carry an id; a row
    typed straight into the Awards screen for someone whose name didn't
    resolve does not, and it would otherwise never reach the person it's
    about. Never a name match on a row that HAS an id: that would put one
    of two same-named players' honours on the other.
    """
    rows = await db.execute(text("""
        SELECT id, season, season_end, category, subcategory, achievement, detail
        FROM player_achievements
        WHERE org_id = :org
          AND (player_id = :pid
               OR (player_id IS NULL AND lower(player_name) = lower(:name)))
        ORDER BY season DESC NULLS LAST, category, achievement
    """), {"org": str(org_id), "pid": str(player_id), "name": name or ""})
    out = [dict(r) for r in rows.mappings().all()]
    if not out:
        return out

    # A club that renamed an award on the Award Types screen renamed it for
    # every recorded win of it, including ones already stored under the old
    # label. Resolved here rather than in the query so a club holding two
    # definitions with the same name can't fan one award row out into two.
    defs = await db.execute(text("""
        SELECT category, subcategory, achievement, display_name
        FROM org_award_definitions
        WHERE org_id = :org AND display_name IS NOT NULL AND display_name <> ''
    """), {"org": str(org_id)})
    renamed = {(d["category"], d["subcategory"] or "", d["achievement"]): d["display_name"]
               for d in defs.mappings().all()}
    if renamed:
        for a in out:
            label = renamed.get((a["category"], a["subcategory"] or "", a["achievement"]))
            if label:
                a["achievement"] = label
    return out


@router.get("/by-org/{org_id}")
async def list_players(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return {"players": await aggregations.career_totals(db, org_id)}


@router.get("/compare")
async def compare_players(org_id: uuid.UUID,
                          ids: str = Query(..., description="comma-separated player ids"),
                          db: AsyncSession = Depends(get_db)):
    try:
        player_ids = [uuid.UUID(x) for x in ids.split(",") if x.strip()][:4]
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad player id")
    if len(player_ids) < 2:
        raise HTTPException(status_code=422, detail="Pick at least two players")
    totals = await aggregations.career_totals(db, org_id, player_ids)
    out = []
    for t in totals:
        seasons = await aggregations.season_by_season(db, org_id, t["player_id"])
        # Under `season_rows`, NOT `seasons` — career_totals already returns
        # `seasons` as the career season COUNT, which is what every other
        # reader of this shape (the Players list, the dashboard boards) means
        # by it. Overwriting it with the row list made Compare render a list
        # of objects into a table cell, which crashes the page outright.
        out.append({**t, "season_rows": [s for s in seasons if s["grade_id"] is None]})
    return {"players": out}


async def _vote_boards(db: AsyncSession, org_id) -> dict:
    """Which B&F counts this CLUB records at all — not this player's own.

    Both sources that can carry a vote (an Import Stats upload and a manual
    adjustment), matching the leaderboard's own vote path — a club whose
    votes were all typed in as corrections still gets the tabs.

    The profile's vote tabs are offered on the club's answer, so a player
    with none shows a column of zeros rather than losing the tab. Gating on
    the player's own tally instead would mean one team-mate's page carries
    the button and the next one doesn't, with nothing on either saying why.
    """
    manual = manual_branch(["club_bf_votes", "comp_bf_votes"])
    row = await db.execute(text(f"""
        WITH src AS (
            SELECT club_bf_votes, comp_bf_votes
            FROM afl_imported_stats
            WHERE organisation_id = :org
            UNION ALL
            {manual}
        )
        SELECT COALESCE(SUM(club_bf_votes), 0) > 0 AS club,
               COALESCE(SUM(comp_bf_votes), 0) > 0 AS comp
        FROM src
    """), {"org": str(org_id)})
    r = row.mappings().first()
    return {"club": bool(r and r["club"]), "comp": bool(r and r["comp"])}


@router.get("/{player_id}")
async def get_player(player_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, player_id)
    if player is None or player.organisation_id is None:
        raise HTTPException(status_code=404, detail="Player not found")
    org_id = player.organisation_id
    totals = await aggregations.career_totals(db, org_id, [player_id])
    seasons = await aggregations.season_by_season(db, org_id, player_id)
    grades = await aggregations.grade_breakdown(db, org_id, player_id)
    games = await aggregations.player_game_log(db, org_id, player_id)
    best_haul = max((g for g in games if g["goals"] is not None),
                    key=lambda g: g["goals"], default=None)
    return {
        "id": str(player.id),
        "name": player.display_name,
        "photo_url": player.photo_url,
        "organisation_id": str(org_id),
        "career": totals[0] if totals else None,
        "seasons": seasons,
        "grade_breakdown": grades,
        "game_log": games,
        "achievements": await _player_achievements(db, org_id, player_id, player.display_name),
        "vote_boards": await _vote_boards(db, org_id),
        "best_haul": {
            "goals": best_haul["goals"],
            "game_id": str(best_haul["game_id"]),
            "round_name": best_haul["round_name"],
            "season_name": best_haul["season_name"],
        } if best_haul and (best_haul["goals"] or 0) > 0 else None,
    }
