// Checks lib/trialStatus.js against the reported case (Shoalwater Bay: paid
// BetterStats, every other module's self-serve trial expired) and its
// neighbours. Run: node verification/verify_trial_status_paying.mjs
import * as ts from '../src/lib/trialStatus.js'
const { trialStatus } = ts
const moduleList = ts.moduleList || (() => '(missing)')

let pass = 0, fail = 0
const check = (label, ok, detail = '') => {
  ok ? pass++ : fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${ok ? '' : `  -> ${detail}`}`)
}
const DAY = 86400000
const iso = (d) => new Date(Date.now() + d * DAY).toISOString()
const user = (mods) => ({ id: 1, role: 'club_admin', entitlements: { billing_modules: mods } })
const paid = { module: 'core', name: 'BetterStats', status: 'active', live: true, trial_ends_at: iso(-13) }
const exp = (k, n) => ({ module: k, name: n, status: 'trial', live: false, trial_ends_at: iso(-13) })
const run = (k, n, d) => ({ module: k, name: n, status: 'trial', live: true, trial_ends_at: iso(d) })

// 1. The reported case: nothing to say.
const s1 = trialStatus(user([paid, exp('select', 'BetterSelect'), exp('socials', 'BetterSocials'), exp('iq', 'BetterIQ')]))
check('paid BetterStats + expired trials: no banner', s1 === null, JSON.stringify(s1))

// 2. Paying club with one module still on trial: named, never "expired".
const s2 = trialStatus(user([paid, exp('select', 'BetterSelect'), run('iq', 'BetterIQ', 4)]))
check('paying club with a running trial is still nudged', !!s2)
check('...marked as paying', s2?.paying === true)
check('...not reported as expired', s2?.expired === false)
check('...names only the running module', JSON.stringify(s2?.names) === '["BetterIQ"]', JSON.stringify(s2?.names))
check('...pre-ticks only the running module', s2?.subscribePath === '/admin/account?subscribe=iq', s2?.subscribePath)
check('...counts down from it', s2?.daysLeft === 4, s2?.daysLeft)

// 3. Unpaid club whose trial ended: still told access is gone (it is).
const s3 = trialStatus(user([exp('core', 'BetterStats'), exp('select', 'BetterSelect')]))
check('unpaid club with expired trial: still "ended"', s3?.expired === true && s3?.paying === false)

// 4. Unpaid club mid-trial: unchanged behaviour.
const s4 = trialStatus(user([run('core', 'BetterStats', 6), run('select', 'BetterSelect', 6)]))
check('unpaid mid-trial club: nudged, not expired, not paying', s4 && !s4.expired && !s4.paying && s4.daysLeft === 6)

// 5. A paid row that is not live (paused org) does not count as paying.
const s5 = trialStatus(user([{ ...paid, live: false }, exp('select', 'BetterSelect')]))
check('a non-live paid row does not suppress the notice', s5?.expired === true)

// 6. past_due still counts as paying.
const s6 = trialStatus(user([{ ...paid, status: 'past_due' }, exp('select', 'BetterSelect')]))
check('past_due BetterStats + expired trial: no banner', s6 === null)

check('moduleList: one', moduleList(['A']) === 'A')
check('moduleList: three', moduleList(['A', 'B', 'C']) === 'A, B and C')

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
