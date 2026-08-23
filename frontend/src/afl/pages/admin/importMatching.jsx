// Shared wizard pieces for the three BetterFootball import tools — Import
// Stats (AflAdminImport.jsx, season totals per player), Import Results
// (AflAdminResultsImport.jsx, the matches themselves) and Import Awards
// (AflAdminAwardsImport.jsx, the honour board). All three walk the same
// road: map the columns, match the sheet's names and labels to the club's
// own, then confirm. Extracted from AflAdminImport so the later wizards
// reuse this rather than growing more copies that drift — exactly what
// produced four divergent UI kits on the cricket side.
//
// Ported originally from BetterStats (Core)'s BetterImport wizard
// (pages/admin/AdminImport.jsx): same visual language, same "never silently
// skip" rule.
import { useEffect, useMemo, useRef, useState } from 'react'
import LoadingSpinner from '../../../components/LoadingSpinner'
import Dropdown from '../../../components/Dropdown'

export const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'
export const num = n => Number(n || 0).toLocaleString()
// Rows per page in the match tables — a 1,900-name honours sheet is a real
// upload, not a hypothetical.
const PAGE_SIZE = 50

export function Pct({ score }) {
  if (score == null) return null
  const tone = score >= 0.85 ? 'text-green-300' : score >= 0.6 ? 'text-pb-amber' : 'text-pb-red/60'
  return <span className={`font-mono text-[10px] ${tone}`}>{Math.round(score * 100)}%</span>
}

