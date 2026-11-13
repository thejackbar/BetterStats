"""rebuild_bowler_wickets never replaces a game's pairings with less than it holds.

CA sometimes returns a card with innings totals and no batting rows (a scorer mid-edit, or a match
it only holds the scoreline of). The client warns "looks incomplete" and still hands the card back.
Such a card holds no dismissals, so a rebuild from it deleted the game's stored pairings and wrote
none. The script now leaves an incomplete card alone and, in --short and --force, never replaces a
game with fewer rows than it holds.

Runs the SHIPPED `rebuild_for_org` over a real Postgres, with only the CA fetch stubbed.

  I1  stored rows, CA card incomplete (totals, no batting)         -> rows untouched      (every mode)
  F1  3 stored rows, a complete card that yields 1                 -> rows untouched      (short, force)
  M1  1 stored row (no fielder), complete card names the keeper    -> replaced, keeper set (short)
  N1  the keeper's card id was never stored, his full name is on the roster and matches one
      player (sync attaches him; the rebuild now does too)         -> replaced, fielder kept
  N2  same, but his roster name is only an initial and surname      -> left alone (a rebuild that
      cannot place him must not strip the fielder from the stored row)
  T1  the club plays itself: two teams of ours, a bowler on each    -> replaced (both sides read)

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_rebuild_bowler_wickets_guards.py
Control: CONTROL=1 switches the two guards off; I1 and F1 then lose their rows.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_partnership_grade_names as base
from app.scripts import rebuild_bowler_wickets as rb

check = base.check
ORG = base.ORG
S, K, B2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
K_CARD_ID = uuid.uuid4()   # the participant id CA gave the keeper in N1/N2, never stored


def team_block():
    return [{"owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(S), "playerShortName": "S Bowler"},
                         {"participantId": str(K), "playerShortName": "K Keeper"}]}]


def complete_card(texts):
    n = len(texts)
    return {
        "teams": team_block(),
        "innings": [{
            "id": "i1", "inningsOrder": 1, "numberOfWicketsFallen": n, "runsScored": 80,
            "batting": [{"dismissalType": "Stumped", "dismissalText": t, "playerShortName": f"B{i}",
                         "batOrder": i + 1, "runsScored": 5, "ballsFaced": 7} for i, t in enumerate(texts)],
            "bowling": [{"participantId": str(S), "playerShortName": "S Bowler", "wicketsTaken": n}],
            "fielding": [{"participantId": str(K), "playerShortName": "K Keeper", "catches": 0,
                          "wicketKeeperCatches": 0, "stumpings": n}],
        }],
    }


def keeper_card(roster_name):
    """The keeper has a participant id we never stored. `roster_name` is how the team sheet writes him."""
    c = complete_card(["st: K Keeper b: S Bowler"])
    c["teams"] = [{"owningOrganisation": {"id": str(ORG)},
                   "players": [{"participantId": str(S), "name": "Sam Bowler"},
                               {"participantId": str(K_CARD_ID), "name": roster_name}]}]
    c["innings"][0]["fielding"][0]["participantId"] = str(K_CARD_ID)
    return c


def two_sides_card():
    """Both teams are the club's (it played itself): a bowler on each, one wicket each."""
    def inn(n, bowler_pid, bowler_short, dis):
        return {"id": f"i{n}", "inningsOrder": n, "numberOfWicketsFallen": 1, "runsScored": 40,
                "batting": [{"dismissalType": "Bowled", "dismissalText": f"b: {bowler_short}", "playerShortName": f"Bat{n}",
                             "batOrder": 1, "runsScored": 4, "ballsFaced": 6}],
                "bowling": [{"participantId": str(bowler_pid), "playerShortName": bowler_short, "wicketsTaken": 1}],
                "fielding": []}
    return {"teams": [{"owningOrganisation": {"id": str(ORG)}, "players": [{"participantId": str(S), "name": "Sam Bowler"}]},
                      {"owningOrganisation": {"id": str(ORG)}, "players": [{"participantId": str(B2), "name": "Bea Second"}]}],
            "innings": [inn(1, S, "S Bowler", 1), inn(2, B2, "B Second", 2)]}


def incomplete_card():
    return {"teams": team_block(),
            "innings": [{"id": "i1", "inningsOrder": 1, "numberOfWicketsFallen": 6, "runsScored": 90,
                         "batting": [], "bowling": [], "fielding": []}]}


