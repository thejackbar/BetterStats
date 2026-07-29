"""BetterSelect — vote collection (admin side).

Config, per-fixture ballot management and the Brownlow-style season
leaderboard. Two capabilities split the surface:

  * MANAGE_VOTES      — settings + the link, entering/editing/deleting ballots
                        (paper votes, the captain texting their 3-2-1 in),
                        lock/reopen, and the per-fixture ballot detail (which
                        necessarily shows who voted for whom).
  * VIEW_VOTE_RESULTS — the leaderboard and per-round results. Handed out per
                        user by the Main Admin, because many clubs keep the
                        count secret until presentation night. club_admins
                        implicitly hold both (role implies all caps).

Everything is derived on read from raw ballots + the current settings — see
services/votes.py.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_VOTES, VIEW_VOTE_RESULTS, require_any_cap, require_cap
from app.models.db import (
    Fixture, Organisation, User, VoteBallot, VoteBallotPick, VoteFixtureOverride,
    VoteSettings, get_db,
)
from app.routers.auth import get_current_club
from app.services import votes as vote_svc

router = APIRouter(prefix="/votes", tags=["votes"])


# ─── Settings ────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None
    voter_mode: Optional[str] = None
    ballot_values: Optional[list[int]] = None
    counting_method: Optional[str] = None
    tie_policy: Optional[str] = None
    allow_self_vote: Optional[bool] = None
    allow_non_participants: Optional[bool] = None
    auto_close_days: Optional[int] = None


def _settings_payload(s: Optional[VoteSettings]) -> dict:
    cfg = vote_svc.effective_config(s)
    cfg["token"] = s.link_token if s else None
    return cfg


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    return _settings_payload(await vote_svc.get_settings(db, club.id))


@router.post("/settings")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    s = await vote_svc.get_settings(db, club.id)
    if not s:
        s = VoteSettings(organisation_id=club.id)
        db.add(s)

    if body.voter_mode is not None:
        if body.voter_mode not in vote_svc.VOTER_MODES:
            raise HTTPException(status_code=400, detail="Invalid voter mode")
        s.voter_mode = body.voter_mode
    if body.counting_method is not None:
        if body.counting_method not in vote_svc.COUNTING_METHODS:
            raise HTTPException(status_code=400, detail="Invalid counting method")
        s.counting_method = body.counting_method
    if body.tie_policy is not None:
        if body.tie_policy not in vote_svc.TIE_POLICIES:
            raise HTTPException(status_code=400, detail="Invalid tie policy")
        s.tie_policy = body.tie_policy
    if body.ballot_values is not None:
        if not body.ballot_values:
            raise HTTPException(status_code=400, detail="The ballot needs at least one position")
        s.ballot_values = vote_svc.clean_ballot_values(body.ballot_values)
    if body.allow_self_vote is not None:
        s.allow_self_vote = bool(body.allow_self_vote)
    if body.allow_non_participants is not None:
        s.allow_non_participants = bool(body.allow_non_participants)
    if body.auto_close_days is not None:
        if not (1 <= int(body.auto_close_days) <= 60):
            raise HTTPException(status_code=400, detail="Auto-close must be 1-60 days")
        s.auto_close_days = int(body.auto_close_days)
    if body.require_pin is not None:
        s.require_pin = bool(body.require_pin)
    if body.enabled is not None:
        s.enabled = bool(body.enabled)
        if s.enabled and not s.link_token:
            s.link_token = secrets.token_urlsafe(24)

    await db.commit()
    await db.refresh(s)
    return _settings_payload(s)


@router.post("/settings/regenerate")
async def regenerate_link(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    s = await vote_svc.get_settings(db, club.id)
    if not s:
        raise HTTPException(status_code=404, detail="Voting isn't set up yet")
    s.link_token = secrets.token_urlsafe(24)
    await db.commit()
    return _settings_payload(s)


# ─── Fixtures ────────────────────────────────────────────────────────────────

async def _org_fixture(db: AsyncSession, club: Organisation, fixture_id: str) -> Fixture:
    try:
        fid = uuid.UUID(fixture_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fixture id")
    fx = await db.get(Fixture, fid)
    if not fx or fx.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fx


@router.get("/fixtures")
async def list_vote_fixtures(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """Played fixtures for a season year, newest first, each annotated with its
    voting state and ballot count. Also returns the season-year options."""
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)
    today = date.today()
    year = year or vote_svc.season_year_for(today)

    dates_res = await db.execute(
        select(Fixture.played_on).where(
            Fixture.organisation_id == club.id, Fixture.played_on.is_not(None),
        )
    )
    years = sorted(
        {vote_svc.season_year_for(d) for (d,) in dates_res.fetchall() if d and d <= today},
        reverse=True,
    )

    start, end = vote_svc.season_window(year)
    fx_res = await db.execute(
        select(Fixture)
        .where(
            Fixture.organisation_id == club.id,
            Fixture.played_on.is_not(None),
            Fixture.played_on >= start,
            Fixture.played_on <= min(end, today),
        )
        .order_by(Fixture.played_on.desc())
    )
    fixtures = fx_res.scalars().all()
    fids = [f.id for f in fixtures]

    synced: set[str] = set()
    counts: dict[str, int] = {}
    overrides: dict[str, str] = {}
    grade_names: dict[str, str] = {}
    if fids:
        from sqlalchemy import text
        g_res = await db.execute(text("SELECT id FROM games WHERE id = ANY(:ids)"), {"ids": fids})
        synced = {str(r[0]) for r in g_res.fetchall()}
        c_res = await db.execute(
            text("SELECT fixture_id, COUNT(*) FROM vote_ballots "
                 "WHERE organisation_id = :org AND fixture_id = ANY(:ids) GROUP BY fixture_id"),
            {"org": club.id, "ids": fids},
        )
        counts = {str(fid): n for fid, n in c_res.fetchall()}
        o_res = await db.execute(
            select(VoteFixtureOverride).where(VoteFixtureOverride.fixture_id.in_(fids))
        )
        overrides = {str(o.fixture_id): o.status for o in o_res.scalars().all()}
        gids = {f.grade_id for f in fixtures if f.grade_id}
        if gids:
            gn_res = await db.execute(
                text("SELECT id, name FROM grades WHERE id = ANY(:ids)"), {"ids": list(gids)},
            )
            grade_names = {str(gid): name for gid, name in gn_res.fetchall()}

    out = []
    for f in fixtures:
        fid = str(f.id)
        state = vote_svc.fixture_vote_state(f, cfg, overrides.get(fid), fid in synced, today)
        close = vote_svc.fixture_close_date(f, cfg)
        out.append({
            "id": fid,
            "opponent": f.opponent_name or f.label,
            "round": vote_svc.round_label_for(f),
            "date": f.played_on.isoformat() if f.played_on else None,
            "grade": grade_names.get(str(f.grade_id)) if f.grade_id else None,
            "grade_id": str(f.grade_id) if f.grade_id else None,
            "home_away": f.home_away,
            "state": state,
            "closes_on": close.isoformat() if close and state == "open" else None,
            "ballots": counts.get(fid, 0),
        })
    return {"year": year, "years": years or [year], "fixtures": out, "settings": _settings_payload(s)}


@router.get("/fixtures/{fixture_id}")
async def fixture_detail(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Everything about one fixture's vote: eligible players, every ballot
    (with picks — MANAGE_VOTES only, since this shows who voted for whom), and
    the computed weekly result under the current settings."""
    fx = await _org_fixture(db, club, fixture_id)
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)
    has_game = await vote_svc.game_exists(db, fx.id)
    override = await vote_svc.get_override(db, fx.id)
    state = vote_svc.fixture_vote_state(fx, cfg, override, has_game)

    eligible = await vote_svc.eligible_players(db, club.id, fx.id) if has_game else []
    ballots_by_fx = await vote_svc.load_ballots_by_fixture(db, club.id, [fx.id])
    ballots = ballots_by_fx.get(str(fx.id), [])

    pids = {str(p.player_id) for b in ballots for p in b.picks}
    pids |= {str(b.voter_player_id) for b in ballots if b.voter_player_id}
    names = await vote_svc.player_names(db, club.id, pids)
    for p in eligible:
        names.setdefault(p["id"], p["name"])

    values = cfg["ballot_values"]
    totals = vote_svc.tally_ballots(ballots, values)
    awarded = vote_svc.award_weekly_points(totals, cfg)
    results = sorted(
        (
            {"player_id": pid, "name": names.get(pid, "Unknown"),
             "raw": t["raw"], "counts": t["counts"], "points": awarded.get(pid, 0)}
            for pid, t in totals.items()
        ),
        key=lambda r: (-r["points"], -r["raw"], r["name"]),
    )

    return {
        "fixture": {
            "id": str(fx.id),
            "opponent": fx.opponent_name or fx.label,
            "round": vote_svc.round_label_for(fx),
            "date": fx.played_on.isoformat() if fx.played_on else None,
            "state": state,
            "override": override,
        },
        "settings": _settings_payload(s),
        "eligible": eligible,
        "ballots": [
            {
                "id": str(b.id),
                "voter_player_id": str(b.voter_player_id) if b.voter_player_id else None,
                "voter": names.get(str(b.voter_player_id)) if b.voter_player_id else b.voter_name,
                "voter_kind": b.voter_kind,
                "source": b.source,
                "picks": [
                    {"position": p.position, "player_id": str(p.player_id),
                     "name": names.get(str(p.player_id), "Unknown")}
                    for p in sorted(b.picks, key=lambda p: p.position)
                ],
            }
            for b in sorted(ballots, key=lambda b: (b.voter_kind != "player", (b.voter_name or names.get(str(b.voter_player_id), "")).lower()))
        ],
        "results": results,
    }


