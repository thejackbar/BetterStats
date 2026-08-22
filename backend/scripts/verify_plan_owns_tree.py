"""A plan owns its themes; a theme owns its objectives (migration 276), against
a real Postgres.

The suite builds the PRE-276 shape by hand — a theme with no plan, an objective
with no plan, an objective with no theme — runs the shipped conversion, and
asserts the three states are gone WITHOUT anything the club wrote being deleted:
every objective is still there, under a real theme, on a real plan, and every
action and motion serving one is still there too.

Then it runs the shipped service and route bodies against the converted schema:
a plan delete taking its own tree and no other plan's, a theme delete reaching
only its own plan's objectives, both refusing to strand an action or a motion,
and the two writers refusing to create a themeless objective or a planless theme
in the first place.
"""
import asyncio, os, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/home/user/BetterStats/backend')
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres@/postgres?host=/var/tmp&port=55432')
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text, func
from app.models.db import (Base, Organisation, ClubStrategicPlan, ClubStrategicPillar,
                           ClubObjective, CommitteeTask, CommitteeMeeting, MeetingMotion)
from app.services import committee as svc
from app.services.pillar_plan_ddl import PILLAR_PLAN_SPLIT_SQL, PILLAR_PLAN_CLAIM_SQL
from app.services.plan_tree_ddl import PLAN_TREE_SQL

C = []
def ok(n, c, e=''):
    C.append((c, n, e))
    if not c:
        print('FAIL:', n, e)


PRE_276 = (
    "ALTER TABLE club_strategic_pillars ALTER COLUMN plan_id DROP NOT NULL",
    "ALTER TABLE club_objectives ALTER COLUMN plan_id DROP NOT NULL",
    "ALTER TABLE club_objectives ALTER COLUMN pillar_id DROP NOT NULL",
    "ALTER TABLE club_objectives DROP CONSTRAINT IF EXISTS club_objectives_plan_id_fkey",
    """ALTER TABLE club_objectives ADD CONSTRAINT club_objectives_plan_id_fkey
       FOREIGN KEY (plan_id) REFERENCES club_strategic_plans(id) ON DELETE SET NULL""",
    "ALTER TABLE club_objectives DROP CONSTRAINT IF EXISTS club_objectives_pillar_id_fkey",
    """ALTER TABLE club_objectives ADD CONSTRAINT club_objectives_pillar_id_fkey
       FOREIGN KEY (pillar_id) REFERENCES club_strategic_pillars(id) ON DELETE SET NULL""",
)


async def del_type(c, table, ref):
    """The FK's ON DELETE action: 'c' cascade, 'n' set null.

    Cast to text in SQL — `confdeltype` is Postgres's internal ``"char"`` and
    asyncpg hands that back as BYTES, so a bare comparison against 'c' is
    quietly false however right the constraint is.
    """
    return await c.scalar(text("""
        SELECT confdeltype::text FROM pg_constraint
        WHERE conrelid::regclass::text = :t AND contype = 'f'
          AND confrelid::regclass::text = :r
    """), {"t": table, "r": ref})