async def main() -> None:
    await base.build_schema()
    games, cards = {}, {}
    async with base.Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("CREATE TABLE IF NOT EXISTS merge_logs (id SERIAL PRIMARY KEY, org_id UUID, keep_player_id UUID, "
                 "removed_player_id UUID, undone_at TIMESTAMPTZ)")
        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i,'Us CC','us',true)", i=ORG)
        sid, gr = uuid.uuid4(), uuid.uuid4()
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s,:o,'S 2025',2025)", s=sid, o=ORG)
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:g,:s,'1st',:x,'senior',ARRAY['senior'])", g=gr, s=sid, x=str(gr))
        for pid, nm in ((S, "Sam Bowler"), (K, "Kev Keeper"), (B2, "Bea Second")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:p,:o,:n,:g,'active')",
                     p=pid, o=ORG, n=nm, g=str(pid))

        async def game(label, held, card, *, fielder=None, bowlers=None):
            g = uuid.uuid4()
            games[label] = g
            cards[str(g)] = card
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, status) "
                     "VALUES (:g,:gr,:d,'Us','Them','COMPLETED')", g=g, gr=gr, d=date(2025, 10, 1))
            for i in range(held):
                await ex("INSERT INTO bowler_wickets (game_id, innings_number, bowler_id, fielder_id, batter_name, "
                         "dismissal_type, caught_behind) VALUES (:g,:i,:b,:f,'OLD','stumped',FALSE)",
                         g=g, i=i + 1, b=(bowlers or [S] * held)[i], f=fielder)

        await game("I1", 2, incomplete_card())
        await game("F1", 3, complete_card(["st: K Keeper b: S Bowler"]))
        await game("M1", 1, complete_card(["st:  b: S Bowler"]))
        await game("N1", 1, keeper_card("Kev Keeper"), fielder=K)
        await game("N2", 1, keeper_card("K Keeper"), fielder=K)
        await game("T1", 2, two_sides_card(), bowlers=[S, B2])
        await s.commit()

    async def fake(match_id, **kw):
        return cards.get(str(match_id))
    rb.get_match_scorecard = fake
    if os.environ.get("CONTROL"):
        rb._scorecard_looks_incomplete = lambda *a, **k: False   # guard 1 off

    async def held(label):
        async with base.Session() as s:
            return (await s.execute(text("SELECT COUNT(*), COUNT(fielder_id) FROM bowler_wickets WHERE game_id=:g"),
                                    {"g": games[label]})).one()

    async def replaced(label):
        """(rows, rows with a fielder, rows still marked OLD): OLD is what the seed stored."""
        async with base.Session() as s:
            return tuple((await s.execute(text(
                "SELECT COUNT(*), COUNT(fielder_id), COUNT(*) FILTER (WHERE batter_name = 'OLD') "
                "FROM bowler_wickets WHERE game_id=:g"), {"g": games[label]})).one())

    await rb.rebuild_for_org(str(ORG), "short")
    print("\n-- --short --")
    i1, f1, m1 = await held("I1"), await held("F1"), await held("M1")
    check("an incomplete card leaves the game's 2 rows alone (I1)", tuple(i1) == (2, 0), str(tuple(i1)))
    check("a card that would give fewer rows leaves the 3 stored (F1)", tuple(f1) == (3, 0), str(tuple(f1)))
    check("a complete card names the keeper on the blank row (M1)", tuple(m1) == (1, 1), str(tuple(m1)))

    await rb.rebuild_for_org(str(ORG), "force")
    print("\n-- --force --")
    i1, f1 = await held("I1"), await held("F1")
    check("force: the incomplete game still keeps its rows (I1)", tuple(i1) == (2, 0), str(tuple(i1)))
    check("force: the fewer-rows game still keeps its rows (F1)", tuple(f1) == (3, 0), str(tuple(f1)))
    print("\n-- the club gate reads the roster the way sync does (--force) --")
    n1, n2, t1 = await replaced("N1"), await replaced("N2"), await replaced("T1")
    check("a keeper with an unstored card id is attached by full name: rewritten, fielder kept (N1)",
          n1 == (1, 1, 0), str(n1))
    check("a keeper who cannot be placed leaves the stored row, fielder and all (N2)", n2 == (1, 1, 1), str(n2))
    check("a club playing itself: both sides read, the game is rewritten (T1)", t1[0] == 2 and t1[2] == 0, str(t1))
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