# ─── Ballot entry / moderation ───────────────────────────────────────────────

class AdminBallot(BaseModel):
    voter_player_id: Optional[str] = None
    voter_name: Optional[str] = None
    picks: list[str]  # player ids, position 1 first


async def _replace_picks(db: AsyncSession, ballot: VoteBallot, pick_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(VoteBallotPick).where(VoteBallotPick.ballot_id == ballot.id))
    for i, pid in enumerate(pick_ids, start=1):
        db.add(VoteBallotPick(ballot_id=ballot.id, position=i, player_id=pid))


def _validate_picks(picks: list[str], eligible_ids: set[str], max_positions: int,
                    voter_player_id: Optional[str], allow_self_vote: bool,
                    require_full: bool) -> list[uuid.UUID]:
    if not picks:
        raise HTTPException(status_code=400, detail="Pick at least one player")
    if len(picks) > max_positions:
        raise HTTPException(status_code=400, detail=f"The ballot has {max_positions} position(s)")
    if require_full and len(picks) < max_positions:
        raise HTTPException(status_code=400, detail="Fill every voting position")
    if len(set(picks)) != len(picks):
        raise HTTPException(status_code=400, detail="Each position must be a different player")
    out = []
    for pid in picks:
        if pid not in eligible_ids:
            raise HTTPException(status_code=400, detail="Votes can only go to players who played in this game")
        if voter_player_id and pid == voter_player_id and not allow_self_vote:
            raise HTTPException(status_code=400, detail="Voting for yourself isn't allowed at this club")
        out.append(uuid.UUID(pid))
    return out


