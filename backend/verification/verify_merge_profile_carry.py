"""A merge must keep the person, not only their cricket.

Reported at Applecross: two freshly added players showed up as duplicates, and
merging them "wiped their data / photos". The merge kept the synced record (the
one with the games) and deleted the roster record, which is the one that holds
the headshot, contact details, date of birth, squad and availability. None of it
was carried.

Runs the SHIPPED `_merge_players_core` and `undo_merge` against a real Postgres.
Nothing here replays their logic. Run it on its own database (its stub tables
differ from the other merge suites'):

    createdb -h /tmp -p 5599 -U postgres bettercricket_profile
    DATABASE_URL=postgresql+asyncpg://postgres@/bettercricket_profile?host=/tmp&port=5599 \\
        python verification/verify_merge_profile_carry.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base
from fastapi import HTTPException

from app.routers.admin import _merge_players_core, undo_merge, UndoMergeRequest
from app.routers.images import get_player_hero_photo, get_player_photo

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/bettercricket_profile?host=/tmp&port=5599",
)
PASS, FAIL = [], []

# Lifespan-created in raw SQL, so create_all never makes them.
EXTRA_DDL = (
    """
    CREATE TABLE IF NOT EXISTS merge_logs (
        id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
        keep_player_id UUID, keep_player_name TEXT,
        removed_player_id UUID, removed_player_name TEXT,
        removed_player_playhq_id TEXT, keep_original_playhq_id TEXT,
        moved_season_stat_ids JSONB DEFAULT '[]', batting_innings_ids JSONB DEFAULT '[]',
        bowling_spell_ids JSONB DEFAULT '[]', fielding_stat_ids JSONB DEFAULT '[]',
        fall_of_wicket_ids JSONB DEFAULT '[]', batter1_partnership_ids JSONB DEFAULT '[]',
        batter2_partnership_ids JSONB DEFAULT '[]', milestone_ids JSONB DEFAULT '[]',
        bowler_wicket_ids JSONB DEFAULT '[]', fielder_wicket_ids JSONB DEFAULT '[]',
        grade_stat_ids JSONB DEFAULT '[]', appearance_game_ids JSONB DEFAULT '[]',
        imported_stat_ids JSONB DEFAULT '[]',
        carried_row_ids JSONB DEFAULT '{}', removed_cricketstatz_player_id TEXT,
        undone_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_achievements (
        id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID,
        player_name TEXT NOT NULL, season TEXT, season_end TEXT,
        category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
        detail TEXT, import_batch_id UUID, created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY, org_id UUID, user_id UUID, action TEXT,
        target_type TEXT, target_id TEXT, details JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
)

ORG = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001")
KEEP = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000a")   # synced: the games, a PlayHQ id
REMOVE = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000b")  # roster: the person's details
TEAM_A = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000a1")
TEAM_B = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000a2")
FIXTURE = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000f1")
SESSION = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000e1")
PHOTO = b"\x89PNG-headshot-bytes"
HERO = b"\x89PNG-action-shot-bytes"
KEEP_HERO = b"\x89PNG-keeper-own-action-shot"


class FakeUser:
    id = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000ff")
    username = "verifier"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


async def seed(db) -> None:
    await db.execute(text("""
        INSERT INTO organisations (id, name, slug, is_active)
        VALUES (:o, 'Applecross Cricket Club', 'applecross-verify', true)
    """), {"o": str(ORG)})
    await db.execute(text("""
        INSERT INTO teams (id, organisation_id, name) VALUES
            (:a, :o, '1st XI'), (:b, :o, '2nd XI')
    """), {"a": str(TEAM_A), "b": str(TEAM_B), "o": str(ORG)})

    # The synced record: has the PlayHQ id, so the merge screen defaults to
    # keeping it. It holds a hero photo and a phone number of its own.
    await db.execute(text("""
        INSERT INTO players (id, organisation_id, name, playhq_id, phone,
                             hero_photo_data, hero_photo_mime)
        VALUES (:k, :o, 'Acharige, Pasindu', 'phq-123', '0400 000 111', :hero, 'image/png')
    """), {"k": str(KEEP), "o": str(ORG), "hero": KEEP_HERO})

    # The roster record: no games, but the person's details.
    await db.execute(text("""
        INSERT INTO players (id, organisation_id, name, photo_url, photo_data, photo_mime,
                             hero_photo_data, hero_photo_mime, email, phone,
                             date_of_birth, shirt_number, squad_team_id, batting_hand,
                             skill_positions, player_role)
        VALUES (:r, :o, 'Pasindu Acharige', CAST(:purl AS text),
                :photo, 'image/jpeg', :hero, 'image/png', 'pasindu@example.com', '0400 999 999',
                CAST('2001-04-05' AS date), '77', :team, 'RIGHT',
                CAST('["BAT","WKT"]' AS jsonb), 'Batter')
    """), {"r": str(REMOVE), "o": str(ORG), "purl": f"/api/images/players/{REMOVE}/photo?v=ab12cd34", "photo": PHOTO, "hero": HERO, "team": str(TEAM_A)})

    # Availability: one date only the roster record has, one both have.
    for pid, d in ((REMOVE, date(2026, 10, 10)), (REMOVE, date(2026, 10, 17)),
                   (KEEP, date(2026, 10, 17))):
        await db.execute(text("""
            INSERT INTO player_availability (organisation_id, player_id, avail_date, status)
            VALUES (:o, :p, :d, 'AVAILABLE')
        """), {"o": str(ORG), "p": str(pid), "d": d})
    await db.execute(text("""
        INSERT INTO player_availability_periods (organisation_id, player_id, start_date, status, reason)
        VALUES (:o, :p, CAST('2026-12-20' AS date), 'UNAVAILABLE', 'Holiday')
    """), {"o": str(ORG), "p": str(REMOVE)})

    # Squads: the roster record is in both teams, the synced one in the second.
    for team, pid in ((TEAM_A, REMOVE), (TEAM_B, REMOVE), (TEAM_B, KEEP)):
        await db.execute(text("""
            INSERT INTO team_members (team_id, player_id, organisation_id)
            VALUES (:t, :p, :o)
        """), {"t": str(team), "p": str(pid), "o": str(ORG)})

    await db.execute(text("""
        INSERT INTO fixtures (id, organisation_id, source, status)
        VALUES (:f, :o, 'manual', 'UPCOMING')
    """), {"f": str(FIXTURE), "o": str(ORG)})
    await db.execute(text("""
        INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id, batting_order)
        VALUES (:f, :p, :o, 3)
    """), {"f": str(FIXTURE), "p": str(REMOVE), "o": str(ORG)})

    await db.execute(text("""
        INSERT INTO net_sessions (id, organisation_id, session_date)
        VALUES (:s, :o, CAST('2026-09-24' AS date))
    """), {"s": str(SESSION), "o": str(ORG)})
    await db.execute(text("""
        INSERT INTO net_attendance (id, session_id, organisation_id, player_id, batted)
        VALUES (gen_random_uuid(), :s, :o, :p, true)
    """), {"s": str(SESSION), "o": str(ORG), "p": str(REMOVE)})

    # The club's member record: linked to the roster player, with a payment
    # history somebody decided on. Must stay linked to the person after a merge.
    await db.execute(text("""
        INSERT INTO fee_members (id, organisation_id, player_id, full_name, email)
        VALUES (gen_random_uuid(), :o, :p, 'Pasindu Acharige', 'pasindu@example.com')
    """), {"o": str(ORG), "p": str(REMOVE)})
    await db.execute(text("""
        INSERT INTO comms_contacts (id, organisation_id, email, name, source, player_id)
        VALUES (gen_random_uuid(), :o, 'pasindu@example.com', 'Pasindu Acharige', 'player', :p)
    """), {"o": str(ORG), "p": str(REMOVE)})
    await db.execute(text("""
        INSERT INTO player_name_aliases (id, organisation_id, player_id, alias_name, alias_key, source)
        VALUES (gen_random_uuid(), :o, :p, 'Pas Acharige', 'acharige pas', 'manual')
    """), {"o": str(ORG), "p": str(REMOVE)})
    await db.commit()


async def one(db, sql: str, **params):
    return (await db.execute(text(sql), params)).mappings().first()


async def scalar(db, sql: str, **params):
    return (await db.execute(text(sql), params)).scalar()


def image_url_owner(url):
    from app.services.merge_profile import image_url_owner as f
    return f(url)


async def fetch(route, url, session_maker):
    """Follow a stored photo address the way a browser does: take the id out of it
    and call the shipped image route. Returns the bytes, or 'HTTP <code>'."""
    pid = (url or "").split("/")[4] if (url or "").count("/") >= 5 else ""
    async with session_maker() as db:
        try:
            resp = await route(pid, db)
        except HTTPException as e:
            return f"HTTP {e.status_code}"
    return bytes(resp.body)


async def main() -> int:
    engine = create_async_engine(DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for statement in EXTRA_DDL:
            await conn.execute(text(statement))

    async with session_maker() as db:
        await seed(db)

    # The setup must be one the bug can show in: the roster record really does
    # hold a photo, and the synced one really has none.
    async with session_maker() as db:
        r = await one(db, "SELECT photo_data, email, date_of_birth FROM players WHERE id = :p", p=str(REMOVE))
        k = await one(db, "SELECT photo_data, email, date_of_birth FROM players WHERE id = :p", p=str(KEEP))
    print("\nThe setup")
    check("the roster record holds a photo, email and date of birth",
          bool(r["photo_data"]) and r["email"] and r["date_of_birth"] is not None)
    check("the synced record holds none of them", not k["photo_data"] and not k["email"] and k["date_of_birth"] is None)

    async with session_maker() as db:
        result = await _merge_players_core(db, KEEP, REMOVE, ORG, FakeUser())

    print("\nMerging the roster record into the synced one")
    async with session_maker() as db:
        p = await one(db, """
            SELECT photo_url, photo_data, photo_mime, hero_photo_data, email, phone,
                   date_of_birth, shirt_number, squad_team_id, batting_hand,
                   skill_positions, player_role, playhq_id
              FROM players WHERE id = :p""", p=str(KEEP))
        gone = await scalar(db, "SELECT COUNT(*) FROM players WHERE id = :p", p=str(REMOVE))
    check("the duplicate record is gone", gone == 0)
    check("the headshot is on the kept player", bytes(p["photo_data"] or b"") == PHOTO, repr(p["photo_data"]))
    check("with its type, as one picture", p["photo_mime"] == "image/jpeg")
    # The address names a player. Copied as-is it names the one just deleted, and
    # every screen then asks for a picture that has no row: 404, "photo wiped".
    check("its address names the kept player, not the deleted one",
          image_url_owner(p["photo_url"]) == str(KEEP), str(p["photo_url"]))
    served = await fetch(get_player_photo, p["photo_url"], session_maker)
    check("and the address, followed through the real image route, serves the picture",
          served == PHOTO, repr(served))
    check("email carried", p["email"] == "pasindu@example.com")
    check("date of birth carried", p["date_of_birth"] == date(2001, 4, 5))
    check("shirt number carried", p["shirt_number"] == "77")
    check("squad carried", p["squad_team_id"] == TEAM_A)
    check("batting hand and role carried", p["batting_hand"] == "RIGHT" and p["player_role"] == "Batter")
    check("positions carried", p["skill_positions"] == ["BAT", "WKT"], str(p["skill_positions"]))
    check("the keeper's own phone is not overwritten", p["phone"] == "0400 000 111", str(p["phone"]))
    check("nor its own action shot", bytes(p["hero_photo_data"] or b"") == KEEP_HERO)
    check("the keeper keeps its PlayHQ id", p["playhq_id"] == "phq-123")
    check("the merge says what it filled",
          bool(result.get("kept_player_id")))

    async with session_maker() as db:
        avail = await scalar(db, "SELECT COUNT(*) FROM player_availability WHERE player_id = :p", p=str(KEEP))
        periods = await scalar(db, "SELECT COUNT(*) FROM player_availability_periods WHERE player_id = :p", p=str(KEEP))
        teams = await scalar(db, "SELECT COUNT(*) FROM team_members WHERE player_id = :p", p=str(KEEP))
        lineup = await scalar(db, "SELECT COUNT(*) FROM fixture_lineups WHERE player_id = :p", p=str(KEEP))
        nets = await scalar(db, "SELECT COUNT(*) FROM net_attendance WHERE player_id = :p", p=str(KEEP))
        member = await scalar(db, "SELECT COUNT(*) FROM fee_members WHERE player_id = :p", p=str(KEEP))
        contact = await scalar(db, "SELECT COUNT(*) FROM comms_contacts WHERE player_id = :p", p=str(KEEP))
        alias = await scalar(db, "SELECT COUNT(*) FROM player_name_aliases WHERE player_id = :p AND alias_key = 'acharige pas'", p=str(KEEP))
    check("availability: the date only the roster record had, and the shared one once", avail == 2, str(avail))
    check("an availability window", periods == 1, str(periods))
    check("both squads (the shared one once)", teams == 2, str(teams))
    check("the selected lineup spot", lineup == 1, str(lineup))
    check("nets attendance", nets == 1, str(nets))
    check("the club's member record is still linked to the person", member == 1, str(member))
    check("their contact row", contact == 1, str(contact))
    check("the spelling a live feed still resolves", alias == 1, str(alias))

    print("\nUndoing it")
    async with session_maker() as db:
        log_id = await scalar(db, "SELECT id FROM merge_logs WHERE org_id = :o ORDER BY id DESC LIMIT 1", o=str(ORG))
    async with session_maker() as db:
        await undo_merge(UndoMergeRequest(merge_log_id=log_id, org_id=str(ORG)), db, FakeUser())
    async with session_maker() as db:
        back_teams = await scalar(db, "SELECT COUNT(*) FROM team_members WHERE player_id = :p", p=str(REMOVE))
        kept_teams = await scalar(db, "SELECT COUNT(*) FROM team_members WHERE player_id = :p", p=str(KEEP))
        back_avail = await scalar(db, "SELECT COUNT(*) FROM player_availability WHERE player_id = :p", p=str(REMOVE))
        kept_avail = await scalar(db, "SELECT COUNT(*) FROM player_availability WHERE player_id = :p", p=str(KEEP))
        back_lineup = await scalar(db, "SELECT COUNT(*) FROM fixture_lineups WHERE player_id = :p", p=str(REMOVE))
        back_member = await scalar(db, "SELECT COUNT(*) FROM fee_members WHERE player_id = :p", p=str(REMOVE))
        kept_photo = await scalar(db, "SELECT photo_data FROM players WHERE id = :p", p=str(KEEP))
    check("the restored player gets their squad back, the keeper keeps its own", back_teams == 1 and kept_teams == 1,
          f"{back_teams}/{kept_teams}")
    check("and their own availability date", back_avail == 1 and kept_avail == 1, f"{back_avail}/{kept_avail}")
    check("and the lineup spot", back_lineup == 1, str(back_lineup))
    check("and the member record", back_member == 1, str(back_member))
    check("the photo stays with the keeper rather than being lost on undo",
          bytes(kept_photo or b"") == PHOTO)

    print("\nA club-to-club merge must not point a player at the other club")
    other_org = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
    other_team = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000a3")
    k2 = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000c")
    r2 = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000d")
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO organisations (id, name, slug, is_active)
            VALUES (:o, 'Other Cricket Club', 'other-verify', true)"""), {"o": str(other_org)})
        await db.execute(text("INSERT INTO teams (id, organisation_id, name) VALUES (:t, :o, 'Their 1st XI')"),
                         {"t": str(other_team), "o": str(other_org)})
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name, squad_team_id) VALUES
                (:k, :o, 'Keeper, Two', NULL), (:r, :o, 'Removed Two', :t)"""),
                         {"k": str(k2), "r": str(r2), "o": str(ORG), "t": str(other_team)})
        # Rows the removed player brought from the other club (a club merge
        # re-homes the player but not their rows), and one that is this club's.
        await db.execute(text("""
            INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t, :p, :o)"""),
                         {"t": str(other_team), "p": str(r2), "o": str(other_org)})
        await db.execute(text("""
            INSERT INTO player_availability (organisation_id, player_id, avail_date, status)
            VALUES (:o1, :p, CAST('2026-11-01' AS date), 'AVAILABLE'),
                   (:o2, :p, CAST('2026-11-08' AS date), 'AVAILABLE')"""),
                         {"o1": str(other_org), "o2": str(ORG), "p": str(r2)})
        await db.commit()
    async with session_maker() as db:
        await _merge_players_core(db, k2, r2, ORG, FakeUser())
    async with session_maker() as db:
        squad = await scalar(db, "SELECT squad_team_id FROM players WHERE id = :p", p=str(k2))
        foreign_rows = await scalar(db, """
            SELECT (SELECT COUNT(*) FROM team_members WHERE player_id = :p)
                 + (SELECT COUNT(*) FROM player_availability
                     WHERE player_id = :p AND organisation_id = :other)""", p=str(k2), other=str(other_org))
        own_rows = await scalar(db, """
            SELECT COUNT(*) FROM player_availability WHERE player_id = :p AND organisation_id = :o""",
                                p=str(k2), o=str(ORG))
    check("the other club's squad is not copied onto the player", squad is None, str(squad))
    check("none of the other club's rows follow them", foreign_rows == 0, str(foreign_rows))
    check("but the row that is this club's still does", own_rows == 1, str(own_rows))

    print("\nA member record is never deleted to settle a clash")
    # Merge again after re-linking: both players now hold a fee member.
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO fee_members (id, organisation_id, player_id, full_name)
            VALUES (gen_random_uuid(), :o, :p, 'Pasindu A (keeper)')
        """), {"o": str(ORG), "p": str(KEEP)})
        await db.commit()
    async with session_maker() as db:
        before = await scalar(db, "SELECT COUNT(*) FROM fee_members WHERE organisation_id = :o", o=str(ORG))
        await _merge_players_core(db, KEEP, REMOVE, ORG, FakeUser())
    async with session_maker() as db:
        after = await scalar(db, "SELECT COUNT(*) FROM fee_members WHERE organisation_id = :o", o=str(ORG))
        linked = await scalar(db, "SELECT COUNT(*) FROM fee_members WHERE player_id = :p", p=str(KEEP))
    check("two member records before, two after", before == 2 and after == 2, f"{before} -> {after}")
    check("the keeper's stays linked to the keeper", linked == 1, str(linked))

    print("\nA keeper holding only a dead photo address still takes the real picture")
    k3 = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000e")
    r3 = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000f")
    ghost = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000aa")
    async with session_maker() as db:
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name, photo_url) VALUES
                (:k, :o, 'Keeper, Three', CAST(:dead AS text))"""),
                         {"k": str(k3), "o": str(ORG), "dead": f"/api/images/players/{ghost}/photo?v=00000000"})
        await db.execute(text("""
            INSERT INTO players (id, organisation_id, name, photo_url, photo_data, photo_mime,
                                 hero_photo_url, hero_photo_data, hero_photo_mime)
            VALUES (:r, :o, 'Removed Three', CAST(:u AS text), :p, 'image/png', CAST(:h AS text), :hd, 'image/png')"""),
                         {"r": str(r3), "o": str(ORG), "p": PHOTO, "hd": HERO,
                          "u": f"/api/images/players/{r3}/photo?v=11111111",
                          "h": f"/api/images/players/{r3}/hero-photo?v=22222222"})
        await db.commit()
    async with session_maker() as db:
        await _merge_players_core(db, k3, r3, ORG, FakeUser())
    async with session_maker() as db:
        p3 = await one(db, "SELECT photo_url, hero_photo_url FROM players WHERE id = :p", p=str(k3))
    check("the dead address did not count as a picture",
          await fetch(get_player_photo, p3["photo_url"], session_maker) == PHOTO, str(p3["photo_url"]))
    check("the action shot's address was rebuilt for the keeper too",
          await fetch(get_player_hero_photo, p3["hero_photo_url"], session_maker) == HERO, str(p3["hero_photo_url"]))

    print("\nThe repair script fixes photos a merge already broke, and only those")
    from app.scripts.repair_player_photo_urls import run as repair
    broken, lost, fine = (uuid.UUID(f"bbbbbbbb-0000-4000-8000-0000000000b{i}") for i in (1, 2, 3))
    gone = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000bb")
    async with session_maker() as db:
        for pid, name, url, data, hero_url, hero_data in (
            (broken, "Broken Photo", f"/api/images/players/{gone}/photo?v=aaaaaaaa", PHOTO,
             f"/api/images/players/{gone}/hero-photo?v=bbbbbbbb", HERO),
            (lost, "Lost Photo", f"/api/images/players/{gone}/photo?v=cccccccc", None, None, None),
            (fine, "Fine Photo", f"/api/images/players/{fine}/photo?v=dddddddd", PHOTO, None, None),
        ):
            await db.execute(text("""
                INSERT INTO players (id, organisation_id, name, photo_url, photo_data, photo_mime,
                                     hero_photo_url, hero_photo_data, hero_photo_mime)
                VALUES (:i, :o, :n, CAST(:u AS text), :d, 'image/png', CAST(:hu AS text), :hd, 'image/png')"""),
                             {"i": str(pid), "o": str(ORG), "n": name, "u": url, "d": data, "hu": hero_url, "hd": hero_data})
        await db.commit()
    async with session_maker() as db:
        before = {r.id: (r.photo_url, r.hero_photo_url) for r in (await db.execute(text(
            "SELECT id, photo_url, hero_photo_url FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(broken), str(lost), str(fine)]})).all()}
    check("the broken one really does 404 before the repair",
          await fetch(get_player_photo, before[broken][0], session_maker) == "HTTP 404")
    await repair(str(ORG), apply=False)
    async with session_maker() as db:
        dry = {r.id: (r.photo_url, r.hero_photo_url) for r in (await db.execute(text(
            "SELECT id, photo_url, hero_photo_url FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(broken), str(lost), str(fine)]})).all()}
    check("a dry run changes nothing", dry == before)
    await repair(str(ORG), apply=True)
    async with session_maker() as db:
        after = {r.id: (r.photo_url, r.hero_photo_url) for r in (await db.execute(text(
            "SELECT id, photo_url, hero_photo_url FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(broken), str(lost), str(fine)]})).all()}
        audits = await scalar(db, "SELECT COUNT(*) FROM audit_logs WHERE org_id = :o AND action = 'repair_player_photo_urls'", o=str(ORG))
    check("the broken headshot serves its picture after --apply",
          await fetch(get_player_photo, after[broken][0], session_maker) == PHOTO, str(after[broken][0]))
    check("and so does its action shot",
          await fetch(get_player_hero_photo, after[broken][1], session_maker) == HERO, str(after[broken][1]))
    check("a row with no picture left is left alone", after[lost] == before[lost])
    check("a healthy row is left alone", after[fine] == before[fine])
    check("the repair is in the club's activity log", audits == 1, str(audits))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
