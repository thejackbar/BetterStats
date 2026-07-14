import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from sqlalchemy.sql import func

from app.models.db import (
    Organisation, Season, Grade, Game, Player,
    BattingInnings, BowlingSpell, FieldingStat, FallOfWicket, Partnership, GameAppearance,
    BowlerWicket,
    PlayerSeasonStats, PlayerSeasonGradeStats, Milestone,
    SyncRun, async_session_maker
)
from app.services import playhq_client
from app.services.grade_labels import suggest_category

logger = logging.getLogger(__name__)

_TEAM_SUFFIX_RE = re.compile(
    r'\s+(\d+(?:st|nd|rd|th)s?(?:\s+XI)?|XI|[A-Za-z]\s+Grade)\s*$',
    re.IGNORECASE,
)


def strip_team_suffix(name: str) -> str:
    """Return the club name by stripping grade/team-number suffixes.

    'North Perth 2nd XI' -> 'North Perth'
    'Applecross 1sts'    -> 'Applecross'
    'South Perth A Grade'-> 'South Perth'
    'North Perth'        -> 'North Perth'  (no suffix — unchanged)
    """
    if not name:
        return name
    stripped = _TEAM_SUFFIX_RE.sub('', name).strip()
    return stripped or name


def classify_match_result(scorecard: dict, our_org_id_str: str) -> Optional[str]:
    """Return 'WIN' / 'LOSS' / 'DRAW' / None for our team in this match.

    PlayHQ two-day matches use compound resultType strings — the prefix
    carries the overall match outcome (WON_OUTRIGHT_*, LOST_OUTRIGHT_*,
    DRAWN_*_FIRST_INNINGS). The suffix records the first-innings result,
    which we don't surface as a separate bucket here.
    """
    teams_data = scorecard.get("teams") or []
    our_team = next(
        (t for t in teams_data
         if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == our_org_id_str.lower()),
        None,
    )
    if not our_team:
        return None
    our_team_id = (our_team.get("id") or "").lower()
    summary_teams = (scorecard.get("matchSummary") or {}).get("teams") or []
    for st in summary_teams:
        if (st.get("id") or "").lower() != our_team_id:
            continue
        rt = (st.get("resultType") or "").upper()
        if st.get("isWinner") or rt.startswith("WON"):
            return "WIN"
        if rt.startswith("LOST"):
            return "LOSS"
        if rt.startswith("DRAWN") or rt in ("DREW", "TIED"):
            return "DRAW"
        return None
    return None


def _parse_uuid(val: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError):
        return None


def _org_player_id(org_id: uuid.UUID, grassroots_guid: str) -> uuid.UUID:
    """Per-club player id derived from the org + raw CA participant GUID.

    Mirrors the Season id scheme (uuid5(org, grassroots_id)). A CA participant
    GUID is shared across every club a person plays for, so it can't be a global
    primary key — this gives each club its own deterministic id for that person.
    """
    return uuid.uuid5(org_id, grassroots_guid)


async def _resolve_org_player(
    session: AsyncSession,
    org_id: uuid.UUID,
    org_player_map: dict[str, uuid.UUID],
    grassroots_guid: str,
    name: str,
    merged_away: dict,
) -> Optional[uuid.UUID]:
    """Resolve a CA participant GUID to this org's player id, creating a per-club
    player (id = uuid5(org, guid)) the first time the org sees that GUID.

    ``org_player_map`` is a ``grassroots_id -> player_id`` cache for the org and
    is updated in place. Returns ``None`` when the GUID belongs to a player that
    was merged away (so the caller redirects via ``merged_away`` rather than
    recreating it). Legacy single-club orgs are unaffected: their existing rows
    already sit in the map keyed by their raw GUID, so this returns the same
    raw-GUID id it always did.
    """
    pid = org_player_map.get(grassroots_guid)
    if pid is not None:
        return pid
    # Merged away (legacy merges store the raw GUID as removed_player_id) — don't
    # resurrect it; the caller redirects its stats to the kept player.
    if grassroots_guid in merged_away:
        return None
    guid_uuid = _parse_uuid(grassroots_guid)
    # Only mint a per-club uuid5 id when the raw GUID is ALREADY a player id in
    # another club (the genuine shared-participant collision). Otherwise keep
    # using the raw GUID as the id — that's the legacy scheme the game-level
    # scorecard sync relies on (it matches scorecard participantId == player id),
    # so ordinary single-club players are completely unaffected. Per-club uuid5
    # players are aggregate-only until the game-level sync learns to translate
    # participantId -> player id (a separate, testable step).
    clash = await session.get(Player, guid_uuid) if guid_uuid else None
    new_id = _org_player_id(org_id, grassroots_guid) if clash is not None else guid_uuid
    if new_id is None:
        return None
    session.add(Player(id=new_id, name=name, organisation_id=org_id, grassroots_id=grassroots_guid))
    org_player_map[grassroots_guid] = new_id
    return new_id


async def _resolve_org_grade(
    session: AsyncSession,
    org_id: uuid.UUID,
    org_grade_map: dict[str, uuid.UUID],
    grassroots_guid: str,
    name: str,
    season_id: uuid.UUID,
) -> Optional[uuid.UUID]:
    """Resolve a CA grade GUID to this org's grade id, creating a per-club grade
    (id = uuid5(org, guid)) the first time the org sees that GUID.

    A CA grade is competition-wide — one GUID is shared by every club in the
    grade — so the raw GUID can't be a global primary key (only the first club to
    sync it would ever own the row). Mirrors the Season/Player per-club id scheme:
    keep the raw GUID in grassroots_id (what the grassroots API is keyed on), and
    only mint a per-club uuid5 id when the raw GUID is ALREADY a grade in another
    club (the genuine shared-grade collision). Otherwise keep the raw GUID as the
    id — that's the legacy scheme, so every club already on the platform and the
    game-level sync that matches grade.id == raw GUID are completely unaffected.

    ``org_grade_map`` is a ``grassroots_id -> grade_id`` cache for the org, updated
    in place; a re-sync finds the existing row here and returns it unchanged.
    """
    gid = org_grade_map.get(grassroots_guid)
    if gid is not None:
        return gid
    guid_uuid = _parse_uuid(grassroots_guid)
    if guid_uuid is None:
        return None
    clash = await session.get(Grade, guid_uuid)
    new_id = uuid.uuid5(org_id, grassroots_guid) if clash is not None else guid_uuid
    session.add(Grade(
        id=new_id, season_id=season_id, name=name, grassroots_id=grassroots_guid,
        category=suggest_category(name),
    ))
    org_grade_map[grassroots_guid] = new_id
    return new_id


async def find_matching_organisation(
    session: AsyncSession, org_id: Optional[uuid.UUID], name: str = "",
    *, include_archived: bool = True,
) -> Optional[Organisation]:
    """Read-only lookup for "is this external club already an Organisation row",
    used both to guard upsert_organisation against duplicates and, at search time
    (self_serve_trial.py), to tell an operator a club is already registered before
    they try to create it again. Three layered checks, same order in both callers:
      1. id match — direct.
      2. playhq_id match — deterministic. If an existing org already has its
         playhq_id populated with the incoming id, this is unambiguously the same
         club seen from the PHQ side.
      3. name match (case-insensitive) — fuzzy fallback for cases where the
         cross-ID-space link was never recorded (e.g. legacy data, or sync came in
         via PHQ before the GR-side playhq_id lookup ran).

    ``include_archived`` — set False for the self-serve "is this club already
    registered" duplicate-check (an archived club should read as available to
    register again, since archiving is meant to make room for exactly that).
    Keep the default True for ``upsert_organisation``'s own dedup guard, which
    must still find and reuse an archived row rather than creating a second one
    for the same CA org — self_serve_trial.py separately un-archives it as part
    of finishing the registration.
    """
    def _ok(o) -> bool:
        return o is not None and (include_archived or o.archived_at is None)

    org = await session.get(Organisation, org_id) if org_id else None
    if not _ok(org):
        org = None

    if not org and org_id:
        q = select(Organisation).where(Organisation.playhq_id == str(org_id))
        if not include_archived:
            q = q.where(Organisation.archived_at.is_(None))
        org = (await session.execute(q)).scalar_one_or_none()

    incoming_name = (name or "").strip()
    if not org and incoming_name:
        q = select(Organisation).where(func.lower(Organisation.name) == incoming_name.lower())
        if not include_archived:
            q = q.where(Organisation.archived_at.is_(None))
        org = (await session.execute(q)).scalar_one_or_none()

    return org


async def upsert_organisation(session: AsyncSession, org_data: dict) -> Organisation:
    org_id = _parse_uuid(org_data.get("id", ""))
    incoming_name = (org_data.get("name") or "").strip()

    org = await find_matching_organisation(session, org_id, incoming_name)
    if org and org.id != org_id:
        logger.warning(
            f"upsert_organisation: incoming id {org_id} / name '{incoming_name}' "
            f"matches existing org {org.id} — reusing to avoid duplicate"
        )

    if not org:
        org = Organisation(
            id=org_id,
            name=incoming_name,
            short_name=org_data.get("shortName", ""),
        )
        session.add(org)
    else:
        org.name = incoming_name or org.name

    await session.commit()
    return org


