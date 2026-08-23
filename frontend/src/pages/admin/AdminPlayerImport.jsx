import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import Dropdown from '../../components/Dropdown'
import { PbSpinner } from '../../lib/presskit'
import { genderLabel, battingHandLabel, bowlingLabel, ageFromDob } from '../../lib/playerAttributes'

// ── the columns this importer understands ────────────────────────────────────
// Player name is required, matched by NameColumnFields below (one combined
// column with a word-order format, or separate first-name/surname columns) —
// it isn't in this flat list because it needs its own mode toggle, not a
// single FieldRow. Everything else is optional and only updates a player
// when the cell has a value (a blank never overwrites).
const FIELDS = [
  ['email', 'Email', false, ''],
  ['phone', 'Phone / mobile', false, ''],
  ['squad', 'Squad (selection pool)', false, 'Assign the player to a selection-pool team.'],
  ['player_role', 'Role', false, 'Batter, Bowler, All Rounder, Keeper…'],
  ['batting_hand', 'Batting hand', false, 'Right / Left handed.'],
  ['bowling', 'Bowling', false, 'e.g. Right-arm fast-medium, Off spin.'],
  ['gender', 'Gender', false, 'Male / Female.'],
  ['date_of_birth', 'Date of birth', false, '2012-03-04, 4 Mar 2012 or 04/03/2012 (day first).'],
  ['is_opening_batsman', 'Opening batter', false, 'Yes / No.'],
  ['is_overseas', 'Overseas player', false, 'Yes / No.'],
  ['overseas_country', 'Overseas country', false, 'Filling this in marks them overseas.'],
  ['status', 'Active / inactive', false, 'Inactive hides them from availability and selection.'],
  ['is_public', 'Show on public website', false, 'Show / Hide.'],
  ['financial', 'Fees status', false, 'Financial / Not financial. Only sets it, clear it on the profile.'],
  ['training', 'Training', false, 'At training / Not at training.'],
]
const FIELD_LABEL = {
  player_name: 'Player name', player_first_name: 'First name', player_last_name: 'Surname',
  ...Object.fromEntries(FIELDS.map(([k, l]) => [k, l])),
}

// Mirrors import_ingest.NAME_FORMAT_LABELS on the backend.
const NAME_FORMAT_OPTIONS = [
  ['auto', 'Auto-detect (recommended)'],
  ['first_last', 'First name then Surname: e.g. "Jack Barendse"'],
  ['last_first', 'Surname then First name: e.g. "Barendse Jack" or "Barendse, Jack"'],
]

const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'

// ── per-field display for the review screen (codes → human labels) ───────────
const yesNo = (v) => (v === true ? 'Yes' : v === false ? 'No' : '—')
// A date of birth arrives as an ISO string on both sides of the comparison
// (the server sends what it holds and what it would write), so the age it
// works out to comes from the shared helper rather than a second parser.
const dobFmt = (v) => {
  if (!v) return '—'
  const iso = String(v).slice(0, 10)
  const age = ageFromDob(iso)
  return age == null ? iso : `${iso} · ${age} yrs`
}
const SIMPLE = {
  email: { label: 'Email', fmt: (v) => v || '—' },
  phone: { label: 'Phone', fmt: (v) => v || '—' },
  gender: { label: 'Gender', fmt: (v) => genderLabel(v) || '—' },
  player_role: { label: 'Role', fmt: (v) => v || '—' },
  batting_hand: { label: 'Batting', fmt: (v) => battingHandLabel(v) || '—' },
  date_of_birth: { label: 'Born', fmt: dobFmt },
  is_opening_batsman: { label: 'Opener', fmt: yesNo },
  is_overseas: { label: 'Overseas', fmt: yesNo },
  overseas_country: { label: 'Country', fmt: (v) => v || '—' },
  status: { label: 'Status', fmt: (v) => (v === 'inactive' ? 'Inactive' : v === 'active' ? 'Active' : '—') },
  is_public: { label: 'Website', fmt: (v) => (v === false ? 'Hidden' : v === true ? 'Shown' : '—') },
  is_financial_override: { label: 'Fees', fmt: (v) => (v === true ? 'Financial' : v === false ? 'Not financial' : 'Automatic') },
  trained_override: { label: 'Training', fmt: (v) => (v === true ? 'At training' : v === false ? 'Not at training' : 'Automatic') },
}
function changeRows(p) {
  const rows = []
  const cur = p.current || {}, prop = p.proposed || {}
  for (const f of ['email', 'phone', 'gender', 'player_role', 'batting_hand',
                   'date_of_birth', 'is_opening_batsman', 'is_overseas', 'overseas_country',
                   'status', 'is_public', 'is_financial_override', 'trained_override']) {
    if (f in prop) rows.push({ label: SIMPLE[f].label, from: SIMPLE[f].fmt(cur[f]), to: SIMPLE[f].fmt(prop[f]) })
  }
  if ('bowling_action' in prop || 'bowling_type' in prop) {
    const na = ('bowling_action' in prop) ? prop.bowling_action : cur.bowling_action
    const nt = ('bowling_type' in prop) ? prop.bowling_type : cur.bowling_type
    rows.push({ label: 'Bowling', from: bowlingLabel(cur.bowling_action, cur.bowling_type), to: bowlingLabel(na, nt) })
  }
  if (p.squad && ['set', 'change', 'new'].includes(p.squad.action)) {
    rows.push({
      label: 'Squad',
      from: p.current_squad_name || '—',
      to: p.squad.action === 'new' ? `${p.squad.name} · new team` : p.squad.name,
    })
  }
  return rows
}

