from sqlalchemy import (
    Column, Boolean, Integer, Numeric, Date, Text, ForeignKey,
    TIMESTAMP, JSON, UniqueConstraint, LargeBinary
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import func
import uuid

from app.config.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_maker() as session:
        yield session


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=True)
    username = Column(Text, unique=True, nullable=True)
    password_hash = Column(Text)
    display_name = Column(Text, nullable=True)
    last_login_at = Column(TIMESTAMP(timezone=True), nullable=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(TIMESTAMP(timezone=True), nullable=True)
    last_notification_seen_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_seen_app_version = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    memberships = relationship("ClubMembership", back_populates="user")


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    short_name = Column(Text)
    playhq_id = Column(Text, nullable=True)
    slug = Column(Text, unique=True, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    primary_color = Column(Text, default="#16c784", nullable=True)
    accent_color = Column(Text, default="#243352", nullable=True)
    logo_url = Column(Text, nullable=True)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime = Column(Text, nullable=True)
    hero_image_url = Column(Text, nullable=True)
    theme_mode = Column(Text, default="auto", nullable=True)
    theme_config = Column(JSONB, nullable=True)
    contact_email = Column(Text, nullable=True)
    player_name_format = Column(Text, default="last_first", nullable=True)
    # BetterSelect: a player is "dormant" (hidden from default selection) if they
    # haven't appeared within this many months. Also bounds team squad
    # suggestions. Default 24 (migration 048).
    dormancy_months = Column(Integer, nullable=False, server_default="24", default=24)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    seasons = relationship("Season", back_populates="organisation")
    players = relationship("Player", back_populates="organisation")
    memberships = relationship("ClubMembership", back_populates="club")


class Sponsor(Base):
    __tablename__ = "org_sponsors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    website_url = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubMembership(Base):
    __tablename__ = "club_memberships"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_club_membership"),
        # An admin account is linked to exactly one club.
        UniqueConstraint("user_id", name="uq_membership_one_per_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, default="club_admin", nullable=False)
    # JSONB array of capability strings. Empty list = "no extra caps beyond
    # role". For super_admin/club_admin the list is ignored (those roles
    # imply all caps). For club_member, this is the explicit allowlist.
    capabilities = Column(JSONB, default=list, nullable=False, server_default="[]")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    club = relationship("Organisation", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class Season(Base):
    __tablename__ = "seasons"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    # Per-club derived id (uuid5 of org id + grassroots_id). The raw Cricket
    # Australia season GUID lives in grassroots_id — it is shared across clubs
    # so it cannot be the primary key.
    grassroots_id = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    year = Column(Integer)
    synced_at = Column(TIMESTAMP(timezone=True))
    display_order = Column(Integer, nullable=True)

    organisation = relationship("Organisation", back_populates="seasons")
    grades = relationship("Grade", back_populates="season")
    player_stats = relationship("PlayerSeasonStats", back_populates="season")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(UUID(as_uuid=True), primary_key=True)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"))
    name = Column(Text, nullable=False)
    display_name_override = Column(Text, nullable=True)
    playhq_id = Column(Text, nullable=True)
    # Fee-tracking format override. NULL = derive from Game.match_format.
    # One of: 'two_day' | 'one_day' | 't20' | 'women' | 'exclude'.
    # 'women' is needed because women's (PSWL) grades come through as plain
    # One Day / T20 and can't be told apart from the men's competition;
    # 'exclude' drops a grade from match-fee accrual entirely.
    fee_format = Column(Text, nullable=True)

    season = relationship("Season", back_populates="grades")
    games = relationship("Game", back_populates="grade")

    @property
    def display_name(self) -> str:
        return self.display_name_override or self.name


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("organisation_id", "playhq_id", name="uq_player_org_playhq_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    display_name_override = Column(Text, nullable=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    playhq_id = Column(Text, nullable=True)
    photo_url = Column(Text, nullable=True)
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime = Column(Text, nullable=True)
    gender = Column(Text, nullable=True)
    is_player = Column(Boolean, default=True, nullable=True)
    player_role = Column(Text, nullable=True)
    is_overseas = Column(Boolean, nullable=True)
    overseas_country = Column(Text, nullable=True)
    # BetterSelect cricket attributes for selection filters (migration 050).
    batting_hand = Column(Text, nullable=True)        # 'LEFT' | 'RIGHT'
    bowling_action = Column(Text, nullable=True)      # 'RIGHT_ARM' | 'LEFT_ARM'
    bowling_type = Column(Text, nullable=True)        # FAST|FAST_MEDIUM|MEDIUM|MEDIUM_FAST|FINGER_SPIN|WRIST_SPIN
    is_opening_batsman = Column(Boolean, nullable=True)
    # claimed / user_id retained as columns but no longer used in business logic
    claimed = Column(Boolean, default=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    # BetterSelect: admin-managed contact + selection attributes (migration 044)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    skill_positions = Column(JSONB, default=list, nullable=False, server_default="[]")  # e.g. ["BAT","WKT"]
    status = Column(Text, default="active", nullable=False, server_default="active")  # active | inactive

    organisation = relationship("Organisation", back_populates="players")
    batting_innings = relationship("BattingInnings", back_populates="player")
    bowling_spells = relationship("BowlingSpell", back_populates="player")
    fielding_stats = relationship("FieldingStat", back_populates="player")
    appearances = relationship("GameAppearance", back_populates="player")
    milestones = relationship("Milestone", back_populates="player")
    season_stats = relationship("PlayerSeasonStats", back_populates="player")

    @property
    def display_name(self) -> str:
        return self.display_name_override or self.name


class Game(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"))
    played_at = Column(Date)
    home_team = Column(Text)
    away_team = Column(Text)
    home_club = Column(Text)
    away_club = Column(Text)
    opp_org_id = Column(Text)
    opp_club_name = Column(Text)
    result = Column(Text)
    winning_team = Column(Text)
    is_final = Column(Boolean, default=False, nullable=False, server_default='false')
    raw_payload = Column(JSON)
    venue = Column(Text)
    match_format = Column(Text, nullable=True)

    grade = relationship("Grade", back_populates="games")
    batting_innings = relationship("BattingInnings", back_populates="game")
    bowling_spells = relationship("BowlingSpell", back_populates="game")
    fielding_stats = relationship("FieldingStat", back_populates="game")
    appearances = relationship("GameAppearance", back_populates="game")
    fall_of_wickets = relationship("FallOfWicket", back_populates="game")
    partnerships = relationship("Partnership", back_populates="game")


class Fixture(Base):
    """BetterSelect: upcoming / scheduled matches — the foundation availability
    and team selection build on. BetterStats otherwise stores only completed
    games. Two sources:
      - 'playhq': synced from the partner API; id == the CA/PlayHQ game GUID,
        so a played fixture maps 1:1 to the eventual games.id row.
      - 'manual': admin-created (friendlies / pre-season) so lineups & social
        posts can be built without an official PlayHQ game; id is a uuid4.
    """
    __tablename__ = "fixtures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    source = Column(Text, nullable=False, server_default="manual")  # 'playhq' | 'manual'
    playhq_id = Column(Text, nullable=True)
    label = Column(Text, nullable=True)         # free-text title (friendlies / manual)
    round = Column(Text, nullable=True)
    played_on = Column(Date, nullable=True)     # match date (mirrors games.played_at)
    end_on = Column(Date, nullable=True)        # multi-day cricket
    start_time = Column(Text, nullable=True)    # "HH:MM" local, display only
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    home_away = Column(Text, nullable=True)     # HOME | AWAY | BYE (our perspective)
    opponent_name = Column(Text, nullable=True)
    venue = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="UPCOMING")  # UPCOMING|IN_PROGRESS|FINAL|CANCELLED|BYE
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")
    grade = relationship("Grade")
    team = relationship("Team")


class Team(Base):
    """BetterSelect: a first-class club team. BetterStats otherwise only has
    team *names* on games. Players are not hard-assigned to teams (club-wide
    model); a team groups fixtures and, later, scopes selection.
    """
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_team_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    short_name = Column(Text, nullable=True)
    sequence = Column(Integer, default=0, nullable=False, server_default="0")  # hierarchy rank (1 = top team)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    default_formation = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    source = Column(Text, nullable=False, server_default="manual")  # 'auto' | 'manual'
    playhq_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")
    grade = relationship("Grade")


class TeamMember(Base):
    """BetterSelect: manual squad membership — a player in a team's pool.

    Optional override on top of the club-wide model. History suggests who's
    played for a team recently; this records the admin's actual squad. M2M:
    a player can sit in several teams' squads.
    """
    __tablename__ = "team_members"

    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class FixtureLineup(Base):
    """BetterSelect Phase 3: a player picked for a fixture (the team sheet).

    Per-fixture: the same player can be in two fixtures' lineups on one weekend
    (the shared-player split). Any cross-fixture selection rule is enforced in
    the app layer, not here. batting_order is the slot (1..n), nullable until
    the side is ordered.
    """
    __tablename__ = "fixture_lineups"

    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    batting_order = Column(Integer, nullable=True)
    is_captain = Column(Boolean, default=False, nullable=False, server_default="false")
    is_wicket_keeper = Column(Boolean, default=False, nullable=False, server_default="false")
    selected_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class PlayerAvailability(Base):
    """BetterSelect: a player's availability for a playing DATE (admin-recorded).

    Keyed on (player, date), NOT per fixture: one answer covers every fixture
    that day. A two-day game contributes both its dates (played_on = week 1,
    end_on = week 2). Club-wide model — recorded_by/at track which admin set it
    (no player-facing input).
    """
    __tablename__ = "player_availability"
    __table_args__ = (
        UniqueConstraint("player_id", "avail_date", name="uq_player_availability_player_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    avail_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False, server_default="NO_RESPONSE")  # AVAILABLE|UNAVAILABLE|MAYBE|NO_RESPONSE
    note = Column(Text, nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class BattingInnings(Base):
    __tablename__ = "batting_innings"
    __table_args__ = (
        UniqueConstraint("game_id", "innings_number", "player_id", name="uq_batting_innings_game_inns_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    innings_number = Column(Integer, default=1)
    runs = Column(Integer)
    balls = Column(Integer)
    fours = Column(Integer)
    sixes = Column(Integer)
    strike_rate = Column(Numeric(6, 2))
    dismissal_type = Column(Text)
    not_out = Column(Boolean, default=False)
    batting_position = Column(Integer)
    did_not_bat = Column(Boolean, default=False)

    game = relationship("Game", back_populates="batting_innings")
    player = relationship("Player", back_populates="batting_innings")


class BowlingSpell(Base):
    __tablename__ = "bowling_spells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    innings_number = Column(Integer, default=1)
    overs = Column(Numeric(4, 1))
    maidens = Column(Integer)
    runs = Column(Integer)
    wickets = Column(Integer)
    wides = Column(Integer)
    no_balls = Column(Integer)
    economy = Column(Numeric(5, 2))

    game = relationship("Game", back_populates="bowling_spells")
    player = relationship("Player", back_populates="bowling_spells")


class FieldingStat(Base):
    __tablename__ = "fielding_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    catches = Column(Integer, default=0)
    catches_wk = Column(Integer, default=0)
    run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)

    game = relationship("Game", back_populates="fielding_stats")
    player = relationship("Player", back_populates="fielding_stats")


class BowlerWicket(Base):
    __tablename__ = "bowler_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    bowler_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    fielder_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter_name = Column(Text)
    batter_position = Column(Integer)
    # Denormalised from the dismissed batter's scorecard row. We don't store
    # opposition batting in batting_innings, so without these columns we have
    # no way to derive 'ducks/golden ducks inflicted'.
    batter_runs = Column(Integer, nullable=True)
    batter_balls = Column(Integer, nullable=True)
    dismissal_type = Column(Text, nullable=False)


class GameAppearance(Base):
    __tablename__ = "game_appearances"

    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    team_name = Column(Text, nullable=True)
    is_captain = Column(Boolean, default=False, nullable=False, server_default='false')
    is_wicket_keeper = Column(Boolean, default=False, nullable=False, server_default='false')

    game = relationship("Game", back_populates="appearances")
    player = relationship("Player", back_populates="appearances")


class FallOfWicket(Base):
    __tablename__ = "fall_of_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    score_at_fall = Column(Integer)
    overs_at_fall = Column(Numeric(5, 1))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)

    game = relationship("Game", back_populates="fall_of_wickets")
    player = relationship("Player")


class Partnership(Base):
    __tablename__ = "partnerships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    batter1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    runs = Column(Integer, default=0)
    balls = Column(Integer)
    batter1_runs = Column(Integer)
    batter2_runs = Column(Integer)
    is_club_innings = Column(Boolean, nullable=True)

    game = relationship("Game", back_populates="partnerships")
    batter1 = relationship("Player", foreign_keys=[batter1_id])
    batter2 = relationship("Player", foreign_keys=[batter2_id])


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    milestone_type = Column(Text, nullable=False)
    milestone_value = Column(Integer, nullable=False)
    achieved_at = Column(Date)
    detail = Column(Text)

    player = relationship("Player", back_populates="milestones")
    game = relationship("Game")


class PlayerSeasonGradeStats(Base):
    __tablename__ = "player_season_grade_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "grade_id", name="uq_player_season_grade"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id  = Column(UUID(as_uuid=True), ForeignKey("grades.id",  ondelete="CASCADE"), nullable=False)
    matches          = Column(Integer, default=0)
    batting_innings  = Column(Integer, default=0)
    runs             = Column(Integer, default=0)
    not_outs         = Column(Integer, default=0)
    high_score       = Column(Integer)
    bowling_innings  = Column(Integer, default=0)
    wickets          = Column(Integer, default=0)
    runs_conceded    = Column(Integer, default=0)
    catches          = Column(Integer, default=0)
    run_outs         = Column(Integer, default=0)
    stumpings        = Column(Integer, default=0)
    synced_at        = Column(TIMESTAMP(timezone=True))


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    __table_args__ = (UniqueConstraint("player_id", "season_id", name="uq_player_season"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    # Batting
    matches = Column(Integer, default=0)
    batting_innings = Column(Integer, default=0)
    runs = Column(Integer, default=0)
    not_outs = Column(Integer, default=0)
    balls_faced = Column(Integer, default=0)
    fifties = Column(Integer, default=0)
    hundreds = Column(Integer, default=0)
    ducks = Column(Integer, default=0)
    high_score = Column(Integer)
    is_hs_not_out = Column(Boolean, default=False)
    batting_average = Column(Numeric(8, 2))
    batting_strike_rate = Column(Numeric(8, 2))
    fours = Column(Integer, default=0)
    sixes = Column(Integer, default=0)
    batting_minutes = Column(Integer, default=0)
    # Bowling
    bowling_innings = Column(Integer, default=0)
    wickets = Column(Integer, default=0)
    overs = Column(Numeric(8, 1), default=0)
    bowling_balls = Column(Integer, default=0)
    runs_conceded = Column(Integer, default=0)
    maidens = Column(Integer, default=0)
    bowling_economy = Column(Numeric(6, 2))
    bowling_average = Column(Numeric(8, 2))
    bowling_strike_rate = Column(Numeric(6, 2))
    best_bowling_wickets = Column(Integer)
    best_bowling_figures = Column(Text)
    five_wicket_innings = Column(Integer, default=0)
    wides = Column(Integer, default=0)
    no_balls = Column(Integer, default=0)
    # Fielding
    catches = Column(Integer, default=0)
    catches_wk = Column(Integer, default=0)
    catches_non_wk = Column(Integer, default=0)
    run_outs = Column(Integer, default=0)
    assisted_run_outs = Column(Integer, default=0)
    unassisted_run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)
    source = Column(Text, nullable=False, server_default='api')

    player = relationship("Player", back_populates="season_stats")
    season = relationship("Season", back_populates="player_stats")


class ManualPartnershipRecord(Base):
    __tablename__ = "manual_partnership_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    batter1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter1_name = Column(Text, nullable=False)
    batter2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter2_name = Column(Text, nullable=False)
    grade_name = Column(Text, nullable=False)
    season_year = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    runs = Column(Integer, nullable=False)
    is_not_out = Column(Boolean, server_default="false", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    org = relationship("Organisation")
    batter1 = relationship("Player", foreign_keys=[batter1_id])
    batter2 = relationship("Player", foreign_keys=[batter2_id])


# ─── Manual entry tables (historical stat backfill) ──────────────────────────


class ManualGame(Base):
    __tablename__ = "manual_games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    played_at = Column(Date, nullable=True)
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    opposition = Column(Text, nullable=True)
    venue = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    winning_team = Column(Text, nullable=True)
    is_final = Column(Boolean, server_default="false", nullable=False)
    match_format = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    season = relationship("Season")
    grade = relationship("Grade")
    batting_innings = relationship("ManualBattingInnings", back_populates="manual_game", cascade="all, delete-orphan")
    bowling_spells = relationship("ManualBowlingSpell", back_populates="manual_game", cascade="all, delete-orphan")
    fielding_stats = relationship("ManualFieldingStat", back_populates="manual_game", cascade="all, delete-orphan")


class ManualBattingInnings(Base):
    __tablename__ = "manual_batting_innings"
    __table_args__ = (
        UniqueConstraint("manual_game_id", "innings_number", "player_id", name="uq_manual_batting_game_inns_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, server_default="1", nullable=False)
    batting_position = Column(Integer, nullable=True)
    runs = Column(Integer, server_default="0", nullable=False)
    balls = Column(Integer, nullable=True)
    fours = Column(Integer, server_default="0", nullable=False)
    sixes = Column(Integer, server_default="0", nullable=False)
    strike_rate = Column(Numeric(6, 2), nullable=True)
    dismissal_type = Column(Text, nullable=True)
    not_out = Column(Boolean, server_default="false", nullable=False)
    did_not_bat = Column(Boolean, server_default="false", nullable=False)

    manual_game = relationship("ManualGame", back_populates="batting_innings")
    player = relationship("Player")


class ManualBowlingSpell(Base):
    __tablename__ = "manual_bowling_spells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, server_default="1", nullable=False)
    overs = Column(Numeric(4, 1), nullable=True)
    maidens = Column(Integer, server_default="0", nullable=False)
    runs = Column(Integer, server_default="0", nullable=False)
    wickets = Column(Integer, server_default="0", nullable=False)
    wides = Column(Integer, server_default="0", nullable=False)
    no_balls = Column(Integer, server_default="0", nullable=False)
    economy = Column(Numeric(5, 2), nullable=True)

    manual_game = relationship("ManualGame", back_populates="bowling_spells")
    player = relationship("Player")


class ManualFieldingStat(Base):
    __tablename__ = "manual_fielding_stats"
    __table_args__ = (
        UniqueConstraint("manual_game_id", "player_id", name="uq_manual_fielding_game_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    catches = Column(Integer, server_default="0", nullable=False)
    catches_wk = Column(Integer, server_default="0", nullable=False)
    run_outs = Column(Integer, server_default="0", nullable=False)
    stumpings = Column(Integer, server_default="0", nullable=False)

    manual_game = relationship("ManualGame", back_populates="fielding_stats")
    player = relationship("Player")


class ManualSeasonAdjustment(Base):
    __tablename__ = "manual_season_adjustments"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "grade_id", name="uq_manual_season_adj_player_season_grade"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    games_played = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    batting_runs = Column(Integer, server_default="0", nullable=False)
    batting_not_outs = Column(Integer, server_default="0", nullable=False)
    batting_balls = Column(Integer, server_default="0", nullable=False)
    batting_fours = Column(Integer, server_default="0", nullable=False)
    batting_sixes = Column(Integer, server_default="0", nullable=False)
    batting_fifties = Column(Integer, server_default="0", nullable=False)
    batting_hundreds = Column(Integer, server_default="0", nullable=False)
    batting_ducks = Column(Integer, server_default="0", nullable=False)
    batting_high_score = Column(Integer, nullable=True)
    batting_high_score_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    bowling_overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    bowling_maidens = Column(Integer, server_default="0", nullable=False)
    bowling_runs = Column(Integer, server_default="0", nullable=False)
    bowling_wickets = Column(Integer, server_default="0", nullable=False)
    bowling_wides = Column(Integer, server_default="0", nullable=False)
    bowling_no_balls = Column(Integer, server_default="0", nullable=False)
    bowling_five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    bowling_best_wickets = Column(Integer, nullable=True)
    bowling_best_figures = Column(Text, nullable=True)
    fielding_catches = Column(Integer, server_default="0", nullable=False)
    fielding_catches_wk = Column(Integer, server_default="0", nullable=False)
    fielding_run_outs = Column(Integer, server_default="0", nullable=False)
    fielding_stumpings = Column(Integer, server_default="0", nullable=False)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    player = relationship("Player")
    season = relationship("Season")
    grade = relationship("Grade")


class ManualCareerAdjustment(Base):
    __tablename__ = "manual_career_adjustments"
    __table_args__ = (
        UniqueConstraint("player_id", "organisation_id", name="uq_manual_career_adj_player_org"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    games_played = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    batting_runs = Column(Integer, server_default="0", nullable=False)
    batting_not_outs = Column(Integer, server_default="0", nullable=False)
    batting_balls = Column(Integer, server_default="0", nullable=False)
    batting_fours = Column(Integer, server_default="0", nullable=False)
    batting_sixes = Column(Integer, server_default="0", nullable=False)
    batting_fifties = Column(Integer, server_default="0", nullable=False)
    batting_hundreds = Column(Integer, server_default="0", nullable=False)
    batting_ducks = Column(Integer, server_default="0", nullable=False)
    batting_high_score = Column(Integer, nullable=True)
    batting_high_score_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    bowling_overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    bowling_maidens = Column(Integer, server_default="0", nullable=False)
    bowling_runs = Column(Integer, server_default="0", nullable=False)
    bowling_wickets = Column(Integer, server_default="0", nullable=False)
    bowling_five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    bowling_best_wickets = Column(Integer, nullable=True)
    bowling_best_figures = Column(Text, nullable=True)
    fielding_catches = Column(Integer, server_default="0", nullable=False)
    fielding_catches_wk = Column(Integer, server_default="0", nullable=False)
    fielding_run_outs = Column(Integer, server_default="0", nullable=False)
    fielding_stumpings = Column(Integer, server_default="0", nullable=False)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    player = relationship("Player")


class ManualEditLog(Base):
    __tablename__ = "manual_edit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(Text, nullable=False)
    target_table = Column(Text, nullable=False)
    target_id = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    before_json = Column(JSONB, nullable=True)
    after_json = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    undone_at = Column(TIMESTAMP(timezone=True), nullable=True)
    undone_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PlayerSyncRequest(Base):
    __tablename__ = "player_sync_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, server_default="pending", nullable=False)
    requester_note = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    player = relationship("Player")
    org = relationship("Organisation")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    kind = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="running")
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)


class SavedReport(Base):
    __tablename__ = "saved_reports"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_saved_reports_org_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    slug = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    query_json = Column(JSONB, nullable=False)
    visibility = Column(Text, nullable=False, server_default="club")
    view_count = Column(Integer, nullable=False, server_default="0")
    # Club-visibility reports start as 'pending' and only show on the public
    # list after an admin approves them. Private and admin-authored reports
    # are auto-approved on save. Values: 'pending' | 'approved' | 'rejected'.
    status = Column(Text, nullable=False, server_default="approved")
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class PhqIdSuggestion(Base):
    __tablename__ = "phq_id_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    phq_player_id = Column(Text, nullable=False)
    phq_first_name = Column(Text, nullable=True)
    phq_last_name = Column(Text, nullable=True)
    confidence = Column(Text, nullable=False)  # 'auto' | 'high' | 'low'
    game_count = Column(Integer, server_default="1")
    status = Column(Text, server_default="pending", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    org = relationship("Organisation")
    player = relationship("Player", foreign_keys=[player_id])


class Family(Base):
    __tablename__ = "families"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_families_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    members = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (
        UniqueConstraint("family_id", "player_id", name="uq_family_member_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("families.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    relationship_label = Column("relationship", Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    family = relationship("Family", back_populates="members")
    player = relationship("Player")


# ───────────────────────────────────────────────────────────────────────────
# Fee Tracking (migration 041)
#
# A self-contained membership/match-fee ledger that lives alongside the stats
# data. Every fee-paying person is a `fee_members` row; the financial state
# for a given season is a `fee_member_seasons` row pointing at one
# `fee_schedule` tier. Match-day fees accrue as `fee_match_days` rows, mostly
# auto-derived from GameAppearance each sync (admins can override). Payments
# are reconciled by hand against bank statements (`fee_payments`).
#
# The money is driven entirely by the member's tier (fee_schedule), never the
# format: match fee = days_played × tier.match_day_rate. Format only affects
# how many days a game contributes (two-day = 2) and which report bucket it
# lands in.
# ───────────────────────────────────────────────────────────────────────────

# Payment-type values on a fee_schedule tier.
FEE_PAYMENT_TYPES = ("standard", "upfront", "complimentary", "left_club")
# fee_match_days.fee_format / Grade.fee_format values.
FEE_FORMATS = ("two_day", "one_day", "t20", "women", "exclude")


class FeeSchedule(Base):
    """A membership tier for one season — the spreadsheet's PARMS rate card.

    `membership_amount` is the one-off membership fee; `match_day_rate` is the
    per-day match fee (0 for Upfront tiers, who prepay via membership).
    """
    __tablename__ = "fee_schedule"
    __table_args__ = (
        UniqueConstraint("season_id", "name", name="uq_fee_schedule_season_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    payment_type = Column(Text, nullable=False, server_default="standard")
    membership_amount = Column(Numeric(10, 2), nullable=False, server_default="0")
    match_day_rate = Column(Numeric(10, 2), nullable=False, server_default="0")
    display_order = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FeeMember(Base):
    """A fee-paying person. Linked to a stats Player where one exists; manual
    members (life members, sponsors, ICL who don't play) have player_id NULL.

    `current_tier` carries forward season-to-season: it seeds the tier when a
    new member-season is opened, and is updated whenever an admin sets a tier.
    """
    __tablename__ = "fee_members"
    __table_args__ = (
        UniqueConstraint("organisation_id", "player_id", name="uq_fee_member_org_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    mobile = Column(Text, nullable=True)
    # Name of the fee_schedule tier this member currently sits in (carry-forward
    # default). Not a FK — schedules are per-season, this is a cross-season hint.
    current_tier = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player")
    seasons = relationship("FeeMemberSeason", back_populates="member", cascade="all, delete-orphan")


class FeeMemberSeason(Base):
    """A member's financial state for one season. fee_schedule_id NULL means
    'needs a tier assigned' — the review queue surfaced on the Members page."""
    __tablename__ = "fee_member_seasons"
    __table_args__ = (
        UniqueConstraint("member_id", "season_id", name="uq_fee_member_season"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    fee_schedule_id = Column(UUID(as_uuid=True), ForeignKey("fee_schedule.id", ondelete="SET NULL"), nullable=True)
    is_new_registration = Column(Boolean, nullable=False, server_default="false")
    membership_payment_method = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member = relationship("FeeMember", back_populates="seasons")
    schedule = relationship("FeeSchedule")
    match_days = relationship("FeeMatchDay", back_populates="member_season", cascade="all, delete-orphan")
    payments = relationship("FeePayment", back_populates="member_season", cascade="all, delete-orphan")


class FeeMatchDay(Base):
    """One game's contribution to a member's match-day count. Auto-derived from
    GameAppearance during sync; `auto_derived=False` once an admin overrides it
    (e.g. drops a two-day game from 2 days to 1), which makes sync leave it
    alone thereafter.

    `paid_payment_id` links to the FeePayment that settled this match day. The
    'Mark Paid' button creates a payment and links it here; deleting the
    payment from the Payments page nulls this out (FK ON DELETE SET NULL).
    A single bulk payment can settle multiple match-day rows, so multiple
    rows may share the same `paid_payment_id`."""
    __tablename__ = "fee_match_days"
    __table_args__ = (
        UniqueConstraint("member_season_id", "game_id", name="uq_fee_match_day_member_game"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_season_id = Column(UUID(as_uuid=True), ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=True)
    played_at = Column(Date, nullable=True)
    fee_format = Column(Text, nullable=True)
    days_played = Column(Numeric(3, 1), nullable=False, server_default="1")
    auto_derived = Column(Boolean, nullable=False, server_default="true")
    paid_payment_id = Column(UUID(as_uuid=True), ForeignKey("fee_payments.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member_season = relationship("FeeMemberSeason", back_populates="match_days")
    game = relationship("Game")
    paid_payment = relationship("FeePayment", foreign_keys=[paid_payment_id])


class FeePayment(Base):
    """A payment reconciled against a bank statement. Defined now so Phase 2
    (payments + financial status) is purely additive; no endpoints write here
    yet."""
    __tablename__ = "fee_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_season_id = Column(UUID(as_uuid=True), ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False, server_default="0")
    paid_at = Column(Date, nullable=True)
    kind = Column(Text, nullable=False, server_default="membership")  # 'membership' | 'match_day'
    method = Column(Text, nullable=True)
    bank_ref = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member_season = relationship("FeeMemberSeason", back_populates="payments")
