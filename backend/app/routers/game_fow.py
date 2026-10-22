"""A club types the fall of wickets for its own innings of a synced match.

Cricket Australia's scorecard is sometimes short (six wickets, four fall-of-wicket rows) and the
club's paper scorebook has the rest. See `services/fow_overrides.py` for where the rows live and
why. Gated by MANAGE_MANUAL_ENTRIES, the same capability as every other hand-typed correction.

    GET    /games/{id}/fall-of-wickets/editor        what the editor opens on
    PUT    /games/{id}/fall-of-wickets/{innings}     replace the club's wickets for one innings
    DELETE /games/{id}/fall-of-wickets/{innings}     put Cricket Australia's back

Only a synced match is editable here (an uploaded or imported card is edited from Manual entries),
and only the innings the club itself batted.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_MANUAL_ENTRIES, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import fow_overrides as fo
from app.services import grassroots_scores_client as gr
from app.services import participant_relink as relink
from app.services.club_grades import club_game_sql

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


class FowRowIn(BaseModel):
    wicket_number: int
    score_at_fall: Optional[int] = None
    participant_id: Optional[str] = None


class FowEditIn(BaseModel):
    rows: list[FowRowIn] = Field(default_factory=list, max_length=fo.MAX_WICKETS)


async def _load(db: AsyncSession, club: Organisation, game_id: str):
    """The game's scorecard and the club's id resolver, or an HTTP error saying why not."""
    row = (await db.execute(text(f"""
        SELECT g.id, g.source FROM v_effective_games g
         WHERE g.id::text = :g AND {club_game_sql('g', 'org')}"""),
        {"g": game_id, "org": str(club.id)})).first()
    if row is None:
        raise HTTPException(status_code=404, detail="That match is not one of this club's.")
    if row.source != "api":
        raise HTTPException(
            status_code=409,
            detail="This card was uploaded or imported by the club. Edit it from Manual entries.")
    card = await gr.get_match_scorecard(str(row.id), force=True)
    if not card:
        raise HTTPException(
            status_code=502,
            detail="Cricket Australia's scorecard for this match is not available right now. Try again shortly.")
    if relink._our_team(card, club.id) is None:
        raise HTTPException(status_code=409, detail="This club's team is not on that scorecard.")
    by_guid, merged, _unique = await relink._org_maps(db, club.id)

    def resolve(guid):
        return relink._known(guid, by_guid, merged) if guid else None

    return row.id, card, resolve


@router.get("/{game_id}/fall-of-wickets/editor")
async def fow_editor(
    game_id: str,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, card, resolve = await _load(db, club, game_id)
    return {"game_id": str(gid), "innings": await fo.editor(db, club.id, gid, card, resolve)}


def _find_innings(editor: list[dict], num: int) -> dict:
    inn = next((i for i in editor if i["innings_number"] == num), None)
    if inn is None:
        raise HTTPException(status_code=404, detail="The club did not bat in that innings, so there is nothing to edit.")
    return inn


@router.put("/{game_id}/fall-of-wickets/{innings_number}")
async def save_fow(
    game_id: str,
    innings_number: int,
    data: FowEditIn,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, card, resolve = await _load(db, club, game_id)
    before = _find_innings(await fo.editor(db, club.id, gid, card, resolve), innings_number)
    inn = fo.batting_innings(card, innings_number)
    if not data.rows:
        raise HTTPException(
            status_code=422,
            detail="No wickets entered. To go back to Cricket Australia's figures, use Reset instead.")
    rows, errors = fo.clean_rows(inn, [r.model_dump() for r in data.rows])
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))

    await fo.save(db, club.id, current_user.id, gid, innings_number, rows)
    await fo.apply(db, club.id, gid, card, resolve)
    after = _find_innings(await fo.editor(db, club.id, gid, card, resolve), innings_number)
    warnings = []
    if len(rows) > before["wickets"]:
        warnings.append(
            f"The batting card shows {before['wickets']} dismissal(s) and you entered {len(rows)} wickets, "
            "so no partnerships could be worked out for this innings. Check the batting card.")
    summary = fo.summarise(innings_number, rows, after["stands"], before["wickets"])
    await fo.audit(
        db, club.id, current_user, gid, "fow_edit", summary,
        {"innings": innings_number, "before": before["fow"], "after": after["fow"],
         "stands": [{"wicket": s["wicket_number"], "runs": s["runs"]} for s in after["stands"]]})
    await db.commit()
    return {"innings": after, "summary": summary, "warnings": warnings}


@router.delete("/{game_id}/fall-of-wickets/{innings_number}")
async def reset_fow(
    game_id: str,
    innings_number: int,
    current_user: User = Depends(require_cap(MANAGE_MANUAL_ENTRIES)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    gid, card, resolve = await _load(db, club, game_id)
    before = _find_innings(await fo.editor(db, club.id, gid, card, resolve), innings_number)
    if not before["edited"]:
        raise HTTPException(status_code=409, detail="This innings has no wickets the club typed, so there is nothing to reset.")
    await fo.remove(db, club.id, gid, innings_number)
    await fo.restore_synced(db, club.id, gid, card, resolve, innings_number)
    after = _find_innings(await fo.editor(db, club.id, gid, card, resolve), innings_number)
    summary = f"Fall of wickets for innings {innings_number} put back to Cricket Australia's figures."
    await fo.audit(db, club.id, current_user, gid, "fow_reset", summary,
                   {"innings": innings_number, "before": before["fow"], "after": after["fow"]})
    await db.commit()
    return {"innings": after, "summary": summary, "warnings": []}
