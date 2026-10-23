"""Judge every club card that is linked to a synced game: is it on a game of its own grade?

Shared by the read-only audit (`scripts/audit_pairing`) and the repair that unlinks a card from a game
of another grade (`card_review_actions.bulk_unlink_wrong_grade`), so the two can never disagree about
which links are wrong. The import that made these links ignored grade; this is the check that reads it.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import text

from app.services import card_review as cr
from app.services import card_review_doubles as dbl
from app.services import match_pairing as mp

LINKED = """
    SELECT m.id::text AS mid, m.season_id::text AS season_id, m.played_at, COALESCE(m.opposition, '') AS opposition, m.review_pair_ok,
           m.superseded_by_game_id::text AS gid, COALESCE(gr.display_name_override, gr.name) AS grade,
           g.played_at AS g_day, COALESCE(gg.display_name_override, gg.name) AS g_grade,
           CASE WHEN g.home_org_id = CAST(:org AS UUID) THEN g.away_team
                WHEN g.away_org_id = CAST(:org AS UUID) THEN g.home_team
                ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team) END AS g_opp
      FROM manual_games m
      JOIN games g ON g.id = m.superseded_by_game_id
      LEFT JOIN grades gr ON gr.id = m.grade_id
      LEFT JOIN grades gg ON gg.id = g.grade_id
     WHERE m.organisation_id = CAST(:org AS UUID)
"""

# Clubs and Cricket Australia name an age group differently from season to season (Payneham's "Under 16"
# is Cricket Australia's "Under 17 Division 2" in 2019/20). When a club's OWN links, proved by batters,
# show two names are one grade in a season, an unproven link between the same two names is not called wrong.
ALIAS_MIN = 2

# the verdicts that say the card is on a game of another grade and nothing a person decided keeps it there
WRONG_GRADE = ("contradicted_grade_differs", "unproven_grade_differs")


def classify_link(card_grade, game_grade, shared: int, club_n: int, game_n: int, confirmed: bool, person_ok: bool) -> str:
    """One word for a linked pair. Pure, so the suite can drive every branch."""
    gk, hk = dbl.grade_key(card_grade), dbl.grade_key(game_grade)
    differs = bool(gk and hk and gk != hk)
    unreadable = not (gk and hk)
    if person_ok:
        return "person_ok_grade_differs" if differs else "person_ok"
    if confirmed:
        if differs:
            return "proved_grade_names_differ"
        return "proved_grade_unreadable" if unreadable else "proved"
    if club_n and game_n:  # both hold batters and they do not agree
        return "contradicted_grade_differs" if differs else "contradicted"
    if differs:
        return "unproven_grade_differs"
    return "unproven_grade_unreadable" if unreadable else "unproven_same_grade"


async def linked_verdicts(db, org_id) -> list[dict]:
    """Every linked card with its game, the batters they share and a `verdict` (see classify_link)."""
    org = str(org_id)
    rows = [dict(r) for r in (await db.execute(text(LINKED), {"org": org})).mappings().all()]
    if not rows:
        return []
    mine = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": [r["mid"] for r in rows]})
    theirs = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org, "ids": sorted({r["gid"] for r in rows})})
    for r in rows:
        a, b = set(mine.get(r["mid"], ())), set(theirs.get(r["gid"], ()))
        r["shared"], r["club_n"], r["game_n"] = len(a & b), len(a), len(b)
        r["verdict"] = classify_link(r["grade"], r["g_grade"], r["shared"], len(a), len(b),
                                     cr.confirms_pair(a, b), bool(r["review_pair_ok"]))
        r["day_gap"] = mp._day_gap(r["played_at"], r["g_day"])
        r["opposition_agrees"] = mp.teams_agree(r["opposition"], r["g_opp"] or "")
    pair = lambda r: (r["season_id"], dbl.grade_key(r["grade"]), dbl.grade_key(r["g_grade"]))  # noqa: E731
    seen = Counter(pair(r) for r in rows if r["verdict"] == "proved_grade_names_differ")
    aliases = {k for k, n in seen.items() if n >= ALIAS_MIN}
    for r in rows:
        r["alias"] = pair(r) in aliases
        if r["alias"] and r["verdict"] == "contradicted_grade_differs":
            r["verdict"] = "contradicted"
        elif r["alias"] and r["verdict"] == "unproven_grade_differs":
            r["verdict"] = "unproven_same_grade"
    return rows
