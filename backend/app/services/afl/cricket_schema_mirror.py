"""Give the football database every table and column the shared modules expect.

BetterAdmin (accounts, emails, stock, directory, roster, committee, events,
facilities, diary) and BetterSocials are one implementation serving both sports.
Their routers are sport-agnostic, but a good part of their schema was never put
on the ORM: cricket's ``main.py`` lifespan creates ~190 tables and adds ~300
columns in raw SQL, and ``Base.metadata.create_all`` cannot see any of it. The
football database is built by ``create_all``, so without this a shared router
mounted here fails the first time it touches ``roster_areas`` or
``fee_members.member_category``.

The alternative was copying the statements BetterAdmin needs into
``afl_main.py`` by hand, which is how the two drift: the next cricket release
adds a column, the football copy does not, and a football screen 500s. So this
READS cricket's lifespan instead of copying it. ``main.py`` is parsed (never
imported, which would boot the cricket app) and every literal ``text("...")``
statement in its lifespan that is purely additive is replayed here, in file
order, each in its own savepoint:

* ``CREATE TABLE IF NOT EXISTS``
* ``CREATE [UNIQUE] INDEX IF NOT EXISTS``
* ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` (every clause)
* ``ALTER TABLE ... ALTER COLUMN ... SET DEFAULT`` / ``DROP NOT NULL``

Nothing that moves or removes data is ever replayed: no UPDATE, INSERT,
DELETE, DROP, constraint change, view or ``DO`` block. A cricket backfill is
about cricket data; on a football database it would at best do nothing and at
worst act on a football row it was never written for.

This is the same posture the football silo already takes with the ORM: a
cricket-only table exists here, empty, so any shared code path finds its
table. The data silo comes from the separate database, not a trimmed schema.

The DDL modules cricket runs by import rather than by literal (the committee
plan tree, role programs, comms segments, the asset register, notifications)
are listed in ``SHARED_DDL_MODULES`` and run whole: they are the one copy of
that schema, idempotent by design, and every backfill in them is a no-op on a
football club's empty tables.
"""
from __future__ import annotations

import ast
import importlib
import logging
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

logger = logging.getLogger(__name__)

MAIN_PY = Path(__file__).resolve().parents[2] / "main.py"

_CREATE_TABLE = re.compile(r"^CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", re.I)
_CREATE_INDEX = re.compile(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b", re.I)
_ALTER = re.compile(r"^ALTER\s+TABLE\s+(IF\s+EXISTS\s+)?[\w\".]+\s+(.*)$", re.I | re.S)
_ADD_COLUMN = re.compile(r"^ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", re.I)
_RELAX_COLUMN = re.compile(r"^ALTER\s+COLUMN\s+\w+\s+(SET\s+DEFAULT\b|DROP\s+NOT\s+NULL\s*$)", re.I)

# (module, attribute) pairs cricket's lifespan runs by import. Each attribute is
# a list of statements or a single SQL string.
SHARED_DDL_MODULES = (
    ("app.services.role_program_ddl", "STATEMENTS"),
    ("app.services.comms_segment_ddl", "STATEMENTS"),
    ("app.services.asset_register_ddl", "ASSET_REGISTER_SQL"),
    ("app.services.notification_ddl", "STATEMENTS"),
    ("app.services.committee_sync_ddl", "STATEMENTS"),
    ("app.services.pillar_plan_ddl", "PILLAR_PLAN_SPLIT_SQL"),
    ("app.services.pillar_plan_ddl", "PILLAR_PLAN_CLAIM_SQL"),
    ("app.services.plan_tree_ddl", "PLAN_TREE_SQL"),
    ("app.services.invoice_billing_ddl", "STATEMENTS"),
    # BetterSocials is mounted on the football app too, so its saved templates
    # need their table there.
    ("app.services.social_template_ddl", "STATEMENTS"),
)


def _split_top_level(clauses: str) -> list[str]:
    """Split an ALTER TABLE's clause list on the commas between clauses, not
    the ones inside a type or a default (``NUMERIC(4,2)``, ``'{}'``)."""
    out, depth, quote, cur = [], 0, False, []
    for ch in clauses:
        if ch == "'":
            quote = not quote
        elif not quote and ch == "(":
            depth += 1
        elif not quote and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def is_additive(sql: str) -> bool:
    """True when replaying ``sql`` can only add schema, never change data."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:  # several statements in one literal: not ours to judge
        return False
    if _CREATE_TABLE.match(s) or _CREATE_INDEX.match(s):
        return True
    m = _ALTER.match(s)
    if not m:
        return False
    clauses = _split_top_level(m.group(2))
    return bool(clauses) and all(_ADD_COLUMN.match(c) or _RELAX_COLUMN.match(c) for c in clauses)


@lru_cache(maxsize=1)
def harvested_statements() -> tuple[str, ...]:
    """Every additive literal statement in cricket's lifespan, in file order."""
    tree = ast.parse(MAIN_PY.read_text())
    life = next(n for n in ast.walk(tree)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "lifespan")
    found = []
    for node in ast.walk(life):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "text"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            found.append((node.lineno, node.col_offset, node.args[0].value.strip()))
    found.sort()
    return tuple(sql for _, _, sql in found if is_additive(sql))


def shared_module_statements() -> list[str]:
    out = []
    for mod_name, attr in SHARED_DDL_MODULES:
        value = getattr(importlib.import_module(mod_name), attr)
        out.extend([value] if isinstance(value, str) else list(value))
    return out


async def apply(conn) -> dict:
    """Replay the harvest, then the shared DDL modules. Each statement runs in
    its own savepoint, so one that cannot apply here (an index on a column only
    a later cricket statement adds, say) is skipped without aborting the boot.
    Returns counts, for the boot log."""
    applied = skipped = 0
    for sql in [*harvested_statements(), *shared_module_statements()]:
        try:
            async with conn.begin_nested():
                await conn.execute(text(sql))
            applied += 1
        except Exception as exc:  # noqa: BLE001 — one statement must not stop the boot
            skipped += 1
            logger.debug("cricket_schema_mirror: skipped %s… (%s)", sql[:80].replace("\n", " "), exc)
    # The harvest can reference a table a later statement creates, so a second
    # pass picks up anything whose dependency landed after it.
    if skipped:
        retried = 0
        for sql in harvested_statements():
            try:
                async with conn.begin_nested():
                    await conn.execute(text(sql))
                retried += 1
            except Exception:  # noqa: BLE001
                pass
        logger.info("cricket_schema_mirror: second pass re-ran %d statements", retried)
    return {"applied": applied, "skipped": skipped}
