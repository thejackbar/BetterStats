import { useState, useEffect, useRef } from 'react'
import { api } from '../../../lib/api'

// The two field sets an audience rule can be built from, and the row that edits
// one. Split out of CommsSegments so the two mounts can never share a field set
// by accident.
//
// ⚠ SCOPE RULE (docs/design_handoff_betterclubhouse/PROJECT_RULES.md).
// BetterComms serves two audiences from one engine and they stay strictly
// separated:
//   · Club scope — a club officer emailing their own people. CLUB_FIELD_DEFS,
//     and nothing else. This is what BetterAdmin's Segments screen imports.
//   · Super Admin scope — BetterCricket's own marketing against the Clubs
//     Directory. DIRECTORY_FIELD_DEFS is that field set and it must never be
//     reachable from a club build: not behind a dropdown, not greyed out, not
//     listed and disabled. It is imported by the super-admin mount only.
// Apply the same rule to any future module that gains a platform-side mode.

const STAT_OPS = [['gte', 'at least'], ['lte', 'at most']]
const IS_OP = [['eq', 'is']]
const YESNO = [['yes', 'yes'], ['no', 'no']]

// The six modules a prospect can trial / request, by entitlement key.
const MODULE_OPTS = [
  ['core', 'BetterStats'], ['select', 'BetterSelect'], ['socials', 'BetterSocials'],
  ['admin', 'BetterAdmin'], ['iq', 'BetterIQ'], ['fantasy', 'BetterFantasyCricket'],
]

// ── Club scope ───────────────────────────────────────────────────────────────
// A normal club's members and their cricket data. Stat / role / availability
// fields read the linked player, so they narrow to the playing squad
// automatically. Fields with an `optionsKey` pull their dropdown values from
// /segments/options (the club's real roles / teams), so we never guess vocab.
export const CLUB_FIELD_DEFS = {
  tag: { label: 'Has tag', input: 'text', ops: [['has', 'is']] },
  // The one condition that reads the ledger rather than the roster. Resolved
  // server-side from the same fees calculation the Accounts screen runs, so
  // "email everyone who owes" targets exactly the people that screen shows.
  owes_money: {
    label: 'Owes money', input: 'select', ops: IS_OP,
    options: [['yes', 'yes, still owes'], ['no', 'no, settled or in credit']],
  },
  source: {
    label: 'In the directory as', input: 'select', ops: IS_OP,
    options: [['player', 'A player'], ['member', 'A fee member'], ['import', 'Imported'], ['manual', 'Added manually']],
  },
  role: { label: 'Player role', input: 'select', ops: IS_OP, optionsKey: 'roles' },
  gender: { label: 'Gender', input: 'select', ops: IS_OP, optionsKey: 'genders' },
  squad_team: { label: 'Squad / team', input: 'select', ops: IS_OP, optionsKey: 'teams' },
  availability: {
    label: 'Availability', input: 'select', ops: IS_OP,
    options: [['available', 'available for an upcoming game'], ['not_set', 'no availability set']],
  },
  matches_this_season: { label: 'Matches this season', input: 'number', ops: STAT_OPS },
  runs_this_season: { label: 'Runs this season', input: 'number', ops: STAT_OPS },
  wickets_this_season: { label: 'Wickets this season', input: 'number', ops: STAT_OPS },
  catches_this_season: { label: 'Catches this season', input: 'number', ops: STAT_OPS },
  fifties_this_season: { label: 'Fifties this season', input: 'number', ops: STAT_OPS },
  hundreds_this_season: { label: 'Hundreds this season', input: 'number', ops: STAT_OPS },
  five_wickets_this_season: { label: '5-wicket hauls this season', input: 'number', ops: STAT_OPS },
}

