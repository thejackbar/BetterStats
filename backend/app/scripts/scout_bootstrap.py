"""Bootstrap a BetterScout silo: create the first Scout Org and its first
user. Run inside the bs-scout-backend container (or locally against
app.scout_main's database):

    python -m app.scripts.scout_bootstrap <org_name> <username> <password>

e.g.  python -m app.scripts.scout_bootstrap "Jack's Scouting" jack 'Better2026!'

Idempotent: an existing org (matched by name) or user (matched by username)
is reused as-is — a rerun never overwrites an existing password, same rule
afl_bootstrap.py follows.
"""
import asyncio
import re
import sys
import uuid

from sqlalchemy import select

from app.models.db import async_session_maker
from app.models.scout import ScoutOrg, ScoutUser
from app.services import scout_auth


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "scout-org"


async def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    org_name, username, password = sys.argv[1:4]
    username = username.strip().lower()

    async with async_session_maker() as session:
        # The schema is created by app.scout_main's lifespan on first boot,
        # not here — running this against a never-started backend would
        # otherwise fail with a wall of raw SQL that reads like a code bug
        # rather than an ordering mistake (same guard afl_bootstrap.py uses).
        try:
            await session.execute(select(ScoutUser).limit(1))
        except Exception:
            print(
                "The BetterScout database has no schema yet — start "
                "app.scout_main once so it can create the tables, then "
                "re-run this script."
            )
            sys.exit(1)

        res = await session.execute(select(ScoutOrg).where(ScoutOrg.name == org_name))
        org = res.scalar_one_or_none()
        if org is None:
            org = ScoutOrg(id=uuid.uuid4(), name=org_name, slug=_slugify(org_name))
            session.add(org)
            await session.flush()
            print(f"scout org created: {org.name} ({org.id}) slug={org.slug}")
        else:
            print(f"scout org exists: {org.name} ({org.id})")

        res = await session.execute(select(ScoutUser).where(ScoutUser.username == username))
        user = res.scalar_one_or_none()
        if user is None:
            user = ScoutUser(
                id=uuid.uuid4(),
                scout_org_id=org.id,
                username=username,
                display_name=username,
                role="owner",
                password_hash=scout_auth.hash_password(password),
            )
            session.add(user)
            print(f"scout user created: {username}")
        else:
            print(f"scout user exists: {username} (password unchanged)")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
