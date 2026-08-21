"""seed_sales_templates, against a real Postgres, through the shipped function.

The load-bearing case is a database that already holds the PREVIOUS seed: the
new key has to be inserted and the renamed row has to pick up its new name
without disturbing one a super admin has renamed themselves.
"""
import asyncio, os, sys, uuid
sys.path.insert(0, '/home/user/BetterStats/backend')
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres@/postgres?host=/var/tmp&port=55432')
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text
from app.models.db import Base, Organisation, CommsTemplate
from app.services import sales_email as se

C = []
def ok(n, c, e=''):
    C.append((c, n, e))
    if not c: print('FAIL:', n, e)

async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def names(db):
        rows = (await db.execute(
            select(CommsTemplate.sales_template_key, CommsTemplate.name, CommsTemplate.subject,
                   CommsTemplate.html)
            .where(CommsTemplate.sales_template_key.isnot(None)))).all()
        return {k: (n, s, h) for k, n, s, h in rows}

    async with S() as db:
        org = Organisation(id=uuid.uuid4(), name='BetterCricket', slug='bettercricket',
                           is_marketing_outreach=True)
        db.add(org); await db.commit()

        # ── a database carrying the PREVIOUS seed, incl. the old name ─────
        db.add_all([
            CommsTemplate(organisation_id=org.id, sales_template_key=k,
                          name=('Email following voicemail - offer to extend trial'
                                if k == 'voicemail_followup_extend_trial' else se._db_name(k)),
                          subject='old', html='<p>old</p>')
            for k in ('information', 'voicemail_followup', 'voicemail_followup_extend_trial',
                      'trial_information', 'trial_extension', 'demo', 'subscribe', 'custom')
        ])
        await db.commit()

        inserted = await se.seed_sales_templates(db)
        await db.commit()
        got = await names(db)

        ok('the new key is seeded exactly once', inserted == 1, str(inserted))
        ok('the approaching-expiry template exists',
           'voicemail_followup_extend_trial_soon' in got, str(sorted(got)))
        ok('it is named for a trial approaching expiry',
           got.get('voicemail_followup_extend_trial_soon', ('',))[0]
           == 'Email following voicemail. Trial approaching expiry - offer to extend',
           str(got.get('voicemail_followup_extend_trial_soon')))
        ok('the existing row is renamed for an expired trial',
           got['voicemail_followup_extend_trial'][0]
           == 'Email following voicemail. Trial expired - offer to extend',
           str(got['voicemail_followup_extend_trial']))
        ok('the renamed row keeps the html a rep may have edited',
           got['voicemail_followup_extend_trial'][2] == '<p>old</p>',
           got['voicemail_followup_extend_trial'][2])
        ok('the new row carries its own body, not the old one',
           "finishes shortly" in got['voicemail_followup_extend_trial_soon'][2],
           got['voicemail_followup_extend_trial_soon'][2][:120])
        ok('and its merge tokens survived (no .format() collapse)',
           '{{first_name}}' in got['voicemail_followup_extend_trial_soon'][2]
           and '{{club}}' in got['voicemail_followup_extend_trial_soon'][2],
           got['voicemail_followup_extend_trial_soon'][2][:160])
        ok('the seeded link points at the login page',
           '/login' in got['voicemail_followup_extend_trial_soon'][2])

        # ── running it again changes nothing ─────────────────────────────
        again = await se.seed_sales_templates(db)
        await db.commit()
        ok('a second run inserts nothing', again == 0, str(again))
        ok('and renames nothing further', (await names(db)) == got)

        # ── a super admin's own name is never overwritten ─────────────────
        await db.execute(text(
            "UPDATE comms_templates SET name = 'My own name' "
            "WHERE sales_template_key = 'voicemail_followup_extend_trial'"))
        await db.commit()
        await se.seed_sales_templates(db)
        await db.commit()
        got2 = await names(db)
        ok("a hand-renamed row keeps the super admin's name",
           got2['voicemail_followup_extend_trial'][0] == 'My own name',
           str(got2['voicemail_followup_extend_trial'][0]))

        # ── the two built bodies actually differ ──────────────────────────
        s1, h1, t1 = se._render_template_hardcoded(
            'voicemail_followup_extend_trial_soon',
            contact_name='Jack', club_name='Applecross CC', rep_name='Elton')
        s2, h2, t2 = se._render_template_hardcoded(
            'voicemail_followup_extend_trial',
            contact_name='Jack', club_name='Applecross CC', rep_name='Elton')
        ok('the approaching-expiry email says the trial finishes shortly', 'finishes shortly' in h1, h1[:160])
        ok('the expired email says the trial has finished', 'has finished' in h2, h2[:160])
        ok('the two bodies are not the same email', h1 != h2)
        ok('both name the club', 'Applecross CC' in h1 and 'Applecross CC' in h2)
        ok('both greet the contact', 'Hi Jack,' in h1 and 'Hi Jack,' in h2)

        # ── the dropdown order a rep sees ────────────────────────────────
        keys = list(se.TEMPLATE_LABELS)
        ok('approaching expiry precedes already expired',
           keys.index('voicemail_followup_extend_trial_soon')
           < keys.index('voicemail_followup_extend_trial'), str(keys))
        ok('both sit under the general voicemail follow-up',
           keys.index('voicemail_followup') < keys.index('voicemail_followup_extend_trial_soon'), str(keys))

    await eng.dispose()
    p = sum(1 for c, *_ in C if c)
    print(f'\n{p}/{len(C)} checks passed')
    for c, n, e in C:
        if not c: print('  x', n, e)
    sys.exit(0 if p == len(C) else 1)

asyncio.run(main())