// ── Super Admin scope — NEVER import this from a club-facing screen ──────────
// A prospect club / its officer and what they have done. Each reads telemetry
// we already hold (exports, sent/open/click events, enquiries, club + customer
// status), so a campaign can target who has or hasn't done something today.
export const DIRECTORY_FIELD_DEFS = {
  tag: { label: 'Has tag', input: 'text', ops: [['has', 'is']] },
  exported: { label: 'Exported from directory', input: 'select', ops: IS_OP, options: YESNO },
  emailed: { label: 'Emailed via BetterComms', input: 'select', ops: IS_OP, options: YESNO },
  opened: { label: 'Opened an email', input: 'select', ops: IS_OP, options: YESNO },
  clicked: { label: 'Clicked an email link', input: 'select', ops: IS_OP, options: YESNO },
  enquired: { label: 'Sent a Contact Us enquiry', input: 'select', ops: IS_OP, options: YESNO },
  visited_page: {
    label: 'Visited a page', input: 'multi', ops: [['eq', 'is any of']],
    options: [
      ['stats', 'BetterStats page'], ['select', 'BetterSelect page'], ['socials', 'BetterSocials page'],
      ['admin', 'BetterAdmin page'], ['betteriq', 'BetterIQ page'], ['fantasy', 'BetterFantasyCricket page'],
      ['pricing', 'Pricing page'], ['compare', 'Compare page'], ['about', 'About page'],
      ['faq', 'FAQ page'], ['contact', 'Contact Us page'], ['any', 'Any page'],
    ],
  },
  is_trialing: { label: 'Is trialing module', input: 'multi', ops: [['eq', 'is any of']], options: MODULE_OPTS },
  requested_trial: { label: 'Requested a trial', input: 'multi', ops: [['eq', 'is any of']], options: MODULE_OPTS },
  had_demo: {
    label: 'Had a demo', input: 'multi', ops: [['eq', 'is any of']],
    options: [['in_trial', 'In a trial'], ['trial_expired', 'Trial has expired'], ['customer', 'Is now a customer']],
  },
  // Where the club sits on BetterCricket's OWN sales pipeline. Won / not won
  // partitions every directory club, so a single select answers both directions
  // — no need for the multi-select the primary-admin rule below needs. Won-ness
  // is read from the deal's STAGE, not its status field, the same rule the
  // commission report follows; an archived deal is off the pipeline and does
  // not count.
  deal_won: {
    label: 'Sales pipeline stage', input: 'select', ops: IS_OP,
    options: [['won', 'Won'], ['not_won', 'Anything but Won']],
  },
  // Whether anybody at the club actually runs it. The three states partition
  // every directory club, which is what lets one rule both include and exclude:
  // pick "Nobody assigned" to target the clubs a super admin set up that no real
  // contact ever took over (in practice, test clubs), or pick the other two to
  // leave them out. A club that was never onboarded is deliberately its OWN
  // state rather than being lumped in with the unassigned — it has no club
  // record to have an admin, and folding it in would make "exclude the clubs
  // with no primary admin" quietly drop every prospect in the directory.
  primary_admin: {
    label: 'Club primary admin', input: 'multi', ops: [['eq', 'is any of']],
    options: [
      ['assigned', 'Someone is assigned'],
      ['unassigned', 'Nobody assigned (club is on the platform)'],
      ['not_onboarded', 'Club is not on the platform'],
    ],
  },
  // Naming a club or a person outright, rather than describing them. Both are
  // ORDINARY rules and are ANDed with the others, so "is any of" NARROWS the
  // audience to what is picked — it does not add those people on top of what the
  // rest of the rules matched. "is none of" is the counterpart, and is what
  // takes a test club or one person out of a send.
  club_is: {
    label: 'Specific club', input: 'search', entityKind: 'club',
    ops: [['in', 'is any of'], ['not_in', 'is none of']],
  },
  contact_is: {
    label: 'Specific contact', input: 'search', entityKind: 'contact',
    ops: [['in', 'is any of'], ['not_in', 'is none of']],
  },
  customer_status: {
    label: 'Customer status', input: 'select', ops: IS_OP,
    options: [['none', 'not a customer'], ['trial', 'on a trial'], ['active', 'active customer'], ['lapsed', 'lapsed / paused']],
  },
  // Where the club's own trial stands, read off its subscription rows. The same
  // definition resolves {{trial_days_left}} / {{trial_days_since_expiry}} /
  // {{trial_end_date}}, so the number the email prints is the number the
  // audience was picked on. A club with no tracked trial has no day count and
  // so can never be caught by a bound on its own.
  trial_status: {
    label: 'Club trial', input: 'select', ops: IS_OP,
    options: [['in_trial', 'is running now'], ['expired', 'has expired'], ['none', 'no trial on record']],
  },
  trial_days_left: { label: 'Days left in trial', input: 'number', ops: STAT_OPS },
  trial_days_since_expiry: { label: 'Days since trial expired', input: 'number', ops: STAT_OPS },
  directory_status: {
    label: 'Directory status', input: 'select', ops: IS_OP,
    options: [['new', 'new'], ['enriched', 'enriched'], ['contacted', 'contacted'], ['onboarded', 'onboarded'], ['suppressed', 'suppressed']],
  },
  club_state: { label: 'Club state', input: 'select', ops: IS_OP, optionsKey: 'states' },
  association: { label: 'Association', input: 'select', ops: IS_OP, optionsKey: 'associations' },
  country: { label: 'Country', input: 'select', ops: IS_OP, optionsKey: 'countries' },
  page_views: { label: 'Page views', input: 'number', ops: STAT_OPS },
  distinct_visitors: { label: 'Users viewing', input: 'number', ops: STAT_OPS },
  engagement_score: { label: 'Engagement score', input: 'number', ops: STAT_OPS },
}