function Pct({ score }) {
  if (score == null) return null
  const tone = score >= 0.85 ? 'text-green-300' : score >= 0.6 ? 'text-pb-amber' : 'text-pb-red/60'
  return <span className={`font-mono text-[10px] ${tone}`}>{Math.round(score * 100)}%</span>
}

function StatusBadge({ status }) {
  const map = {
    exact: ['MATCHED', 'text-green-300 border-green-300/30'],
    manual: ['CHOSEN', 'text-green-300 border-green-300/30'],
    fuzzy: ['REVIEW', 'text-pb-amber border-pb-amber/30'],
    none: ['NO MATCH', 'text-pb-red/70 border-pb-red/30'],
    ambiguous: ['MERGE FIRST', 'text-pb-red/70 border-pb-red/30'],
    new: ['NEW PLAYER', 'text-pb-accent border-pb-accent/40'],
    skip: ['SKIP', 'text-pb-faint border-pb-faint/30'],
  }
  const [label, tone] = map[status] || [status?.toUpperCase() || '—', 'text-pb-faint border-pb-faint/30']
  return <span className={`font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 ${tone}`}>{label}</span>
}

const STEP_LABELS = { upload: 'Upload', map: 'Columns', players: 'Players', squads: 'Squads', review: 'Review' }