export function StatusBadge({ status }) {
  const map = {
    exact: ['MATCHED', 'text-green-300 border-green-300/30'],
    manual: ['CHOSEN', 'text-green-300 border-green-300/30'],
    matched: ['MATCHED', 'text-green-300 border-green-300/30'],
    fuzzy: ['REVIEW', 'text-pb-amber border-pb-amber/30'],
    none: ['NO MATCH', 'text-pb-red/70 border-pb-red/30'],
    ambiguous: ['MERGE FIRST', 'text-pb-red/70 border-pb-red/30'],
    new: ['NEW PLAYER', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
    new_award: ['NEW AWARD', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
    // Two people in the sheet under one name — the import can't pick for you.
    clash: ['TWO PEOPLE', 'text-pb-red/70 border-pb-red/30'],
    skip: ['SKIP', 'text-pb-faint border-pb-faint/30'],
    unassigned: ['UNASSIGNED', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
    prior: ['UNASSIGNED', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
    own: ['AS-IS', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
  }
  const [label, tone] = map[status] || [status?.toUpperCase() || '—', 'text-pb-faint border-pb-faint/30']
  return <span className={`font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 ${tone}`}>{label}</span>
}

// player/season/grade rows key their match-to id differently — grades match
// on the grade's NAME (free text, no grade table row of its own to point at).
export function idField(kind) {
  if (kind === 'player') return 'player_id'
  if (kind === 'season') return 'season_id'
  if (kind === 'award') return 'definition_id'
  return 'grade_name'
}

export function candStatLine(p) {
  if (!p) return null
  const bits = []
  if (p.games) bits.push(`${num(p.games)} games`)
  if (p.goals) bits.push(`${num(p.goals)} goals`)
  return bits.length ? bits.join(' · ') : 'no stats at this club yet'
}

// One column-mapping row — reads left-to-right "field ← your column", green
// once matched, with the auto-match confidence shown alongside.
export function FieldRow({ field, label, required, value, headers, conf, matchedOn, onMap }) {
  return (
    <div className={`flex items-center gap-2 rounded px-2 py-1.5 border ${value ? 'border-green-300/30' : 'pb-hairline'}`}>
      <span className="text-[11px] font-semibold text-green-300 w-40 shrink-0 leading-tight">
        {label}{required && <span className="text-pb-red/70 ml-0.5">*</span>}
      </span>
      <span className="text-pb-faintest text-[11px] shrink-0" aria-hidden>←</span>
      <select className={`${cell} flex-1 min-w-0 text-pb-text`} value={value || ''} onChange={e => onMap(field, e.target.value)}>
        <option value="">, not in my file, </option>
        {headers.map(h => <option key={h} value={h}>{h}</option>)}
      </select>
      {/* A column matched on its VALUES rather than its header (an outcome
          column called "Column1", say) — worth saying so, since the header
          itself gives no clue why it was picked. */}
      {matchedOn === 'values'
        ? <span className="font-mono text-[9px] text-pb-faint shrink-0" title="Matched on what's in the column, not its heading">BY VALUES</span>
        : <Pct score={conf} />}
    </div>
  )
}

export function valueLabel(value, idName, kind) {
  if (!value) return kind === 'grade' ? '. Unresolved (kept against the whole club). ' : '. Unresolved (will be skipped), '
  if (value === '__new__') return kind === 'award' ? '+ Add as a new award type' : '+ Add as new player'
  if (value === '__skip__') return kind === 'award' ? "Don't import this award" : 'Skip this row'
  if (value === '__unassigned__') return '↪ Unassigned (no matching season)'
  if (value === '__own__') return 'Use this label as-is'
  return idName.get(value) || '(selected)'
}

// A sheet's season label is very often already exactly what the season
// should be called ("1969", "Summer 1972/73") — no reason to ask the admin
// to retype it. Pulls out a 4-digit year if one's present anywhere in it.
export function parseSeasonGuess(label) {
  // A bare-year Excel cell sometimes comes through float-typed (1980.0) —
  // the parser stringifies every cell as-is, so a clean ".0" tail is worth
  // stripping before it becomes a season's permanent display name.
  const s = String(label || '').trim().replace(/^(\d{4})\.0$/, '$1')
  const m = s.match(/(19|20)\d{2}/)
  return { name: s, year: m ? parseInt(m[0], 10) : null }
}

// Searchable combobox shared by the Players/Seasons/Grades steps — renders
// only a handful of options at a time so it stays snappy on a big roster.
// A hand-kept historical sheet often predates anything the club has synced,
// so — for seasons only — there's a way to mint one on the spot rather than
// forcing every pre-sync decade into "unassigned".
export function SearchSelect({ value, idName, candidates, options, onChange, kind, onCreateSeason, rawLabel }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newYear, setNewYear] = useState('')
  const [creatingBusy, setCreatingBusy] = useState(false)
  const [createErr, setCreateErr] = useState(null)
  const ref = useRef(null)
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    const base = ql ? options.filter(o => (o.name || '').toLowerCase().includes(ql)) : options
    return base.slice(0, 25)
  }, [q, options])
  const pick = v => { onChange(v); setOpen(false); setQ('') }
  const closeAll = () => { setOpen(false); setCreating(false); setCreateErr(null) }
  const unresolved = !value
  const guess = kind === 'season' ? parseSeasonGuess(rawLabel) : null

  function openCreateForm() {
    setNewName(guess?.name || '')
    setNewYear(guess?.year ? String(guess.year) : '')
    setCreateErr(null)
    setCreating(true)
  }
  async function submitNewSeason() {
    const n = newName.trim()
    if (!n) { setCreateErr('Name is required'); return }
    setCreatingBusy(true); setCreateErr(null)
    try {
      const s = await onCreateSeason({ name: n, year: newYear ? parseInt(newYear, 10) : null })
      setNewName(''); setNewYear('')
      pick(s.id)
    } catch (e) { setCreateErr(e.message) } finally { setCreatingBusy(false) }
  }
  async function quickCreateSeason() {
    if (!guess?.name) return
    setCreatingBusy(true); setCreateErr(null)
    try {
      const s = await onCreateSeason(guess)
      pick(s.id)
    } catch (e) { setCreateErr(e.message); setCreating(false) } finally { setCreatingBusy(false) }
  }

  const item = 'block w-full text-left px-2 py-1 text-[12px] text-pb-dim hover:bg-pb-surface2 hover:text-pb-text rounded'
  return (
    <div className="relative max-w-md" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className={`${cell} w-full text-left flex items-center justify-between ${unresolved ? 'text-pb-amber' : ''}`}>
        <span className="truncate">{valueLabel(value, idName, kind)}</span>
        <span className="text-pb-faint ml-2">▾</span>
      </button>
      <Dropdown anchorRef={ref} open={open} onClose={closeAll} align="start" width={300} maxHeight={300}
        className="bg-pb-surface border pb-hairline rounded shadow-xl p-1">
        {kind === 'season' && creating ? (
          <div className="p-2">
            <div className="flex flex-wrap items-center gap-1.5 mb-2">
              <input autoFocus placeholder="e.g. Summer 1972/73" value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitNewSeason() }}
                className="flex-1 min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
              <input placeholder="Year" value={newYear}
                onChange={e => setNewYear(e.target.value.replace(/\D/g, '').slice(0, 4))}
                onKeyDown={e => { if (e.key === 'Enter') submitNewSeason() }}
                className="w-16 shrink-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={submitNewSeason} disabled={creatingBusy}
                className="font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1 text-black bg-[var(--pb-accent)] disabled:opacity-50">
                {creatingBusy ? 'ADDING…' : 'ADD SEASON'}
              </button>
              <button type="button" onClick={() => { setCreating(false); setCreateErr(null) }}
                className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Cancel</button>
            </div>
            {createErr && <p className="text-[10px] text-pb-red/70 mt-1.5">{createErr}</p>}
          </div>
        ) : (
          <>
            {kind === 'player' && (
              <button className={item} onClick={() => pick('__new__')}>+ Add as new player</button>
            )}
            {kind === 'award' && (
              <button className={item} onClick={() => pick('__new__')}>+ Add as a new award type</button>
            )}
            {kind === 'season' && (
              <>
                <button className={item} onClick={() => pick('__unassigned__')}>↪ Unassigned (no matching season)</button>
                {guess?.name && (
                  <button className={item} onClick={quickCreateSeason} disabled={creatingBusy}>
                    {creatingBusy ? 'Adding…' : `⚡ Create "${guess.name}"${guess.year ? ` (${guess.year})` : ''}`}
                  </button>
                )}
                <button className={item} onClick={openCreateForm}>+ Create new season (edit name/year)</button>
                {createErr && <p className="px-2 text-[10px] text-pb-red/70">{createErr}</p>}
              </>
            )}
            {kind === 'grade' && (
              <button className={item} onClick={() => pick('__own__')}>Use this label as-is</button>
            )}
            {kind !== 'grade' && (
              <button className={item} onClick={() => pick('__skip__')}>
                {kind === 'award' ? "Don't import this award" : `Skip this ${kind === 'player' ? 'name' : 'row'}`}
              </button>
            )}
            {(candidates || []).length > 0 && <div className="px-2 pt-2 pb-1 font-mono text-[9px] tracking-wide2 text-pb-faint">SUGGESTED</div>}
            {(candidates || []).map(c => (
              <button key={c.id} className={`${item} leading-tight py-1.5`} onClick={() => pick(c.id)}>
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate">{c.name}</span>
                  {c.confidence != null && <span className="text-pb-faint shrink-0">{Math.round(c.confidence * 100)}%</span>}
                </span>
                {kind === 'player' && c.stats && <span className="block text-[10px] text-pb-faint mt-0.5">{candStatLine(c.stats)}</span>}
              </button>
            ))}
            <div className="px-1 pt-2 pb-1 sticky top-0">
              <input autoFocus value={q} onChange={e => setQ(e.target.value)}
                placeholder={`Search all ${kind === 'player' ? 'players' : kind === 'grade' ? 'grades' : kind === 'award' ? 'award types' : 'seasons'}…`}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
            </div>
            {filtered.map(o => <button key={o.id} className={item} onClick={() => pick(o.id)}>{o.name}</button>)}
            {filtered.length === 0 && <div className="px-2 py-1 text-[11px] text-pb-faint">No matches</div>}
          </>
        )}
      </Dropdown>
    </div>
  )
}