@router.post("/fixtures/{fixture_id}/ballots")
async def admin_enter_ballot(
    fixture_id: str,
    body: AdminBallot,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Enter (or replace) a ballot on a voter's behalf — paper votes, the
    captain texting their 3-2-1 in. Deliberately looser than the public page:
    works whatever the voting state (paper votes often arrive after close) and
    for any named voter, not just those the self-serve mode would let through —
    but picks are still restricted to who actually played, and the club's
    self-vote rule still applies."""
    fx = await _org_fixture(db, club, fixture_id)
    if not await vote_svc.game_exists(db, fx.id):
        raise HTTPException(status_code=409, detail="This game's scorecard hasn't synced yet — votes open once it has")
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)
    eligible = await vote_svc.eligible_players(db, club.id, fx.id)
    eligible_ids = {p["id"] for p in eligible}

    voter_pid: Optional[uuid.UUID] = None
    voter_name: Optional[str] = None
    if body.voter_player_id:
        try:
            voter_pid = uuid.UUID(body.voter_player_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid voter")
        from app.models.db import Player
        voter = await db.get(Player, voter_pid)
        if not voter or voter.organisation_id != club.id:
            raise HTTPException(status_code=404, detail="Voter not found")
    else:
        voter_name = (body.voter_name or "").strip()[:120]
        if not voter_name:
            raise HTTPException(status_code=400, detail="Give the voter a name")

    pick_ids = _validate_picks(
        body.picks, eligible_ids, len(cfg["ballot_values"]),
        str(voter_pid) if voter_pid else None, cfg["allow_self_vote"],
        require_full=False,
    )

    if voter_pid is not None:
        res = await db.execute(select(VoteBallot).where(
            VoteBallot.fixture_id == fx.id, VoteBallot.voter_player_id == voter_pid,
        ))
    else:
        from sqlalchemy import func
        res = await db.execute(select(VoteBallot).where(
            VoteBallot.fixture_id == fx.id,
            VoteBallot.voter_player_id.is_(None),
            func.lower(VoteBallot.voter_name) == voter_name.lower(),
        ))
    ballot = res.scalar_one_or_none()
    if not ballot:
        ballot = VoteBallot(
            organisation_id=club.id,
            fixture_id=fx.id,
            voter_player_id=voter_pid,
            voter_name=voter_name,
            voter_kind="player" if (voter_pid and str(voter_pid) in eligible_ids) else "non_player",
            source="admin",
            recorded_by=user.id,
        )
        db.add(ballot)
        await db.flush()
    else:
        ballot.source = "admin"
        ballot.recorded_by = user.id
    await _replace_picks(db, ballot, pick_ids)
    await db.commit()
    return {"status": "ok", "ballot_id": str(ballot.id)}


@router.delete("/ballots/{ballot_id}")
async def delete_ballot(
    ballot_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Remove a ballot outright — the spoof-voter moderation path."""
    try:
        bid = uuid.UUID(ballot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ballot id")
    ballot = await db.get(VoteBallot, bid)
    if not ballot or ballot.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Ballot not found")
    await db.delete(ballot)
    await db.commit()
    return {"status": "ok"}


# ─── Lock / reopen ───────────────────────────────────────────────────────────

async def _set_override(db: AsyncSession, club: Organisation, fx: Fixture,
                        status: str, user_id) -> None:
    res = await db.execute(
        select(VoteFixtureOverride).where(VoteFixtureOverride.fixture_id == fx.id)
    )
    row = res.scalar_one_or_none()
    if row:
        row.status = status
        row.set_by = user_id
    else:
        db.add(VoteFixtureOverride(
            fixture_id=fx.id, organisation_id=club.id, status=status, set_by=user_id,
        ))
    await db.commit()


@router.post("/fixtures/{fixture_id}/lock")
async def lock_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    fx = await _org_fixture(db, club, fixture_id)
    await _set_override(db, club, fx, "locked", user.id)
    return {"status": "ok", "state": "locked"}


@router.post("/fixtures/{fixture_id}/reopen")
async def reopen_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    fx = await _org_fixture(db, club, fixture_id)
    await _set_override(db, club, fx, "reopened", user.id)
    return {"status": "ok", "state": "open"}


# ─── Leaderboard ─────────────────────────────────────────────────────────────

@router.get("/leaderboard")
async def leaderboard(
    year: Optional[int] = None,
    grade_id: Optional[str] = None,
    through_round: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """The Brownlow board — round-by-round, club-wide or one grade, cumulative
    standings through a chosen round (leave through_round off for the full
    season to date). Gated per user via VIEW_VOTE_RESULTS."""
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)
    year = year or vote_svc.season_year_for(date.today())

    board = await vote_svc.build_leaderboard(
        db, club.id, cfg, year, grade_id=grade_id or None, through_round=through_round,
    )

    # Grade options: grades whose fixtures collected votes this season (from an
    # unfiltered pass when a grade filter is applied, so options don't collapse
    # to the current selection).
    if grade_id:
        full = await vote_svc.build_leaderboard(db, club.id, cfg, year)
    else:
        full = board
    grades: dict[str, str] = {}
    for rd in full["rounds"]:
        for f in rd["fixtures"]:
            if f["grade_id"] and f["grade"]:
                grades[f["grade_id"]] = f["grade"]
    board["grades"] = sorted(
        ({"id": gid, "name": name} for gid, name in grades.items()),
        key=lambda g: g["name"],
    )
    return board
