"""Bootstrap an AFL silo: register a club from PlayHQ and create the first
super-admin user. Run inside the bs-afl-backend container:

    python -m app.scripts.afl_bootstrap <playhq_org_id> <username> <password> [--sync]

e.g.  python -m app.scripts.afl_bootstrap d14445c4 admin 'changeme' --sync

Idempotent: an existing org/user is reused, membership created if missing.
"""
import asyncio
import sys
import uuid

import bcrypt
from sqlalchemy import select

from app.models.db import ClubMembership, User, async_session_maker


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_sync = "--sync" in sys.argv
    if len(args) != 3:
        print(__doc__)
        sys.exit(1)
    playhq_org_id, username, password = args

    from app.services.afl import sync as afl_sync

    async with async_session_maker() as session:
        # The schema is created by app.afl_main's lifespan on first boot, not
        # here. Running this against a never-started backend would otherwise
        # fail with a wall of raw SQL ('relation "organisations" does not
        # exist') that reads like a code bug rather than an ordering mistake.
        try:
            await session.execute(select(User).limit(1))
        except Exception:
            print(
                "The AFL database has no schema yet — start the backend once "
                "so it can create the tables, then re-run this:\n"
                "  docker compose up -d bs-afl-database bs-afl-backend\n"
                "  docker compose logs --tail=5 bs-afl-backend"
                "   # wait for 'Application startup complete.'"
            )
            sys.exit(1)

        org = await afl_sync.register_organisation(session, playhq_org_id)
        print(f"organisation: {org.name} ({org.id}) slug={org.slug}")

        res = await session.execute(select(User).where(User.username == username.lower()))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                username=username.lower(),
                display_name=username,
                password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            )
            session.add(user)
            await session.flush()
            print(f"user created: {username}")
        else:
            print(f"user exists: {username}")

        res = await session.execute(select(ClubMembership).where(ClubMembership.user_id == user.id))
        membership = res.scalar_one_or_none()
        if membership is None:
            session.add(ClubMembership(club_id=org.id, user_id=user.id, role="super_admin"))
            print("membership created: super_admin")
        await session.commit()

    if do_sync:
        print("starting full sync (this can take a while for a multi-season club)…")
        stats = await afl_sync.sync_organisation(org.id, full=True)
        print("sync done:", {k: v for k, v in stats.items() if not k.startswith("progress_")})


if __name__ == "__main__":
    asyncio.run(main())
