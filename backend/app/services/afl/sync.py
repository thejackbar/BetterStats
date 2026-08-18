"""AFL sync engine — PlayHQ → the AFL silo's database.

Pipeline (each step verified live against Curtin Uni Wesley, org d14445c4 —
see docs/afl-playhq-data-source.md):

  1. discoverCompetitions  → seasons (one row per competition-season pair)
  2. discoverTeams         → our teams + their grades, per season
  2b. discoverTeamFixture  → per team, any grade it has since been re-graded
                             OUT of. Step 2 only ever names a team's current
                             grade, so without this the rounds played before a
                             mid-season move are never discovered at all.
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


async def _former_grades_for_team(playhq_season_id: str, raw_team_id: str,
                                  known_grade_ids: set[str]) -> dict[str, str]:
    """Grades this team played in that ``discoverTeams`` no longer reports —
    ``{playhq grade id: grade name}``, empty when there are none.

    A community-footy side is routinely re-graded a few rounds into a season
    (Hampton's Under 19s opened 2026 in Division 1 and moved to Division 2
    from round 6). ``discoverTeams`` answers with the grade the team is in
    NOW, so the rounds played before the move sit in a grade the ordinary
    discovery has no way to reach, and they simply never arrive. The team's
    own fixture is the one place PlayHQ carries the grade per round, so it is
    what tells us the earlier division existed at all.

    Filtered to the season being synced when the payload names it, so a team
    id PlayHQ happens to reuse across years can't drag another season's grade
    into this one.
    """
    found: dict[str, str] = {}
    for rnd in await phq.get_team_fixture(raw_team_id):
        for gm in rnd.get("games") or []:
            # Every game in the round comes back, not only this team's, so the
            # rounds our side had a bye in don't file another club's fixture
            # under a grade we never played.
            sides = (gm.get("home") or {}, gm.get("away") or {})
            if not any(str(s.get("id") or "") == raw_team_id for s in sides):
                continue
            grade = ((gm.get("round") or {}).get("grade")) or {}
            raw_gid = str(grade.get("id") or "")
            if not raw_gid or raw_gid in known_grade_ids or raw_gid in found:
                continue
            season = grade.get("season") or {}
            if season.get("id") and str(season["id"]) != str(playhq_season_id):
                continue
            found[raw_gid] = grade.get("name") or "Grade"
    return found


async def _upsert_teams_and_grades(session: AsyncSession, org: Organisation,
                                   season_row_id: uuid.UUID,
                                   playhq_season_id: str) -> list[dict]:
    """discoverTeams for one season → grades + afl_teams, plus any grade a
    team has since been re-graded out of (see ``_former_grades_for_team``).
    Returns [{grade_row_id, playhq_grade_id, team_playhq_ids, team_names}]."""
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

    # A former grade carries the same team, so it is added as its own entry
    # here and the game-discovery walk below picks it up with no further
    # special-casing. `current` is what keeps the team ROW pointed at the
    # grade the side is in now: a team can only hold one grade_id, and the
    # division it has moved on from is not it.
    current_grade_ids = set(by_grade)
    for t in teams:
        raw_tid = str(t.get("id") or "")
        if not raw_tid:
            continue
        for raw_gid, gname in (await _former_grades_for_team(
                playhq_season_id, raw_tid, current_grade_ids)).items():
            entry = by_grade.setdefault(str(raw_gid), {"name": gname, "teams": []})
            entry["teams"].append(t)

    out = []
    for raw_gid, info in by_grade.items():
        is_current = raw_gid in current_grade_ids
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
            elif is_current:
                trow.name = t.get("name") or trow.name
                trow.season_id = season_row_id
                trow.grade_id = gid
        out.append({
            "grade_row_id": gid, "playhq_grade_id": raw_gid,
            "grade_name": info["name"], "former_grade": not is_current,
            "team_playhq_ids": team_ids, "team_names": team_names,
        })
    await session.commit()
    return out


async def _resolve_org_player(session: AsyncSession, org_id: uuid.UUID,
                              profile_id: Optional[str], participant_id: str,
                              name: str, cache: dict) -> Optional[uuid.UUID]:
    """Find-or-create the players row for one of OUR participants. Keyed on the
    PlayHQ profile id when present (stable per person); falls back to the
    participant id for anonymous/fill-in entries that carry no profile."""
    raw_key = str(profile_id or f"participant:{participant_id}")
    if raw_key in cache:
        return cache[raw_key]
    res = await session.execute(select(Player).where(
        Player.organisation_id == org_id, Player.grassroots_id == raw_key))
    player = res.scalar_one_or_none()
    if player is None:
        player = Player(
            id=derive_id(org_id, f"player:{raw_key}"),
            organisation_id=org_id,
            grassroots_id=raw_key,
            playhq_id=str(participant_id),
            name=name,
        )
        session.add(player)
        # No try/rollback here: a rollback expires EVERY object in the session,
        # and the next plain attribute read (details.playhq_id, org.id, ...)
        # then triggers a lazy re-SELECT outside an await — the
        # "greenlet_spawn has not been called" failure. The sync is
        # single-threaded, so there's no real insert race; a genuine failure
        # bubbles to the per-game handler, which rolls back cleanly and moves
        # on to the next game.
        await session.flush()
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


async def _sync_game_stats(session: AsyncSession, org_id: uuid.UUID,
                           game_row: Game, details: AflGameDetails,
                           our_team_ids: set[str], player_cache: dict) -> bool:
    """Pull gameView for one game and store scores, periods, player lines and
    best players. Returns True when stats landed."""
    # Capture the ORM reads we need as plain values ONCE, before any flush
    # could expire them mid-loop (see _resolve_org_player's note).
    playhq_gid = details.playhq_id
    game_pk = game_row.id

    gv = await phq.get_game(playhq_gid)
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
    await session.execute(delete(AflGamePeriod).where(AflGamePeriod.game_id == game_pk))
    await session.execute(delete(AflPlayerGameLine).where(AflPlayerGameLine.game_id == game_pk))

    for side, side_stats, team in (("HOME", stats.get("home"), home),
                                   ("AWAY", stats.get("away"), away)):
        side_stats = side_stats or {}
        for prow in _extract_periods(side_stats):
            session.add(AflGamePeriod(
                id=derive_id(org_id, f"period:{playhq_gid}:{side}:{prow['period_number']}"),
                game_id=game_pk, side=side, **prow,
            ))

        bog_by_pid, bog_by_name = _bog_by_line_key(side_stats)
        # Attribute by the side's own team id, not our_side — when two of the
        # club's teams meet each other, BOTH sides' players are ours.
        is_ours = str(team.get("id")) in our_team_ids
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
                    session, org_id, profile_id, participant_id, name, player_cache)
            session.add(AflPlayerGameLine(
                id=derive_id(org_id, f"line:{playhq_gid}:{side}:{participant_id}"),
                game_id=game_pk, side=side, team_name=team_name,
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
            if is_ours:
                player_id = await _resolve_org_player(
                    session, org_id, profile_id, key, name, player_cache)
            session.add(AflPlayerGameLine(
                id=derive_id(org_id, f"line:{playhq_gid}:{side}:{key}"),
                game_id=game_pk, side=side, team_name=team_name,
                playhq_participant_id=key,
                playhq_profile_id=str(profile_id) if profile_id else None,
                player_id=player_id, name=name,
                goals=0, behinds=0, bog_ranking=bp.get("ranking"),
            ))
    details.synced_at = datetime.now(timezone.utc)
    return True


async def _sync_game_events(session: AsyncSession, org_id: uuid.UUID,
                            game_row: Game, details: AflGameDetails) -> int:
    """Store the play-by-play feed. Scorer lines resolve to our players by
    jumper number + name against the game's own lines."""
    # Plain values captured once — see _resolve_org_player's note on why ORM
    # attribute reads must not happen after a flush/rollback mid-run.
    playhq_gid = details.playhq_id
    game_pk = game_row.id
    events = await phq.get_game_events(playhq_gid)
    if not events:
        details.events_synced_at = datetime.now(timezone.utc)
        return 0

    res = await session.execute(select(AflPlayerGameLine).where(
        AflPlayerGameLine.game_id == game_pk,
        AflPlayerGameLine.player_id.is_not(None)))
    our_lines = res.scalars().all()
    # Per-side maps: jumper numbers repeat across the two teams, and in an
    # intra-club game both sides are ours.
    by_number = {(l.side, l.jumper_number): l.player_id for l in our_lines if l.jumper_number}
    by_name = {(l.side, _norm_name(l.name)): l.player_id for l in our_lines}

    await session.execute(delete(AflGameEvent).where(AflGameEvent.game_id == game_pk))
    ordered = sorted(events, key=lambda e: int(e.get("timestamp") or 0))
    for i, ev in enumerate(ordered):
        scorer_number = scorer_name = None
        player_id = None
        desc = ev.get("description")
        if desc:
            m = _SCORER_RE.match(desc)
            if m:
                scorer_number, scorer_name = m.group(1), m.group(2)
        ev_side = ev.get("side")
        if scorer_name and ev_side:
            player_id = (by_number.get((ev_side, scorer_number))
                         or by_name.get((ev_side, _norm_name(scorer_name))))
        session.add(AflGameEvent(
            id=derive_id(org_id, f"event:{playhq_gid}:{ev.get('id')}"),
            game_id=game_pk,
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


async def _discover_grade_games(session: AsyncSession, org_pk: uuid.UUID,
                                grade_row_id: uuid.UUID, playhq_grade_id: str,
                                our_team_ids: set[str], full: bool,
                                stats: dict) -> list[tuple[uuid.UUID, str]]:
    """Walk one grade's fixture (discoverGradeFixture), upserting Game +
    AflGameDetails for every game either side of which is in
    ``our_team_ids``. Returns the (game row id, raw game id) pairs whose
    stats still need a gameView fetch.

    Extracted so ``link_grade_manually`` (the admin override for a grade our
    own discoverTeams call doesn't currently report — e.g. a team re-graded
    into a different division mid-season, so its OLD grade drops out of the
    "current teams" snapshot discoverTeams answers with) can walk a single
    grade exactly the way the main sync loop below does, rather than a
    second, drifting copy of this logic.
    """
    todo: list[tuple[uuid.UUID, str]] = []
    rounds = await phq.get_grade_fixture(playhq_grade_id, force=full)
    for rnd in rounds:
        for gm in rnd.get("games") or []:
            home = gm.get("home") or {}
            away = gm.get("away") or {}
            h_id, a_id = str(home.get("id")), str(away.get("id"))
            if h_id not in our_team_ids and a_id not in our_team_ids:
                continue
            raw_gid = str(gm.get("id"))
            game_row_id = derive_id(org_pk, f"game:{raw_gid}")
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
                game_row = Game(id=game_row_id, grade_id=grade_row_id)
                session.add(game_row)
            game_row.grade_id = grade_row_id
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
            # Only downgrade to fixture-level status if stats have never
            # been synced (gameView is the authority after).
            if details.synced_at is None or status == "FINAL":
                details.status = status
            stats["games_discovered"] = stats.get("games_discovered", 0) + 1

            needs_stats = (
                full
                or details.synced_at is None
                or prev_status != "FINAL"
            ) and status == "FINAL"
            if needs_stats:
                todo.append((game_row_id, raw_gid))
    return todo


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
    stats = {"seasons": 0, "grades": 0, "teams": 0, "former_grades": 0,
             "games_discovered": 0, "games_stats_synced": 0, "games_failed": 0,
             "events_stored": 0, "players": 0, "season_stat_rows": 0}
    try:
        async with async_session_maker() as session:
            org = await session.get(Organisation, org_id)
            if not org or not org.playhq_id:
                raise ValueError("Organisation missing or has no playhq_id")
            # Plain copies: a rollback anywhere below expires every ORM object
            # in the session, and a later plain read of org.id would then try
            # to re-SELECT outside an await ("greenlet_spawn has not been
            # called"). org_pk/org_playhq are immune to that.
            org_pk = org.id
            org_playhq = org.playhq_id

            _progress(stats, "Discovering competitions", 2)
            await update_sync_run(run_id, stats)
            data = await phq.get_org_competitions(org_playhq, force=full)
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
            # Surfaced on the Data Sync page so a re-grade the club never told
            # us about reads as a thing that was found, rather than a silent
            # jump in the grade count.
            stats["former_grades"] = sum(1 for g in grade_infos if g.get("former_grade"))

            our_team_ids = {tid for g in grade_infos for tid in g["team_playhq_ids"]}

            # ── Game discovery per grade ─────────────────────────────────
            todo: list[tuple[uuid.UUID, str]] = []  # (game row id, raw game id)
            for idx, gi in enumerate(grade_infos):
                _progress(stats, "Discovering games",
                          10 + 20 * (idx / max(1, len(grade_infos))),
                          idx, len(grade_infos))
                await update_sync_run(run_id, stats)
                todo.extend(await _discover_grade_games(
                    session, org_pk, gi["grade_row_id"], gi["playhq_grade_id"],
                    our_team_ids, full, stats))
                await session.commit()

            # ── Per-game stats + events ──────────────────────────────────
            player_cache: dict = {}
            for idx, (game_row_id, raw_gid) in enumerate(todo):
                _progress(stats, "Syncing game stats",
                          30 + 60 * (idx / max(1, len(todo))), idx, len(todo))
                if idx % 5 == 0:
                    await update_sync_run(run_id, stats)
                # Interim rollup so a first big sync fills the public
                # leaderboards progressively instead of only at the end.
                if idx and idx % 100 == 0:
                    try:
                        await _rollup_season_stats(session, org_pk)
                        await session.commit()
                    except Exception:  # noqa: BLE001 — final rollup still runs
                        await session.rollback()
                game_row = await session.get(Game, game_row_id)
                details = await session.get(AflGameDetails, game_row_id)
                try:
                    ok = await _sync_game_stats(session, org_pk, game_row, details,
                                                our_team_ids, player_cache)
                    if ok:
                        stats["games_stats_synced"] += 1
                        stats["events_stored"] += await _sync_game_events(
                            session, org_pk, game_row, details)
                    await session.commit()
                except Exception as exc:  # noqa: BLE001
                    # One unusable game (upstream error, unexpected payload
                    # shape) must not abort a 900-game sync. Roll back just
                    # this game's writes and carry on; the count surfaces on
                    # the admin Data Sync page.
                    await session.rollback()
                    stats["games_failed"] = stats.get("games_failed", 0) + 1
                    logger.warning("game %s stats failed: %s", raw_gid, exc)
                # Gentle pacing between game fetches.
                await asyncio.sleep(0.2)

            stats["players"] = len(player_cache)

            # ── Rollup ───────────────────────────────────────────────────
            _progress(stats, "Computing season totals", 95)
            await update_sync_run(run_id, stats)
            stats["season_stat_rows"] = await _rollup_season_stats(session, org_pk)
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


# ─── Manually linking a grade discoverTeams doesn't (or no longer) report ──
#
# discoverTeams answers with each team's CURRENT grade only — there is no
# "grade history" in the payload. A community-footy team that gets re-graded
# mid-season (a round-robin split, promotion/relegation after the first few
# rounds) drops its OLD grade out of every future sync's "teams & grades"
# snapshot, and — if the club was only synced for the first time after the
# move — that old grade's rounds may never have been discovered at all, even
# though the aggregate participant-stats feed (a different, grade-agnostic
# endpoint) still knows the player played them. This is the admin's manual
# way back in: paste a PlayHQ link to any one match from the missing grade
# and we pull the whole thing in.

_PLAYHQ_GAME_URL_RE = re.compile(r"game-centre/([0-9a-zA-Z]{4,12})", re.I)
_BARE_GAME_CODE_RE = re.compile(r"^[0-9a-zA-Z]{4,12}$")


def parse_playhq_game_ref(raw: str) -> Optional[str]:
    """Pull the short game-centre code out of a pasted PlayHQ match URL, or
    accept a bare code typed in directly. None for anything else. Unlike
    cricket's Grassroots API, this short code genuinely IS the AFL discover
    API's own gameID (verified live — see the CLAUDE.md note on the
    cricket/AFL discrepancy), so no candidate-matching is needed once it's
    parsed out."""
    text = (raw or "").strip()
    if not text:
        return None
    m = _PLAYHQ_GAME_URL_RE.search(text)
    if m:
        return m.group(1)
    if _BARE_GAME_CODE_RE.match(text):
        return text
    return None


def _norm_org_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _match_our_side(org: Organisation, home: dict, away: dict) -> Optional[str]:
    """Which side of one game is this club — matched by PlayHQ organisation
    id first (the reliable signal), club name only as a fallback for an
    older row with no id captured. Returns 'home' | 'away' | None."""
    for side_name, side in (("home", home), ("away", away)):
        side_org = (side or {}).get("organisation") or {}
        if org.playhq_id and str(side_org.get("id") or "") == str(org.playhq_id):
            return side_name
    for side_name, side in (("home", home), ("away", away)):
        side_org = (side or {}).get("organisation") or {}
        if org.name and _norm_org_name(side_org.get("name") or "") == _norm_org_name(org.name):
            return side_name
    return None


async def resolve_grade_from_game(org: Organisation, raw_ref: str) -> dict:
    """Resolve a pasted PlayHQ match link (or bare short code) into the
    grade it belongs to, so the admin never has to go hunting for a raw
    grade id — any one match from the missing rounds is enough."""
    game_id = parse_playhq_game_ref(raw_ref)
    if not game_id:
        raise ValueError("Paste a PlayHQ match link (or its short code)")
    game = await phq.get_game(game_id, force=True)
    if not game:
        raise ValueError("PlayHQ doesn't recognise that match")
    grade = ((game.get("round") or {}).get("grade")) or {}
    grade_id = grade.get("id")
    if not grade_id:
        raise ValueError("That match has no grade on PlayHQ")

    home = game.get("home") or {}
    away = game.get("away") or {}
    season = grade.get("season") or {}
    return {
        "grade_id": str(grade_id),
        "grade_name": grade.get("name") or "Grade",
        "playhq_season_name": season.get("name"),
        "competition_name": ((season.get("competition") or {}).get("name")),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_club": (home.get("organisation") or {}).get("name"),
        "away_club": (away.get("organisation") or {}).get("name"),
        "matched_side": _match_our_side(org, home, away),
    }


async def link_grade_manually(org_id: uuid.UUID, season_row_id: uuid.UUID,
                              raw_grade_id: str, grade_name: str) -> dict:
    """Pull one grade's whole fixture in directly by id, bypassing
    discoverTeams entirely — the admin override for a grade the ordinary
    sync can no longer discover on its own (see the module note above).
    Raises when nothing in the fixture belongs to this club, so a mistyped
    id can't silently create an empty grade with no games."""
    async with async_session_maker() as session:
        org = await session.get(Organisation, org_id)
        if not org or not org.playhq_id:
            raise ValueError("Organisation missing or has no playhq_id")
        season = await session.get(Season, season_row_id)
        if not season or season.organisation_id != org.id:
            raise ValueError("Season not found for this club")

        rounds = await phq.get_grade_fixture(raw_grade_id, force=True)
        if not rounds:
            raise ValueError("PlayHQ returned no fixture for that grade")

        our_team_ids: set[str] = set()
        team_names: dict[str, str] = {}
        for rnd in rounds:
            for gm in rnd.get("games") or []:
                home, away = gm.get("home") or {}, gm.get("away") or {}
                our_side = _match_our_side(org, home, away)
                if not our_side:
                    continue
                side = home if our_side == "home" else away
                tid = str(side.get("id") or "")
                if tid:
                    our_team_ids.add(tid)
                    if side.get("name"):
                        team_names[tid] = side["name"]

        if not our_team_ids:
            raise ValueError("No games in that grade's fixture belong to this club")

        gid = derive_id(org.id, f"grade:{raw_grade_id}")
        grade_row = await session.get(Grade, gid)
        if grade_row is None:
            grade_row = Grade(id=gid, season_id=season_row_id,
                              grassroots_id=str(raw_grade_id),
                              name=grade_name or "Grade", playhq_id=str(raw_grade_id))
            session.add(grade_row)
        else:
            grade_row.season_id = season_row_id
            if grade_name:
                grade_row.name = grade_name

        # A team discovered this way carries no gender/age_group — that
        # only ever comes from discoverTeams, and neither is displayed
        # anywhere that would read as a gap.
        for tid in our_team_ids:
            trow_id = derive_id(org.id, f"team:{tid}")
            trow = await session.get(AflTeam, trow_id)
            if trow is None:
                trow = AflTeam(id=trow_id, organisation_id=org.id, season_id=season_row_id,
                               grade_id=gid, playhq_id=tid, name=team_names.get(tid, "Team"))
                session.add(trow)
            else:
                trow.grade_id = gid
                trow.season_id = season_row_id
        await session.commit()

        stats: dict = {}
        todo = await _discover_grade_games(
            session, org.id, gid, str(raw_grade_id), our_team_ids, True, stats)
        await session.commit()

        player_cache: dict = {}
        games_stats_synced = 0
        for game_row_id, raw_gid in todo:
            game_row = await session.get(Game, game_row_id)
            details = await session.get(AflGameDetails, game_row_id)
            try:
                ok = await _sync_game_stats(session, org.id, game_row, details,
                                            our_team_ids, player_cache)
                if ok:
                    games_stats_synced += 1
                    await _sync_game_events(session, org.id, game_row, details)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — one bad game must not sink the rest
                await session.rollback()
                logger.warning("link_grade_manually: game %s stats failed: %s", raw_gid, exc)
            await asyncio.sleep(0.2)

        await _rollup_season_stats(session, org.id)
        await session.commit()

        return {
            "grade_id": str(gid),
            "grade_name": grade_row.name,
            "teams_found": len(our_team_ids),
            "games_discovered": stats.get("games_discovered", 0),
            "games_stats_synced": games_stats_synced,
        }
