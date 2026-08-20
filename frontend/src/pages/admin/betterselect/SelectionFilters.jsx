// The Selection pool's filter bar. One shared system across both board views:
//   row 1  — search · sort popover · Filters button (active-count badge)
//   row 2  — quick role chips (Bat/Bowl/All/WK) · Hide unavailable · recency
//   panel  — Availability · Bowling · Batting hand · Form groups, plus the
//            searchable Squad picker and the compact Selection-status control
//   below  — removable active-filter pills + Clear all, and an "X of Y" count.
//
// State lives in the URL via useFilters (filters.jsx) so it survives navigation
// and is shareable; this component only composes the presentation. The long
// squad list is handled by SquadPicker (search + quick picks); selection status
// is a 3-way segmented control rather than yet another checkbox.
import { useState } from 'react'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import { Icon, Chip, Search, RecencySelect, Dot, Segmented, FilterButton } from './ui'
import { SortMenu, SquadPicker } from './filters'
import { BOWL_KINDS, HAND_KINDS, FORM_BUCKETS, SORTS, ageFilterOptions, ageFilterLabel } from './selectionMeta'
import { RULE_FILTERS } from './selectionRules'

const ROLE_QUICK = [['BAT', 'Bat'], ['BWL', 'Bowl'], ['ALL', 'All'], ['WKT', 'WK']]
const ROLE_LABEL = { BAT: 'Batter', BWL: 'Bowler', ALL: 'All-rounder', WKT: 'Keeper' }
const STATUS_OPTS = [{ value: '', label: 'All' }, { value: 'unselected', label: 'Unselected' }, { value: 'clash', label: 'In another XI' }]
// Fees and training. Each carries a third answer — "Not known" — because a
// club that runs neither BetterFees nor Net Manager, and hasn't set the flag
// by hand on a player, genuinely has no answer for them, and that list is
// the useful one: it's who still has to be asked.
const FEES_OPTS = [
  { value: '', label: 'All' },
  { value: 'owing', label: 'Non-financial' },
  { value: 'financial', label: 'Paid up' },
  { value: 'unknown', label: 'Not known' },
]
const TRAINING_OPTS = [
  { value: '', label: 'All' },
  { value: 'trained', label: 'At training' },
  { value: 'missing', label: 'Not at training' },
  { value: 'unknown', label: 'Not known' },
]
const optLabel = (opts, v) => (opts.find((o) => o.value === v) || {}).label || v

function PanelGroup({ label, children }) {
  return (
    <div className="min-w-0">
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest pb-1 border-b border-pb-hairline">{label}</div>
      <div className="flex flex-col gap-0.5 mt-1.5">{children}</div>
    </div>
  )
}
/* Says where a flag's answer comes from, so "Not known" reads as a state of
 * the club's data rather than a broken filter. */
function SourceNote({ source, from, manual }) {
  return (
    <div className="text-[10.5px] leading-snug text-pb-faintest mt-1.5">{source ? from : manual}</div>
  )
}
function Check({ label, checked, onChange, dot }) {
  return (
    <label className="flex items-center gap-2 text-[12.5px] text-pb-dim hover:text-pb-text cursor-pointer py-0.5">
      <input type="checkbox" checked={checked} onChange={onChange} className="accent-pb-accent w-3.5 h-3.5 shrink-0" />
      {dot && <Dot status={dot} size={7} />}
      {label}
    </label>
  )
}

