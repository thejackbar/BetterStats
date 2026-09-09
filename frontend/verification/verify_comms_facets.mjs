import { readFileSync } from 'fs'
const src = readFileSync('/home/user/BetterStats/frontend/src/pages/admin/bettercomms/audience.jsx', 'utf8')

// Lift the real shipped code out of the file — never a retyped copy.
const grab = (re, what) => { const m = src.match(re); if (!m) throw new Error('could not lift ' + what); return m[0] }
const code = [
  grab(/export const FACETS = \[[\s\S]*?\n\]/, 'FACETS'),
  grab(/export function emptyFilters\(\) \{[\s\S]*?\n\}/, 'emptyFilters'),
  grab(/export function matchesFilters\([\s\S]*?\n\}/, 'matchesFilters'),
  grab(/export function facetOptionsFrom\([\s\S]*?\n\}/, 'facetOptionsFrom'),
].join('\n').replace(/^export /gm, '')

const { FACETS, emptyFilters, facetOptionsFrom, matchesFilters } =
  await import('data:text/javascript,' + encodeURIComponent(code +
    '\nexport { FACETS, emptyFilters, facetOptionsFrom, matchesFilters }'))

let pass = 0, fail = 0
const check = (name, fn) => {
  try { const r = fn(); r ? (pass++, console.log(`  ok   ${name}`)) : (fail++, console.log(`  FAIL ${name}`)) }
  catch (e) { fail++; console.log(`  FAIL ${name} -> ${e.message}`) }
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// The reported crash: the screen loads before any contact has arrived.
check('no contacts at all does not throw', () => !!facetOptionsFrom([]))
check('null contacts does not throw', () => !!facetOptionsFrom(null))
check('a club contact carrying no directory fields does not throw',
  () => !!facetOptionsFrom([{ name: 'A', email: 'a@b.c' }]))

// Every facet in the kit is answered, none missing, none extra.
check('every FACETS key is present in the options',
  () => eq(Object.keys(facetOptionsFrom([])).sort(), FACETS.map(f => f.key).sort()))
check('every FACETS key is present in emptyFilters',
  () => eq(Object.keys(emptyFilters()).sort(), FACETS.map(f => f.key).sort()))
check('role is one of them (migration 295)', () => FACETS.some(f => f.key === 'role'))

// The 800+ exported directory rows: role must actually reach the picker.
const exported = [
  { name: 'A', role: 'Secretary', club: 'Applecross', state: 'WA' },
  { name: 'B', role: 'Treasurer', club: 'Applecross', state: 'WA' },
  { name: 'C', role: 'Secretary', club: 'High Wycombe', state: 'WA' },
]
// Every read goes through `check` so an absent/throwing part is REPORTED,
// not left to kill the run and hide every check below it.
check('role options are collected, de-duplicated and sorted',
  () => eq(facetOptionsFrom(exported).role, ['Secretary', 'Treasurer']))
check('the other facets still work as before',
  () => eq(facetOptionsFrom(exported).club, ['Applecross', 'High Wycombe']))
check('a facet nobody carries stays empty, so it is never offered',
  () => eq(facetOptionsFrom(exported).country, []))

// The filter the picker then drives.
check('filtering on a role keeps only that role',
  () => exported.filter(c => matchesFilters(c, { ...emptyFilters(), role: ['Secretary'] })).length === 2)
check('an untouched filter keeps everybody',
  () => exported.filter(c => matchesFilters(c, emptyFilters())).length === 3)

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
