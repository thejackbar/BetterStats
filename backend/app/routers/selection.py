"""BetterSelect Phase 3 — team selection (lineups).

Pick a side for a fixture from the available pool. The pool is the club's
players annotated with their availability for THAT fixture's playing date
(availability is keyed on date, so one answer covers every fixture that day),
plus squad membership and the dormancy/recency signal the availability matrix
already computes.

Lineups are per-fixture: the same player can be selected for two fixtures on
the same weekend (the shared-player split case). Whether that's allowed/warned
is a rule layer that reads these rows — the storage itself doesn't constrain it.

All endpoints scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, FixtureLineup, Grade, Organisation, Player, Team, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import resolve_period_statuses
from app.services import selection_clash, selection_notify, selection_rules, selection_seed
from app.services.selection_pool import assemble_selection, rule_context, side_size
from app.services.side_size import effective_min, valid_min_size, valid_side_size

router = APIRouter(prefix="/selection", tags=["selection"])

# Selection-pool assembly — scoring, recency wall, women's/men's gender
# wall, squad tier and per-date availability — lives in
# app/services/selection_pool.py so BetterIQ reuses the identical model.


class LineupSlot(BaseModel):
    player_id: str
    batting_order: Optional[int] = None
    is_captain: bool = False
    is_wicket_keeper: bool = False


class Demotion(BaseModel):
    """A bumped player cascading down into a called-up player's vacated slot in
    a lower-grade, same-date fixture."""
    player_id: str
    fixture_id: str
    batting_order: Optional[int] = None


class LineupSet(BaseModel):
    players: list[LineupSlot]
    demotions: list[Demotion] = []


class TeamSizeSet(BaseModel):
    size: int
    # The fixture the selector is looking at. When it belongs to one of our
    # teams the number is saved on THAT team; without it (or for a fixture with
    # no team) it is the club default, as before.
    fixture_id: Optional[str] = None
    # The fewest players the team may field (size stays the maximum). Sent only
    # to change it: absent leaves it alone, an explicit null clears it. A
    # minimum belongs to a team, so it is refused without one.
    min_size: Optional[int] = None


class DraftDemotion(Demotion):
    """A pending cascade as the board holds it; ``callup_id`` is the call-up
    that bumped the player, so the cascade can be re-judged at confirm."""
    callup_id: Optional[str] = None


class DraftSet(BaseModel):
    """The board's unconfirmed working state. ``slots`` keeps the gaps (a null
    is an empty slot) so a half-filled side comes back where it was left."""
    slots: list[Optional[str]] = []
    captain_id: Optional[str] = None
    wicket_keeper_id: Optional[str] = None
    demotions: list[DraftDemotion] = []
    # The draft version this board last saw (0 = it saw none). A draft that has
    # moved on since is refused with 409 and the current draft, never overwritten.
    base_version: int = 0


async def _get_owned_fixture(db: AsyncSession, fixture_id: str, club_id) -> Fixture:
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return f


@router.get("/overview")
async def selection_overview(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All upcoming fixtures with their finalised lineups, for the matchday
    board. One row per fixture, players in batting order, each carrying their
    skill roles + per-date availability so the board can derive a health
    summary (balance / keeper / captain / flags / status) without a second
    round-trip. Declared before /{fixture_id} so 'overview' isn't read as an id.
    """
    fx_res = await db.execute(
        select(Fixture)
        .where(
            Fixture.organisation_id == club.id,
            Fixture.played_on >= date.today(),
            Fixture.status != "CANCELLED",
        )
        .order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    )
    fixtures = fx_res.scalars().all()
    if not fixtures:
        return {"fixtures": [], "default_team_size": side_size(club)}

    # Team names + seniority, to show which of our teams each fixture belongs to
    # and order a matchday's teams (1st XI → 2nd → …) in the team switcher.
    tm_res = await db.execute(select(Team).where(Team.organisation_id == club.id))
    teams = tm_res.scalars().all()
    team_names = {str(t.id): (t.short_name or t.name) for t in teams}
    team_seqs = {str(t.id): t.sequence for t in teams}
    team_sizes = {str(t.id): side_size(club, t) for t in teams}
    team_mins = {str(t.id): effective_min(t.min_team_size, team_sizes[str(t.id)]) for t in teams}

    # Teams that play at the same time on the same day (most clubs start every
    # side at once) would otherwise come back in whatever order Postgres likes.
    # Break the tie the way every squad list does: ranked teams first by
    # hierarchy (1st XI, 2nd XI, ...), then unranked ones by name, numbers read
    # as numbers (OD3s before OD10s). Date and start time still lead.
    def _team_order(f: Fixture):
        seq = team_seqs.get(str(f.team_id)) if f.team_id else None
        name = (team_names.get(str(f.team_id)) if f.team_id else None) or f.label or f.opponent_name or ""
        return (
            f.played_on is None, f.played_on or date.min,
            f.start_time is None, f.start_time or "",
            not (seq or 0) > 0, seq or 0,
            [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name.lower())],
            str(f.id),
        )

    fixtures = sorted(fixtures, key=_team_order)

    # Grade label per fixture (drives the small grade badge).
    grade_ids = {f.grade_id for f in fixtures if f.grade_id}
    grade_names: dict[str, str] = {}
    if grade_ids:
        gr_res = await db.execute(
            select(Grade.id, Grade.display_name_override, Grade.name).where(Grade.id.in_(grade_ids))
        )
        for gid, dno, nm in gr_res.fetchall():
            grade_names[str(gid)] = dno or nm

    # Lineups for these fixtures, with player display name + roles + flags, in order.
    rows_res = await db.execute(
        select(
            FixtureLineup.fixture_id,
            FixtureLineup.batting_order,
            FixtureLineup.is_captain,
            FixtureLineup.is_wicket_keeper,
            func.coalesce(Player.display_name_override, Player.name),
            Player.id,
            Player.skill_positions,
        )
        .join(Player, FixtureLineup.player_id == Player.id)
        .where(FixtureLineup.organisation_id == club.id)
        .order_by(FixtureLineup.batting_order.asc().nullslast())
    )
    by_fixture: dict[str, list] = {}
    for fid, order, cap, wk, name, pid, skills in rows_res.fetchall():
        by_fixture.setdefault(str(fid), []).append({
            "player_id": str(pid), "display_name": name,
            "batting_order": order, "is_captain": cap, "is_wicket_keeper": wk,
            "skill_positions": skills or [],
        })

    # Availability for every fixture's playing date (explicit answer wins, then
    # the period fallback) — same resolution the builder uses, so the board's
    # health flags match what you'd see inside.
    dates = sorted({f.played_on for f in fixtures if f.played_on})
    explicit: dict[tuple[str, str], str] = {}
    period_map: dict[str, dict] = {}
    if dates:
        av_res = await db.execute(
            text(
                "SELECT player_id, avail_date, status FROM player_availability "
                "WHERE organisation_id = :org AND avail_date BETWEEN :lo AND :hi"
            ),
            {"org": club.id, "lo": dates[0], "hi": dates[-1]},
        )
        for pid, d, status in av_res.fetchall():
            explicit[(d.isoformat(), str(pid))] = status
        period_map = await resolve_period_statuses(db, club.id, dates)

    def avail_for(date_iso: str | None, pid: str) -> str:
        if not date_iso:
            return "NO_RESPONSE"
        if (date_iso, pid) in explicit:
            return explicit[(date_iso, pid)]
        info = period_map.get(date_iso, {}).get(pid)
        return info["status"] if info else "NO_RESPONSE"

    # Fixtures with an unconfirmed draft behind them. A flag only: the draft
    # itself goes to people who can edit the XI, through /{id}/draft.
    draft_rows = await db.execute(
        text(
            "SELECT fixture_id, updated_at FROM selection_drafts "
            "WHERE organisation_id = :org AND fixture_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"org": club.id, "ids": [str(f.id) for f in fixtures]},
    )
    drafts = {str(fid): at for fid, at in draft_rows.fetchall()}

    out = []
    for f in fixtures:
        date_iso = f.played_on.isoformat() if f.played_on else None
        lineup = by_fixture.get(str(f.id), [])
        for p in lineup:
            p["availability"] = avail_for(date_iso, p["player_id"])
        out.append({
            "id": str(f.id),
            "label": f.label,
            "opponent_name": f.opponent_name,
            "home_away": f.home_away,
            "played_on": date_iso,
            "start_time": f.start_time,
            "round": f.round,
            "venue": f.venue,
            "team_name": team_names.get(str(f.team_id)) if f.team_id else None,
            "team_sequence": team_seqs.get(str(f.team_id)) if f.team_id else None,
            "team_size": team_sizes.get(str(f.team_id), side_size(club)) if f.team_id else side_size(club),
            "team_min": team_mins.get(str(f.team_id)) if f.team_id else None,
            "grade_name": grade_names.get(str(f.grade_id)) if f.grade_id else None,
            "lineup": lineup,
            "has_draft": str(f.id) in drafts,
            "draft_updated_at": drafts[str(f.id)].isoformat() if str(f.id) in drafts and drafts[str(f.id)] else None,
        })

    return {"fixtures": out, "default_team_size": side_size(club)}


@router.get("/selected-players")
async def selected_players(
    on: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Player ids named in ANY saved XI for a round.

    A "round" is a Mon–Sun week. Anchor it with ?on=YYYY-MM-DD (expanded to that
    date's week) or an explicit ?from=&to= window. Powers the cross-screen
    "Selected" filter: a player counts as selected if they're picked in some XI
    that round (one XI per date is enforced on save, so it's unambiguous).
    Declared before /{fixture_id} so the literal path isn't read as an id.
    """
    if from_ and to:
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
    elif on:
        anchor = date.fromisoformat(on)
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    else:
        raise HTTPException(status_code=400, detail="Provide ?on= or ?from=&to=")
    if end < start:
        start, end = end, start

    res = await db.execute(
        text(
            "SELECT DISTINCT fl.player_id FROM fixture_lineups fl "
            "JOIN fixtures f ON fl.fixture_id = f.id "
            "WHERE fl.organisation_id = :org "
            "AND ((f.played_on BETWEEN :start AND :end) "
            "OR (f.end_on BETWEEN :start AND :end))"
        ),
        {"org": club.id, "start": start, "end": end},
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "player_ids": [str(r[0]) for r in res.fetchall()],
    }


@router.get("/{fixture_id}")
async def get_selection(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A fixture's lineup + the pickable pool with per-date availability.

    Pool players carry availability for the fixture date, squads, recency
    (last_played / is_dormant), squad tier, gender wall and a form score.
    Delegates to the shared assembler so BetterIQ analyses the same pool.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    return await assemble_selection(db, club, fx)


@router.get("/{fixture_id}/previous-xi")
async def previous_xi(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The most recent prior fixture's named XI, for "fill from last week".

    Looks back for the SAME team's last fixture (before this one's date) that has
    a saved lineup. A fixture with no team of its own falls back to the same
    grade. It never borrows another team's XI: a women's side with no history of
    its own used to be filled with the men's last XI, because the lookup fell
    back to "any of the club's prior fixtures". Returns player ids in batting
    order plus the captain/keeper, so the selection board can seed empty slots,
    and the source fixture's team so the board can name where the side came from.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    empty = {"source_fixture_id": None, "player_ids": [], "captain_id": None, "wicket_keeper_id": None}

    if fx.team_id:
        scope = Fixture.team_id == fx.team_id
    elif fx.grade_id:
        scope = Fixture.grade_id == fx.grade_id
    else:
        return empty  # nothing says which side this is, so there is no "last week"

    q = select(Fixture).where(Fixture.organisation_id == club.id, Fixture.id != fx.id, scope)
    if fx.played_on:
        q = q.where(Fixture.played_on < fx.played_on)
    q = q.order_by(Fixture.played_on.desc().nullslast(), Fixture.start_time.desc().nullslast())
    prior = (await db.execute(q)).scalars().all()

    for f in prior:
        rows = (await db.execute(
            select(FixtureLineup).where(FixtureLineup.fixture_id == f.id)
        )).scalars().all()
        if not rows:
            continue
        rows.sort(key=lambda r: (r.batting_order or 999))
        return {
            "source_fixture_id": str(f.id),
            "source_label": f.opponent_name or f.label,
            "source_round": f.round,
            "source_date": f.played_on.isoformat() if f.played_on else None,
            "player_ids": [str(r.player_id) for r in rows],
            "captain_id": next((str(r.player_id) for r in rows if r.is_captain), None),
            "wicket_keeper_id": next((str(r.player_id) for r in rows if r.is_wicket_keeper), None),
        }

    return empty


@router.post("/default-team-size")
async def set_default_team_size(
    body: TeamSizeSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Persist a lineup size (0 = no limit) so the Selection format selector
    sticks across reloads. With a `fixture_id` of one of our teams the number is
    that team's own; otherwise it is the club default every team without its own
    number follows."""
    if not valid_side_size(body.size):
        raise HTTPException(status_code=400, detail="Invalid team size")
    team = None
    if body.fixture_id:
        fx = await _get_owned_fixture(db, body.fixture_id, club.id)
        if fx.team_id:
            team = await db.get(Team, fx.team_id)
            if team is not None and team.organisation_id != club.id:
                team = None
    if team is not None:
        team.default_team_size = body.size
        if "min_size" in body.model_fields_set:
            if body.min_size is not None and not valid_min_size(body.min_size, body.size):
                raise HTTPException(status_code=400, detail="The minimum must be a whole number below the side size")
            team.min_team_size = body.min_size
        elif effective_min(team.min_team_size, body.size) is None:
            # The size moved to or below the stored minimum: drop it rather than
            # keep a number that no longer means anything.
            team.min_team_size = None
        scope = "team"
    else:
        if body.min_size is not None:
            raise HTTPException(status_code=400, detail="A minimum needs a team")
        club.default_team_size = body.size
        scope = "club"
    await db.commit()
    return {
        "status": "ok", "default_team_size": body.size, "scope": scope,
        "min_size": team.min_team_size if team is not None else None,
    }


async def _current_draft(db: AsyncSession, fixture_id, org_id) -> dict:
    row = (await db.execute(
        text(
            "SELECT d.draft, d.updated_at, COALESCE(u.display_name, u.username), d.version "
            "FROM selection_drafts d LEFT JOIN users u ON u.id = d.updated_by "
            "WHERE d.fixture_id = :fid AND d.organisation_id = :org"
        ),
        {"fid": fixture_id, "org": org_id},
    )).first()
    if not row:
        return {"draft": None, "version": 0}
    return {
        "draft": row[0],
        "updated_at": row[1].isoformat() if row[1] else None,
        "updated_by": row[2],
        "version": row[3],
    }


def _draft_conflict(current: dict) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "draft_conflict",
        "message": "Someone else changed this draft since you loaded it.",
        **current,
    })


@router.get("/{fixture_id}/draft")
async def get_draft(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """The autosaved, unconfirmed side for this fixture: ``draft`` (null when
    there is none) and its ``version``. The board polls this to pick up another
    selector's changes.

    Separate from GET /selection/{id} so the pool payload BetterIQ shares is
    unchanged, and so only someone who can edit the XI is ever handed a
    half-built one."""
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    current = await _current_draft(db, fx.id, club.id)
    if current["draft"] is not None:
        # A carried draft (never edited) drops anyone who has since said
        # unavailable for the date. The stored row and its version are unchanged.
        current["draft"] = await selection_seed.without_unavailable(db, club.id, fx.played_on, current["draft"])
    return current


@router.put("/{fixture_id}/draft")
async def save_draft(
    fixture_id: str,
    body: DraftSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Autosave the board's working side. Never touches ``fixture_lineups``,
    so none of the checks the confirm path makes (clashes, call-ups, blocking
    rules) run here: they are judged when the selector confirms. Only the shape
    is cleaned up: ids that are not this club's players are dropped, and a
    captain or keeper who is not in the slots is cleared.

    ``base_version`` is the version the board last saw. If the draft has moved
    on (another selector saved, confirmed or discarded it) nothing is written
    and the answer is a 409 carrying the current draft. The write is one
    conditional statement, so two simultaneous saves cannot both win."""
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    if len(body.slots) > 40:
        raise HTTPException(status_code=400, detail="Too many slots")

    def _uid(v):
        try:
            return uuid.UUID(v) if v else None
        except (ValueError, AttributeError, TypeError):
            return None

    wanted = {_uid(v) for v in body.slots} - {None}
    wanted |= {_uid(body.captain_id), _uid(body.wicket_keeper_id)} - {None}
    wanted |= {u for u in (_uid(d.player_id) for d in body.demotions) if u}
    wanted |= {u for u in (_uid(d.callup_id) for d in body.demotions) if u}
    owned: set[uuid.UUID] = set()
    if wanted:
        res = await db.execute(
            select(Player.id).where(Player.organisation_id == club.id, Player.id.in_(wanted))
        )
        owned = {r[0] for r in res.fetchall()}

    seen: set[uuid.UUID] = set()
    slots: list[Optional[str]] = []
    for v in body.slots:
        u = _uid(v)
        if u is None or u not in owned or u in seen:
            slots.append(None)
            continue
        seen.add(u)
        slots.append(str(u))
    cap = _uid(body.captain_id)
    wk = _uid(body.wicket_keeper_id)
    demotions = []
    for d in body.demotions:
        u, f, c = _uid(d.player_id), _uid(d.fixture_id), _uid(d.callup_id)
        if u and f and u in owned and c in seen:
            demotions.append({
                "player_id": str(u), "fixture_id": str(f),
                "batting_order": d.batting_order, "callup_id": str(c),
            })
    payload = {
        "slots": slots,
        "captain_id": str(cap) if cap in seen else None,
        "wicket_keeper_id": str(wk) if wk in seen else None,
        "demotions": demotions,
    }
    params = {"fid": fx.id, "org": club.id, "d": json.dumps(payload), "uid": user.id}
    if body.base_version > 0:
        row = (await db.execute(
            text(
                "UPDATE selection_drafts SET draft = CAST(:d AS jsonb), updated_by = :uid, "
                "updated_at = now(), version = version + 1 "
                "WHERE fixture_id = :fid AND organisation_id = :org AND version = :base "
                "RETURNING version"
            ),
            {**params, "base": body.base_version},
        )).first()
    else:
        # The board saw no draft: only write if there still is none.
        row = (await db.execute(
            text(
                "INSERT INTO selection_drafts (fixture_id, organisation_id, draft, updated_by, updated_at, version) "
                "VALUES (:fid, :org, CAST(:d AS jsonb), :uid, now(), 1) "
                "ON CONFLICT (fixture_id) DO NOTHING RETURNING version"
            ),
            params,
        )).first()
    if row is None:
        current = await _current_draft(db, fx.id, club.id)
        await db.rollback()
        raise _draft_conflict(current)
    await db.commit()
    return {"status": "ok", "version": row[0]}


@router.delete("/{fixture_id}/draft")
async def discard_draft(
    fixture_id: str,
    base_version: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Throw the draft away: the board goes back to the confirmed XI. With
    ``base_version`` it only deletes the draft the caller saw: one another
    selector has changed since is refused (409), and one that is already gone
    is a no-op."""
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    sql = "DELETE FROM selection_drafts WHERE fixture_id = :fid AND organisation_id = :org"
    params: dict = {"fid": fx.id, "org": club.id}
    if base_version:
        sql += " AND version = :base"
        params["base"] = base_version
    deleted = (await db.execute(text(sql + " RETURNING 1"), params)).first()
    if deleted is None and base_version:
        current = await _current_draft(db, fx.id, club.id)
        if current["draft"] is not None:
            await db.rollback()
            raise _draft_conflict(current)
    await db.commit()
    return {"status": "ok", "version": 0}


@router.put("/{fixture_id}")
async def set_selection(
    fixture_id: str,
    body: LineupSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
    # Last, so a caller that passes db, club and user positionally is unaffected.
    background_tasks: BackgroundTasks = None,
):
    """Replace a fixture's lineup with the given set of players.

    Full-replace (not incremental): the selection board sends the whole side.
    Validates players belong to the club; de-dupes; clamps roles. A same-date
    clash with a same/higher grade is blocked (409); a clash with a strictly
    lower grade is a call-up — the player is removed from that lower XI here.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Validate + de-dupe incoming player ids.
    seen: set[uuid.UUID] = set()
    slots: list[LineupSlot] = []
    for s in body.players:
        pid = uuid.UUID(s.player_id)
        if pid in seen:
            continue
        seen.add(pid)
        slots.append(s)

    if seen:
        owned_res = await db.execute(
            select(Player.id).where(
                Player.organisation_id == club.id,
                Player.id.in_(seen),
            )
        )
        owned = {r[0] for r in owned_res.fetchall()}
        missing = seen - owned
        if missing:
            raise HTTPException(status_code=400, detail="One or more players are not in your club")

        # Clash policy: a player may be in only ONE XI per date — BUT a higher
        # grade takes precedence over a lower one. Team.sequence ranks our teams
        # (1st XI = 1, 2nd XI = 2 …), so a strictly lower sequence is the higher
        # grade. Picking a player here who's already in a *lower* grade calls
        # them up: we remove them from that XI on save. A clash with the same/a
        # higher grade (or one whose rank we can't tell) still blocks the save.
        if fx.played_on:
            this_seq: Optional[int] = None
            if fx.team_id:
                this_team = await db.get(Team, fx.team_id)
                if this_team and (this_team.sequence or 0) > 0:
                    this_seq = this_team.sequence

            clash_res = await db.execute(
                select(
                    FixtureLineup.player_id,
                    FixtureLineup.fixture_id,
                    func.coalesce(Player.display_name_override, Player.name),
                    Team.sequence,
                )
                .select_from(FixtureLineup)
                .join(Fixture, FixtureLineup.fixture_id == Fixture.id)
                .join(Player, FixtureLineup.player_id == Player.id)
                .outerjoin(Team, Fixture.team_id == Team.id)
                .where(
                    FixtureLineup.organisation_id == club.id,
                    Fixture.id != fx.id,
                    Fixture.played_on == fx.played_on,
                    FixtureLineup.player_id.in_(seen),
                )
            )
            blocking: set[str] = set()
            call_ups: list[tuple] = []  # (player_id, other_fixture_id) to vacate
            clash_rows = clash_res.fetchall()
            # Same-date games that can be played alongside this one (back to
            # back, or junior against senior) are not clashes: the player stays
            # in both XIs. Re-judged here, not trusted from the browser.
            playable = await selection_clash.compatible_fixtures(
                db, club.id, fx, {r[1] for r in clash_rows}
            )
            for pid, other_fid, pname, other_seq in clash_rows:
                if str(other_fid) in playable:
                    continue
                can_override = (
                    this_seq is not None
                    and (other_seq or 0) > 0
                    and this_seq < other_seq
                )
                if can_override:
                    call_ups.append((pid, other_fid))
                else:
                    blocking.add(pname)
            if blocking:
                names = ", ".join(sorted(blocking))
                raise HTTPException(
                    status_code=409,
                    detail=f"Already selected for another fixture on {fx.played_on.isoformat()}: {names}",
                )
            # Vacate the lower-grade XIs the called-up players came from.
            for pid, other_fid in call_ups:
                await db.execute(
                    text("DELETE FROM fixture_lineups WHERE fixture_id = :fid AND player_id = :pid"),
                    {"fid": other_fid, "pid": pid},
                )

            # Cascade: a player bumped out of THIS XI by a call-up drops into the
            # team below, taking the called-up player's now-vacant slot. The board
            # sends these as demotions; we only honour a demotion into a fixture we
            # just vacated a call-up from (which is, by construction, an owned,
            # same-date, strictly-lower-grade XI) and never for a player who's
            # still named in this XI.
            if body.demotions and call_ups:
                vacated = {str(fid) for _, fid in call_ups}
                parsed: list[tuple[uuid.UUID, uuid.UUID, Optional[int]]] = []
                demo_pids: set[uuid.UUID] = set()
                for d in body.demotions:
                    try:
                        d_pid = uuid.UUID(d.player_id)
                        d_fid = uuid.UUID(d.fixture_id)
                    except (ValueError, AttributeError, TypeError):
                        continue
                    if d_pid in seen or str(d_fid) not in vacated:
                        continue
                    demo_pids.add(d_pid)
                    parsed.append((d_pid, d_fid, d.batting_order))
                if demo_pids:
                    own2 = await db.execute(
                        select(Player.id).where(
                            Player.organisation_id == club.id,
                            Player.id.in_(demo_pids),
                        )
                    )
                    owned_demo = {r[0] for r in own2.fetchall()}
                    for d_pid, d_fid, d_bo in parsed:
                        if d_pid not in owned_demo:
                            continue
                        await db.execute(
                            text("DELETE FROM fixture_lineups WHERE fixture_id = :fid AND player_id = :pid"),
                            {"fid": d_fid, "pid": d_pid},
                        )
                        db.add(FixtureLineup(
                            fixture_id=d_fid,
                            player_id=d_pid,
                            organisation_id=club.id,
                            batting_order=d_bo,
                            is_captain=False,
                            is_wicket_keeper=False,
                            selected_by=user.id,
                        ))

    # The club's own association rules. Only a rule the club marked BLOCKING
    # refuses a save; a warning has already been shown on the board and is the
    # selector's to weigh. Re-checked here rather than trusted from the
    # browser — the board counts an overseas cap live so it can be watched
    # filling up, but this is the copy that decides.
    if seen:
        picked = (await db.execute(
            select(Player).where(Player.id.in_(seen))
        )).scalars().all()
        breaches = (await rule_context(db, club, fx, picked)).blocking_for(
            [str(pid) for pid in seen]
        )
        if breaches:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "selection_rules",
                    "message": "This side breaks a rule your club has set as blocking.",
                    "breaches": breaches,
                },
            )

    # Replace: clear existing rows, insert the new set.
    await db.execute(
        text("DELETE FROM fixture_lineups WHERE fixture_id = :fid"),
        {"fid": fx.id},
    )
    for s in slots:
        db.add(FixtureLineup(
            fixture_id=fx.id,
            player_id=uuid.UUID(s.player_id),
            organisation_id=club.id,
            batting_order=s.batting_order,
            is_captain=bool(s.is_captain),
            is_wicket_keeper=bool(s.is_wicket_keeper),
            selected_by=user.id,
        ))
    # Confirming makes the draft redundant: same transaction, so a failed
    # confirm leaves the draft alone.
    await db.execute(
        text("DELETE FROM selection_drafts WHERE fixture_id = :fid"),
        {"fid": fx.id},
    )
    # The team's next round opens with this side as a draft. Never blocks the
    # confirm and never touches a side somebody has already started.
    ordered = sorted(slots, key=lambda s: (s.batting_order is None, s.batting_order or 0))
    await selection_seed.seed_next_round_draft(
        db,
        org_id=club.id,
        fixture_id=fx.id,
        team_id=fx.team_id,
        played_on=fx.played_on,
        user_id=user.id,
        player_ids=[s.player_id for s in ordered],
        captain_id=next((s.player_id for s in ordered if s.is_captain), None),
        wicket_keeper_id=next((s.player_id for s in ordered if s.is_wicket_keeper), None),
    )
    await db.commit()
    # A club that asked for it has the confirmed side emailed to its captain.
    # After the commit, on its own session, never part of the confirm itself.
    if slots and background_tasks is not None \
            and selection_rules.club_config(club).get("notify_captain_on_confirm"):
        background_tasks.add_task(selection_notify.auto_send_captain, club.id, fx.id, user.id)
    return {"status": "ok", "count": len(slots)}


class NotifyBody(BaseModel):
    to: str = "captain"                 # captain | players
    message: Optional[str] = None       # an extra note for the players' email


@router.post("/{fixture_id}/notify")
async def notify_selection(
    fixture_id: str,
    body: NotifyBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Email the CONFIRMED side: to its captain (with every player's mobile) or
    to each selected player. A draft is never sent. See services/selection_notify."""
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    if body.to == "captain":
        return await selection_notify.send_to_captain(db, club, fx.id, user_id=user.id)
    if body.to == "players":
        note = (body.message or "")[:1000]
        return await selection_notify.send_to_players(db, club, fx.id, user_id=user.id, message=note)
    raise HTTPException(status_code=400, detail="Send to the captain or the players.")


@router.get("/{fixture_id}/notices")
async def selection_notices(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """What has been emailed about this fixture's confirmed side, newest first."""
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    return {"notices": await selection_notify.list_notices(db, club, fx.id)}
