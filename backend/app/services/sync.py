import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.models.db import (
    Organisation, Season, Grade, Game, Player,
    BattingInnings, BowlingSpell, FieldingStat, async_session_maker
)
from app.services import playhq_client

logger = logging.getLogger(__name__)


def _parse_uuid(val: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError):
        return None


def _extract_player_stats(game_summary: dict, game_id: uuid.UUID) -> dict:
    """
    Parse the PlayHQ game summary payload into structured stat rows.
    Returns dict with keys: players, batting, bowling, fielding.
    """
    players = {}
    batting = []
    bowling = []
    fielding = []

    innings_list = game_summary.get("innings", [])
    for innings in innings_list:
        team = innings.get("team", {})

        # Batting
        for i, batter in enumerate(innings.get("batting", [])):
            participant = batter.get("participant", {})
            pid_raw = participant.get("id")
            if not pid_raw:
                continue
            pid = _parse_uuid(pid_raw)
            if not pid:
                continue

            players[pid] = participant.get("displayName", "Unknown")

            runs = batter.get("runs", 0) or 0
            balls = batter.get("balls", 0) or 0
            fours = batter.get("fours", 0) or 0
            sixes = batter.get("sixes", 0) or 0
            not_out = batter.get("notOut", False)
            dismissal = batter.get("dismissalType", "")
            sr = round(runs / balls * 100, 2) if balls > 0 else 0.0

            batting.append({
                "game_id": game_id,
                "player_id": pid,
                "runs": runs,
                "balls": balls,
                "fours": fours,
                "sixes": sixes,
                "strike_rate": sr,
                "dismissal_type": dismissal,
                "not_out": not_out,
                "batting_position": i + 1,
            })

        # Bowling
        for bowler in innings.get("bowling", []):
            participant = bowler.get("participant", {})
            pid_raw = participant.get("id")
            if not pid_raw:
                continue
            pid = _parse_uuid(pid_raw)
            if not pid:
                continue

            players[pid] = participant.get("displayName", "Unknown")

            overs_raw = bowler.get("overs", 0) or 0
            runs_conceded = bowler.get("runs", 0) or 0
            wickets = bowler.get("wickets", 0) or 0
            maidens = bowler.get("maidens", 0) or 0
            wides = bowler.get("wides", 0) or 0
            no_balls = bowler.get("noBalls", 0) or 0
            economy = round(runs_conceded / overs_raw, 2) if overs_raw > 0 else 0.0

            bowling.append({
                "game_id": game_id,
                "player_id": pid,
                "overs": overs_raw,
                "maidens": maidens,
                "runs": runs_conceded,
                "wickets": wickets,
                "wides": wides,
                "no_balls": no_balls,
                "economy": economy,
            })

        # Fielding
        fielding_data = innings.get("fielding", [])
        for fielder in fielding_data:
            participant = fielder.get("participant", {})
            pid_raw = participant.get("id")
            if not pid_raw:
                continue
            pid = _parse_uuid(pid_raw)
            if not pid:
                continue

            players[pid] = participant.get("displayName", "Unknown")

            fielding.append({
                "game_id": game_id,
                "player_id": pid,
                "catches": fielder.get("catches", 0) or 0,
                "run_outs": fielder.get("runOuts", 0) or 0,
                "stumpings": fielder.get("stumpings", 0) or 0,
            })

    return {"players": players, "batting": batting, "bowling": bowling, "fielding": fielding}


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
        org.name = org_data.get("name", org.name)
    await session.commit()
    return org


