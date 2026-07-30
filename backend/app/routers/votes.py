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
    eligibility_source: Optional[str] = None


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
    if body.eligibility_source is not None:
        if body.eligibility_source not in vote_svc.ELIGIBILITY_SOURCES:
            raise HTTPException(status_code=400, detail="Invalid eligibility source")
        s.eligibility_source = body.eligibility_source
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
    grade_id: Optional[str] = None,
    round_key: Optional[str] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """Played fixtures for a season year, newest first, each annotated with its
    voting state and ballot count.

    ``grade_id`` (one of the club's teams/grades) and ``round_key`` (the
    ``key`` of one of the returned ``rounds``) narrow the list — a club with
    several grades otherwise gets one long jumbled list with no way to jump
    straight to, say, 1st XI Round 10. ``q`` is a free-text opponent search.
    ``grades``/``rounds`` in the response are built from the WHOLE season
    regardless of the other filters, so the dropdowns never collapse to just
    the current selection.
    """
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
    season_fixtures = fx_res.scalars().all()

    # sync_fixtures never populated Fixture.grade_id (see effective_grade_ids'
    # own docstring) — fall back to the synced game's own grade for any
    # fixture whose column is unset, so the filter has options at all.
    grade_by_fixture = await vote_svc.effective_grade_ids(db, season_fixtures)

    grade_names: dict[str, str] = {}
    gids = {gid for gid in grade_by_fixture.values() if gid}
    if gids:
        from sqlalchemy import text
        gn_res = await db.execute(
            text("SELECT id, name FROM grades WHERE id = ANY(:ids)"), {"ids": list(gids)},
        )
        grade_names = {str(gid): name for gid, name in gn_res.fetchall()}
    grades = sorted(
        ({"id": gid, "name": name} for gid, name in grade_names.items()),
        key=lambda g: g["name"],
    )

    # Round options scoped to the grade filter (if any) but not the round
    # filter itself, newest first.
    rounds_seen: dict[str, tuple[str, Optional[date]]] = {}
    for f in season_fixtures:
        if grade_id and str(grade_by_fixture.get(str(f.id))) != grade_id:
            continue
        key = vote_svc.round_key_for(f)
        if key not in rounds_seen:
            rounds_seen[key] = (vote_svc.round_label_for(f), f.played_on)
    rounds = [
        {"key": k, "label": lbl}
        for k, (lbl, d) in sorted(
            rounds_seen.items(), key=lambda kv: vote_svc.round_sort_key(kv[1][0], kv[1][1]), reverse=True,
        )
    ]

    # Batch queries run over the WHOLE season (not just the filtered subset)
    # so the summary counters below reflect the real season state regardless
    # of which grade/round/search the manager currently has selected — the
    # same "options never collapse to the current filter" rule as grades/rounds.
    season_fids = [f.id for f in season_fixtures]
    season_match_ids = [vote_svc.match_ref_id(f) for f in season_fixtures]

    synced: set[str] = set()
    lineup_saved: set[str] = set()
    counts: dict[str, int] = {}
    overrides: dict[str, VoteFixtureOverride] = {}
    scorecard_counts: dict[str, int] = {}
    lineup_counts: dict[str, int] = {}
    player_counts: dict[str, int] = {}
    if season_fids:
        from sqlalchemy import text
        g_res = await db.execute(text("SELECT id FROM games WHERE id = ANY(:ids)"), {"ids": season_match_ids})
        synced_games = {str(r[0]) for r in g_res.fetchall()}
        synced = {str(f.id) for f in season_fixtures if str(vote_svc.match_ref_id(f)) in synced_games}
        l_res = await db.execute(
            text("SELECT DISTINCT fixture_id FROM fixture_lineups "
                 "WHERE organisation_id = :org AND fixture_id = ANY(:ids)"),
            {"org": club.id, "ids": season_fids},
        )
        lineup_saved = {str(r[0]) for r in l_res.fetchall()}
        c_res = await db.execute(
            text("SELECT fixture_id, COUNT(*) FROM vote_ballots "
                 "WHERE organisation_id = :org AND fixture_id = ANY(:ids) GROUP BY fixture_id"),
            {"org": club.id, "ids": season_fids},
        )
        counts = {str(fid): n for fid, n in c_res.fetchall()}
        o_res = await db.execute(
            select(VoteFixtureOverride).where(VoteFixtureOverride.fixture_id.in_(season_fids))
        )
        overrides = {str(o.fixture_id): o for o in o_res.scalars().all()}
        scorecard_counts = await vote_svc.scorecard_voter_counts(db, club.id, [gid for gid in season_match_ids if str(gid) in synced_games])
        lineup_counts = await vote_svc.lineup_voter_counts(db, club.id, [fid for fid in season_fids if str(fid) in lineup_saved])
        player_counts = await vote_svc.player_ballot_counts(db, club.id, season_fids)

    def _row(f: Fixture) -> dict:
        fid = str(f.id)
        ov = overrides.get(fid)
        source = vote_svc.effective_source(cfg, ov.eligibility_source if ov else None)
        # Cheap readiness for the list: a live Play.Cricket check per row would
        # mean one upstream call per fixture, so a 'playhq' fixture reads as
        # ready once played and the ballot page reports an unpublished side.
        ready = (
            fid in synced or fid in lineup_saved
            or (source == "playhq" and f.played_on is not None and f.played_on <= today)
        )
        state = vote_svc.fixture_vote_state(f, cfg, ov.status if ov else None, ready, today)
        close = vote_svc.fixture_close_date(f, cfg)
        eff_gid = grade_by_fixture.get(fid)
        match_id = vote_svc.match_ref_id(f)
        voters_expected = vote_svc.voters_expected_for(source, match_id, f.id, scorecard_counts, lineup_counts)
        ballots = counts.get(fid, 0)
        outstanding_count = max(0, voters_expected - player_counts.get(fid, 0)) if voters_expected else 0
        return {
            "id": fid,
            "opponent": f.opponent_name or f.label,
            "round": vote_svc.round_label_for(f),
            "round_key": vote_svc.round_key_for(f),
            "date": f.played_on.isoformat() if f.played_on else None,
            "grade": grade_names.get(str(eff_gid)) if eff_gid else None,
            "grade_id": str(eff_gid) if eff_gid else None,
            "home_away": f.home_away,
            "state": state,
            "source": source,
            "source_override": ov.eligibility_source if ov else None,
            "has_lineup": fid in lineup_saved,
            "synced": fid in synced,
            "closes_on": close.isoformat() if close and state == "open" else None,
            "ballots": ballots,
            "voters_expected": voters_expected,
            "outstanding_count": outstanding_count,
            "_round_key": vote_svc.round_key_for(f),
        }

    season_rows = [_row(f) for f in season_fixtures]
    rows_by_id = {r["id"]: r for r in season_rows}

    fixtures = season_fixtures
    if grade_id:
        fixtures = [f for f in fixtures if str(grade_by_fixture.get(str(f.id))) == grade_id]
    if round_key:
        fixtures = [f for f in fixtures if vote_svc.round_key_for(f) == round_key.lower()]
    if q:
        ql = q.strip().lower()
        fixtures = [f for f in fixtures if ql in (f.opponent_name or f.label or "").lower()]
    out = [{k: v for k, v in rows_by_id[str(f.id)].items() if k != "_round_key"} for f in fixtures]

    # Counter strip — whole season, unaffected by the current filters.
    round_keys_total = {r["_round_key"] for r in season_rows}
    round_keys_with_ballots = {r["_round_key"] for r in season_rows if r["ballots"] > 0}
    latest_round_key = season_rows[0]["_round_key"] if season_rows else None  # season_fixtures sorted newest-first
    latest_round_rows = [r for r in season_rows if r["_round_key"] == latest_round_key] if latest_round_key else []
    summary = {
        "open": sum(1 for r in season_rows if r["state"] == "open"),
        "awaiting_team": sum(1 for r in season_rows if r["state"] == "awaiting_team"),
        "ballots_in": sum(r["ballots"] for r in latest_round_rows),
        "ballots_expected": sum(r["voters_expected"] for r in latest_round_rows),
        "rounds_counted": len(round_keys_with_ballots),
        "rounds_total": len(round_keys_total),
    }

    return {
        "year": year, "years": years or [year], "fixtures": out, "settings": _settings_payload(s),
        "grades": grades, "grade_id": grade_id, "rounds": rounds, "round_key": round_key, "q": q,
        "summary": summary,
    }


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
    ov = await vote_svc.get_override(db, fx.id)
    # check_all so the admin can see what each source would give them before
    # switching this fixture over.
    elig = await vote_svc.resolve_eligibility(
        db, club, fx, cfg, ov.eligibility_source if ov else None, check_all=True,
    )
    eligible = elig["players"]
    state = vote_svc.fixture_vote_state(fx, cfg, ov.status if ov else None, bool(eligible))
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

    outstanding = await vote_svc.outstanding_voters(db, club.id, eligible, ballots)

    return {
        "fixture": {
            "id": str(fx.id),
            "opponent": fx.opponent_name or fx.label,
            "round": vote_svc.round_label_for(fx),
            "date": fx.played_on.isoformat() if fx.played_on else None,
            "state": state,
            "override": ov.status if ov else None,
            "voters_expected": len(eligible),
        },
        "outstanding": outstanding,
        "settings": _settings_payload(s),
        "eligibility": {
            "requested": elig["requested"],
            "used": elig["used"],
            "fell_back": elig["fell_back"],
            "counts": elig["counts"],
            "unmatched": elig["unmatched"],
            "override": ov.eligibility_source if ov else None,
            "labels": elig["labels"],
        },
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
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)
    ov = await vote_svc.get_override(db, fx.id)
    elig = await vote_svc.resolve_eligibility(
        db, club, fx, cfg, ov.eligibility_source if ov else None,
    )
    eligible = elig["players"]
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail="No team list for this game yet — save a BetterSelect XI, publish the side on Play.Cricket, or wait for the scorecard to sync",
        )
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
                        user_id, *, status: str | None = None,
                        source: str | None = None) -> None:
    """Upsert the fixture's override row. Only the field(s) passed are touched,
    so setting a source never disturbs a lock (and vice versa)."""
    res = await db.execute(
        select(VoteFixtureOverride).where(VoteFixtureOverride.fixture_id == fx.id)
    )
    row = res.scalar_one_or_none()
    if not row:
        row = VoteFixtureOverride(fixture_id=fx.id, organisation_id=club.id)
        db.add(row)
    if status is not None:
        row.status = status
    if source is not None:
        # "" clears the override and falls back to the club default.
        row.eligibility_source = source or None
    row.set_by = user_id
    await db.commit()


