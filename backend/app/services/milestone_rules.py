"""Single source of truth for the milestone scheme.

Thresholds (same for upcoming and achieved):
  matches : 50, 100, 150, 200, 250, ...   (every 50)
  catches : 50, 100, 150, 200, 250, ...   (every 50)
  runs    : 500, 1000, 2000, 3000, ...    (500, then every 1000)
  wickets : 50, 100, 200, 300, 400, ...   (50, then every 100)

Upcoming "in-reach" windows:
  matches : 2 from 50, 5 from 100+
  catches : 5 from every
  runs    : 50 from 500, 100 from 1000+
  wickets : 5 from 50, 10 from 100+

Smaller pre-existing milestone rows (10/25 matches, 100/250 runs, ...) are
kept in the DB but filtered out of the display by ``is_displayable``.
"""

MILESTONE_TYPES = {
    "runs", "wickets", "matches", "catches", "grade_matches",
    "grade_runs", "grade_wickets", "grade_catches",
}


def next_threshold(mt: str, current: int) -> int | None:
    if mt in ("runs", "grade_runs"):
        if current < 500:
            return 500
        return ((current // 1000) + 1) * 1000
    if mt in ("wickets", "grade_wickets"):
        if current < 50:
            return 50
        return ((current // 100) + 1) * 100
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        return ((current // 50) + 1) * 50
    return None


def crossed_thresholds(mt: str, current: int) -> list[int]:
    if current <= 0:
        return []
    if mt in ("runs", "grade_runs"):
        out: list[int] = []
        if current >= 500:
            out.append(500)
        out.extend(range(1000, current + 1, 1000))
        return out
    if mt in ("wickets", "grade_wickets"):
        out = []
        if current >= 50:
            out.append(50)
        out.extend(range(100, current + 1, 100))
        return out
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        if current < 50:
            return []
        return list(range(50, current + 1, 50))
    return []


def reach_window(mt: str, threshold: int) -> int:
    if mt in ("runs", "grade_runs"):
        return 50 if threshold == 500 else 100
    if mt in ("wickets", "grade_wickets"):
        return 5 if threshold == 50 else 10
    if mt in ("matches", "grade_matches"):
        return 2 if threshold == 50 else 5
    if mt in ("catches", "grade_catches"):
        return 5
    return 0


def is_displayable(mt: str, value: int) -> bool:
    """True if a stored milestone row matches the current scheme.

    Used to filter old, smaller-threshold rows out of the achieved list
    without deleting them from the DB.
    """
    if value is None:
        return False
    if mt in ("runs", "grade_runs"):
        return value == 500 or (value >= 1000 and value % 1000 == 0)
    if mt in ("wickets", "grade_wickets"):
        return value == 50 or (value >= 100 and value % 100 == 0)
    if mt in ("matches", "grade_matches", "catches", "grade_catches"):
        return value >= 50 and value % 50 == 0
    return False