export function newRule(defs) {
  const first = Object.keys(defs)[0]
  return { field: first, op: defs[first].ops[0][0], value: '' }
}

// Resolve a field's dropdown options from the fetched club/directory options.
export function optionsFor(def, opts) {
  if (def.options) return def.options
  if (def.optionsKey === 'roles') return (opts.roles || []).map(r => [r, r])
  if (def.optionsKey === 'genders') return opts.genders || []
  if (def.optionsKey === 'teams') return (opts.teams || []).map(t => [t.id, t.name])
  if (def.optionsKey === 'states') return (opts.states || []).map(s => [s, s])
  if (def.optionsKey === 'associations') return (opts.associations || []).map(a => [a, a])
  if (def.optionsKey === 'countries') return (opts.countries || []).map(c => [c, c])
  return []
}

// Multi-select rule value: pick one or more [value, label] options. The rule
// value is stored as an array of the chosen value keys.
export function MultiSelectValues({ options, selected, onChange, inputCls }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [])
  const sel = Array.isArray(selected) ? selected : []
  const toggle = (v) => onChange(sel.includes(v) ? sel.filter(x => x !== v) : [...sel, v])
  const labels = options.filter(([v]) => sel.includes(v)).map(([, l]) => l)
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 max-w-[240px] ${inputCls}`}>
        <span className="truncate">{labels.length ? labels.join(', ') : 'choose…'}</span>
        {sel.length > 0 && (
          <span role="button" title="Clear" className="text-pb-faint hover:text-pb-red"
            onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-60 max-h-72 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          {options.map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 px-1 py-0.5 text-sm text-pb-text hover:bg-pb-surface rounded cursor-pointer">
              <input type="checkbox" className="accent-pb-accent" checked={sel.includes(v)} onChange={() => toggle(v)} />
              <span className="truncate">{l}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

// Rule value that NAMES rows (clubs, contacts) rather than describing them.
// The server searches, so a directory of thousands is never shipped to the
// browser to draw a dropdown somebody is about to type into anyway — the same
// call PersonSearch makes. Chosen ids are re-fetched alongside every search so a
// saved rule renders its names before anybody types, and a chosen row can always
// be seen and un-picked even once the search box has moved on.
export function SearchMultiSelect({ kind, selected, onChange, inputCls }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [options, setOptions] = useState([])
  const [chosen, setChosen] = useState([])
  const [loading, setLoading] = useState(false)
  const ref = useRef(null)
  const seq = useRef(0)
  const sel = Array.isArray(selected) ? selected : (selected ? [selected] : [])
  const selKey = sel.join(',')

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [])

  useEffect(() => {
    // Debounced, and a response is DROPPED if the box has moved on since — a
    // slow search for "sm" must not land on top of the results for "smith".
    const mine = ++seq.current
    setLoading(true)
    const t = setTimeout(() => {
      api.commsSegmentEntities(kind, q, selKey ? selKey.split(',') : [])
        .then(r => {
          if (seq.current !== mine) return
          setOptions(r?.options || [])
          setChosen(r?.chosen || [])
        })
        .catch(() => { if (seq.current === mine) { setOptions([]) } })
        .finally(() => { if (seq.current === mine) setLoading(false) })
    }, 220)
    return () => clearTimeout(t)
  }, [kind, q, selKey])

  const toggle = (id) => onChange(sel.includes(id) ? sel.filter(x => x !== id) : [...sel, id])
  const rest = options.filter(o => !sel.includes(o.id))
  const label = chosen.length
    ? (chosen.length <= 2 ? chosen.map(c => c.label).join(', ') : `${chosen.length} chosen`)
    : (sel.length ? `${sel.length} chosen` : 'choose…')

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 max-w-[240px] ${inputCls}`}>
        <span className="truncate">{label}</span>
        {sel.length > 0 && (
          <span role="button" title="Clear" className="text-pb-faint hover:text-pb-red"
            onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-72 max-h-80 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          <input autoFocus value={q} onChange={e => setQ(e.target.value)}
            placeholder={kind === 'club' ? 'Search clubs…' : 'Search name or email…'}
            className="w-full mb-2 px-2 py-1.5 rounded bg-pb-surface text-pb-text border pb-hairline text-sm" />
          {chosen.map(o => (
            <Row key={o.id} o={o} checked onToggle={() => toggle(o.id)} />
          ))}
          {chosen.length > 0 && rest.length > 0 && (
            <div className="my-1.5 border-t pb-hairline-t" />
          )}
          {rest.map(o => <Row key={o.id} o={o} checked={false} onToggle={() => toggle(o.id)} />)}
          {!loading && rest.length === 0 && chosen.length === 0 && (
            <div className="px-1 py-2 text-xs text-pb-dim">
              {q ? 'Nothing matched.' : 'Start typing to search.'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ o, checked, onToggle }) {
  return (
    <label className="flex items-start gap-2 px-1 py-1 text-sm text-pb-text hover:bg-pb-surface rounded cursor-pointer">
      <input type="checkbox" className="accent-pb-accent mt-0.5" checked={checked} onChange={onToggle} />
      <span className="min-w-0">
        <span className="block truncate">{o.label}</span>
        {o.hint && o.hint !== o.label && (
          <span className="block truncate text-xs text-pb-dim">{o.hint}</span>
        )}
      </span>
    </label>
  )
}

// One `field · operator · value · remove` row. `inputCls` lets a caller dress
// the controls in its own screen's language.
export function RuleRow({ rule, defs, opts, onChange, onRemove, inputCls = 'px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm' }) {
  const def = defs[rule.field] || defs[Object.keys(defs)[0]]
  const keys = Object.keys(defs)
  return (
    <div className="flex flex-wrap items-center gap-2 py-1.5">
      <select value={rule.field}
        onChange={e => {
          const nd = defs[e.target.value]
          onChange({ field: e.target.value, op: nd.ops[0][0], value: '' })
        }}
        className={inputCls}>
        {keys.map(k => <option key={k} value={k}>{defs[k].label}</option>)}
      </select>
      <select value={rule.op} onChange={e => onChange({ ...rule, op: e.target.value })} className={inputCls}>
        {def.ops.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      {def.input === 'search' ? (
        <SearchMultiSelect kind={def.entityKind} inputCls={inputCls}
          selected={rule.value}
          onChange={(vals) => onChange({ ...rule, value: vals })} />
      ) : def.input === 'multi' ? (
        <MultiSelectValues options={optionsFor(def, opts)} inputCls={inputCls}
          selected={Array.isArray(rule.value) ? rule.value : (rule.value ? [rule.value] : [])}
          onChange={(vals) => onChange({ ...rule, value: vals })} />
      ) : def.input === 'select' ? (
        <select value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          className={`${inputCls} max-w-[200px]`}>
          <option value="">choose…</option>
          {optionsFor(def, opts).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ) : (
        <input value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          type={def.input === 'number' ? 'number' : 'text'}
          placeholder={def.input === 'number' ? '0' : 'e.g. Committee'}
          className={`${inputCls} w-32`} />
      )}
      <button onClick={onRemove} className="text-pb-faint hover:text-pb-red text-sm px-1" title="Remove condition">✕</button>
    </div>
  )
}
