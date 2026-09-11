"""BetterComms Lists → Segments merge, against a real Postgres.

"Lists" and "Segments" were two audience concepts a club had to learn apart: a
Segment is a live RULE, a List a hand-picked ROLL CALL. They are one concept
now — a Segment carries an ACTIVE rule AND a frozen STATIC set
(``comms_segment_members``), and the final audience is the UNION of the two.
Every former list becomes a pure-static segment (migration 304).

This exercises the SHIPPED engine, DDL and router bodies:

  * migration 304 applied 3× (idempotent) over a populated pre-304 schema, incl.
    the name-collision suffix and the members / wizard-ledger backfill;
  * the lifespan mirror and the migration run the SAME one-copy DDL;
  * the UNION — a hand-picked contact matching NO rule (control: absent without
    the static set), a suppressed hand-pick excluded by sendable_where, and a
    pure-static segment resolving to its members alone rather than everyone;
  * the scope guards BOTH ways (directory fields barred in a club, member fields
    barred in an outreach org), fail-closed rather than widening;
  * saved_list campaign back-compat resolving through the migrated segment, and
    the pre-migration fallback to the list's own members;
  * every mem_* field agreeing with directory.list_people's real output;
  * a repointed producer (admin_contact_list) writing a segment, not a list.

    python -m verification.verify_comms_segments_merge
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_segments_merge",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import (  # noqa: E402
    Base, ClubMembership, ClubRole, ClubRoleType, CommsContact, CommsList,
    CommsListMember, CommsSegment, CommsSegmentMember, FeeMember, MarketingClub,
    MembershipType, Organisation, Player, Team, User, VolunteerRole,
)
from app.services import comms_segments  # noqa: E402
from app.services.comms_segment_ddl import STATEMENTS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


# directory.list_people reads lifespan-added schema invisible to create_all: a
# raw-migration COLUMN on fee_members, and two raw-SQL TABLES with no ORM model.
# The lifespan-only trap this repo's notes already document.
_RAW = [
    "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT",
    """CREATE TABLE IF NOT EXISTS member_membership_types (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
        membership_type_id UUID NOT NULL REFERENCES membership_types(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (member_id, membership_type_id))""",
    """CREATE TABLE IF NOT EXISTS player_achievements (
        id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID,
        player_name TEXT NOT NULL, season TEXT, category TEXT NOT NULL,
        subcategory TEXT, achievement TEXT NOT NULL, detail TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW())""",
]


async def build_schema(engine):
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _RAW:
            await conn.execute(text(stmt))


# ── Section 1: migration 304 over a populated pre-304 schema ──────────────────
async def section_migration(engine, Session):
    print("\n── migration 304 over a populated pre-304 schema ──────────────")
    await build_schema(engine)

    org_id = uuid.uuid4()
    ca = uuid.uuid4()   # contact A
    cb = uuid.uuid4()   # contact B
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Club", slug="club"))
        await db.flush()
        db.add_all([
            CommsContact(id=ca, organisation_id=org_id, email="a@x.com", source="member"),
            CommsContact(id=cb, organisation_id=org_id, email="b@x.com", source="member"),
        ])
        await db.commit()

    # Simulate pre-304: strip what migration 304 adds, and put list_id back to
    # NOT NULL (its pre-304 shape).
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS comms_segment_members CASCADE"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_comms_segments_legacy_list"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_wizard_club_lists_segment_club"))
        for col in ("legacy_list_id", "origin", "source"):
            await conn.execute(text(f"ALTER TABLE comms_segments DROP COLUMN IF EXISTS {col}"))
        await conn.execute(text("ALTER TABLE wizard_club_lists DROP COLUMN IF EXISTS segment_id"))
        await conn.execute(text("ALTER TABLE wizard_club_lists ALTER COLUMN list_id SET NOT NULL"))

    seg_hand = uuid.uuid4()      # a hand-built segment named "Committee"
    list_news = uuid.uuid4()     # a list "Newsletter" (no name collision)
    list_comm = uuid.uuid4()     # a list "Committee" (collides with the segment)
    async with Session() as db:
        # A hand-built segment (raw insert — the ORM model still maps the dropped
        # columns, so an ORM insert would try to write them).
        await db.execute(text(
            "INSERT INTO comms_segments (id, organisation_id, name, definition, created_at, updated_at) "
            "VALUES (:i, :o, 'Committee', '{\"match\":\"all\",\"rules\":[]}'::jsonb, NOW(), NOW())"),
            {"i": seg_hand, "o": org_id})
        for lid, nm in [(list_news, "Newsletter"), (list_comm, "Committee")]:
            await db.execute(text(
                "INSERT INTO comms_lists (id, organisation_id, name, source, created_at, updated_at) "
                "VALUES (:i, :o, :n, 'manual', NOW(), NOW())"), {"i": lid, "o": org_id, "n": nm})
        await db.execute(text("INSERT INTO comms_list_members (id, list_id, contact_id, created_at) "
                              "VALUES (gen_random_uuid(), :l, :c, NOW())"), {"l": list_news, "c": ca})
        for c in (ca, cb):
            await db.execute(text("INSERT INTO comms_list_members (id, list_id, contact_id, created_at) "
                                  "VALUES (gen_random_uuid(), :l, :c, NOW())"), {"l": list_comm, "c": c})
        await db.execute(text(
            "INSERT INTO wizard_club_lists (id, list_id, list_name, club_key, club_name, contacts_added, created_at) "
            "VALUES (gen_random_uuid(), :l, 'Newsletter', 'k1', 'K One', 1, NOW())"), {"l": list_news})
        await db.commit()

    # Apply the migration THREE times — the lifespan re-runs it on every boot.
    async with engine.begin() as conn:
        for _ in range(3):
            for stmt in STATEMENTS:
                await conn.execute(text(stmt))

    async with Session() as db:
        async def scalar(sql, **p):
            return (await db.execute(text(sql), p)).scalar()

        migrated = (await db.execute(text(
            "SELECT id, name, source, legacy_list_id FROM comms_segments "
            "WHERE legacy_list_id IS NOT NULL ORDER BY name"), {})).mappings().all()
        by_list = {str(r["legacy_list_id"]): r for r in migrated}
        check("every list migrated to exactly one segment", len(migrated) == 2, str(len(migrated)))
        check("the un-colliding list keeps its name",
              by_list.get(str(list_news), {}).get("name") == "Newsletter",
              by_list.get(str(list_news), {}).get("name"))
        comm_name = by_list.get(str(list_comm), {}).get("name") or ""
        check("a list colliding with a hand-built segment is suffixed",
              comm_name.startswith("Committee (list ") and comm_name != "Committee", comm_name)
        check("the migrated segment carries the list's source", by_list.get(str(list_news), {}).get("source") == "manual")
        hand = await scalar("SELECT name FROM comms_segments WHERE id = :i", i=seg_hand)
        check("the hand-built segment is untouched", hand == "Committee", hand)

        n_news = await scalar("SELECT COUNT(*) FROM comms_segment_members WHERE segment_id = :s", s=by_list[str(list_news)]["id"])
        n_comm = await scalar("SELECT COUNT(*) FROM comms_segment_members WHERE segment_id = :s", s=by_list[str(list_comm)]["id"])
        check("the un-colliding list's one member carried over", n_news == 1, str(n_news))
        check("the colliding list's two members carried over", n_comm == 2, str(n_comm))

        wseg = await scalar("SELECT segment_id FROM wizard_club_lists WHERE list_id = :l", l=list_news)
        check("the wizard ledger row now points at the migrated segment",
              str(wseg) == str(by_list[str(list_news)]["id"]), str(wseg))

        total_seg = await scalar("SELECT COUNT(*) FROM comms_segments")
        total_mem = await scalar("SELECT COUNT(*) FROM comms_segment_members")
        check("3× apply is idempotent — no duplicate segments", total_seg == 3, str(total_seg))
        check("3× apply is idempotent — no duplicate members", total_mem == 3, str(total_mem))

    # The downgrade drops only what it added; the migrated segments stay.
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS comms_segment_members"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_comms_segments_legacy_list"))
        await conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS legacy_list_id"))
        await conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS origin"))
        await conn.execute(text("ALTER TABLE comms_segments DROP COLUMN IF EXISTS source"))
    async with Session() as db:
        gone = (await db.execute(text("SELECT to_regclass('comms_segment_members')"))).scalar()
        kept = (await db.execute(text("SELECT COUNT(*) FROM comms_segments"))).scalar()
        check("downgrade drops comms_segment_members", gone is None)
        check("downgrade keeps the migrated segments (a club's edits survive)", kept == 3, str(kept))

    # The one-copy DDL is run by BOTH the migration and the lifespan mirror.
    mig = open(os.path.join(REPO, "backend/alembic/versions/304_comms_segment_static.py")).read()
    main_src = open(os.path.join(REPO, "backend/app/main.py")).read()
    check("the migration runs services/comms_segment_ddl.STATEMENTS",
          "from app.services.comms_segment_ddl import STATEMENTS" in mig and "for stmt in STATEMENTS" in mig)
    check("the lifespan mirror runs the same one-copy STATEMENTS",
          "from app.services.comms_segment_ddl import STATEMENTS" in main_src)


# ── Section 2: the UNION, scope guards, saved_list back-compat ────────────────
async def section_behaviour(engine, Session):
    print("\n── the union, scope guards, saved_list back-compat ────────────")
    await build_schema(engine)

    org_id, out_id = uuid.uuid4(), uuid.uuid4()
    A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    OUT, OUT2 = uuid.uuid4(), uuid.uuid4()
    mc_id, out_mem = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        club = Organisation(id=org_id, name="Club", slug="club2")
        outreach = Organisation(id=out_id, name="BetterCricket", slug="bc", is_marketing_outreach=True)
        db.add_all([club, outreach])
        await db.flush()
        # A directory club A is linked to, so a directory rule (engagement_score)
        # WOULD match A absent the club-context guard — that is what makes the
        # scope-guard check discriminating rather than incidentally empty.
        db.add(MarketingClub(id=mc_id, grassroots_guid="g1", name="Club", engagement_score=50))
        # A member in the OUTREACH org, so a club-member rule (mem_gender) WOULD
        # match absent the outreach guard.
        db.add(FeeMember(id=out_mem, organisation_id=out_id, full_name="Ivy Out", gender="female"))
        await db.flush()
        db.add_all([
            CommsContact(id=A, organisation_id=org_id, email="a@x.com", source="member",
                         tags=["vip"], marketing_club_id=mc_id),
            CommsContact(id=B, organisation_id=org_id, email="b@x.com", source="member"),
            # C is a hand-pick that must be suppressed by the send gate.
            CommsContact(id=C, organisation_id=org_id, email="c@x.com", source="member", subscribed=False),
            CommsContact(id=OUT, organisation_id=out_id, email="o@x.com", source="import"),
            CommsContact(id=OUT2, organisation_id=out_id, email="o2@x.com", source="member", member_id=out_mem),
        ])
        await db.commit()
        club = await db.get(Organisation, org_id)
        outreach = await db.get(Organisation, out_id)

        rule_vip = {"match": "all", "rules": [{"field": "tag", "op": "eq", "value": "vip"}]}

        async def emails(defn, static=None):
            rows = await comms_segments.resolve_contacts(db, club, defn, static_ids=static)
            return {c.email for c in rows}

        # UNION: A matches the rule; B is a hand-pick that matches NO rule; C is
        # a suppressed hand-pick.
        got = await emails(rule_vip, static=[B, C])
        check("the union includes a hand-picked contact matching no rule", "b@x.com" in got, str(sorted(got)))
        check("the rule side still matches", "a@x.com" in got)
        check("a suppressed hand-pick is excluded by the send gate", "c@x.com" not in got, str(sorted(got)))
        # Control: the SAME rule without the static set does NOT include B.
        control = await emails(rule_vip)
        check("control — without the static set the non-matching hand-pick is absent",
              control == {"a@x.com"}, str(sorted(control)))

        # PURE-STATIC: no rules, a hand-picked set → the members alone, not everyone.
        pure = await emails({"match": "all", "rules": []}, static=[B])
        check("a pure-static segment resolves to its members alone", pure == {"b@x.com"}, str(sorted(pure)))
        # Control: no rules AND no static is the legacy pure-rule widen (everyone
        # sendable), so it is the STATIC set that narrows a pure-static segment,
        # not a general "empty = nobody".
        widen = await emails({"match": "all", "rules": []})
        check("control — empty rules with no static still widen to everyone sendable",
              widen == {"a@x.com", "b@x.com"}, str(sorted(widen)))
        count_pure = await comms_segments.count(db, club, {"match": "all", "rules": []}, static_ids=[B])
        check("count agrees with the pure-static resolve", count_pure == 1, str(count_pure))

        # SCOPE GUARDS, fail-closed BOTH ways (the club has sendable contacts, so
        # an empty result is the guard firing, not missing data).
        dir_rule = {"match": "all", "rules": [{"field": "engagement_score", "op": "gte", "value": 1}]}
        guarded = await emails(dir_rule)
        check("a directory-only rule in a club context fails closed (empty), not widened",
              guarded == set(), str(sorted(guarded)))
        mem_rule = {"match": "all", "rules": [{"field": "mem_gender", "op": "eq", "value": ["female"]}]}
        out_rows = await comms_segments.resolve_contacts(db, outreach, mem_rule)
        check("a club-member rule in an outreach context fails closed (empty), not widened",
              {c.email for c in out_rows} == set(), str([c.email for c in out_rows]))

        # saved_list back-compat: a historical campaign names a list_id. It
        # resolves through the segment the list migrated into.
        from app.routers import comms as comms_router
        L = CommsList(id=uuid.uuid4(), organisation_id=org_id, name="Old list")
        db.add(L)
        await db.flush()
        db.add(CommsListMember(id=uuid.uuid4(), list_id=L.id, contact_id=A))
        S = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="Old list (migrated)",
                         definition={"match": "all", "rules": []}, source="manual",
                         legacy_list_id=L.id)
        db.add(S)
        await db.flush()
        db.add(CommsSegmentMember(segment_id=S.id, contact_id=B))
        # A second list with NO migrated segment — the pre-migration fallback.
        L2 = CommsList(id=uuid.uuid4(), organisation_id=org_id, name="Legacy only")
        db.add(L2)
        await db.flush()
        db.add(CommsListMember(id=uuid.uuid4(), list_id=L2.id, contact_id=A))
        await db.commit()
        club = await db.get(Organisation, org_id)

        via_seg = {c.email for c in await comms_router._resolve_audience(
            db, club, {"type": "saved_list", "list_id": str(L.id)})}
        check("a saved_list campaign resolves through the migrated segment's members",
              via_seg == {"b@x.com"}, str(sorted(via_seg)))
        via_list = {c.email for c in await comms_router._resolve_audience(
            db, club, {"type": "saved_list", "list_id": str(L2.id)})}
        check("a list with no migrated segment falls back to its own members",
              via_list == {"a@x.com"}, str(sorted(via_list)))


# ── Section 3: every mem_* field agrees with directory.list_people ────────────
async def section_member_fields(engine, Session):
    print("\n── mem_* fields agree with directory.list_people's output ─────")
    await build_schema(engine)
    from app.services import directory

    org_id = uuid.uuid4()
    mem_id, player_id, team_id, mt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rt_id, role_id = uuid.uuid4(), uuid.uuid4()
    contact_rich, contact_plain = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Rich", slug="rich"))
        await db.flush()
        db.add(Team(id=team_id, organisation_id=org_id, name="1st XI"))
        db.add(MembershipType(id=mt_id, organisation_id=org_id, name="Senior Player",
                              is_playing=True, scope="internal", sort_order=0))
        db.add(ClubRoleType(id=rt_id, organisation_id=org_id, name="Volunteers", category="general"))
        await db.flush()
        db.add(ClubRole(id=role_id, organisation_id=org_id, title="Scorer", role_type_id=rt_id))
        db.add(Player(id=player_id, organisation_id=org_id, name="Rae Rich",
                      gender="male", status="active", squad_team_id=team_id, is_player=True))
        await db.flush()
        db.add(FeeMember(id=mem_id, organisation_id=org_id, full_name="Rae Rich",
                         player_id=player_id, is_life_member=True, is_honorary=False,
                         gender="female"))
        await db.flush()
        db.add(VolunteerRole(id=uuid.uuid4(), organisation_id=org_id, member_id=mem_id, role_id=role_id))
        await db.execute(text(
            "INSERT INTO member_membership_types (id, organisation_id, member_id, membership_type_id) "
            "VALUES (gen_random_uuid(), :o, :m, :t)"), {"o": org_id, "m": mem_id, "t": mt_id})
        # The rich member's contact carries both ids; a plain contact carries
        # neither and must be excluded by every mem_* rule.
        db.add(CommsContact(id=contact_rich, organisation_id=org_id, email="rich@x.com",
                            source="member", player_id=player_id, member_id=mem_id))
        db.add(CommsContact(id=contact_plain, organisation_id=org_id, email="plain@x.com", source="import"))
        await db.commit()
        club = await db.get(Organisation, org_id)

        people = await directory.list_people(db, org_id)
        person = next((p for p in people if p.get("member_id") == str(mem_id)), None)
        check("list_people returns the rich member", person is not None)

        async def emails(field, value):
            defn = {"match": "all", "rules": [{"field": field, "op": "eq", "value": value}]}
            rows = await comms_segments.resolve_contacts(db, club, defn)
            return {c.email for c in rows}

        # For each field, the engine's resolved set must equal exactly the
        # contacts whose list_people person satisfies the matcher — with the rich
        # member matched and the plain contact excluded.
        cases = [
            ("mem_membership_type", [str(mt_id)]),
            ("mem_squad", [str(team_id)]),
            ("mem_gender", ["female"]),
            ("mem_honour", ["life_member"]),
            ("mem_is_playing", "yes"),
            ("mem_player_status", "active"),
            ("mem_club_role", ["volunteer"]),
        ]
        for field, value in cases:
            oracle = {"rich@x.com"} if comms_segments._person_matches_member(field, value, person) else set()
            got = await emails(field, value)
            check(f"{field} resolves to exactly the list_people-matched contacts",
                  got == oracle and got == {"rich@x.com"}, f"got={sorted(got)} oracle={sorted(oracle)}")

        # A real value matching nobody narrows to nobody (fail-closed), never widens.
        none = await emails("mem_squad", [str(uuid.uuid4())])
        check("a member rule matching nobody resolves to nobody (not everyone)", none == set(), str(sorted(none)))
        # An empty multi-select drops the rule and widens to everyone sendable.
        empty = await emails("mem_squad", [])
        check("an empty member selection drops the rule and widens",
              empty == {"rich@x.com", "plain@x.com"}, str(sorted(empty)))


# ── the matcher against the documented list_people facet shape ────────────────
def section_matcher_unit():
    print("\n── _person_matches_member against the list_people facet shape ─")
    m = comms_segments._person_matches_member
    tid = str(uuid.uuid4())
    p = {
        "player_id": str(uuid.uuid4()), "member_id": str(uuid.uuid4()),
        "membership_types": [{"id": tid, "name": "Senior Player"}],
        "tier": {"id": tid, "name": "Full"}, "squad": {"id": tid, "name": "1st XI"},
        "gender": "Female", "player_status": "active",
        "is_life_member": True, "is_honorary": False,
        "segs": ["Volunteer", "Committee"],
    }
    check("mem_membership_type matches its id", m("mem_membership_type", [tid], p))
    check("mem_membership_type misses an unknown id", not m("mem_membership_type", [str(uuid.uuid4())], p))
    check("mem_membership_tier matches its id", m("mem_membership_tier", [tid], p))
    check("mem_squad matches its id", m("mem_squad", [tid], p))
    check("mem_gender is case-insensitive", m("mem_gender", ["female"], p))
    check("mem_club_role reads the segs labels", m("mem_club_role", ["committee"], p))
    check("mem_club_role misses a role not held", not m("mem_club_role", ["official"], p))
    check("mem_honour reads life membership", m("mem_honour", ["life_member"], p))
    check("mem_honour misses honorary when not honorary", not m("mem_honour", ["honorary"], p))
    check("mem_is_playing yes matches a linked player", m("mem_is_playing", "yes", p))
    check("mem_is_playing no misses a linked player", not m("mem_is_playing", "no", p))
    check("mem_player_status active matches", m("mem_player_status", "active", p))
    check("mem_player_status former misses an active player", not m("mem_player_status", "former", p))
    # A read-through player (no member row) and a non-player (no player row).
    only_player = {"player_id": str(uuid.uuid4()), "member_id": None, "player_status": "inactive",
                   "segs": [], "membership_types": [], "gender": None, "is_life_member": False,
                   "is_honorary": False, "tier": None, "squad": None}
    check("mem_player_status former matches an inactive player", m("mem_player_status", "former", only_player))
    check("mem_is_playing no matches a non-player",
          m("mem_is_playing", "no", {"player_id": None, "member_id": str(uuid.uuid4()),
                                     "segs": [], "membership_types": [], "gender": None,
                                     "is_life_member": False, "is_honorary": False,
                                     "tier": None, "squad": None, "player_status": None}))


# ── Section 4: a repointed producer writes a segment, not a list ──────────────
async def section_producer(engine, Session):
    print("\n── a repointed producer writes a segment, not a list ──────────")
    await build_schema(engine)
    from app.services import admin_contact_list

    out_id, club_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=out_id, name="BetterCricket", slug="bc2", is_marketing_outreach=True))
        db.add(Organisation(id=club_id, name="Rovers", slug="rovers"))
        await db.flush()
        db.add(User(id=user_id, username="admin1", email="admin@rovers.com"))
        await db.flush()
        db.add(ClubMembership(id=uuid.uuid4(), user_id=user_id, club_id=club_id,
                              role="club_admin", is_primary_admin=True))
        await db.commit()

        res = await admin_contact_list.sync(db, apply=True)
        await db.commit()
        check("the producer ran (an outreach org is designated)", res.get("status") != "no_outreach_org", str(res))

        segs = (await db.execute(select(CommsSegment).where(CommsSegment.organisation_id == out_id))).scalars().all()
        check("it created exactly one auto segment", len(segs) == 1 and segs[0].source == "auto",
              str([(s.name, s.source) for s in segs]))
        lists = (await db.execute(select(CommsList).where(CommsList.organisation_id == out_id))).scalars().all()
        check("it created NO legacy list", len(lists) == 0, str(len(lists)))
        if segs:
            n = (await db.execute(select(CommsSegmentMember).where(
                CommsSegmentMember.segment_id == segs[0].id))).scalars().all()
            check("the club admin landed in the segment's static set", len(n) == 1, str(len(n)))

    # Structural: the three repointed producers reference the segment tables and
    # none creates a CommsList row.
    for path in ["app/services/admin_contact_list.py", "app/services/crm_list_export.py",
                 "app/services/wizard_club_lists.py"]:
        src = open(os.path.join(REPO, "backend", path)).read()
        check(f"{os.path.basename(path)} creates a segment, never a CommsList",
              "CommsSegmentMember(" in src and "CommsList(" not in src)


# ── Section 5: excluding other segments' audiences, and duplicate ─────────────
async def section_exclusions(engine, Session):
    print("\n── excluding other segments' audiences, and duplicate ─────────")
    await build_schema(engine)
    from app.routers import comms as comms_router

    org_id = uuid.uuid4()
    A, B, C, D = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Club", slug="club-ex"))
        await db.flush()
        # Two "females", one "engaged", one plain — the user's worked example in
        # miniature: everyone MINUS the Females segment MINUS the engaged segment.
        db.add_all([
            CommsContact(id=A, organisation_id=org_id, email="a@x.com", source="member", tags=["female"]),
            CommsContact(id=B, organisation_id=org_id, email="b@x.com", source="member", tags=["female"]),
            CommsContact(id=C, organisation_id=org_id, email="c@x.com", source="member", tags=["engaged"]),
            CommsContact(id=D, organisation_id=org_id, email="d@x.com", source="member"),
        ])
        await db.flush()

        seg_f = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="Females",
                             definition={"match": "all", "rules": [{"field": "tag", "op": "eq", "value": "female"}]})
        seg_e = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="Engaged",
                             definition={"match": "all", "rules": [{"field": "tag", "op": "eq", "value": "engaged"}]})
        # "All contacts", a pure-static roll call of everyone (Segment 1).
        seg_all = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="All contacts",
                               definition={"match": "all", "rules": []})
        db.add_all([seg_f, seg_e, seg_all])
        await db.flush()
        db.add_all([CommsSegmentMember(segment_id=seg_all.id, contact_id=c) for c in (A, B, C, D)])
        await db.commit()
        club = await db.get(Organisation, org_id)

        async def emails(defn, static=None, seen=frozenset()):
            rows = await comms_segments.resolve_contacts(db, club, defn, static_ids=static, _seen=seen)
            return {c.email for c in rows}

        # The excluded segments each resolve to their own audience first.
        check("the Females segment resolves to its two contacts",
              await emails(seg_f.definition) == {"a@x.com", "b@x.com"})
        check("the Engaged segment resolves to its one contact",
              await emails(seg_e.definition) == {"c@x.com"})

        # A static-all base MINUS Females MINUS Engaged = the plain contact alone.
        diff_def = {"match": "all", "rules": [], "exclude_segments": [str(seg_f.id), str(seg_e.id)]}
        got = await emails(diff_def, static=[A, B, C, D])
        check("static-everyone minus Females minus Engaged leaves only the plain contact",
              got == {"d@x.com"}, str(sorted(got)))

        # The same result from a pure-RULE everyone base (empty rules, no static),
        # which is what "duplicate the all-contacts base then exclude" resolves to
        # when the base is a rule rather than a roll call.
        got2 = await emails({"match": "all", "rules": [], "exclude_segments": [str(seg_f.id), str(seg_e.id)]})
        check("rule-everyone minus Females minus Engaged also leaves only the plain contact",
              got2 == {"d@x.com"}, str(sorted(got2)))

        # Excluding just one of the two subtracts only that segment's audience.
        one = await emails({"match": "all", "rules": [], "exclude_segments": [str(seg_f.id)]}, static=[A, B, C, D])
        check("excluding only Females leaves the engaged and the plain contact",
              one == {"c@x.com", "d@x.com"}, str(sorted(one)))

        # count() takes the exclusion path and agrees with resolve.
        n = await comms_segments.count(db, club, diff_def, static_ids=[A, B, C, D])
        check("count agrees with the excluding resolve", n == 1, str(n))

        # Control: DROP the exclusions and the base is everyone again — this is
        # what the previous commit (no exclusion support) resolved to.
        base = await emails({"match": "all", "rules": []}, static=[A, B, C, D])
        check("control — without exclusions the base is all four contacts",
              base == {"a@x.com", "b@x.com", "c@x.com", "d@x.com"}, str(sorted(base)))

        # A junk id in exclude_segments is dropped, never raises.
        junk = await emails({"match": "all", "rules": [], "exclude_segments": ["not-a-uuid", str(seg_f.id)]},
                            static=[A, B, C, D])
        check("a junk exclusion id is ignored; the valid one still subtracts",
              junk == {"c@x.com", "d@x.com"}, str(sorted(junk)))

        # An exclusion pointing at another club's segment subtracts nobody.
        other = Organisation(id=uuid.uuid4(), name="Other", slug="other-ex")
        db.add(other)
        await db.flush()
        oseg = CommsSegment(id=uuid.uuid4(), organisation_id=other.id, name="Theirs",
                            definition={"match": "all", "rules": []})
        db.add(oseg)
        await db.commit()
        club = await db.get(Organisation, org_id)
        foreign = await comms_segments.resolve_contacts(
            db, club, {"match": "all", "rules": [], "exclude_segments": [str(oseg.id)]}, static_ids=[A, B, C, D])
        check("excluding another club's segment subtracts nobody",
              {c.email for c in foreign} == {"a@x.com", "b@x.com", "c@x.com", "d@x.com"},
              str(sorted(c.email for c in foreign)))

        # CYCLE GUARD: X excludes Y, Y excludes X. Resolving X terminates.
        x = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="X",
                         definition={"match": "all", "rules": []})
        y = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="Y",
                         definition={"match": "all", "rules": []})
        db.add_all([x, y])
        await db.flush()
        db.add_all([CommsSegmentMember(segment_id=x.id, contact_id=A),
                    CommsSegmentMember(segment_id=y.id, contact_id=B)])
        x.definition = {"match": "all", "rules": [], "exclude_segments": [str(y.id)]}
        y.definition = {"match": "all", "rules": [], "exclude_segments": [str(x.id)]}
        await db.commit()
        club = await db.get(Organisation, org_id)
        # X = {A} minus Y's audience; Y = {B} minus X's audience. The guard stops
        # the recursion, so X resolves to {A} without hanging.
        cyc = await comms_segments.resolve_contacts(
            db, club, x.definition, static_ids=[A], _seen=frozenset({x.id}))
        check("a mutual-exclusion cycle terminates and resolves to the base",
              {c.email for c in cyc} == {"a@x.com"}, str(sorted(c.email for c in cyc)))

        # DUPLICATE copies the definition (rules AND exclusions) AND the static set.
        src = CommsSegment(id=uuid.uuid4(), organisation_id=org_id, name="Source",
                           definition={"match": "all", "rules": [{"field": "tag", "op": "eq", "value": "female"}],
                                       "exclude_segments": [str(seg_e.id)]}, source="manual")
        db.add(src)
        await db.flush()
        db.add_all([CommsSegmentMember(segment_id=src.id, contact_id=A),
                    CommsSegmentMember(segment_id=src.id, contact_id=B)])
        await db.commit()
        club = await db.get(Organisation, org_id)

        copy_out = await comms_router.duplicate_segment(str(src.id), _=None, club=club, db=db)
        check("the duplicate is named with a (copy) suffix",
              copy_out["name"].startswith("Source (copy)"), copy_out["name"])
        check("the duplicate carries the source's rules",
              copy_out["definition"].get("rules") == [{"field": "tag", "op": "eq", "value": "female"}],
              str(copy_out["definition"].get("rules")))
        check("the duplicate carries the source's exclusions",
              copy_out["definition"].get("exclude_segments") == [str(seg_e.id)],
              str(copy_out["definition"].get("exclude_segments")))
        check("the duplicate copied both static members", copy_out.get("member_count") == 2,
              str(copy_out.get("member_count")))
        copy_mem = (await db.execute(select(CommsSegmentMember).where(
            CommsSegmentMember.segment_id == uuid.UUID(copy_out["id"])))).scalars().all()
        check("the duplicate's members are real rows, not just a reported count", len(copy_mem) == 2, str(len(copy_mem)))
        # The copy is a distinct segment — the source is untouched.
        src_mem = (await db.execute(select(CommsSegmentMember).where(
            CommsSegmentMember.segment_id == src.id))).scalars().all()
        check("the source keeps its own members after duplication", len(src_mem) == 2, str(len(src_mem)))


async def main() -> int:
    engine = create_async_engine(DB_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    await section_migration(engine, Session)
    await section_behaviour(engine, Session)
    await section_member_fields(engine, Session)
    section_matcher_unit()
    await section_producer(engine, Session)
    await section_exclusions(engine, Session)
    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
