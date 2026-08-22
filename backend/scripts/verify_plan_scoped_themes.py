"""A theme belongs to ONE plan (migration 275), against a real Postgres.

The first block REPRODUCES what was reported: two plans, a theme shared
between them, and deleting that theme from the second plan's tree taking the
first plan's objectives with it. It builds the PRE-275 shape by hand so the
migration has something to convert, then runs the shipped backfill and asserts
each plan came out with its own tree.
"""
import asyncio, os, sys, uuid
sys.path.insert(0, '/home/user/BetterStats/backend')
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres@/postgres?host=/var/tmp&port=55432')
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text
from app.models.db import (Base, Organisation, ClubStrategicPlan, ClubStrategicPillar,
                           ClubObjective, CommitteeTask)
from app.services import committee as svc
from app.services.pillar_plan_ddl import PILLAR_PLAN_SPLIT_SQL, PILLAR_PLAN_CLAIM_SQL

C = []
def ok(n, c, e=''):
    C.append((c, n, e))
    if not c: print('FAIL:', n, e)


async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        # The models carry migration 276's shape, so the columns come out NOT
        # NULL. This suite is about 275, whose whole input is rows that have no
        # plan — so the constraints are relaxed back to the PRE-275 shape and
        # the rows below build it by hand.
        for stmt in (
            "ALTER TABLE club_strategic_pillars ALTER COLUMN plan_id DROP NOT NULL",
            "ALTER TABLE club_objectives ALTER COLUMN plan_id DROP NOT NULL",
            "ALTER TABLE club_objectives ALTER COLUMN pillar_id DROP NOT NULL",
        ):
            await c.execute(text(stmt))
    S = async_sessionmaker(eng, expire_on_commit=False)

    async with S() as db:
        org_id = uuid.uuid4()
        db.add(Organisation(id=org_id, name='A', slug='a')); await db.flush()

        p1 = ClubStrategicPlan(organisation_id=org_id, name='Plan 1')
        p2 = ClubStrategicPlan(organisation_id=org_id, name='Plan 2')
        db.add_all([p1, p2]); await db.flush()
        p1_id, p2_id = p1.id, p2.id

        # Plan 1: two themes, two objectives each, one with an action on it.
        shared = ClubStrategicPillar(organisation_id=org_id, name='Participation')
        finance = ClubStrategicPillar(organisation_id=org_id, name='Finances')
        lonely = ClubStrategicPillar(organisation_id=org_id, name='Never used')
        db.add_all([shared, finance, lonely]); await db.flush()
        shared_id, finance_id, lonely_id = shared.id, finance.id, lonely.id

        o1 = ClubObjective(organisation_id=org_id, title='Grow juniors', plan_id=p1_id, pillar_id=shared_id)
        o2 = ClubObjective(organisation_id=org_id, title='Balance books', plan_id=p1_id, pillar_id=finance_id)
        # The objective the club added to Plan 2, under the SAME theme row —
        # which is how one theme came to span two plans.
        o3 = ClubObjective(organisation_id=org_id, title='Plan 2 work', plan_id=p2_id, pillar_id=shared_id)
        db.add_all([o1, o2, o3]); await db.flush()
        o1_id, o2_id, o3_id = o1.id, o2.id, o3.id
        t1 = CommitteeTask(organisation_id=org_id, title='Book the nets', objective_id=o1_id)
        db.add(t1); await db.commit()
        t1_id = t1.id

        # ── the reported failure, on the OLD model ───────────────────────
        before = (await db.execute(
            select(ClubObjective.id).where(ClubObjective.pillar_id == shared_id))).all()
        ok('pre-275 one theme really did span both plans', len(before) == 2, str(before))

        # ── now migrate ──────────────────────────────────────────────────
        await db.execute(text(PILLAR_PLAN_SPLIT_SQL))
        await db.execute(text(PILLAR_PLAN_CLAIM_SQL))
        await db.commit()
        db.expire_all()

        async def pillars_of(plan_id):
            rows = (await db.execute(
                select(ClubStrategicPillar.id, ClubStrategicPillar.name)
                .where(ClubStrategicPillar.plan_id == plan_id))).all()
            return {n: i for i, n in rows}

        a = await pillars_of(p1_id)
        b = await pillars_of(p2_id)
        ok('plan 1 keeps both its themes', set(a) == {'Participation', 'Finances'}, str(set(a)))
        ok('plan 2 gets its OWN copy of the shared theme', set(b) == {'Participation'}, str(set(b)))
        ok("and it is a different row from plan 1's",
           a.get('Participation') != b.get('Participation'), f"{a.get('Participation')} {b.get('Participation')}")

        async def obj_pillar(oid):
            return (await db.execute(
                select(ClubObjective.pillar_id).where(ClubObjective.id == oid))).scalar_one()
        ok("plan 1's objective stays on plan 1's theme", await obj_pillar(o1_id) == a['Participation'])
        ok("plan 2's objective moves to plan 2's theme", await obj_pillar(o3_id) == b['Participation'])
        ok('a theme with no objectives is left unclaimed',
           (await db.execute(select(ClubStrategicPillar.plan_id)
                             .where(ClubStrategicPillar.id == lonely_id))).scalar_one() is None)

        # idempotent — the app re-runs this on every boot
        await db.execute(text(PILLAR_PLAN_SPLIT_SQL))
        await db.execute(text(PILLAR_PLAN_CLAIM_SQL))
        await db.commit(); db.expire_all()
        ok('running the backfill again mints nothing',
           len((await db.execute(select(ClubStrategicPillar.id))).all()) == 4)

        # ── the reported disaster can no longer happen ───────────────────
        assert await svc.delete_pillar(db, org_id, b["Participation"])
        await db.commit(); db.expire_all()
        left = {r[0] for r in (await db.execute(select(ClubObjective.id))).all()}
        ok("deleting plan 2's theme takes plan 2's objective", o3_id not in left)
        ok("and leaves plan 1's objectives alone", {o1_id, o2_id} <= left, str(left))
        ok('the action serving plan 1 is untouched',
           (await db.execute(select(CommitteeTask.objective_id)
                             .where(CommitteeTask.id == t1_id))).scalar_one() == o1_id)

        # ── deleting a plan takes its themes, and only its themes ────────
        assert await svc.delete_plan(db, org_id, p1_id)
        await db.commit(); db.expire_all()
        names = {n for (n,) in (await db.execute(select(ClubStrategicPillar.name))).all()}
        ok("plan 1's themes go with plan 1", names == {'Never used'}, str(names))
        ok('the unclaimed theme survives a plan delete', 'Never used' in names)
        ok('the action is kept and simply unlinked',
           (await db.execute(select(CommitteeTask.objective_id)
                             .where(CommitteeTask.id == t1_id))).scalar_one() is None)

        # ── an objective cannot sit in one plan under another plan's theme ─
        p3 = ClubStrategicPlan(organisation_id=org_id, name='Plan 3')
        db.add(p3); await db.flush(); p3_id = p3.id
        th3 = ClubStrategicPillar(organisation_id=org_id, name='T3', plan_id=p3_id)
        db.add(th3); await db.commit(); th3_id = th3.id
        made = await svc.upsert_objective(db, org_id, title='Mismatched',
                                          plan_id=p2_id, pillar_id=th3_id)
        await db.commit()
        ok("an objective follows its theme's plan", made['plan_id'] == str(p3_id), str(made['plan_id']))

        # ── a theme cannot be filed under another club's plan ────────────
        other_id = uuid.uuid4()
        db.add(Organisation(id=other_id, name='B', slug='b')); await db.commit()
        try:
            await svc.upsert_pillar(db, other_id, name='Sneaky', plan_id=p3_id)
            ok("another club's plan is refused", False, 'no error raised')
        except ValueError as e:
            ok("another club's plan is refused", 'not this club' in str(e), str(e))
        await db.rollback()

        # ── the starter plan builds its own themes under its own plan ────
        fresh_id = uuid.uuid4()
        db.add(Organisation(id=fresh_id, name='C', slug='c', diary_start_month=7)); await db.commit()
        seeded = await svc.seed_starter_plan(db, fresh_id)
        await db.commit(); db.expire_all()
        seeded_plan = uuid.UUID(seeded['plan']['id'])
        made_pillars = (await db.execute(
            select(ClubStrategicPillar.plan_id)
            .where(ClubStrategicPillar.organisation_id == fresh_id))).all()
        ok('every starter theme belongs to the starter plan',
           len(made_pillars) == 4 and all(r[0] == seeded_plan for r in made_pillars), str(made_pillars))
        again = await svc.seed_starter_plan(db, fresh_id)
        await db.commit(); db.expire_all()
        ok('seeding twice creates no second set of themes',
           again['created_plan'] is False
           and len((await db.execute(select(ClubStrategicPillar.id)
                                     .where(ClubStrategicPillar.organisation_id == fresh_id))).all()) == 4)

        # ── list_pillars scoped to one plan ──────────────────────────────
        rows = await svc.list_pillars(db, org_id, plan_id=p3_id)
        ok('list_pillars can be narrowed to one plan',
           [r['name'] for r in rows] == ['T3'], str(rows))
        ok('and every row says which plan it belongs to',
           rows and rows[0]['plan_id'] == str(p3_id), str(rows))

    await eng.dispose()
    p = sum(1 for c, *_ in C if c)
    print(f'\n{p}/{len(C)} checks passed')
    for c, n, e in C:
        if not c: print('  x', n, e)
    sys.exit(0 if p == len(C) else 1)

asyncio.run(main())
