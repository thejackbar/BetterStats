"""Carry a confirmed XI forward as the next round's draft.

When a selector confirms a side, the same team's next upcoming fixture that has
no XI yet gets that side as an UNCONFIRMED draft (``selection_drafts``), so the
next round opens already populated and the selector edits rather than rebuilds.

Rules this module keeps:

* A draft is working state. Nothing here touches ``fixture_lineups``, so the
  carried side never leaks into votes, BetterIQ, the matchday board or the
  public Lineups page until somebody confirms it.
* A selector's own work is never overwritten. A fixture that already has a
  confirmed XI, or a draft somebody has saved, is left alone. The draft this
  module writes is tagged ``seeded_from`` (the source fixture id). The board
  rebuilds the payload on its first save, which drops the tag, so a tagged
  draft is by definition untouched and may be refreshed when the source XI is
  confirmed again, or removed when the source is emptied.
* Nobody is taken out for having said UNAVAILABLE. The carried side is the
  selector's starting point, and an availability answer is shown on each card
  (and per weekend for a two-day game); removing a name behind their back hid a
  decision that is theirs. (An earlier version dropped them, at seed time and on
  read; ``left_out`` stays in the payload, always empty, for older boards.)
* Only the immediate next fixture is seeded, never a chain: round 3 is seeded
  when round 2 is confirmed, not from round 1.
* Never raises: a failure here must not take down the confirm that called it.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


log = logging.getLogger(__name__)

# The app has no per-club timezone, so a fixture a day or two behind today still
# counts as "next" rather than being dropped on a timezone edge.
_RECENT_DAYS = 2


async def next_fixture_id(
    db: AsyncSession, org_id, team_id, fixture_id, played_on: Optional[date], today: Optional[date] = None,
    grade_ids: Optional[list] = None,
):
    """``(id, played_on)`` of the team's next upcoming fixture after
    ``played_on``, or None. ``grade_ids`` narrows it to one side of a squad that
    covers several teams (the 1st XI's side is not seeded from the 2nd XI's)."""
    if not team_id or not played_on:
        return None
    floor = (today or date.today()) - timedelta(days=_RECENT_DAYS)
    row = (await db.execute(
        text(
            "SELECT id, played_on FROM fixtures "
            "WHERE organisation_id = :org AND team_id = :team AND id <> :fid "
            "AND (CAST(:gids AS uuid[]) IS NULL OR grade_id = ANY(CAST(:gids AS uuid[]))) "
            "AND status = 'UPCOMING' AND played_on > :on AND played_on >= :floor "
            "ORDER BY played_on, start_time NULLS LAST, id LIMIT 1"
        ),
        {"org": org_id, "team": team_id, "fid": fixture_id, "on": played_on, "floor": floor,
         "gids": [uuid.UUID(str(g)) for g in grade_ids] if grade_ids else None},
    )).first()
    return (row[0], row[1]) if row else None


async def seed_next_round_draft(
    db: AsyncSession,
    *,
    org_id,
    fixture_id,
    team_id,
    played_on: Optional[date],
    user_id,
    player_ids: list[str],
    captain_id: Optional[str] = None,
    wicket_keeper_id: Optional[str] = None,
    today: Optional[date] = None,
    grade_ids: Optional[list] = None,
) -> Optional[str]:
    """Seed (or refresh, or clear) the next round's draft from a confirmed XI.

    ``player_ids`` is the XI in batting order. Writes inside the caller's
    transaction and does not commit. Returns the seeded fixture id, or None
    when nothing was written."""
    try:
        async with db.begin_nested():
            found = await next_fixture_id(db, org_id, team_id, fixture_id, played_on, today, grade_ids)
            if found is None:
                return None
            nxt, nxt_on = found
            src = str(fixture_id)

            if not player_ids:
                # Nobody left to carry (the source XI was emptied, or all said
                # no): drop only a draft that is still the
                # untouched copy of it.
                await db.execute(
                    text("DELETE FROM selection_drafts WHERE fixture_id = :nf AND draft->>'seeded_from' = :src"),
                    {"nf": nxt, "src": src},
                )
                return None

            payload = json.dumps({
                "slots": list(player_ids),
                "captain_id": captain_id if captain_id in player_ids else None,
                "wicket_keeper_id": wicket_keeper_id if wicket_keeper_id in player_ids else None,
                "demotions": [],
                "left_out": [],
                "seeded_from": src,
            })
            params = {"nf": nxt, "org": org_id, "d": payload, "uid": user_id, "src": src}

            # Refresh a copy nobody has touched.
            refreshed = (await db.execute(
                text(
                    "UPDATE selection_drafts SET draft = CAST(:d AS jsonb), updated_by = :uid, "
                    "updated_at = now(), version = version + 1 "
                    "WHERE fixture_id = :nf AND organisation_id = :org AND draft->>'seeded_from' = :src "
                    "RETURNING 1"
                ),
                params,
            )).first()
            if refreshed:
                return str(nxt)

            # Otherwise only where nothing exists: no confirmed XI, no draft.
            created = (await db.execute(
                text(
                    "INSERT INTO selection_drafts (fixture_id, organisation_id, draft, updated_by, updated_at, version) "
                    "SELECT CAST(:nf AS uuid), CAST(:org AS uuid), CAST(:d AS jsonb), CAST(:uid AS uuid), now(), 1 "
                    "WHERE NOT EXISTS (SELECT 1 FROM fixture_lineups WHERE fixture_id = CAST(:nf AS uuid)) "
                    "ON CONFLICT (fixture_id) DO NOTHING RETURNING 1"
                ),
                params,
            )).first()
            return str(nxt) if created else None
    except Exception:  # noqa: BLE001 - a carry-forward must never fail a confirm
        log.exception("could not seed the next round's draft from fixture %s", fixture_id)
        return None