@router.post("/fixtures/{fixture_id}/lock")
async def lock_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    fx = await _org_fixture(db, club, fixture_id)
    await _set_override(db, club, fx, user.id, status="locked")
    return {"status": "ok", "state": "locked"}


@router.post("/fixtures/{fixture_id}/reopen")
async def reopen_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    fx = await _org_fixture(db, club, fixture_id)
    await _set_override(db, club, fx, user.id, status="reopened")
    return {"status": "ok", "state": "open"}


class SourceBody(BaseModel):
    eligibility_source: Optional[str] = None  # None/"" clears back to the club default


@router.post("/fixtures/{fixture_id}/source")
async def set_fixture_source(
    fixture_id: str,
    body: SourceBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Override which team list this one fixture's votes run off — e.g. a club
    that normally waits for the scorecard voting on the night of a final."""
    fx = await _org_fixture(db, club, fixture_id)
    src = body.eligibility_source or ""
    if src and src not in vote_svc.ELIGIBILITY_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid eligibility source")
    await _set_override(db, club, fx, user.id, source=src)
    return {"status": "ok", "eligibility_source": src or None}


# ─── Bulk actions (Games hub) ────────────────────────────────────────────────

class BulkStateBody(BaseModel):
    fixture_ids: list[str]
    action: str  # "open" | "lock"


@router.post("/bulk-state")
async def bulk_state(
    body: BulkStateBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Open or lock several fixtures at once from the hub's multi-select.
    Same per-fixture rules as the single lock/reopen endpoints; a fixture
    that can't transition (no team list yet, for "open") is reported in
    ``skipped`` rather than failing the whole request."""
    if body.action not in ("open", "lock"):
        raise HTTPException(status_code=400, detail="Action must be 'open' or 'lock'")
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)

    updated = 0
    skipped = []
    for raw_id in body.fixture_ids:
        try:
            fx = await _org_fixture(db, club, raw_id)
        except HTTPException:
            skipped.append({"fixture_id": raw_id, "reason": "not_found"})
            continue
        if body.action == "lock":
            await _set_override(db, club, fx, user.id, status="locked")
            updated += 1
            continue
        ov = await vote_svc.get_override(db, fx.id)
        elig = await vote_svc.resolve_eligibility(db, club, fx, cfg, ov.eligibility_source if ov else None)
        if not elig["players"]:
            skipped.append({"fixture_id": raw_id, "reason": "awaiting_team"})
            continue
        await _set_override(db, club, fx, user.id, status="reopened")
        updated += 1
    return {"updated": updated, "skipped": skipped}


