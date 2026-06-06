"""Lazy async engine for the *external* KlubPro Postgres.

The KlubPro → BetterStats migration tooling reads staged player / sponsor data
(and writes operator decisions) in the KlubPro database's ``klubpro_migration``
schema. That database is entirely separate from BetterStats, so it gets its own
engine — created lazily on first use so the app boots normally when migration is
not configured (`KLUBPRO_DATABASE_URL` empty), which is every deploy except an
active onboarding session.

Nothing here is mapped with the ORM: KlubPro is an external system we only touch
through schema-qualified raw SQL, so it never participates in our migrations.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings

_engine = None
_session_maker: Optional[async_sessionmaker] = None


def klubpro_configured() -> bool:
    """True when an operator has pointed us at a KlubPro database."""
    return bool((settings.klubpro_database_url or "").strip())


def _maker() -> async_sessionmaker:
    global _engine, _session_maker
    if _session_maker is None:
        if not klubpro_configured():
            raise RuntimeError(
                "KlubPro migration database is not configured. Set "
                "KLUBPRO_DATABASE_URL (e.g. postgresql+asyncpg://klubpro_admin:"
                "<pw>@klubpro-postgres:5432/klubpro) and restart the backend."
            )
        # pool_pre_ping: the KlubPro box may idle between onboarding sessions;
        # without it a stale pooled connection surfaces as a hard 500.
        _engine = create_async_engine(
            settings.klubpro_database_url, echo=False, pool_pre_ping=True
        )
        _session_maker = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_maker


async def get_klubpro_db():
    """FastAPI dependency yielding a session on the KlubPro database."""
    async with _maker()() as session:
        yield session
