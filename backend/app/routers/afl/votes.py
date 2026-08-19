"""BetterFootball — vote collection (admin side).

Medals, per-game ballot management and the best-and-fairest season count. The
cricket surface's shape, keyed on ``games`` rather than a fixtures table, and
with no eligibility source to pick between: football has one team list, the one
PlayHQ returns with the game, already stored by the sync.

Two capabilities split the surface, the SAME two cricket uses:

  * MANAGE_VOTES      — medals and their links, entering/editing/deleting
                        ballots (paper votes, the captain texting their 3-2-1
                        in), lock/reopen, and the per-game ballot detail (which
                        necessarily shows who voted for whom).
  * VIEW_VOTE_RESULTS — the count. Handed out per user by the Main Admin,
                        because a club keeps its B&F secret until presentation
                        night. club_admins implicitly hold both.

Everything is derived on read — see services/afl/votes.py.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_VOTES, VIEW_VOTE_RESULTS, require_any_cap, require_cap
from app.models.afl import AflVoteBallot, AflVoteBallotPick, AflVoteGameOverride, AflVoteMedal
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.services.afl import lineups as lineup_svc
from app.services.afl import votes as vote_svc

router = APIRouter(prefix="/votes", tags=["afl-votes"])


# ─── Medals ──────────────────────────────────────────────────────────────────

class MedalUpdate(BaseModel):
    name: Optional[str] = None
    grade_ids: Optional[list[str]] = None
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None
    voter_mode: Optional[str] = None
    ballot_values: Optional[list[int]] = None
    counting_method: Optional[str] = None
    tie_policy: Optional[str] = None
    allow_self_vote: Optional[bool] = None
    allow_non_participants: Optional[bool] = None
    auto_close_days: Optional[int] = None


def _medal_payload(m: Optional[AflVoteMedal], grade_names: Optional[dict] = None) -> dict:
    cfg = vote_svc.effective_config(m)
    cfg["token"] = m.link_token if m else None
    cfg["grade_names"] = (grade_names or {}).get(str(m.id), []) if m else []
    return cfg


async def _medals_payload(db: AsyncSession, club: Organisation) -> list[dict]:
    medals = await vote_svc.list_medals(db, club.id)
    names = await vote_svc.medal_grade_names(db, club.id, medals)
    return [_medal_payload(m, names) for m in medals]


async def _one_payload(db: AsyncSession, club: Organisation, m: AflVoteMedal) -> dict:
    return _medal_payload(m, await vote_svc.medal_grade_names(db, club.id, [m]))


async def _resolve_or_404(db: AsyncSession, club: Organisation, medal_id: Optional[str]) -> Optional[AflVoteMedal]:
    """The medal a read means. A named id that doesn't resolve is a 404 — a
    stale link should say so rather than silently counting a different award."""
    if medal_id:
        medal = await vote_svc.get_medal(db, club.id, medal_id)
        if not medal:
            raise HTTPException(status_code=404, detail="Medal not found")
        return medal
    return await vote_svc.resolve_medal(db, club.id)


async def _medal_for_write(db: AsyncSession, club: Organisation, medal_id: Optional[str]) -> AflVoteMedal:
    """The medal a write targets. Never None — a club acting on votes for the
    first time gets its default medal minted rather than a confusing 404."""
    if medal_id:
        medal = await vote_svc.get_medal(db, club.id, medal_id)
        if not medal:
            raise HTTPException(status_code=404, detail="Medal not found")
        return medal
    return await vote_svc.ensure_default_medal(db, club.id)


def _apply(m: AflVoteMedal, body: MedalUpdate) -> None:
    """Validate and assign. Only fields actually sent are touched, so the
    grades panel and the ballot panel save independently."""
    if body.name is not None:
        if not (body.name or "").strip():
            raise HTTPException(status_code=400, detail="Give the medal a name")
        m.name = vote_svc.clean_medal_name(body.name)
    if body.grade_ids is not None:
        # An empty list is meaningful: it means every grade.
        m.grade_ids = vote_svc.clean_grade_ids(body.grade_ids)
    if body.voter_mode is not None:
        if body.voter_mode not in vote_svc.VOTER_MODES:
            raise HTTPException(status_code=400, detail="Invalid voter mode")
        m.voter_mode = body.voter_mode
    if body.counting_method is not None:
        if body.counting_method not in vote_svc.COUNTING_METHODS:
            raise HTTPException(status_code=400, detail="Invalid counting method")
        m.counting_method = body.counting_method
    if body.tie_policy is not None:
        if body.tie_policy not in vote_svc.TIE_POLICIES:
            raise HTTPException(status_code=400, detail="Invalid tie policy")
        m.tie_policy = body.tie_policy
    if body.ballot_values is not None:
        if not body.ballot_values:
            raise HTTPException(status_code=400, detail="The ballot needs at least one position")
        m.ballot_values = vote_svc.clean_ballot_values(body.ballot_values)
    if body.allow_self_vote is not None:
        m.allow_self_vote = bool(body.allow_self_vote)
    if body.allow_non_participants is not None:
        m.allow_non_participants = bool(body.allow_non_participants)
    if body.auto_close_days is not None:
        if not (1 <= int(body.auto_close_days) <= 60):
            raise HTTPException(status_code=400, detail="Auto-close must be 1-60 days")
        m.auto_close_days = int(body.auto_close_days)
    if body.require_pin is not None:
        m.require_pin = bool(body.require_pin)
    if body.enabled is not None:
        m.enabled = bool(body.enabled)
        if m.enabled and not m.link_token:
            m.link_token = vote_svc.new_token()


@router.get("/medals")
async def list_medals(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """Every medal, plus the grade options one can be scoped to — each grade
    NAME once, since listing it per season would offer a decade of rows that
    all mean the same thing."""
    return {
        "medals": await _medals_payload(db, club),
        "grades": await vote_svc.club_grade_options(db, club.id),
    }


@router.post("/medals")
async def create_medal(
    body: MedalUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Add a medal. A second medal starts from the DEFAULTS, not a copy of the
    first — a club adding a Reserves medal beside a senior one is usually
    changing the ballot shape, and inheriting settings it then has to notice
    and undo is the worse mistake."""
    existing = await vote_svc.list_medals(db, club.id)
    medal = AflVoteMedal(
        id=uuid.uuid4(), organisation_id=club.id,
        name=vote_svc.clean_medal_name(body.name) if body.name else vote_svc.DEFAULT_MEDAL_NAME,
        position=len(existing),
    )
    db.add(medal)
    _apply(medal, body)
    await db.commit()
    await db.refresh(medal)
    return await _one_payload(db, club, medal)


