from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)

from app.models.db import Game, Grade, Season, Organisation, BattingInnings, BowlingSpell, FieldingStat, Player, get_db
from app.services.aggregations import get_game_fall_of_wickets, get_game_partnerships
from app.services import playhq_partner_client

router = APIRouter(prefix="/games", tags=["games"])


async def _enrich_scorecard_player_ids(
    scorecard: dict,
    org: Organisation,
    db: AsyncSession,
) -> None:
    """Add player_id to batting/bowling rows whose playhq_appearance_id matches a DB Player."""
    appearance_ids = set()
    for innings in (scorecard.get("innings") or []):
        for row in innings.get("batting", []) + innings.get("bowling", []):
            if row.get("playhq_appearance_id"):
                appearance_ids.add(row["playhq_appearance_id"])
    if not appearance_ids:
        return
    result = await db.execute(
        select(Player).where(
            Player.organisation_id == org.id,
            Player.playhq_id.in_(appearance_ids),
        )
    )
    playhq_to_db: dict[str, str] = {p.playhq_id: str(p.id) for p in result.scalars().all()}
    for innings in (scorecard.get("innings") or []):
        for row in innings.get("batting", []) + innings.get("bowling", []):
            phq_id = row.get("playhq_appearance_id")
            if phq_id:
                row["player_id"] = playhq_to_db.get(phq_id)


def _filter_by_season(games: list, season_obj) -> list:
    """Filter PlayHQ partner API games to those matching a DB Season.
    Tries exact name match first, falls back to year-range match so that
    cross-year seasons (e.g. Summer 2024/25 spans Oct 2024 – Mar 2025) still work.
    """
    name = (season_obj.name or "").strip().lower()
    by_name = [g for g in games if g.get("season", "").strip().lower() == name]
    if by_name:
        return by_name
    # Fallback: match by the season's start year — games played in year Y or Y+1
    year = season_obj.year
    if year:
        return [
            g for g in games
            if g.get("played_at", "")[:4] in (str(year), str(year + 1))
        ]
    return []


@router.get("")
async def list_games(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    finals_only: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if org and org.playhq_id:
        db_seasons_res = await db.execute(
            select(Season).where(Season.organisation_id == uuid.UUID(org_id))
        )
        db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
        recent = [g for g in all_games if g.get("status") == "FINAL" and g.get("played_at")]
        if season_id:
            season_obj = await db.get(Season, uuid.UUID(season_id))
            if season_obj:
                recent = _filter_by_season(recent, season_obj)
        if grade_id:
            grade_obj = await db.get(Grade, uuid.UUID(grade_id))
            if grade_obj:
                recent = [g for g in recent if (g.get("grade") or {}).get("name", "").strip().lower() == grade_obj.name.strip().lower()]
        if finals_only:
            recent = [g for g in recent if "final" in (g.get("round") or {}).get("name", "").lower()]
        recent.sort(key=lambda x: x["played_at"], reverse=True)
        return recent[:limit]

    # Fallback: DB query (empty for most installs until games are synced)
    query = (
        select(Game, Grade, Season)
        .join(Grade, Grade.id == Game.grade_id)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == uuid.UUID(org_id))
    )
    if season_id:
        query = query.where(Season.id == uuid.UUID(season_id))
    if grade_id:
        query = query.where(Grade.id == uuid.UUID(grade_id))
    if finals_only:
        query = query.where(Game.is_final == True)
    query = query.order_by(Game.played_at.desc()).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": str(game.id),
            "played_at": game.played_at.isoformat() if game.played_at else None,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "result": game.result,
            "winning_team": game.winning_team,
            "grade": {"id": str(grade.id), "name": grade.display_name, "raw_name": grade.name},
            "season": {"id": str(season.id), "name": season.name, "year": season.year},
        }
        for game, grade, season in result.all()
    ]


