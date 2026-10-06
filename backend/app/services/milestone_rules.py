"""Single source of truth for the milestone scheme.

Default thresholds (same for upcoming and achieved):
  matches : 50, 100, 150, 200, 250, ...   (every 50)
  catches : 50, 100, 150, 200, 250, ...   (every 50)
  runs    : 500, 1000, 2000, 3000, ...    (500, then every 1000)
  wickets : 50, 100, 200, 300, 400, ...   (50, then every 100)

A club can pick the run and wicket increments (``Scheme``): runs every 250,
500 or 1000, wickets every 25, 50 or 100. The default, 1000 and 100, is the
list above with its extra first rung (500 runs, 50 wickets); any other step is
a plain multiple of itself. Matches and catches have no setting.

Upcoming "in-reach" windows follow the threshold, not the step:
  matches : 2 from 50, 5 from 100+
  catches : 5 from every
  runs    : 50 below 1000, 100 from 1000+
  wickets : 5 below 100, 10 from 100+

Smaller pre-existing milestone rows (10/25 matches, 100/250 runs, ...) are
kept in the DB but filtered out of the display by ``is_displayable``. A row
the club's own scheme does not use (a 250 once the club goes back to 1000) is
hidden the same way and comes back if the club picks that step again.

Every function takes an optional ``scheme``; ``None`` is the default scheme, so
a caller with no club in hand (BetterScout) behaves as it always has. A caller
with a club loads one with ``load_scheme``.
"""
from __future__ import annotations

from dataclasses import dataclass

MILESTONE_TYPES = {
    "runs", "wickets", "matches", "catches", "grade_matches",
    "grade_runs", "grade_wickets", "grade_catches",
}

RUNS_STEPS = (250, 500, 1000)
WICKETS_STEPS = (25, 50, 100)
DEFAULT_RUNS_STEP = 1000
DEFAULT_WICKETS_STEP = 100


@dataclass(frozen=True)
class Scheme:
    runs_step: int = DEFAULT_RUNS_STEP
    wickets_step: int = DEFAULT_WICKETS_STEP

    @property
    def is_default(self) -> bool:
        return (self.runs_step == DEFAULT_RUNS_STEP
                and self.wickets_step == DEFAULT_WICKETS_STEP)


DEFAULT_SCHEME = Scheme()


def clean_runs_step(value) -> int:
    """A stored or submitted runs step, or the default when it is not one we offer."""
    return value if value in RUNS_STEPS else DEFAULT_RUNS_STEP


def clean_wickets_step(value) -> int:
    return value if value in WICKETS_STEPS else DEFAULT_WICKETS_STEP


async def load_scheme(db, org_id) -> Scheme:
    """The club's own increments. Unset, or a value we do not offer, is the default."""
    from sqlalchemy import text
    if not org_id:
        return DEFAULT_SCHEME
    row = (await db.execute(
        text("SELECT milestone_runs_step, milestone_wickets_step "
             "FROM organisations WHERE id = CAST(:org AS uuid)"),
        {"org": str(org_id)},
    )).first()
    if not row:
        return DEFAULT_SCHEME
    return Scheme(clean_runs_step(row[0]), clean_wickets_step(row[1]))


def _ladder(mt: str, scheme: Scheme | None) -> tuple[int, int | None] | None:
    """(step, extra first rung) for a runs or wickets type, else None.

    The extra rung is the default scheme's 500 runs / 50 wickets, which sits
    below its first full step. A club that picks a smaller step does not need it.
    """
    sc = scheme or DEFAULT_SCHEME
    if mt in ("runs", "grade_runs"):
        return sc.runs_step, (500 if sc.runs_step == DEFAULT_RUNS_STEP else None)
    if mt in ("wickets", "grade_wickets"):
        return sc.wickets_step, (50 if sc.wickets_step == DEFAULT_WICKETS_STEP else None)
    return None


def next_threshold(mt: str, current: int, scheme: Scheme | None = None) -> int | None:
    ladder = _ladder(mt, scheme)
    if ladder:
        step, extra = ladder
        if extra is not None and current < extra:
            return extra
        return ((current // step) + 1) * step
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        return ((current // 50) + 1) * 50
    return None


def crossed_thresholds(mt: str, current: int, scheme: Scheme | None = None) -> list[int]:
    if current <= 0:
        return []
    ladder = _ladder(mt, scheme)
    if ladder:
        step, extra = ladder
        out: list[int] = []
        if extra is not None and current >= extra:
            out.append(extra)
        out.extend(range(step, current + 1, step))
        return out
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        if current < 50:
            return []
        return list(range(50, current + 1, 50))
    return []


def reach_window(mt: str, threshold: int, scheme: Scheme | None = None) -> int:
    if mt in ("runs", "grade_runs"):
        return 50 if threshold < 1000 else 100
    if mt in ("wickets", "grade_wickets"):
        return 5 if threshold < 100 else 10
    if mt in ("matches", "grade_matches"):
        return 2 if threshold == 50 else 5
    if mt in ("catches", "grade_catches"):
        return 5
    return 0


def is_displayable(mt: str, value: int, scheme: Scheme | None = None) -> bool:
    """True if a stored milestone row matches the current scheme.

    Used to filter old, smaller-threshold rows out of the achieved list
    without deleting them from the DB.
    """
    if value is None:
        return False
    ladder = _ladder(mt, scheme)
    if ladder:
        step, extra = ladder
        return value == extra or (value >= step and value % step == 0)
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        return value >= 50 and value % 50 == 0
    return False
