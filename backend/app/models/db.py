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
    # claimed / user_id retained as columns but no longer used in business logic
    claimed = Column(Boolean, default=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)

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
