"""Pull the `v_effective_*` view definitions straight out of the migrations.

Retyping a view into a harness is how a suite ends up proving something about
SQL the app doesn't run. Each view is taken from the LAST migration that
defines it, applied in migration order.
"""
from __future__ import annotations

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"

# The migrations that define a `v_effective_*` view, DISCOVERED rather than
# listed. A hand-kept list goes stale the moment somebody adds a migration that
# redefines one, and the failure is silent in the worst way: every suite keeps
# passing while testing SQL the app no longer runs. Migration 291 was exactly
# that - it moved `caught_behind` onto the manual branch, the list did not know,
# and the harness went on serving the hardcoded NULL.
#
# Ordered by the numeric prefix, so a later file supersedes the views it
# redefines. A file whose only CREATE sits in downgrade() carries the PRIOR
# definition and is dropped by `view_statements` below, not here.
_CREATE = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(v_effective_\w+)\s+AS", re.I)


def _upgrade_src(src: str) -> str:
    """Only the upgrade() body — a downgrade holds the PRIOR definition."""
    i = src.find("def upgrade()")
    j = src.find("def downgrade()")
    if i == -1:
        return src
    return src[i:j] if j > i else src[i:]


def _view_migrations() -> list[str]:
    """Every migration filename mentioning a `v_effective_*` CREATE, in order."""
    hits = []
    for f in VERSIONS.glob("*.py"):
        prefix = f.name.split("_", 1)[0]
        if not prefix.isdigit():
            continue
        if _CREATE.search(f.read_text()):
            hits.append((int(prefix), f.name))
    return [n for _, n in sorted(hits)]


def view_statements() -> list[tuple[str, str]]:
    """[(view_name, create_sql)] — the LAST definition of each view, in order.

    Only the newest definition is applied: an earlier one is superseded by
    construction, and applying it first would test SQL the app never runs.
    """
    out: list[tuple[str, str]] = []
    for name in _view_migrations():
        src = (VERSIONS / name).read_text()
        body = _upgrade_src(src)
        # Every triple-quoted string in the upgrade path, whether inlined in an
        # op.execute(...) or hoisted into a module-level constant it references.
        blocks = re.findall(r'"""(.*?)"""', src, re.S)
        constants = {
            cm.group(2): cm.group(1)
            for cm in re.finditer(r'^([A-Z_0-9]+)\s*=\s*"""(.*?)"""', src, re.S | re.M)
        }
        # Names the upgrade path reaches, following one constant to another:
        # a migration that collects its DDL into a STATEMENTS list and loops
        # over it never mentions the view constant in upgrade() at all. That
        # is the shape migration 291 uses, and without this the harness keeps
        # the SUPERSEDED definition and every check about the new one fails
        # while the code is correct.
        reachable = set(re.findall(r"\b([A-Z_0-9]{2,})\b", body))
        assigns = dict(re.findall(r"^([A-Z_0-9]+)\s*=\s*(.+?)$", src, re.M))
        for _ in range(5):        # bounded: a chain this long is pathological
            grew = False
            for lhs, rhs in assigns.items():
                if lhs in reachable:
                    continue
                if any(r in reachable for r in re.findall(r"\b([A-Z_0-9]{2,})\b", rhs)):
                    reachable.add(lhs)
                    grew = True
            # a list built across lines: STATEMENTS = [ ... VIEW, ]
            for lhs in list(constants.values()):
                if lhs in reachable:
                    continue
                blk = re.search(rf"^([A-Z_0-9]+)\s*=\s*\[(.*?)^\]", src, re.S | re.M)
                if blk and blk.group(1) in reachable and re.search(rf"\b{lhs}\b", blk.group(2)):
                    reachable.add(lhs)
                    grew = True
            if not grew:
                break
        for block in blocks:
            m = _CREATE.search(block)
            if not m:
                continue
            # Keep a block if it sits inline in upgrade(), or is a module
            # constant the upgrade path executes by name. A block that only
            # appears in downgrade() is the PRIOR definition — skip it.
            const = constants.get(block)
            if block in body or (const and const in reachable):
                out.append((m.group(1), block))
    latest: dict[str, str] = {}
    for name, sql in out:
        latest[name] = sql
    return [(n, latest[n]) for n in dict.fromkeys(n for n, _ in out)]
