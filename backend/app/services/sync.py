import logging
import uuid
from datetime import datetime, timezone, date
from typing import Optional

# Rolling in-memory sync log (last 30 entries per org, survives until restart)
_sync_log: dict[str, list] = {}

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from sqlalchemy.sql import func

from app.models.db import (
    Organisation, Season, Grade, Game, Player,
    BattingInnings, BowlingSpell, FallOfWicket, Partnership,
    PlayerSeasonStats, Milestone, PhqIdSuggestion, async_session_maker
)
from app.services import playhq_client

logger = logging.getLogger(__name__)


def _parse_uuid(val: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError):
        return None


async def upsert_organisation(session: AsyncSession, org_data: dict) -> Organisation:
    org_id = _parse_uuid(org_data.get("id", ""))
    org = await session.get(Organisation, org_id)
    if not org:
        org = Organisation(
            id=org_id,
            name=org_data.get("name", ""),
            short_name=org_data.get("shortName", ""),
        )
        session.add(org)
    else:
        org.name = org_data.get("name") or org.name
    await session.commit()
    return org


def _record_sync_log(org_id: str, started_at: str, stats: dict, error: str = "") -> None:
    entry = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "error": error,
    }
    log = _sync_log.setdefault(org_id, [])
    log.insert(0, entry)
    _sync_log[org_id] = log[:30]