// One column-mapping row: "BetterStats field ← your column", with the field's
// own note underneath. FIELDS has carried a hint per field since it was
// written and nothing ever drew it — which only started to matter with the
// date of birth, where "04/03/2012 is 4 March" is the difference between a
// junior's age being right and being three weeks out.
function FieldRow({ field, label, required, hint, value, headers, conf, onMap }) {
  return (
    <div className={`rounded px-2 py-1.5 border ${value ? 'border-green-300/30' : 'pb-hairline'}`}>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold text-green-300 w-36 shrink-0 leading-tight">
          {label}{required && <span className="text-pb-red/70 ml-0.5">*</span>}
        </span>
        <span className="text-pb-faintest text-[11px] shrink-0" aria-hidden>←</span>
        <select className={`${cell} flex-1 min-w-0 text-pb-text`} value={value || ''} onChange={(e) => onMap(field, e.target.value)}>
          <option value="">not in my file</option>
          {headers.map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
        {conf != null && <Pct score={conf} />}
      </div>
      {hint && <div className="text-[10.5px] text-pb-faintest leading-snug mt-1 ml-[152px]">{hint}</div>}
    </div>
  )
}

// Player name mapping: one combined column (with an explicit word-order format
// so "Surname Firstname" isn't silently misread) or two separate first/surname
// columns (unambiguous by construction — the sheet already tells us which part
// is which). Toggling mode clears the other mode's mapping.
function NameColumnFields({ nameMode, setNameMode, nameFormat, setNameFormat, mapping, setMap, headers, confByField }) {
  return (
    <div className="mb-2">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className="text-[11px] font-semibold text-green-300 shrink-0 leading-tight">
          Player name<span className="text-pb-red/70 ml-0.5">*</span>
        </span>
        <div className="flex gap-1">
          {[['single', 'ONE COLUMN'], ['split', 'FIRST NAME + SURNAME']].map(([m, label]) => (
            <button key={m} type="button" onClick={() => setNameMode(m)}
              className={`font-mono text-[9px] tracking-wide2 px-2.5 py-1 rounded border ${nameMode === m ? 'text-pb-bg border-transparent' : 'text-pb-faint pb-hairline hover:text-pb-text'}`}
              style={nameMode === m ? { background: 'var(--pb-accent)' } : undefined}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {nameMode === 'single' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <FieldRow field="player_name" label={FIELD_LABEL.player_name} required
            value={mapping.player_name} headers={headers} conf={confByField.player_name} onMap={setMap} />
          <div className="flex items-center gap-2 rounded px-2 py-1.5 border pb-hairline">
            <span className="text-[11px] font-semibold text-pb-faint w-16 shrink-0 leading-tight">Format</span>
            <select className={`${cell} flex-1 min-w-0 text-pb-text`} value={nameFormat} onChange={(e) => setNameFormat(e.target.value)}>
              {NAME_FORMAT_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <FieldRow field="player_first_name" label={FIELD_LABEL.player_first_name}
            value={mapping.player_first_name} headers={headers} conf={confByField.player_first_name} onMap={setMap} />
          <FieldRow field="player_last_name" label={FIELD_LABEL.player_last_name} required
            value={mapping.player_last_name} headers={headers} conf={confByField.player_last_name} onMap={setMap} />
        </div>
      )}
      <p className="text-[11px] text-pb-faint mt-1.5 leading-relaxed max-w-2xl">
        {nameMode === 'single'
          ? 'One name column. Pick the word order it\'s written in so "Surname Firstname" isn\'t misread as first-name-first.'
          : 'Two separate columns match unambiguously, no format guess needed. A surname-only sheet also works, just leave First name unmapped.'}
      </p>
    </div>
  )
}

// ── searchable picker (renders a handful of options at a time, scales to
//    thousands of players without freezing) ───────────────────────────────────
function valueLabel(value, idName, kind) {
  if (!value) return kind === 'squad' ? 'Leave unset' : 'Skip (unmatched)'
  if (value === '__new__') return kind === 'squad' ? '+ Create new team' : '+ Create new player'
  if (value === '__skip__') return kind === 'squad' ? 'Leave unset' : 'Skip'
  return idName.get(value) || '(selected)'
}

function SearchSelect({ value, idName, candidates, options, onChange, kind }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    const base = ql ? options.filter((o) => (o.name || '').toLowerCase().includes(ql)) : options
    return base.slice(0, 25)
  }, [q, options])
  const pick = (v) => { onChange(v); setOpen(false); setQ('') }
  const item = 'block w-full text-left px-2 py-1 text-[12px] text-pb-dim hover:bg-pb-surface2 hover:text-pb-text rounded'
  const unresolved = !value
  return (
    <div className="relative max-w-md" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)}
        className={`${cell} w-full text-left flex items-center justify-between ${unresolved ? 'text-pb-amber' : ''}`}>
        <span className="truncate">{valueLabel(value, idName, kind)}</span>
        <span className="text-pb-faint ml-2">▾</span>
      </button>
      <Dropdown anchorRef={ref} open={open} onClose={() => setOpen(false)} align="start" width={288} maxHeight={300}
        className="bg-pb-surface border pb-hairline rounded shadow-xl p-1">
        <button className={item} onClick={() => pick('__new__')}>{kind === 'squad' ? '+ Create new team' : '+ Create new player'}</button>
        <button className={item} onClick={() => pick('__skip__')}>{kind === 'squad' ? 'Leave unset' : 'Skip this player'}</button>
        {(candidates || []).length > 0 && <div className="px-2 pt-2 pb-1 font-mono text-[9px] tracking-wide2 text-pb-faint">SUGGESTED</div>}
        {(candidates || []).map((c) => (
          <button key={c.id} className={`${item} leading-tight py-1.5`} onClick={() => pick(c.id)}>
            <span className="flex items-center justify-between gap-2">
              <span className="truncate">{c.name}</span>
              {c.confidence != null && <span className="text-pb-faint shrink-0">{Math.round(c.confidence * 100)}%</span>}
            </span>
          </button>
        ))}
        <div className="px-1 pt-2 pb-1 sticky top-0">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search all ${kind === 'squad' ? 'teams' : 'players'}…`}
            className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
        </div>
        {filtered.map((o) => <button key={o.id} className={item} onClick={() => pick(o.id)}>{o.name}</button>)}
        {filtered.length === 0 && <div className="px-2 py-1 text-[11px] text-pb-faint">No matches</div>}
      </Dropdown>
    </div>
  )
}

const PAGE_SIZE = 50
const RESOLVED = ['exact', 'manual']

// ── player matching, three passes: confirm matched / review close / no-match ──
function PlayerMatch({ rows, allPlayers, overrides, setOverride, setOverridesBulk, loading, nextLabel, onNext, onBack }) {
  const [tab, setTab] = useState(null)
  const [page, setPage] = useState(0)

  const idName = useMemo(() => {
    const m = new Map()
    allPlayers.forEach((o) => m.set(o.id, o.name))
    rows.forEach((r) => {
      (r.candidates || []).forEach((c) => m.set(c.player_id, c.name))
      if (r.matched_name && r.player_id) m.set(r.player_id, r.matched_name)
    })
    return m
  }, [allPlayers, rows])

  const buckets = useMemo(() => {
    const matched = [], close = [], nomatch = []
    rows.forEach((r) => {
      if (RESOLVED.includes(r.status)) matched.push(r)
      else if (['fuzzy', 'ambiguous'].includes(r.status)) close.push(r)
      else nomatch.push(r) // none, new, skip
    })
    return { matched, close, nomatch }
  }, [rows])

  useEffect(() => {
    if (tab === null && rows.length) setTab(buckets.close.length ? 'close' : buckets.nomatch.length ? 'nomatch' : 'matched')
  }, [rows, buckets, tab])
  useEffect(() => { setPage(0) }, [tab])

  const active = tab || 'matched'
  const list = buckets[active] || []
  const pageCount = Math.max(1, Math.ceil(list.length / PAGE_SIZE))
  const safe = Math.min(page, pageCount - 1)
  const pageRows = list.slice(safe * PAGE_SIZE, safe * PAGE_SIZE + PAGE_SIZE)
  const valueFor = (r) => { const ov = overrides[r.raw_name]; if (ov) return ov; if (r.player_id) return r.player_id; return '' }

  const uniqueClose = useMemo(() => buckets.close.filter((r) => (r.candidates || []).length === 1 && r.status !== 'ambiguous'), [buckets.close])

  function confirmUnique() {
    const patch = {}
    uniqueClose.forEach((r) => { patch[r.raw_name] = r.candidates[0].player_id })
    setOverridesBulk(patch)
  }
  function bulkNomatch(val) {
    const patch = {}; buckets.nomatch.forEach((r) => { patch[r.raw_name] = val }); setOverridesBulk(patch)
  }

  const TABS = [
    ['matched', '1. Matched', buckets.matched.length],
    ['close', '2. Review close', buckets.close.length],
    ['nomatch', '3. No match', buckets.nomatch.length],
  ]

  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">Match players</h2>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          Exact name matches link automatically. Confirm the close ones, and decide what to do with any name we
          don't recognise: create a new player, point it at an existing one, or skip it. Skipped and unconfirmed
          rows are left out of the import.
        </p>
        {loading && rows.length === 0 ? (
          <div className="py-10 text-center"><PbSpinner message="Matching players…" /></div>
        ) : (
          <>
            <div className="flex gap-1 mb-4 flex-wrap">
              {TABS.map(([k, label, n]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border ${active === k ? 'text-pb-bg border-transparent' : 'text-pb-faint pb-hairline hover:text-pb-text'}`}
                  style={active === k ? { background: 'var(--pb-accent)' } : undefined}>
                  {label} ({n})
                </button>
              ))}
            </div>

            {active === 'matched' && (
              <p className="text-[12px] text-green-300 mb-3">
                {buckets.matched.length} name{buckets.matched.length === 1 ? '' : 's'} matched a player exactly, so there's nothing to do unless one looks wrong.
              </p>
            )}
            {active === 'close' && buckets.close.length > 0 && (
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <p className="text-[12px] text-pb-amber">Pick the right player, create a new one, or skip.</p>
                {uniqueClose.length > 0 && (
                  <button onClick={confirmUnique} className="ml-auto font-mono text-[10px] tracking-wide2 rounded px-3 py-1.5 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
                    CONFIRM {uniqueClose.length} SINGLE MATCH{uniqueClose.length === 1 ? '' : 'ES'}
                  </button>
                )}
              </div>
            )}
            {active === 'nomatch' && buckets.nomatch.length > 0 && (
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <p className="text-[12px] text-pb-faint">No player like this exists. These are <span className="text-pb-faint">skipped</span> by default. Create them as new players, or pick an existing one.</p>
                <button onClick={() => bulkNomatch('__new__')} className="ml-auto font-mono text-[10px] tracking-wide2 border border-pb-accent/40 text-pb-accent rounded px-3 py-1.5 hover:bg-pb-accent/10">CREATE ALL NEW</button>
                <button onClick={() => bulkNomatch('__skip__')} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text">SKIP ALL</button>
              </div>
            )}

            <div className="overflow-x-auto overflow-y-visible">
              <table className="w-full text-[12px] min-w-[560px]">
                <thead>
                  <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                    <th className="py-2 pr-2">NAME IN SHEET</th>
                    <th className="py-2 pr-2 w-28">STATUS</th>
                    <th className="py-2 pr-2">MATCH TO</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((r, i) => {
                    const candidates = (r.candidates || []).map((c) => ({ id: c.player_id, name: c.name, confidence: c.confidence }))
                    return (
                      <tr key={r.raw_name + i} className="pb-hairline-t align-middle">
                        <td className="py-2 pr-2 text-pb-text">
                          {r.raw_name}
                          {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                        </td>
                        <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                        <td className="py-2 pr-2">
                          <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allPlayers}
                            onChange={(v) => setOverride(r.raw_name, v)} kind="player" />
                        </td>
                      </tr>
                    )
                  })}
                  {list.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-pb-dim text-[12px]">Nothing in this pass.</td></tr>}
                </tbody>
              </table>
            </div>
            {pageCount > 1 && (
              <div className="flex items-center gap-2 mt-3 font-mono text-[10px] text-pb-faint justify-end">
                <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safe === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
                {safe + 1} / {pageCount}
                <button onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={safe >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
              </div>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>{nextLabel}</button>
      </div>
    </>
  )
}

// ── squad matching (compact; only when a squad column is mapped) ──────────────
function SquadMatch({ rows, allTeams, overrides, setOverride, loading, onNext, onBack }) {
  const idName = useMemo(() => {
    const m = new Map()
    allTeams.forEach((o) => m.set(o.id, o.name))
    rows.forEach((r) => {
      (r.candidates || []).forEach((c) => m.set(c.team_id, c.name))
      if (r.matched_name && r.team_id) m.set(r.team_id, r.matched_name)
    })
    return m
  }, [allTeams, rows])
  const valueFor = (r) => { const ov = overrides[r.raw_label]; if (ov) return ov; if (r.team_id) return r.team_id; return '' }

  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">Match squads</h2>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          Each squad name in your file maps to a selection-pool team. Exact names link automatically; pick a team for
          the rest, create a new one, or leave it unset. Squad is optional, so anything left unset just won't change.
        </p>
        {loading && rows.length === 0 ? (
          <div className="py-10 text-center"><PbSpinner message="Matching squads…" /></div>
        ) : (
          <div className="overflow-x-auto overflow-y-visible">
            <table className="w-full text-[12px] min-w-[480px]">
              <thead>
                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                  <th className="py-2 pr-2">SQUAD IN SHEET</th>
                  <th className="py-2 pr-2 w-28">STATUS</th>
                  <th className="py-2 pr-2">TEAM</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const candidates = (r.candidates || []).map((c) => ({ id: c.team_id, name: c.name, confidence: c.confidence }))
                  return (
                    <tr key={r.raw_label + i} className="pb-hairline-t align-middle">
                      <td className="py-2 pr-2 text-pb-text">{r.raw_label}</td>
                      <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                      <td className="py-2 pr-2">
                        <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allTeams}
                          onChange={(v) => setOverride(r.raw_label, v)} kind="squad" />
                      </td>
                    </tr>
                  )
                })}
                {rows.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-pb-dim text-[12px]">No squad values in your file.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>NEXT: REVIEW →</button>
      </div>
    </>
  )
}