async def start_sync_run(
    org_id: uuid.UUID,
    kind: str,
    player_id: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with async_session_maker() as session:
        session.add(SyncRun(
            id=run_id,
            org_id=org_id,
            player_id=player_id,
            kind=kind,
            status="running",
            stats={},
        ))
        await session.commit()
    return run_id


async def update_sync_run(run_id: uuid.UUID, stats: dict) -> None:
    """Merge `stats` into the run's existing stats dict (don't replace).

    Each sub-phase (PlayHQ Partner, Grassroots scores) tracks its own keys.
    Merging means keys from earlier phases stay visible on the dashboard even
    while a later phase is writing its own progress.
    """
    from sqlalchemy.orm.attributes import flag_modified
    async with async_session_maker() as session:
        run = await session.get(SyncRun, run_id)
        if run:
            merged = dict(run.stats or {})
            merged.update(stats)
            run.stats = merged
            flag_modified(run, "stats")  # JSON column mutation hint
            run.updated_at = datetime.now(timezone.utc)
            await session.commit()


def _progress(stats: dict, phase: str, pct: float,
              done: Optional[int] = None, total: Optional[int] = None) -> None:
    """Stamp live-progress keys onto a stats dict. update_sync_run merges them
    into the run row so the admin Data Sync page can draw a real percentage
    bar; finish_sync_run strips them again. `pct` is the overall 0-100
    position across the WHOLE sync (phases own fixed slices of the range), so
    the bar never moves backwards between phases. done/total are the current
    phase's counters (None clears a previous phase's counts on merge)."""
    stats["progress_phase"] = phase
    stats["progress_pct"] = max(0, min(100, round(pct)))
    stats["progress_done"] = done
    stats["progress_total"] = total


async def finish_sync_run(run_id: uuid.UUID, stats: dict, error: str = "") -> None:
    """Mark a run as final. Stats here are merged on top of whatever is in the
    DB — preserves intermediate updates from sub-phases."""
    from sqlalchemy.orm.attributes import flag_modified
    async with async_session_maker() as session:
        run = await session.get(SyncRun, run_id)
        if not run:
            return
        merged = dict(run.stats or {})
        merged.update(stats)
        # Progress keys only matter while the run is live — drop them so
        # finished history rows don't carry a stale "Saving scorecards · 97%".
        for k in ("progress_phase", "progress_pct", "progress_done", "progress_total"):
            merged.pop(k, None)
        run.stats = merged
        flag_modified(run, "stats")
        run.status = "error" if error else "success"
        run.error = error or None
        now = datetime.now(timezone.utc)
        run.completed_at = now
        run.updated_at = now
        await session.commit()


async def _backfill_missing_season_stats(org_id_str: str) -> int:
    """Insert player_season_stats rows for (player, season) pairs that appear in
    per-game tables but have no aggregate row.

    CA's Grassroots aggregate API can omit low-volume players for older
    seasons. The career-stats queries SUM from player_season_stats, so without
    a row the player reads 0 matches/runs/wickets despite real scorecards.
    Compute a synthetic aggregate from batting_innings + bowling_spells +
    fielding_stats so the headline numbers line up with what we know happened.

    DNB/Absent batting rows are excluded everywhere (matches the v3.0.2.2
    rule that those aren't real innings). Returns the number of rows inserted.
    """
    org_uuid = _parse_uuid(org_id_str)
    if not org_uuid:
        return 0

    async with async_session_maker() as session:
        result = await session.execute(
            text(
                """
                WITH bat_innings AS (
                    SELECT bi.player_id, gr.season_id, bi.game_id,
                           bi.runs, bi.balls, bi.fours, bi.sixes,
                           COALESCE(bi.not_out, FALSE) AS not_out
                    FROM batting_innings bi
                    JOIN games g    ON g.id = bi.game_id
                    JOIN grades gr  ON gr.id = g.grade_id
                    JOIN seasons s  ON s.id = gr.season_id
                    WHERE s.organisation_id = :org_id
                      AND COALESCE(LOWER(bi.dismissal_type), '')
                          NOT IN ('absent', 'did not bat', 'dnb')
                ),
                bowl_spells AS (
                    SELECT bs.player_id, gr.season_id, bs.game_id, bs.innings_number,
                           bs.runs, bs.wickets, bs.maidens,
                           bs.wides, bs.no_balls, bs.overs
                    FROM bowling_spells bs
                    JOIN games g   ON g.id = bs.game_id
                    JOIN grades gr ON gr.id = g.grade_id
                    JOIN seasons s ON s.id = gr.season_id
                    WHERE s.organisation_id = :org_id
                ),
                field_stats AS (
                    SELECT fs.player_id, gr.season_id, fs.game_id,
                           fs.catches, fs.run_outs, fs.stumpings
                    FROM fielding_stats fs
                    JOIN games g   ON g.id = fs.game_id
                    JOIN grades gr ON gr.id = g.grade_id
                    JOIN seasons s ON s.id = gr.season_id
                    WHERE s.organisation_id = :org_id
                ),
                appearances AS (
                    SELECT ga.player_id, gr.season_id, ga.game_id
                    FROM game_appearances ga
                    JOIN games g   ON g.id = ga.game_id
                    JOIN grades gr ON gr.id = g.grade_id
                    JOIN seasons s ON s.id = gr.season_id
                    WHERE s.organisation_id = :org_id
                ),
                pairs AS (
                    SELECT player_id, season_id FROM bat_innings
                    UNION
                    SELECT player_id, season_id FROM bowl_spells
                    UNION
                    SELECT player_id, season_id FROM field_stats
                    UNION
                    SELECT player_id, season_id FROM appearances
                ),
                missing AS (
                    SELECT p.player_id, p.season_id
                    FROM pairs p
                    LEFT JOIN player_season_stats pss
                      ON pss.player_id = p.player_id AND pss.season_id = p.season_id
                    WHERE pss.id IS NULL
                ),
                bat_agg AS (
                    SELECT
                        player_id, season_id,
                        COUNT(*)                                              AS innings,
                        COALESCE(SUM(runs), 0)                                AS runs,
                        SUM(CASE WHEN not_out THEN 1 ELSE 0 END)              AS not_outs,
                        COALESCE(SUM(balls), 0)                               AS balls_faced,
                        SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
                        SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END)          AS hundreds,
                        SUM(CASE WHEN runs = 0 AND NOT not_out THEN 1 ELSE 0 END) AS ducks,
                        MAX(runs)                                             AS high_score,
                        COALESCE(SUM(fours), 0)                               AS fours,
                        COALESCE(SUM(sixes), 0)                               AS sixes,
                        COUNT(DISTINCT game_id)                               AS bat_games
                    FROM bat_innings
                    GROUP BY player_id, season_id
                ),
                bowl_agg AS (
                    SELECT
                        player_id, season_id,
                        COUNT(DISTINCT (game_id, innings_number))             AS bowling_innings,
                        COALESCE(SUM(wickets), 0)                             AS wickets,
                        COALESCE(SUM(runs), 0)                                AS runs_conceded,
                        COALESCE(SUM(maidens), 0)                             AS maidens,
                        COALESCE(SUM(wides), 0)                               AS wides,
                        COALESCE(SUM(no_balls), 0)                            AS no_balls,
                        COALESCE(SUM(
                            FLOOR(COALESCE(overs, 0))::int * 6
                            + ROUND((COALESCE(overs, 0) - FLOOR(COALESCE(overs, 0))) * 10)::int
                        ), 0)                                                 AS total_balls,
                        SUM(CASE WHEN wickets >= 5 THEN 1 ELSE 0 END)         AS five_fors,
                        MAX(wickets)                                          AS best_wkts,
                        COUNT(DISTINCT game_id)                               AS bowl_games
                    FROM bowl_spells
                    GROUP BY player_id, season_id
                ),
                field_agg AS (
                    SELECT
                        player_id, season_id,
                        COALESCE(SUM(catches), 0)                             AS catches,
                        COALESCE(SUM(run_outs), 0)                            AS run_outs,
                        COALESCE(SUM(stumpings), 0)                           AS stumpings,
                        COUNT(DISTINCT game_id)                               AS field_games
                    FROM field_stats
                    GROUP BY player_id, season_id
                ),
                games_count AS (
                    SELECT player_id, season_id, COUNT(DISTINCT game_id) AS matches FROM (
                        SELECT player_id, season_id, game_id FROM bat_innings
                        UNION
                        SELECT player_id, season_id, game_id FROM bowl_spells
                        UNION
                        SELECT player_id, season_id, game_id FROM field_stats
                        UNION
                        SELECT player_id, season_id, game_id FROM appearances
                    ) all_games
                    GROUP BY player_id, season_id
                )
                INSERT INTO player_season_stats (
                    player_id, season_id, matches,
                    batting_innings, runs, not_outs, balls_faced,
                    fifties, hundreds, ducks, high_score, fours, sixes,
                    bowling_innings, wickets, overs, bowling_balls,
                    runs_conceded, maidens, best_bowling_wickets,
                    five_wicket_innings, wides, no_balls,
                    catches, run_outs, stumpings,
                    source
                )
                SELECT
                    m.player_id, m.season_id,
                    COALESCE(gc.matches, 0),
                    COALESCE(ba.innings, 0),
                    COALESCE(ba.runs, 0),
                    COALESCE(ba.not_outs, 0),
                    COALESCE(ba.balls_faced, 0),
                    COALESCE(ba.fifties, 0),
                    COALESCE(ba.hundreds, 0),
                    COALESCE(ba.ducks, 0),
                    ba.high_score,
                    COALESCE(ba.fours, 0),
                    COALESCE(ba.sixes, 0),
                    COALESCE(bo.bowling_innings, 0),
                    COALESCE(bo.wickets, 0),
                    CASE WHEN bo.total_balls IS NULL OR bo.total_balls = 0 THEN 0
                         ELSE (bo.total_balls / 6)::numeric + ((bo.total_balls % 6)::numeric / 10)
                    END,
                    COALESCE(bo.total_balls, 0),
                    COALESCE(bo.runs_conceded, 0),
                    COALESCE(bo.maidens, 0),
                    bo.best_wkts,
                    COALESCE(bo.five_fors, 0),
                    COALESCE(bo.wides, 0),
                    COALESCE(bo.no_balls, 0),
                    COALESCE(fa.catches, 0),
                    COALESCE(fa.run_outs, 0),
                    COALESCE(fa.stumpings, 0),
                    'backfill'
                FROM missing m
                LEFT JOIN bat_agg     ba ON ba.player_id = m.player_id AND ba.season_id = m.season_id
                LEFT JOIN bowl_agg    bo ON bo.player_id = m.player_id AND bo.season_id = m.season_id
                LEFT JOIN field_agg   fa ON fa.player_id = m.player_id AND fa.season_id = m.season_id
                LEFT JOIN games_count gc ON gc.player_id = m.player_id AND gc.season_id = m.season_id
                ON CONFLICT (player_id, season_id) DO NOTHING
                RETURNING 1
                """
            ),
            {"org_id": str(org_uuid)},
        )
        inserted = len(result.fetchall())
        await session.commit()
        if inserted:
            logger.info(f"Backfilled {inserted} player_season_stats rows from per-game data for org {org_id_str}")
        return inserted


# Caps how many org-level syncs can be pulling from the shared, rate-sensitive
# Grassroots proxy at once (see CLAUDE.md's Data Source Topology notes on
# politeness/pagination). Each sync already fans out up to 6 concurrent
# scorecard requests via grassroots_scores_client's own semaphore, so 2
# concurrent org syncs already means up to 12 concurrent proxy requests. The
# weekly scheduled sync (jobs/scheduler.py) awaits one org at a time already,
# so this never affects it — it exists for the case several "Sync Now"
# clicks or self-serve trial registrations land close together from the
# admin UI.
_SYNC_GOVERNOR = asyncio.Semaphore(2)


async def sync_organisation(
    org_id_str: str,
    run_id: Optional[uuid.UUID] = None,
    kind: str = "org_full",
) -> dict:
    """Thin concurrency gate in front of ``_sync_organisation_impl`` — every
    caller (weekly cron, manual Sync Now, Full Rebuild, self-serve trial
    registration) goes through here so the governor above applies uniformly,
    at the one place that actually talks to the shared proxy, rather than
    each call site needing to know about it."""
    if run_id is not None and _SYNC_GOVERNOR.locked():
        await update_sync_run(run_id, {
            "progress_phase": "Queued — waiting for another club's sync to finish",
            "progress_pct": 0, "progress_done": None, "progress_total": None,
        })
    async with _SYNC_GOVERNOR:
        return await _sync_organisation_impl(org_id_str, run_id=run_id, kind=kind)


async def _sync_organisation_impl(
    org_id_str: str,
    run_id: Optional[uuid.UUID] = None,
    kind: str = "org_full",
) -> dict:
    """Full historical sync for an organisation using season-aggregate stats."""
    logger.info(f"Starting sync for org {org_id_str} (run_id={run_id}, kind={kind})")

    org_uuid = _parse_uuid(org_id_str)
    owns_run = run_id is None
    if owns_run and org_uuid:
        run_id = await start_sync_run(org_uuid, kind)

    org_data = await playhq_client.get_organisation(org_id_str)
    if not org_data:
        if run_id:
            await finish_sync_run(run_id, {}, "Organisation not found")
        return {"error": "Organisation not found", "org_id": org_id_str}

    stats = {"seasons": 0, "player_seasons": 0, "season_stats": 0,
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
        if run_id:
            _progress(stats, "Season totals", 1, 0, len(seasons))
            await update_sync_run(run_id, stats)

        # grassroots_id -> player_id for this org's existing players. New players
        # (incl. the second club of a shared CA GUID) are minted as
        # uuid5(org, guid) and added to this map as they're seen. For a legacy
        # single-club org every row's grassroots_id == its raw-GUID id, so this
        # resolves to exactly the same ids sync has always used.
        org_player_map: dict[str, uuid.UUID] = {}
        _opm_res = await session.execute(
            select(Player.grassroots_id, Player.id).where(Player.organisation_id == org_id)
        )
        for _gid, _pid in _opm_res.all():
            if _gid:
                org_player_map[str(_gid)] = _pid

        # grassroots_id -> grade_id for this org's existing grades. Same per-club
        # id scheme as players: a shared CA grade GUID is minted as uuid5(org, guid)
        # the first time this org sees it (when another club already owns the raw
        # GUID), so a club that shares grades with an earlier-synced club gets its
        # own grade rows. Legacy single-club grades have grassroots_id == id, so
        # this resolves to exactly the same ids sync has always used.
        org_grade_map: dict[str, uuid.UUID] = {}
        _ogm_res = await session.execute(
            select(Grade.grassroots_id, Grade.id)
            .join(Season, Grade.season_id == Season.id)
            .where(Season.organisation_id == org_id)
        )
        for _ggid, _grid in _ogm_res.all():
            if _ggid:
                org_grade_map[str(_ggid)] = _grid

        for season_idx, season_data in enumerate(seasons, start=1):
            raw_season_id = (season_data.get("id") or "").strip()
            if not _parse_uuid(raw_season_id):
                continue
            # Cricket Australia's season GUID ("Summer 2025/26") is shared
            # across every club, so it can't be the Season primary key — a
            # second club's sync would collide on the first club's row and
            # overwrite its stats. Derive a per-club season id instead, and
            # keep the raw CA GUID in grassroots_id for the stats API calls.
            season_id = uuid.uuid5(org_id, raw_season_id)

            start_date_str = season_data.get("startDate", "")
            year = int(start_date_str[:4]) if start_date_str else None

            season = await session.get(Season, season_id)
            if not season:
                season = Season(
                    id=season_id,
                    organisation_id=org_id,
                    grassroots_id=raw_season_id,
                    name=season_data.get("name", ""),
                    year=year,
                )
                session.add(season)
            else:
                season.grassroots_id = raw_season_id
                if year is not None and season.year is None:
                    season.year = year
            season.synced_at = datetime.now(timezone.utc)
            await session.commit()
            stats["seasons"] += 1

            # Seed Grade rows from this season's teams. The game-level sync
            # discovers matches by iterating grades from the DB, but the
            # org-level /grades endpoint is empty for clubs whose grades are
            # owned by their association rather than the club itself. Each
            # team, however, carries its grade id — so derive grades here.
            teams_data = await playhq_client.get_teams(org_id_str, raw_season_id)
            for t in teams_data:
                grade_objs = list(t.get("grades") or [])
                if t.get("grade"):
                    grade_objs.append(t["grade"])
                for gd in grade_objs:
                    raw_grade_id = ((gd or {}).get("id") or "").strip()
                    if not _parse_uuid(raw_grade_id):
                        continue
                    # Per-club grade resolution: mints uuid5(org, guid) when this
                    # grade GUID is already owned by another club, else keeps the
                    # raw GUID. Replaces the old global session.get(Grade, guid)
                    # skip that left shared grades attached to whichever club
                    # synced first.
                    await _resolve_org_grade(
                        session, org_id, org_grade_map, raw_grade_id,
                        gd.get("name", "Unknown Grade"), season_id,
                    )
            await session.commit()

            # Fetch season-aggregate stats from grassroots API
            batting_list = await playhq_client.get_batting_stats(org_id_str, raw_season_id)
            bowling_list = await playhq_client.get_bowling_stats(org_id_str, raw_season_id)
            fielding_list = await playhq_client.get_fielding_stats(org_id_str, raw_season_id)

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

            # Build merged-player map so sync doesn't recreate deleted duplicates.
            # Filter by undone_at IS NULL — historically-bad rows get marked undone by
            # an admin op (e.g. merge that was reversed by a later re-merge in the
            # opposite direction; the original entry is stale data poisoning the redirect).
            # Resolve transitively (A→B→C ⇒ A→C) with cycle break so a chain
            # of merges still lands on the final kept player.
            try:
                merge_res = await session.execute(
                    text(
                        "SELECT removed_player_id::text AS removed, keep_player_id::text AS keep "
                        "FROM merge_logs "
                        "WHERE org_id = :org_id AND undone_at IS NULL"
                    ),
                    {"org_id": str(org_id)},
                )
                raw_redirects: dict[str, str] = {r.removed: r.keep for r in merge_res.mappings().all()}
                merged_away: dict[str, uuid.UUID] = {}
                for removed_id, target in raw_redirects.items():
                    seen = {removed_id}
                    while target in raw_redirects and target not in seen:
                        seen.add(target)
                        target = raw_redirects[target]
                    merged_away[removed_id] = uuid.UUID(target)
            except Exception:
                await session.rollback()
                merged_away = {}

            # Resolve each CA participant GUID to this org's player id, minting a
            # per-club player (uuid5(org, guid)) for any GUID the org hasn't seen
            # before. Merged-away GUIDs are skipped (not resurrected).
            for pid, pdata in player_data.items():
                await _resolve_org_player(
                    session, org_id, org_player_map, str(pid), pdata["name"], merged_away
                )
            await session.commit()

            # Replace existing season stats for this season
            await session.execute(
                delete(PlayerSeasonStats).where(PlayerSeasonStats.season_id == season_id)
            )

            processed_in_season: set[uuid.UUID] = set()
            for pid, pdata in player_data.items():
                guid_str = str(pid)
                # Resolve the CA GUID to this org's player id, then redirect a
                # merged-away player to the kept one.
                resolved = org_player_map.get(guid_str) or merged_away.get(guid_str)
                if resolved is None:
                    continue
                effective_pid = merged_away.get(str(resolved), resolved)
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
            stats["player_seasons"] += len(player_data)
            stats["season_stats"] += len(player_data)
            logger.info(f"Season {season_data.get('name')}: {len(player_data)} players synced")
            if run_id:
                # Season totals own 1→40% of the overall bar.
                _progress(stats, "Season totals",
                          1 + 39 * season_idx / max(len(seasons), 1),
                          season_idx, len(seasons))
                await update_sync_run(run_id, stats)

            # Per-grade aggregate sync — same CA endpoints + `gradeId` param.
            # Lets us attribute per-grade match counts exactly instead of
            # heuristically (the org-level stats above collapse grades).
            try:
                grades_for_season = await session.execute(
                    select(Grade.id, Grade.grassroots_id).where(Grade.season_id == season_id)
                )
                grade_ids_this_season = grades_for_season.all()
                if grade_ids_this_season:
                    await session.execute(
                        delete(PlayerSeasonGradeStats).where(
                            PlayerSeasonGradeStats.season_id == season_id
                        )
                    )
                    grade_rows_written = 0
                    for grade_uuid, grade_grassroots in grade_ids_this_season:
                        # The CA stats API is keyed on the raw (shared) grade GUID;
                        # grade_uuid may now be a per-club uuid5 id. grassroots_id
                        # == id for legacy grades, so this is unchanged for them.
                        grade_id_str = grade_grassroots or str(grade_uuid)
                        try:
                            gbat = await playhq_client.get_batting_stats(org_id_str, raw_season_id, grade_id_str)
                            gbowl = await playhq_client.get_bowling_stats(org_id_str, raw_season_id, grade_id_str)
                            gfield = await playhq_client.get_fielding_stats(org_id_str, raw_season_id, grade_id_str)
                        except Exception as e:
                            logger.warning(f"GR per-grade aggregate failed for grade={grade_id_str} season={raw_season_id}: {e}")
                            continue

                        per_grade: dict[uuid.UUID, dict] = {}
                        for p in gbat:
                            pid = _parse_uuid(p.get("id"))
                            if not pid:
                                continue
                            per_grade.setdefault(pid, {})["batting"] = p.get("statistics", {})
                        for p in gbowl:
                            pid = _parse_uuid(p.get("id"))
                            if not pid:
                                continue
                            per_grade.setdefault(pid, {})["bowling"] = p.get("statistics", {})
                        for p in gfield:
                            pid = _parse_uuid(p.get("id"))
                            if not pid:
                                continue
                            per_grade.setdefault(pid, {})["fielding"] = p.get("statistics", {})

                        seen_pids: set[uuid.UUID] = set()
                        for pid, pdata in per_grade.items():
                            guid_str = str(pid)
                            resolved = org_player_map.get(guid_str) or merged_away.get(guid_str)
                            if resolved is None:
                                continue
                            effective_pid = merged_away.get(str(resolved), resolved)
                            if effective_pid in seen_pids:
                                continue
                            seen_pids.add(effective_pid)
                            if not await session.get(Player, effective_pid):
                                continue
                            b = pdata.get("batting", {})
                            bw = pdata.get("bowling", {})
                            f = pdata.get("fielding", {})
                            session.add(PlayerSeasonGradeStats(
                                player_id=effective_pid,
                                season_id=season_id,
                                grade_id=grade_uuid,
                                matches=b.get("matches") or bw.get("matches") or f.get("matches") or 0,
                                batting_innings=b.get("battingInnings") or 0,
                                runs=b.get("battingAggregate") or 0,
                                not_outs=b.get("battingNotOuts") or 0,
                                high_score=b.get("battingHighScore"),
                                bowling_innings=bw.get("bowlingInnings") or 0,
                                wickets=bw.get("bowlingWickets") or 0,
                                runs_conceded=bw.get("bowlingRuns") or 0,
                                catches=(f.get("fieldingTotalCatches")
                                         or ((f.get("fieldingCatches") or 0) + (f.get("fieldingWicketKeeperCatches") or 0))),
                                run_outs=f.get("fieldingRunOuts") or 0,
                                stumpings=f.get("fieldingStumpings") or 0,
                                synced_at=datetime.now(timezone.utc),
                            ))
                            grade_rows_written += 1
                    await session.commit()
                    stats["grade_stats"] = stats.get("grade_stats", 0) + grade_rows_written
                    logger.info(f"Season {season_data.get('name')}: {grade_rows_written} per-grade aggregate rows across {len(grade_ids_this_season)} grades")
                    if run_id:
                        await update_sync_run(run_id, stats)
            except Exception as e:
                import traceback as _tbg
                logger.error(f"Per-grade aggregate sync failed for season {raw_season_id}: {e}\n{_tbg.format_exc()}")
                await session.rollback()

        # Recompute milestones for all players in this org
        if run_id:
            _progress(stats, "Milestones", 41)
            await update_sync_run(run_id, stats)
        all_pids_res = await session.execute(
            select(Player.id).where(Player.organisation_id == org_id)
        )
        all_player_ids = [r[0] for r in all_pids_res]
        if all_player_ids:
            await _compute_milestones(session, all_player_ids, org_id)

        # Grassroots /scores/* — game-level scorecards for all seasons.
        # The PlayHQ Partner game-level sync was removed (May 2026) — see git history
        # or CLAUDE.md for context. Grassroots covers 50+ seasons including recent ones.
        # Independent of org.playhq_id; uses its own DB session because the
        # outer session has been through hundreds of commits during PlayHQ
        # phase and can leave ORM state in a bad spot for async I/O.
        try:
            gr_stats = await sync_grassroots_game_level_data(org_id_str, run_id=run_id)
            stats.update(gr_stats)
        except Exception as e:
            import traceback as _tb2
            logger.error(f"Grassroots game-level sync failed for {org_id_str}: {e}\n{_tb2.format_exc()}")

        if run_id:
            _progress(stats, "Finalising", 99)
            await update_sync_run(run_id, stats)

        # CA's aggregate API sometimes omits low-volume players for old seasons,
        # leaving them with scorecard rows but no player_season_stats row. Every
        # career number on the player page sums from player_season_stats, so
        # those players show "0 matches" despite having real innings. Synthesise
        # the missing aggregate from the per-game tables we already have.
        try:
            backfilled = await _backfill_missing_season_stats(org_id_str)
            stats["aggregate_backfill"] = backfilled
            if run_id:
                await update_sync_run(run_id, stats)
        except Exception as e:
            import traceback as _tb3
            logger.error(f"Aggregate backfill failed for {org_id_str}: {e}\n{_tb3.format_exc()}")

        # BetterImport: re-derive the non-GR remainder of any uploaded historical
        # summaries against the GR data we just (re)synced. Runs last so the
        # residual shrinks automatically as GR coverage grows — no re-import. A
        # no-op for orgs that have never imported (migration 070).
        try:
            from app.services.import_reconcile import reconcile_imported_totals
            stats["import_reconciled"] = await reconcile_imported_totals(org_id_str)
            if run_id:
                await update_sync_run(run_id, stats)
        except Exception as e:
            import traceback as _tb4
            logger.error(f"Import reconcile failed for {org_id_str}: {e}\n{_tb4.format_exc()}")

        logger.info(f"Sync complete: {stats}")

        # Refresh Postgres planner statistics. Every sync delete+reinserts this
        # org's player_season_stats (and the GR pass rewrites the per-game
        # tables), which leaves the statistics stale until autovacuum catches
        # up. player_season_stats is a GLOBAL table (all clubs), so a stale plan
        # makes the all-seasons leaderboard / club summary scan every club's
        # rows and time out (35s → nginx 504) — the dashboard/leaderboard hang
        # on a freshly-synced club while a player search (a light query) works.
        # ANALYZE is seconds against a multi-minute sync and makes the heavy
        # aggregate reads return in ~1s. Best-effort: never fail a sync over it.
        try:
            async with async_session_maker() as analyze_session:
                await analyze_session.execute(text("ANALYZE"))
                await analyze_session.commit()
        except Exception as e:
            logger.warning(f"Post-sync ANALYZE failed for {org_id_str}: {e}")

        if run_id and owns_run:
            await finish_sync_run(run_id, stats)
        elif run_id:
            await update_sync_run(run_id, stats)
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


_GR_DISMISSAL_SHORT = {
    "Caught": "c",
    "Bowled": "b",
    "LBW": "lbw",
    "Stumped": "st",
    "Run Out": "run out",
    "Hit Wicket": "hit wicket",
    "Hit the ball twice": "hit the ball twice",
    "Retired Hurt": "retired hurt",
    "Obstructing the field": "obstructing",
    "Timed Out": "timed out",
    "Handled the ball": "handled the ball",
}


def _norm_name(s: str) -> str:
    """Normalise curly/smart apostrophes to straight apostrophe so scorecard
    dismissalText and playerShortName compare equal regardless of which
    Unicode variant CA's API returns in each field."""
    return s.replace("’", "'").replace("‘", "'")


def extract_bowler_wickets(
    scorecard: dict,
    game_uuid: uuid.UUID,
    gate_pids: set,
    pid_by_guid: dict,
    merged_away: dict,
) -> list:
    """Return a list of BowlerWicket rows to insert from a GR scorecard.

    For each innings, builds short-name → participantId maps from the bowling
    and fielding rows (with the team-level roster as a fallback for stumpers
    who didn't appear in fielding_rows), parses dismissalText, and emits one
    BowlerWicket per credit-dismissal where the bowler resolves to one of
    our players (directly or via the merge map).

    Pure function — does NOT touch the DB. Caller adds the returned objects
    to its own session.
    """
    out: list = []

    pid_to_short_name: dict[str, str] = {}
    for team in (scorecard.get("teams") or []):
        for pl in ((team.get("players") or []) + (team.get("nonPlayingMembers") or [])):
            pid = pl.get("participantId") or pl.get("id")
            name = pl.get("playerShortName") or pl.get("displayName") or pl.get("name")
            if pid and name:
                pid_to_short_name[pid] = _norm_name(name)

    def _resolve(name_to_pid: dict, name):
        if not name:
            return None
        pid_str = name_to_pid.get(_norm_name(name))
        if not pid_str:
            return None
        try:
            g = uuid.UUID(pid_str)
        except ValueError:
            return None
        # raw participant GUID -> this org's player id (identity for legacy
        # single-club orgs where grassroots_id == id), then merge redirect.
        p = pid_by_guid.get(g)
        if p is None:
            p = merged_away.get(g)
            if p is None:
                return None
        else:
            p = merged_away.get(p, p)
        return p if p in gate_pids else None

    for inn in (scorecard.get("innings") or []):
        inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
        batting_rows = inn.get("batting") or []
        bowling_rows = inn.get("bowling") or []
        fielding_rows = inn.get("fielding") or []
        keeper_names = _innings_keeper_names(fielding_rows)

        bowl_name_to_pid: dict[str, str] = {}
        for r in bowling_rows:
            pid_s = r.get("participantId")
            if not pid_s:
                continue
            name = r.get("playerShortName") or pid_to_short_name.get(pid_s)
            if name:
                bowl_name_to_pid.setdefault(_norm_name(name), pid_s)

        field_name_to_pid: dict[str, str] = {}
        for r in fielding_rows:
            pid_s = r.get("participantId")
            if not pid_s:
                continue
            name = r.get("playerShortName") or pid_to_short_name.get(pid_s)
            if name:
                field_name_to_pid.setdefault(_norm_name(name), pid_s)
        # Stumpers are fielders (the keeper) but may not appear in
        # fielding_rows if their only contribution was a stumping; the
        # bowling-side roster covers them too via pid_to_short_name.
        for r in bowling_rows:
            pid_s = r.get("participantId")
            name = r.get("playerShortName") or pid_to_short_name.get(pid_s) if pid_s else None
            if name:
                norm = _norm_name(name)
                if norm not in field_name_to_pid:
                    field_name_to_pid[norm] = pid_s

        for row in batting_rows:
            dt_long = row.get("dismissalType") or ""
            if dt_long not in _BOWLER_CREDIT_DT:
                continue
            d_text = row.get("dismissalText") or ""
            bowler_name, fielder_name, method = _parse_bowler_and_fielder(d_text, dt_long)
            bowler_pid = _resolve(bowl_name_to_pid, bowler_name)
            if bowler_pid is None:
                continue
            fielder_pid = _resolve(field_name_to_pid, fielder_name) if fielder_name else None
            b_runs = row.get("runsScored")
            b_balls = row.get("ballsFaced")
            out.append(BowlerWicket(
                game_id=game_uuid,
                innings_number=inn_num,
                bowler_id=bowler_pid,
                fielder_id=fielder_pid,
                batter_name=row.get("playerShortName") or pid_to_short_name.get(row.get("participantId") or ""),
                batter_position=row.get("batOrder"),
                dismissal_type=method or None,
                caught_behind=(method == "caught" and _caught_by_keeper(d_text, keeper_names)),
                batter_runs=int(b_runs) if b_runs is not None else None,
                batter_balls=int(b_balls) if b_balls is not None else None,
            ))

    return out


_NON_WICKET_DT = {"absent", "did not bat", "dnb", "retired hurt", "retired not out"}


# Bowler-credit dismissal types from CA's `dismissalType` field.
# Run-outs, retirements, obstructions etc. don't credit the bowler.
_BOWLER_CREDIT_DT = {"Caught", "Bowled", "LBW", "Stumped", "Hit Wicket"}


# Cricket-scorecard bowler marker: literal lowercase "b" (optionally "b:")
# preceded by whitespace or at the start of the text, followed by whitespace.
# Lowercase-only on purpose so a fielder's initial like "B Cooper" doesn't
# false-match the marker — the indicator is always lowercase in convention.
_BOWLER_MARKER_RE = re.compile(r'(?:^|\s)b:?\s+')
# Caught/Stumped fielder: between the "c"/"st" prefix and the next " b" marker.
_CAUGHT_FIELDER_RE = re.compile(r'^c:?\s+(.+?)\sb:?\s+')
_STUMPED_FIELDER_RE = re.compile(r'^st:?\s+(.+?)\sb:?\s+')
# Caught-and-bowled: "c & b ..." or "c and b ..." (with optional colon).
_CB_RE = re.compile(r'^c\s*(?:&|and)\s*b:?\s+')
# LBW where the text has no separate " b" marker — e.g. "lbw: BowlerName".
_LBW_DIRECT_RE = re.compile(r'^lbw:?\s+(.+?)\s*$', re.IGNORECASE)


def _parse_bowler_and_fielder(dismissal_text: str, dismissal_type: str) -> tuple[str | None, str | None, str]:
    """Parse GR `dismissalText` to extract bowler name, fielder name, and a
    canonical short dismissal method.

    Handles both colon and non-colon variants observed in CA data:
      "b: J Birbeck"           -> bowler="J Birbeck", fielder=None,     method="bowled"
      "b J Birbeck"            -> same as above
      "c: A Dillon b: J Birbeck" -> bowler="J Birbeck", fielder="A Dillon", method="caught"
      "c & b: J Birbeck"       -> bowler="J Birbeck", fielder=None,     method="caught and bowled"
      "c&b J Birbeck"          -> same (no spaces)
      "c and b J Birbeck"      -> same as above
      "c J Birbeck b J Birbeck" -> reclassified to "caught and bowled" (same-name form)
      "lbw b: J Birbeck"       -> bowler="J Birbeck", fielder=None,     method="lbw"
      "lbw: J Birbeck"         -> bowler="J Birbeck", fielder=None,     method="lbw"
      "st †Smith b: J Birbeck" -> bowler="J Birbeck", fielder="Smith",  method="stumped"
      "hit wicket b J Birbeck" -> bowler="J Birbeck", fielder=None,     method="hit wicket"
    """
    if not dismissal_text:
        return None, None, ""
    text = dismissal_text.strip()
    dt = (dismissal_type or "").strip()

    # Caught-and-bowled is detected FIRST because the spaceless form "c&b"
    # has no whitespace before the "b" marker, so the general bowler-tail
    # extractor below would fail. Extract the bowler directly from the tail.
    if dt == "Caught":
        cb_match = re.match(r'^c\s*(?:&|and)\s*b:?\s*', text)
        if cb_match:
            bowler_name = text[cb_match.end():].strip() or None
            return bowler_name, None, "caught and bowled"

    # Bowler = everything after the LAST lowercase "b"/"b:" marker.
    matches = list(_BOWLER_MARKER_RE.finditer(text))
    bowler_name = text[matches[-1].end():].strip() if matches else None

    if dt == "Bowled":
        return bowler_name, None, "bowled"
    if dt == "LBW":
        if not bowler_name:
            m = _LBW_DIRECT_RE.match(text)
            if m:
                bowler_name = m.group(1).strip()
        return bowler_name, None, "lbw"
    if dt == "Hit Wicket":
        return bowler_name, None, "hit wicket"
    if dt == "Stumped":
        m = _STUMPED_FIELDER_RE.match(text)
        fielder = m.group(1).strip().lstrip("†").strip() if m else None
        return bowler_name, fielder, "stumped"
    if dt == "Caught":
        m = _CAUGHT_FIELDER_RE.match(text)
        fielder = m.group(1).strip().lstrip("†").strip() if m else None
        # CA sometimes writes c&b as "c X b X" with the same name in both
        # slots instead of using the "c & b" shorthand. Reclassify these.
        if fielder and bowler_name and fielder == bowler_name:
            return bowler_name, None, "caught and bowled"
        return bowler_name, fielder, "caught"
    return bowler_name, None, ""


def _innings_keeper_names(fielding_rows: list) -> set[str]:
    """Normalised short-names of the wicketkeeper(s) in this innings — the
    fielders credited with a wicketkeeper catch or a stumping. CA puts NO keeper
    marker in dismissalText (it reads plain "c: C Cecchi b: A Ricci"), so a
    'caught' is 'caught behind' iff its catcher is one of these."""
    names: set[str] = set()
    for f in (fielding_rows or []):
        if (f.get("wicketKeeperCatches") or 0) > 0 or (f.get("stumpings") or 0) > 0:
            nm = f.get("playerShortName")
            if nm:
                names.add(_norm_name(nm).strip().lower())
    return names


def _caught_by_keeper(dismissal_text: str, keeper_names: set[str]) -> bool:
    """True when a caught dismissal's catcher is the wicketkeeper ("caught
    behind"). The catcher is the fielder named between 'c' and 'b' in
    dismissalText (e.g. "c: C Cecchi b: A Ricci" → "C Cecchi"); we match it
    against the innings' keepers (the fielders with a wk-catch / stumping), since
    CA marks no keeper symbol in the text. Caller gates on dismissalType ==
    'Caught'. `keeper_names` comes from `_innings_keeper_names(inn['fielding'])`."""
    if not dismissal_text or not keeper_names:
        return False
    m = _CAUGHT_FIELDER_RE.match(_norm_name(dismissal_text).strip())
    if not m:
        return False
    catcher = m.group(1).strip().lstrip("†").strip().lower()
    return catcher in keeper_names


def _count_dismissals_grassroots(batting_rows: list) -> int:
    """Number of wickets that actually fell in this innings."""
    return len(_dismissed_pids_grassroots(batting_rows))


def _dismissed_pids_grassroots(batting_rows: list) -> set:
    """Set of participantIds for batters who were genuinely dismissed
    (excludes Not Out, DNB, Absent, Retired Hurt, Retired Not Out)."""
    pids = set()
    for b in batting_rows:
        dt_id = b.get("dismissalTypeId") or 0
        if dt_id in (0, 1):
            continue
        if (b.get("dismissalType") or "").lower() in _NON_WICKET_DT:
            continue
        pid = b.get("participantId")
        if pid:
            pids.add(pid)
    return pids


# Most extras a single partnership could plausibly add on top of the two batters'
# own runs. Used to sanity-check FOW-derived stands against corrupt cumulative
# scores — generous enough never to reject a real stand.
_MAX_STAND_EXTRAS = 50


def _derive_partnerships_grassroots(batting_rows: list, fow_rows: list) -> list:
    """Derive per-wicket partnerships from a Grassroots-shaped innings.

    Grassroots batting rows use `participantId` + `batOrder` + `runsScored`;
    fall-of-wicket rows use `participantId` + `order` (wicket number) + `runs`
    (score at fall). This deriver assumes participantId IS the player_id —
    which it is, because both come from the same Grassroots namespace.
    """
    # Exclude both "didn't bat" (dismissalTypeId=0) and "Absent" / "DNB" string types —
    # these batters were never at the crease so can't be in any partnership.
    _SKIP_DT = {"absent", "did not bat", "dnb"}
    valid = [
        b for b in batting_rows
        if (b.get("dismissalTypeId") or 0) != 0
        and (b.get("dismissalType") or "").lower() not in _SKIP_DT
    ]
    if len(valid) < 2:
        return []

    # Incomplete FOW data poisons every partnership it touches: the loop below
    # marches `at_crease` forward one wicket per FOW row, so a single 5/215 row
    # in an innings that actually lost 7 wickets gets attributed to the openers
    # as a 215-run 5th-wicket stand. Refuse to derive unless FOW count matches
    # the dismissals in the batting card.
    dismissed_pids = _dismissed_pids_grassroots(batting_rows)
    if not dismissed_pids or len(fow_rows) != len(dismissed_pids):
        return []

    # PSWL / women's scorecards sometimes encode a *retirement* as a FOW row
    # (order=N, pid=retired batter). Combined with a missed real-wicket FOW,
    # the count check above can coincidentally pass: 1 retirement-FOW + 1
    # missed dismissal looks like 1 == 1. Catch this by requiring every FOW
    # participantId to point to a genuinely dismissed batter.
    fow_pids = {f.get("participantId") for f in fow_rows if f.get("participantId")}
    if fow_pids and not fow_pids.issubset(dismissed_pids):
        return []
    batters = sorted(valid, key=lambda r: r.get("batOrder") or 99)
    at_crease = list(batters[:2])
    next_in = 2
    prev_score = 0
    result = []

    for fow in sorted(fow_rows, key=lambda f: f.get("order") or 99):
        wkt = fow.get("order") or len(result) + 1
        score = fow.get("runs")
        dismissed_pid = fow.get("participantId")

        b1 = at_crease[0] if len(at_crease) > 0 else None
        b2 = at_crease[1] if len(at_crease) > 1 else None
        result.append({
            "wicket_number": wkt,
            "batter1_id": b1.get("participantId") if b1 else None,
            "batter2_id": b2.get("participantId") if b2 else None,
            "batter1_runs": b1.get("runsScored") if b1 else None,
            "batter2_runs": b2.get("runsScored") if b2 else None,
            "runs": (score - prev_score) if score is not None else None,
        })

        if dismissed_pid:
            at_crease = [b for b in at_crease if b.get("participantId") != dismissed_pid]
        elif at_crease:
            at_crease.pop()

        if next_in < len(batters):
            at_crease.append(batters[next_in])
            next_in += 1
        if score is not None:
            prev_score = score

    # CA occasionally records a nonsensical cumulative `score_at_fall` — observed
    # 435 for a 49-run innings, which turned the 2nd-wicket delta into a phantom
    # 381-run stand between two batters who made 25 and 1. The count/dismissal
    # checks above can't catch it: the FOW row COUNT is still right. A stand can
    # never be worth more than its two batters' innings totals plus a little for
    # extras, and a cumulative score can't go backwards, so a delta outside those
    # bounds means the FOW scores are corrupt and every delta in the innings is
    # unreliable. Refuse the innings, like the checks above.
    for p in result:
        runs = p.get("runs")
        if runs is None:
            continue
        cap = (p.get("batter1_runs") or 0) + (p.get("batter2_runs") or 0) + _MAX_STAND_EXTRAS
        if runs < 0 or runs > cap:
            return []
    return result


async def sync_grassroots_game_level_data(
    org_id_str: str,
    run_id: Optional[uuid.UUID] = None,
) -> dict:
    """Pull game-level scorecards from the Grassroots /scores/* API.

    Covers pre-PlayHQ-migration history (~2002 onwards). Post-migration games
    can return 204 (Grassroots doesn't have them) and are silently skipped.
    NOTE (Jul 2026): this comment used to say those 204s were "already handled
    by the PlayHQ Partner sync path" — that path (`sync_game_level_data`) was
    REMOVED from `sync_organisation` in the May 2026 Partner API audit, so a
    204'd match today has NO fallback and stays missing across every future
    sync, including a Full Rebuild (it hits the exact same 204 every time).
    Use `app.scripts.list_skipped_matches` to see which matches this affects
    for a given club/grade.

    Each game is processed in its OWN short-lived DB session. Holding one
    session across thousands of inserts has been observed to deadlock with
    SQLAlchemy/asyncpg, so we open-commit-close per game and accept the small
    per-game overhead in exchange for robustness.
    """
    from app.services import grassroots_scores_client as gr
    from datetime import date as date_cls

    stats = {
        "gr_teams_scanned": 0, "gr_matches_seen": 0,
        "gr_games_new": 0, "gr_games_skipped_done": 0, "gr_games_skipped_no_data": 0,
        "gr_batting": 0, "gr_bowling": 0, "gr_fielding": 0,
        "gr_partnerships": 0, "gr_fow": 0, "gr_appearances": 0,
    }
    org_uuid = _parse_uuid(org_id_str)
    if not org_uuid:
        logger.warning(f"GR-sync: invalid org_id_str {org_id_str!r}")
        return stats

    # ── DISCOVERY PHASE ────────────────────────────────────────────────────────
    # Short-lived session: enumerate grades and known players. Read-only.
    grades: list[tuple] = []  # (grade_id, season_id, grade_name)
    known_player_ids: set[uuid.UUID] = set()
    pid_by_guid: dict[uuid.UUID, uuid.UUID] = {}  # raw CA participant GUID -> this org's player id
    async with async_session_maker() as session:
        org = await session.get(Organisation, org_uuid)
        if not org:
            logger.warning(f"GR-sync: org {org_id_str} not found")
            return stats

        grades_res = await session.execute(
            select(Grade.id, Grade.season_id, Grade.name, Grade.grassroots_id)
            .join(Season, Grade.season_id == Season.id)
            .where(Season.organisation_id == org_uuid)
        )
        grades_rows = grades_res.all()
        # (raw_grade_guid, season_id, grade_name, our_grade_id). The grassroots
        # /scores/grades/{id}/matches API is keyed on the shared raw GUID, while
        # our grade id may now be a per-club uuid5 — carry both. Identity for
        # legacy grades (grassroots_id == id).
        grades = [((r[3] or str(r[0])), r[1], r[2], r[0]) for r in grades_rows]
        # raw CA grade GUID -> this org's grade id, to translate the scorecard's
        # grade.id (always the shared raw GUID) onto the right grade row.
        grade_id_by_guid: dict[str, uuid.UUID] = {
            (r[3] or str(r[0])): r[0] for r in grades_rows
        }
        logger.info(f"GR-sync: {len(grades)} grades for org {org_uuid}")

        # participant GUID -> this org's player id. Identity for a legacy
        # single-club org (grassroots_id == id); for a per-club player
        # (id = uuid5(org, guid)) it maps the scorecard's raw participantId to
        # the uuid5 id so game-level rows attach to the right record.
        player_res = await session.execute(
            select(Player.id, Player.grassroots_id).where(Player.organisation_id == org_uuid)
        )
        for _pid, _gid in player_res:
            known_player_ids.add(_pid)
            g = _parse_uuid(_gid) if _gid else None
            if g is not None:
                pid_by_guid[g] = _pid
        logger.info(f"GR-sync: {len(known_player_ids)} existing players in org")

        # Build merged-away → kept redirect map so scorecards referencing a
        # previously-merged player_id attribute stats to the kept player
        # instead of silently dropping rows.
        merge_res = await session.execute(
            text(
                "SELECT removed_player_id, keep_player_id "
                "FROM merge_logs "
                "WHERE org_id = :oid AND undone_at IS NULL"
            ),
            {"oid": str(org_uuid)},
        )
        raw_redirects: dict[uuid.UUID, uuid.UUID] = {r[0]: r[1] for r in merge_res.fetchall()}
        merged_away: dict[uuid.UUID, uuid.UUID] = {}
        for removed, target in raw_redirects.items():
            seen = {removed}
            while target in raw_redirects and target not in seen:
                seen.add(target)
                target = raw_redirects[target]
            merged_away[removed] = target
        logger.info(f"GR-sync: {len(merged_away)} merged-away player redirects loaded")

    def _team_pid(guid: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
        """Translate a scorecard participantId (raw CA GUID) to this org's player
        id, following merge redirects; None if the GUID isn't one of our players.

        Identity for a legacy single-club org (grassroots_id == id), so its
        game-level attribution is byte-for-byte unchanged. For a per-club player
        (id = uuid5(org, guid)) it returns the uuid5 id so the scorecard's raw
        GUID lands on the right record.
        """
        if guid is None:
            return None
        p = pid_by_guid.get(guid)
        if p is None:
            p = merged_away.get(guid)  # legacy merged-away GUID (removed_player_id == raw GUID)
            if p is None:
                return None
        return merged_away.get(p, p)

    # Enumerate match IDs by fanning out across all known grades.
    # /scores/grades/{id}/matches works for all seasons including pre-2000,
    # unlike the old fixturesladders teams path which had no records for old seasons.
    # Each match in the response includes teams[].owningOrganisation.id — filter
    # to only matches where our org is one of the participants, since large grades
    # return every match between all teams in the competition.
    org_id_str_lower = org_id_str.lower()
    seen_match_ids: set[str] = set()
    match_to_season: dict[str, uuid.UUID] = {}
    match_to_is_final: dict[str, bool] = {}
    match_to_opp: dict[str, tuple[str | None, str]] = {}  # match_id → (opp_org_id, opp_club_name)
    for grade_idx, (grade_guid, season_id, grade_name, _our_grade_id) in enumerate(grades, start=1):
        stats["gr_teams_scanned"] += 1  # reuse existing stat key for continuity
        try:
            matches = await gr.get_grade_matches(grade_guid)
        except Exception as e:
            logger.warning(f"GR-sync: grade {grade_name} ({grade_guid}) matches failed: {e}")
            continue
        for m in matches:
            mid = m.get("id")
            if not mid or mid in seen_match_ids:
                continue
            teams = m.get("teams") or []
            our_team_m = next(
                (t for t in teams if (t.get("owningOrganisation") or {}).get("id", "").lower() == org_id_str_lower),
                None,
            )
            if not our_team_m:
                continue
            seen_match_ids.add(mid)
            match_to_season[mid] = season_id
            round_name = (m.get("round") or {}).get("name", "")
            match_to_is_final[mid] = "final" in round_name.lower()
            opp_team_m = next((t for t in teams if t is not our_team_m), None)
            if opp_team_m:
                opp_org = opp_team_m.get("owningOrganisation") or {}
                opp_id = opp_org.get("id")
                opp_name = (
                    opp_org.get("name")
                    or opp_org.get("displayName")
                    or opp_team_m.get("displayName")
                    or opp_team_m.get("name")
                    or ""
                )
                match_to_opp[mid] = (opp_id, opp_name)
        if run_id:
            # Match discovery owns 42→55% of the overall bar.
            _progress(stats, "Finding matches",
                      42 + 13 * grade_idx / max(len(grades), 1),
                      grade_idx, len(grades))
            await update_sync_run(run_id, stats)

    stats["gr_matches_seen"] = len(seen_match_ids)
    logger.info(f"GR-sync: discovered {len(seen_match_ids)} unique match IDs across {stats['gr_teams_scanned']} grades")
    if run_id:
        _progress(stats, "Saving scorecards", 55, 0, len(seen_match_ids))
        await update_sync_run(run_id, stats)

    # Bulk-update is_final on all discovered games (backfills existing rows).
    if seen_match_ids:
        finals_ids = [mid for mid, f in match_to_is_final.items() if f]
        non_finals_ids = [mid for mid, f in match_to_is_final.items() if not f]
        async with async_session_maker() as upd_session:
            if finals_ids:
                await upd_session.execute(
                    text("UPDATE games SET is_final = TRUE WHERE id = ANY(:ids)"),
                    {"ids": [uuid.UUID(mid) for mid in finals_ids]},
                )
            if non_finals_ids:
                await upd_session.execute(
                    text("UPDATE games SET is_final = FALSE WHERE id = ANY(:ids)"),
                    {"ids": [uuid.UUID(mid) for mid in non_finals_ids]},
                )
            await upd_session.commit()
        logger.info(f"GR-sync: bulk-updated is_final ({len(finals_ids)} finals, {len(non_finals_ids)} non-finals)")

    if match_to_opp:
        opp_rows = []
        for mid, (opp_id, opp_name) in match_to_opp.items():
            try:
                opp_rows.append({"gid": uuid.UUID(mid), "opp_id": opp_id, "opp_name": opp_name})
            except ValueError:
                pass
        if opp_rows:
            async with async_session_maker() as upd_session:
                await upd_session.execute(
                    text("""
                        UPDATE games
                        SET opp_org_id = :opp_id, opp_club_name = :opp_name
                        WHERE id = :gid AND opp_org_id IS NULL
                    """),
                    opp_rows,
                )
                await upd_session.commit()
            logger.info(f"GR-sync: bulk-updated opp_org_id for up to {len(opp_rows)} games")

    # ── PER-GAME PROCESSING ───────────────────────────────────────────────────
    processed = 0
    for match_id_str in seen_match_ids:
        processed += 1
        try:
            match_uuid = uuid.UUID(match_id_str)
        except ValueError:
            continue

        # Fetch first (no session needed). 204 → not in Grassroots, skip.
        scorecard = await gr.get_match_scorecard(match_id_str)
        if not scorecard:
            stats["gr_games_skipped_no_data"] += 1
            continue

        # Teams / our roster, resolved up front (independent of whether a Game
        # row already exists for this match) — needed below to tell "fully
        # processed" apart from "row exists but our team's stats were never
        # attached", since a shared match between two clubs we both sync
        # would otherwise look identical to one we've already done ourselves.
        teams_data = scorecard.get("teams") or []
        our_team = next(
            (t for t in teams_data if ((t.get("owningOrganisation") or {}).get("id") or "").lower() == org_id_str.lower()),
            None,
        )
        our_team_name = ""
        our_team_pids: set[uuid.UUID] = set()
        if our_team:
            our_team_name = our_team.get("displayName") or our_team.get("name") or ""
            for roster_p in (our_team.get("players") or []):
                rpid = _team_pid(_parse_uuid(roster_p.get("participantId") or ""))
                if rpid is not None:
                    our_team_pids.add(rpid)

        # Open a fresh per-game session.
        try:
            async with async_session_maker() as session:
                # A match between two clubs we BOTH sync shares one games.id row
                # (the raw CA match GUID) — whichever club synced it first
                # created the row, but that sync only ever attaches ITS OWN
                # team's players (our_team_pids gates every insert below). So
                # gate the skip on whether OUR players already have an
                # appearance row for this game, not on whether the Game row
                # exists — otherwise the second club's stats for that match
                # never land, even across a Full Rebuild (the same
                # row-exists check would keep short-circuiting first).
                existing = await session.execute(
                    text("SELECT venue, result FROM games WHERE id=:gid LIMIT 1"),
                    {"gid": match_id_str},
                )
                existing_row = existing.fetchone()
                game_exists = existing_row is not None

                our_appearances_done = True
                if game_exists and our_team_pids:
                    our_appear_check = await session.execute(
                        text(
                            "SELECT 1 FROM game_appearances "
                            "WHERE game_id=:gid AND player_id = ANY(:pids) LIMIT 1"
                        ),
                        {"gid": match_id_str, "pids": list(our_team_pids)},
                    )
                    our_appearances_done = our_appear_check.first() is not None

                if game_exists:
                    existing_venue, existing_result = existing_row
                    updates: dict[str, str] = {}
                    if existing_venue is None:
                        venue_name = (scorecard.get("venue") or {}).get("name")
                        if venue_name:
                            updates["venue"] = venue_name
                    if existing_result is None:
                        # Pre-v1.0.3.1 the result parser only recognised literal
                        # WON_ON_FIRST_INNINGS / LOST / DREW / TIED, so every
                        # outright-loss row (and every drawn-with-FI row) landed
                        # with result=NULL. Backfill from the scorecard now that
                        # classify_match_result handles WON_*/LOST_*/DRAWN_*.
                        new_result = classify_match_result(scorecard, org_id_str)
                        if new_result:
                            updates["result"] = new_result
                    if updates:
                        set_clause = ", ".join(f"{k}=:{k}" for k in updates)
                        await session.execute(
                            text(f"UPDATE games SET {set_clause} WHERE id=:gid"),
                            {**updates, "gid": match_id_str},
                        )
                        await session.commit()
                    if our_appearances_done:
                        stats["gr_games_skipped_done"] += 1
                        continue
                    # else: the row exists (the other synced club created it)
                    # but our own team's stats were never attached — fall
                    # through and attach them below, without re-inserting Game.

                season_id = match_to_season.get(match_id_str)
                if not season_id and seasons:
                    season_id = seasons[0][0]

                # Grade — the scorecard's grade.id is the shared raw CA grade GUID.
                # Map it onto this org's grade id (which may now be a per-club
                # uuid5). The aggregate pass seeds every grade get_teams returns, so
                # the discovery map normally has it.
                grade_data = scorecard.get("grade") or {}
                grade_guid_str = grade_data.get("id")
                grade_uuid = grade_id_by_guid.get(grade_guid_str) if grade_guid_str else None
                if grade_uuid is None and grade_guid_str:
                    # Safety net for a grade present in a scorecard but not seeded
                    # by get_teams. Resolve against the DB directly (not the cache)
                    # so a previously rolled-back game session can't leave a stale
                    # id, and so we never mint a second row for a grade we already
                    # own.
                    raw_guid = _parse_uuid(grade_guid_str)
                    if raw_guid is not None:
                        existing_grade = (await session.execute(
                            select(Grade.id)
                            .join(Season, Grade.season_id == Season.id)
                            .where(
                                Season.organisation_id == org_uuid,
                                Grade.grassroots_id == grade_guid_str,
                            )
                        )).scalars().first()
                        if existing_grade is not None:
                            grade_uuid = existing_grade
                        else:
                            # Per-club mint only when another club already owns the
                            # raw GUID, mirroring _resolve_org_grade.
                            clash = await session.get(Grade, raw_guid)
                            grade_uuid = uuid.uuid5(org_uuid, grade_guid_str) if clash is not None else raw_guid
                            _gname = grade_data.get("name", "Unknown Grade")
                            session.add(Grade(
                                id=grade_uuid,
                                season_id=season_id,
                                name=_gname,
                                grassroots_id=grade_guid_str,
                                playhq_id=grade_guid_str,
                                category=suggest_category(_gname),
                            ))
                            try:
                                await session.flush()
                            except Exception as e:
                                logger.warning(f"GR-sync: grade flush failed for {grade_guid_str}: {e}")
                                continue  # session auto-rollback on context exit
                        grade_id_by_guid[grade_guid_str] = grade_uuid

                # Date
                played_at = None
                for sched in (scorecard.get("matchSchedule") or []):
                    iso = sched.get("startDateTime") or ""
                    if iso:
                        try:
                            played_at = date_cls.fromisoformat(iso[:10])
                            break
                        except ValueError:
                            pass

                # isHome lives on matchSummary.teams, NOT on the top-level
                # teams array (which has no isHome field at all). Bug from
                # initial version: was reading from teams_data and getting
                # empty home_team on every game.
                # Roster pid -> short name (covers both teams; used for bowler
                # and fielder name resolution when parsing dismissalText).
                pid_to_short_name: dict[str, str] = {}
                for _team in teams_data:
                    for _pl in ((_team.get("players") or []) + (_team.get("nonPlayingMembers") or [])):
                        _pid = _pl.get("participantId") or _pl.get("id")
                        _name = _pl.get("playerShortName") or _pl.get("displayName") or _pl.get("name")
                        if _pid and _name:
                            pid_to_short_name[_pid] = _name

                summary_teams = (scorecard.get("matchSummary") or {}).get("teams") or []
                home_team_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is True), "")
                away_team_name = next((t.get("displayName", "") for t in summary_teams if t.get("isHome") is False), "")
                winner_name = next((t.get("displayName") for t in (teams_data or []) + summary_teams if t.get("isWinner")), None)
                result_text = classify_match_result(scorecard, org_id_str)

                # Game — only create the row the first time; when it already
                # exists (the other synced club created it), just attach our
                # own team's stats to it below instead of re-inserting it.
                if not game_exists:
                    venue_name = (scorecard.get("venue") or {}).get("name")
                    _opp_id, _opp_name = match_to_opp.get(match_id_str, (None, ""))
                    session.add(Game(
                        id=match_uuid,
                        grade_id=grade_uuid,
                        played_at=played_at,
                        home_team=home_team_name,
                        away_team=away_team_name,
                        home_club=strip_team_suffix(home_team_name),
                        away_club=strip_team_suffix(away_team_name),
                        opp_org_id=_opp_id,
                        opp_club_name=_opp_name,
                        result=result_text,
                        winning_team=winner_name,
                        is_final=match_to_is_final.get(match_id_str, False),
                        venue=venue_name,
                    ))
                    try:
                        await session.flush()
                    except Exception as e:
                        logger.warning(f"GR-sync: game flush failed for {match_id_str}: {e}")
                        continue  # session auto-rollback on context exit

                bat_count = bowl_count = field_count = part_count = fow_count = appear_count = 0

                # our_team_pids / our_team_name were resolved up front (used
                # for the appearances-done gate above too), gating every
                # per-innings stat insert below: a player who's currently in
                # known_player_ids but played AGAINST us in this game (e.g. was
                # on another club's roster that season) would otherwise have
                # their opposition batting/bowling/fielding picked up as ours,
                # inflating their match count and stats.

                # Roster: insert one GameAppearance per club player listed in the
                # team-sheet. Covers selected players who didn't bat/bowl/take a
                # dismissal (forfeits, washouts, late-order batters who didn't
                # get a hit, fielders with no chances). Matches play.cricket's
                # match-count which is based on selection, not stat lines.
                if our_team:
                    seen_appear_pids: set[uuid.UUID] = set()
                    for roster_p in (our_team.get("players") or []):
                        rpid = _team_pid(_parse_uuid(roster_p.get("participantId") or ""))
                        if rpid is None:
                            continue
                        if rpid in seen_appear_pids:
                            continue  # multi-team appearance (shouldn't happen for one team)
                        seen_appear_pids.add(rpid)
                        roles = roster_p.get("roles") or []
                        is_captain = any((r or "").lower() == "captain" for r in roles)
                        is_wk = any("wicket" in (r or "").lower() for r in roles)
                        session.add(GameAppearance(
                            game_id=match_uuid, player_id=rpid,
                            team_name=our_team_name,
                            is_captain=is_captain, is_wicket_keeper=is_wk,
                        ))
                        appear_count += 1

                for inn in (scorecard.get("innings") or []):
                    # CA's GR API returns `inningsNumber: 1` for BOTH innings
                    # (data bug their end). `inningsOrder` is the field that
                    # actually distinguishes 1st vs 2nd innings — using
                    # `inningsNumber` collapses both teams' batting/FOW/etc.
                    # into the same row group, which silently breaks per-innings
                    # partnership derivation.
                    inn_num = inn.get("inningsOrder") or inn.get("inningsNumber") or 1
                    batting_rows = inn.get("batting") or []
                    bowling_rows = inn.get("bowling") or []
                    fielding_rows = inn.get("fielding") or []
                    fow_rows = inn.get("fallOfWickets") or []
                    keeper_names = _innings_keeper_names(fielding_rows)

                    for row in batting_rows:
                        pid = _team_pid(_parse_uuid(row.get("participantId") or ""))
                        if pid is None or pid not in our_team_pids:
                            continue
                        dt_id = row.get("dismissalTypeId") or 0
                        if dt_id == 0:
                            continue
                        dt_long = row.get("dismissalType") or ""
                        is_dnb = dt_long.lower() in ("absent", "did not bat", "dnb")
                        if is_dnb:
                            # Store as DNB row (did_not_bat=True) so scorecards can list
                            # the player, but exclude from innings counts / averages.
                            session.add(BattingInnings(
                                game_id=match_uuid, player_id=pid, innings_number=inn_num,
                                batting_position=row.get("batOrder"),
                                runs=None, balls=None, fours=None, sixes=None,
                                not_out=False, dismissal_type=None, did_not_bat=True,
                            ))
                            continue
                        not_out = dt_id == 1
                        dt_short = _GR_DISMISSAL_SHORT.get(dt_long, dt_long.lower())
                        caught_behind = (
                            dt_long == "Caught"
                            and _caught_by_keeper(row.get("dismissalText") or "", keeper_names)
                        )
                        session.add(BattingInnings(
                            game_id=match_uuid, player_id=pid, innings_number=inn_num,
                            batting_position=row.get("batOrder"),
                            runs=row.get("runsScored") or 0,
                            balls=row.get("ballsFaced") or 0,
                            fours=row.get("foursScored") or 0,
                            sixes=row.get("sixesScored") or 0,
                            not_out=not_out,
                            dismissal_type=dt_short or None,
                            caught_behind=caught_behind,
                            did_not_bat=False,
                        ))
                        bat_count += 1

                    for row in bowling_rows:
                        pid = _team_pid(_parse_uuid(row.get("participantId") or ""))
                        if pid is None or pid not in our_team_pids:
                            continue
                        econ = None
                        try:
                            econ_raw = row.get("economy")
                            econ = float(econ_raw) if econ_raw is not None else None
                        except (TypeError, ValueError):
                            pass
                        session.add(BowlingSpell(
                            game_id=match_uuid, player_id=pid, innings_number=inn_num,
                            overs=row.get("oversBowled"),
                            maidens=row.get("maidensBowled"),
                            runs=row.get("runsConceded"),
                            wickets=row.get("wicketsTaken"),
                            wides=row.get("wideBalls"),
                            no_balls=row.get("noBalls"),
                            economy=econ,
                        ))
                        bowl_count += 1

                    for row in fielding_rows:
                        pid = _team_pid(_parse_uuid(row.get("participantId") or ""))
                        if pid is None or pid not in our_team_pids:
                            continue
                        catches_wk = row.get("wicketKeeperCatches") or 0
                        catches_total = row.get("totalCatches")
                        if catches_total is None:
                            catches_total = (row.get("catches") or 0) + catches_wk
                        session.add(FieldingStat(
                            game_id=match_uuid, player_id=pid,
                            catches=catches_total or 0,
                            catches_wk=catches_wk,
                            run_outs=row.get("runOuts") or 0,
                            stumpings=row.get("stumpings") or 0,
                        ))
                        field_count += 1

                    for row in fow_rows:
                        # Resolve player_id only when the falling batter was
                        # on OUR team — opposition batters who happen to also
                        # be in our players table (current club members who
                        # played AGAINST us in this game) must not be tagged,
                        # or their personal FOW history gets polluted.
                        # The row itself is still inserted so the game-level
                        # scorecard view can display both innings' wickets.
                        pid = _team_pid(_parse_uuid(row.get("participantId") or ""))
                        if pid is not None and pid not in our_team_pids:
                            pid = None
                        wkt = row.get("order")
                        if wkt is None:
                            continue
                        session.add(FallOfWicket(
                            game_id=match_uuid, innings_number=inn_num,
                            wicket_number=wkt,
                            score_at_fall=row.get("runs"),
                            player_id=pid,
                            batter_name=row.get("playerShortName"),
                        ))
                        fow_count += 1

                    # Classify the innings: club batting or opposition? Prefer
                    # the authoritative batting-team id when the payload carries
                    # one, else fall back to a roster-majority vote (the club
                    # innings is the card whose batters are mostly club players).
                    inn_team_id = None
                    for _tk in ("battingTeamId", "teamId"):
                        _tv = inn.get(_tk)
                        if _tv:
                            inn_team_id = str(_tv).lower()
                            break
                    if inn_team_id is None:
                        for _tk in ("battingTeam", "team"):
                            _to = inn.get(_tk)
                            if isinstance(_to, dict) and _to.get("id"):
                                inn_team_id = str(_to["id"]).lower()
                                break
                    if inn_team_id is not None and our_team and our_team.get("id"):
                        is_club_innings = inn_team_id == str(our_team["id"]).lower()
                    else:
                        club_n = total_n = 0
                        for _br in batting_rows:
                            _bp = _br.get("participantId")
                            if not _bp:
                                continue
                            total_n += 1
                            _bc = _team_pid(_parse_uuid(_bp))
                            if _bc is not None and _bc in our_team_pids:
                                club_n += 1
                        is_club_innings = total_n > 0 and club_n * 2 > total_n

                    for p in _derive_partnerships_grassroots(batting_rows, fow_rows):
                        b1_id = b2_id = None
                        for src_key, dst in (("batter1_id", "b1"), ("batter2_id", "b2")):
                            v = p.get(src_key)
                            if v:
                                cand = _team_pid(_parse_uuid(v))
                                if cand is not None and cand in our_team_pids:
                                    if dst == "b1":
                                        b1_id = cand
                                    else:
                                        b2_id = cand
                        if not b1_id and not b2_id:
                            continue
                        session.add(Partnership(
                            game_id=match_uuid, innings_number=inn_num,
                            wicket_number=p["wicket_number"],
                            batter1_id=b1_id, batter2_id=b2_id,
                            runs=p.get("runs") or 0,
                            batter1_runs=p.get("batter1_runs"),
                            batter2_runs=p.get("batter2_runs"),
                            is_club_innings=is_club_innings,
                        ))
                        part_count += 1

                # Bowler wickets: emit rows for credit-dismissals attributable
                # to one of our players. Helper builds short-name → pid maps
                # from each innings' bowling/fielding rows and resolves through
                # merged_away. Reused by app.scripts.rebuild_bowler_wickets.
                for bw in extract_bowler_wickets(scorecard, match_uuid, our_team_pids, pid_by_guid, merged_away):
                    session.add(bw)

                if bat_count == 0 and bowl_count == 0 and appear_count == 0:
                    stats["gr_games_skipped_no_data"] += 1
                    continue  # session auto-rollback

                await session.commit()
                stats["gr_games_new"] += 1
                stats["gr_batting"] += bat_count
                stats["gr_bowling"] += bowl_count
                stats["gr_fielding"] += field_count
                stats["gr_partnerships"] += part_count
                stats["gr_fow"] += fow_count
                stats["gr_appearances"] += appear_count
        except Exception as e:
            logger.error(f"GR-sync: per-game exception for {match_id_str}: {e}")
            # session has already auto-closed; just move on

        if run_id and processed % 25 == 0:
            # Scorecards own 55→99% of the overall bar — the long phase.
            _progress(stats, "Saving scorecards",
                      55 + 44 * processed / max(len(seen_match_ids), 1),
                      processed, len(seen_match_ids))
            await update_sync_run(run_id, stats)
            logger.info(f"GR-sync: processed {processed}/{len(seen_match_ids)} games, stats={stats}")

    logger.info(f"GR-sync complete: {stats} for org {org_uuid}")
    return stats


async def _compute_milestones(session: AsyncSession, player_ids: list, org_id: uuid.UUID):
    from sqlalchemy import text
    from app.services.milestone_rules import crossed_thresholds

    detail_fmt = {
        "runs":    lambda v: f"{v:,} career runs",
        "wickets": lambda v: f"{v} career wickets",
        "matches": lambda v: f"{v} career matches",
        "catches": lambda v: f"{v} career catches",
    }

    for pid in player_ids:
        pid_str = str(pid)

        # Scope to this org's seasons only. A CA participant GUID is shared
        # across clubs, so a dual-club player can have player_season_stats rows
        # under another club's seasons; counting them all would mint inflated
        # career milestones (mirrors the v_effective view guard, migration 060).
        totals_res = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(pss.runs), 0)    AS runs,
                    COALESCE(SUM(pss.wickets), 0) AS wickets,
                    COALESCE(SUM(pss.matches), 0) AS matches,
                    COALESCE(SUM(pss.catches), 0) AS catches
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE pss.player_id = :pid AND s.organisation_id = :org_id
            """),
            {"pid": pid_str, "org_id": str(org_id)}
        )
        totals = dict(totals_res.mappings().first() or {})

        exist_res = await session.execute(
            text("SELECT milestone_type, milestone_value FROM milestones WHERE player_id=:pid"),
            {"pid": pid_str}
        )
        existing = {(r[0], r[1]) for r in exist_res.fetchall()}

        new_milestones = []
        today = date.today()

        for mt in ("runs", "wickets", "matches", "catches"):
            current = int(totals.get(mt) or 0)
            for threshold in crossed_thresholds(mt, current):
                if (mt, threshold) in existing:
                    continue
                new_milestones.append(Milestone(
                    player_id=pid, milestone_type=mt, milestone_value=threshold,
                    detail=detail_fmt[mt](threshold), achieved_at=today,
                ))

        for m in new_milestones:
            session.add(m)

    if player_ids:
        await session.commit()


async def deep_sync_player(
    org_id_str: str,
    player_id_str: str,
    run_id: Optional[uuid.UUID] = None,
) -> dict:
    """Refresh a player's game-level data via the Grassroots sync.

    The old PlayHQ Partner per-player reprocess is retired — the Grassroots
    /scores pass already covers every season including the current one. Rather
    than a bespoke Partner fetch, this delegates to the org's Grassroots sync,
    which re-pulls aggregate season stats and any new game-level scorecards
    (including this player's). The caller owns the sync run (``run_id`` is passed
    through, so we update but never finish it here).
    """
    org_uuid = _parse_uuid(org_id_str)
    player_uuid = _parse_uuid(player_id_str)
    if org_uuid is None or player_uuid is None:
        return {"error": "Invalid organisation or player id"}

    async with async_session_maker() as session:
        org = await session.get(Organisation, org_uuid)
        if not org:
            return {"error": "Organisation not found"}
        player = await session.get(Player, player_uuid)
        if not player:
            return {"error": "Player not found"}

    logger.info(
        f"DeepSync: delegating player {player_id_str} to the Grassroots org sync "
        f"for {org_id_str} (Partner path retired)"
    )
    stats = await sync_organisation(org_id_str, run_id=run_id, kind="player_deep")
    if isinstance(stats, dict):
        return {**stats, "deep_sync_player": player_id_str}
    return {"deep_sync_player": player_id_str}
