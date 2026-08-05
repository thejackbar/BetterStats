"""AFL-specific tables, on the same SQLAlchemy Base as the shared models.

These only ever hold data in an AFL silo's database (bs-afl-database) — the
cricket deployment never imports this module at runtime, and the AFL
deployment reuses the shared tables (organisations, users, seasons, grades,
players, games, sync_runs, ...) from app.models.db alongside these.

Identity scheme (see docs/afl-betterstats-plan.md): every synced row's PK is
uuid5(organisation_id, playhq_id) — per-club from day one, so the shared-GUID
collisions the cricket product had to retrofit fixes for (players/grades/
seasons/games) are impossible here. The raw PlayHQ id is stored alongside and
is what every PlayHQ API call uses.
"""
from sqlalchemy import (
    Column, Boolean, Integer, Text, Date, ForeignKey, TIMESTAMP, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.db import Base


class AflTeam(Base):
    """One of the club's team entries in a grade — e.g. "Curtin Uni Wesley (A)"
    in "A Grade Men". From discoverTeams. A team belongs to a grade belongs to
    a season (both shared tables)."""
    __tablename__ = "afl_teams"
    __table_args__ = (
        UniqueConstraint("organisation_id", "playhq_id", name="uq_afl_team_org_playhq"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)  # uuid5(org, playhq_id)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"), nullable=True)
    playhq_id = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    gender = Column(Text, nullable=True)       # MENS | WOMENS | MIXED | ...
    age_group = Column(Text, nullable=True)
    synced_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class AflGameDetails(Base):
    """1:1 extension of the shared games row with the AFL-shaped result data.

    The shared games table carries what it already models well (grade link,
    date, team names, result letter, winner, venue, is_final); everything
    AFL-specific lands here rather than as nullable cricket-table columns.
    """
    __tablename__ = "afl_game_details"

    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    # Raw PlayHQ game id (the game-centre URL code). NULL for a game that came
    # from the Import Results tool — there is no PlayHQ game behind it.
    playhq_id = Column(Text, nullable=True)
    round_name = Column(Text, nullable=True)          # "Round 16"
    round_abbrev = Column(Text, nullable=True)        # "R16"
    status = Column(Text, nullable=True)               # UPCOMING | FINAL | ...
    start_time = Column(Text, nullable=True)           # "14:00:00" as given
    our_side = Column(Text, nullable=True)             # HOME | AWAY
    home_goals = Column(Integer, nullable=True)
    home_behinds = Column(Integer, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    away_behinds = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    # PlayHQ's own pre-written margin sentence ("X won by 6 points") — never
    # computed by us when the feed provides it.
    outcome_description = Column(Text, nullable=True)
    home_logo_url = Column(Text, nullable=True)
    away_logo_url = Column(Text, nullable=True)
    venue_name = Column(Text, nullable=True)
    venue_suburb = Column(Text, nullable=True)
    events_synced_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # When the per-game STATS last landed (gameView parsed into periods/lines).
    # NULL = discovered only — this is the incremental sync's "still needs a
    # stats pull" signal, so it must NOT have a server default (a discovery
    # insert would otherwise read as already-synced and be skipped forever).
    synced_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # ── Import Results (routers/afl/result_imports.py) ────────────────────
    # 'playhq' (synced) | 'import' (a row from a club's own results
    # spreadsheet). Everything below is only ever set on an imported game;
    # source is what keeps the two apart everywhere it matters — the
    # already-synced guard at import time, and the undo, which must never be
    # able to delete a game the sync has since taken over.
    source = Column(Text, nullable=False, default="playhq", server_default="playhq")
    import_batch_id = Column(UUID(as_uuid=True), nullable=True)
    import_ref = Column(Text, nullable=True)       # the sheet's own game id, kept for traceability
    is_bye = Column(Boolean, nullable=False, default=False, server_default="false")
    is_forfeit = Column(Boolean, nullable=False, default=False, server_default="false")
    # What the club actually wrote in its results column ("Won on Forfiet",
    # "Missing Score") — the derived W/L/D lives on games.result, this keeps
    # the original wording so a club can always see its own record.
    result_note = Column(Text, nullable=True)


class AflGamePeriod(Base):
    """Per-quarter (and overtime) score for one side of one game.

    PlayHQ returns per-period DELTAS in arbitrary order — the sync stores them
    ordered by the canonical period sequence with period_number 1..4 (+5..N
    for overtime by overtimeSequenceNo). Cumulative display totals are summed
    on read.
    """
    __tablename__ = "afl_game_periods"
    __table_args__ = (
        UniqueConstraint("game_id", "side", "period_number", name="uq_afl_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    side = Column(Text, nullable=False)                # HOME | AWAY
    period_number = Column(Integer, nullable=False)    # 1..4, then overtime
    period_value = Column(Text, nullable=False)        # FIRST_QTR | ... | OVERTIME
    goals = Column(Integer, nullable=False, default=0)
    behinds = Column(Integer, nullable=False, default=0)
    score = Column(Integer, nullable=False, default=0)


class AflPlayerGameLine(Base):
    """One player's line in one game — BOTH sides are stored (the match page
    renders the full game from our own DB, no live PlayHQ fetch). Our own
    club's participants resolve to a players row via player_id; the
    opposition's stay name-only (player_id NULL), same posture as cricket's
    opposition scorecard rows.
    """
    __tablename__ = "afl_player_game_lines"
    __table_args__ = (
        UniqueConstraint("game_id", "side", "playhq_participant_id", name="uq_afl_line"),
        Index("ix_afl_line_player", "player_id"),
        Index("ix_afl_line_game", "game_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    side = Column(Text, nullable=False)                # HOME | AWAY
    team_name = Column(Text, nullable=True)
    # Raw PlayHQ ids. participant = per-registration, profile = the stable
    # person-level id (players.grassroots_id keys on profile id).
    playhq_participant_id = Column(Text, nullable=False)
    playhq_profile_id = Column(Text, nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    name = Column(Text, nullable=False)
    jumper_number = Column(Text, nullable=True)
    goals = Column(Integer, nullable=False, default=0)
    behinds = Column(Integer, nullable=False, default=0)
    # Best on Ground: NULL = not named in best players; 1 = named first.
    # Leaderboards count non-NULL (flat count); ranking kept for future
    # weighted views.
    bog_ranking = Column(Integer, nullable=True)
    player_points = Column(Integer, nullable=True)     # the competition PP column
    is_captain = Column(Boolean, nullable=False, default=False, server_default="false")
    played = Column(Boolean, nullable=False, default=True, server_default="true")


class AflGameEvent(Base):
    """Play-by-play scoring feed, stored at sync time from the spectator API
    so the public match page reads our own DB. sequence orders the feed
    (derived from the event timestamps, oldest first)."""
    __tablename__ = "afl_game_events"
    __table_args__ = (
        UniqueConstraint("game_id", "playhq_event_id", name="uq_afl_event"),
        Index("ix_afl_event_game", "game_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    playhq_event_id = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)
    period_value = Column(Text, nullable=True)         # FIRST_QTR | ...
    period_label = Column(Text, nullable=True)         # "1st Quarter"
    clock = Column(Text, nullable=True)                # "05:32" (count-up stamp)
    side = Column(Text, nullable=True)                 # HOME | AWAY
    team_name = Column(Text, nullable=True)
    event_type = Column(Text, nullable=True)           # Goal | Behind
    scorer_name = Column(Text, nullable=True)
    scorer_number = Column(Text, nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    progressive_score = Column(Text, nullable=True)    # "85 - 49" as given
    event_timestamp = Column(Text, nullable=True)      # raw ms-epoch string from the feed


class AflPlayerSeasonStats(Base):
    """The season rollup, recomputed from afl_player_game_lines on every sync
    (delete + reinsert per org — derived data, the game lines are the source
    of truth). grade_id NULL = the whole-season row; per-grade rows sit
    alongside for grade-filtered views.
    """
    __tablename__ = "afl_player_season_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "grade_id", name="uq_afl_pss"),
        Index("ix_afl_pss_season", "season_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"), nullable=True)
    games = Column(Integer, nullable=False, default=0)
    goals = Column(Integer, nullable=False, default=0)
    behinds = Column(Integer, nullable=False, default=0)
    bog_count = Column(Integer, nullable=False, default=0)
    captain_games = Column(Integer, nullable=False, default=0)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
