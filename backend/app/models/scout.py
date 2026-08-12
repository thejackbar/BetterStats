"""BetterScout — tenant models.

A Scout Org is a brand-new top-level tenant type (a recruiting agency like
CricExchange, or a premier club scouting its own feeder-club juniors), NOT an
Organisation row: it has no relationship to any club, no PlayHQ id of its
own, and its users never touch routers/auth.py's User/ClubMembership tables
or the bs_session cookie those use. See services/scout_auth.py for the
completely separate login/session mechanism these tables back.

Deliberately NOT a separate database/silo (unlike AFL) — BetterScout lives in
the same app process and the same database as the rest of BetterCricket, so
a normal deploy (which already runs `alembic upgrade head` on boot) picks it
up with no extra server setup. Registered on the same `Base` as every other
model (imported from app.models.db) purely so the ORM knows about these two
tables; the real DDL lives in alembic/versions/236_scout_org_tenant.py (+ its
idempotent mirror in main.py's lifespan), same as every other table in this
app. Isolation from club/player data is enforced by having zero foreign keys
in or out of these two tables and a completely separate login (see
services/scout_auth.py), not by a separate database.
"""
import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.db import Base


class ScoutOrg(Base):
    """A scouting tenant. Deliberately flat/simple for the foundational phase
    — no billing tier or module-entitlement columns yet (those arrive with
    the pricing-tier phase); is_active is the one on/off switch a login
    checks."""
    __tablename__ = "scout_orgs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    # Reserved for a future org-scoped URL/share-link namespace — not read by
    # anything in the foundational login flow, which resolves purely off
    # username (see scout_auth.read_session).
    slug = Column(Text, unique=True, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    # Same theme shape as Organisation (primary_color/accent_color/theme_mode)
    # so the shared ThemeProvider needs no new branching for this silo — just
    # a different feed function than the club-scoped one.
    primary_color = Column(Text, nullable=True, default="#16c784")
    accent_color = Column(Text, nullable=True, default="#243352")
    theme_mode = Column(Text, nullable=True, default="dark")
    logo_url = Column(Text, nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ScoutUser(Base):
    """A Scout Org's login. Flat FK to ScoutOrg — no separate membership join
    table (unlike User/ClubMembership), since phase 1 has no per-org role
    model beyond a single advisory `role` string with no enforcement. A real
    multi-user permission model arrives with the watchlist-collaboration
    phase, not here."""
    __tablename__ = "scout_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scout_org_id = Column(UUID(as_uuid=True), ForeignKey("scout_orgs.id", ondelete="CASCADE"), nullable=False)

    # Globally unique, not unique-per-org — there's no org-slug login step in
    # this phase, so /auth/login resolves a user by username alone (mirrors
    # how routers/auth.py resolves User.username with no club context either).
    username = Column(Text, unique=True, nullable=False)
    email = Column(Text, nullable=True)
    password_hash = Column(Text, nullable=True)
    display_name = Column(Text, nullable=True)
    role = Column(Text, nullable=False, default="owner", server_default="owner")

    last_login_at = Column(TIMESTAMP(timezone=True), nullable=True)
    failed_login_count = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(TIMESTAMP(timezone=True), nullable=True)

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
