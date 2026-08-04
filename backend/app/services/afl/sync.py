"""AFL sync engine — PlayHQ → the AFL silo's database.

Pipeline (each step verified live against Curtin Uni Wesley, org d14445c4 —
see docs/afl-playhq-data-source.md):

  1. discoverCompetitions  → seasons (one row per competition-season pair)
  2. discoverTeams         → our teams + their grades, per season
  3. discoverGradeFixture  → every game id in each of our grades (we keep only
                             the games one of OUR teams plays in)
  4. gameView              → result, quarter scores, BOTH teams' player lines,
                             best players, venue
  5. gameEventsSpectator   → play-by-play, stored
  6. rollup                → afl_player_season_stats recomputed from the lines

Identity: PlayHQ discover ids are short hex codes, not UUIDs, so every row's
primary key is a uuid5 derivation — the org from a fixed namespace, every
other entity from (org uuid, raw id). Per-club by construction; the raw id is
stored on the row and is what the API calls use. Player identity keys on the
PlayHQ *profile* id (stable per person), not the per-registration participant
id.

Incremental vs full: a plain sync skips the per-game stats fetch for games
already stored as FINAL with their stats present; ``full=True`` re-pulls
everything (the Full Rebuild button).
"""
import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    Game, Grade, Organisation, Player, Season, async_session_maker,
)
from app.models.afl import (
    AflGameDetails, AflGameEvent, AflGamePeriod, AflPlayerGameLine,
    AflPlayerSeasonStats, AflTeam,
)
# Shared run bookkeeping — the same sync_runs rows/helpers the cricket silo
# uses, so the admin Data Sync surface works identically for both sports.
from app.services.sync import (  # noqa: F401  (re-exported for callers)
    start_sync_run, update_sync_run, finish_sync_run, _progress,
)
from app.services.afl import playhq_client as phq

logger = logging.getLogger(__name__)

# Fixed namespace for deriving org UUIDs from PlayHQ's short org codes.
AFL_NS = uuid.uuid5(uuid.NAMESPACE_URL, "playhq:afl")

_PERIOD_ORDER = {
    "FIRST_QTR": 1, "SECOND_QTR": 2, "THIRD_QTR": 3, "FOURTH_QTR": 4,
    "FIRST_HALF": 1, "SECOND_HALF": 2,
}

_SCORER_RE = re.compile(r"^\s*(?:(\d+)\.\s*)?(.+?)\s*$")


def org_uuid(playhq_org_id: str) -> uuid.UUID:
    return uuid.uuid5(AFL_NS, str(playhq_org_id))


def derive_id(org_id: uuid.UUID, raw_id: str) -> uuid.UUID:
    return uuid.uuid5(org_id, str(raw_id))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "club"


def _best_logo(logo: Optional[dict]) -> Optional[str]:
    """Largest available size url from a PlayHQ logo object."""
    sizes = (logo or {}).get("sizes") or []
    best, best_w = None, -1
    for s in sizes:
        w = ((s.get("dimensions") or {}).get("width")) or 0
        if s.get("url") and w > best_w:
            best, best_w = s["url"], w
    return best


def _season_year(season: dict) -> Optional[int]:
    name = (season.get("name") or "").strip()
    if re.fullmatch(r"\d{4}", name):
        return int(name)
    for key in ("endDate", "startDate"):
        val = season.get(key) or ""
        m = re.match(r"(\d{4})", val)
        if m:
            return int(m.group(1))
    return None


def _profile_name(profile: Optional[dict], fallback: Optional[str] = None) -> str:
    if profile:
        name = " ".join(p for p in [profile.get("firstName"), profile.get("lastName")] if p).strip()
        if name:
            return name
    return (fallback or "").strip() or "Unknown"


