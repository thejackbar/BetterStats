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

        # Two keys are new against that seed now: the approaching-expiry
        # sibling, and the trial-offer voicemail added after it.
        ok('the new keys are seeded exactly once each', inserted == 2, str(inserted))
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

        # ── the trial-offer voicemail ─────────────────────────────────────
        K = 'voicemail_followup_trial_offer'
        ok('the trial-offer template exists', K in got, str(sorted(got)))
        ok('it carries the short Comms name the ask specified',
           got[K][0] == 'Email following VM. Trial offer', str(got[K][0]))
        ok('its dropdown label is the one the ask specified',
           se.TEMPLATE_LABELS[K] == 'Email following voicemail - trial offer',
           se.TEMPLATE_LABELS[K])
        ok('its body is copied from trial information, the same six steps',
           all(x in got[K][2] for x in ('Search for your club', 'Create your admin account',
                                        '14-day trial')),
           got[K][2][:200])
        ok('and the same Start your trial button',
           '/trial' in got[K][2] and 'Start your trial' in got[K][2], got[K][2][:200])
        ok('it opens on the voicemail line the other follow-ups share',
           "left a voicemail" in got[K][2], got[K][2][:200])
        ok('its merge tokens survived (no .format() collapse)',
           '{{first_name}}' in got[K][2] and '{{club}}' in got[K][2], got[K][2][:160])
        ok('its subject is the trial-information subject',
           got[K][1] == se._SEED_SUBJECT['trial_information'], str(got[K][1]))
        ok('it is not byte-for-byte the trial information template',
           got[K][2] != got['trial_information'][2])

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

        # ── the built body, and how it relates to trial information ──────
        s3, h3, t3 = se._render_template_hardcoded(
            K, contact_name='Jack', club_name='Applecross CC', rep_name='Elton')
        s4, h4, t4 = se._render_template_hardcoded(
            'trial_information', contact_name='Jack', club_name='Applecross CC', rep_name='Elton')
        ok('the built trial-offer email carries the trial steps',
           'Create your admin account' in h3 and '/trial' in h3, h3[:200])
        ok('it opens with the voicemail line', "left a voicemail" in h3, h3[:200])
        ok('trial information itself does NOT mention a voicemail',
           "left a voicemail" not in h4, h4[:200])
        ok('the two are not the same email', h3 != h4)
        ok('its plain-text half carries the voicemail line too',
           "left a voicemail" in t3, t3[:160])
        ok('both name the club and greet the contact',
           'Applecross CC' in h3 and 'Hi Jack,' in h3)

        # ── the dropdown order a rep sees ────────────────────────────────
        keys = list(se.TEMPLATE_LABELS)
        ok('approaching expiry precedes already expired',
           keys.index('voicemail_followup_extend_trial_soon')
           < keys.index('voicemail_followup_extend_trial'), str(keys))
        ok('both sit under the general voicemail follow-up',
           keys.index('voicemail_followup') < keys.index('voicemail_followup_extend_trial_soon'), str(keys))
        ok('offering a trial precedes extending one',
           keys.index(K) < keys.index('voicemail_followup_extend_trial_soon'), str(keys))
        ok('and it sits IMMEDIATELY after the general voicemail follow-up',
           keys.index(K) == keys.index('voicemail_followup') + 1, str(keys))

        # ── every built-in is complete ───────────────────────────────────
        ok('every built-in template has a label, a seed body and a seed subject',
           all(k in se.TEMPLATE_LABELS and k in se._SEED_BODY and k in se._SEED_SUBJECT
               for k in se.BUILT_IN_TEMPLATES), str(se.BUILT_IN_TEMPLATES))
        ok('every seeded row landed in the database',
           set(se.BUILT_IN_TEMPLATES) <= set(got), str(sorted(set(se.BUILT_IN_TEMPLATES) - set(got))))

    await eng.dispose()
    p = sum(1 for c, *_ in C if c)
    print(f'\n{p}/{len(C)} checks passed')
    for c, n, e in C:
        if not c: print('  x', n, e)
    sys.exit(0 if p == len(C) else 1)

asyncio.run(main())
