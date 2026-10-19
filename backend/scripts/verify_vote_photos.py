"""Verification for player photos on the admin Votes payloads, against a real Postgres.

Runs the SHIPPED service and route body (``build_leaderboard``, ``player_photos``,
``fixture_detail``) over a seeded club, so what is checked is what the Votes screens
receive: ``photo_url`` on every standing, on the last-round results, on the game's
count, and on each ballot's voter and picks.

Photo keys are read with ``.get`` so a run against the code before this change
reports "absent" instead of crashing: a control run that crashes is not a control run.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_photos.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DSN = os.environ["DATABASE_URL"]

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


ORG, OTHER_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
USER = uuid.uuid4()
TODAY = date.today()
PLAYED = date(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 10, 1)

URL_A, URL_B = "https://cdn.example.test/a.jpg", "https://cdn.example.test/b.jpg"
# Four players with a different photo state each, plus one at another club.
P_PHOTO, P_NONE, P_EMPTY, P_PHOTO2 = (uuid.uuid4() for _ in range(4))
P_OTHER_CLUB = uuid.uuid4()
VOTER = uuid.uuid4()
PHOTOS = {P_PHOTO: URL_A, P_NONE: None, P_EMPTY: "", P_PHOTO2: URL_B}
FX, GAME = uuid.uuid4(), uuid.uuid4()


async def seed(db) -> None:
    from app.models.db import (
        Fixture, Game, GameAppearance, Grade, Organisation, Player, Season, User,
        VoteBallot, VoteBallotPick, VoteMedal,
    )
    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross"))
    db.add(Organisation(id=OTHER_ORG, name="Other CC", short_name="OCC", slug="other"))
    db.add(User(id=USER, username="admin", email="admin@example.com", password_hash="x"))
    db.add(Season(id=SEASON, organisation_id=ORG, name="Summer", year=PLAYED.year))
    db.add(Grade(id=GRADE, season_id=SEASON, name="4th Grade"))
    for pid, url in PHOTOS.items():
        db.add(Player(id=pid, organisation_id=ORG, name=f"Player {str(pid)[:4]}", photo_url=url))
    db.add(Player(id=VOTER, organisation_id=ORG, name="Voter Vee", photo_url=URL_B))
    db.add(Player(id=P_OTHER_CLUB, organisation_id=OTHER_ORG, name="Elsewhere", photo_url="https://other.example.test/x.jpg"))
    await db.flush()
    db.add(Game(id=GAME, grade_id=GRADE))
    db.add(Fixture(id=FX, organisation_id=ORG, playhq_id=str(GAME), opponent_name="Melville",
                   round="2", played_on=PLAYED, end_on=PLAYED, home_away="H"))
    await db.flush()
    for pid in (*PHOTOS, VOTER):
        db.add(GameAppearance(game_id=GAME, player_id=pid, is_captain=False))
    medal = VoteMedal(id=uuid.uuid4(), organisation_id=ORG, name="Best Player", enabled=True)
    db.add(medal)
    await db.flush()
    ballot = VoteBallot(id=uuid.uuid4(), organisation_id=ORG, fixture_id=FX, medal_id=medal.id,
                        voter_player_id=VOTER, voter_kind="player", source="public")
    db.add(ballot)
    await db.flush()
    for pos, pid in enumerate((P_PHOTO, P_NONE, P_EMPTY), start=1):
        db.add(VoteBallotPick(ballot_id=ballot.id, position=pos, player_id=pid))
    await db.commit()
    return medal.id


async def main() -> None:
    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    from app.models.db import Base
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as db:
        medal_id = await seed(db)

    from app.services import votes as vote_svc
    from app.routers import votes as votes_router
    from app.models.db import Organisation, VoteMedal

    async with Session() as db:
        club = await db.get(Organisation, ORG)
        medal = await db.get(VoteMedal, medal_id)
        cfg = vote_svc.effective_config(medal)

        # ── The lookup ─────────────────────────────────────────────────────
        lookup = getattr(vote_svc, "player_photos", None)
        got = await lookup(db, ORG, {str(p) for p in (*PHOTOS, VOTER, P_OTHER_CLUB)}) if lookup else {}
        check("player_photos exists", lookup is not None)
        check("a player with a photo is returned with its URL", got.get(str(P_PHOTO)) == URL_A, str(got))
        check("a player with no photo is left out, not returned as None", str(P_NONE) not in got)
        check("an empty-string photo is treated as no photo", str(P_EMPTY) not in got)
        check("another club's player is never returned (org scoped)", str(P_OTHER_CLUB) not in got)
        check("no ids, no query, empty answer",
              (await lookup(db, ORG, set()) if lookup else None) == {})

        # ── The leaderboard ────────────────────────────────────────────────
        board = await vote_svc.build_leaderboard(
            db, ORG, cfg, vote_svc.season_year_for(PLAYED), medal=medal)
        by_pid = {s["player_id"]: s for s in board["standings"]}
        check("the board has the three voted-for players", len(by_pid) == 3, str(list(by_pid)))
        check("standing: photo player carries photo_url", by_pid[str(P_PHOTO)].get("photo_url") == URL_A,
              str(by_pid[str(P_PHOTO)].get("photo_url")))
        check("standing: player with no photo has photo_url None", by_pid[str(P_NONE)].get("photo_url") is None
              and "photo_url" in by_pid[str(P_NONE)])
        check("standing: empty-string photo comes back as None", by_pid[str(P_EMPTY)].get("photo_url") is None
              and "photo_url" in by_pid[str(P_EMPTY)])
        check("standing: points and names are unchanged by the photo lookup",
              by_pid[str(P_PHOTO)]["points"] == 3 and by_pid[str(P_PHOTO)]["name"].startswith("Player "))
        lr = {r["player_id"]: r for r in (board["last_round"] or {}).get("results", [])}
        check("last round: the scoring player carries photo_url", lr.get(str(P_PHOTO), {}).get("photo_url") == URL_A,
              str(lr))
        check("last round: the three players who scored appear", set(lr) == {str(P_PHOTO), str(P_NONE), str(P_EMPTY)},
              str(set(lr)))
        check("last round: a scorer with no photo has photo_url None and the key is present",
              lr.get(str(P_NONE), {}).get("photo_url", "absent") is None)

        # ── The game detail (the shipped route body) ───────────────────────
        class FakeUser:
            id = USER

        detail = await votes_router.fixture_detail(str(FX), medal_id=str(medal_id), db=db, club=club, user=FakeUser())
        res = {r["player_id"]: r for r in detail["results"]}
        check("game count: photo player carries photo_url", res[str(P_PHOTO)].get("photo_url") == URL_A,
              str(res[str(P_PHOTO)].get("photo_url")))
        check("game count: no-photo player has photo_url None and the key is present",
              res[str(P_NONE)].get("photo_url") is None and "photo_url" in res[str(P_NONE)])
        b = detail["ballots"][0]
        check("ballot: the voter's photo is sent", b.get("voter_photo_url") == URL_B, str(b.get("voter_photo_url")))
        picks = {p["player_id"]: p for p in b["picks"]}
        check("ballot: picks carry photo_url", picks[str(P_PHOTO)].get("photo_url") == URL_A)
        check("ballot: a pick with no photo has photo_url None and the key is present",
              picks[str(P_NONE)].get("photo_url") is None and "photo_url" in picks[str(P_NONE)])
        check("ballot: positions and names are unchanged",
              [p["position"] for p in b["picks"]] == [1, 2, 3] and b["voter"] == "Voter Vee")

        # A ballot cast by a typed-in name (no player record) has no voter photo.
        from app.models.db import VoteBallot, VoteBallotPick
        nb = VoteBallot(id=uuid.uuid4(), organisation_id=ORG, fixture_id=FX, medal_id=medal_id,
                        voter_player_id=None, voter_name="Coach Carl", voter_kind="non_player", source="admin")
        db.add(nb)
        await db.flush()
        db.add(VoteBallotPick(ballot_id=nb.id, position=1, player_id=P_PHOTO2))
        await db.commit()
        detail2 = await votes_router.fixture_detail(str(FX), medal_id=str(medal_id), db=db, club=club, user=FakeUser())
        carl = next(x for x in detail2["ballots"] if x["voter"] == "Coach Carl")
        check("ballot: a typed-in voter has voter_photo_url None", carl.get("voter_photo_url") is None
              and "voter_photo_url" in carl)
        check("ballot: that ballot's pick still carries its photo", carl["picks"][0].get("photo_url") == URL_B)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