@router.patch("/medals/{medal_id}")
async def update_medal(
    medal_id: str,
    body: MedalUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    medal = await vote_svc.get_medal(db, club.id, medal_id)
    if not medal:
        raise HTTPException(status_code=404, detail="Medal not found")
    _apply(medal, body)
    await db.commit()
    await db.refresh(medal)
    return await _one_payload(db, club, medal)


@router.delete("/medals/{medal_id}")
async def delete_medal(
    medal_id: str,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Delete a medal and every ballot cast towards it. The ballots cascade, so
    this destroys a season's count — hence the explicit ``confirm`` once any
    exist, and the refusal to remove a club's last medal (which would leave the
    screens with nothing to resolve to)."""
    medal = await vote_svc.get_medal(db, club.id, medal_id)
    if not medal:
        raise HTTPException(status_code=404, detail="Medal not found")
    if len(await vote_svc.list_medals(db, club.id)) <= 1:
        raise HTTPException(status_code=409, detail="A club keeps at least one medal — rename this one instead")
    res = await db.execute(
        select(func.count()).select_from(AflVoteBallot).where(AflVoteBallot.medal_id == medal.id))
    ballots = int(res.scalar() or 0)
    if ballots and not confirm:
        raise HTTPException(
            status_code=409,
            detail=f"{ballots} ballot(s) have been cast for this medal and would be deleted with it")
    await db.delete(medal)
    await db.commit()
    return {"status": "ok", "deleted_ballots": ballots}


@router.post("/medals/{medal_id}/regenerate")
async def regenerate_link(
    medal_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    medal = await vote_svc.get_medal(db, club.id, medal_id)
    if not medal:
        raise HTTPException(status_code=404, detail="Medal not found")
    medal.link_token = vote_svc.new_token()
    await db.commit()
    return await _one_payload(db, club, medal)


# ─── Games ───────────────────────────────────────────────────────────────────

@router.get("/games")
async def list_vote_games(
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    round_key: Optional[str] = None,
    q: Optional[str] = None,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """Played games ONE MEDAL counts, newest first, each with its voting state
    and ballot progress.

    ``grade_id`` / ``round_key`` / ``q`` narrow further. The grade and round
    option lists are built from the whole season regardless of the other
    filters, so the dropdowns never collapse to the current selection.
    """
    medal = await _resolve_or_404(db, club, medal_id)
    cfg = vote_svc.effective_config(medal)
    today = date.today()

    seasons = await vote_svc.club_seasons(db, club.id)
    if not season_id and seasons:
        season_id = seasons[0]["id"]

    rows = await vote_svc.season_games(db, club.id, season_id)
    allowed = await vote_svc.medal_grade_ids(db, club.id, medal)
    rows = [r for r in rows if vote_svc.medal_covers(allowed, r.get("grade_id"))]

    grades = sorted(
        ({"id": str(r["grade_id"]), "name": r["grade_name"]} for r in rows if r["grade_id"]),
        key=lambda g: g["name"])
    grades = list({g["id"]: g for g in grades}.values())

    rounds_seen: dict[str, tuple[str, Optional[date]]] = {}
    for r in rows:
        if grade_id and str(r.get("grade_id")) != grade_id:
            continue
        key = vote_svc.round_key_for(r)
        if key not in rounds_seen:
            rounds_seen[key] = (vote_svc.round_label_for(r), r["played_at"])
    rounds = [
        {"key": k, "label": lbl}
        for k, (lbl, d) in sorted(rounds_seen.items(),
                                  key=lambda kv: vote_svc.round_sort_key(kv[1][0], kv[1][1]),
                                  reverse=True)
    ]

    # Batch queries run over the WHOLE season, not the filtered subset, so the
    # counter strip reflects the real state whatever filter is on screen.
    gids = [r["id"] for r in rows]
    counts = await vote_svc.ballot_counts(db, club.id, gids, medal.id if medal else None)
    player_counts = await vote_svc.player_ballot_counts(db, club.id, gids, medal.id if medal else None)
    expected = await lineup_svc.lineup_counts(db, club.id, gids)
    overrides = await vote_svc.overrides_by_game(db, medal.id if medal else None, gids)

    def _row(r: dict) -> dict:
        gid = str(r["id"])
        ov = overrides.get(gid)
        voters_expected = expected.get(gid, 0)
        # A team list either exists or it doesn't — unlike cricket there is no
        # cheap-vs-live distinction to make, because it's held data.
        state = vote_svc.game_vote_state(r, cfg, ov.status if ov else None,
                                         voters_expected > 0, today)
        close = vote_svc.game_close_date(r, cfg)
        return {
            "id": gid,
            "opponent": vote_svc.game_label(r),
            "round": vote_svc.round_label_for(r),
            "round_key": vote_svc.round_key_for(r),
            "date": r["played_at"].isoformat() if r["played_at"] else None,
            "grade": r["grade_name"],
            "grade_id": str(r["grade_id"]) if r["grade_id"] else None,
            "result": r["result"],
            "state": state,
            "closes_on": close.isoformat() if close and state == "open" else None,
            "ballots": counts.get(gid, 0),
            "voters_expected": voters_expected,
            "outstanding_count": max(0, voters_expected - player_counts.get(gid, 0)),
        }

    season_rows = [_row(r) for r in rows]
    by_id = {r["id"]: r for r in season_rows}

    shown = rows
    if grade_id:
        shown = [r for r in shown if str(r.get("grade_id")) == grade_id]
    if round_key:
        shown = [r for r in shown if vote_svc.round_key_for(r) == round_key.lower()]
    if q:
        ql = q.strip().lower()
        shown = [r for r in shown if ql in vote_svc.game_label(r).lower()]

    latest_key = season_rows[0]["round_key"] if season_rows else None
    latest = [r for r in season_rows if r["round_key"] == latest_key] if latest_key else []
    summary = {
        "open": sum(1 for r in season_rows if r["state"] == "open"),
        "awaiting_team": sum(1 for r in season_rows if r["state"] == "awaiting_team"),
        "ballots_in": sum(r["ballots"] for r in latest),
        "ballots_expected": sum(r["voters_expected"] for r in latest),
        "rounds_counted": len({r["round_key"] for r in season_rows if r["ballots"] > 0}),
        "rounds_total": len({r["round_key"] for r in season_rows}),
    }

    return {
        "season_id": season_id, "seasons": seasons,
        "games": [by_id[str(r["id"])] for r in shown],
        "settings": _medal_payload(medal),
        "grades": grades, "grade_id": grade_id,
        "rounds": rounds, "round_key": round_key, "q": q,
        "summary": summary,
        "medals": await _medals_payload(db, club),
        "medal_id": str(medal.id) if medal else None,
    }


async def _org_game(db: AsyncSession, club: Organisation, game_id: str) -> dict:
    try:
        gid = uuid.UUID(game_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid game id")
    row = await vote_svc.get_game(db, club.id, gid)
    if not row:
        raise HTTPException(status_code=404, detail="Game not found")
    return row


@router.get("/games/{game_id}")
async def game_detail(
    game_id: str,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Everything about one game's vote for one medal: the votable list, every
    ballot with its picks (MANAGE_VOTES only, since this shows who voted for
    whom) and the weekly result under that medal's settings."""
    row = await _org_game(db, club, game_id)
    medal = await _resolve_or_404(db, club, medal_id)
    cfg = vote_svc.effective_config(medal)
    ov = await vote_svc.get_override(db, medal.id if medal else None, row["id"])
    eligible, unmatched = await vote_svc.eligible_players(db, club.id, row["id"])
    state = vote_svc.game_vote_state(row, cfg, ov.status if ov else None, bool(eligible))

    ballots = (await vote_svc.load_ballots_by_game(
        db, club.id, [row["id"]], medal.id if medal else None)).get(str(row["id"]), [])

    pids = {str(p.player_id) for b in ballots for p in b.picks}
    pids |= {str(b.voter_player_id) for b in ballots if b.voter_player_id}
    names = await vote_svc.player_names(db, club.id, pids)
    for p in eligible:
        names.setdefault(p["id"], p["name"])

    values = cfg["ballot_values"]
    totals = vote_svc.tally_ballots(ballots, values)
    awarded = vote_svc.award_weekly_points(totals, cfg)
    results = sorted(
        ({"player_id": pid, "name": names.get(pid, "Unknown"), "raw": t["raw"],
          "counts": t["counts"], "points": awarded.get(pid, 0)}
         for pid, t in totals.items()),
        key=lambda r: (-r["points"], -r["raw"], r["name"]))

    return {
        "game": {
            "id": str(row["id"]),
            "opponent": vote_svc.game_label(row),
            "round": vote_svc.round_label_for(row),
            "date": row["played_at"].isoformat() if row["played_at"] else None,
            "grade": row["grade_name"],
            "state": state,
            "override": ov.status if ov else None,
            "voters_expected": len(eligible),
        },
        "settings": _medal_payload(medal),
        "eligible": eligible,
        # Named on PlayHQ's team sheet but not one of our player records — a
        # fill-in, or someone the sync hasn't minted yet. Surfaced rather than
        # dropped so a short list has a visible reason.
        "unmatched": unmatched,
        "outstanding": await vote_svc.outstanding_voters(db, club.id, eligible, ballots),
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
            for b in sorted(ballots, key=lambda b: (
                b.voter_kind != "player",
                (b.voter_name or names.get(str(b.voter_player_id), "")).lower()))
        ],
        "results": results,
    }


