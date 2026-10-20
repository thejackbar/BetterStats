"""Single source of truth for the milestone scheme.

Default thresholds (same for upcoming and achieved):
  matches : 50, 100, 150, 200, 250, ...   (every 50)
  catches : 50, 100, 150, 200, 250, ...   (every 50)
  runs    : 500, 1000, 2000, 3000, ...    (500, then every 1000)
  wickets : 50, 100, 200, 300, 400, ...   (50, then every 100)

A club can pick the increments (``Scheme``). Presets: runs every 250, 500 or
1000, wickets every 25, 50 or 100, matches and catches every 25, 50 or 100. A
club can also type its own step, inside the limits in ``STEP_LIMITS``. The
default runs and wickets steps, 1000 and 100, are the list above with its extra
first rung (500 runs, 50 wickets); any other step is a plain multiple of itself.

A club can also give a single grade its own increments
(``services/grade_milestone_schemes``). That book hands a grade-level milestone
(runs, wickets, matches or catches within "A Grade") the grade's ``Scheme``;
everything without a grade keeps the club's.

Upcoming "in-reach" windows follow the threshold, not the step:
  matches : 2 from 50, 5 from 100+
  catches : 5 from every
  runs    : 50 below 1000, 100 from 1000+
  wickets : 5 below 100, 10 from 100+
A window never reaches past half a step, so a small custom step cannot put
every player "in reach" of the next rung. No preset is affected by the cap.

Smaller pre-existing milestone rows (10/25 matches, 100/250 runs, ...) are
kept in the DB but filtered out of the display by ``is_displayable``. A row
the club's own scheme does not use (a 250 once the club goes back to 1000) is
hidden the same way and comes back if the club picks that step again.

Every function takes an optional ``scheme``; ``None`` is the default scheme, so
a caller with no club in hand (BetterScout) behaves as it always has. A caller
with a club loads one with ``load_scheme``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

MILESTONE_TYPES = {
    "runs", "wickets", "matches", "catches", "grade_matches",
    "grade_runs", "grade_wickets", "grade_catches",
}

RUNS_STEPS = (250, 500, 1000)
WICKETS_STEPS = (25, 50, 100)
MATCHES_STEPS = (25, 50, 100)
CATCHES_STEPS = (25, 50, 100)
DEFAULT_RUNS_STEP = 1000
DEFAULT_WICKETS_STEP = 100
DEFAULT_MATCHES_STEP = 50
DEFAULT_CATCHES_STEP = 50

#: stat -> (smallest, largest, a typed step must be a multiple of).
STEP_LIMITS = {
    "runs": (100, 10000, 25),
    "wickets": (10, 1000, 5),
    "matches": (10, 500, 5),
    "catches": (10, 500, 5),
}
STATS = tuple(STEP_LIMITS)
PRESET_STEPS = {
    "runs": RUNS_STEPS, "wickets": WICKETS_STEPS,
    "matches": MATCHES_STEPS, "catches": CATCHES_STEPS,
}
DEFAULT_STEPS = {
    "runs": DEFAULT_RUNS_STEP, "wickets": DEFAULT_WICKETS_STEP,
    "matches": DEFAULT_MATCHES_STEP, "catches": DEFAULT_CATCHES_STEP,
}

_STAT_OF_TYPE = {
    "runs": "runs", "grade_runs": "runs",
    "wickets": "wickets", "grade_wickets": "wickets",
    "matches": "matches", "grade_matches": "matches",
    "catches": "catches", "grade_catches": "catches",
}


def step_problem(stat: str, value) -> str | None:
    """Why a step is not allowed for ``stat``, or None when it is.

    The one validator: the save endpoints refuse with this text and the clean_*
    readers below fall back to the default on anything that fails it.
    """
    lo, hi, unit = STEP_LIMITS[stat]
    if isinstance(value, bool) or not isinstance(value, int):
        return f"{stat.capitalize()} step must be a whole number"
    if value < lo or value > hi:
        return f"{stat.capitalize()} step must be between {lo:,} and {hi:,}"
    if value % unit:
        return f"{stat.capitalize()} step must be a multiple of {unit}"
    return None


def is_valid_step(stat: str, value) -> bool:
    return step_problem(stat, value) is None


@dataclass(frozen=True)
class Scheme:
    runs_step: int = DEFAULT_RUNS_STEP
    wickets_step: int = DEFAULT_WICKETS_STEP
    matches_step: int = DEFAULT_MATCHES_STEP
    catches_step: int = DEFAULT_CATCHES_STEP

    @property
    def is_default(self) -> bool:
        return (self.runs_step == DEFAULT_RUNS_STEP
                and self.wickets_step == DEFAULT_WICKETS_STEP
                and self.matches_step == DEFAULT_MATCHES_STEP
                and self.catches_step == DEFAULT_CATCHES_STEP)

    def step_for(self, stat: str) -> int:
        return getattr(self, f"{stat}_step")

    def with_steps(self, **steps) -> "Scheme":
        """This scheme with the given stats' steps swapped in. None leaves one alone."""
        return replace(self, **{f"{k}_step": v for k, v in steps.items() if v is not None})


