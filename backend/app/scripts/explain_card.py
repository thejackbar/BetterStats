"""Why is this club scorecard linked to the game it is, and what is on the game it should be on?

Read-only. Reported off Shoalwater Bay: after the wrong-link repair and `repair_crossed_pairs`, a few
cards were still "pairing looks wrong" and neither script would move them (`held back`: a move would
not be a closed swap). The cause is always something SITTING on the game the card matches: another
club card, one a person confirmed, or one that matches that game less well. This prints, for each card
given by the first characters of its id (the 8 characters the repair scripts print), the card's flags,
the game it is linked to now, and every synced game within a week, with how many of the card's
batters are on it, whether it is free, and if not WHICH card holds it, how well that card matches it,
and whether a person confirmed that link.

    python -m app.scripts.explain_card <org-id-or-slug> <card-id-prefix> [<card-id-prefix> ...]
"""
import asyncio
import sys
from datetime import timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import card_review as cr
from app.services import match_pairing as mp

_GAMES = """
    SELECT g.id::text AS id, g.played_at, g.match_format, g.home_team, g.away_team, g.opp_club_name,
           COALESCE(gr.display_name_override, gr.name) AS grade,
           tw.id::text AS holder, tw.review_pair_ok AS holder_ok, tw.review_source AS holder_source,
           tw.pairing_locked AS holder_locked, tw.cricketstatz_import_id IS NOT NULL AS holder_cs,
           COALESCE(tw.opposition, '') AS holder_opp
      FROM games g
      LEFT JOIN grades gr ON gr.id = g.grade_id
      LEFT JOIN seasons s ON s.id = gr.season_id
      LEFT JOIN manual_games tw ON tw.superseded_by_game_id = g.id
     WHERE (s.organisation_id = CAST(:org AS UUID) OR g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID))
       AND g.played_at BETWEEN :lo AND :hi
     ORDER BY g.played_at, g.id
"""


async def explain(db, org_id: str, prefix: str) -> None:
    rows = (await db.execute(text(
        "SELECT m.id::text AS id, m.played_at, m.opposition, m.match_format, m.superseded_by_game_id::text AS gid, "
        "m.review_pair_ok, m.review_source, m.review_choice, m.pairing_locked, m.pair_prefers_import, "
        "COALESCE(gr.display_name_override, gr.name) AS grade, s.name AS season "
        "FROM manual_games m LEFT JOIN grades gr ON gr.id = m.grade_id LEFT JOIN seasons s ON s.id = m.season_id "
        "WHERE m.organisation_id = CAST(:o AS UUID) AND m.id::text LIKE :p"), {"o": org_id, "p": prefix + "%"})).mappings().all()
    if len(rows) != 1:
        print(f"\n[{prefix}] {'no card' if not rows else 'more than one card'} starts with that. Give more characters.")
        return
    m = rows[0]
    cid = m["id"]
    sig = frozenset((await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": [cid]})).get(cid, ()))
    print(f"\n=== card {cid[:8]}: {m['grade']} v {m['opposition']}, {m['played_at']}  ({m['season']})  [{m['match_format'] or 'no format'}]")
    print(f"    {len(sig)} batters; link confirmed by a person={bool(m['review_pair_ok'])}; display chosen by={m['review_source'] or 'nobody'}"
          f" ({m['review_choice'] or 'no choice'}); import locked={bool(m['pairing_locked'])}; shows the {'club card' if m['pair_prefers_import'] else 'Cricket Australia game'}")
    lo, hi = m["played_at"] - timedelta(days=7), m["played_at"] + timedelta(days=7)
    games = (await db.execute(text(_GAMES), {"org": org_id, "lo": lo, "hi": hi})).mappings().all()
    gcards = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org_id, "ids": [g["id"] for g in games]}) if games else {}
    holders = [g["holder"] for g in games if g["holder"]]
    hcards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": holders}) if holders else {}
    for g in games:
        gsig = frozenset(gcards.get(g["id"], ()))
        shared = len(sig & gsig)
        opp = g["opp_club_name"] or f"{g['home_team']} v {g['away_team']}"
        mark = "  <- LINKED NOW" if g["id"] == m["gid"] else ""
        verdict = ""
        if g["id"] != m["gid"]:
            if cr.confirms_pair(set(sig), set(gsig)):
                if not g["holder"]:
                    verdict = "FREE and matches this card: the wrong-link scan offers it"
                else:
                    hs = frozenset(hcards.get(g["holder"], ()))
                    verdict = (f"MATCHES this card but is held by card {g['holder'][:8]} ({g['holder_opp']}), which shares {len(hs & gsig)} of its "
                               f"{len(hs)} batters with it; link confirmed by a person={bool(g['holder_ok'])}; "
                               f"{'CricketStatz import' if g['holder_cs'] else 'club card'}")
            else:
                verdict = "does not match this card"
        print(f"    game {g['id'][:8]}  {g['played_at']}  {g['grade']} v {opp}  [{g['match_format'] or 'no format'}]  "
              f"{len(gsig)} batters, {shared} in common{mark}")
        if verdict:
            print(f"        {verdict}")


async def main(org: str, prefixes: list) -> None:
    async with async_session_maker() as db:
        org_id = (await db.execute(text("SELECT id::text FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).scalar()
        if not org_id:
            print(f"No club '{org}'.")
            return
        for p in prefixes:
            await explain(db, org_id, p)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
