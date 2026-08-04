"""Player name aliases — a former/alternate name that still resolves to the
right player.

A live feed (a Play.Cricket team list, a Grassroots scorecard) identifies a
participant by GUID first, but falls back to matching by NAME when the GUID
doesn't match anything we hold (CA is known to issue a different GUID for the
same real person across a migration boundary — see the dual-GUID notes in
CLAUDE.md). That name fallback breaks the moment a club renames a player in
BetterCricket after they've already appeared under their old name: the old
name no longer textually resembles anything on the player's record at all
(not even a surname-and-initial match), so a genuinely-registered player reads
as an unknown fill-in.

``player_name_aliases`` closes that gap with an explicit, org-scoped
``alias_key -> player_id`` map — no fuzzy matching needed, since it's either
an exact recorded alias or it isn't. Two ways a row gets created:
  * automatically, the moment a rename happens (``seed_alias_on_rename``,
    ``source='rename'``) — so this never recurs for a FUTURE rename with no
    admin action needed;
  * by hand, via the admin "Also known as" panel (``source='manual'``) — the
    only way to fix a rename that happened before this table existed.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_WS = re.compile(r"\s+")


def normalise_name_key(name) -> str:
    """Lowercased, comma-stripped, whitespace-collapsed, word-order-independent
    key — "Wijesinghe, Shaylyn" and "Shaylyn Wijesinghe" both key to
    "shaylyn wijesinghe", so it doesn't matter whether the alias was recorded
    in our "Last, First" convention or a live feed's "First Last" one.
    """
    n = str(name or "").replace(",", " ").strip().lower()
    n = _WS.sub(" ", n)
    tokens = sorted(t for t in n.split() if t)
    return " ".join(tokens)


async def org_alias_map(db: AsyncSession, org_id) -> dict[str, str]:
    """Every alias in the org, keyed by `normalise_name_key` -> player id
    (string). Cheap — this table is small per club."""
    res = await db.execute(
        text("SELECT alias_key, player_id FROM player_name_aliases WHERE organisation_id = :org"),
        {"org": org_id},
    )
    return {key: str(pid) for key, pid in res.fetchall()}


async def seed_alias_on_rename(db: AsyncSession, org_id, player_id, old_name: Optional[str]) -> None:
    """Best-effort: record `old_name` as an alias for `player_id`.

    Never raises — a rename must always succeed even if this bookkeeping
    fails — and never overwrites an alias already claimed by a different
    player (``ON CONFLICT DO NOTHING``): a genuine collision just means this
    particular old name isn't captured, which is a rare, low-stakes edge case,
    not something worth blocking the rename itself over.

    The INSERT runs inside its own SAVEPOINT: catching the Python exception
    alone isn't enough to make this safe for a caller who does more work in
    the same transaction afterward (a rename is very often one step inside a
    bigger merge/rename operation) — once one statement in a Postgres
    transaction fails, every later statement in that same transaction fails
    too with "current transaction is aborted" until something rolls back, so
    a bare try/except here would silently poison the caller's transaction
    the moment this INSERT can't run (e.g. player_name_aliases missing from
    a database that predates it — see the AFL merge-players 500 this was
    written to fix). The SAVEPOINT contains that failure to just this insert.
    """
    key = normalise_name_key(old_name)
    if not key:
        return
    try:
        async with db.begin_nested():
            # id supplied here, not left to a database default: the ORM model
            # (PlayerNameAlias) only has a Python-side default=uuid.uuid4,
            # which a raw SQL INSERT bypassing the ORM never sees — and
            # whichever code path creates this table first (Base.metadata.
            # create_all vs. the raw-SQL migration mirror) decides whether a
            # server-side DEFAULT ends up on the column at all. Generating it
            # here makes this INSERT correct regardless of either.
            await db.execute(
                text(
                    "INSERT INTO player_name_aliases (id, organisation_id, player_id, alias_name, alias_key, source) "
                    "VALUES (:id, :org, :pid, :name, :key, 'rename') "
                    "ON CONFLICT (organisation_id, alias_key) DO NOTHING"
                ),
                {"id": str(uuid.uuid4()), "org": org_id, "pid": player_id, "name": old_name, "key": key},
            )
    except Exception:
        pass