async def sync_organisation(org_id_str: str) -> dict:
    """Full historical sync for an organisation using season-aggregate stats."""
    logger.info(f"Starting sync for org {org_id_str}")
    started_at = datetime.now(timezone.utc).isoformat()

    org_data = await playhq_client.get_organisation(org_id_str)
    if not org_data:
        _record_sync_log(org_id_str, started_at, {}, "Organisation not found")
        return {"error": "Organisation not found", "org_id": org_id_str}

    stats = {"seasons": 0, "players": 0, "season_stats": 0,
             "games_new": 0, "batting": 0, "bowling": 0, "partnerships": 0,
             "playhq_games_found": 0, "playhq_games_final": 0}

    async with async_session_maker() as session:
        org = await upsert_organisation(session, org_data)
        org_id = org.id

        # Populate PlayHQ native ID if not already stored
        if not org.playhq_id:
            playhq_id = await playhq_client.lookup_playhq_id(org_id_str, org.name)
            if playhq_id:
                org.playhq_id = playhq_id
                await session.commit()
                logger.info(f"Stored playhq_id {playhq_id} for org {org_id_str}")

        seasons = await playhq_client.get_seasons(org_id_str)
        logger.info(f"Found {len(seasons)} seasons")

        for season_data in seasons:
            season_id = _parse_uuid(season_data.get("id", ""))
            if not season_id:
                continue

            start_date_str = season_data.get("startDate", "")
            year = int(start_date_str[:4]) if start_date_str else None

            season = await session.get(Season, season_id)
            if not season:
                season = Season(
                    id=season_id,
                    organisation_id=org_id,
                    name=season_data.get("name", ""),
                    year=year,
                )
                session.add(season)
            season.synced_at = datetime.now(timezone.utc)
            await session.commit()
            stats["seasons"] += 1

            # Fetch season-aggregate stats from grassroots API
            batting_list = await playhq_client.get_batting_stats(org_id_str, str(season_id))
            bowling_list = await playhq_client.get_bowling_stats(org_id_str, str(season_id))
            fielding_list = await playhq_client.get_fielding_stats(org_id_str, str(season_id))

            # Merge all participant data keyed by player UUID
            player_data: dict[uuid.UUID, dict] = {}

            for p in batting_list:
                pid = _parse_uuid(p.get("id"))
                if not pid:
                    continue
                player_data.setdefault(pid, {"name": p.get("name") or p.get("shortName", "Unknown")})
                player_data[pid]["batting"] = p.get("statistics", {})

            for p in bowling_list:
                pid = _parse_uuid(p.get("id"))
                if not pid:
                    continue
                player_data.setdefault(pid, {"name": p.get("name") or p.get("shortName", "Unknown")})
                player_data[pid]["bowling"] = p.get("statistics", {})

            for p in fielding_list:
                pid = _parse_uuid(p.get("id"))
                if not pid:
                    continue
                player_data.setdefault(pid, {"name": p.get("name") or p.get("shortName", "Unknown")})
                player_data[pid]["fielding"] = p.get("statistics", {})

            if not player_data:
                continue

            # Build merged-player map so sync doesn't recreate deleted duplicates
            try:
                merge_res = await session.execute(
                    text("SELECT removed_player_id::text, keep_player_id FROM merge_logs WHERE org_id = :org_id"),
                    {"org_id": str(org_id)},
                )
                merged_away: dict[str, uuid.UUID] = {
                    r.removed_player_id: r.keep_player_id for r in merge_res.mappings().all()
                }
            except Exception:
                await session.rollback()
                merged_away = {}

            # Upsert players — skip any that were merged away
            for pid, pdata in player_data.items():
                if str(pid) in merged_away:
                    continue
                player = await session.get(Player, pid)
                if not player:
                    player = Player(id=pid, name=pdata["name"], organisation_id=org_id)
                    session.add(player)
            await session.commit()

            # Replace existing season stats for this season
            await session.execute(
                delete(PlayerSeasonStats).where(PlayerSeasonStats.season_id == season_id)
            )

            processed_in_season: set[uuid.UUID] = set()
            for pid, pdata in player_data.items():
                # Redirect stats for merged-away players to the kept player
                effective_pid = merged_away.get(str(pid), pid)
                if effective_pid in processed_in_season:
                    continue
                processed_in_season.add(effective_pid)
                pid = effective_pid
                # Safety: skip if the target player doesn't exist in DB (e.g. merge chain issue)
                if not await session.get(Player, pid):
                    logger.warning(f"Skipping stats for player {pid}: not found in players table")
                    continue
                bat = pdata.get("batting", {})
                bowl = pdata.get("bowling", {})
                field = pdata.get("fielding", {})

                # Derive overs from balls (cricket notation: 7 balls = 1.1 overs)
                bowling_balls = bowl.get("bowlingBalls") or 0
                full_overs = bowling_balls // 6
                extra_balls = bowling_balls % 6
                cricket_overs = full_overs + extra_balls / 10.0

                # Best bowling figures is a string like "4-13"
                best_figures = bowl.get("bowlingBestInnings") or ""
                best_wkts = None
                if best_figures and "-" in best_figures:
                    try:
                        best_wkts = int(best_figures.split("-")[0])
                    except ValueError:
                        best_wkts = None

                row = PlayerSeasonStats(
                    player_id=pid,
                    season_id=season_id,
                    matches=bat.get("matches") or bowl.get("matches") or field.get("matches") or 0,
                    batting_innings=bat.get("battingInnings") or 0,
                    runs=bat.get("battingAggregate") or 0,
                    not_outs=bat.get("battingNotOuts") or 0,
                    balls_faced=bat.get("battingBallsFaced") or 0,
                    fifties=bat.get("batting50s") or 0,
                    hundreds=bat.get("batting100s") or 0,
                    ducks=bat.get("batting0s") or 0,
                    high_score=bat.get("battingHighScore"),
                    is_hs_not_out=bat.get("isBattingHSNotOut") or False,
                    batting_average=bat.get("battingAverage"),
                    batting_strike_rate=bat.get("battingStrikeRate"),
                    fours=bat.get("battingFours") or 0,
                    sixes=bat.get("battingSixes") or 0,
                    batting_minutes=bat.get("battingMinutes") or 0,
                    bowling_innings=bowl.get("bowlingInnings") or 0,
                    wickets=bowl.get("bowlingWickets") or 0,
                    overs=cricket_overs,
                    bowling_balls=bowling_balls,
                    runs_conceded=bowl.get("bowlingRuns") or 0,
                    maidens=bowl.get("bowlingMaidens") or 0,
                    bowling_economy=bowl.get("bowlingEconomyRate"),
                    bowling_average=bowl.get("bowlingAverage"),
                    bowling_strike_rate=bowl.get("bowlingStrikeRate"),
                    best_bowling_wickets=best_wkts,
                    best_bowling_figures=best_figures or None,
                    five_wicket_innings=bowl.get("bowling5WIs") or 0,
                    wides=bowl.get("bowlingWides") or 0,
                    no_balls=bowl.get("bowlingNoBalls") or 0,
                    catches=field.get("fieldingTotalCatches") or 0,
                    catches_wk=field.get("fieldingCatchesWK") or 0,
                    catches_non_wk=field.get("fieldingCatchesNonWK") or 0,
                    run_outs=field.get("fieldingRunOuts") or 0,
                    assisted_run_outs=field.get("fieldingAssistedRunOuts") or 0,
                    unassisted_run_outs=field.get("fieldingUnassistedRunOuts") or 0,
                    stumpings=field.get("fieldingStumpings") or 0,
                )
                session.add(row)

            await session.commit()
            stats["players"] += len(player_data)
            stats["season_stats"] += len(player_data)
            logger.info(f"Season {season_data.get('name')}: {len(player_data)} players synced")

        # Recompute milestones for all players in this org
        all_pids_res = await session.execute(
            select(Player.id).where(Player.organisation_id == org_id)
        )
        all_player_ids = [r[0] for r in all_pids_res]
        if all_player_ids:
            await _compute_milestones(session, all_player_ids, org_id)

        # Backfill PlayHQ player IDs + full game-level data
        if org.playhq_id:
            import traceback as _tb
            try:
                from app.services import playhq_partner_client
                db_seasons_res2 = await session.execute(
                    select(Season).where(Season.organisation_id == org_id)
                )
                db_seasons_list = [
                    {"id": str(s.id), "name": s.name}
                    for s in db_seasons_res2.scalars().all()
                ]
                all_games = await playhq_partner_client.get_org_games(
                    org.playhq_id, org.name,
                    db_seasons=db_seasons_list,
                    grassroots_org_id=org_id_str,
                )
                final_count = sum(1 for g in all_games if g.get('status') == 'FINAL')
                stats["playhq_games_found"] = len(all_games)
                stats["playhq_games_final"] = final_count
                logger.info(f"PlayHQ: {len(all_games)} total games, {final_count} FINAL")
            except Exception as e:
                logger.error(f"PlayHQ get_org_games failed for {org_id_str}: {e}\n{_tb.format_exc()}")
                all_games = []

            if all_games:
                try:
                    await _backfill_player_playhq_ids(session, org, all_games)
                except Exception as e:
                    logger.error(f"PlayHQ backfill failed for {org_id_str}: {e}\n{_tb.format_exc()}")
                    await session.rollback()
                try:
                    game_stats = await sync_game_level_data(session, org, all_games)
                    stats.update(game_stats)
                except Exception as e:
                    logger.error(f"PlayHQ game-level sync failed for {org_id_str}: {e}\n{_tb.format_exc()}")

        logger.info(f"Sync complete: {stats}")
        _record_sync_log(org_id_str, started_at, stats)
        return stats