# ─── Nudge (email reminder) ──────────────────────────────────────────────────
#
# The design brief assumed automated SMS/WhatsApp reminders; this codebase has
# no SMS/WhatsApp sending integration (BetterComms is email-only). A nudge is
# therefore a reminder email to the player's stored address — a player with no
# email simply can't be nudged this way (reason "no_contact"). Rate-limited to
# one nudge per player per fixture per NUDGE_COOLDOWN_HOURS, same posture as
# the BetterComms usage policy: never let a manager mashing the button spam a
# player's inbox.

class NudgeBody(BaseModel):
    fixture_id: Optional[str] = None
    fixture_ids: Optional[list[str]] = None
    player_ids: Optional[list[str]] = None


@router.post("/nudge")
async def nudge(
    body: NudgeBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    if not body.fixture_id and not body.fixture_ids:
        raise HTTPException(status_code=400, detail="Provide fixture_id or fixture_ids")
    s = await vote_svc.get_settings(db, club.id)
    cfg = vote_svc.effective_config(s)

    target_fixture_ids = [body.fixture_id] if body.fixture_id else list(body.fixture_ids or [])
    targets: list[tuple[Fixture, dict, bool]] = []
    for raw_id in target_fixture_ids:
        try:
            fx = await _org_fixture(db, club, raw_id)
        except HTTPException:
            continue
        ov = await vote_svc.get_override(db, fx.id)
        elig = await vote_svc.resolve_eligibility(db, club, fx, cfg, ov.eligibility_source if ov else None)
        ballots_by_fx = await vote_svc.load_ballots_by_fixture(db, club.id, [fx.id])
        outstanding = await vote_svc.outstanding_voters(db, club.id, elig["players"], ballots_by_fx.get(str(fx.id), []))
        wanted = set(body.player_ids) if (body.fixture_id and body.player_ids) else None
        candidates = [p for p in outstanding if wanted is None or p["id"] in wanted]
        if not candidates:
            continue
        recent = await vote_svc.recently_nudged(db, fx.id, [uuid.UUID(p["id"]) for p in candidates])
        for p in candidates:
            targets.append((fx, p, p["id"] in recent))

    sent = 0
    failed = []
    for fx, p, is_recent in targets:
        if is_recent:
            failed.append({"player_id": p["id"], "reason": "recently_nudged"})
            continue
        ok, reason = await vote_svc.send_nudge(db, club, fx, p, s.link_token if s else None)
        if ok:
            sent += 1
        else:
            failed.append({"player_id": p["id"], "reason": reason})
    await db.commit()
    return {"sent": sent, "failed": failed}


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

    # Club/stage lockup for the leaderboard header and the awards-night stage.
    board["club_name"] = club.name
    board["club_short"] = _club_short(club.name, club.short_name)
    board["season_label"] = vote_svc.season_label(year)
    board["grade_name"] = grades.get(grade_id) if grade_id else "Whole club"
    board["grade_id"] = grade_id
    board["race_caption"] = None  # no synthesis attempted yet — nullable per the API contract
    return board


def _club_short(name: Optional[str], short_name: Optional[str]) -> str:
    if short_name:
        return short_name.strip()[:6].upper()
    words = [w for w in (name or "").split() if w]
    initials = "".join(w[0] for w in words[:3]).upper()
    return initials or "CC"