async def sync_organisation(org_id_str: str) -> dict:
    """
    Full historical sync for an organisation.
    Returns progress summary dict.
    """
    logger.info(f"Starting sync for org {org_id_str}")

    org_data = await playhq_client.get_organisation(org_id_str)
    if not org_data:
        return {"error": "Organisation not found", "org_id": org_id_str}

    stats = {"seasons": 0, "grades": 0, "games": 0, "players": 0}

    async with async_session_maker() as session:
        org = await upsert_organisation(session, org_data)
        org_id = org.id

        seasons = await playhq_client.get_seasons(org_id_str)
        logger.info(f"Found {len(seasons)} seasons")

        for season_data in seasons:
            season_id = _parse_uuid(season_data.get("id", ""))
            if not season_id:
                continue

            season = await session.get(Season, season_id)
            if not season:
                season = Season(
                    id=season_id,
                    organisation_id=org_id,
                    name=season_data.get("name", ""),
                    year=season_data.get("year"),
                )
                session.add(season)
            season.synced_at = datetime.now(timezone.utc)
            await session.commit()
            stats["seasons"] += 1

            grades = await playhq_client.get_grades(str(season_id))
            for grade_data in grades:
                grade_id = _parse_uuid(grade_data.get("id", ""))
                if not grade_id:
                    continue

                grade = await session.get(Grade, grade_id)
                if not grade:
                    grade = Grade(
                        id=grade_id,
                        season_id=season_id,
                        name=grade_data.get("name", ""),
                    )
                    session.add(grade)
                    await session.commit()
                stats["grades"] += 1

                fixtures = await playhq_client.get_fixtures(str(grade_id))
                game_ids = [f.get("id") for f in fixtures if f.get("id")]

                for game_id_raw in game_ids:
                    game_id = _parse_uuid(game_id_raw)
                    if not game_id:
                        continue

                    existing_game = await session.get(Game, game_id)
                    if existing_game and existing_game.raw_payload:
                        continue

                    summary = await playhq_client.get_game_summary(game_id_raw)
                    if not summary:
                        continue

                    await _upsert_game(session, summary, game_id, grade_id, org_id)
                    stats["games"] += 1

        logger.info(f"Sync complete: {stats}")
        return stats


async def _upsert_game(
    session: AsyncSession,
    summary: dict,
    game_id: uuid.UUID,
    grade_id: uuid.UUID,
    org_id: uuid.UUID,
):
    result_data = summary.get("result", {})
    played_at_raw = summary.get("dateTime") or summary.get("date")
    played_at = None
    if played_at_raw:
        try:
            played_at = datetime.fromisoformat(played_at_raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    game = await session.get(Game, game_id)
    if not game:
        game = Game(
            id=game_id,
            grade_id=grade_id,
            played_at=played_at,
            home_team=summary.get("homeTeam", {}).get("name", ""),
            away_team=summary.get("awayTeam", {}).get("name", ""),
            result=result_data.get("type", ""),
            winning_team=result_data.get("winningTeam", {}).get("name", "") if result_data.get("winningTeam") else "",
            raw_payload=summary,
        )
        session.add(game)
    else:
        game.raw_payload = summary
        game.result = result_data.get("type", game.result)
    await session.commit()

    extracted = _extract_player_stats(summary, game_id)

    # Upsert players
    for pid, name in extracted["players"].items():
        player = await session.get(Player, pid)
        if not player:
            player = Player(id=pid, name=name, organisation_id=org_id)
            session.add(player)
    await session.commit()

    # Remove old stats for this game then insert fresh
    await session.execute(delete(BattingInnings).where(BattingInnings.game_id == game_id))
    await session.execute(delete(BowlingSpell).where(BowlingSpell.game_id == game_id))
    await session.execute(delete(FieldingStat).where(FieldingStat.game_id == game_id))

    for row in extracted["batting"]:
        session.add(BattingInnings(**row))
    for row in extracted["bowling"]:
        session.add(BowlingSpell(**row))
    for row in extracted["fielding"]:
        session.add(FieldingStat(**row))

    await session.commit()


async def process_game_updated_webhook(payload: dict):
    """Handle GAME.UPDATED webhook event."""
    game_data = payload.get("game", payload.get("data", {}))
    game_id_raw = game_data.get("id")
    if not game_id_raw:
        logger.warning("Webhook GAME.UPDATED missing game id")
        return

    summary = await playhq_client.get_game_summary(game_id_raw)
    if not summary:
        return

    game_id = _parse_uuid(game_id_raw)
    async with async_session_maker() as session:
        existing = await session.get(Game, game_id)
        if existing and existing.grade_id:
            grade = await session.get(Grade, existing.grade_id)
            season = await session.get(Season, grade.season_id) if grade else None
            org_id = season.organisation_id if season else None
            if org_id:
                await _upsert_game(session, summary, game_id, existing.grade_id, org_id)
                logger.info(f"Webhook: updated game {game_id_raw}")