def _derive_partnerships(
    batting_rows: list,
    fow_rows: list,
    playhq_to_player_id: dict,
    name_to_pid: dict | None = None,
) -> list:
    """Derive per-wicket partnership data from batting order + fall of wickets."""
    if len(batting_rows) < 2:
        return []

    def resolve_pid(b):
        if not b:
            return None
        pid = playhq_to_player_id.get(b.get("playhq_appearance_id") or "")
        if not pid and name_to_pid:
            name_lc = (b.get("name") or "").strip().lower()
            pid = name_to_pid.get(name_lc) if name_lc else None
        return pid

    batters = sorted(batting_rows, key=lambda r: r.get("batting_position") or 99)
    at_crease = list(batters[:2])
    next_in = 2
    prev_score = 0
    result = []

    for fow in sorted(fow_rows, key=lambda f: f.get("wicket_number") or 99):
        wkt = fow.get("wicket_number") or len(result) + 1
        score = fow.get("score_at_fall")
        dismissed_phq = fow.get("batter_playhq_id")

        b1 = at_crease[0] if len(at_crease) > 0 else None
        b2 = at_crease[1] if len(at_crease) > 1 else None

        result.append({
            "wicket_number": wkt,
            "batter1_id": resolve_pid(b1),
            "batter2_id": resolve_pid(b2),
            "batter1_runs": b1.get("runs") if b1 else None,
            "batter2_runs": b2.get("runs") if b2 else None,
            "runs": (score - prev_score) if score is not None else None,
        })

        if dismissed_phq:
            at_crease = [b for b in at_crease if b.get("playhq_appearance_id") != dismissed_phq]
        elif at_crease:
            at_crease.pop()

        if next_in < len(batters):
            at_crease.append(batters[next_in])
            next_in += 1

        if score is not None:
            prev_score = score

    return result


