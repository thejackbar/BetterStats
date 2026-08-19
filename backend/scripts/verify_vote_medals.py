"""Verification for vote medals (migration 267) against a real Postgres.

Runs the SHIPPED statements and the SHIPPED service/route functions — not a
replay of their logic — over a populated pre-267 schema, so the things that
actually go wrong here (a backfill that duplicates on re-run, a unique index
that still keys on the fixture alone, a leaderboard that counts two medals'
ballots into one total) fail loudly rather than reading as fine.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_medals.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DSN = os.environ["DATABASE_URL"]

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


# ── Schema ──────────────────────────────────────────────────────────────────
# Everything EXCEPT the vote tables is built from the ORM models, never by hand
# — a hand-written test schema that spells a column differently is how a whole
# suite passes against a shared mistake (see the bowling_spells.runs note in
# CLAUDE.md). The five vote tables are the exception, and have to be: they must
# start in their PRE-267 shape for the migration to have anything to do.

PRE_267 = [
    """CREATE TABLE vote_settings (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT false,
        link_token TEXT,
        require_pin BOOLEAN NOT NULL DEFAULT true,
        voter_mode TEXT NOT NULL DEFAULT 'players',
        ballot_values JSONB NOT NULL DEFAULT '[3,2,1]'::jsonb,
        counting_method TEXT NOT NULL DEFAULT 'rank',
        tie_policy TEXT NOT NULL DEFAULT 'share',
        allow_self_vote BOOLEAN NOT NULL DEFAULT false,
        allow_non_participants BOOLEAN NOT NULL DEFAULT false,
        auto_close_days INTEGER NOT NULL DEFAULT 7,
        eligibility_source TEXT NOT NULL DEFAULT 'scorecard',
        updated_at TIMESTAMPTZ DEFAULT now())""",
    "CREATE UNIQUE INDEX uq_vote_settings_link_token ON vote_settings(link_token) WHERE link_token IS NOT NULL",
    """CREATE TABLE vote_ballots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
        voter_player_id UUID REFERENCES players(id) ON DELETE CASCADE,
        voter_name TEXT,
        voter_kind TEXT NOT NULL DEFAULT 'player',
        source TEXT NOT NULL DEFAULT 'self',
        recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now())""",
    "CREATE UNIQUE INDEX uq_vote_ballot_player ON vote_ballots(fixture_id, voter_player_id) WHERE voter_player_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_vote_ballot_name ON vote_ballots(fixture_id, lower(voter_name)) WHERE voter_player_id IS NULL AND voter_name IS NOT NULL",
    """CREATE TABLE vote_ballot_picks (
        ballot_id UUID NOT NULL REFERENCES vote_ballots(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        PRIMARY KEY (ballot_id, position),
        UNIQUE (ballot_id, player_id))""",
    """CREATE TABLE vote_fixture_overrides (
        fixture_id UUID PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        status TEXT,
        eligibility_source TEXT,
        set_by UUID REFERENCES users(id) ON DELETE SET NULL,
        set_at TIMESTAMPTZ DEFAULT now())""",
    """CREATE TABLE vote_nudges (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        sent_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
]


async def build_schema(conn) -> None:
    from app.models.db import Base
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    non_vote = [t for name, t in Base.metadata.tables.items() if not name.startswith("vote_")]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=non_vote))
    for stmt in PRE_267:
        await conn.execute(text(stmt))


ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
SEASON = uuid.uuid4()
SENIOR = uuid.uuid4()      # grade
COLTS = uuid.uuid4()       # grade
SEASON_NEXT = uuid.uuid4()
SENIOR_NEXT_SEASON = uuid.uuid4()
COLTS_NEXT_SEASON = uuid.uuid4()
USER = uuid.uuid4()
TODAY = date.today()
# Anchor inside one AU season year (Jul→Jun) so season_window can't split them.
PLAYED = date(TODAY.year if TODAY.month >= 7 else TODAY.year - 1, 10, 1)

