import logging
import uuid
from datetime import datetime, timezone, date
from typing import Optional

# Rolling in-memory sync log (last 30 entries per org, survives only until restart)
_sync_log: dict[str, list] = {}

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from sqlalchemy.sql import func

from app.models.db import (
    Organisation, Season, Grade, Game, Player,
    BattingInnings, BowlingSpell, FallOfWicket, Partnership,
    PlayerSeasonStats, Milestone, async_session_maker
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

    stats = {"seasons": 0, "players": 0, "season_stats": 0}

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
                logger.info(f"PlayHQ: {len(all_games)} total games, {sum(1 for g in all_games if g.get('status') == 'FINAL')} FINAL")
            except Exception as e:
                logger.error(f"PlayHQ get_org_games failed for {org_id_str}: {e}\n{_tb.format_exc()}")
                all_games = []

            if all_games:
                try:
                    await _backfill_player_playhq_ids(session, org, all_games)
                except Exception as e:
                    logger.error(f"PlayHQ backfill failed for {org_id_str}: {e}\n{_tb.format_exc()}")
                try:
                    await sync_game_level_data(session, org, all_games)
                except Exception as e:
                    logger.error(f"PlayHQ game-level sync failed for {org_id_str}: {e}\n{_tb.format_exc()}")

        logger.info(f"Sync complete: {stats}")
        _record_sync_log(org_id_str, started_at, stats)
        return stats