# ─── Ballot entry / moderation ───────────────────────────────────────────────

class AdminBallot(BaseModel):
    voter_player_id: Optional[str] = None
    voter_name: Optional[str] = None
    picks: list[str]  # player ids, position 1 first


@router.post("/games/{game_id}/ballots")
async def admin_enter_ballot(
    game_id: str,
    body: AdminBallot,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Enter (or replace) a ballot on a voter's behalf — paper votes, the
    captain texting their 3-2-1 in. Deliberately looser than the public page:
    it works whatever the voting state (paper votes often arrive after close)
    and for any named voter. Picks are still restricted to who was named on the
    team sheet, and the club's self-vote rule still applies."""
    row = await _org_game(db, club, game_id)
    medal = await _medal_for_write(db, club, medal_id)
    cfg = vote_svc.effective_config(medal)
    eligible, _ = await vote_svc.eligible_players(db, club.id, row["id"])
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail="No team list for this game yet — PlayHQ hasn't given us one, or the game isn't synced")
    eligible_ids = {p["id"] for p in eligible}

    voter_pid: Optional[uuid.UUID] = None
    voter_name: Optional[str] = None
    if body.voter_player_id:
        try:
            voter_pid = uuid.UUID(body.voter_player_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid voter")
        voter = await db.get(Player, voter_pid)
        if not voter or voter.organisation_id != club.id:
            raise HTTPException(status_code=404, detail="Voter not found")
    else:
        voter_name = (body.voter_name or "").strip()[:120]
        if not voter_name:
            raise HTTPException(status_code=400, detail="Give the voter a name")

    picks = _validate_picks(body.picks, eligible_ids, len(cfg["ballot_values"]),
                            str(voter_pid) if voter_pid else None, cfg["allow_self_vote"],
                            require_full=False)

    # Scoped to the medal, matching the partial unique: entering someone's
    # Reserves votes must not overwrite the senior ballot they already gave.
    if voter_pid is not None:
        res = await db.execute(select(AflVoteBallot).where(
            AflVoteBallot.medal_id == medal.id,
            AflVoteBallot.game_id == row["id"],
            AflVoteBallot.voter_player_id == voter_pid))
    else:
        res = await db.execute(select(AflVoteBallot).where(
            AflVoteBallot.medal_id == medal.id,
            AflVoteBallot.game_id == row["id"],
            AflVoteBallot.voter_player_id.is_(None),
            func.lower(AflVoteBallot.voter_name) == voter_name.lower()))
    ballot = res.scalar_one_or_none()
    if not ballot:
        ballot = AflVoteBallot(
            id=uuid.uuid4(), organisation_id=club.id, medal_id=medal.id,
            game_id=row["id"], voter_player_id=voter_pid, voter_name=voter_name,
            voter_kind="player" if (voter_pid and str(voter_pid) in eligible_ids) else "non_player",
            source="admin", recorded_by=user.id)
        db.add(ballot)
        await db.flush()
    else:
        ballot.source = "admin"
        ballot.recorded_by = user.id
    await _replace_picks(db, ballot, picks)
    await db.commit()
    return {"status": "ok", "ballot_id": str(ballot.id)}


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
            raise HTTPException(status_code=400, detail="Votes can only go to players named for this game")
        if voter_player_id and pid == voter_player_id and not allow_self_vote:
            raise HTTPException(status_code=400, detail="Voting for yourself isn't allowed at this club")
        out.append(uuid.UUID(pid))
    return out


async def _replace_picks(db: AsyncSession, ballot: AflVoteBallot, pick_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(AflVoteBallotPick).where(AflVoteBallotPick.ballot_id == ballot.id))
    for i, pid in enumerate(pick_ids, start=1):
        db.add(AflVoteBallotPick(ballot_id=ballot.id, position=i, player_id=pid))


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
    ballot = await db.get(AflVoteBallot, bid)
    if not ballot or ballot.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Ballot not found")
    await db.delete(ballot)
    await db.commit()
    return {"status": "ok"}


# ─── Lock / reopen ───────────────────────────────────────────────────────────

async def _set_override(db: AsyncSession, club: Organisation, medal: AflVoteMedal,
                        game_id, user_id, status: str) -> None:
    res = await db.execute(select(AflVoteGameOverride).where(
        AflVoteGameOverride.medal_id == medal.id,
        AflVoteGameOverride.game_id == game_id))
    row = res.scalar_one_or_none()
    if not row:
        row = AflVoteGameOverride(medal_id=medal.id, game_id=game_id, organisation_id=club.id)
        db.add(row)
    row.status = status
    row.set_by = user_id
    await db.commit()


@router.post("/games/{game_id}/lock")
async def lock_game(
    game_id: str,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    row = await _org_game(db, club, game_id)
    medal = await _medal_for_write(db, club, medal_id)
    await _set_override(db, club, medal, row["id"], user.id, "locked")
    return {"status": "ok", "state": "locked"}


@router.post("/games/{game_id}/reopen")
async def reopen_game(
    game_id: str,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    row = await _org_game(db, club, game_id)
    medal = await _medal_for_write(db, club, medal_id)
    await _set_override(db, club, medal, row["id"], user.id, "reopened")
    return {"status": "ok", "state": "open"}


class BulkStateBody(BaseModel):
    game_ids: list[str]
    action: str  # "open" | "lock"
    medal_id: Optional[str] = None


@router.post("/bulk-state")
async def bulk_state(
    body: BulkStateBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Open or lock several games at once. A game that can't open (no team list
    yet) is reported in ``skipped`` rather than failing the whole request."""
    if body.action not in ("open", "lock"):
        raise HTTPException(status_code=400, detail="Action must be 'open' or 'lock'")
    medal = await _medal_for_write(db, club, body.medal_id)

    updated, skipped = 0, []
    for raw in body.game_ids:
        try:
            row = await _org_game(db, club, raw)
        except HTTPException:
            skipped.append({"game_id": raw, "reason": "not_found"})
            continue
        if body.action == "lock":
            await _set_override(db, club, medal, row["id"], user.id, "locked")
            updated += 1
            continue
        eligible, _ = await vote_svc.eligible_players(db, club.id, row["id"])
        if not eligible:
            skipped.append({"game_id": raw, "reason": "awaiting_team"})
            continue
        await _set_override(db, club, medal, row["id"], user.id, "reopened")
        updated += 1
    return {"updated": updated, "skipped": skipped}


# ─── Nudge ───────────────────────────────────────────────────────────────────

class NudgeBody(BaseModel):
    game_id: Optional[str] = None
    game_ids: Optional[list[str]] = None
    player_ids: Optional[list[str]] = None
    medal_id: Optional[str] = None


@router.post("/nudge")
async def nudge(
    body: NudgeBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_VOTES)),
):
    """Email the players who haven't voted yet. Rate-limited to one per player
    per game per medal per 24h — same posture as the BetterComms usage policy,
    so a manager mashing the button can't spam a player's inbox."""
    if not body.game_id and not body.game_ids:
        raise HTTPException(status_code=400, detail="Provide game_id or game_ids")
    medal = await _medal_for_write(db, club, body.medal_id)

    targets = []
    for raw in ([body.game_id] if body.game_id else list(body.game_ids or [])):
        try:
            row = await _org_game(db, club, raw)
        except HTTPException:
            continue
        eligible, _ = await vote_svc.eligible_players(db, club.id, row["id"])
        ballots = (await vote_svc.load_ballots_by_game(
            db, club.id, [row["id"]], medal.id)).get(str(row["id"]), [])
        outstanding = await vote_svc.outstanding_voters(db, club.id, eligible, ballots)
        wanted = set(body.player_ids) if (body.game_id and body.player_ids) else None
        candidates = [p for p in outstanding if wanted is None or p["id"] in wanted]
        if not candidates:
            continue
        recent = await vote_svc.recently_nudged(
            db, medal.id, row["id"], [uuid.UUID(p["id"]) for p in candidates])
        for p in candidates:
            targets.append((row, p, p["id"] in recent))

    sent, failed = 0, []
    for row, p, is_recent in targets:
        if is_recent:
            failed.append({"player_id": p["id"], "reason": "recently_nudged"})
            continue
        ok, reason = await vote_svc.send_nudge(db, club, medal, row, p, medal.link_token)
        if ok:
            sent += 1
        else:
            failed.append({"player_id": p["id"], "reason": reason})
    await db.commit()
    return {"sent": sent, "failed": failed}


# ─── The count ───────────────────────────────────────────────────────────────

@router.get("/leaderboard")
async def leaderboard(
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    through_round: Optional[str] = None,
    medal_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_any_cap(MANAGE_VOTES, VIEW_VOTE_RESULTS)),
):
    """ONE medal's count — round by round, cumulative standings through a
    chosen round (leave ``through_round`` off for the season to date). Gated
    per user via VIEW_VOTE_RESULTS, because a club keeps its B&F secret until
    presentation night."""
    medal = await _resolve_or_404(db, club, medal_id)
    cfg = vote_svc.effective_config(medal)
    seasons = await vote_svc.club_seasons(db, club.id)
    if not season_id and seasons:
        season_id = seasons[0]["id"]

    board = await vote_svc.build_leaderboard(
        db, club.id, cfg, season_id, grade_id=grade_id or None,
        through_round=through_round, medal=medal)

    # Grade options from an unfiltered pass, so they don't collapse to the
    # current selection.
    full = board if not grade_id else await vote_svc.build_leaderboard(
        db, club.id, cfg, season_id, medal=medal)
    grades: dict[str, str] = {}
    for rd in full["rounds"]:
        for g in rd["games"]:
            if g["grade_id"] and g["grade"]:
                grades[g["grade_id"]] = g["grade"]

    board["grades"] = sorted(({"id": gid, "name": n} for gid, n in grades.items()),
                             key=lambda g: g["name"])
    board["seasons"] = seasons
    board["season_id"] = season_id
    board["club_name"] = club.name
    board["club_short"] = _club_short(club.name, club.short_name)
    board["season_label"] = next((s["name"] for s in seasons if s["id"] == season_id), "")
    # "Whole club" is only honest for a medal counting every grade; one
    # restricted to its own set says so instead, since that IS its whole board.
    board["grade_name"] = (
        grades.get(grade_id) if grade_id
        else ("Whole club" if not cfg["grade_ids"] else board.get("medal_name")))
    board["grade_id"] = grade_id
    board["medals"] = await _medals_payload(db, club)
    return board


def _club_short(name: Optional[str], short_name: Optional[str]) -> str:
    if short_name:
        return short_name.strip()[:6].upper()
    initials = "".join(w[0] for w in (name or "").split()[:3]).upper()
    return initials or "FC"