// ── review + commit ──────────────────────────────────────────────────────────
function ReviewStep({ resolved, resolving, committing, committed, onCommit, onBack, onReset }) {
  const [showUnchanged, setShowUnchanged] = useState(false)

  if (committed) {
    return (
      <div className="pb-card p-6">
        <div className="font-mono text-[10px] tracking-wide2 text-green-300 mb-2">IMPORT COMPLETE</div>
        <h2 className="font-display font-bold text-xl text-pb-text mb-3">
          {committed.players_updated} player{committed.players_updated === 1 ? '' : 's'} updated{committed.players_created ? `, ${committed.players_created} created` : ''}
        </h2>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed max-w-2xl">
          {committed.fields_written} field{committed.fields_written === 1 ? '' : 's'} set
          {committed.squads_assigned ? `, ${committed.squads_assigned} squad assignment${committed.squads_assigned === 1 ? '' : 's'}` : ''}.
          {committed.rows_skipped ? ` ${committed.rows_skipped} unmatched row${committed.rows_skipped === 1 ? ' was' : 's were'} skipped.` : ''}
        </p>
        <div className="flex gap-3">
          <button onClick={onReset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>IMPORT ANOTHER</button>
          <Link to="/admin/players" className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text">VIEW PLAYERS</Link>
        </div>
      </div>
    )
  }

  const preview = resolved?.preview || []
  const changing = preview.filter((p) => p.change_count > 0)
  const unchanged = preview.filter((p) => p.change_count === 0)
  const shown = showUnchanged ? preview : changing
  const totals = resolved?.totals || {}

  return (
    <>
      {(resolved?.warnings || []).map((w, i) => (
        <div key={i} className="pb-card p-3 mb-3 border-l-2 border-pb-amber/50">
          <span className="text-[12px] text-pb-amber">{w}</span>
        </div>
      ))}
      <div className="pb-card p-5 mb-4">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h2 className="font-display font-semibold text-lg text-pb-text">Review changes</h2>
          <span className="font-mono text-[10px] text-pb-faint">
            {changing.length} changing · {totals.players_new || 0} new · {totals.rows_skipped || 0} skipped{resolving ? ' · syncing…' : ''}
          </span>
        </div>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          Only the fields with a value in your file are shown. <span className="text-pb-dim">An empty cell never overwrites
          what a player already has.</span> Check the before → after below, then import.
        </p>

        {unchanged.length > 0 && (
          <button onClick={() => setShowUnchanged((v) => !v)} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2.5 py-1 text-pb-faint hover:text-pb-text mb-3">
            {showUnchanged ? 'HIDE' : 'SHOW'} {unchanged.length} ALREADY UP TO DATE
          </button>
        )}

        <div className="space-y-2">
          {shown.slice(0, 400).map((p) => {
            const rows = changeRows(p)
            return (
              <div key={p.player_id || `new:${p.raw_name}`} className="border pb-hairline rounded px-3 py-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-pb-text text-[13px] font-semibold">{p.player_name}</span>
                  {p.new && <span className="font-mono text-[8px] tracking-wide2 text-pb-accent border border-pb-accent/40 rounded px-1 py-0.5">NEW</span>}
                  {rows.length === 0 && <span className="font-mono text-[9px] text-pb-faint">no change</span>}
                </div>
                {rows.length > 0 && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5">
                    {rows.map((c, j) => (
                      <div key={j} className="flex items-baseline gap-2 text-[12px]">
                        <span className="font-mono text-[9px] tracking-wide2 text-pb-faint w-16 shrink-0">{c.label.toUpperCase()}</span>
                        <span className="text-pb-faint line-through decoration-pb-faint/40 truncate">{c.from}</span>
                        <span className="text-pb-faintest" aria-hidden>→</span>
                        <span className="text-green-300 truncate">{c.to}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          {resolving && preview.length === 0 && <div className="py-8 text-center"><PbSpinner message="Working out changes…" /></div>}
          {!resolving && changing.length === 0 && unchanged.length === 0 && (
            <div className="py-4 text-center text-pb-dim text-[12px]">No matched players yet. Go back and match some names.</div>
          )}
          {!resolving && changing.length === 0 && unchanged.length > 0 && !showUnchanged && (
            <div className="py-4 text-center text-pb-dim text-[12px]">Every matched player is already up to date, so there's nothing to change.</div>
          )}
        </div>
        {changing.length > 400 && (
          <p className="font-mono text-[10px] text-pb-faintest mt-2">Showing the first 400 of {changing.length}. All will be imported.</p>
        )}

        {(resolved?.notes || []).length > 0 && (
          <details className="mt-4">
            <summary className="font-mono text-[10px] tracking-wide2 text-pb-faint cursor-pointer">{resolved.notes.length} cell(s) couldn't be read, left unchanged</summary>
            <ul className="mt-2 text-[11px] text-pb-faint space-y-0.5">
              {resolved.notes.map((n, i) => <li key={i}>· {n}</li>)}
            </ul>
          </details>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onCommit} disabled={committing || (changing.length === 0)}
          className="ml-auto px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          {committing ? 'IMPORTING…' : `IMPORT ${changing.length} PLAYER${changing.length === 1 ? '' : 'S'}`}
        </button>
      </div>
    </>
  )
}

export default function AdminPlayerImport() {
  const toast = useToast()
  const [step, setStep] = useState('upload')
  const [file, setFile] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [parsed, setParsed] = useState(null)
  const [mapping, setMapping] = useState({})
  const [confByField, setConfByField] = useState({})
  const [nameMode, setNameModeRaw] = useState('single')   // single column vs first+surname
  const [nameFormat, setNameFormat] = useState('auto')     // word order, single-column mode only
  const [playerOverrides, setPlayerOverrides] = useState({})
  const [squadOverrides, setSquadOverrides] = useState({})
  const [resolved, setResolved] = useState(null)
  const [resolving, setResolving] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [allTeams, setAllTeams] = useState([])

  useEffect(() => {
    api.adminListPlayers().then((p) => setAllPlayers((p || []).map((x) => ({ id: x.id, name: x.display_name || x.name })))).catch(() => {})
    api.bsListTeams().then((t) => setAllTeams((t || []).map((x) => ({ id: x.id, name: x.name })))).catch(() => setAllTeams([]))
  }, [])

  const hasSquad = !!mapping.squad
  const steps = useMemo(
    () => hasSquad ? ['upload', 'map', 'players', 'squads', 'review'] : ['upload', 'map', 'players', 'review'],
    [hasSquad],
  )

  // Keep the change preview fresh as the mapping / matches change (debounced).
  // Waits for a name column to be mapped — without it /resolve 422s.
  const nameReady = nameMode === 'split' ? !!mapping.player_last_name : !!mapping.player_name
  useEffect(() => {
    if (!parsed || !nameReady) return
    let cancelled = false
    setResolving(true)
    const payload = { rows: parsed.rows, mapping, name_format: nameFormat, player_overrides: playerOverrides, squad_overrides: squadOverrides }
    const t = setTimeout(() => {
      api.playerImportResolve(payload)
        .then((r) => { if (!cancelled) setResolved(r) })
        .catch((e) => { if (!cancelled) toast.error(e.message) })
        .finally(() => { if (!cancelled) setResolving(false) })
    }, 200)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parsed, JSON.stringify(mapping), nameFormat, JSON.stringify(playerOverrides), JSON.stringify(squadOverrides)])

  async function runParse() {
    if (!file) return
    setParsing(true); setParsed(null); setResolved(null); setCommitted(null)
    setPlayerOverrides({}); setSquadOverrides({})
    setNameModeRaw('single'); setNameFormat('auto')
    try {
      const p = await api.playerImportPreview(file)
      const m = {}, c = {}
      Object.entries(p.mapping_suggestions || {}).forEach(([f, v]) => { m[f] = v.column; c[f] = v.confidence })
      // A sheet with separate first-name/surname columns auto-suggests both —
      // switch straight to split mode so the match isn't sitting one tab over.
      if ((m.player_first_name || m.player_last_name) && !m.player_name) setNameModeRaw('split')
      setParsed(p); setMapping(m); setConfByField(c)
      setStep('map')
      toast.success(`Parsed ${p.row_count} row${p.row_count === 1 ? '' : 's'}`)
    } catch (e) { toast.error(e.message) } finally { setParsing(false) }
  }

  function setMap(field, col) {
    setMapping((m) => { const n = { ...m }; if (col) n[field] = col; else delete n[field]; return n })
    setConfByField((c) => ({ ...c, [field]: undefined }))
  }
  // Switching name mode clears the OTHER mode's mapping, so a stale player_name
  // (or first/last) mapping from before the switch can't linger and silently
  // win server-side (resolve_row_name prefers first/last whenever either is set).
  function setNameMode(mode) {
    setNameModeRaw(mode)
    if (mode === 'split') { setMap('player_name', '') }
    else { setMap('player_first_name', ''); setMap('player_last_name', '') }
  }
  function setPOverride(name, val) {
    setPlayerOverrides((o) => { const n = { ...o }; if (val === '') delete n[name]; else n[name] = val; return n })
  }
  function setPOverridesBulk(patch) { setPlayerOverrides((o) => ({ ...o, ...patch })) }
  function setSOverride(label, val) {
    setSquadOverrides((o) => { const n = { ...o }; if (val === '') delete n[label]; else n[label] = val; return n })
  }

  const mapReady = nameReady
  const mappedValueFields = FIELDS.filter(([k]) => mapping[k]).map(([k]) => k)

  async function commit() {
    setCommitting(true)
    try {
      const res = await api.playerImportCommit({
        rows: parsed.rows, mapping, name_format: nameFormat, filename: file?.name,
        player_overrides: playerOverrides, squad_overrides: squadOverrides,
      })
      setCommitted(res)
      toast.success(`Updated ${res.players_updated} player${res.players_updated === 1 ? '' : 's'}`)
    } catch (e) { toast.error(e.message) } finally { setCommitting(false) }
  }

  function reset() {
    setStep('upload'); setFile(null); setParsed(null); setResolved(null); setCommitted(null)
    setMapping({}); setPlayerOverrides({}); setSquadOverrides({})
    setNameModeRaw('single'); setNameFormat('auto')
  }

  return (
    <BetterStatsLayout>
      <div className="max-w-5xl">
        <Link to="/admin/players" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← PLAYERS</Link>
        <h1 className="font-display font-bold text-2xl text-pb-text mt-2 mb-1">Import player details</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed max-w-3xl">
          Upload a spreadsheet to fill in player details in bulk. Mainly email and phone, plus any of squad,
          role, batting hand, bowling, gender, date of birth, opening batter, overseas, active or inactive,
          website visibility, fees and training. We match each row to a player by name (the same smart
          matching used across the site) and show you exactly what will change before anything is saved.
        </p>

        {/* Stepper */}
        <div className="flex items-center gap-1 mb-6 flex-wrap">
          {steps.map((s, i) => {
            const active = s === step
            const done = steps.indexOf(step) > i
            const reachable = parsed || s === 'upload'
            return (
              <button key={s} disabled={!reachable} onClick={() => reachable && setStep(s)}
                className={`font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border transition-colors ${
                  active ? 'text-pb-bg border-transparent' : done ? 'text-green-300 border-green-300/30' : 'text-pb-faint pb-hairline'
                } ${!reachable ? 'opacity-40 cursor-not-allowed' : 'hover:text-pb-text'}`}
                style={active ? { background: 'var(--pb-accent)' } : undefined}>
                {i + 1}. {STEP_LABELS[s]}
              </button>
            )
          })}
          {resolving && <span className="font-mono text-[10px] text-pb-faint ml-2">syncing…</span>}
        </div>

        {/* Upload */}
        {step === 'upload' && (
          <div className="pb-card p-5 mb-6">
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
              <div>
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">CSV OR EXCEL FILE</label>
                <input type="file" accept=".csv,.xlsx,.xlsm,text/csv"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="block text-pb-dim text-sm file:bg-pb-surface2 file:border file:pb-hairline file:rounded file:px-3 file:py-1.5 file:mr-3 file:font-mono file:text-[10px] file:text-pb-text file:cursor-pointer" />
              </div>
              <button onClick={runParse} disabled={!file || parsing}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
                {parsing ? 'PARSING…' : 'PARSE FILE'}
              </button>
            </div>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              One row per player, a Name column plus whichever details you have. Headers can be anything, we map them next.{' '}
              Start from a template:{' '}
              <a href="/api/club-admin/player-import/template.xlsx" className="text-pb-accent hover:underline">Excel with dropdowns</a>
              {' '}(Role, Batting, Bowling, Gender, Opening batter, Overseas, Status, Website, Fees, Training
              and your BetterSelect squads are all pick lists){' '}or{' '}
              <a href="/api/club-admin/player-import/template.csv" className="text-pb-accent hover:underline">plain CSV</a>.
            </p>
          </div>
        )}
        {parsing && <PbSpinner message="Parsing file…" />}

        {/* Map columns */}
        {step === 'map' && parsed && (
          <>
            <div className="pb-card p-5 mb-4">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">MATCH YOUR COLUMNS</div>
                <span className="font-mono text-[10px] text-pb-faint">{parsed.row_count} rows · {parsed.headers.length} columns</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-4 pb-3 pb-hairline-b">
                <span className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
                  <span className="inline-block w-2.5 h-2.5 rounded-sm bg-green-300/80"></span>BetterStats field
                </span>
                <span className="text-pb-faintest text-[11px]" aria-hidden>←</span>
                <span className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
                  <span className="inline-block w-2.5 h-2.5 rounded-sm bg-pb-text/80 border pb-hairline"></span>your column
                </span>
                <span className="text-pb-faintest text-[10px] sm:ml-1">Only Name is required. Map whichever details you have and leave the rest blank.</span>
              </div>
              <NameColumnFields nameMode={nameMode} setNameMode={setNameMode} nameFormat={nameFormat} setNameFormat={setNameFormat}
                mapping={mapping} setMap={setMap} headers={parsed.headers} confByField={confByField} />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {FIELDS.map(([f, label, required, hint]) => (
                  <FieldRow key={f} field={f} label={label} required={required} hint={hint}
                    value={mapping[f]} headers={parsed.headers} conf={confByField[f]} onMap={setMap} />
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {!mapReady && <span className="font-mono text-[10px] text-pb-red/70">Map the Player name column to continue.</span>}
              {mapReady && mappedValueFields.length === 0 && (
                <span className="font-mono text-[10px] text-pb-amber">Map at least one detail column (e.g. Email), otherwise there's nothing to import.</span>
              )}
              <button onClick={() => setStep('players')} disabled={!mapReady}
                className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                NEXT: MATCH PLAYERS →
              </button>
            </div>
          </>
        )}

        {/* Match players */}
        {step === 'players' && (
          <PlayerMatch
            rows={(resolved?.players) || []} allPlayers={allPlayers}
            overrides={playerOverrides} setOverride={setPOverride} setOverridesBulk={setPOverridesBulk}
            loading={resolving}
            nextLabel={hasSquad ? 'NEXT: SQUADS →' : 'NEXT: REVIEW →'}
            onNext={() => setStep(hasSquad ? 'squads' : 'review')}
            onBack={() => setStep('map')}
          />
        )}

        {/* Match squads */}
        {step === 'squads' && (
          <SquadMatch
            rows={(resolved?.squads) || []} allTeams={allTeams}
            overrides={squadOverrides} setOverride={setSOverride} loading={resolving}
            onNext={() => setStep('review')} onBack={() => setStep('players')}
          />
        )}

        {/* Review & commit */}
        {step === 'review' && (
          <ReviewStep
            resolved={resolved} resolving={resolving} committing={committing} committed={committed}
            onCommit={commit} onBack={() => setStep(hasSquad ? 'squads' : 'players')} onReset={reset}
          />
        )}
      </div>
    </BetterStatsLayout>
  )
}
