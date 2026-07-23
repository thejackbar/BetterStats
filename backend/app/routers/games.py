from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)

from app.models.db import Game, Grade, Season, Organisation, BattingInnings, BowlingSpell, FieldingStat, Player, ManualGame, ManualBattingInnings, ManualBowlingSpell, ManualFieldingStat, get_db
from app.services.aggregations import get_game_fall_of_wickets, get_game_partnerships
from app.services.sync import _caught_by_keeper, _innings_keeper_names

router = APIRouter(prefix="/games", tags=["games"])


async def _fetch_manual_games_as_list(
    db: AsyncSession,
    org_id: uuid.UUID,
    season_id: Optional[str],
    grade_id: Optional[str],
    finals_only: Optional[bool],
) -> list[dict]:
    """Return manual_games for this org shaped like the API game-list entries."""
    q = (
        select(ManualGame, Grade, Season)
        .join(Season, Season.id == ManualGame.season_id)
        .outerjoin(Grade, Grade.id == ManualGame.grade_id)
        .where(ManualGame.organisation_id == org_id)
    )
    if season_id:
        q = q.where(ManualGame.season_id == uuid.UUID(season_id))
    if grade_id:
        q = q.where(ManualGame.grade_id == uuid.UUID(grade_id))
    if finals_only:
        q = q.where(ManualGame.is_final.is_(True))
    rows = await db.execute(q)
    out = []
    for game, grade, season in rows.all():
        out.append({
            "id": str(game.id),
            "played_at": game.played_at.isoformat() if game.played_at else None,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "result": game.result,
            "winning_team": game.winning_team,
            "grade": ({"id": str(grade.id), "name": grade.display_name, "raw_name": grade.name}
                      if grade else {"id": None, "name": "(manual)", "raw_name": "(manual)"}),
            "season": {"id": str(season.id), "name": season.name, "year": season.year},
            "is_manual": True,
        })
    return out


