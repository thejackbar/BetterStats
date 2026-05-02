from sqlalchemy import (
    Column, String, Boolean, Integer, Numeric, Date, Text, ForeignKey,
    TIMESTAMP, JSON
)
from sqlalchemy.dialects.postgresql import UUID
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
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    players = relationship("Player", back_populates="user")


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    short_name = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    seasons = relationship("Season", back_populates="organisation")
    players = relationship("Player", back_populates="organisation")


class Season(Base):
    __tablename__ = "seasons"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    name = Column(Text, nullable=False)
    year = Column(Integer)
    synced_at = Column(TIMESTAMP(timezone=True))

    organisation = relationship("Organisation", back_populates="seasons")
    grades = relationship("Grade", back_populates="season")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(UUID(as_uuid=True), primary_key=True)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"))
    name = Column(Text, nullable=False)

    season = relationship("Season", back_populates="grades")
    games = relationship("Game", back_populates="grade")


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    claimed = Column(Boolean, default=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    organisation = relationship("Organisation", back_populates="players")
    user = relationship("User", back_populates="players")
    batting_innings = relationship("BattingInnings", back_populates="player")
    bowling_spells = relationship("BowlingSpell", back_populates="player")
    fielding_stats = relationship("FieldingStat", back_populates="player")


class Game(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"))
    played_at = Column(Date)
    home_team = Column(Text)
    away_team = Column(Text)
    result = Column(Text)
    winning_team = Column(Text)
    raw_payload = Column(JSON)

    grade = relationship("Grade", back_populates="games")
    batting_innings = relationship("BattingInnings", back_populates="game")
    bowling_spells = relationship("BowlingSpell", back_populates="game")
    fielding_stats = relationship("FieldingStat", back_populates="game")


class BattingInnings(Base):
    __tablename__ = "batting_innings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    runs = Column(Integer)
    balls = Column(Integer)
    fours = Column(Integer)
    sixes = Column(Integer)
    strike_rate = Column(Numeric(6, 2))
    dismissal_type = Column(Text)
    not_out = Column(Boolean, default=False)
    batting_position = Column(Integer)

    game = relationship("Game", back_populates="batting_innings")
    player = relationship("Player", back_populates="batting_innings")


class BowlingSpell(Base):
    __tablename__ = "bowling_spells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
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
    run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)

    game = relationship("Game", back_populates="fielding_stats")
    player = relationship("Player", back_populates="fielding_stats")