@router.get("/playhq/{playhq_game_id}")
async def get_playhq_game(
    playhq_game_id: str,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        raise HTTPException(status_code=404, detail="Organisation not found or no PlayHQ ID")
    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    game = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    if not game:
        logger.warning(f"PlayHQ game {playhq_game_id!r} not found in {len(all_games)} games for org {org.id}")
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("/playhq/{playhq_game_id}/scorecard/debug")
async def debug_playhq_scorecard(
    playhq_game_id: str,
    org_id: str = Query(...),
):
    """Return raw PlayHQ REST period/team structure alongside parsed innings count."""
    from app.services.playhq_partner_client import BASE_URL, _get, _parse_summary_rest
    try:
        raw = await _get(f"{BASE_URL}/v2/games/{playhq_game_id}/summary")
    except Exception as e:
        return {"error": str(e), "fixture_id": playhq_game_id, "hint": "PlayHQ API call failed — check fixture ID is a PlayHQ game ID, not an internal DB UUID"}
    data = raw.get("data") or {}
    if not data:
        return {"error": "PlayHQ returned empty data", "raw_keys": list(raw.keys()), "fixture_id": playhq_game_id}
    periods_summary = [
        {
            "name": p.get("name"),
            "teams": [
                {"id": t.get("id"), "name": t.get("name"), "discipline": t.get("discipline")}
                for t in (p.get("teams") or [])
            ],
        }
        for p in (data.get("periods") or [])
    ]
    try:
        parsed = _parse_summary_rest(data)
    except Exception as e:
        parsed = {"innings": [], "parse_error": str(e)}
    return {
        "fixture_id": playhq_game_id,
        "periods_count": len(periods_summary),
        "periods": periods_summary,
        "teams_top_level": [{"id": t.get("id"), "name": t.get("name")} for t in (data.get("teams") or [])],
        "parsed_innings_count": len(parsed.get("innings", [])),
        "parsed_innings": [
            {"innings_number": inn["innings_number"], "batting_team": inn["batting_team"], "bowling_team": inn["bowling_team"], "batting_rows": len(inn["batting"]), "bowling_rows": len(inn["bowling"])}
            for inn in parsed.get("innings", [])
        ],
        "parse_error": parsed.get("parse_error"),
    }


@router.get("/playhq/{playhq_game_id}/scorecard")
async def get_playhq_scorecard(
    playhq_game_id: str,
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org or not org.playhq_id:
        raise HTTPException(status_code=404, detail="Organisation not found or no PlayHQ ID")
    db_seasons_res = await db.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    db_seasons = [{"id": str(s.id), "name": s.name} for s in db_seasons_res.scalars().all()]
    all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name, db_seasons=db_seasons, grassroots_org_id=str(org.id))
    matched = next((g for g in all_games if str(g.get("id", "")) == playhq_game_id), None)
    game_url = matched.get("url", "") if matched else ""
    try:
        scorecard = await playhq_partner_client.get_fixture_scorecard(playhq_game_id, game_url=game_url)
        await _enrich_scorecard_player_ids(scorecard, org, db)
    except Exception as e:
        logger.warning(f"PlayHQ scorecard fetch failed for {playhq_game_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Scorecard unavailable: {e}")

    # Flatten innings-nested structure into the same shape the frontend expects
    batting_flat = []
    bowling_flat = []
    innings_totals: dict[int, dict] = {}
    for inn in (scorecard.get("innings") or []):
        n = inn.get("innings_number", 1)
        innings_totals[n] = {
            "runs": inn.get("total_runs"),
            "wickets": inn.get("total_wickets"),
            "batting_team": inn.get("batting_team", ""),
        }
        for row in (inn.get("batting") or []):
            batting_flat.append({
                "innings_number": n,
                "player_id": row.get("player_id"),
                "player_name": row.get("name"),
                "runs": row.get("runs"),
                "balls": row.get("balls"),
                "fours": row.get("fours"),
                "sixes": row.get("sixes"),
                "strike_rate": row.get("strike_rate"),
                "dismissal_type": row.get("how_out"),
                "not_out": row.get("not_out", False),
            })
        for row in (inn.get("bowling") or []):
            bowling_flat.append({
                "innings_number": n,
                "player_id": row.get("player_id"),
                "player_name": row.get("name"),
                "overs": row.get("overs"),
                "maidens": row.get("maidens"),
                "runs": row.get("runs"),
                "wickets": row.get("wickets"),
                "wides": row.get("wides"),
                "no_balls": row.get("no_balls"),
                "economy": row.get("economy"),
            })

    meta = matched or {}
    return {
        "id": playhq_game_id,
        "home_team": meta.get("home_team"),
        "away_team": meta.get("away_team"),
        "played_at": meta.get("played_at"),
        "result": meta.get("result"),
        "winning_team": meta.get("winning_team"),
        "grade": meta.get("grade"),
        "season": meta.get("season"),
        "innings_totals": innings_totals,
        "batting": batting_flat,
        "bowling": bowling_flat,
        "fielding": [],
        "fall_of_wickets": scorecard.get("fall_of_wickets") or [],
        "partnerships": scorecard.get("partnerships") or [],
    }


@router.get("/{game_id}/scorecard/gr-debug")
async def debug_gr_scorecard(game_id: str):
    """Return raw GR scorecard JSON for field-name inspection. Dev use only."""
    from app.services.grassroots_scores_client import get_match_scorecard
    data = await get_match_scorecard(game_id)
    if data is None:
        return {"status": "204_or_error", "game_id": game_id}
    innings = data.get("innings") or []
    sample = {}
    for inn in innings:
        batting = inn.get("batting") or []
        if batting and "first_batting_row_keys" not in sample:
            sample["first_batting_row_keys"] = list(batting[0].keys())
            sample["first_batting_row"] = batting[0]
        bowling = inn.get("bowling") or []
        if bowling and "first_bowling_row_keys" not in sample:
            sample["first_bowling_row_keys"] = list(bowling[0].keys())
            sample["first_bowling_row"] = bowling[0]
    # Expose all innings-level keys (minus batting/bowling/fielding arrays)
    sample["innings_objects"] = [
        {k: v for k, v in inn.items() if k not in ("batting", "bowling", "fielding", "fallOfWickets")}
        for inn in innings
    ]
    teams = data.get("teams") or []
    sample["teams_keys"] = [list(t.keys()) for t in teams]
    sample["teams_count"] = len(teams)
    sample["innings_count"] = len(innings)
    sample["top_level_keys"] = list(data.keys())
    match_summary = data.get("matchSummary") or {}
    sample["match_summary_keys"] = list(match_summary.keys())
    sample["match_summary_teams"] = match_summary.get("teams") or []
    # Full team rosters: players + nonPlayingMembers per team
    sample["team_rosters"] = []
    for t in teams:
        t_name = t.get("displayName") or t.get("name") or ""
        members = []
        for p in (t.get("players") or []):
            members.append({
                "type": "player",
                "participantId": p.get("participantId") or p.get("id"),
                "playerShortName": p.get("playerShortName") or p.get("displayName") or p.get("name"),
            })
        for p in (t.get("nonPlayingMembers") or []):
            members.append({
                "type": "nonPlaying",
                "participantId": p.get("participantId") or p.get("id"),
                "playerShortName": p.get("playerShortName") or p.get("displayName") or p.get("name"),
            })
        sample["team_rosters"].append({"team": t_name, "members": members})
    return sample


@router.get("/{game_id}/scorecard")
async def get_scorecard(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    game = await db.get(Game, uuid.UUID(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    grade = await db.get(Grade, game.grade_id) if game.grade_id else None
    season = await db.get(Season, grade.season_id) if grade else None

    # Batting with player names via join
    batting_res = await db.execute(
        select(BattingInnings, Player)
        .outerjoin(Player, Player.id == BattingInnings.player_id)
        .where(BattingInnings.game_id == game.id)
        .order_by(BattingInnings.innings_number, BattingInnings.batting_position)
    )
    batting_rows = batting_res.all()

    # Bowling with player names via join
    bowling_res = await db.execute(
        select(BowlingSpell, Player)
        .outerjoin(Player, Player.id == BowlingSpell.player_id)
        .where(BowlingSpell.game_id == game.id)
        .order_by(BowlingSpell.innings_number)
    )
    bowling_rows = bowling_res.all()

    # Fielding with player names via join
    fielding_res = await db.execute(
        select(FieldingStat, Player)
        .outerjoin(Player, Player.id == FieldingStat.player_id)
        .where(FieldingStat.game_id == game.id)
    )
    fielding_rows = fielding_res.all()

    # Build innings summary map (totals per innings)
    innings_meta: dict[int, dict] = {}
    for bi, p in batting_rows:
        n = bi.innings_number or 1
        if n not in innings_meta:
            innings_meta[n] = {"batting_team": None, "bowling_team": None}

    batting_flat = [
        {
            "innings_number": bi.innings_number or 1,
            "player_id": str(bi.player_id) if bi.player_id else None,
            "player_name": p.display_name if p else None,
            "runs": bi.runs,
            "balls": bi.balls,
            "fours": bi.fours,
            "sixes": bi.sixes,
            "strike_rate": float(bi.strike_rate) if bi.strike_rate is not None else None,
            "dismissal_type": bi.dismissal_type,
            "not_out": bi.not_out,
            "batting_position": bi.batting_position,
            "did_not_bat": bool(bi.did_not_bat),
        }
        for bi, p in batting_rows
    ]

    bowling_flat = [
        {
            "innings_number": bs.innings_number or 1,
            "player_id": str(bs.player_id) if bs.player_id else None,
            "player_name": p.display_name if p else None,
            "overs": float(bs.overs) if bs.overs is not None else None,
            "maidens": bs.maidens,
            "runs": bs.runs,
            "wickets": bs.wickets,
            "wides": bs.wides,
            "no_balls": bs.no_balls,
            "economy": float(bs.economy) if bs.economy is not None else None,
        }
        for bs, p in bowling_rows
    ]

    fielding_flat = [
        {
            "player_id": str(fs.player_id) if fs.player_id else None,
            "player_name": p.display_name if p else None,
            "catches": fs.catches,
            "run_outs": fs.run_outs,
            "stumpings": fs.stumpings,
        }
        for fs, p in fielding_rows
        if (fs.catches or 0) + (fs.run_outs or 0) + (fs.stumpings or 0) > 0
    ]

    # Derive innings totals from batting data for the summary strip
    innings_totals: dict[int, dict] = {}
    for row in batting_flat:
        if row["did_not_bat"]:
            continue
        n = row["innings_number"]
        if n not in innings_totals:
            innings_totals[n] = {"runs": 0, "wickets": 0, "extras": 0, "team": None}
        innings_totals[n]["runs"] += row["runs"] or 0
        if not row["not_out"] and row["dismissal_type"]:
            innings_totals[n]["wickets"] += 1

    # Add extras (wides + no-balls) from bowling per innings
    for row in bowling_flat:
        n = row["innings_number"]
        if n not in innings_totals:
            innings_totals[n] = {"runs": 0, "wickets": 0, "extras": 0, "team": None}
        innings_totals[n].setdefault("extras", 0)
        innings_totals[n]["extras"] += (row["wides"] or 0) + (row["no_balls"] or 0)

    fow = await get_game_fall_of_wickets(db, game.id)
    partnerships = await get_game_partnerships(db, game.id)

    # Live-fetch opposition data from GR API (not stored in DB).
    # game.id IS the GR match UUID, so we can call directly.
    opp_batting: list[dict] = []
    opp_bowling: list[dict] = []
    opp_extras: dict[int, int] = {}

    try:
        from app.services.grassroots_scores_client import get_match_scorecard
        import re as _re
        gr_data = await get_match_scorecard(str(game.id))
        if gr_data:
            if season:
                pid_res = await db.execute(
                    select(Player.id).where(Player.organisation_id == season.organisation_id)
                )
                known_ids: set = {r[0] for r in pid_res}
            else:
                known_ids = set()

            # Player IDs already in DB batting data for this game.
            db_batting_pids: set = {
                uuid.UUID(r["player_id"]) for r in batting_flat if r["player_id"]
            }

            _DNB = {"absent", "did not bat", "dnb"}

            # Match on (surname, first_initial) — handles "Baker, Daniel" (DB format)
            # vs "D Baker" (GR playerShortName). Sorted-word approach fails because
            # "baker daniel" != "baker d".
            def _name_key(n: str) -> tuple[str, str]:
                n = (n or "").strip()
                if "," in n:
                    parts = n.split(",", 1)
                    surname = parts[0].strip().lower()
                    first = parts[1].strip()
                    return (surname, first[0].lower() if first else "")
                words = n.split()
                if not words:
                    return ("", "")
                return (words[-1].lower(), words[0][0].lower() if words[0] else "")

            our_batting_fingerprints: set[tuple[str, str]] = {
                _name_key(r["player_name"]) for r in batting_flat if r.get("player_name")
            }

            # Org name first word — identifies which GR team is ours vs opposition.
            org_obj = await db.get(Organisation, season.organisation_id) if season else None
            org_word = (org_obj.name or "").lower().split()[0] if org_obj and org_obj.name else ""

            # GR confirmed fields (via /scorecard/gr-debug):
            #   teams[]: players[], nonPlayingMembers[], id, displayName, name, owningOrganisation
            #   batting rows: participantId, playerShortName, batOrder, batInstance,
            #                 ballsFaced, foursScored, sixesScored, runsScored, battingMinutes,
            #                 strikeRate, dismissalTypeId, dismissalType, dismissalText,
            #                 isOnStrike, isOnNonStrike, highlight

            # Build pid→shortName map from both playing and non-playing members.
            # Track opp roster pids (players + non-playing = DNB candidates).
            # Also track our team roster pids for the same reason.
            pid_to_name: dict[str, str] = {}
            opp_roster_pids: set[str] = set()
            our_team_roster_pids: set[str] = set()
            for _team in (gr_data.get("teams") or []):
                _team_name = (_team.get("displayName") or _team.get("name") or "").lower()
                _is_our_team = bool(org_word and org_word in _team_name)
                _all_members = (_team.get("players") or []) + (_team.get("nonPlayingMembers") or [])
                for _pl in _all_members:
                    _pid = _pl.get("participantId") or _pl.get("id")
                    _name = (_pl.get("playerShortName") or _pl.get("displayName") or
                             _pl.get("name") or "")
                    if _pid and _name:
                        pid_to_name[_pid] = _name
                    if _is_our_team and _pid:
                        our_team_roster_pids.add(_pid)
                    elif not _is_our_team and _pid:
                        opp_roster_pids.add(_pid)

            # Accumulate our own DNB players missing from DB (pre-migration games).
            our_missing_dnb: dict[uuid.UUID, tuple[int, int | None]] = {}
            # GR-sourced dismissal text for our players (enriches batting_flat after loop).
            # Keyed by GR UUID (for players whose DB uuid matches GR).
            our_dismissal_text: dict[uuid.UUID, str] = {}
            # Keyed by name key (surname, initial) — covers players whose DB uuid is a PlayHQ
            # uuid that doesn't match GR's uuid, e.g. Daniel Baker.
            our_dismissal_text_by_name: dict[tuple, str] = {}

            # Track opp pids seen in innings (incl. DNB) and which inn nums opp batted in.
            opp_all_batting_pids: set[str] = set()
            opp_batting_inn_nums: set[int] = set()
            # Track our pids seen batting in GR innings (to avoid re-adding as DNB).
            our_batting_pids_seen_in_gr: set[uuid.UUID] = set()
            # Authoritative innings totals from GR innings objects.
            # Fields confirmed: runsScored, numberOfWicketsFallen, totalExtras,
            #                   byesRuns, legByesRuns, wideBalls, noBalls, penalties
            gr_inn_totals: dict[int, dict] = {}

            for inn in (gr_data.get("innings") or []):
                inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1

                # Capture authoritative innings totals directly from GR.
                # totalExtras covers byes/leg-byes/penalties not on bowling rows.
                gr_inn_totals[inn_num] = {
                    "runs": inn.get("runsScored"),
                    "wickets": inn.get("numberOfWicketsFallen"),
                    "extras": inn.get("totalExtras"),
                    "batting_team_id": inn.get("battingTeamId"),
                }

                for row in (inn.get("batting") or []):
                    pid_str = row.get("participantId")
                    if not pid_str:
                        continue
                    try:
                        pid = uuid.UUID(pid_str)
                    except ValueError:
                        continue

                    if pid in known_ids:
                        our_batting_pids_seen_in_gr.add(pid)
                        dt_text = row.get("dismissalText")
                        if dt_text:
                            our_dismissal_text[pid] = dt_text
                        if pid not in db_batting_pids:
                            dt_id_o = row.get("dismissalTypeId") or 0
                            dt_long_o = (row.get("dismissalType") or "").lower()
                            if dt_id_o != 0 and dt_long_o in _DNB:
                                our_missing_dnb[pid] = (inn_num, row.get("batOrder"))
                        continue

                    dt_id = row.get("dismissalTypeId") or 0
                    dt_long = row.get("dismissalType") or ""
                    is_dnb = dt_long.lower() in _DNB
                    if dt_id == 0 and not is_dnb:
                        continue

                    # playerShortName is on each batting row (confirmed by gr-debug).
                    name = row.get("playerShortName") or pid_to_name.get(pid_str, "Unknown")
                    nk = _name_key(name)
                    if nk in our_batting_fingerprints:
                        # Still capture dismissal — this player is ours but has a GR UUID that
                        # doesn't match their DB PlayHQ UUID (uuid-namespace mismatch).
                        dt_text = row.get("dismissalText")
                        if dt_text and (row.get("dismissalType") or "").lower() not in _DNB:
                            our_dismissal_text_by_name[nk] = dt_text
                        continue

                    # Player is in our team's GR roster but UUID doesn't match DB —
                    # the our_team_roster_pids injection below will handle them as DNB.
                    # Don't add to opp_batting to avoid duplication.
                    if pid_str in our_team_roster_pids:
                        continue

                    # dismissalText is pre-formatted: "c S Aplin b W Dagg", "b W Dagg", etc.
                    dismissal_str = None if is_dnb else (
                        row.get("dismissalText") or dt_long.lower() or None
                    )

                    opp_all_batting_pids.add(pid_str)
                    if not is_dnb:
                        opp_batting_inn_nums.add(inn_num)
                    opp_batting.append({
                        "innings_number": inn_num,
                        "player_id": None,
                        "player_name": name,
                        "runs": None if is_dnb else (row.get("runsScored") or 0),
                        "balls": None if is_dnb else (row.get("ballsFaced") or 0),
                        "fours": None if is_dnb else (row.get("foursScored") or 0),
                        "sixes": None if is_dnb else (row.get("sixesScored") or 0),
                        "dismissal_type": dismissal_str,
                        "not_out": dt_id == 1,
                        "did_not_bat": is_dnb,
                        "batting_position": row.get("batOrder"),
                    })

                for row in (inn.get("bowling") or []):
                    pid_str = row.get("participantId")
                    if not pid_str:
                        continue
                    try:
                        pid = uuid.UUID(pid_str)
                    except ValueError:
                        continue
                    if pid in known_ids:
                        continue
                    name = pid_to_name.get(pid_str, "Unknown")
                    if _name_key(name) in our_batting_fingerprints:
                        continue
                    econ = None
                    try:
                        econ_raw = row.get("economy")
                        econ = float(econ_raw) if econ_raw is not None else None
                    except (TypeError, ValueError):
                        pass
                    opp_bowling.append({
                        "innings_number": inn_num,
                        "player_id": None,
                        "player_name": name,
                        "overs": row.get("oversBowled"),
                        "maidens": row.get("maidensBowled"),
                        "runs": row.get("runsConceded"),
                        "wickets": row.get("wicketsTaken"),
                        "wides": row.get("wideBalls"),
                        "no_balls": row.get("noBalls"),
                        "economy": econ,
                    })
                    # Try both GR field-name variants (wideBalls confirmed in sync.py; widesScored as fallback)
                    _w = (row.get("wideBalls") or row.get("widesScored") or row.get("wides") or 0)
                    _nb = (row.get("noBalls") or row.get("noBallsScored") or row.get("noBallsBowled") or 0)
                    opp_extras[inn_num] = opp_extras.get(inn_num, 0) + _w + _nb

            # Enrich our batting_flat with GR dismissal text (e.g. "c K Verdonk b W Dagg").
            if our_dismissal_text or our_dismissal_text_by_name:
                for bf_row in batting_flat:
                    if bf_row.get("did_not_bat"):
                        continue
                    enriched = False
                    # Primary: GR UUID matches DB UUID exactly.
                    if bf_row.get("player_id") and our_dismissal_text:
                        try:
                            bf_pid = uuid.UUID(bf_row["player_id"])
                            if bf_pid in our_dismissal_text:
                                bf_row["dismissal_type"] = our_dismissal_text[bf_pid]
                                enriched = True
                        except (ValueError, KeyError):
                            pass
                    # Fallback: name-key match for PlayHQ-uuid-vs-GR-uuid mismatch players.
                    if not enriched and our_dismissal_text_by_name and bf_row.get("player_name"):
                        nk = _name_key(bf_row["player_name"])
                        if nk in our_dismissal_text_by_name:
                            bf_row["dismissal_type"] = our_dismissal_text_by_name[nk]

            # Inject DNB rows for our own roster members absent from innings batting.
            # Covers players who only appear in teams[].nonPlayingMembers[] (not in batting array).
            if our_team_roster_pids:
                _our_inn = min(
                    (r["innings_number"] for r in batting_flat if not r.get("did_not_bat")),
                    default=1,
                )
                _unresolved_roster_pids: list[str] = []
                for ros_pid_str in our_team_roster_pids:
                    try:
                        ros_pid = uuid.UUID(ros_pid_str)
                    except ValueError:
                        continue
                    if ros_pid in db_batting_pids:
                        continue
                    if ros_pid in our_batting_pids_seen_in_gr:
                        continue
                    if ros_pid in our_missing_dnb:
                        continue
                    if not pid_to_name.get(ros_pid_str):
                        continue
                    if ros_pid in known_ids:
                        our_missing_dnb[ros_pid] = (_our_inn, None)
                    else:
                        # UUID mismatch (PlayHQ ID in DB vs GR UUID) — resolve by name
                        _unresolved_roster_pids.append(ros_pid_str)

                # Name-based lookup for UUID-mismatched roster members.
                if _unresolved_roster_pids and season:
                    _all_res = await db.execute(
                        select(Player).where(Player.organisation_id == season.organisation_id)
                    )
                    _nk_to_player: dict[tuple, Player] = {}
                    for _pl in _all_res.scalars().all():
                        _nk_to_player[_name_key(_pl.display_name)] = _pl
                    for _ros_str in _unresolved_roster_pids:
                        _ros_name = pid_to_name.get(_ros_str, "")
                        if not _ros_name:
                            continue
                        _nk = _name_key(_ros_name)
                        if _nk in our_batting_fingerprints:
                            continue  # they batted, not a DNB
                        _matched = _nk_to_player.get(_nk)
                        if not _matched or _matched.id in db_batting_pids or _matched.id in our_missing_dnb:
                            continue
                        our_missing_dnb[_matched.id] = (_our_inn, None)

            # Inject DNB rows for opp roster/non-playing members absent from innings batting.
            # GR includes nonPlayingMembers in teams[] — covers Oscar Brown / Sachin Dhadli style cases.
            if opp_roster_pids and opp_batting_inn_nums:
                opp_dnb_inn = min(opp_batting_inn_nums)
                for dnb_pid_str in opp_roster_pids:
                    if dnb_pid_str in opp_all_batting_pids:
                        continue
                    try:
                        dnb_pid = uuid.UUID(dnb_pid_str)
                    except ValueError:
                        continue
                    if dnb_pid in known_ids:
                        continue
                    dnb_name = pid_to_name.get(dnb_pid_str, "")
                    if not dnb_name:
                        continue
                    opp_batting.append({
                        "innings_number": opp_dnb_inn,
                        "player_id": None,
                        "player_name": dnb_name,
                        "runs": None, "balls": None, "fours": None, "sixes": None,
                        "dismissal_type": None, "not_out": False,
                        "batting_position": None, "did_not_bat": True,
                    })

            # Append our own DNB players missing from DB (pre-migration games).
            if our_missing_dnb:
                dnb_player_res = await db.execute(
                    select(Player).where(Player.id.in_(our_missing_dnb.keys()))
                )
                dnb_player_map = {p.id: p for p in dnb_player_res.scalars().all()}
                for dnb_pid, (dnb_inn, dnb_order) in our_missing_dnb.items():
                    dnb_player = dnb_player_map.get(dnb_pid)
                    batting_flat.append({
                        "innings_number": dnb_inn,
                        "player_id": str(dnb_pid),
                        "player_name": dnb_player.display_name if dnb_player else None,
                        "runs": None, "balls": None, "fours": None, "sixes": None,
                        "strike_rate": None, "dismissal_type": None, "not_out": False,
                        "batting_position": dnb_order, "did_not_bat": True,
                    })

            # Compute opp batting totals per innings (runs+wickets) so the frontend
            # can display the correct score in the opp batting card header.
            opp_inn_totals: dict[int, dict] = {}
            for r in opp_batting:
                n = r["innings_number"]
                if n not in opp_inn_totals:
                    opp_inn_totals[n] = {"runs": 0, "wickets": 0}
                if not r["did_not_bat"] and r["runs"] is not None:
                    opp_inn_totals[n]["runs"] += r["runs"]
                if not r["did_not_bat"] and not r.get("not_out") and r.get("dismissal_type"):
                    opp_inn_totals[n]["wickets"] += 1

            # Populate batting_team in innings_totals from GR summary teams
            summary_teams = (gr_data.get("matchSummary") or {}).get("teams") or []
            home_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is True), "") or game.home_team or ""
            away_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is False), "") or game.away_team or ""

            we_are_home = bool(org_word and game.home_team and org_word in game.home_team.lower())
            our_display_name = home_name if we_are_home else away_name
            opp_display_name = away_name if we_are_home else home_name

            our_batting_inns = {r["innings_number"] for r in batting_flat if not r["did_not_bat"]}
            for inn_num_t in set(list(innings_totals.keys()) + [r["innings_number"] for r in opp_batting]):
                if inn_num_t not in innings_totals:
                    innings_totals[inn_num_t] = {"runs": 0, "wickets": 0, "extras": 0}
                # For opp batting innings, overwrite runs/wickets with actual totals
                if inn_num_t not in our_batting_inns and inn_num_t in opp_inn_totals:
                    innings_totals[inn_num_t]["runs"] = opp_inn_totals[inn_num_t]["runs"]
                    innings_totals[inn_num_t]["wickets"] = opp_inn_totals[inn_num_t]["wickets"]
                if inn_num_t in our_batting_inns:
                    innings_totals[inn_num_t]["batting_team"] = our_display_name or game.home_team or ""
                else:
                    innings_totals[inn_num_t]["batting_team"] = opp_display_name or game.away_team or ""
                # Use GR innings-level totalExtras as authoritative source.
                # This covers byes, leg-byes, penalties and avoids the per-bowler
                # field-name uncertainty. Applies to both our and opp innings.
                if inn_num_t in gr_inn_totals:
                    _gr = gr_inn_totals[inn_num_t]
                    if _gr.get("extras") is not None:
                        innings_totals[inn_num_t]["extras"] = _gr["extras"]
                    # For opp innings, GR wicket count is more reliable than counting
                    # dismissal strings (which can vary based on dismissal text parsing).
                    if inn_num_t not in our_batting_inns and _gr.get("wickets") is not None:
                        innings_totals[inn_num_t]["wickets"] = _gr["wickets"]

    except Exception as e:
        import traceback
        logger.error(f"get_scorecard: GR live-fetch failed for {game_id}: {e}\n{traceback.format_exc()}")

    return {
        "id": str(game.id),
        "home_team": game.home_team,
        "away_team": game.away_team,
        "played_at": game.played_at.isoformat() if game.played_at else None,
        "result": game.result,
        "winning_team": game.winning_team,
        "grade": {"id": str(grade.id), "name": grade.display_name, "raw_name": grade.name} if grade else None,
        "season": {"id": str(season.id), "name": season.name} if season else None,
        "innings_totals": innings_totals,
        "batting": batting_flat,
        "bowling": bowling_flat,
        "opp_batting": opp_batting,
        "opp_bowling": opp_bowling,
        "fielding": fielding_flat,
        "fall_of_wickets": fow,
        "partnerships": partnerships,
    }