async def sync_game_level_data(
    session: AsyncSession,
    org: Organisation,
    all_games: list,
) -> dict:
    """Store game-level batting/bowling/partnership rows from PlayHQ scorecards."""
    from app.services import playhq_partner_client
    from datetime import date as date_cls

    stats = {"games_new": 0, "batting": 0, "bowling": 0, "partnerships": 0,
             "games_skipped_done": 0, "games_skipped_season": 0, "games_skipped_no_stats": 0}

    final_games = [g for g in all_games if g.get("status") == "FINAL"]
    org_id = org.id  # cache before any rollback can expire the ORM object

    seasons_res = await session.execute(
        select(Season).where(Season.organisation_id == org.id)
    )
    # Store as plain dicts so session rollbacks can't expire these and trigger async lazy-loads
    season_by_name = {
        s.name.strip().lower(): {"id": s.id, "year": s.year}
        for s in seasons_res.scalars().all() if s.name
    }

    players_res = await session.execute(
        select(Player).where(Player.organisation_id == org.id)
    )
    phq_to_pid: dict[str, uuid.UUID] = {}
    name_to_pid: dict[str, uuid.UUID] = {}
    for p in players_res.scalars().all():
        if p.playhq_id:
            phq_to_pid[p.playhq_id] = p.id
        n = (p.name or "").strip().lower()
        if not n:
            continue
        name_to_pid[n] = p.id
        # Index both "First Last" and "Last, First" so either scorecard format matches
        if "," in n:
            parts = [x.strip() for x in n.split(",", 1)]
            if len(parts) == 2:
                name_to_pid[f"{parts[1]} {parts[0]}"] = p.id
        else:
            words = n.split()
            if len(words) >= 2:
                name_to_pid[f"{' '.join(words[1:])}, {words[0]}"] = p.id
    logger.info(f"GameSync: {len(phq_to_pid)} players with playhq_id, {len(name_to_pid)} name entries for org {org_id}")

    for game_data in final_games:
        game_id_str = game_data.get("id")
        if not game_id_str:
            continue
        try:
            game_uuid = uuid.UUID(game_id_str)
        except ValueError:
            continue

        try:
            existing_game = await session.get(Game, game_uuid)
        except Exception as e:
            logger.error(f"GameSync: session error looking up game {game_id_str}: {e}")
            await session.rollback()
            continue
        if existing_game:
            from sqlalchemy import text as _text
            has_stats = await session.execute(
                _text("SELECT 1 FROM batting_innings WHERE game_id=:gid LIMIT 1"),
                {"gid": str(game_uuid)},
            )
            if has_stats.scalar():
                stats["games_skipped_done"] += 1
                continue
            else:
                logger.info(f"GameSync: re-processing dead game record {game_id_str}")
                await session.execute(
                    _text("DELETE FROM fall_of_wickets WHERE game_id=:gid"), {"gid": str(game_uuid)}
                )
                await session.execute(
                    _text("DELETE FROM partnerships WHERE game_id=:gid"), {"gid": str(game_uuid)}
                )
                await session.execute(
                    _text("DELETE FROM bowling_spells WHERE game_id=:gid"), {"gid": str(game_uuid)}
                )
                await session.execute(
                    _text("DELETE FROM games WHERE id=:gid"), {"gid": str(game_uuid)}
                )
                try:
                    await session.commit()
                except Exception as e:
                    logger.error(f"GameSync: dead-game delete commit failed for {game_id_str}: {e}")
                    await session.rollback()
                    continue

        s_name = (game_data.get("season") or "").strip().lower()
        season = season_by_name.get(s_name)
        if not season:
            played_str = game_data.get("played_at", "")
            year = played_str[:4] if played_str else ""
            season = next(
                (s for s in season_by_name.values()
                 if str(s["year"]) == year or str((s["year"] or 0) + 1) == year),
                None,
            )
        if not season:
            logger.warning(f"GameSync: no season match for game {game_id_str} (season={s_name!r})")
            stats["games_skipped_season"] += 1
            continue

        grade_phq = game_data.get("grade_id") or ""
        try:
            grade_uuid = uuid.UUID(grade_phq)
        except (ValueError, TypeError):
            logger.warning(f"GameSync: invalid grade_id {grade_phq!r} for game {game_id_str}")
            continue

        grade = await session.get(Grade, grade_uuid)
        if not grade:
            grade_name = (game_data.get("grade") or {}).get("name", "Unknown Grade")
            grade = Grade(id=grade_uuid, season_id=season["id"], name=grade_name, playhq_id=grade_phq)
            session.add(grade)
            try:
                await session.flush()
            except Exception as e:
                logger.error(f"GameSync: flush failed for grade {grade_uuid} in game {game_id_str}: {e}")
                await session.rollback()
                continue

        played_at = None
        try:
            played_at = date_cls.fromisoformat(game_data["played_at"]) if game_data.get("played_at") else None
        except ValueError:
            pass

        game_obj = Game(
            id=game_uuid,
            grade_id=grade.id,
            played_at=played_at,
            home_team=game_data.get("home_team", ""),
            away_team=game_data.get("away_team", ""),
            result=game_data.get("result"),
            winning_team=game_data.get("winning_team"),
        )
        session.add(game_obj)
        try:
            await session.flush()
        except Exception as e:
            logger.error(f"GameSync: flush failed for game {game_id_str}: {e}")
            await session.rollback()
            continue

        try:
            scorecard = await playhq_partner_client.get_fixture_scorecard(
                game_id_str, game_url=game_data.get("url", "")
            )
        except Exception as e:
            logger.warning(f"GameSync: scorecard fetch failed for {game_id_str}: {e}")
            await session.rollback()
            continue

        innings_list = scorecard.get("innings") or []
        batting_stored = 0
        bowling_stored = 0
        partnerships_stored = 0

        for innings in innings_list:
            inn_num = innings.get("innings_number", 1)

            for row in innings.get("batting", []):
                pid = phq_to_pid.get(row.get("playhq_appearance_id") or "")
                if not pid:
                    name_lc = (row.get("name") or "").strip().lower()
                    pid = name_to_pid.get(name_lc) if name_lc else None
                if not pid:
                    continue
                session.add(BattingInnings(
                    game_id=game_uuid,
                    player_id=pid,
                    innings_number=inn_num,
                    runs=row.get("runs"),
                    balls=row.get("balls"),
                    fours=row.get("fours"),
                    sixes=row.get("sixes"),
                    not_out=row.get("not_out", False),
                    dismissal_type=row.get("how_out") or None,
                    batting_position=row.get("batting_position"),
                ))
                batting_stored += 1

            for row in innings.get("bowling", []):
                pid = phq_to_pid.get(row.get("playhq_appearance_id") or "")
                if not pid:
                    name_lc = (row.get("name") or "").strip().lower()
                    pid = name_to_pid.get(name_lc) if name_lc else None
                if not pid:
                    continue
                overs_val = None
                try:
                    overs_val = float(row["overs"]) if row.get("overs") is not None else None
                except (ValueError, TypeError):
                    pass
                session.add(BowlingSpell(
                    game_id=game_uuid,
                    player_id=pid,
                    innings_number=inn_num,
                    overs=overs_val,
                    maidens=row.get("maidens"),
                    runs=row.get("runs"),
                    wickets=row.get("wickets"),
                    wides=row.get("wides"),
                    no_balls=row.get("no_balls"),
                    economy=row.get("economy"),
                ))
                bowling_stored += 1

            for fow in (innings.get("fall_of_wickets") or []):
                wkt_num = fow.get("wicket_number") or None
                if wkt_num is None:
                    continue  # wicket_number is NOT NULL in DB — skip malformed FoW rows
                pid = phq_to_pid.get(fow.get("batter_playhq_id") or "")
                if not pid:
                    name_lc = (fow.get("name") or "").strip().lower()
                    pid = name_to_pid.get(name_lc) if name_lc else None
                session.add(FallOfWicket(
                    game_id=game_uuid,
                    innings_number=inn_num,
                    wicket_number=wkt_num,
                    score_at_fall=fow.get("score_at_fall"),
                    overs_at_fall=fow.get("overs_at_fall"),
                    player_id=pid,
                ))

            batting_with_pos = [r for r in innings.get("batting", []) if r.get("batting_position")]
            fow_data = innings.get("fall_of_wickets") or []
            for p in _derive_partnerships(batting_with_pos, fow_data, phq_to_pid, name_to_pid):
                if p.get("batter1_id") or p.get("batter2_id"):
                    session.add(Partnership(
                        game_id=game_uuid,
                        innings_number=inn_num,
                        wicket_number=p["wicket_number"],
                        batter1_id=p.get("batter1_id"),
                        batter2_id=p.get("batter2_id"),
                        runs=p.get("runs") or 0,
                        batter1_runs=p.get("batter1_runs"),
                        batter2_runs=p.get("batter2_runs"),
                    ))
                    partnerships_stored += 1

        if batting_stored == 0 and bowling_stored == 0:
            sample_names = []
            for inn in (scorecard.get("innings") or [])[:1]:
                sample_names = [(r.get("name"), r.get("playhq_appearance_id")) for r in (inn.get("batting") or [])[:3]]
            logger.warning(
                f"GameSync: no stats for {game_id_str} — "
                f"scorecard innings={len(scorecard.get('innings') or [])}, "
                f"sample batting={sample_names}, "
                f"name_to_pid sample={list(name_to_pid.keys())[:3]}"
            )
            stats["games_skipped_no_stats"] += 1
            await session.rollback()
            continue

        try:
            await session.commit()
            stats["batting"] += batting_stored
            stats["bowling"] += bowling_stored
            stats["partnerships"] += partnerships_stored
            stats["games_new"] += 1
        except Exception as e:
            logger.error(f"GameSync: commit failed for game {game_id_str}: {e}")
            await session.rollback()

    logger.info(f"GameSync: {stats} for org {org_id}")
    return stats


