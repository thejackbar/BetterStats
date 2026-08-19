"""Verification for BetterFootball votes + team lists, against a real Postgres.

Runs the SHIPPED service and route bodies over an AFL-shaped database built
from the ORM models, so the things that actually go wrong here fail loudly:
a team list read from the wrong side of the game, a count that adds two medals'
ballots together, a medal that stops counting when the new season's grades
appear, and the asyncpg parameter-typing trap that bit the cricket side.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \\
            python scripts/verify_afl_votes.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
USER = uuid.uuid4()
SEASON = uuid.uuid4()
SEASON_NEXT = uuid.uuid4()
SENIORS = uuid.uuid4()
RESERVES = uuid.uuid4()
SENIORS_NEXT = uuid.uuid4()
RESERVES_NEXT = uuid.uuid4()
GAME_SEN = uuid.uuid4()
GAME_RES = uuid.uuid4()
FOREIGN_GAME = uuid.uuid4()
PLAYED = date.today() - timedelta(days=3)

# Six, not five: a 5-position ballot plus the self-vote rule needs six names
# to be castable at all, which is itself worth knowing.
OURS = [uuid.uuid4() for _ in range(6)]     # our players, all named
THEIRS_NAME = "Opposition Bloke"            # never one of ours


async def build(conn):
    """Every table from the ORM models — never hand-written. A test schema that
    spells a column differently is how a whole suite passes against a shared
    mistake (see the bowling_spells.runs note in CLAUDE.md)."""
    from app.models.db import Base
    import app.models.afl  # noqa: F401  — registers the AFL tables on Base
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await conn.run_sync(Base.metadata.create_all)


async def seed(db):
    from app.models.afl import AflGameDetails, AflPlayerGameLine
    from app.models.db import Game, Grade, Organisation, Player, Season, User

    db.add(Organisation(id=ORG, name="Curtin Uni Wesley", short_name="CUW", slug="cuw"))
    db.add(Organisation(id=OTHER_ORG, name="Other FC", short_name="OFC", slug="ofc"))
    db.add(User(id=USER, username="admin", email="a@example.com", password_hash="x"))
    db.add(Season(id=SEASON, organisation_id=ORG, name="2026", year=PLAYED.year))
    db.add(Season(id=SEASON_NEXT, organisation_id=ORG, name="2027", year=PLAYED.year + 1))
    for gid, sid, nm in ((SENIORS, SEASON, "A Grade Men"), (RESERVES, SEASON, "Reserves"),
                         (SENIORS_NEXT, SEASON_NEXT, "A Grade Men"),
                         (RESERVES_NEXT, SEASON_NEXT, "Reserves")):
        db.add(Grade(id=gid, season_id=sid, name=nm))
    for i, pid in enumerate(OURS):
        db.add(Player(id=pid, organisation_id=ORG, name=f"Player {i}", email=f"p{i}@example.com"))
    await db.flush()

    for gid, grade, home, away in ((GAME_SEN, SENIORS, "Curtin Uni Wesley", "Melville"),
                                   (GAME_RES, RESERVES, "Kingsley", "Curtin Uni Wesley")):
        db.add(Game(id=gid, grade_id=grade, played_at=PLAYED, home_team=home, away_team=away))
    await db.flush()

    # Our side is HOME in the seniors game and AWAY in the reserves one, so a
    # read that assumes one or the other shows up immediately.
    for gid, our_side in ((GAME_SEN, "HOME"), (GAME_RES, "AWAY")):
        db.add(AflGameDetails(game_id=gid, playhq_id=str(gid), status="FINAL",
                              our_side=our_side, publish_lineup=True, round_name="5"))
    await db.flush()

    for gid, our_side in ((GAME_SEN, "HOME"), (GAME_RES, "AWAY")):
        other = "AWAY" if our_side == "HOME" else "HOME"
        for i, pid in enumerate(OURS):
            db.add(AflPlayerGameLine(
                id=uuid.uuid4(), game_id=gid, side=our_side, team_name="Curtin Uni Wesley",
                playhq_participant_id=f"{gid}-{i}", player_id=pid, name=f"Player {i}",
                jumper_number=str(i + 1), is_captain=(i == 0), goals=i, behinds=0))
        # The opposition's own named side, on the SAME game row. Anything that
        # reads a team list without scoping to our_side will pick this up.
        db.add(AflPlayerGameLine(
            id=uuid.uuid4(), game_id=gid, side=other, team_name="Them",
            playhq_participant_id=f"{gid}-opp", player_id=None, name=THEIRS_NAME,
            jumper_number="1", goals=0, behinds=0))
    # A player named on our sheet we hold no record for — a fill-in.
    db.add(AflPlayerGameLine(
        id=uuid.uuid4(), game_id=GAME_SEN, side="HOME", team_name="Curtin Uni Wesley",
        playhq_participant_id=f"{GAME_SEN}-fillin", player_id=None,
        name="Late Inclusion", jumper_number="44", goals=0, behinds=0))
    await db.commit()


async def main():
    engine = create_async_engine(DSN)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await build(conn)
    async with Session() as db:
        await seed(db)

    from app.services.afl import lineups as lineup_svc
    from app.services.afl import votes as vote_svc

    # ── Team lists ─────────────────────────────────────────────────────────
    async with Session() as db:
        out = await lineup_svc.game_lineups(db, ORG, GAME_SEN)
        check("a game's team list resolves", out is not None)
        check("both sides come back", len(out["teams"]) == 2)
        ours = next(t for t in out["teams"] if t["is_ours"])
        theirs = next(t for t in out["teams"] if not t["is_ours"])
        check("our side is the one PlayHQ says is ours", ours["side"] == "HOME", ours["side"])
        check("the opposition's named side is kept, but marked theirs",
              any(p["name"] == THEIRS_NAME for p in theirs["players"]))
        check("the opposition never leaks onto our side",
              not any(p["name"] == THEIRS_NAME for p in ours["players"]))
        check("the captain sorts first", ours["players"][0]["is_captain"], str(ours["players"][0]))
        check("PlayHQ's publish flag is reported", out["published"] is True)

        # The reserves game has our side as AWAY — the same read must follow it.
        res = await lineup_svc.game_lineups(db, ORG, GAME_RES)
        ours_res = next(t for t in res["teams"] if t["is_ours"])
        check("our side follows the game, not a hardcoded HOME", ours_res["side"] == "AWAY")

        check("another club can't read our game", await lineup_svc.game_lineups(db, OTHER_ORG, GAME_SEN) is None)

        players, unmatched = await lineup_svc.our_lineup_players(db, ORG, GAME_SEN)
        check("the votable list is our named side only", len(players) == len(OURS), str(len(players)))
        check("a fill-in we hold no record for is reported, not silently dropped",
              unmatched == ["Late Inclusion"], str(unmatched))
        check("the opposition is never votable", THEIRS_NAME not in [p["name"] for p in players])

        counts = await lineup_svc.lineup_counts(db, ORG, [GAME_SEN, GAME_RES])
        check("batch counts match the per-game read",
              counts.get(str(GAME_SEN)) == len(OURS) and counts.get(str(GAME_RES)) == len(OURS),
              str(counts))

    # ── Medals ─────────────────────────────────────────────────────────────
    from app.routers.afl import votes as votes_router

    class FakeClub:
        id = ORG
        name = "Curtin Uni Wesley"
        short_name = "CUW"

    class FakeUser:
        id = USER

    club, user = FakeClub(), FakeUser()

    async with Session() as db:
        first = await vote_svc.ensure_default_medal(db, ORG)
        await db.commit()
        check("a club's first medal is minted on demand", first.name == "Best & Fairest")
        check("...counting every grade until told otherwise",
              vote_svc.clean_grade_ids(first.grade_ids) == [])

        reserves = await votes_router.create_medal(
            votes_router.MedalUpdate(name="Reserves Medal", ballot_values=[5, 4, 3, 2, 1],
                                     grade_ids=[str(RESERVES)], enabled=True),
            db=db, club=club, user=user)
        check("a second medal keeps its own ballot shape",
              reserves["ballot_values"] == [5, 4, 3, 2, 1])
        check("enabling a medal mints its own link", bool(reserves["token"]))
        check("a medal reports the grade names behind its ids",
              reserves["grade_names"] == ["Reserves"], str(reserves["grade_names"]))

        opts = await vote_svc.club_grade_options(db, ORG)
        check("the grade picker offers each name once, not once per season",
              sorted(o["name"] for o in opts) == ["A Grade Men", "Reserves"], str(opts))

        res_medal = await vote_svc.get_medal(db, ORG, reserves["medal_id"])
        allowed = await vote_svc.medal_grade_ids(db, ORG, res_medal)
        check("a restricted medal counts its own grade", vote_svc.medal_covers(allowed, RESERVES))
        check("...and not another", not vote_svc.medal_covers(allowed, SENIORS))
        # The reason ids are expanded through names: next season's Reserves is a
        # different grades row, and the medal must not stop counting.
        check("a restricted medal picks up NEXT season's grade of the same name",
              vote_svc.medal_covers(allowed, RESERVES_NEXT), str(allowed))
        check("...and still not next season's other grade",
              not vote_svc.medal_covers(allowed, SENIORS_NEXT))
        check("a game whose grade can't be placed is left out of a restricted medal",
              not vote_svc.medal_covers(allowed, None))
        check("...but counted by an all-grades one", vote_svc.medal_covers(None, None))

        check("a medal id from another club never resolves",
              await vote_svc.get_medal(db, OTHER_ORG, reserves["medal_id"]) is None)

    # ── Ballots and the count ──────────────────────────────────────────────
    async with Session() as db:
        medals = await vote_svc.list_medals(db, ORG)
        # Capture the ids as plain strings: a rollback below EXPIRES every ORM
        # object on this session, and touching an expired attribute afterwards
        # is a MissingGreenlet waiting to happen (the same lesson
        # services/afl/sync.py's _sync_game_stats documents).
        champ_id, res_id = str(medals[0].id), str(medals[1].id)

        # Three voters give the seniors medal a 3-2-1 on the seniors game.
        for voter in OURS[:3]:
            await votes_router.admin_enter_ballot(
                str(GAME_SEN), votes_router.AdminBallot(
                    voter_player_id=str(voter), picks=[str(OURS[3]), str(OURS[4]), str(OURS[5])]),
                medal_id=champ_id, db=db, club=club, user=user)
        # One voter gives the reserves medal a 5-4-3-2-1 on the reserves game.
        await votes_router.admin_enter_ballot(
            str(GAME_RES), votes_router.AdminBallot(
                voter_player_id=str(OURS[0]),
                picks=[str(OURS[1]), str(OURS[2]), str(OURS[3]), str(OURS[4]), str(OURS[5])]),
            medal_id=res_id, db=db, club=club, user=user)
        check("ballots enter against each medal", True)

        # The self-vote rule, which is off by default.
        refused = False
        try:
            await votes_router.admin_enter_ballot(
                str(GAME_SEN), votes_router.AdminBallot(
                    voter_player_id=str(OURS[1]),
                    picks=[str(OURS[1]), str(OURS[2]), str(OURS[3])]),
                medal_id=champ_id, db=db, club=club, user=user)
        except Exception as e:
            refused = "yourself" in str(getattr(e, "detail", e)).lower()
            await db.rollback()
        check("voting for yourself is refused unless the club allows it", refused)

        # A pick who wasn't named for the game.
        stranger = False
        try:
            await votes_router.admin_enter_ballot(
                str(GAME_SEN), votes_router.AdminBallot(
                    voter_name="Coach", picks=[str(uuid.uuid4()), str(OURS[2]), str(OURS[3])]),
                medal_id=champ_id, db=db, club=club, user=user)
        except Exception as e:
            stranger = "named for this game" in str(getattr(e, "detail", e)).lower()
            await db.rollback()
        check("a vote can't go to someone who wasn't named", stranger)

        # The SAME voter on the SAME game, for the other medal — allowed, and
        # it must not overwrite the first.
        await votes_router.admin_enter_ballot(
            str(GAME_RES), votes_router.AdminBallot(
                voter_player_id=str(OURS[0]), picks=[str(OURS[4]), str(OURS[3]), str(OURS[2])]),
            medal_id=champ_id, db=db, club=club, user=user)
        n = (await db.execute(text(
            "SELECT count(*) FROM afl_vote_ballots WHERE game_id = :g AND voter_player_id = :p"),
            {"g": GAME_RES, "p": OURS[0]})).scalar()
        check("one voter holds a ballot per medal on the same game", n == 2, f"got {n}")

    async with Session() as db:
        medals = await vote_svc.list_medals(db, ORG)
        champ, res_medal = medals[0], medals[1]

        board_champ = await vote_svc.build_leaderboard(
            db, ORG, vote_svc.effective_config(champ), SEASON, medal=champ)
        board_res = await vote_svc.build_leaderboard(
            db, ORG, vote_svc.effective_config(res_medal), SEASON, medal=res_medal)

        champ_games = {g["id"] for rd in board_champ["rounds"] for g in rd["games"]}
        res_games = {g["id"] for rd in board_res["rounds"] for g in rd["games"]}
        check("the all-grades medal counts both games",
              champ_games == {str(GAME_SEN), str(GAME_RES)}, str(champ_games))
        check("the Reserves medal counts only its own grade's game",
              res_games == {str(GAME_RES)}, str(res_games))

        champ_total = sum(s["points"] for s in board_champ["standings"])
        res_total = sum(s["points"] for s in board_res["standings"])
        # 'rank' is the default and it is NOT a raw tally: each game's votes are
        # converted, so the week's top vote-getter earns ballot_values[0] however
        # many 3s they collected. Three voters all giving 3-2-1 to the same three
        # players is still 3+2+1 = 6 for that game, not 18.
        #   seniors game 6 + the seniors medal's ballot on the reserves game 6 = 12
        check("the seniors count sums only its own ballots", champ_total == 12, f"got {champ_total}")
        # One 5-4-3-2-1 ballot converts to 5+4+3+2+1.
        check("the Reserves count isn't inflated by the other medal", res_total == 15, f"got {res_total}")

        # The same ballots under 'tally' must give the raw sum instead — the one
        # setting that changes what a season's numbers mean.
        tally_cfg = {**vote_svc.effective_config(medals[0]), "counting_method": "tally"}
        tallied = await vote_svc.build_leaderboard(db, ORG, tally_cfg, SEASON, medal=medals[0])
        check("switching a medal to a full tally restates the season from the same ballots",
              sum(s["points"] for s in tallied["standings"]) == 24,
              f"got {sum(s['points'] for s in tallied['standings'])}")
        check("each board names its own medal",
              board_champ["medal_name"] == "Best & Fairest"
              and board_res["medal_name"] == "Reserves Medal")

        counts_champ = await vote_svc.player_ballot_counts(db, ORG, [GAME_RES], champ.id)
        counts_res = await vote_svc.player_ballot_counts(db, ORG, [GAME_RES], res_medal.id)
        check("voted-already counts are per medal (the asyncpg CAST path)",
              counts_champ.get(str(GAME_RES)) == 1 and counts_res.get(str(GAME_RES)) == 1,
              f"{counts_champ} / {counts_res}")

        # Locking one medal's count on a game must not lock the other's.
        await votes_router.lock_game(str(GAME_RES), medal_id=str(res_medal.id),
                                     db=db, club=club, user=user)
        ov_res = await vote_svc.get_override(db, res_medal.id, GAME_RES)
        ov_champ = await vote_svc.get_override(db, champ.id, GAME_RES)
        check("locking is per medal", ov_res.status == "locked" and ov_champ is None)

        nudged = await vote_svc.recently_nudged(db, champ.id, GAME_SEN, [OURS[0]])
        check("nothing reads as nudged before anything is sent", not nudged)

    # ── Route-level guards ─────────────────────────────────────────────────
    async with Session() as db:
        listed = await votes_router.list_medals(db=db, club=club, user=user)
        check("the medals endpoint returns both plus grade options",
              len(listed["medals"]) == 2 and len(listed["grades"]) == 2)

        games = await votes_router.list_vote_games(
            season_id=str(SEASON), medal_id=None, db=db, club=club, user=user)
        check("the games list shows what the first medal counts", len(games["games"]) == 2,
              str(len(games["games"])))
        check("a played game with a team list reads as open",
              all(g["state"] in ("open", "closed", "locked") for g in games["games"]),
              str([g["state"] for g in games["games"]]))
        check("the games list reports the expected voter count",
              all(g["voters_expected"] == len(OURS) for g in games["games"]),
              str([g["voters_expected"] for g in games["games"]]))

        medals = await vote_svc.list_medals(db, ORG)
        res_games = await votes_router.list_vote_games(
            season_id=str(SEASON), medal_id=str(medals[1].id), db=db, club=club, user=user)
        check("a restricted medal's games list drops the other grade",
              len(res_games["games"]) == 1, str(len(res_games["games"])))

        bad = False
        try:
            await votes_router._resolve_or_404(db, club, str(uuid.uuid4()))
        except Exception as e:
            bad = getattr(e, "status_code", None) == 404
        check("a stale medal id 404s rather than counting a different award", bad)

        foreign = False
        try:
            await votes_router._org_game(db, club, str(FOREIGN_GAME))
        except Exception as e:
            foreign = getattr(e, "status_code", None) == 404
        check("a game id that isn't ours 404s", foreign)

        last = False
        try:
            await votes_router.delete_medal(str(medals[1].id), confirm=True, db=db, club=club, user=user)
            await votes_router.delete_medal(str(medals[0].id), confirm=True, db=db, club=club, user=user)
        except Exception as e:
            last = "at least one" in str(getattr(e, "detail", e)).lower()
            await db.rollback()
        check("a club's last medal can't be deleted", last)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
