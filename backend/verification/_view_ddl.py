"""Pull the `v_effective_*` view definitions straight out of the migrations.

Retyping a view into a harness is how a suite ends up proving something about
SQL the app doesn't run. Each view is taken from the LAST migration that
defines it, applied in migration order.
"""
from __future__ import annotations

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
# In migration order. Each later file supersedes the views it redefines.
FILES = [
    "038_effective_per_game_views.py",
    "075_batting_caught_behind.py",
    "093_manual_bowler_wickets.py",
    "147_fillin_partnerships_fielding_names.py",
    "252_statlab_residual_grade_label.py",
    "266_game_status_unplayed_matches.py",
]
_CREATE = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(v_effective_\w+)\s+AS", re.I)


def _upgrade_src(src: str) -> str:
    """Only the upgrade() body — a downgrade holds the PRIOR definition."""
    i = src.find("def upgrade()")
    j = src.find("def downgrade()")
    if i == -1:
        return src
    return src[i:j] if j > i else src[i:]


def view_statements() -> list[tuple[str, str]]:
    """[(view_name, create_sql)] — the LAST definition of each view, in order.

    Only the newest definition is applied: an earlier one is superseded by
    construction, and applying it first would test SQL the app never runs.
    """
    out: list[tuple[str, str]] = []
    for name in FILES:
        src = (VERSIONS / name).read_text()
        body = _upgrade_src(src)
        # Every triple-quoted string in the upgrade path, whether inlined in an
        # op.execute(...) or hoisted into a module-level constant it references.
        blocks = re.findall(r'"""(.*?)"""', src, re.S)
        constants = {
            cm.group(2): cm.group(1)
            for cm in re.finditer(r'^([A-Z_0-9]+)\s*=\s*"""(.*?)"""', src, re.S | re.M)
        }
        for block in blocks:
            m = _CREATE.search(block)
            if not m:
                continue
            # Keep a block if it sits inline in upgrade(), or is a module
            # constant the upgrade path executes by name. A block that only
            # appears in downgrade() is the PRIOR definition — skip it.
            const = constants.get(block)
            if block in body or (const and re.search(rf'\b{const}\b', body)):
                out.append((m.group(1), block))
    latest: dict[str, str] = {}
    for name, sql in out:
        latest[name] = sql
    return [(n, latest[n]) for n in dict.fromkeys(n for n, _ in out)]