async def _backfill_player_playhq_ids(
    session: AsyncSession,
    org: Organisation,
    all_games: list,
) -> int:
    from app.services import playhq_partner_client

    keyword = org.name.split()[0].lower() if org.name else ""
    final_games = [g for g in all_games if g.get("status") == "FINAL"]
    final_games.sort(key=lambda g: g.get("played_at") or "", reverse=True)

    stamped = 0
    for game in final_games[:50]:
        game_id = game.get("id")
        if not game_id:
            continue
        try:
            appearances, teams = await playhq_partner_client.get_game_appearances(game_id)
        except Exception as e:
            logger.warning(f"Backfill: appearances fetch failed for {game_id}: {e}")
            continue

        matched_team_ids = {
            t["id"] for t in teams
            if keyword and keyword in t.get("name", "").lower()
        }
        keyword_matched = bool(matched_team_ids)
        if not matched_team_ids:
            matched_team_ids = {t["id"] for t in teams if t.get("id")}
            if teams:
                logger.warning(
                    f"Backfill: keyword '{keyword}' matched no teams in game {game_id}; "
                    f"using all {len(matched_team_ids)} teams (name-match only)"
                )

        for app in appearances:
            phq_id = app.get("id")
            team_id = app.get("teamId")
            if not phq_id or team_id not in matched_team_ids:
                continue

            first = app.get("firstName", "")
            last = app.get("lastName", "")
            full_name = f"{first} {last}".strip()
            if not full_name:
                continue

            existing_res = await session.execute(
                select(Player).where(
                    Player.organisation_id == org.id,
                    Player.playhq_id == phq_id,
                )
            )
            if existing_res.scalar_one_or_none():
                continue

            # Match both "Jack Barendse" and "Barendse, Jack" (Grassroots Last-First format)
            name_variants = [full_name.lower()]
            parts = full_name.split(None, 1)
            if len(parts) == 2:
                name_variants.append(f"{parts[1]}, {parts[0]}".lower())

            from sqlalchemy import or_ as _or
            name_res = await session.execute(
                select(Player).where(
                    Player.organisation_id == org.id,
                    _or(*[func.lower(Player.name) == v for v in name_variants]),
                    Player.playhq_id.is_(None),
                ).limit(1)
            )
            player = name_res.scalars().first()
            if player:
                player.playhq_id = phq_id
                stamped += 1
            elif keyword_matched:
                session.add(Player(
                    id=uuid.uuid4(),
                    name=full_name,
                    organisation_id=org.id,
                    playhq_id=phq_id,
                ))
                stamped += 1

        await session.commit()

    logger.info(f"Backfill: stamped/created {stamped} player PlayHQ IDs for org {org.id}")
    return stamped


_RUN_MILESTONES = [50, 100, 250, 500, 1000, 2000, 3000, 5000]
_WICKET_MILESTONES = [5, 10, 25, 50, 100, 200, 300]
_MATCH_MILESTONES = [10, 25, 50, 100, 150, 200]
_CATCH_MILESTONES = [10, 25, 50, 100]