def _stat_count(stats: list[dict] | None, stat_type: str) -> int:
    for s in stats or []:
        if ((s.get("type") or {}).get("value")) == stat_type:
            try:
                return int(s.get("count") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


async def register_organisation(session: AsyncSession, playhq_org_id: str) -> Organisation:
    """Find-or-create the Organisation row for a PlayHQ org code. Pulls the
    org's profile (name/logo/contact) from PlayHQ on create."""
    oid = org_uuid(playhq_org_id)
    org = await session.get(Organisation, oid)
    if org:
        return org
    data = await phq.get_org_competitions(playhq_org_id)
    profile = data.get("organisation") or {}
    name = profile.get("name") or f"Club {playhq_org_id}"
    slug = _slugify(name)
    # Keep the slug unique without clobbering an existing club's.
    existing = await session.execute(select(Organisation.id).where(Organisation.slug == slug))
    if existing.first():
        slug = f"{slug}-{str(playhq_org_id)[:6]}"
    org = Organisation(
        id=oid,
        name=name,
        playhq_id=str(playhq_org_id),
        slug=slug,
        is_active=True,
        logo_url=_best_logo(profile.get("logo")),
        contact_email=profile.get("email"),
    )
    session.add(org)
    await session.commit()
    return org


async def _upsert_seasons(session: AsyncSession, org: Organisation,
                          competitions: list[dict]) -> list[dict]:
    """One Season row per (competition, season) pair. Returns
    [{season_row_id, playhq_season_id, name, year, status}] for the walk."""
    out = []
    for comp in competitions:
        comp_name = comp.get("name") or "Competition"
        for s in comp.get("seasons") or []:
            raw_id = s.get("id")
            if not raw_id:
                continue
            sid = derive_id(org.id, f"season:{raw_id}")
            row = await session.get(Season, sid)
            display = f"{comp_name} {s.get('name') or ''}".strip()
            year = _season_year(s)
            if row is None:
                row = Season(
                    id=sid, organisation_id=org.id, grassroots_id=str(raw_id),
                    name=display, year=year,
                )
                session.add(row)
            else:
                row.name = display
                row.year = year
            row.synced_at = datetime.now(timezone.utc)
            out.append({
                "row_id": sid, "playhq_id": str(raw_id), "name": display,
                "year": year, "status": ((s.get("status") or {}).get("value")),
            })
    await session.commit()
    return out


async def _upsert_teams_and_grades(session: AsyncSession, org: Organisation,
                                   season_row_id: uuid.UUID,
                                   playhq_season_id: str) -> list[dict]:
    """discoverTeams for one season → grades + afl_teams. Returns
    [{grade_row_id, playhq_grade_id, team_playhq_ids, team_names}]."""
    teams = await phq.get_org_teams(playhq_season_id, org.playhq_id)
    by_grade: dict[str, dict] = {}
    for t in teams:
        grade = t.get("grade") or {}
        raw_gid = grade.get("id")
        if not raw_gid:
            continue
        g = by_grade.setdefault(str(raw_gid), {
            "name": grade.get("name") or "Grade",
            "teams": [],
        })
        g["teams"].append(t)

    out = []
    for raw_gid, info in by_grade.items():
        gid = derive_id(org.id, f"grade:{raw_gid}")
        row = await session.get(Grade, gid)
        if row is None:
            row = Grade(id=gid, season_id=season_row_id, grassroots_id=raw_gid,
                        name=info["name"], playhq_id=raw_gid)
            session.add(row)
        else:
            row.name = info["name"]
            row.season_id = season_row_id
        team_ids, team_names = [], []
        for t in info["teams"]:
            raw_tid = str(t.get("id"))
            team_ids.append(raw_tid)
            team_names.append(t.get("name") or "")
            tid = derive_id(org.id, f"team:{raw_tid}")
            trow = await session.get(AflTeam, tid)
            if trow is None:
                trow = AflTeam(
                    id=tid, organisation_id=org.id, season_id=season_row_id,
                    grade_id=gid, playhq_id=raw_tid, name=t.get("name") or "",
                    gender=((t.get("gender") or {}).get("value")),
                    age_group=((t.get("ageGroup") or {}).get("value")),
                )
                session.add(trow)
            else:
                trow.name = t.get("name") or trow.name
                trow.season_id = season_row_id
                trow.grade_id = gid
        out.append({
            "grade_row_id": gid, "playhq_grade_id": raw_gid,
            "grade_name": info["name"],
            "team_playhq_ids": team_ids, "team_names": team_names,
        })
    await session.commit()
    return out


async def _resolve_org_player(session: AsyncSession, org: Organisation,
                              profile_id: Optional[str], participant_id: str,
                              name: str, cache: dict) -> Optional[uuid.UUID]:
    """Find-or-create the players row for one of OUR participants. Keyed on the
    PlayHQ profile id when present (stable per person); falls back to the
    participant id for anonymous/fill-in entries that carry no profile."""
    raw_key = str(profile_id or f"participant:{participant_id}")
    if raw_key in cache:
        return cache[raw_key]
    res = await session.execute(select(Player).where(
        Player.organisation_id == org.id, Player.grassroots_id == raw_key))
    player = res.scalar_one_or_none()
    if player is None:
        player = Player(
            id=derive_id(org.id, f"player:{raw_key}"),
            organisation_id=org.id,
            grassroots_id=raw_key,
            playhq_id=str(participant_id),
            name=name,
        )
        session.add(player)
        try:
            await session.flush()
        except Exception:
            # Unique-race fallback: someone else inserted this player in the
            # same run — reread.
            await session.rollback()
            res = await session.execute(select(Player).where(
                Player.organisation_id == org.id, Player.grassroots_id == raw_key))
            player = res.scalar_one()
    cache[raw_key] = player.id
    return player.id


def _extract_periods(side_stats: dict) -> list[dict]:
    """PlayHQ's periods[] is unordered and holds per-quarter DELTAS. Order by
    the canonical sequence (overtime after regulation by its sequence no)."""
    rows = []
    for p in (side_stats or {}).get("periods") or []:
        val = ((p.get("period") or {}).get("value")) or ""
        ot = p.get("overtimeSequenceNo") or 0
        base = _PERIOD_ORDER.get(val)
        if base is None:
            base = 4 + max(1, ot)  # OVERTIME or unknown: after regulation
        stats = p.get("statistics") or []
        rows.append({
            "period_number": base if not (val == "OVERTIME" and ot) else 4 + ot,
            "period_value": val or "UNKNOWN",
            "goals": _stat_count(stats, "6_POINT_SCORE"),
            "behinds": _stat_count(stats, "1_POINT_SCORE"),
            "score": _stat_count(stats, "TOTAL_SCORE"),
        })
    rows.sort(key=lambda r: r["period_number"])
    return rows


def _bog_by_line_key(side_stats: dict) -> tuple[dict, dict]:
    """Best-players maps for one side: by participant id and by normalised
    name (the feed sometimes returns name-only anonymous entries)."""
    by_pid, by_name = {}, {}
    for bp in (side_stats or {}).get("bestPlayers") or []:
        ranking = bp.get("ranking")
        part = bp.get("participant") or {}
        pid = part.get("id")
        name = _profile_name(part.get("profile"), part.get("name"))
        if pid:
            by_pid[str(pid)] = ranking
        if name and name != "Unknown":
            by_name[_norm_name(name)] = ranking
    return by_pid, by_name


async def _sync_game_stats(session: AsyncSession, org: Organisation,
                           game_row: Game, details: AflGameDetails,
                           our_team_ids: set[str], player_cache: dict) -> bool:
    """Pull gameView for one game and store scores, periods, player lines and
    best players. Returns True when stats landed."""
    gv = await phq.get_game(details.playhq_id)
    if not gv:
        return False

    status = ((gv.get("status") or {}).get("value")) or details.status
    details.status = status

    home = gv.get("home") or {}
    away = gv.get("away") or {}
    our_side = None
    if str(home.get("id")) in our_team_ids:
        our_side = "HOME"
    elif str(away.get("id")) in our_team_ids:
        our_side = "AWAY"
    details.our_side = our_side or details.our_side
    details.home_logo_url = _best_logo(home.get("logo")) or details.home_logo_url
    details.away_logo_url = _best_logo(away.get("logo")) or details.away_logo_url

    alloc = gv.get("allocation") or {}
    court = alloc.get("court") or {}
    venue = court.get("venue") or {}
    details.start_time = alloc.get("time") or details.start_time
    details.venue_name = court.get("name") or venue.get("name") or details.venue_name
    details.venue_suburb = venue.get("suburb") or details.venue_suburb
    game_row.venue = details.venue_name or game_row.venue

    result = gv.get("result") or {}
    rhome, raway = result.get("home") or {}, result.get("away") or {}
    details.home_score = rhome.get("score")
    details.away_score = raway.get("score")
    details.home_goals = _stat_count(rhome.get("statistics"), "TOTAL_GOALS")
    details.home_behinds = _stat_count(rhome.get("statistics"), "TOTAL_BEHINDS")
    details.away_goals = _stat_count(raway.get("statistics"), "TOTAL_GOALS")
    details.away_behinds = _stat_count(raway.get("statistics"), "TOTAL_BEHINDS")
    details.outcome_description = rhome.get("gameOutcomeDescription") or details.outcome_description

    winner_val = ((result.get("winner") or {}).get("value"))  # HOME | AWAY | None
    if winner_val == "HOME":
        game_row.winning_team = game_row.home_team
    elif winner_val == "AWAY":
        game_row.winning_team = game_row.away_team
    if status == "FINAL" and our_side:
        if winner_val is None and details.home_score is not None \
                and details.home_score == details.away_score:
            game_row.result = "D"
        elif winner_val:
            game_row.result = "W" if winner_val == our_side else "L"

    stats = gv.get("statistics") or {}
    await session.execute(delete(AflGamePeriod).where(AflGamePeriod.game_id == game_row.id))
    await session.execute(delete(AflPlayerGameLine).where(AflPlayerGameLine.game_id == game_row.id))

    for side, side_stats, team in (("HOME", stats.get("home"), home),
                                   ("AWAY", stats.get("away"), away)):
        side_stats = side_stats or {}
        for prow in _extract_periods(side_stats):
            session.add(AflGamePeriod(
                id=derive_id(org.id, f"period:{details.playhq_id}:{side}:{prow['period_number']}"),
                game_id=game_row.id, side=side, **prow,
            ))

        bog_by_pid, bog_by_name = _bog_by_line_key(side_stats)
        is_ours = (side == our_side)
        team_name = team.get("name")
        seen_participants: set[str] = set()
        for pl in side_stats.get("players") or []:
            pobj = pl.get("player") or {}
            participant_id = str(pobj.get("id") or "")
            if not participant_id or participant_id in seen_participants:
                continue
            seen_participants.add(participant_id)
            profile = pobj.get("profile")
            profile_id = (profile or {}).get("id")
            name = _profile_name(profile, pobj.get("name"))
            pstats = pl.get("statistics") or []
            ranking = bog_by_pid.get(participant_id)
            if ranking is None:
                ranking = bog_by_name.get(_norm_name(name))
            player_id = None
            if is_ours:
                player_id = await _resolve_org_player(
                    session, org, profile_id, participant_id, name, player_cache)
            session.add(AflPlayerGameLine(
                id=derive_id(org.id, f"line:{details.playhq_id}:{side}:{participant_id}"),
                game_id=game_row.id, side=side, team_name=team_name,
                playhq_participant_id=participant_id,
                playhq_profile_id=str(profile_id) if profile_id else None,
                player_id=player_id, name=name,
                jumper_number=str(pl.get("playerNumber")) if pl.get("playerNumber") is not None else None,
                goals=_stat_count(pstats, "6_POINT_SCORE"),
                behinds=_stat_count(pstats, "1_POINT_SCORE"),
                bog_ranking=ranking,
                player_points=pl.get("playerPoints"),
                is_captain=bool(pl.get("captain")),
            ))

        # A best player named without a player-list row (name-only anonymous
        # entry that matches nothing) still deserves a line so the BOG isn't
        # silently dropped — rare, but cheap to cover.
        for bp in side_stats.get("bestPlayers") or []:
            part = bp.get("participant") or {}
            pid = str(part.get("id") or "")
            if pid and pid in seen_participants:
                continue
            name = _profile_name(part.get("profile"), part.get("name"))
            if not pid and _norm_name(name) in {
                _norm_name(x.get("player", {}).get("name") or _profile_name(x.get("player", {}).get("profile")))
                for x in side_stats.get("players") or []
            }:
                continue
            key = pid or f"bogname:{_norm_name(name)}"
            player_id = None
            profile_id = (part.get("profile") or {}).get("id")
            if side == our_side:
                player_id = await _resolve_org_player(
                    session, org, profile_id, key, name, player_cache)
            session.add(AflPlayerGameLine(
                id=derive_id(org.id, f"line:{details.playhq_id}:{side}:{key}"),
                game_id=game_row.id, side=side, team_name=team_name,
                playhq_participant_id=key,
                playhq_profile_id=str(profile_id) if profile_id else None,
                player_id=player_id, name=name,
                goals=0, behinds=0, bog_ranking=bp.get("ranking"),
            ))
    details.synced_at = datetime.now(timezone.utc)
    return True


async def _sync_game_events(session: AsyncSession, org: Organisation,
                            game_row: Game, details: AflGameDetails) -> int:
    """Store the play-by-play feed. Scorer lines resolve to our players by
    jumper number + name against the game's own lines."""
    events = await phq.get_game_events(details.playhq_id)
    if not events:
        details.events_synced_at = datetime.now(timezone.utc)
        return 0

    res = await session.execute(select(AflPlayerGameLine).where(
        AflPlayerGameLine.game_id == game_row.id,
        AflPlayerGameLine.player_id.is_not(None)))
    our_lines = res.scalars().all()
    by_number = {l.jumper_number: l.player_id for l in our_lines if l.jumper_number}
    by_name = {_norm_name(l.name): l.player_id for l in our_lines}

    await session.execute(delete(AflGameEvent).where(AflGameEvent.game_id == game_row.id))
    ordered = sorted(events, key=lambda e: int(e.get("timestamp") or 0))
    for i, ev in enumerate(ordered):
        scorer_number = scorer_name = None
        player_id = None
        desc = ev.get("description")
        if desc:
            m = _SCORER_RE.match(desc)
            if m:
                scorer_number, scorer_name = m.group(1), m.group(2)
        our_side = details.our_side
        if scorer_name and our_side and ev.get("side") == our_side:
            player_id = by_number.get(scorer_number) or by_name.get(_norm_name(scorer_name))
        session.add(AflGameEvent(
            id=derive_id(org.id, f"event:{details.playhq_id}:{ev.get('id')}"),
            game_id=game_row.id,
            playhq_event_id=str(ev.get("id")),
            sequence=i,
            period_value=ev.get("period"),
            period_label=ev.get("eventSection"),
            clock=ev.get("sportEventStamp"),
            side=ev.get("side"),
            team_name=ev.get("title"),
            event_type=ev.get("score"),
            scorer_name=scorer_name,
            scorer_number=scorer_number,
            player_id=player_id,
            progressive_score=ev.get("progressiveScore"),
        ))
    details.events_synced_at = datetime.now(timezone.utc)
    return len(ordered)


async def _rollup_season_stats(session: AsyncSession, org_id: uuid.UUID) -> int:
    """Recompute afl_player_season_stats from the stored game lines — whole
    season rows (grade_id NULL) plus per-grade rows. Derived data: delete +
    reinsert for the org."""
    await session.execute(text(
        "DELETE FROM afl_player_season_stats WHERE organisation_id = :org"),
        {"org": str(org_id)})
    result = await session.execute(text("""
        INSERT INTO afl_player_season_stats
            (id, organisation_id, player_id, season_id, grade_id,
             games, goals, behinds, bog_count, captain_games, updated_at)
        SELECT gen_random_uuid(), :org, l.player_id, s.id, x.grade_id,
               COUNT(*) FILTER (WHERE l.played),
               COALESCE(SUM(l.goals), 0),
               COALESCE(SUM(l.behinds), 0),
               COUNT(*) FILTER (WHERE l.bog_ranking IS NOT NULL),
               COUNT(*) FILTER (WHERE l.is_captain),
               NOW()
        FROM afl_player_game_lines l
        JOIN games g   ON g.id = l.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        CROSS JOIN LATERAL (VALUES (NULL::uuid), (gr.id)) AS x(grade_id)
        WHERE l.player_id IS NOT NULL
          AND s.organisation_id = :org
        GROUP BY l.player_id, s.id, x.grade_id
    """), {"org": str(org_id)})
    return result.rowcount or 0


async def sync_organisation(org_id: uuid.UUID,
                            run_id: Optional[uuid.UUID] = None,
                            full: bool = False,
                            triggered_by_user_id: Optional[uuid.UUID] = None) -> dict:
    """Sync one club. Owns the run row only when it created it (same
    owns_run contract as the cricket engine — callers passing run_id must
    finish the run themselves)."""
    owns_run = run_id is None
    if owns_run:
        run_id = await start_sync_run(org_id, "afl_full" if full else "afl_sync",
                                      triggered_by_user_id=triggered_by_user_id)
    stats = {"seasons": 0, "grades": 0, "teams": 0, "games_discovered": 0,
             "games_stats_synced": 0, "events_stored": 0, "players": 0,
             "season_stat_rows": 0}
    try:
        async with async_session_maker() as session:
            org = await session.get(Organisation, org_id)
            if not org or not org.playhq_id:
                raise ValueError("Organisation missing or has no playhq_id")

            _progress(stats, "Discovering competitions", 2)
            await update_sync_run(run_id, stats)
            data = await phq.get_org_competitions(org.playhq_id, force=full)
            profile = data.get("organisation") or {}
            if profile.get("name"):
                org.name = org.name or profile["name"]
            if not org.logo_url:
                org.logo_url = _best_logo(profile.get("logo"))

            seasons = await _upsert_seasons(session, org, data.get("competitions") or [])
            stats["seasons"] = len(seasons)

            # ── Teams + grades per season ────────────────────────────────
            _progress(stats, "Discovering teams & grades", 8)
            await update_sync_run(run_id, stats)
            grade_infos = []
            for s in seasons:
                infos = await _upsert_teams_and_grades(
                    session, org, s["row_id"], s["playhq_id"])
                for gi in infos:
                    gi["season_row_id"] = s["row_id"]
                grade_infos.extend(infos)
            stats["grades"] = len(grade_infos)
            stats["teams"] = sum(len(g["team_playhq_ids"]) for g in grade_infos)

            our_team_ids = {tid for g in grade_infos for tid in g["team_playhq_ids"]}

            # ── Game discovery per grade ─────────────────────────────────
            todo: list[tuple[uuid.UUID, str]] = []  # (game row id, raw game id)
            for idx, gi in enumerate(grade_infos):
                _progress(stats, "Discovering games",
                          10 + 20 * (idx / max(1, len(grade_infos))),
                          idx, len(grade_infos))
                await update_sync_run(run_id, stats)
                rounds = await phq.get_grade_fixture(gi["playhq_grade_id"], force=full)
                for rnd in rounds:
                    for gm in rnd.get("games") or []:
                        home = gm.get("home") or {}
                        away = gm.get("away") or {}
                        h_id, a_id = str(home.get("id")), str(away.get("id"))
                        if h_id not in our_team_ids and a_id not in our_team_ids:
                            continue
                        raw_gid = str(gm.get("id"))
                        game_row_id = derive_id(org.id, f"game:{raw_gid}")
                        game_row = await session.get(Game, game_row_id)
                        our_side = "HOME" if h_id in our_team_ids else "AWAY"
                        opp = away if our_side == "HOME" else home
                        played_at = None
                        if gm.get("date"):
                            try:
                                played_at = date.fromisoformat(gm["date"][:10])
                            except ValueError:
                                pass
                        alloc = gm.get("allocation") or {}
                        court = alloc.get("court") or {}
                        if game_row is None:
                            game_row = Game(id=game_row_id, grade_id=gi["grade_row_id"])
                            session.add(game_row)
                        game_row.grade_id = gi["grade_row_id"]
                        game_row.played_at = played_at
                        game_row.home_team = home.get("name")
                        game_row.away_team = away.get("name")
                        game_row.home_club = ((home.get("organisation") or {}).get("name"))
                        game_row.away_club = ((away.get("organisation") or {}).get("name"))
                        game_row.opp_club_name = opp.get("name")
                        game_row.opp_org_id = str((opp.get("organisation") or {}).get("id") or "") or None
                        game_row.is_final = bool(rnd.get("isFinalsRound"))
                        game_row.venue = court.get("name") or ((court.get("venue") or {}).get("name")) or game_row.venue

                        details = await session.get(AflGameDetails, game_row_id)
                        status = ((gm.get("status") or {}).get("value"))
                        if details is None:
                            details = AflGameDetails(game_id=game_row_id, playhq_id=raw_gid)
                            session.add(details)
                        prev_status = details.status
                        details.round_name = rnd.get("name")
                        details.round_abbrev = rnd.get("abbreviatedName")
                        details.our_side = our_side
                        details.start_time = alloc.get("time") or details.start_time
                        # Only downgrade to fixture-level status if stats have
                        # never been synced (gameView is the authority after).
                        if details.synced_at is None or status == "FINAL":
                            details.status = status
                        stats["games_discovered"] += 1

                        needs_stats = (
                            full
                            or details.synced_at is None
                            or prev_status != "FINAL"
                        ) and status == "FINAL"
                        if needs_stats:
                            todo.append((game_row_id, raw_gid))
                await session.commit()

            # ── Per-game stats + events ──────────────────────────────────
            player_cache: dict = {}
            for idx, (game_row_id, raw_gid) in enumerate(todo):
                _progress(stats, "Syncing game stats",
                          30 + 60 * (idx / max(1, len(todo))), idx, len(todo))
                if idx % 5 == 0:
                    await update_sync_run(run_id, stats)
                game_row = await session.get(Game, game_row_id)
                details = await session.get(AflGameDetails, game_row_id)
                try:
                    ok = await _sync_game_stats(session, org, game_row, details,
                                                our_team_ids, player_cache)
                    if ok:
                        stats["games_stats_synced"] += 1
                        stats["events_stored"] += await _sync_game_events(
                            session, org, game_row, details)
                    await session.commit()
                except phq.PlayHQError as exc:
                    await session.rollback()
                    logger.warning("game %s stats failed: %s", raw_gid, exc)
                # Gentle pacing between game fetches.
                await asyncio.sleep(0.2)

            stats["players"] = len(player_cache)

            # ── Rollup ───────────────────────────────────────────────────
            _progress(stats, "Computing season totals", 95)
            await update_sync_run(run_id, stats)
            stats["season_stat_rows"] = await _rollup_season_stats(session, org.id)
            await session.commit()

        _progress(stats, "Done", 100)
        if owns_run:
            await finish_sync_run(run_id, stats)
        else:
            await update_sync_run(run_id, stats)
        return stats
    except Exception as exc:  # noqa: BLE001 — the run row must record any failure
        logger.exception("AFL sync failed for org %s", org_id)
        if owns_run:
            await finish_sync_run(run_id, stats, error=str(exc))
        raise