// ── player matching, in three passes: confirm matched / review close / no-match.
// A name with no candidate at all defaults to "add as new player" (never a
// silent skip) — only a genuinely close/ambiguous name needs a real decision.
//
// Shared by Import Stats and Import Awards. Two things are deliberately the
// caller's to decide: what one line of context to print under each name
// (`sheetLine` — games and goals for a stats sheet, awards won for an
// honours sheet), and what identifies a row. A row's identity is `key` where
// the resolver supplies one and the raw name otherwise: an awards sheet
// carrying the club's own player ids can hold two different people under one
// name, so the name alone can't be the override key there.
export function PlayerMatch({ rows, allPlayers, overrides, setOverride, setOverridesBulk, loading,
                              sheetLine, subtitle, nextLabel, onNext, onBack }) {
  const keyOf = r => r.key || r.raw_name
  const [tab, setTab] = useState(null)
  const [page, setPage] = useState(0)

  const playerStatsById = useMemo(() => {
    const m = new Map()
    allPlayers.forEach(p => m.set(p.id, p))
    return m
  }, [allPlayers])

  const idName = useMemo(() => {
    const m = new Map()
    allPlayers.forEach(o => m.set(o.id, o.name))
    rows.forEach(r => {
      (r.candidates || []).forEach(c => m.set(c.player_id, c.name))
      if (r.matched_name && r.player_id) m.set(r.player_id, r.matched_name)
    })
    return m
  }, [allPlayers, rows])

  const buckets = useMemo(() => {
    const matched = [], close = [], nomatch = []
    rows.forEach(r => {
      const st = r.status
      if (['exact', 'manual'].includes(st)) matched.push(r)
      else if (['fuzzy', 'ambiguous', 'clash'].includes(st)) close.push(r)
      else nomatch.push(r) // none, new, skip
    })
    return { matched, close, nomatch }
  }, [rows])

  // The one rule this whole rebuild exists for: a name with literally no
  // candidate defaults to becoming a brand-new player, never a silent skip.
  useEffect(() => {
    if (!rows.length) return
    setOverridesBulk(prev => {
      let changed = false
      const next = { ...prev }
      for (const r of rows) {
        if (r.auto_status === 'none' && !(keyOf(r) in next)) { next[keyOf(r)] = '__new__'; changed = true }
      }
      return changed ? next : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const valueFor = r => { const ov = overrides[keyOf(r)]; if (ov) return ov; if (r.player_id) return r.player_id; return '' }

  // Rows whose only suggestion is a single player are the safe bulk-confirm.
  const uniqueClose = useMemo(() => buckets.close.filter(r => (r.candidates || []).length === 1), [buckets.close])
  const multiCount = buckets.close.length - uniqueClose.length

  function confirmUniqueSuggested() {
    const patch = {}
    uniqueClose.forEach(r => { patch[keyOf(r)] = r.candidates[0].player_id })
    setOverridesBulk(o => ({ ...o, ...patch }))
  }
  function confirmAllSuggested() {
    const patch = {}
    buckets.close.forEach(r => { const c = (r.candidates || [])[0]; if (c) patch[keyOf(r)] = c.player_id })
    setOverridesBulk(o => ({ ...o, ...patch }))
  }
  function bulkNomatch(val) {
    const patch = {}; buckets.nomatch.forEach(r => { patch[keyOf(r)] = val }); setOverridesBulk(o => ({ ...o, ...patch }))
  }

  const TABS = [
    ['matched', '1. Confirm matched', buckets.matched.length],
    ['close', '2. Review close', buckets.close.length],
    ['nomatch', '3. Review no-match', buckets.nomatch.length],
  ]

  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">Match players</h2>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          {subtitle || 'Three quick passes: confirm the exact matches, review the close ones, then anything with no match defaults to a brand-new player. A name in your history is never silently dropped.'}
        </p>
        {loading && rows.length === 0 ? (
          <div className="py-10 text-center"><LoadingSpinner message="Matching players…" /></div>
        ) : (
          <>
            <div className="flex gap-1 mb-4 flex-wrap">
              {TABS.map(([k, label, n]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border ${active === k ? 'text-black border-transparent bg-[var(--pb-accent)]' : 'text-pb-faint pb-hairline hover:text-pb-text'}`}>
                  {label} ({n})
                </button>
              ))}
            </div>

            {active === 'matched' && (
              <p className="text-[12px] text-green-300 mb-3">
                {buckets.matched.length} name{buckets.matched.length === 1 ? '' : 's'} matched your players exactly. Nothing to do unless one looks wrong.
              </p>
            )}
            {active === 'close' && buckets.close.length > 0 && (
              <div className="mb-3">
                <div className="flex items-center gap-3 mb-2 flex-wrap">
                  <p className="text-[12px] text-pb-amber">Pick the right player, or leave it to become a new one.</p>
                  <div className="ml-auto flex items-center gap-2 flex-wrap">
                    {uniqueClose.length > 0 && (
                      <button onClick={confirmUniqueSuggested}
                        title="Confirm every row that has exactly one suggested player. Rows with more than one suggestion are left for you to choose."
                        className="font-mono text-[10px] tracking-wide2 rounded px-3 py-1.5 font-semibold text-black bg-[var(--pb-accent)]">
                        CONFIRM {uniqueClose.length} SINGLE MATCH{uniqueClose.length === 1 ? '' : 'ES'}
                      </button>
                    )}
                    <button onClick={confirmAllSuggested}
                      className="font-mono text-[10px] tracking-wide2 border border-[var(--pb-accent)]/40 text-[var(--pb-accent)] rounded px-3 py-1.5 hover:bg-[var(--pb-accent)]/10">
                      CONFIRM ALL TOP ({buckets.close.length})
                    </button>
                  </div>
                </div>
                <p className="text-[11px] text-pb-faint leading-relaxed max-w-3xl">
                  {uniqueClose.length > 0 && (
                    <><span className="text-pb-dim">Confirm single matches</span> accepts only the {uniqueClose.length} row{uniqueClose.length === 1 ? '' : 's'} with exactly one suggestion (the safe ones){multiCount > 0 ? `, leaving ${multiCount} with more than one option for you to pick` : ''}. </>
                  )}
                  Confirmed players move to <button className="text-[var(--pb-accent)] hover:underline" onClick={() => setTab('matched')}>Confirm matched</button>, where you can still change or skip any.
                </p>
              </div>
            )}
            {active === 'nomatch' && buckets.nomatch.length > 0 && (
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <p className="text-[12px] text-pb-faint">These default to <span className="text-[var(--pb-accent)]">new players</span>. Change any that already exist, or skip.</p>
                <button onClick={() => bulkNomatch('__new__')} className="ml-auto font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text">CREATE ALL NEW</button>
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
                    const candidates = (r.candidates || []).map(c => ({
                      id: c.player_id, name: c.name, confidence: c.confidence, stats: playerStatsById.get(c.player_id),
                    }))
                    const sheet = sheetLine ? sheetLine(r) : null
                    return (
                      <tr key={keyOf(r) + i} className="pb-hairline-t align-middle">
                        <td className="py-2 pr-2 text-pb-text">
                          {r.raw_name}
                          {r.ref && <span className="font-mono text-[9px] text-pb-faintest ml-1.5">#{r.ref}</span>}
                          {sheet && <div className="text-[10px] text-pb-faint mt-0.5">sheet: {sheet}</div>}
                          {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                        </td>
                        <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                        <td className="py-2 pr-2">
                          <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allPlayers}
                            onChange={v => setOverride(keyOf(r), v)} kind="player" />
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
                <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={safe === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
                {safe + 1} / {pageCount}
                <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={safe >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
              </div>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)]">{nextLabel}</button>
      </div>
    </>
  )
}

// ── shared match table for Seasons + Grades (filter + paginate) ─────────────
const RESOLVED_STATUSES = ['exact', 'manual', 'matched', 'own']

export function MatchTable({ title, subtitle, rows, kind, allOptions, valueFor, onChange, nextLabel, onNext, onBack, loading, onCreateSeason, onBulkCreateSeasons, bulkCreating, labelHeading }) {
  const [onlyReview, setOnlyReview] = useState(true)
  const [page, setPage] = useState(0)
  const noMatchCount = useMemo(() => rows.filter(r => r.status === 'none').length, [rows])

  const idName = useMemo(() => {
    const m = new Map()
    const idf = idField(kind)
    allOptions.forEach(o => m.set(o.id, o.name))
    rows.forEach(r => {
      (r.candidates || []).forEach(c => m.set(c[idf], c.name))
      if (r.matched_name) m.set(r[idf], r.matched_name)
    })
    return m
  }, [allOptions, rows, kind])

  const counts = useMemo(() => {
    let resolved = 0, review = 0
    rows.forEach(r => { (RESOLVED_STATUSES.includes(r.status) ? resolved++ : review++) })
    return { resolved, review, total: rows.length }
  }, [rows])

  const shown = useMemo(() => onlyReview ? rows.filter(r => !RESOLVED_STATUSES.includes(r.status)) : rows, [rows, onlyReview])
  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = shown.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE)
  useEffect(() => { setPage(0) }, [onlyReview, rows.length])

  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">{title}</h2>
        <p className="text-pb-faint text-[12px] mb-3 leading-relaxed max-w-3xl">{subtitle}</p>

        {!loading && rows.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <span className="font-mono text-[10px] text-green-300">{counts.resolved} matched</span>
            <span className="font-mono text-[10px] text-pb-amber">{counts.review} need review</span>
            <button onClick={() => setOnlyReview(v => !v)}
              className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2.5 py-1 text-pb-faint hover:text-pb-text">
              {onlyReview ? `SHOW ALL ${counts.total}` : 'NEEDS REVIEW ONLY'}
            </button>
            {kind === 'season' && noMatchCount > 0 && (
              <button onClick={onBulkCreateSeasons} disabled={bulkCreating}
                title="Creates a season named after each unmatched label (parsing out a year where there is one) and assigns it, no retyping needed for sheets that just use bare years."
                className="font-mono text-[10px] tracking-wide2 rounded px-2.5 py-1 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
                {bulkCreating ? 'CREATING…' : `CREATE SEASONS FOR ALL UNMATCHED (${noMatchCount})`}
              </button>
            )}
            {pageCount > 1 && (
              <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={safePage === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
                {safePage + 1} / {pageCount}
                <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={safePage >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
              </span>
            )}
          </div>
        )}

        <div className="overflow-x-auto overflow-y-visible">
          <table className="w-full text-[12px] min-w-[560px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">{labelHeading || (kind === 'grade' ? 'GRADE/TEAM LABEL' : 'SEASON LABEL')}</th>
                <th className="py-2 pr-2 w-28">STATUS</th>
                <th className="py-2 pr-2">MATCH TO</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                const idf = idField(kind)
                const candidates = (r.candidates || []).map(c => ({ id: c[idf], name: c.name, confidence: c.confidence }))
                return (
                  <tr key={(r.raw_label || '') + i} className="pb-hairline-t align-middle">
                    <td className="py-2 pr-2 text-pb-text">{r.raw_label}</td>
                    <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                    <td className="py-2 pr-2">
                      <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allOptions}
                        onChange={v => onChange(r, v)} kind={kind} onCreateSeason={onCreateSeason} rawLabel={r.raw_label} />
                    </td>
                  </tr>
                )
              })}
              {loading && rows.length === 0 && (
                <tr><td colSpan={3} className="py-8 text-center"><LoadingSpinner message={`Matching ${kind === 'grade' ? 'grades' : 'seasons'}…`} /></td></tr>
              )}
              {!loading && rows.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-pb-dim text-[12px]">Nothing to match.</td></tr>}
              {!loading && rows.length > 0 && shown.length === 0 && (
                <tr><td colSpan={3} className="py-4 text-center text-green-300 text-[12px]">All {kind === 'grade' ? 'grades' : 'seasons'} matched. Nothing to review.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)]">{nextLabel}</button>
      </div>
    </>
  )
}