export default function SelectionFilters({ filters, sort, setSort, squadOptions, yearsF, setYearsF, count, total, flags, rules }) {
  const [open, setOpen] = useState(false)
  const { values, search, setSearch, toggle, setValue, setMulti, clearAll, activeCount } = filters
  const hideUnavail = !!values.hideUnavail
  // Empty for a club that hasn't switched ages on, and the whole group is
  // dropped rather than shown dead — the same call the Fees and Training
  // notes make about a filter their module can't answer.
  const ageOptions = ageFilterOptions(flags)
  // Same call for the club's own rules: no rule bearing on this fixture, no
  // group at all. A control that can only ever answer "everybody is fine" is
  // worse than none.
  const showRules = !!rules?.active
  // A club can switch the plain fees / training notes off entirely on the
  // Selection rules screen. When it has, the server sends no answer for them,
  // so there is nothing for these two groups to filter on and they go.
  const showFees = flags?.show_fees !== false
  const showTraining = flags?.show_training !== false

  const pills = []
  ;(values.role || []).forEach((r) => pills.push({ k: 'r' + r, label: ROLE_LABEL[r] || r, rm: () => toggle('role', r) }))
  ;(values.avail || []).forEach((s) => pills.push({ k: 'a' + s, label: AVAILABILITY[s]?.label || s, rm: () => toggle('avail', s) }))
  ;(values.bowling || []).forEach((b) => pills.push({ k: 'b' + b, label: (BOWL_KINDS.find((x) => x.value === b) || {}).label, rm: () => toggle('bowling', b) }))
  ;(values.hand || []).forEach((h) => pills.push({ k: 'h' + h, label: h === 'RIGHT' ? 'RHB' : 'LHB', rm: () => toggle('hand', h) }))
  ;(values.form || []).forEach((fm) => pills.push({ k: 'f' + fm, label: (FORM_BUCKETS.find((x) => x.value === fm) || {}).label, rm: () => toggle('form', fm) }))
  ;(values.squad || []).forEach((s) => pills.push({ k: 's' + s, label: (squadOptions.find((o) => o.value === s) || {}).label || s, rm: () => toggle('squad', s) }))
  if (values.status) pills.push({ k: 'st', label: values.status === 'unselected' ? 'Unselected' : 'In another XI', rm: () => setValue('status', '') })
  if (hideUnavail) pills.push({ k: 'hu', label: 'Hide unavailable', rm: () => setValue('hideUnavail', false) })
  if (showFees && values.fees) pills.push({ k: 'fee', label: optLabel(FEES_OPTS, values.fees), rm: () => setValue('fees', '') })
  if (showTraining && values.training) pills.push({ k: 'trn', label: optLabel(TRAINING_OPTS, values.training), rm: () => setValue('training', '') })
  if (values.age && ageFilterLabel(values.age, flags)) pills.push({ k: 'age', label: ageFilterLabel(values.age, flags), rm: () => setValue('age', '') })
  if (showRules && values.rules) pills.push({ k: 'rul', label: optLabel(RULE_FILTERS, values.rules), rm: () => setValue('rules', '') })
  // (recency has its own dedicated dropdown control, so it isn't duplicated as a pill)

  const resetAll = () => { clearAll(); setYearsF(0) }

  return (
    <div className="flex flex-col gap-2.5">
      {/* Row 1 — search · sort · filters */}
      <div className="flex items-center gap-2">
        <Search value={search} onChange={setSearch} placeholder="Search players…" className="flex-1 min-w-0" />
        <SortMenu value={sort} onChange={setSort} options={SORTS} />
        <FilterButton active={open} count={activeCount} onClick={() => setOpen((o) => !o)} />
      </div>

      {/* Row 2 — quick role chips + hide-unavailable + recency */}
      <div className="flex flex-wrap items-center gap-1.5">
        {ROLE_QUICK.map(([v, l]) => (
          <Chip key={v} label={l} active={(values.role || []).includes(v)} onClick={() => toggle('role', v)} />
        ))}
        <span className="h-4 w-px bg-pb-hairline2 mx-0.5" />
        <Chip label="Hide unavailable" dot={hideUnavail ? 'var(--pb-positive)' : undefined}
          active={hideUnavail} onClick={() => setValue('hideUnavail', !hideUnavail)} />
        <span className="ml-auto"><RecencySelect value={yearsF} onChange={setYearsF} /></span>
      </div>

      {/* Filters panel */}
      {open && (
        <div className="grid gap-x-5 gap-y-4 rounded-lg border border-pb-hairline2 bg-pb-surface2/40 p-3.5"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
          <PanelGroup label="Availability">
            {AVAIL_ORDER.map((s) => (
              <Check key={s} label={AVAILABILITY[s].label} dot={s}
                checked={(values.avail || []).includes(s)} onChange={() => toggle('avail', s)} />
            ))}
          </PanelGroup>
          <PanelGroup label="Bowling">
            {BOWL_KINDS.map((b) => (
              <Check key={b.value} label={b.label} checked={(values.bowling || []).includes(b.value)} onChange={() => toggle('bowling', b.value)} />
            ))}
          </PanelGroup>
          <PanelGroup label="Batting hand">
            {HAND_KINDS.map((h) => (
              <Check key={h.value} label={h.label} checked={(values.hand || []).includes(h.value)} onChange={() => toggle('hand', h.value)} />
            ))}
          </PanelGroup>
          <PanelGroup label="Form">
            {FORM_BUCKETS.map((f) => (
              <Check key={f.value} label={f.label} checked={(values.form || []).includes(f.value)} onChange={() => toggle('form', f.value)} />
            ))}
          </PanelGroup>
          {ageOptions.length > 0 && (
            <PanelGroup label="Age">
              <select value={values.age || ''} onChange={(e) => setValue('age', e.target.value)}
                className={`w-full bg-transparent text-[12.5px] rounded-md border px-2 py-1.5 focus:outline-none focus:border-pb-accent transition-colors ${
                  values.age ? 'text-pb-accent border-pb-accent/40' : 'text-pb-dim border-pb-hairline hover:text-pb-text'
                }`}>
                <option value="" className="bg-pb-surface text-pb-text">Any age</option>
                {ageOptions.map((o) => (
                  <option key={o.value} value={o.value} className="bg-pb-surface text-pb-text">{o.label}</option>
                ))}
              </select>
              <div className="text-[10.5px] leading-snug text-pb-faintest mt-1.5">
                {flags?.age?.under
                  ? `Ages are shown for players under ${flags.age.under}. Set a date of birth on a player's profile.`
                  : "Worked out from the date of birth on a player's profile."}
              </div>
            </PanelGroup>
          )}
          {showRules && (
            <PanelGroup label="Club rules">
              <Segmented sm value={values.rules || ''} onChange={(v) => setValue('rules', v)} options={RULE_FILTERS} />
              <div className="text-[10.5px] leading-snug text-pb-faintest mt-1.5">
                {(rules.applied || []).map((r) => r.name).join(' · ') || 'Your association rules.'}
              </div>
            </PanelGroup>
          )}
          <PanelGroup label="Squad">
            <SquadPicker options={squadOptions} selected={values.squad || []}
              onToggle={(v) => toggle('squad', v)} onSetMany={(arr) => setMulti('squad', arr)} />
          </PanelGroup>
          <PanelGroup label="Selection">
            <Segmented sm value={values.status || ''} onChange={(v) => setValue('status', v)} options={STATUS_OPTS} />
          </PanelGroup>
          {showFees && (
            <PanelGroup label="Fees">
              <Segmented sm value={values.fees || ''} onChange={(v) => setValue('fees', v)} options={FEES_OPTS} />
              <SourceNote
                source={flags?.financial}
                from="Read from BetterFees, or set on a player's profile."
                manual="Set on a player's profile — turn on BetterFees to have it worked out." />
            </PanelGroup>
          )}
          {showTraining && (
            <PanelGroup label="Training">
              <Segmented sm value={values.training || ''} onChange={(v) => setValue('training', v)} options={TRAINING_OPTS} />
              <SourceNote
                source={flags?.training}
                from={`At nets in the last ${flags?.training_window_days || 21} days, or set on a player's profile.`}
                manual="Set on a player's profile — run a Net Manager session to have it worked out." />
            </PanelGroup>
          )}
        </div>
      )}

      {/* Active pills */}
      {pills.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {pills.map((p) => (
            <button key={p.k} type="button" onClick={p.rm}
              className="inline-flex items-center gap-1 rounded-full bg-pb-accent/12 text-pb-accent text-[11.5px] font-medium pl-2.5 pr-1.5 py-1 hover:bg-pb-accent/22 transition">
              {p.label}<Icon name="close" size={11} className="opacity-70" />
            </button>
          ))}
          <button type="button" onClick={resetAll} className="text-[11.5px] text-pb-faint hover:text-pb-accent underline underline-offset-2 ml-1">Clear all</button>
        </div>
      )}

      <div className="text-[11.5px] text-pb-faint pb-num">{count} of {total} shown</div>
    </div>
  )
}