PLAYERS = [uuid.uuid4() for _ in range(6)]
# Two fixtures: one senior, one colts, same round, both played.
FX_SENIOR, FX_COLTS = uuid.uuid4(), uuid.uuid4()
GAME_SENIOR, GAME_COLTS = uuid.uuid4(), uuid.uuid4()
OLD_TOKEN = "legacy-club-wide-token"


async def seed(db) -> None:
    """Seed through the ORM models, not raw INSERTs — the real tables carry
    NOT NULL columns whose defaults live in Python, so a hand-written INSERT
    that names only the interesting columns fails on the boring ones."""
    from app.models.db import (
        Fixture, GameAppearance, Game, Grade, Organisation, Player, Season, User,
    )
    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross"))
    db.add(Organisation(id=OTHER_ORG, name="Other CC", short_name="OCC", slug="other"))
    db.add(User(id=USER, username="admin", email="admin@example.com", password_hash="x"))
    db.add(Season(id=SEASON, organisation_id=ORG, name="Summer", year=PLAYED.year))
    for gid, nm in ((SENIOR, "1st Grade"), (COLTS, "Colts")):
        db.add(Grade(id=gid, season_id=SEASON, name=nm))
    # Next season's rows: same names, brand-new ids — the shape that would
    # silently break a medal matching on stored ids alone.
    db.add(Season(id=SEASON_NEXT, organisation_id=ORG, name="Summer next", year=PLAYED.year + 1))
    for gid, nm in ((SENIOR_NEXT_SEASON, "1st Grade"), (COLTS_NEXT_SEASON, "Colts")):
        db.add(Grade(id=gid, season_id=SEASON_NEXT, name=nm))
    for n, pid in enumerate(PLAYERS):
        db.add(Player(id=pid, organisation_id=ORG, name=f"Player {n}", email=f"p{n}@example.com"))
    await db.flush()
    for gid, grade in ((GAME_SENIOR, SENIOR), (GAME_COLTS, COLTS)):
        db.add(Game(id=gid, grade_id=grade))
    for fid, gid, opp in ((FX_SENIOR, GAME_SENIOR, "Melville"), (FX_COLTS, GAME_COLTS, "Melville Colts")):
        # playhq_id carries the real match GUID — Fixture.id is a minted uuid4,
        # so match_ref_id() is what ties a fixture to its synced game.
        db.add(Fixture(id=fid, organisation_id=ORG, playhq_id=str(gid), opponent_name=opp,
                       round="5", played_on=PLAYED, end_on=PLAYED, home_away="H"))
    db.add(Fixture(id=uuid.uuid4(), organisation_id=OTHER_ORG, opponent_name="X",
                   round="1", played_on=PLAYED, end_on=PLAYED, home_away="H"))
    await db.flush()
    # Everyone played both games, so eligibility is never the reason a count
    # is short — this suite is about medals, not about who turned out.
    for gid in (GAME_SENIOR, GAME_COLTS):
        for pid in PLAYERS:
            db.add(GameAppearance(game_id=gid, player_id=pid, is_captain=False))
    await db.commit()


