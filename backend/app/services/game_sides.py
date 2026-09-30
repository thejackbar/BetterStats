"""Naming the two sides of a game in SQL, when a scorebook left them blank.

A match imported from a club's own scorebook (the CSFW converter, an uploaded
card) names its opposition and leaves ``home_team`` / ``away_team`` blank,
because the book never recorded which side was at home. Every list that reads
the two team columns straight off ``v_effective_games`` then shows the match as
nothing versus nothing, which is how "no opposition team" was reported off the
Games page while the match page had the name all along.

``sides_sql`` is the one rule: a blank pair on a manual game with an
opposition is named from the club and its opposition, and ``home_away_known``
says the order is not a claim. The match page (``games.get_scorecard``) and
the ORM list in ``games._fetch_manual_games_as_list`` apply the same rule in
Python. A game that carries its own names is untouched.
"""


def sides_sql(g: str, org_name_sql: str) -> str:
    """Three select columns: home_team, away_team, home_away_known.

    ``g`` is the ``v_effective_games`` alias; ``org_name_sql`` is a scalar
    subquery yielding the viewing club's name (it is only evaluated for a
    manual game whose sides are blank).
    """
    blank = (f"{g}.source = 'manual' AND NULLIF({g}.home_team, '') IS NULL "
             f"AND NULLIF({g}.away_team, '') IS NULL AND {g}.opp_club_name IS NOT NULL")
    return (
        f"COALESCE(NULLIF({g}.home_team, ''), CASE WHEN {blank} THEN ({org_name_sql}) END) AS home_team,\n"
        f"COALESCE(NULLIF({g}.away_team, ''), CASE WHEN {blank} THEN {g}.opp_club_name END) AS away_team,\n"
        f"NOT ({blank}) AS home_away_known"
    )