async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])

    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        # The models already carry 276's shape, so the schema is relaxed back
        # to what a club actually upgrades FROM.
        for stmt in PRE_276:
            await c.execute(text(stmt))

    S = async_sessionmaker(eng, expire_on_commit=False)

    # ── the pre-276 shape, built by hand ──────────────────────────────────
    async with S() as db:
        org_id, other_id = uuid.uuid4(), uuid.uuid4()
        db.add_all([Organisation(id=org_id, name='A', slug='a'),
                    Organisation(id=other_id, name='B', slug='b')])
        await db.flush()

        p1 = ClubStrategicPlan(organisation_id=org_id, name='Plan 1')
        p2 = ClubStrategicPlan(organisation_id=org_id, name='Plan 2')
        pb = ClubStrategicPlan(organisation_id=other_id, name='Other club plan')
        db.add_all([p1, p2, pb]); await db.flush()
        p1_id, p2_id, pb_id = p1.id, p2.id, pb.id

        # Plan 1: a proper theme with two objectives.
        t_fac = ClubStrategicPillar(organisation_id=org_id, name='Facilities', plan_id=p1_id)
        # Plan 2: its own theme, its own objective.
        t_vol = ClubStrategicPillar(organisation_id=org_id, name='Volunteers', plan_id=p2_id)
        # The three pre-276 states:
        t_loose = ClubStrategicPillar(organisation_id=org_id, name='Loose theme')     # no plan, has work
        t_empty = ClubStrategicPillar(organisation_id=org_id, name='Empty and loose')  # no plan, no work
        db.add_all([t_fac, t_vol, t_loose, t_empty]); await db.flush()
        fac, vol, loose, empty = t_fac.id, t_vol.id, t_loose.id, t_empty.id

        o_nets = ClubObjective(organisation_id=org_id, title='Rebuild the nets', plan_id=p1_id, pillar_id=fac)
        o_shed = ClubObjective(organisation_id=org_id, title='Re-roof the shed', plan_id=p1_id, pillar_id=fac)
        o_roster = ClubObjective(organisation_id=org_id, title='Fill the roster', plan_id=p2_id, pillar_id=vol)
        o_under = ClubObjective(organisation_id=org_id, title='Under a planless theme', pillar_id=loose)
        o_nowhere = ClubObjective(organisation_id=org_id, title='On nothing at all')
        o_noTheme = ClubObjective(organisation_id=org_id, title='On a plan, under no theme', plan_id=p1_id)
        db.add_all([o_nets, o_shed, o_roster, o_under, o_nowhere, o_noTheme]); await db.flush()
        ids = {k: v.id for k, v in dict(nets=o_nets, shed=o_shed, roster=o_roster,
                                        under=o_under, nowhere=o_nowhere, noTheme=o_noTheme).items()}

        # Real work hanging off two of them, which must survive everything.
        task = CommitteeTask(organisation_id=org_id, title='Get three quotes', objective_id=ids['nets'])
        mtg = CommitteeMeeting(organisation_id=org_id, title='August committee',
                               scheduled_at=datetime(2026, 8, 4, 19, 0, tzinfo=timezone.utc))
        db.add_all([task, mtg]); await db.flush()
        motion = MeetingMotion(meeting_id=mtg.id, description='That the nets be rebuilt', objective_id=ids['nets'])
        db.add(motion); await db.commit()
        task_id, motion_id = task.id, motion.id

        objectives_before = await db.scalar(
            select(func.count()).select_from(ClubObjective).where(ClubObjective.organisation_id == org_id))

    # ── run the shipped conversion, three times ───────────────────────────
    async with eng.begin() as c:
        for _ in range(3):
            for stmt in (PILLAR_PLAN_SPLIT_SQL, PILLAR_PLAN_CLAIM_SQL):
                await c.execute(text(stmt))
            for stmt in PLAN_TREE_SQL:
                await c.execute(text(stmt))
    ok('the conversion applies three times to a populated pre-276 table', True)

    async with S() as db:
        rows = (await db.execute(
            select(ClubObjective.id, ClubObjective.title, ClubObjective.plan_id, ClubObjective.pillar_id)
            .where(ClubObjective.organisation_id == org_id))).all()
        ok('no objective was deleted by the conversion',
           len(rows) == objectives_before, f'{len(rows)} vs {objectives_before}')
        ok('every objective is on a plan', all(r.plan_id for r in rows))
        ok('every objective is under a theme', all(r.pillar_id for r in rows))

        by_id = {r.id: r for r in rows}
        ok('an objective that already had a plan and theme kept both',
           by_id[ids['nets']].plan_id == p1_id and by_id[ids['nets']].pillar_id == fac)
        ok("plan 2's objective stayed on plan 2",
           by_id[ids['roster']].plan_id == p2_id and by_id[ids['roster']].pillar_id == vol)

        pillars = (await db.execute(
            select(ClubStrategicPillar.id, ClubStrategicPillar.name, ClubStrategicPillar.plan_id)
            .where(ClubStrategicPillar.organisation_id == org_id))).all()
        ok('every theme is on a plan', all(p.plan_id for p in pillars))
        ok('a theme with no plan and no objectives was dropped',
           not any(p.id == empty for p in pillars))
        ok('a theme with no plan but real work under it was kept',
           any(p.id == loose for p in pillars))

        plans = {p.name: p.id for p in (await db.execute(
            select(ClubStrategicPlan.id, ClubStrategicPlan.name)
            .where(ClubStrategicPlan.organisation_id == org_id))).all()}
        ok('the unattributable was carried into an "Unfiled work" plan', 'Unfiled work' in plans)
        carrier = plans.get('Unfiled work')
        ok('the theme that had no plan is on the carrier plan',
           next(p.plan_id for p in pillars if p.id == loose) == carrier)
        ok('the objective under it went with its own theme',
           by_id[ids['under']].plan_id == carrier and by_id[ids['under']].pillar_id == loose)
        ok('an objective on nothing at all landed on the carrier plan',
           by_id[ids['nowhere']].plan_id == carrier)

        generals = [p for p in pillars if p.name == 'General']
        ok('a "General" theme was made for objectives that had none', len(generals) >= 1)
        ok('an objective on a plan with no theme was filed inside its OWN plan',
           by_id[ids['noTheme']].plan_id == p1_id
           and next(p.plan_id for p in pillars if p.id == by_id[ids['noTheme']].pillar_id) == p1_id)
        ok('the carrier plan got its own "General" rather than borrowing plan 1\'s',
           by_id[ids['nowhere']].pillar_id != by_id[ids['noTheme']].pillar_id)

        ok('the action serving an objective survived the conversion',
           await db.get(CommitteeTask, task_id) is not None)
        ok('the motion serving an objective survived the conversion',
           await db.get(MeetingMotion, motion_id) is not None)

        ok("another club's plan was left alone",
           await db.get(ClubStrategicPlan, pb_id) is not None)

    # ── the constraints the conversion put in place ───────────────────────
    async with eng.begin() as c:
        for tbl, col in (('club_strategic_pillars', 'plan_id'),
                         ('club_objectives', 'plan_id'),
                         ('club_objectives', 'pillar_id')):
            nullable = await c.scalar(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = :t AND column_name = :c
            """), {"t": tbl, "c": col})
            ok(f'{tbl}.{col} is NOT NULL', nullable == 'NO', str(nullable))

        ok('objectives → plans cascades',
           await del_type(c, 'club_objectives', 'club_strategic_plans') == 'c')
        ok('objectives → themes cascades',
           await del_type(c, 'club_objectives', 'club_strategic_pillars') == 'c')
        ok('themes → plans cascades',
           await del_type(c, 'club_strategic_pillars', 'club_strategic_plans') == 'c')
        # The rule not to relax: work is kept, it just stops being linked.
        ok('actions → objectives still SETS NULL, so an action is never deleted',
           await del_type(c, 'committee_tasks', 'club_objectives') == 'n')
        ok('motions → objectives still SETS NULL, so a motion is never deleted',
           await del_type(c, 'meeting_motions', 'club_objectives') == 'n')

    # ── the shipped writers refuse what the tree cannot hold ──────────────
    async with S() as db:
        try:
            await svc.upsert_objective(db, org_id, None, title='No theme', plan_id=str(p1_id))
            ok('creating an objective with no theme is refused', False, 'it was allowed')
        except ValueError as e:
            ok('creating an objective with no theme is refused', 'theme' in str(e).lower(), str(e))
        await db.rollback()

        try:
            await svc.upsert_pillar(db, org_id, None, name='No plan')
            ok('creating a theme with no plan is refused', False, 'it was allowed')
        except ValueError as e:
            ok('creating a theme with no plan is refused', 'plan' in str(e).lower(), str(e))
        await db.rollback()

        try:
            await svc.upsert_pillar(db, org_id, None, name='Foreign plan', plan_id=str(pb_id))
            ok("a theme on another club's plan is refused", False, 'it was allowed')
        except ValueError as e:
            ok("a theme on another club's plan is refused", True, str(e))
        await db.rollback()

        # An objective takes its plan FROM its theme, whatever the caller sent.
        made = await svc.upsert_objective(db, org_id, None,
                                          title='Follows its theme',
                                          plan_id=str(p2_id), pillar_id=str(fac))
        await db.commit()
        ok('an objective takes its plan from its theme, not from the caller',
           str(made['plan_id']) == str(p1_id), str(made['plan_id']))
        mismatch_id = uuid.UUID(str(made['id']))

    # ── deleting, and what it reaches ─────────────────────────────────────
    async with S() as db:
        # A theme delete reaches its own plan's objectives and nothing else.
        assert await svc.delete_pillar(db, org_id, vol)
        await db.commit()
        db.expire_all()
        left = {r[0] for r in (await db.execute(
            select(ClubObjective.id).where(ClubObjective.organisation_id == org_id))).all()}
        ok("deleting a theme takes its own objectives", ids['roster'] not in left)
        ok("deleting a theme leaves the other plan's objectives alone",
           ids['nets'] in left and ids['shed'] in left)
        ok('an action whose objective was deleted is kept',
           await db.get(CommitteeTask, task_id) is not None)

    async with S() as db:
        # A plan delete takes its own themes and their objectives, and no more.
        assert await svc.delete_plan(db, org_id, p1_id)
        await db.commit()
        db.expire_all()
        left = {r[0] for r in (await db.execute(
            select(ClubObjective.id).where(ClubObjective.organisation_id == org_id))).all()}
        ok('deleting a plan takes its objectives', not {ids['nets'], ids['shed']} & left)
        ok('deleting a plan takes the objective that followed its theme', mismatch_id not in left)
        ok('deleting a plan leaves the carrier plan\'s work alone',
           ids['under'] in left and ids['nowhere'] in left)

        themes_left = {r[0] for r in (await db.execute(
            select(ClubStrategicPillar.id).where(ClubStrategicPillar.organisation_id == org_id))).all()}
        ok('deleting a plan takes its themes', fac not in themes_left)
        ok('deleting a plan leaves another plan\'s themes', loose in themes_left)

        t = await db.get(CommitteeTask, task_id)
        m = await db.get(MeetingMotion, motion_id)
        await db.refresh(t); await db.refresh(m)
        ok('the action outlives the whole plan', t is not None)
        ok('the action simply stops being linked', t.objective_id is None)
        ok('the motion outlives the whole plan', m is not None)
        ok('the motion simply stops being linked', m.objective_id is None)

        ok("another club's plan is still untouched",
           await db.get(ClubStrategicPlan, pb_id) is not None)

    # ── the report a screen reads ─────────────────────────────────────────
    async with S() as db:
        rep = await svc.plan_report(db, org_id)
        ok('every objective in the report is on a plan',
           not (rep.get('unassigned') or {}).get('objective_list'))
        planned = {o['id'] for p in rep['plans'] for o in p['objective_list']}
        ok('the report carries the surviving objectives',
           {str(ids['under']), str(ids['nowhere'])} <= {str(i) for i in planned})
        ok('every theme in the report names its plan',
           all(p.get('plan_id') for p in rep['pillars']))

    await eng.dispose()
    bad = [c for c in C if not c[0]]
    print(f'{len(C) - len(bad)}/{len(C)} checks passed')
    sys.exit(1 if bad else 0)


asyncio.run(main())