async def main() -> None:
    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await build_schema(conn)

    async with Session() as db:
        await seed(db)

    # A club already voting: settings + a link already shared + ballots already
    # cast, on both grades' fixtures. Raw SQL here on purpose — these rows have
    # to be written in the PRE-267 shape the ORM no longer describes.
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO vote_settings (organisation_id, enabled, link_token, "
                 "ballot_values, counting_method, auto_close_days, eligibility_source) "
                 "VALUES (:o, true, :t, '[3,2,1]'::jsonb, 'rank', 400, 'scorecard')"),
            {"o": ORG, "t": OLD_TOKEN},
        )
        for fid in (FX_SENIOR, FX_COLTS):
            for voter in PLAYERS[:3]:
                bid = uuid.uuid4()
                await conn.execute(
                    text("INSERT INTO vote_ballots (id, organisation_id, fixture_id, voter_player_id) "
                         "VALUES (:b,:o,:f,:v)"),
                    {"b": bid, "o": ORG, "f": fid, "v": voter},
                )
                for pos, pick in enumerate(PLAYERS[3:6], start=1):
                    await conn.execute(
                        text("INSERT INTO vote_ballot_picks (ballot_id, position, player_id) "
                             "VALUES (:b,:p,:pl)"),
                        {"b": bid, "p": pos, "pl": pick},
                    )
        await conn.execute(
            text("INSERT INTO vote_fixture_overrides (fixture_id, organisation_id, status) "
                 "VALUES (:f,:o,'reopened')"),
            {"f": FX_SENIOR, "o": ORG},
        )
        await conn.execute(
            text("INSERT INTO vote_nudges (organisation_id, fixture_id, player_id) VALUES (:o,:f,:p)"),
            {"o": ORG, "f": FX_SENIOR, "p": PLAYERS[4]},
        )

    from app.services.vote_medal_ddl import VOTE_MEDAL_STATEMENTS

    # ── Migration applied three times (the lifespan re-runs it every boot) ──
    for run in (1, 2, 3):
        async with engine.begin() as conn:
            for stmt in VOTE_MEDAL_STATEMENTS:
                await conn.execute(text(stmt))
        async with engine.connect() as conn:
            n = (await conn.execute(text(
                "SELECT count(*) FROM vote_medals WHERE organisation_id = :o"), {"o": ORG})).scalar()
            check(f"run {run}: exactly one medal backfilled (no duplicate on re-run)", n == 1, f"got {n}")

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT name, link_token, enabled, auto_close_days, ballot_values, grade_ids "
            "FROM vote_medals WHERE organisation_id = :o"), {"o": ORG})).first()
        check("migrated medal keeps the club's existing link token", row[1] == OLD_TOKEN, str(row[1]))
        check("migrated medal carries the club's settings across",
              row[2] is True and row[3] == 400 and row[4] == [3, 2, 1], str(row))
        check("migrated medal counts EVERY grade (empty grade_ids)", row[5] == [], str(row[5]))

        n = (await conn.execute(text("SELECT count(*) FROM vote_ballots WHERE medal_id IS NULL"))).scalar()
        check("every existing ballot was attached to the migrated medal", n == 0, f"{n} orphaned")
        n = (await conn.execute(text(
            "SELECT count(*) FROM vote_fixture_overrides WHERE medal_id IS NULL"))).scalar()
        check("every existing override was attached", n == 0, f"{n} orphaned")
        n = (await conn.execute(text("SELECT count(*) FROM vote_nudges WHERE medal_id IS NULL"))).scalar()
        check("every existing nudge was attached", n == 0, f"{n} orphaned")

        pk = (await conn.execute(text(
            "SELECT string_agg(a.attname, ',' ORDER BY a.attname) FROM pg_index i "
            "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = 'vote_fixture_overrides'::regclass AND i.indisprimary"))).scalar()
        check("override primary key is now (medal_id, fixture_id)", pk == "fixture_id,medal_id", str(pk))
        old = (await conn.execute(text(
            "SELECT count(*) FROM pg_indexes WHERE indexname IN "
            "('uq_vote_ballot_player','uq_vote_ballot_name')"))).scalar()
        check("the old per-fixture ballot uniques are gone", old == 0, f"{old} left")

    # ── The medal-scoped unique actually holds, and actually allows two ─────
    async with engine.begin() as conn:
        medal_a = (await conn.execute(text(
            "SELECT id FROM vote_medals WHERE organisation_id = :o"), {"o": ORG})).scalar()
        medal_b = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO vote_medals (id, organisation_id, name, grade_ids, position, enabled, link_token) "
                 "VALUES (:i,:o,'Colts Medal',:g,1,true,'colts-token')"),
            {"i": medal_b, "o": ORG, "g": f'["{COLTS}"]'},
        )
        # Same voter, same fixture, DIFFERENT medal — must be allowed.
        await conn.execute(
            text("INSERT INTO vote_ballots (organisation_id, medal_id, fixture_id, voter_player_id) "
                 "VALUES (:o,:m,:f,:v)"),
            {"o": ORG, "m": medal_b, "f": FX_COLTS, "v": PLAYERS[0]},
        )
    check("one voter can hold a ballot for two medals on the same fixture", True)

    dup_rejected = False
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO vote_ballots (organisation_id, medal_id, fixture_id, voter_player_id) "
                     "VALUES (:o,:m,:f,:v)"),
                {"o": ORG, "m": medal_b, "f": FX_COLTS, "v": PLAYERS[0]},
            )
    except Exception:
        dup_rejected = True
    check("a second ballot for the SAME voter/fixture/medal is still refused", dup_rejected)

    # ── Now the shipped service functions ──────────────────────────────────
    from app.services import votes as vote_svc

    async with Session() as db:
        medals = await vote_svc.list_medals(db, ORG)
        check("list_medals returns both, in the club's own order",
              [m.name for m in medals] == ["Club Champion", "Colts Medal"],
              str([m.name for m in medals]))

        m_champ, m_colts = medals[0], medals[1]

        check("resolve_medal with no id falls back to the club's first medal",
              (await vote_svc.resolve_medal(db, ORG)).id == m_champ.id)
        check("a medal id from another club never resolves",
              await vote_svc.get_medal(db, OTHER_ORG, str(m_champ.id)) is None)
        check("a junk medal id resolves to nothing rather than raising",
              await vote_svc.get_medal(db, ORG, "not-a-uuid") is None)
        check("medal_by_token finds the medal behind the club's old link",
              (await vote_svc.medal_by_token(db, OLD_TOKEN)).id == m_champ.id)

        allow_champ = await vote_svc.medal_grade_ids(db, ORG, m_champ)
        allow_colts = await vote_svc.medal_grade_ids(db, ORG, m_colts)
        check("an all-grades medal covers a fixture in any grade",
              allow_champ is None and vote_svc.medal_covers(allow_champ, SENIOR))
        check("a grade-restricted medal covers only its own grades",
              vote_svc.medal_covers(allow_colts, COLTS) and not vote_svc.medal_covers(allow_colts, SENIOR))
        check("a fixture whose grade can't be resolved is left OUT of a restricted medal",
              not vote_svc.medal_covers(allow_colts, None))
        check("...but IS counted by an all-grades medal",
              vote_svc.medal_covers(allow_champ, None))
        # The reason a medal stores names-behind-ids: next season's "Colts" is
        # a different grades row, and a medal must not stop counting on 1 July.
        check("a grade-restricted medal picks up NEXT season's grade of the same name",
              vote_svc.medal_covers(allow_colts, COLTS_NEXT_SEASON),
              f"{allow_colts} missing {COLTS_NEXT_SEASON}")
        check("...and still doesn't pick up another grade in that season",
              not vote_svc.medal_covers(allow_colts, SENIOR_NEXT_SEASON))
        opts = await vote_svc.club_grade_options(db, ORG)
        check("the grade picker offers each grade NAME once, not once per season",
              sorted(o["name"] for o in opts) == ["1st Grade", "Colts"], str(opts))
        names = await vote_svc.medal_grade_names(db, ORG, [m_colts])
        check("a medal reports the grade names behind its stored ids",
              names[str(m_colts.id)] == ["Colts"], str(names))
        check("clean_grade_ids drops junk rather than storing it",
              vote_svc.clean_grade_ids([str(SENIOR), "nope", str(SENIOR)]) == [str(SENIOR)])

        cfg_champ = vote_svc.effective_config(m_champ)
        cfg_colts = vote_svc.effective_config(m_colts)
        check("effective_config reads a medal with no edit (settings carried over)",
              cfg_champ["auto_close_days"] == 400 and cfg_champ["ballot_values"] == [3, 2, 1])
        check("effective_config names the medal", cfg_colts["medal_name"] == "Colts Medal")

        # ── The count itself ───────────────────────────────────────────────
        board_champ = await vote_svc.build_leaderboard(
            db, ORG, cfg_champ, vote_svc.season_year_for(PLAYED), medal=m_champ)
        board_colts = await vote_svc.build_leaderboard(
            db, ORG, cfg_colts, vote_svc.season_year_for(PLAYED), medal=m_colts)

        champ_fx = {f["id"] for rd in board_champ["rounds"] for f in rd["fixtures"]}
        colts_fx = {f["id"] for rd in board_colts["rounds"] for f in rd["fixtures"]}
        check("the all-grades medal's board covers both fixtures",
              champ_fx == {str(FX_SENIOR), str(FX_COLTS)}, str(champ_fx))
        check("the Colts medal's board covers only its own grade's fixture",
              colts_fx == {str(FX_COLTS)}, str(colts_fx))

        champ_total = sum(s["points"] for s in board_champ["standings"])
        colts_total = sum(s["points"] for s in board_colts["standings"])
        # Club Champion: 3 voters × 3-2-1 on 2 fixtures. Colts: 1 voter, 0 picks.
        check("the Club Champion count sums only its OWN ballots",
              champ_total == 12, f"got {champ_total}")
        check("the Colts count is not inflated by the other medal's ballots",
              colts_total == 0, f"got {colts_total}")
        check("each board reports which medal it is",
              board_champ["medal_name"] == "Club Champion" and board_colts["medal_name"] == "Colts Medal")

        # ── Per-medal overrides and nudge cooldown ─────────────────────────
        ov = await vote_svc.get_override(db, m_champ.id, FX_SENIOR)
        check("the migrated override belongs to the migrated medal", ov is not None and ov.status == "reopened")
        check("the other medal has no override on that fixture",
              await vote_svc.get_override(db, m_colts.id, FX_SENIOR) is None)

        recent_champ = await vote_svc.recently_nudged(db, m_champ.id, FX_SENIOR, [PLAYERS[4]])
        recent_colts = await vote_svc.recently_nudged(db, m_colts.id, FX_SENIOR, [PLAYERS[4]])
        check("a nudge counts against its own medal's cooldown", str(PLAYERS[4]) in recent_champ)
        check("...and does not suppress the other medal's reminder", not recent_colts)

        counts_champ = await vote_svc.player_ballot_counts(db, ORG, [FX_COLTS], m_champ.id)
        counts_colts = await vote_svc.player_ballot_counts(db, ORG, [FX_COLTS], m_colts.id)
        check("voted-already counts are per medal",
              counts_champ.get(str(FX_COLTS)) == 3 and counts_colts.get(str(FX_COLTS)) == 1,
              f"{counts_champ} / {counts_colts}")

    # ── The route bodies ───────────────────────────────────────────────────
    from app.routers import votes as votes_router

    class FakeClub:
        id = ORG
        name = "Applecross CC"
        short_name = "ACC"

    class FakeUser:
        id = USER

    async with Session() as db:
        club, user = FakeClub(), FakeUser()

        created = await votes_router.create_medal(
            votes_router.MedalUpdate(name="  Coaches Award  ", ballot_values=[5, 4, 3, 2, 1],
                                     counting_method="tally", grade_ids=[str(SENIOR)]),
            db=db, club=club, user=user)
        check("create_medal trims the name", created["medal_name"] == "Coaches Award")
        check("a new medal starts from defaults, not a copy of the first",
              created["auto_close_days"] == 7, str(created["auto_close_days"]))
        check("a new medal keeps its own ballot shape",
              created["ballot_values"] == [5, 4, 3, 2, 1] and created["counting_method"] == "tally")
        check("a new medal has no public link until it is enabled", created["token"] is None)

        enabled = await votes_router.update_medal(
            created["medal_id"], votes_router.MedalUpdate(enabled=True), db=db, club=club, user=user)
        check("enabling a medal mints its own link token",
              bool(enabled["token"]) and enabled["token"] != OLD_TOKEN)

        cleared = await votes_router.update_medal(
            created["medal_id"], votes_router.MedalUpdate(grade_ids=[]), db=db, club=club, user=user)
        check("clearing grade_ids means every grade, not none", cleared["grade_ids"] == [])

        renamed = await votes_router.update_medal(
            created["medal_id"], votes_router.MedalUpdate(name="Coach's Award"), db=db, club=club, user=user)
        check("renaming a medal leaves its other settings alone",
              renamed["ballot_values"] == [5, 4, 3, 2, 1] and renamed["grade_ids"] == [])

        for bad, field in ((votes_router.MedalUpdate(voter_mode="nope"), "voter mode"),
                           (votes_router.MedalUpdate(counting_method="nope"), "counting method"),
                           (votes_router.MedalUpdate(eligibility_source="nope"), "eligibility source"),
                           (votes_router.MedalUpdate(auto_close_days=0), "auto-close"),
                           (votes_router.MedalUpdate(ballot_values=[]), "empty ballot"),
                           (votes_router.MedalUpdate(name="   "), "blank name")):
            rejected = False
            try:
                await votes_router.update_medal(created["medal_id"], bad, db=db, club=club, user=user)
            except Exception:
                rejected = True
                await db.rollback()
            check(f"an invalid {field} is rejected", rejected)

        listed = await votes_router.list_medals(db=db, club=club, user=user)
        check("list_medals endpoint returns all three", len(listed["medals"]) == 3, str(len(listed["medals"])))

        # Deleting: guarded on ballots, and never the last one.
        refused = False
        try:
            await votes_router.delete_medal(str((await vote_svc.list_medals(db, ORG))[0].id),
                                            confirm=False, db=db, club=club, user=user)
        except Exception as e:
            refused = "ballot" in str(getattr(e, "detail", e)).lower()
            await db.rollback()
        check("deleting a medal with ballots is refused without confirmation", refused)

        gone = await votes_router.delete_medal(created["medal_id"], confirm=False,
                                               db=db, club=club, user=user)
        check("a medal with no ballots deletes cleanly", gone["status"] == "ok")

    async with Session() as db:
        club, user = FakeClub(), FakeUser()
        # Drop to one medal, then check the last-medal guard.
        colts = [m for m in await vote_svc.list_medals(db, ORG) if m.name == "Colts Medal"][0]
        await votes_router.delete_medal(str(colts.id), confirm=True, db=db, club=club, user=user)
        last = False
        try:
            remaining = (await vote_svc.list_medals(db, ORG))[0]
            await votes_router.delete_medal(str(remaining.id), confirm=True, db=db, club=club, user=user)
        except Exception as e:
            last = "at least one" in str(getattr(e, "detail", e)).lower()
            await db.rollback()
        check("a club's last medal can't be deleted", last)

        n = (await db.execute(text("SELECT count(*) FROM vote_ballots WHERE medal_id = :m"),
                              {"m": colts.id})).scalar()
        check("deleting a medal takes its own ballots with it", n == 0, f"{n} left")
        n = (await db.execute(text("SELECT count(*) FROM vote_ballots WHERE organisation_id = :o"),
                              {"o": ORG})).scalar()
        check("...and leaves the other medal's ballots untouched", n == 6, f"got {n}")

        # A named medal that doesn't exist is a 404, not a silent fallback.
        notfound = False
        try:
            await votes_router._resolve_medal_or_404(db, club, str(uuid.uuid4()))
        except Exception as e:
            notfound = getattr(e, "status_code", None) == 404
        check("a stale medal id 404s rather than counting a different award", notfound)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