async def _compute_milestones(session: AsyncSession, player_ids: list, org_id: uuid.UUID):
    from sqlalchemy import text
    for pid in player_ids:
        pid_str = str(pid)

        run_res = await session.execute(
            text("SELECT COALESCE(SUM(runs),0) FROM player_season_stats WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        total_runs = int(run_res.scalar() or 0)

        wkt_res = await session.execute(
            text("SELECT COALESCE(SUM(wickets),0) FROM player_season_stats WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        total_wickets = int(wkt_res.scalar() or 0)

        match_res = await session.execute(
            text("SELECT COALESCE(SUM(matches),0) FROM player_season_stats WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        total_matches = int(match_res.scalar() or 0)

        catch_res = await session.execute(
            text("SELECT COALESCE(SUM(catches),0) FROM player_season_stats WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        total_catches = int(catch_res.scalar() or 0)

        exist_res = await session.execute(
            text("SELECT milestone_type, milestone_value FROM milestones WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        existing = {(r[0], r[1]) for r in exist_res.fetchall()}

        new_milestones = []
        today = date.today()

        for threshold in _RUN_MILESTONES:
            if total_runs >= threshold and ("runs", threshold) not in existing:
                new_milestones.append(Milestone(
                    player_id=pid, milestone_type="runs", milestone_value=threshold,
                    detail=f"{threshold:,} career runs", achieved_at=today,
                ))

        for threshold in _WICKET_MILESTONES:
            if total_wickets >= threshold and ("wickets", threshold) not in existing:
                new_milestones.append(Milestone(
                    player_id=pid, milestone_type="wickets", milestone_value=threshold,
                    detail=f"{threshold} career wickets", achieved_at=today,
                ))

        for threshold in _MATCH_MILESTONES:
            if total_matches >= threshold and ("matches", threshold) not in existing:
                new_milestones.append(Milestone(
                    player_id=pid, milestone_type="matches", milestone_value=threshold,
                    detail=f"{threshold} career matches", achieved_at=today,
                ))

        for threshold in _CATCH_MILESTONES:
            if total_catches >= threshold and ("catches", threshold) not in existing:
                new_milestones.append(Milestone(
                    player_id=pid, milestone_type="catches", milestone_value=threshold,
                    detail=f"{threshold} career catches", achieved_at=today,
                ))

        for m in new_milestones:
            session.add(m)

    if player_ids:
        await session.commit()


async def deep_sync_player(org_id_str: str, player_id_str: str) -> dict:
    """Re-process ALL games for an org, forcing reprocessing for any game that involves the target player."""
    from app.models.db import PlayerSyncRequest
    from app.services import playhq_partner_client

    logger.info(f"DeepSync: starting for player {player_id_str} in org {org_id_str}")

    async with async_session_maker() as session:
        org = await session.get(Organisation, uuid.UUID(org_id_str))
        if not org or not org.playhq_id:
            return {"error": "Organisation not found or missing playhq_id"}

        player = await session.get(Player, uuid.UUID(player_id_str))
        if not player:
            return {"error": "Player not found"}

        player_name = (player.name or "").strip().lower()
        player_phq_id = player.playhq_id

        # Build full name lookup set for this player
        player_names: set[str] = {player_name}
        if "," in player_name:
            parts = [x.strip() for x in player_name.split(",", 1)]
            if len(parts) == 2:
                player_names.add(f"{parts[1]} {parts[0]}")
        else:
            words = player_name.split()
            if len(words) >= 2:
                player_names.add(f"{' '.join(words[1:])}, {words[0]}")

        if player.display_name_override:
            player_names.add(player.display_name_override.strip().lower())

        logger.info(f"DeepSync: player name variants: {player_names}, phq_id={player_phq_id}")

        all_games = await playhq_partner_client.get_org_games(
            org.playhq_id,
            org.name,
        )
        final_games = [g for g in all_games if g.get("status") == "FINAL"]
        logger.info(f"DeepSync: found {len(final_games)} final games for org")

        seasons_res = await session.execute(
            select(Season).where(Season.organisation_id == org.id)
        )
        season_by_name = {
            s.name.strip().lower(): {"id": s.id, "year": s.year}
            for s in seasons_res.scalars().all() if s.name
        }

        players_res = await session.execute(
            select(Player).where(Player.organisation_id == org.id)
        )
        phq_to_pid: dict[str, uuid.UUID] = {}
        name_to_pid: dict[str, uuid.UUID] = {}
        for p in players_res.scalars().all():
            if p.playhq_id:
                phq_to_pid[p.playhq_id] = p.id
            n = (p.name or "").strip().lower()
            if not n:
                continue
            name_to_pid[n] = p.id
            if "," in n:
                pts = [x.strip() for x in n.split(",", 1)]
                if len(pts) == 2:
                    name_to_pid[f"{pts[1]} {pts[0]}"] = p.id
            else:
                wds = n.split()
                if len(wds) >= 2:
                    name_to_pid[f"{' '.join(wds[1:])}, {wds[0]}"] = p.id

        stats = {"games_checked": 0, "games_reprocessed": 0, "batting": 0, "bowling": 0, "partnerships": 0}

        for game_data in final_games:
            game_id_str = game_data.get("id")
            if not game_id_str:
                continue
            try:
                game_uuid = uuid.UUID(game_id_str)
            except ValueError:
                continue

            stats["games_checked"] += 1

            # Check if this game already has a batting row for our player
            player_has_row = await session.execute(
                text("SELECT 1 FROM batting_innings WHERE game_id=:gid AND player_id=:pid LIMIT 1"),
                {"gid": str(game_uuid), "pid": player_id_str},
            )
            if player_has_row.scalar():
                continue  # Already processed for this player

            # Force delete and reprocess this game's stats
            try:
                await session.execute(text("DELETE FROM fall_of_wickets WHERE game_id=:gid"), {"gid": str(game_uuid)})
                await session.execute(text("DELETE FROM partnerships WHERE game_id=:gid"), {"gid": str(game_uuid)})
                await session.execute(text("DELETE FROM bowling_spells WHERE game_id=:gid"), {"gid": str(game_uuid)})
                await session.execute(text("DELETE FROM batting_innings WHERE game_id=:gid"), {"gid": str(game_uuid)})
                await session.execute(text("DELETE FROM games WHERE id=:gid"), {"gid": str(game_uuid)})
                await session.commit()
            except Exception as e:
                logger.error(f"DeepSync: delete failed for game {game_id_str}: {e}")
                await session.rollback()
                continue

            # Re-fetch and store game
            try:
                scorecard = await playhq_partner_client.get_fixture_scorecard(
                    game_id_str,
                    grade_id=game_data.get("grade_id", ""),
                    game_url=game_data.get("url", ""),
                )
            except Exception as e:
                logger.warning(f"DeepSync: scorecard fetch failed for {game_id_str}: {e}")
                continue

            s_name = (game_data.get("season") or "").strip().lower()
            season = season_by_name.get(s_name)
            if not season:
                played_str = game_data.get("played_at", "")
                year_str = played_str[:4] if played_str else ""
                season = next(
                    (v for v in season_by_name.values() if str(v.get("year", "")) == year_str),
                    None,
                )

            grade_phq = game_data.get("grade_id") or ""
            try:
                grade_uuid = uuid.UUID(grade_phq)
            except (ValueError, TypeError):
                grade_uuid = None

            grade = await session.get(Grade, grade_uuid) if grade_uuid else None

            played_str = game_data.get("played_at", "")
            try:
                played_date = date.fromisoformat(played_str) if played_str else None
            except ValueError:
                played_date = None

            new_game = Game(
                id=game_uuid,
                grade_id=grade.id if grade else None,
                played_at=played_date,
                home_team=game_data.get("home_team", ""),
                away_team=game_data.get("away_team", ""),
                result=game_data.get("result"),
                winning_team=game_data.get("winning_team"),
            )
            session.add(new_game)
            try:
                await session.commit()
            except Exception as e:
                logger.error(f"DeepSync: game insert failed for {game_id_str}: {e}")
                await session.rollback()
                continue

            innings_list = scorecard.get("innings") or []
            batting_stored = bowling_stored = partnerships_stored = 0

            for inn in innings_list:
                batting_rows = inn.get("batting") or []
                bowling_rows = inn.get("bowling") or []
                fow_rows = inn.get("fall_of_wickets") or []
                innings_num = inn.get("innings_number", 1)

                batting_with_pos = []
                for pos, row in enumerate(batting_rows, 1):
                    pid = phq_to_pid.get(row.get("playhq_appearance_id") or "")
                    if not pid:
                        name_lc = (row.get("name") or "").strip().lower()
                        pid = name_to_pid.get(name_lc) if name_lc else None

                    batting_with_pos.append({**row, "_pid": pid, "_pos": pos})
                    if pid:
                        bi = BattingInnings(
                            game_id=game_uuid,
                            player_id=pid,
                            innings_number=innings_num,
                            batting_position=pos,
                            runs=row.get("runs") or 0,
                            balls=row.get("balls") or 0,
                            fours=row.get("fours") or 0,
                            sixes=row.get("sixes") or 0,
                            not_out=row.get("not_out", False),
                            dismissal_type=row.get("how_out"),
                        )
                        session.add(bi)
                        batting_stored += 1

                for row in bowling_rows:
                    pid = phq_to_pid.get(row.get("playhq_appearance_id") or "")
                    if not pid:
                        name_lc = (row.get("name") or "").strip().lower()
                        pid = name_to_pid.get(name_lc) if name_lc else None
                    if pid:
                        overs_val = None
                        try:
                            overs_val = float(row["overs"]) if row.get("overs") is not None else None
                        except (ValueError, TypeError):
                            pass
                        bs = BowlingSpell(
                            game_id=game_uuid,
                            player_id=pid,
                            innings_number=innings_num,
                            overs=overs_val,
                            maidens=row.get("maidens"),
                            runs=row.get("runs"),
                            wickets=row.get("wickets"),
                            wides=row.get("wides"),
                            no_balls=row.get("no_balls"),
                            economy=row.get("economy"),
                        )
                        session.add(bs)
                        bowling_stored += 1

                for p in _derive_partnerships(batting_with_pos, fow_rows, phq_to_pid, name_to_pid):
                    session.add(Partnership(
                        game_id=game_uuid,
                        innings_number=innings_num,
                        wicket_number=p["wicket_number"],
                        batter1_id=p.get("batter1_id"),
                        batter2_id=p.get("batter2_id"),
                        runs=p.get("runs") or 0,
                        batter1_runs=p.get("batter1_runs"),
                        batter2_runs=p.get("batter2_runs"),
                    ))
                    partnerships_stored += 1

            if batting_stored == 0 and bowling_stored == 0:
                await session.rollback()
                continue

            try:
                await session.commit()
                stats["batting"] += batting_stored
                stats["bowling"] += bowling_stored
                stats["partnerships"] += partnerships_stored
                stats["games_reprocessed"] += 1
            except Exception as e:
                logger.error(f"DeepSync: commit failed for game {game_id_str}: {e}")
                await session.rollback()

        logger.info(f"DeepSync: complete for player {player_id_str}: {stats}")
        return stats


async def process_game_updated_webhook(payload: dict):
    """Handle GAME.UPDATED webhook event."""


async def suggest_phq_ids(org_id_str: str) -> dict:
    """
    Scan game appearances to suggest PlayHQ ID → player links.
    - Exact name match, unique: auto-link immediately (no admin needed)
    - Exact name match, already used by another player: create 'high' confidence suggestion
    - Partial/initial match: create 'low' confidence suggestion
    Returns counts: {auto_linked, high, low, already_linked, skipped}
    """
    from app.services import playhq_partner_client
    from datetime import datetime, timezone

    logger.info(f"PhqSuggest: starting for org {org_id_str}")

    stats = {"auto_linked": 0, "high": 0, "low": 0, "already_linked": 0, "skipped": 0}

    async with async_session_maker() as session:
        org = await session.get(Organisation, uuid.UUID(org_id_str))
        if not org or not org.playhq_id:
            return {"error": "Organisation not found or missing playhq_id"}

        # Load all org players into lookup structures
        players_res = await session.execute(
            select(Player).where(Player.organisation_id == org.id)
        )
        all_players = players_res.scalars().all()

        # phq_id → player (already linked)
        phq_to_player: dict[str, Player] = {}
        # normalised name → [players] (for matching)
        name_to_players: dict[str, list[Player]] = {}

        def _norm(s: str) -> str:
            return (s or "").strip().lower()

        for p in all_players:
            if p.playhq_id:
                phq_to_player[p.playhq_id] = p
            n = _norm(p.name)
            if n:
                name_to_players.setdefault(n, []).append(p)
                # also index the reversed form
                if "," in n:
                    parts = [x.strip() for x in n.split(",", 1)]
                    rev = f"{parts[1]} {parts[0]}" if len(parts) == 2 else n
                    name_to_players.setdefault(rev, []).append(p)
                else:
                    words = n.split()
                    if len(words) >= 2:
                        rev = f"{' '.join(words[1:])}, {words[0]}"
                        name_to_players.setdefault(rev, []).append(p)

        # Fetch all org games
        all_games = await playhq_partner_client.get_org_games(org.playhq_id, org.name)
        final_games = [g for g in all_games if g.get("status") == "FINAL"]
        logger.info(f"PhqSuggest: {len(final_games)} final games to scan")

        # Collect unique PHQ player appearances: phq_id → {first, last, game_count}
        phq_appearances: dict[str, dict] = {}
        keyword = org.name.split()[0].lower() if org.name else ""

        for game_data in final_games:
            game_id = game_data.get("id")
            if not game_id:
                continue
            try:
                appearances, teams = await playhq_partner_client.get_game_appearances(game_id)
            except Exception:
                continue

            matched_team_ids = {
                t["id"] for t in teams
                if keyword and keyword in t.get("name", "").lower()
            }
            if not matched_team_ids:
                matched_team_ids = {t["id"] for t in teams if t.get("id")}

            for app in appearances:
                phq_id = app.get("id")
                team_id = app.get("teamId")
                if not phq_id or team_id not in matched_team_ids:
                    continue
                if phq_id in phq_appearances:
                    phq_appearances[phq_id]["game_count"] += 1
                else:
                    phq_appearances[phq_id] = {
                        "first": app.get("firstName", ""),
                        "last": app.get("lastName", ""),
                        "game_count": 1,
                    }

        logger.info(f"PhqSuggest: found {len(phq_appearances)} unique PHQ player IDs")

        # Load existing suggestions to avoid duplicates
        existing_sugg_res = await session.execute(
            select(PhqIdSuggestion.phq_player_id)
            .where(PhqIdSuggestion.org_id == org.id)
        )
        existing_phq_ids = {r[0] for r in existing_sugg_res.all()}

        now = datetime.now(timezone.utc)

        for phq_id, info in phq_appearances.items():
            first = info["first"]
            last = info["last"]
            game_count = info["game_count"]
            full_name = f"{first} {last}".strip()
            full_name_rev = f"{last}, {first}".strip(", ")

            # Already linked to a player
            if phq_id in phq_to_player:
                stats["already_linked"] += 1
                continue

            # Find candidate players by exact name match
            candidates: list[Player] = []
            for variant in [_norm(full_name), _norm(full_name_rev)]:
                for p in name_to_players.get(variant, []):
                    if p not in candidates:
                        candidates.append(p)

            # Also try initial match: "R Wilton" → match "Rob Wilton" / "Wilton, Rob"
            initial_candidates: list[Player] = []
            if not candidates and last:
                last_norm = _norm(last)
                first_initial = first[:1].lower() if first else ""
                for n, ps in name_to_players.items():
                    if last_norm in n and first_initial and n.startswith(first_initial):
                        for p in ps:
                            if p not in initial_candidates:
                                initial_candidates.append(p)
                    elif last_norm in n and last_norm == n.split()[-1]:
                        for p in ps:
                            if p not in initial_candidates:
                                initial_candidates.append(p)

            if not candidates and not initial_candidates:
                stats["skipped"] += 1
                continue

            # Determine confidence and action
            if len(candidates) == 1 and candidates[0].playhq_id is None:
                player = candidates[0]
                # Auto-link — exact unique match, player has no PHQ ID yet
                player.playhq_id = phq_id
                phq_to_player[phq_id] = player
                await session.commit()
                stats["auto_linked"] += 1
                logger.info(f"PhqSuggest: auto-linked {full_name} → {player.name} (phq={phq_id})")
                continue

            # Need admin review — create suggestion if not already exists
            if phq_id in existing_phq_ids:
                continue

            if candidates:
                confidence = "high"
                matched_player = candidates[0] if len(candidates) == 1 else None
            else:
                confidence = "low"
                matched_player = initial_candidates[0] if len(initial_candidates) == 1 else None

            sugg = PhqIdSuggestion(
                org_id=org.id,
                player_id=matched_player.id if matched_player else None,
                phq_player_id=phq_id,
                phq_first_name=first,
                phq_last_name=last,
                confidence=confidence,
                game_count=game_count,
                status="pending",
            )
            session.add(sugg)
            existing_phq_ids.add(phq_id)
            if confidence == "high":
                stats["high"] += 1
            else:
                stats["low"] += 1

        await session.commit()

    logger.info(f"PhqSuggest: done for org {org_id_str}: {stats}")
    return stats
