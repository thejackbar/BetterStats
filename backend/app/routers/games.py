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

    # Live-fetch opposition data from GR API (not stored in DB).
    # game.id IS the GR match UUID, so we can call directly. Skip for
    # manual games — their IDs aren't in GR's namespace.
    opp_batting: list[dict] = []
    opp_bowling: list[dict] = []
    opp_extras: dict[int, int] = {}

    try:
        if is_manual:
            raise RuntimeError("skip-gr-fetch-for-manual-game")
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

            # Excludes redacted-name rows ("********") — a name-key built from a
            # placeholder is not a real fingerprint and would falsely "match" every
            # other redacted participant in the game (their own real name, or lack
            # of one, is irrelevant — they'd all collide on the same asterisks).
            our_batting_fingerprints: set[tuple[str, str]] = {
                _name_key(r["player_name"]) for r in batting_flat
                if r.get("player_name") and not _looks_redacted(r["player_name"])
            }

            # Org name first word — identifies which GR team is ours vs opposition.
            org_obj = org
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
            # team id -> display name, straight off GR's own roster — the authoritative
            # source for which team batted in a given innings (via battingTeamId below),
            # independent of any of the "is this batter one of ours" identity matching.
            gr_team_name_by_id: dict[str, str] = {}
            for _team in (gr_data.get("teams") or []):
                _team_name = (_team.get("displayName") or _team.get("name") or "").lower()
                _is_our_team = bool(org_word and org_word in _team_name)
                _tid = (_team.get("id") or "").lower()
                if _tid:
                    gr_team_name_by_id[_tid] = _team.get("displayName") or _team.get("name") or ""
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

            # Accumulate our own known players (already a `players` row) whose
            # batting_innings row for THIS game is missing — covers both DNB and a
            # genuinely scored innings that never made it into the DB (e.g. a
            # placeholder player row for a CA-redacted participant that has a
            # `players` row but no per-game stats attached to it).
            our_missing_rows: dict[uuid.UUID, dict] = {}
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
            # Roster members on OUR team with no `players` row — fill-ins (borrowed
            # players) or CA-redacted juniors. Tracked so they're rendered exactly
            # once (batted/DNB in the innings loop, or as a name-only DNB fallback
            # in the later roster sweep) instead of being dropped or misattributed
            # to the opposition.
            fill_in_seen_pids: set[str] = set()
            # Authoritative innings totals from GR innings objects.
            # Fields confirmed: runsScored, numberOfWicketsFallen, totalExtras,
            #                   byesRuns, legByesRuns, wideBalls, noBalls, penalties
            gr_inn_totals: dict[int, dict] = {}

            for inn in (gr_data.get("innings") or []):
                inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
                keeper_names = _innings_keeper_names(inn.get("fielding") or [])

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
                            is_dnb_o = dt_long_o in _DNB
                            # A real dismissal/innings (dt_id_o != 0) or a flagged DNB —
                            # either way this known player has no batting_innings row
                            # for this game, so inject one from GR's own stats rather
                            # than silently dropping a scored innings.
                            if dt_id_o != 0 or is_dnb_o:
                                our_missing_rows[pid] = {
                                    "innings_number": inn_num,
                                    "runs": None if is_dnb_o else (row.get("runsScored") or 0),
                                    "balls": None if is_dnb_o else (row.get("ballsFaced") or 0),
                                    "fours": None if is_dnb_o else (row.get("foursScored") or 0),
                                    "sixes": None if is_dnb_o else (row.get("sixesScored") or 0),
                                    "strike_rate": _to_float(row.get("strikeRate")),
                                    "dismissal_type": None if is_dnb_o else (dt_text or dt_long_o or None),
                                    "caught_behind": dt_long_o == "caught" and _caught_by_keeper(dt_text or "", keeper_names),
                                    "not_out": dt_id_o == 1,
                                    "batting_position": row.get("batOrder"),
                                    "did_not_bat": is_dnb_o,
                                    "fallback_name": row.get("playerShortName"),
                                }
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

                    # dismissalText is pre-formatted: "c S Aplin b W Dagg", "b W Dagg", etc.
                    dismissal_str = None if is_dnb else (
                        row.get("dismissalText") or dt_long.lower() or None
                    )
                    caught_behind = dt_long == "Caught" and _caught_by_keeper(row.get("dismissalText") or "", keeper_names)

                    # On our team's GR roster but not a known DB player — a fill-in
                    # (borrowed player) or a CA-redacted junior. Show them on our own
                    # batting card, flagged, instead of dropping their runs (which
                    # silently undercounted the innings total) or misattributing them
                    # to the opposition.
                    if pid_str in our_team_roster_pids:
                        fill_in_seen_pids.add(pid_str)
                        _disp_name, _is_fi, _is_red = _classify_unlinked_name(name, row.get("batOrder"))
                        batting_flat.append({
                            "innings_number": inn_num,
                            "player_id": None,
                            "player_name": _disp_name,
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
                            "is_fill_in": _is_fi,
                            "is_redacted": _is_red,
                            "grassroots_participant_id": pid_str if _is_fi else None,
                        })
                        continue

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
                        "caught_behind": caught_behind,
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
                    if pid_str in our_team_roster_pids:
                        # A fill-in bowler for our side — show on our own bowling card
                        # (flagged) instead of misattributing to the opposition.
                        fill_in_seen_pids.add(pid_str)
                        _disp_name, _is_fi, _is_red = _classify_unlinked_name(name, None)
                        bowling_flat.append({
                            "innings_number": inn_num,
                            "player_id": None,
                            "player_name": _disp_name,
                            "overs": row.get("oversBowled"),
                            "maidens": row.get("maidensBowled"),
                            "runs": row.get("runsConceded"),
                            "wickets": row.get("wicketsTaken"),
                            "wides": row.get("wideBalls"),
                            "no_balls": row.get("noBalls"),
                            "economy": econ,
                            "is_fill_in": _is_fi,
                            "is_redacted": _is_red,
                            "grassroots_participant_id": pid_str if _is_fi else None,
                        })
                        continue
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
                    if ros_pid_str in fill_in_seen_pids:
                        continue
                    try:
                        ros_pid = uuid.UUID(ros_pid_str)
                    except ValueError:
                        continue
                    if ros_pid in db_batting_pids:
                        continue
                    if ros_pid in our_batting_pids_seen_in_gr:
                        continue
                    if ros_pid in our_missing_rows:
                        continue
                    if not pid_to_name.get(ros_pid_str):
                        continue
                    if ros_pid in known_ids:
                        our_missing_rows[ros_pid] = {
                            "innings_number": _our_inn, "runs": None, "balls": None,
                            "fours": None, "sixes": None, "strike_rate": None,
                            "dismissal_type": None, "caught_behind": False,
                            "not_out": False, "batting_position": None,
                            "did_not_bat": True, "fallback_name": pid_to_name.get(ros_pid_str),
                        }
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
                        if _looks_redacted(_pl.display_name):
                            continue
                        _nk_to_player[_name_key(_pl.display_name)] = _pl
                    for _ros_str in _unresolved_roster_pids:
                        _ros_name = pid_to_name.get(_ros_str, "")
                        if not _ros_name:
                            continue
                        _nk = _name_key(_ros_name)
                        if _nk in our_batting_fingerprints:
                            continue  # they batted, not a DNB
                        _matched = _nk_to_player.get(_nk)
                        if _matched:
                            if _matched.id in db_batting_pids or _matched.id in our_missing_rows:
                                continue
                            our_missing_rows[_matched.id] = {
                                "innings_number": _our_inn, "runs": None, "balls": None,
                                "fours": None, "sixes": None, "strike_rate": None,
                                "dismissal_type": None, "caught_behind": False,
                                "not_out": False, "batting_position": None,
                                "did_not_bat": True, "fallback_name": _ros_name,
                            }
                        else:
                            # Genuine fill-in with no `players` row at all — inject a
                            # name-only DNB row rather than silently dropping them.
                            fill_in_seen_pids.add(_ros_str)
                            _disp_name, _is_fi, _is_red = _classify_unlinked_name(_ros_name, None)
                            batting_flat.append({
                                "innings_number": _our_inn,
                                "player_id": None,
                                "player_name": _disp_name,
                                "runs": None, "balls": None, "fours": None, "sixes": None,
                                "strike_rate": None, "dismissal_type": None, "not_out": False,
                                "batting_position": None, "did_not_bat": True,
                                "is_fill_in": _is_fi,
                                "is_redacted": _is_red,
                                "grassroots_participant_id": _ros_str if _is_fi else None,
                            })

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

            # Append our own known players (a `players` row exists) whose
            # batting_innings row for this game is missing — DNB (pre-migration
            # games) or a genuinely scored innings we never persisted (e.g. a
            # placeholder row for a CA-redacted participant with no per-game
            # stats attached). `player_name` prefers the DB display name and
            # falls back to GR's own name — the redacted-name normalisation
            # pass below turns an unusable one of either into a Fill-In row.
            if our_missing_rows:
                miss_player_res = await db.execute(
                    select(Player).where(Player.id.in_(our_missing_rows.keys()))
                )
                miss_player_map = {p.id: p for p in miss_player_res.scalars().all()}
                for miss_pid, miss_row in our_missing_rows.items():
                    miss_player = miss_player_map.get(miss_pid)
                    miss_name = (miss_player.display_name if miss_player else None) or miss_row.get("fallback_name")
                    batting_flat.append({
                        "innings_number": miss_row["innings_number"],
                        "player_id": str(miss_pid),
                        "player_name": miss_name,
                        "runs": miss_row["runs"],
                        "balls": miss_row["balls"],
                        "fours": miss_row["fours"],
                        "sixes": miss_row["sixes"],
                        "strike_rate": miss_row["strike_rate"],
                        "dismissal_type": miss_row["dismissal_type"],
                        "caught_behind": miss_row["caught_behind"],
                        "not_out": miss_row["not_out"],
                        "batting_position": miss_row["batting_position"],
                        "did_not_bat": miss_row["did_not_bat"],
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

            # Recompute OUR OWN batting innings totals from the now-fully-populated
            # batting_flat (DB rows + fill-in rows + previously-missing known-player
            # rows injected above). The very first pass (near the top of this
            # function) ran before any of those GR-sourced rows existed, so it
            # would otherwise leave stale, undercounted totals. NOTE: `runs`/`wickets`
            # here are bat-only (extras are tracked and added separately below and
            # again by the frontend) — do not substitute GR's own `runsScored`, which
            # is the full team total including extras and would double-count them.
            our_recomputed: dict[int, dict] = {}
            for row in batting_flat:
                n = row["innings_number"]
                if n not in our_recomputed:
                    our_recomputed[n] = {"runs": 0, "wickets": 0}
                if row["did_not_bat"]:
                    continue
                our_recomputed[n]["runs"] += row["runs"] or 0
                if not row["not_out"] and row["dismissal_type"]:
                    our_recomputed[n]["wickets"] += 1

            for inn_num_t in set(list(innings_totals.keys()) + [r["innings_number"] for r in opp_batting]):
                if inn_num_t not in innings_totals:
                    innings_totals[inn_num_t] = {"runs": 0, "wickets": 0, "extras": 0}
                # For opp batting innings, overwrite runs/wickets with actual totals
                if inn_num_t not in our_batting_inns and inn_num_t in opp_inn_totals:
                    innings_totals[inn_num_t]["runs"] = opp_inn_totals[inn_num_t]["runs"]
                    innings_totals[inn_num_t]["wickets"] = opp_inn_totals[inn_num_t]["wickets"]
                # Prefer GR's own authoritative battingTeamId -> team name lookup over
                # the "is this batter one of ours" inference below, which is derived
                # from player/roster identity matching and can misfire (e.g. the
                # org-name-substring we_are_home check, or an innings whose batting
                # rows all landed in our_missing_rows/fill-in handling).
                _bt_id = str((gr_inn_totals.get(inn_num_t) or {}).get("batting_team_id") or "").lower()
                _resolved_name = gr_team_name_by_id.get(_bt_id)

                if inn_num_t in our_batting_inns:
                    innings_totals[inn_num_t]["batting_team"] = _resolved_name or our_display_name or game.home_team or ""
                    if inn_num_t in our_recomputed:
                        innings_totals[inn_num_t]["runs"] = our_recomputed[inn_num_t]["runs"]
                        innings_totals[inn_num_t]["wickets"] = our_recomputed[inn_num_t]["wickets"]
                else:
                    innings_totals[inn_num_t]["batting_team"] = _resolved_name or opp_display_name or game.away_team or ""
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
