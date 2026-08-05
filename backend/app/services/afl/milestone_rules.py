"""AFL milestone thresholds — games and goals.

Mirrors BetterStats (Core)'s milestone_rules.py, applied to AFL's own stat
shape (no runs/wickets/catches split — just games played and goals kicked).
"games" follows cricket's "matches" ladder (every 50, since a career games
tally sits in the same rough order of magnitude); "goals" follows cricket's
"wickets" ladder (50, then every 100) rather than the much larger "runs"
ladder — an AFL career goal tally (hundreds, not thousands) is closer in
scale to a bowler's career wickets than a batter's career runs.
"""

MILESTONE_TYPES = {"games", "goals"}


def next_threshold(mt: str, current: int) -> int | None:
    if mt == "games":
        return ((current // 50) + 1) * 50
    if mt == "goals":
        if current < 50:
            return 50
        return ((current // 100) + 1) * 100
    return None


def reach_window(mt: str, threshold: int) -> int:
    if mt == "games":
        return 2 if threshold == 50 else 5
    if mt == "goals":
        return 5 if threshold == 50 else 10
    return 0