@router.get("")
async def list_games(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    finals_only: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    manual_games = await _fetch_manual_games_as_list(
        db, uuid.UUID(org_id), season_id, grade_id, finals_only,
    )

    # Recent games come from our own synced data (DB-first). Manual games are
    # NOT part of this query — they're already fetched above by
    # _fetch_manual_games_as_list (correctly org-scoped off
    # ManualGame.organisation_id) and merged in below. This query used to also
    # match `g.source = 'manual'` with no organisation check at all, which (a)
    # leaked every OTHER club's manual games in here too, and (b) duplicated
    # this club's own manual games (once from this query via
    # v_effective_games, once from _fetch_manual_games_as_list) — fixed by
    # restricting this query to `g.source = 'api'` (see migration 169).
    # An API-synced game is ours if we're recorded as home_org_id/away_org_id
    # on the row (the reliable per-club signal for a shared games.id row
    # between two both-synced clubs, set at sync time — see migration 167),
    # or the game's own grade belongs to our org, or one of our own players
    # has a recorded appearance in it — the same rule get_org_results uses,
    # since a shared grade can hold other clubs' games under a grade_id that
    # belongs to whichever club synced it first. grades/seasons are LEFT
    # JOINed (not INNER) so a shared game under a foreign grade_id still
    # returns a row; a season_id/grade_id filter then matches via
    # grassroots_id (the raw CA guid shared across every club's per-club
    # grade/season rows for the same real grade/season) so it still finds a
    # shared game physically attached to the OTHER club's grade row. Matching
    # the org's name against the free-text home_team/away_team CA supplies
    # used to silently drop every game for a club whose CA-recorded team text
    # doesn't literally contain the org's first name-token.
    clauses = [
        """(
            g.source = 'api'
            AND (
                g.home_org_id = CAST(:org_id AS UUID)
                OR g.away_org_id = CAST(:org_id AS UUID)
                OR s.organisation_id = CAST(:org_id AS UUID)
                OR EXISTS (
                    SELECT 1 FROM game_appearances ga
                    JOIN players p ON p.id = ga.player_id
                    WHERE ga.game_id = g.id AND p.organisation_id = CAST(:org_id AS UUID)
                )
            )
        )""",
    ]
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        clauses.append("""(
            s.id = CAST(:season_id AS UUID)
            OR (s.grassroots_id IS NOT NULL AND s.grassroots_id = (
                SELECT grassroots_id FROM seasons WHERE id = CAST(:season_id AS UUID)
            ))
        )""")
        params["season_id"] = season_id
    if grade_id:
        clauses.append("""(
            gr.id = CAST(:grade_id AS UUID)
            OR (gr.grassroots_id IS NOT NULL AND gr.grassroots_id = (
                SELECT grassroots_id FROM grades WHERE id = CAST(:grade_id AS UUID)
            ))
        )""")
        params["grade_id"] = grade_id
    if finals_only:
        clauses.append("g.is_final = TRUE")

    # g.result is ALSO relative to whichever club's sync wrote it first
    # (classify_match_result computes it against that syncing org's own
    # team) — the same single-column-can't-hold-two-perspectives issue
    # opp_org_id had. g.winning_team is the actual winning team's name
    # (neutral, not org-relative), so it's re-derived here against OUR
    # home/away side instead of trusted as stored — falling back to the raw
    # g.result when winning_team is NULL (a symmetric draw/tie/no-result, or
    # a row where home_org_id/away_org_id can't place either side).
    result = await db.execute(
        text(f"""
            SELECT g.id, g.played_at, g.home_team, g.away_team,
                   CASE
                       WHEN g.winning_team IS NULL THEN g.result
                       WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
                       WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
                       WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
                       WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
                       ELSE g.result
                   END AS result,
                   g.winning_team,
                   gr.id AS grade_id, COALESCE(gr.display_name_override, gr.name) AS grade_name,
                   gr.name AS grade_raw,
                   s.id AS season_id, s.name AS season_name, s.year AS season_year
            FROM v_effective_games g
            LEFT JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN seasons s ON s.id = gr.season_id
            WHERE {' AND '.join(clauses)}
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    api_games = [
        {
            "id": str(r.id),
            "played_at": r.played_at.isoformat() if r.played_at else None,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "result": r.result,
            "winning_team": r.winning_team,
            "grade": {"id": str(r.grade_id) if r.grade_id else None, "name": r.grade_name, "raw_name": r.grade_raw},
            "season": {"id": str(r.season_id) if r.season_id else None, "name": r.season_name, "year": r.season_year},
        }
        for r in result
    ]
    combined = api_games + manual_games
    combined.sort(key=lambda x: x.get("played_at") or "", reverse=True)
    return combined[:limit]


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


def _to_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _looks_redacted(name: Optional[str]) -> bool:
    """True for a name that carries no real information — blank, or CA's
    literal asterisk-redaction placeholder for a privacy-protected participant."""
    cleaned = (name or "").strip()
    return not cleaned or set(cleaned) == {"*"}


def _classify_unlinked_name(raw_name: Optional[str], batting_position=None) -> tuple[str, bool, bool]:
    """Classify a player row with no resolvable `players` id.

    Two situations look identical at the code level (no linkable player) but
    read very differently to a club: a genuine fill-in (a borrowed player —
    GR gives their real name, just not one of ours) keeps that name and gets
    a FILL-IN badge; a CA-redacted participant (junior privacy protection —
    GR's `playerShortName` comes back as a literal string of asterisks, no
    real name recoverable anywhere in the feed) shows as "********" as-is —
    the convention clubs already recognise — with no badge, since "Fill-In"
    would misrepresent an unknown identity as a known-but-unregistered one.

    Returns (display_name, is_fill_in, is_redacted).
    """
    cleaned = (raw_name or "").strip()
    if not cleaned or set(cleaned) == {"*"}:
        return "********", False, True
    if cleaned.lower() == "unknown":
        return (f"Fill-In (#{batting_position})" if batting_position else "Fill-In"), True, False
    return cleaned, True, False


async def _gr_scorecard_response(game_id: str) -> Optional[dict]:
    """Full both-teams scorecard for a live / not-yet-synced match, built directly
    from Grassroots. Returns None when GR has nothing for this id (truly unknown).

    Same response shape as the DB path (get_scorecard) so the frontend renders it
    identically — DB-first, Grassroots only when we don't hold the match.
    """
    from app.services.grassroots_scores_client import get_match_scorecard
    gr = await get_match_scorecard(game_id)
    if not gr:
        return None

    teams = gr.get("teams") or []
    team_name: dict[str, str] = {}
    home_team = away_team = None
    for t in teams:
        tid = (t.get("id") or "").lower()
        nm = t.get("displayName") or t.get("name")
        if tid:
            team_name[tid] = nm
        if t.get("isHome"):
            home_team = nm
        else:
            away_team = nm

    played_at = None
    for sched in (gr.get("matchSchedule") or []):
        iso = sched.get("startDateTime") or ""
        if iso:
            played_at = iso[:10]
            break
    grade = gr.get("grade") or {}
    _DNB = {"absent", "did not bat", "dnb"}

    batting: list[dict] = []
    bowling: list[dict] = []
    fow: list[dict] = []
    innings_totals: dict[int, dict] = {}
    for inn in (gr.get("innings") or []):
        inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
        keeper_names = _innings_keeper_names(inn.get("fielding") or [])
        bt_id = str(inn.get("battingTeamId") or "").lower()
        innings_totals[inn_num] = {
            "runs": inn.get("runsScored"),
            "wickets": inn.get("numberOfWicketsFallen"),
            "extras": inn.get("totalExtras"),
            "batting_team": team_name.get(bt_id),
        }
        for row in (inn.get("batting") or []):
            dt_id = row.get("dismissalTypeId") or 0
            dt_long = row.get("dismissalType") or ""
            is_dnb = dt_long.lower() in _DNB
            if dt_id == 0 and not is_dnb:
                continue
            batting.append({
                "innings_number": inn_num,
                "player_id": None,
                "player_name": row.get("playerShortName") or "Unknown",
                "runs": None if is_dnb else (row.get("runsScored") or 0),
                "balls": None if is_dnb else (row.get("ballsFaced") or 0),
                "fours": None if is_dnb else (row.get("foursScored") or 0),
                "sixes": None if is_dnb else (row.get("sixesScored") or 0),
                "strike_rate": _to_float(row.get("strikeRate")),
                "dismissal_type": None if is_dnb else (row.get("dismissalText") or dt_long.lower() or None),
                "caught_behind": dt_long == "Caught" and _caught_by_keeper(row.get("dismissalText") or "", keeper_names),
                "not_out": dt_id == 1,
                "did_not_bat": is_dnb,
                "batting_position": row.get("batOrder"),
            })
        for row in (inn.get("bowling") or []):
            bowling.append({
                "innings_number": inn_num,
                "player_id": None,
                "player_name": row.get("playerShortName") or "Unknown",
                "overs": row.get("oversBowled"),
                "maidens": row.get("maidensBowled"),
                "runs": row.get("runsConceded"),
                "wickets": row.get("wicketsTaken"),
                "wides": row.get("wideBalls"),
                "no_balls": row.get("noBalls"),
                "economy": _to_float(row.get("economy")),
            })
        for row in (inn.get("fallOfWickets") or []):
            wkt = row.get("order")
            if wkt is None:
                continue
            fow.append({
                "innings_number": inn_num,
                "wicket_number": wkt,
                "score_at_fall": row.get("runs"),
                "overs_at_fall": None,
                "player_name": row.get("playerShortName"),
                "player_id": None,
            })

    return {
        "id": game_id,
        "home_team": home_team,
        "away_team": away_team,
        "played_at": played_at,
        "result": None,
        "winning_team": None,
        "result_text": (gr.get("matchSummary") or {}).get("resultText"),
        "grade": {"id": grade.get("id"), "name": grade.get("name"), "raw_name": grade.get("name")} if grade.get("id") else None,
        "season": None,
        "innings_totals": innings_totals,
        "batting": batting,
        "bowling": bowling,
        "opp_batting": [],
        "opp_bowling": [],
        "fielding": [],
        "fall_of_wickets": fow,
        "partnerships": [],
        "live": True,
    }


def _manual_opp_from_payload(payload: dict, innings_totals: dict) -> tuple[list[dict], list[dict]]:
    """Opposition batting/bowling rows for a manually-uploaded scorecard.

    A manual game built by the AI scorecard upload stores the full both-team card in
    `extracted_payload`. Our own players come from the manual_* tables (already in
    batting_flat / bowling_flat); this reads only the OPPOSITION half (player_id stays
    None) so the match view shows both sides, and fills in each innings' team name and
    the opposition totals on innings_totals.
    """
    opp_batting: list[dict] = []
    opp_bowling: list[dict] = []
    for inn in (payload.get("innings") or []):
        try:
            n = int(inn.get("innings_number") or 1)
        except (TypeError, ValueError):
            n = 1
        meta = innings_totals.setdefault(n, {"runs": 0, "wickets": 0, "extras": 0})
        if inn.get("batting_team"):
            meta["batting_team"] = inn["batting_team"]
        extras = inn.get("extras") or {}
        if extras.get("total") is not None:
            meta["extras"] = extras["total"]
        if not inn.get("is_our_team"):
            # Opposition batted → their batters are the opp card; the bowling rows in
            # this innings are OURS (already in bowling_flat).
            if inn.get("total_runs") is not None:
                meta["runs"] = inn["total_runs"]
            if inn.get("total_wickets") is not None:
                meta["wickets"] = inn["total_wickets"]
            for b in (inn.get("batting") or []):
                opp_batting.append({
                    "innings_number": n,
                    "player_id": None,
                    "player_name": b.get("name"),
                    "runs": b.get("runs"),
                    "balls": b.get("balls"),
                    "fours": b.get("fours"),
                    "sixes": b.get("sixes"),
                    "dismissal_type": b.get("dismissal_text") or b.get("how_out"),
                    "caught_behind": None,
                    "not_out": bool(b.get("not_out")),
                    "did_not_bat": bool(b.get("did_not_bat")),
                    "batting_position": b.get("position"),
                })
        else:
            # We batted → the bowling rows are the OPPOSITION's bowlers.
            for b in (inn.get("bowling") or []):
                opp_bowling.append({
                    "innings_number": n,
                    "player_id": None,
                    "player_name": b.get("name"),
                    "overs": b.get("overs"),
                    "maidens": b.get("maidens"),
                    "runs": b.get("runs"),
                    "wickets": b.get("wickets"),
                    "wides": b.get("wides"),
                    "no_balls": b.get("no_balls"),
                    "economy": None,
                })
    return opp_batting, opp_bowling


@router.get("/{game_id}/scorecard")
async def get_scorecard(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    game = await db.get(Game, uuid.UUID(game_id))
    is_manual = False
    if not game:
        manual = await db.get(ManualGame, uuid.UUID(game_id))
        if not manual:
            # Not in our DB → live or never-synced. Build the card from Grassroots
            # (DB-first, GR-fallback). 404 only if GR doesn't know it either.
            gr_card = await _gr_scorecard_response(game_id)
            if gr_card is None:
                raise HTTPException(status_code=404, detail="Game not found")
            return gr_card
        game = manual
        is_manual = True

    grade = await db.get(Grade, game.grade_id) if game.grade_id else None
    season = await db.get(Season, grade.season_id) if grade else None
    org = await db.get(Organisation, season.organisation_id) if season else None
    # A fill-in's runs/wickets always show on the batting/bowling card (no
    # toggle). Whether their name also shows in the lower-stakes partnerships
    # and fielding cards is the club's own call (migration 147) — default on.
    include_fillins_stats = bool(org.include_fill_ins_in_stats) if org else True

    # Manual and synced child models share the same field names, so we just
    # pick which model to query against based on the game's provenance.
    BI = ManualBattingInnings if is_manual else BattingInnings
    BS = ManualBowlingSpell if is_manual else BowlingSpell
    FS = ManualFieldingStat if is_manual else FieldingStat
    game_fk = BI.manual_game_id if is_manual else BI.game_id

    batting_res = await db.execute(
        select(BI, Player)
        .outerjoin(Player, Player.id == BI.player_id)
        .where(game_fk == game.id)
        .order_by(BI.innings_number, BI.batting_position)
    )
    batting_rows = batting_res.all()

    bowling_res = await db.execute(
        select(BS, Player)
        .outerjoin(Player, Player.id == BS.player_id)
        .where((BS.manual_game_id if is_manual else BS.game_id) == game.id)
        .order_by(BS.innings_number)
    )
    bowling_rows = bowling_res.all()

    fielding_res = await db.execute(
        select(FS, Player)
        .outerjoin(Player, Player.id == FS.player_id)
        .where((FS.manual_game_id if is_manual else FS.game_id) == game.id)
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
            "caught_behind": bi.caught_behind,
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

    fielding_flat = []
    for fs, p in fielding_rows:
        if (fs.catches or 0) + (fs.run_outs or 0) + (fs.stumpings or 0) <= 0:
            continue
        if fs.player_id:
            fielding_flat.append({
                "player_id": str(fs.player_id),
                "player_name": p.display_name if p else None,
                "catches": fs.catches,
                "run_outs": fs.run_outs,
                "stumpings": fs.stumpings,
            })
        elif include_fillins_stats and fs.player_name:
            _disp_name, _is_fi, _is_red = _classify_unlinked_name(fs.player_name, None)
            fielding_flat.append({
                "player_id": None,
                "player_name": _disp_name,
                "catches": fs.catches,
                "run_outs": fs.run_outs,
                "stumpings": fs.stumpings,
                "is_fill_in": _is_fi,
                "is_redacted": _is_red,
            })
        # else: toggle off, or no name captured at sync time — the row is
        # silently omitted, matching pre-migration-146 behaviour.

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

    # Fall of wickets + partnerships read through the v_effective_* views, so an
    # uploaded manual card (manual_fall_of_wickets / manual_partnerships) shows them
    # too. Manual opposition batting/bowling still comes from extracted_payload below.
    fow = await get_game_fall_of_wickets(db, game.id)
    partnerships = await get_game_partnerships(db, game.id)
    # batterN_name already falls back to the raw fill-in/redacted GR name (see
    # get_game_partnerships) whenever batterN_id is NULL — strip it back out
    # if the club has the toggle off, else classify it the same way a
    # batting/bowling fill-in row is (real name + badge vs literal "********").
    for pt in partnerships:
        for _id_key, _name_key_, _fi_key, _red_key in (
            ("batter1_id", "batter1_name", "batter1_is_fill_in", "batter1_is_redacted"),
            ("batter2_id", "batter2_name", "batter2_is_fill_in", "batter2_is_redacted"),
        ):
            if pt.get(_id_key):
                continue
            if not include_fillins_stats or not pt.get(_name_key_):
                pt[_name_key_] = None
                continue
            _disp_name, _is_fi, _is_red = _classify_unlinked_name(pt[_name_key_], None)
            pt[_name_key_] = _disp_name
            pt[_fi_key] = _is_fi
            pt[_red_key] = _is_red

    # Live-fetch the match scorecard from Grassroots. When it's available (true
    # for effectively every non-manual game — GR's /scores/* endpoint reaches
    # back to the 1970s), it is the single source of truth for BOTH teams:
    # every displayed stat and innings total below comes straight from it, not
    # from summing whatever we happen to have already stored. Our own
    # `players` table is consulted only to attach a `player_id` link to a name
    # for hyperlinking through to a profile — never to decide what a row's
    # numbers are or which team it belongs to. (Previously a player already
    # registered with our club — including one who turned out as a guest for
    # the OTHER side that day — got merged onto our own card purely because
    # their GUID existed somewhere in our `players` table, corrupting that
    # innings' total; team membership must come from the match's own roster,
    # not from "is this id ours anywhere, ever".)
    #
    # The DB-sourced batting_flat/bowling_flat/innings_totals built above stay
    # untouched until every row below has been built successfully — only then
    # do they get swapped in. So a GR outage, or any exception in this block,
    # leaves the page showing our last-synced copy instead of erroring out.
    opp_batting: list[dict] = []
    opp_bowling: list[dict] = []

    try:
        if is_manual:
            raise RuntimeError("skip-gr-fetch-for-manual-game")
        from app.services.grassroots_scores_client import get_match_scorecard
        gr_data = await get_match_scorecard(str(game.id))
        if gr_data:
            _DNB = {"absent", "did not bat", "dnb"}

            # Match on (surname, first_initial) — handles "Baker, Daniel" (DB
            # format) vs "D Baker" (GR playerShortName). Also the fallback for
            # when GR's participant GUID for this match doesn't match anything
            # we have stored at all — CA is known to issue a different GUID
            # for the same real person across a MyCricket/PlayHQ migration
            # boundary, so id-only matching alone misses them.
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

            # `org` can legitimately be unresolvable (see `include_fillins_stats`
            # above) — that only means no `players` row can ever be linked for
            # a hyperlink; it must never block rebuilding the card itself from
            # Grassroots, which needs no org lookup at all to be correct.
            # `Player.display_name` is a Python @property (display_name_override
            # or name), not a mapped column — it can't go inside select(...)
            # (doing so throws at request time, not at import/compile time,
            # which is how this got past a syntax check). Select the two real
            # columns behind it and compute the same fallback in Python.
            player_rows = []
            if org:
                player_res = await db.execute(
                    select(Player.id, Player.grassroots_id, Player.display_name_override, Player.name)
                    .where(Player.organisation_id == org.id)
                )
                player_rows = player_res.all()
            known_ids: set = {r[0] for r in player_rows}
            guid_to_pid: dict[str, uuid.UUID] = {r[1]: r[0] for r in player_rows if r[1]}
            id_to_display: dict[uuid.UUID, str] = {r[0]: (r[2] or r[3]) for r in player_rows}
            nk_to_pid: dict[tuple, uuid.UUID] = {}
            for _pid, _guid, _override, _name in player_rows:
                _dname = _override or _name
                if _dname and not _looks_redacted(_dname):
                    nk_to_pid.setdefault(_name_key(_dname), _pid)

            def _resolve_linked_id(pid_str: str, name: str) -> Optional[uuid.UUID]:
                """Which of our own players (if any) this GR participant is —
                purely for a hyperlink, never for deciding a row's stats or
                which team it's on. Tries the literal id, then the stored raw
                GUID alias, then a name match for the GUID-mismatch case above."""
                try:
                    pid = uuid.UUID(pid_str)
                except (TypeError, ValueError):
                    pid = None
                if pid is not None and pid in known_ids:
                    return pid
                if pid_str in guid_to_pid:
                    return guid_to_pid[pid_str]
                if name and not _looks_redacted(name):
                    return nk_to_pid.get(_name_key(name))
                return None

            # Org name first word — a fallback signal for which GR team is
            # ours, used only when the DB-overlap signal below has nothing to
            # go on (see it for why that one comes first).
            org_word = (org.name or "").lower().split()[0] if org and org.name else ""

            # Names we ALREADY have a stored batting/bowling row for on this
            # exact game (batting_rows/bowling_rows were queried further up,
            # independent of org/season resolution). By construction sync only
            # ever writes rows for our own team, so whichever GR team's roster
            # overlaps these names is ours — a signal that doesn't depend on
            # `org` resolving at all, and is trusted over org-name matching
            # when it has anything to go on. Without this, a game whose
            # grade/season chain fails to resolve an org (happens — see the
            # `org` guards above) silently lost this whole rebuild the moment
            # any `org.` field was touched; that bug is fixed by not
            # depending on `org` for this signal in the first place.
            _existing_game_names: set = set()
            for _bi, _p in batting_rows:
                if _p and _p.display_name and not _looks_redacted(_p.display_name):
                    _existing_game_names.add(_name_key(_p.display_name))
            for _bs, _p in bowling_rows:
                if _p and _p.display_name and not _looks_redacted(_p.display_name):
                    _existing_game_names.add(_name_key(_p.display_name))

            # GR confirmed fields (via /scorecard/gr-debug):
            #   teams[]: players[], nonPlayingMembers[], id, displayName, name, owningOrganisation
            #   batting rows: participantId, playerShortName, batOrder, batInstance,
            #                 ballsFaced, foursScored, sixesScored, runsScored, battingMinutes,
            #                 strikeRate, dismissalTypeId, dismissalType, dismissalText,
            #                 isOnStrike, isOnNonStrike, highlight
            _teams_raw = gr_data.get("teams") or []

            # Pass 1: team id -> (display name, logo, members, DB-overlap count).
            # Logo field name isn't contractually documented on this endpoint —
            # same defensive fallback chain already used for the BetterSocials
            # match-import (`admin.py::build_team`) and confirmed on the
            # ladders endpoint (`ladders.py`) as `logoUrl`.
            gr_team_name_by_id: dict[str, str] = {}
            gr_team_logo_by_id: dict[str, str] = {}
            _team_members: dict[str, list] = {}
            _team_overlap: dict[str, int] = {}
            for _team in _teams_raw:
                _tid = (_team.get("id") or "").lower()
                if not _tid:
                    continue
                _members = (_team.get("players") or []) + (_team.get("nonPlayingMembers") or [])
                gr_team_name_by_id[_tid] = _team.get("displayName") or _team.get("name") or ""
                # The team object itself (a grade-level side, e.g. a sponsor
                # name) carries no logo — it's the parent club's, nested under
                # owningOrganisation.logoUrl (confirmed against a live payload).
                # The bare fallback keys are kept in case a differently-shaped
                # response ever puts it directly on the team.
                _owner = _team.get("owningOrganisation") or {}
                gr_team_logo_by_id[_tid] = (_owner.get("logoUrl") or _owner.get("logo") or
                                             _team.get("logoUrl") or _team.get("logo") or
                                             _team.get("imageUrl") or _team.get("image") or None)
                _team_members[_tid] = _members
                _team_overlap[_tid] = sum(
                    1 for _pl in _members
                    if _name_key(_pl.get("playerShortName") or _pl.get("displayName") or
                                 _pl.get("name") or "") in _existing_game_names
                )

            # Our own club's own uploaded logo (same precedence
            # social_rounds.py::_club_dict uses: an external URL if set, else
            # our own served endpoint if we hold the actual image bytes)
            # takes priority over GR's when this side is ours — a controlled,
            # always-available source beats an unconfirmed upstream field.
            _our_logo = None
            if org:
                _our_logo = org.logo_url or (f"/images/organisations/{org.id}/logo" if org.logo_data else None)

            # Pass 2: decide which team id is ours, DB-overlap first.
            if any(_team_overlap.values()):
                _our_tid = max(_team_overlap, key=_team_overlap.get)
            elif org_word:
                _our_tid = next(
                    (tid for tid, nm in gr_team_name_by_id.items() if org_word in nm.lower()),
                    None,
                )
            else:
                _our_tid = None

            # Pass 3: populate the roster sets now that "ours" is settled.
            pid_to_name: dict[str, str] = {}
            opp_roster_pids: set[str] = set()
            our_team_roster_pids: set[str] = set()
            for _tid, _members in _team_members.items():
                _is_our_team = _tid == _our_tid
                for _pl in _members:
                    _pid = _pl.get("participantId") or _pl.get("id")
                    _name = (_pl.get("playerShortName") or _pl.get("displayName") or
                             _pl.get("name") or "")
                    if _pid and _name:
                        pid_to_name[_pid] = _name
                    if _is_our_team and _pid:
                        our_team_roster_pids.add(_pid)
                    elif not _is_our_team and _pid:
                        opp_roster_pids.add(_pid)

            summary_teams = (gr_data.get("matchSummary") or {}).get("teams") or []
            home_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is True), "") or game.home_team or ""
            away_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is False), "") or game.away_team or ""
            we_are_home = bool(org_word and game.home_team and org_word in game.home_team.lower())
            our_display_name = home_name if we_are_home else away_name
            opp_display_name = away_name if we_are_home else home_name

            new_batting: list[dict] = []
            new_bowling: list[dict] = []
            new_opp_batting: list[dict] = []
            new_opp_bowling: list[dict] = []
            new_innings_totals: dict[int, dict] = {}
            # Authoritative innings totals from GR innings objects (wickets/extras
            # only — `runs` is deliberately not read from here, see below).
            gr_inn_totals: dict[int, dict] = {}
            all_seen_batting_pids: set[str] = set()
            our_inn_nums: list[int] = []
            opp_inn_nums: list[int] = []

            for inn in (gr_data.get("innings") or []):
                inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
                keeper_names = _innings_keeper_names(inn.get("fielding") or [])
                bt_id = str(inn.get("battingTeamId") or "").lower()
                gr_inn_totals[inn_num] = {
                    "wickets": inn.get("numberOfWicketsFallen"),
                    "extras": inn.get("totalExtras"),
                }
                _bt_is_ours = _our_tid is not None and bt_id == _our_tid
                (our_inn_nums if _bt_is_ours else opp_inn_nums).append(inn_num)
                new_innings_totals[inn_num] = {
                    "runs": 0,
                    "wickets": 0,
                    "extras": inn.get("totalExtras") or 0,
                    "batting_team": gr_team_name_by_id.get(bt_id) or (our_display_name if _bt_is_ours else opp_display_name),
                    "logo_url": (_our_logo if _bt_is_ours else None) or gr_team_logo_by_id.get(bt_id),
                }

                for row in (inn.get("batting") or []):
                    pid_str = row.get("participantId")
                    if not pid_str:
                        continue
                    all_seen_batting_pids.add(pid_str)

                    dt_id = row.get("dismissalTypeId") or 0
                    dt_long = row.get("dismissalType") or ""
                    is_dnb = dt_long.lower() in _DNB
                    if dt_id == 0 and not is_dnb:
                        continue

                    # playerShortName is on each batting row (confirmed by gr-debug).
                    name = row.get("playerShortName") or pid_to_name.get(pid_str) or "Unknown"
                    # dismissalText is pre-formatted: "c S Aplin b W Dagg", "b W Dagg", etc.
                    dismissal_str = None if is_dnb else (row.get("dismissalText") or dt_long.lower() or None)
                    caught_behind = dt_long == "Caught" and _caught_by_keeper(row.get("dismissalText") or "", keeper_names)
                    base = {
                        "innings_number": inn_num,
                        "runs": None if is_dnb else (row.get("runsScored") or 0),
                        "balls": None if is_dnb else (row.get("ballsFaced") or 0),
                        "fours": None if is_dnb else (row.get("foursScored") or 0),
                        "sixes": None if is_dnb else (row.get("sixesScored") or 0),
                        "strike_rate": _to_float(row.get("strikeRate")),
                        "dismissal_type": dismissal_str,
                        "caught_behind": caught_behind,
                        "not_out": dt_id == 1,
                        "batting_position": row.get("batOrder"),
                        "did_not_bat": is_dnb,
                    }

                    if pid_str in our_team_roster_pids:
                        linked_id = _resolve_linked_id(pid_str, name)
                        if linked_id:
                            new_batting.append({**base, "player_id": str(linked_id),
                                                 "player_name": id_to_display.get(linked_id) or name})
                        else:
                            # On our team's GR roster but not a registered player — a
                            # fill-in (borrowed player) or a CA-redacted junior.
                            _disp_name, _is_fi, _is_red = _classify_unlinked_name(name, row.get("batOrder"))
                            new_batting.append({**base, "player_id": None, "player_name": _disp_name,
                                                 "is_fill_in": _is_fi, "is_redacted": _is_red,
                                                 "grassroots_participant_id": pid_str if _is_fi else None})
                    else:
                        new_opp_batting.append({**base, "player_id": None, "player_name": name})

                    if not is_dnb:
                        totals = new_innings_totals[inn_num]
                        totals["runs"] += base["runs"] or 0
                        if not base["not_out"] and base["dismissal_type"]:
                            totals["wickets"] += 1

                for row in (inn.get("bowling") or []):
                    pid_str = row.get("participantId")
                    if not pid_str:
                        continue
                    name = row.get("playerShortName") or pid_to_name.get(pid_str) or "Unknown"
                    base = {
                        "innings_number": inn_num,
                        "overs": row.get("oversBowled"),
                        "maidens": row.get("maidensBowled"),
                        "runs": row.get("runsConceded"),
                        "wickets": row.get("wicketsTaken"),
                        "wides": row.get("wideBalls"),
                        "no_balls": row.get("noBalls"),
                        "economy": _to_float(row.get("economy")),
                    }
                    if pid_str in our_team_roster_pids:
                        linked_id = _resolve_linked_id(pid_str, name)
                        if linked_id:
                            new_bowling.append({**base, "player_id": str(linked_id),
                                                 "player_name": id_to_display.get(linked_id) or name})
                        else:
                            _disp_name, _is_fi, _is_red = _classify_unlinked_name(name, None)
                            new_bowling.append({**base, "player_id": None, "player_name": _disp_name,
                                                 "is_fill_in": _is_fi, "is_redacted": _is_red,
                                                 "grassroots_participant_id": pid_str if _is_fi else None})
                    else:
                        new_opp_bowling.append({**base, "player_id": None, "player_name": name})

            # Roster members GR lists per team (incl. non-playing squad members)
            # who never appear in any innings' batting array at all — a DNB row
            # so they're not silently dropped, attached to the first innings
            # their own team batted in.
            our_dnb_inn = min(our_inn_nums, default=1)
            opp_dnb_inn = min(opp_inn_nums, default=(2 if our_dnb_inn == 1 else 1))
            for ros_pid_str in our_team_roster_pids - all_seen_batting_pids:
                name = pid_to_name.get(ros_pid_str)
                if not name:
                    continue
                dnb_base = {
                    "innings_number": our_dnb_inn, "runs": None, "balls": None, "fours": None,
                    "sixes": None, "strike_rate": None, "dismissal_type": None,
                    "caught_behind": False, "not_out": False, "batting_position": None,
                    "did_not_bat": True,
                }
                linked_id = _resolve_linked_id(ros_pid_str, name)
                if linked_id:
                    new_batting.append({**dnb_base, "player_id": str(linked_id),
                                         "player_name": id_to_display.get(linked_id) or name})
                else:
                    _disp_name, _is_fi, _is_red = _classify_unlinked_name(name, None)
                    new_batting.append({**dnb_base, "player_id": None, "player_name": _disp_name,
                                         "is_fill_in": _is_fi, "is_redacted": _is_red,
                                         "grassroots_participant_id": ros_pid_str if _is_fi else None})
            for dnb_pid_str in opp_roster_pids - all_seen_batting_pids:
                name = pid_to_name.get(dnb_pid_str)
                if not name:
                    continue
                new_opp_batting.append({
                    "innings_number": opp_dnb_inn, "player_id": None, "player_name": name,
                    "runs": None, "balls": None, "fours": None, "sixes": None,
                    "dismissal_type": None, "caught_behind": False, "not_out": False,
                    "batting_position": None, "did_not_bat": True,
                })

            # GR's own wicket/extras counts are more reliable than what we can
            # derive from dismissal-string parsing — byes/leg-byes/penalties in
            # particular aren't attributable to any one bowling row. Applies
            # uniformly to both sides now (previously only the opposition
            # innings got this treatment). `runs` stays the bat-only sum
            # computed above — extras are tracked separately and added again
            # by the frontend, so substituting GR's own `runsScored` (the full
            # team total) here would double-count them.
            for inn_num, gr_tot in gr_inn_totals.items():
                totals = new_innings_totals.setdefault(
                    inn_num, {"runs": 0, "wickets": 0, "extras": 0, "batting_team": None, "logo_url": None})
                if gr_tot.get("wickets") is not None:
                    totals["wickets"] = gr_tot["wickets"]
                if gr_tot.get("extras") is not None:
                    totals["extras"] = gr_tot["extras"]

            # Everything above built cleanly — swap it in as the page's data.
            # (Left untouched on any exception, including a GR outage above,
            # so the page falls back to our last-synced copy instead of erroring.)
            batting_flat = new_batting
            bowling_flat = new_bowling
            opp_batting = new_opp_batting
            opp_bowling = new_opp_bowling
            innings_totals = new_innings_totals

    except Exception as e:
        import traceback
        logger.error(f"get_scorecard: GR live-fetch failed for {game_id}: {e}\n{traceback.format_exc()}")

    # Manual games skip the GR feed; if the card was uploaded with the AI scorecard
    # tool it carries the opposition half in its stored payload, so render both sides.
    if is_manual and getattr(game, "extracted_payload", None):
        opp_batting, opp_bowling = _manual_opp_from_payload(game.extracted_payload, innings_totals)

    # A `players` row can exist with an unusable name — a stale placeholder row
    # for a CA-redacted participant (see `_classify_unlinked_name`), created by
    # an earlier sync bug rather than by a real registration. Whatever created
    # the row, showing a linked "********" profile is never right, so
    # normalise any such row to the same unlinked, unbadged redacted shape
    # used elsewhere on this card (never `is_fill_in` — a stale garbage row is
    # not a "fill-in" in the borrowed-player sense, it's an unknown identity).
    for _row in batting_flat:
        if _row.get("player_id") and _looks_redacted(_row.get("player_name")):
            _row["player_id"] = None
            _row["player_name"] = "********"
            _row["is_redacted"] = True
    for _row in bowling_flat:
        if _row.get("player_id") and _looks_redacted(_row.get("player_name")):
            _row["player_id"] = None
            _row["player_name"] = "********"
            _row["is_redacted"] = True

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