DEFAULT_SCHEME = Scheme()


def _clean(stat: str, value) -> int:
    return value if is_valid_step(stat, value) else DEFAULT_STEPS[stat]


def clean_runs_step(value) -> int:
    """A stored or submitted runs step, or the default when it is not an allowed one."""
    return _clean("runs", value)


def clean_wickets_step(value) -> int:
    return _clean("wickets", value)


def clean_matches_step(value) -> int:
    return _clean("matches", value)


def clean_catches_step(value) -> int:
    return _clean("catches", value)


async def load_scheme(db, org_id) -> Scheme:
    """The club's own increments. Unset, or a value we do not offer, is the default."""
    from sqlalchemy import text
    if not org_id:
        return DEFAULT_SCHEME
    row = (await db.execute(
        text("SELECT milestone_runs_step, milestone_wickets_step, "
             "milestone_matches_step, milestone_catches_step "
             "FROM organisations WHERE id = CAST(:org AS uuid)"),
        {"org": str(org_id)},
    )).first()
    if not row:
        return DEFAULT_SCHEME
    return Scheme(clean_runs_step(row[0]), clean_wickets_step(row[1]),
                  clean_matches_step(row[2]), clean_catches_step(row[3]))


def _ladder(mt: str, scheme: Scheme | None) -> tuple[int, int | None] | None:
    """(step, extra first rung) for a milestone type, else None.

    The extra rung is the default scheme's 500 runs / 50 wickets, which sits
    below its first full step. A club that picks a smaller step does not need
    it, and matches and catches have none.
    """
    stat = _STAT_OF_TYPE.get(mt)
    if stat is None:
        return None
    sc = scheme or DEFAULT_SCHEME
    step = sc.step_for(stat)
    if stat == "runs":
        return step, (500 if step == DEFAULT_RUNS_STEP else None)
    if stat == "wickets":
        return step, (50 if step == DEFAULT_WICKETS_STEP else None)
    return step, None


def next_threshold(mt: str, current: int, scheme: Scheme | None = None) -> int | None:
    ladder = _ladder(mt, scheme)
    if not ladder:
        return None
    step, extra = ladder
    if extra is not None and current < extra:
        return extra
    return ((current // step) + 1) * step


def crossed_thresholds(mt: str, current: int, scheme: Scheme | None = None) -> list[int]:
    if current <= 0:
        return []
    ladder = _ladder(mt, scheme)
    if not ladder:
        return []
    step, extra = ladder
    out: list[int] = []
    if extra is not None and current >= extra:
        out.append(extra)
    out.extend(range(step, current + 1, step))
    return out


def reach_window(mt: str, threshold: int, scheme: Scheme | None = None) -> int:
    if mt in ("runs", "grade_runs"):
        window = 50 if threshold < 1000 else 100
    elif mt in ("wickets", "grade_wickets"):
        window = 5 if threshold < 100 else 10
    elif mt in ("matches", "grade_matches"):
        window = 2 if threshold == 50 else 5
    elif mt in ("catches", "grade_catches"):
        window = 5
    else:
        return 0
    step = (scheme or DEFAULT_SCHEME).step_for(_STAT_OF_TYPE[mt])
    return min(window, max(1, step // 2))


def is_displayable(mt: str, value: int, scheme: Scheme | None = None) -> bool:
    """True if a stored milestone row matches the current scheme.

    Used to filter old, smaller-threshold rows out of the achieved list
    without deleting them from the DB.
    """
    if value is None:
        return False
    ladder = _ladder(mt, scheme)
    if not ladder:
        return False
    step, extra = ladder
    return value == extra or (value >= step and value % step == 0)
