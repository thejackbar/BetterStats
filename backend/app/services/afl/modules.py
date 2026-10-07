"""The add-on modules a football club can hold, and the default grant.

Football has no billing or module marketplace, so every football club holds
every football module unless a super admin switches one off for it. The switch
is ``organisations.module_overrides`` (the one entitlement source, see
``app/auth/modules.py``), the same list cricket uses.

BetterAdmin is one switch covering its four entitlement keys, exactly as
cricket sells it as one module.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.modules import (
    MODULE_COMMS, MODULE_CRM, MODULE_FEES, MODULE_MERCH, MODULE_SELECT, MODULE_SOCIALS,
)

AFL_MODULE_TOGGLES = {
    "socials": (MODULE_SOCIALS,),
    "select": (MODULE_SELECT,),
    "admin": (MODULE_FEES, MODULE_COMMS, MODULE_MERCH, MODULE_CRM),
}

# Every entitlement key behind those switches, in a stable order.
AFL_DEFAULT_MODULES = tuple(sorted({k for keys in AFL_MODULE_TOGGLES.values() for k in keys}))

# Stored in platform_settings.settings once the backfill below has run, so a
# super admin who later switches a module off for a club is not reverted on the
# next boot (the lifespan re-runs every statement on every boot).
GRANT_MARKER = "afl_default_modules_granted"


def with_default_modules(held) -> list[str]:
    """``held`` plus every football module, as a fresh sorted list."""
    return sorted(set(held or ()) | set(AFL_DEFAULT_MODULES))


async def grant_default_modules_once(conn: AsyncConnection) -> int:
    """Give every existing football club every football module, one time.

    Additive: it only ever adds keys to ``module_overrides`` and never removes
    one, so a module a club already holds, or a key outside this set, is left
    alone. Returns the number of clubs changed (0 once the marker is set).
    """
    done = (await conn.execute(text(
        "SELECT settings ->> :k FROM platform_settings WHERE id = 1"), {"k": GRANT_MARKER})).scalar()
    if done:
        return 0
    res = await conn.execute(text("""
        UPDATE organisations o SET module_overrides = (
            SELECT COALESCE(jsonb_agg(k ORDER BY k), '[]'::jsonb) FROM (
                SELECT jsonb_array_elements_text(COALESCE(o.module_overrides, '[]'::jsonb)) AS k
                UNION
                SELECT unnest(CAST(:keys AS text[]))
            ) s)
        WHERE NOT (COALESCE(o.module_overrides, '[]'::jsonb) @> CAST(:keys_json AS jsonb))
    """), {"keys": list(AFL_DEFAULT_MODULES), "keys_json": json.dumps(list(AFL_DEFAULT_MODULES))})
    await conn.execute(text(
        "UPDATE platform_settings SET settings = jsonb_set(settings, CAST(:path AS text[]), 'true'::jsonb) "
        "WHERE id = 1"), {"path": [GRANT_MARKER]})
    return res.rowcount or 0

