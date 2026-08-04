import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'
import Dropdown from '../../../components/Dropdown'

// Ported from BetterStats (Core)'s BetterImport wizard
// (pages/admin/AdminImport.jsx) — same visual language, same three-pass
// player-matching flow, same "never silently skip" rule. Trimmed to AFL's
// simpler shape: no career-vs-season-by-season toggle (a season column is
// just optional), no batting/bowling field groups, no GR-reconciliation
// residual math (AFL's "already synced" is a flat overlap flag, not a
// per-metric reconciler) and no inline "+ Create new season" (AFL has no
// manual-season-creation endpoint yet).
const FIELD_LABEL = {
  player_name: 'Player name', season_label: 'Season', grade_label: 'Grade / team',
  games_played: 'Games', goals: 'Goals', behinds: 'Behinds',
  bog_count: 'Best on Ground', captain_games: 'Captain games',
  club_bf_votes: 'Club B&F votes', comp_bf_votes: 'Competition B&F votes',
}
const IDENTITY_FIELDS = ['player_name', 'season_label', 'grade_label']
const STAT_FIELDS = ['games_played', 'goals', 'behinds', 'bog_count', 'captain_games', 'club_bf_votes', 'comp_bf_votes']
const REQUIRED_FIELDS = new Set(['player_name'])

const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'
const num = n => Number(n || 0).toLocaleString()

const STEP_LABELS = { upload: 'Upload', columns: 'Columns', players: 'Players', seasons: 'Seasons', grades: 'Grades', confirm: 'Confirm' }

function Pct({ score }) {
  if (score == null) return null
  const tone = score >= 0.85 ? 'text-green-300' : score >= 0.6 ? 'text-pb-amber' : 'text-pb-red/60'
  return <span className={`font-mono text-[10px] ${tone}`}>{Math.round(score * 100)}%</span>
}

function StatusBadge({ status }) {
  const map = {
    exact: ['MATCHED', 'text-green-300 border-green-300/30'],
    manual: ['CHOSEN', 'text-green-300 border-green-300/30'],
    matched: ['MATCHED', 'text-green-300 border-green-300/30'],
    fuzzy: ['REVIEW', 'text-pb-amber border-pb-amber/30'],
    none: ['NO MATCH', 'text-pb-red/70 border-pb-red/30'],
    ambiguous: ['MERGE FIRST', 'text-pb-red/70 border-pb-red/30'],
    new: ['NEW PLAYER', 'text-[var(--pb-accent)] border-[var(--pb-accent)]/40'],
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
function idField(kind) { return kind === 'player' ? 'player_id' : kind === 'season' ? 'season_id' : 'grade_name' }

// A player's own sheet history — computed purely client-side from the raw
// uploaded rows (no backend round-trip), so a name in "Review close" or
// "Review no-match" shows what it's actually claiming before you decide.
function computeSheetStats(rows, mapping) {
  const nameCol = mapping.player_name?.column
  if (!nameCol) return {}
  const seasonCol = mapping.season_label?.column
  const gamesCol = mapping.games_played?.column
  const goalsCol = mapping.goals?.column
  const out = {}
  for (const r of rows) {
    const name = String(r[nameCol] || '').trim()
    if (!name) continue
    const o = out[name] || (out[name] = { rows: 0, games: 0, goals: 0, seasons: new Set() })
    o.rows++
    if (gamesCol) o.games += Number(r[gamesCol]) || 0
    if (goalsCol) o.goals += Number(r[goalsCol]) || 0
    if (seasonCol) { const s = String(r[seasonCol] || '').trim(); if (s) o.seasons.add(s) }
  }
  return out
}
function sheetStatLine(s) {
  if (!s) return null
  const bits = []
  if (s.seasons.size) bits.push(`${s.seasons.size} season${s.seasons.size === 1 ? '' : 's'}`)
  if (s.games) bits.push(`${num(s.games)} games`)
  if (s.goals) bits.push(`${num(s.goals)} goals`)
  return bits.length ? bits.join(' · ') : null
}
function candStatLine(p) {
  if (!p) return null
  const bits = []
  if (p.games) bits.push(`${num(p.games)} games`)
  if (p.goals) bits.push(`${num(p.goals)} goals`)
  return bits.length ? bits.join(' · ') : 'no stats at this club yet'
}

// One column-mapping row — reads left-to-right "field ← your column", green
// once matched, with the auto-match confidence shown alongside.
function FieldRow({ field, value, headers, conf, onMap }) {
  const label = FIELD_LABEL[field]
  const required = REQUIRED_FIELDS.has(field)
  return (
    <div className={`flex items-center gap-2 rounded px-2 py-1.5 border ${value ? 'border-green-300/30' : 'pb-hairline'}`}>
      <span className="text-[11px] font-semibold text-green-300 w-40 shrink-0 leading-tight">
        {label}{required && <span className="text-pb-red/70 ml-0.5">*</span>}
      </span>
      <span className="text-pb-faintest text-[11px] shrink-0" aria-hidden>←</span>
      <select className={`${cell} flex-1 min-w-0 text-pb-text`} value={value || ''} onChange={e => onMap(field, e.target.value)}>
        <option value="">— not in my file —</option>
        {headers.map(h => <option key={h} value={h}>{h}</option>)}
      </select>
      {conf != null && <Pct score={conf} />}
    </div>
  )
}

function valueLabel(value, idName, kind) {
  if (!value) return kind === 'grade' ? '— Unresolved (kept against the whole club) —' : '— Unresolved (will be skipped) —'
  if (value === '__new__') return '+ Add as new player'
  if (value === '__skip__') return 'Skip this row'
  if (value === '__unassigned__') return '↪ Unassigned (no matching season)'
  if (value === '__own__') return 'Use this label as-is'
  return idName.get(value) || '(selected)'
}

// A sheet's season label is very often already exactly what the season
// should be called ("1969", "Summer 1972/73") — no reason to ask the admin
// to retype it. Pulls out a 4-digit year if one's present anywhere in it.
function parseSeasonGuess(label) {
  const s = String(label || '').trim()
  const m = s.match(/(19|20)\d{2}/)
  return { name: s, year: m ? parseInt(m[0], 10) : null }
}

// Searchable combobox shared by the Players/Seasons/Grades steps — renders
// only a handful of options at a time so it stays snappy on a big roster.
// A hand-kept historical sheet often predates anything the club has synced,
// so — for seasons only — there's a way to mint one on the spot rather than
// forcing every pre-sync decade into "unassigned".
function SearchSelect({ value, idName, candidates, options, onChange, kind, onCreateSeason, rawLabel }) {
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
              <button className={item} onClick={() => pick('__skip__')}>Skip this {kind === 'player' ? 'name' : 'row'}</button>
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
                placeholder={`Search all ${kind === 'player' ? 'players' : kind === 'grade' ? 'grades' : 'seasons'}…`}
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

// ── shared match table for Seasons + Grades (filter + paginate) ─────────────
const RESOLVED_STATUSES = ['exact', 'manual', 'matched', 'own']
const PAGE_SIZE = 50

function MatchTable({ title, subtitle, rows, kind, allOptions, valueFor, onChange, nextLabel, onNext, onBack, loading, onCreateSeason, onBulkCreateSeasons, bulkCreating }) {
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
                title="Creates a season named after each unmatched label (parsing out a year where there is one) and assigns it — no retyping needed for sheets that just use bare years."
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
                <th className="py-2 pr-2">{kind === 'grade' ? 'GRADE/TEAM LABEL' : 'SEASON LABEL'}</th>
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
                <tr><td colSpan={3} className="py-4 text-center text-green-300 text-[12px]">All {kind === 'grade' ? 'grades' : 'seasons'} matched — nothing to review.</td></tr>
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

// ── player matching, in three passes: confirm matched / review close / no-match.
// A name with no candidate at all defaults to "add as new player" (never a
// silent skip) — only a genuinely close/ambiguous name needs a real decision.
function PlayerMatch({ rows, sheetStats, allPlayers, overrides, setOverride, setOverridesBulk, loading, nextLabel, onNext, onBack }) {
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
      else if (['fuzzy', 'ambiguous'].includes(st)) close.push(r)
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
        if (r.auto_status === 'none' && !(r.raw_name in next)) { next[r.raw_name] = '__new__'; changed = true }
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
  const valueFor = r => { const ov = overrides[r.raw_name]; if (ov) return ov; if (r.player_id) return r.player_id; return '' }

  // Rows whose only suggestion is a single player are the safe bulk-confirm.
  const uniqueClose = useMemo(() => buckets.close.filter(r => (r.candidates || []).length === 1), [buckets.close])
  const multiCount = buckets.close.length - uniqueClose.length

  function confirmUniqueSuggested() {
    const patch = {}
    uniqueClose.forEach(r => { patch[r.raw_name] = r.candidates[0].player_id })
    setOverridesBulk(o => ({ ...o, ...patch }))
  }
  function confirmAllSuggested() {
    const patch = {}
    buckets.close.forEach(r => { const c = (r.candidates || [])[0]; if (c) patch[r.raw_name] = c.player_id })
    setOverridesBulk(o => ({ ...o, ...patch }))
  }
  function bulkNomatch(val) {
    const patch = {}; buckets.nomatch.forEach(r => { patch[r.raw_name] = val }); setOverridesBulk(o => ({ ...o, ...patch }))
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
          Three quick passes: confirm the exact matches, review the close ones, then anything with no match
          defaults to a brand-new player — a name in your history is never silently dropped.
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
                {buckets.matched.length} name{buckets.matched.length === 1 ? '' : 's'} matched your players exactly — nothing to do unless one looks wrong.
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
                    const sheet = sheetStatLine(sheetStats[r.raw_name])
                    return (
                      <tr key={r.raw_name + i} className="pb-hairline-t align-middle">
                        <td className="py-2 pr-2 text-pb-text">
                          {r.raw_name}
                          {sheet && <div className="text-[10px] text-pb-faint mt-0.5">sheet: {sheet}</div>}
                          {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                        </td>
                        <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                        <td className="py-2 pr-2">
                          <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allPlayers}
                            onChange={v => setOverride(r.raw_name, v)} kind="player" />
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

// ── review + commit ──────────────────────────────────────────────────────────
function ReviewStep({ resolved, resolving, committing, committed, unresolved, onCommit, onBack, onReset }) {
  if (committed) {
    return (
      <div className="pb-card p-6">
        <div className="font-mono text-[10px] tracking-wide2 text-green-300 mb-2">IMPORT COMPLETE</div>
        <h2 className="font-display font-bold text-xl text-pb-text mb-3">
          {committed.players_imported} player{committed.players_imported === 1 ? '' : 's'} imported
          {committed.players_created ? `, ${committed.players_created} created` : ''}
        </h2>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed max-w-2xl">
          {committed.rows_written} row{committed.rows_written === 1 ? '' : 's'} written.
          {committed.rows_skipped ? ` ${committed.rows_skipped} unresolved row(s) were skipped.` : ''}
        </p>
        <div className="flex gap-3">
          <button onClick={onReset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)]">IMPORT ANOTHER</button>
          <Link to="/admin/players" className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text">VIEW PLAYERS</Link>
        </div>
      </div>
    )
  }
  const preview = resolved?.preview || []
  const shownPreview = preview.slice(0, 300)
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
          <h2 className="font-display font-semibold text-lg text-pb-text">Confirm import</h2>
          <span className="font-mono text-[10px] text-pb-faint">
            {totals.players_matched || 0} matched · {totals.players_new || 0} new · {totals.rows_skipped || 0} skipped{resolving ? ' · syncing…' : ''}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[680px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">PLAYER</th>
                <th className="py-2 pr-2 text-right">ROWS</th>
                <th className="py-2 pr-2 text-right">GAMES</th>
                <th className="py-2 pr-2 text-right">GOALS</th>
                <th className="py-2 pr-2 text-right">BEHINDS</th>
                <th className="py-2 pr-2 text-right">CLUB B&F</th>
                <th className="py-2 pr-2 text-right">COMP B&F</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {shownPreview.map(p => (
                <tr key={p.player_id || `new:${p.player_name}`} className="pb-hairline-t">
                  <td className="py-2 pr-2 text-pb-text">
                    {p.player_name}
                    {p.new && <span className="ml-2 font-mono text-[8px] tracking-wide2 text-[var(--pb-accent)] border border-[var(--pb-accent)]/40 rounded px-1 py-0.5">NEW</span>}
                  </td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.rows)}</td>
                  <td className="py-2 pr-2 font-mono text-[12px] text-pb-text text-right font-semibold">{num(p.games)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.goals)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.behinds)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.club_bf_votes)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.comp_bf_votes)}</td>
                  <td className="py-2 pr-2">{p.already_synced_overlap && <span className="font-mono text-[9px] text-pb-faint" title="Some season(s) shown here are already synced from PlayHQ — those rows still import but the synced figures win.">already synced</span>}</td>
                </tr>
              ))}
              {resolving && preview.length === 0 && <tr><td colSpan={8} className="py-8 text-center"><LoadingSpinner message="Reconciling…" /></td></tr>}
              {!resolving && preview.length === 0 && <tr><td colSpan={8} className="py-4 text-center text-pb-dim">No matched players yet — go back and resolve the matches.</td></tr>}
            </tbody>
          </table>
        </div>
        {preview.length > shownPreview.length && (
          <p className="font-mono text-[10px] text-pb-faintest mt-2">Showing the top {shownPreview.length} of {preview.length} players by games — all will be imported.</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        {unresolved > 0 && <span className="font-mono text-[10px] text-pb-amber">{unresolved} player(s) still unresolved — they'll be skipped.</span>}
        <button onClick={onCommit} disabled={committing || preview.length === 0}
          className="ml-auto px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
          {committing ? 'IMPORTING…' : `IMPORT ${preview.length} PLAYER${preview.length === 1 ? '' : 'S'}`}
        </button>
      </div>
    </>
  )
}

function PastImports({ history, expandedBatch, batchPlayers, loadingBatchPlayers, onToggle, onUndo }) {
  if (!history.length) return null
  return (
    <div className="pb-card p-5">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">PAST IMPORTS</div>
      <table className="w-full text-[12px]">
        <tbody>
          {history.map(b => (
            <Fragment key={b.id}>
              <tr className="pb-hairline-t">
                <td className="py-2 pr-2 text-pb-text">
                  {!b.undone_at && (
                    <button onClick={() => onToggle(b)} className="text-pb-faint hover:text-pb-text mr-1.5 font-mono text-[10px]" title="Show players in this import">
                      {expandedBatch === b.id ? '▾' : '▸'}
                    </button>
                  )}
                  {b.filename || '(unnamed)'}
                </td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-dim">{b.row_count} rows</td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-faintest">{(b.committed_at || b.created_at || '').slice(0, 10)}</td>
                <td className="py-2 pr-2 text-right">
                  {b.undone_at
                    ? <span className="font-mono text-[9px] text-pb-faint">UNDONE</span>
                    : <button onClick={() => onUndo(b)} className="font-mono text-[9px] tracking-wide2 text-pb-red/70 hover:text-pb-red border border-pb-red/30 rounded px-2 py-0.5">UNDO</button>}
                </td>
              </tr>
              {expandedBatch === b.id && (
                <tr>
                  <td colSpan={4} className="pb-2 pl-6 pr-2">
                    {loadingBatchPlayers && !batchPlayers[b.id] ? (
                      <div className="font-mono text-[10px] text-pb-faint py-1">loading players…</div>
                    ) : (
                      <div className="rounded border pb-hairline divide-y pb-hairline-t">
                        {(batchPlayers[b.id] || []).map((p, i) => (
                          <div key={i} className="flex items-center justify-between px-2 py-1.5">
                            <span className="text-pb-dim">{p.player_name} {p.season_label ? `— ${p.season_label}` : ''} {p.grade_label ? `(${p.grade_label})` : ''}</span>
                            <span className="font-mono text-[10px] text-pb-faintest">
                              {p.games_played}g {p.goals}gl {p.behinds}b
                              {(p.club_bf_votes || p.comp_bf_votes) ? ` · ${p.club_bf_votes || 0} club/${p.comp_bf_votes || 0} comp votes` : ''}
                            </span>
                          </div>
                        ))}
                        {(batchPlayers[b.id] || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest px-2 py-1.5">No rows.</div>}
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AflAdminImport() {
  const toast = useToast()

  const [step, setStep] = useState('upload')
  const fileRef = useRef(null)
  const [parsing, setParsing] = useState(false)
  const [filename, setFilename] = useState(null)
  const [headers, setHeaders] = useState([])
  const [rows, setRows] = useState([])
  const [mapping, setMapping] = useState({})

  const [playerOverrides, setPlayerOverrides] = useState({})
  const [seasonOverrides, setSeasonOverrides] = useState({})
  const [gradeOverrides, setGradeOverrides] = useState({})
  const [resolved, setResolved] = useState(null)
  const [resolving, setResolving] = useState(false)

  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(null)

  const [allPlayers, setAllPlayers] = useState([])
  const [allSeasons, setAllSeasons] = useState([])
  const [history, setHistory] = useState([])
  const [expandedBatch, setExpandedBatch] = useState(null)
  const [batchPlayers, setBatchPlayers] = useState({})
  const [loadingBatchPlayers, setLoadingBatchPlayers] = useState(false)

  const loadHistory = () => { aflApi.importsList().then(setHistory).catch(() => {}) }
  useEffect(() => {
    aflApi.adminListPlayers().then(ps => setAllPlayers((ps || []).map(p => ({
      id: p.id, name: p.display_name || p.name, games: p.games, goals: p.goals,
    })))).catch(() => {})
    aflApi.importsSeasons().then(ss => setAllSeasons((ss || []).map(s => ({
      id: s.id, name: (s.year && !String(s.name).includes(String(s.year))) ? `${s.name} (${s.year})` : s.name,
    })))).catch(() => {})
    loadHistory()
  }, [])

  const hasSeasonCol = !!mapping.season_label?.column
  const hasGradeCol = !!mapping.grade_label?.column
  const steps = useMemo(() => {
    const s = ['upload', 'columns', 'players']
    if (hasSeasonCol) s.push('seasons')
    if (hasGradeCol) s.push('grades')
    s.push('confirm')
    return s
  }, [hasSeasonCol, hasGradeCol])

  // Live-reconcile whenever the mapping or any override changes — mirrors
  // BetterStats (Core)'s BetterImport: the preview stays current as you work
  // instead of needing an explicit "Continue" to move the data forward.
  useEffect(() => {
    if (!headers.length) return
    let cancelled = false
    setResolving(true)
    const body = {
      rows, mapping,
      player_overrides: playerOverrides, season_overrides: seasonOverrides, grade_overrides: gradeOverrides,
    }
    const t = setTimeout(() => {
      aflApi.importsResolve(body)
        .then(r => { if (!cancelled) setResolved(r) })
        .catch(e => { if (!cancelled) toast.error(e.message) })
        .finally(() => { if (!cancelled) setResolving(false) })
    }, 200)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, JSON.stringify(mapping), JSON.stringify(playerOverrides), JSON.stringify(seasonOverrides), JSON.stringify(gradeOverrides)])

  // Unmatched season labels default to "unassigned" rather than blocking
  // progress — the same residual-bucket idea BetterImport uses.
  useEffect(() => {
    const ss = resolved?.seasons
    if (!ss) return
    setSeasonOverrides(prev => {
      let changed = false
      const next = { ...prev }
      for (const s of ss) {
        if (s.auto_status === 'none' && !(s.raw_label in next)) { next[s.raw_label] = '__unassigned__'; changed = true }
      }
      return changed ? next : prev
    })
  }, [resolved?.seasons])

  const sheetStats = useMemo(() => computeSheetStats(rows, mapping), [rows, mapping])

  async function onFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setParsing(true)
    setHeaders([]); setRows([]); setMapping({}); setResolved(null); setCommitted(null)
    setPlayerOverrides({}); setSeasonOverrides({}); setGradeOverrides({})
    try {
      const res = await aflApi.importsPreview(f)
      setHeaders(res.headers); setRows(res.rows); setMapping(res.mapping); setFilename(f.name)
      setStep('columns')
      toast.success(`Parsed ${res.row_count} row${res.row_count === 1 ? '' : 's'}`)
    } catch (err) { toast.error(err.message) } finally {
      setParsing(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const mappedColumn = field => mapping[field]?.column || ''
  const setMap = (field, column) => {
    setMapping(m => column ? { ...m, [field]: { column, confidence: 1 } } : (() => { const n = { ...m }; delete n[field]; return n })())
  }
  const setPOverride = (name, val) => setPlayerOverrides(o => { const n = { ...o }; if (!val) delete n[name]; else n[name] = val; return n })
  const setPOverridesBulk = fn => setPlayerOverrides(fn)
  const setSOverride = (label, val) => setSeasonOverrides(o => { const n = { ...o }; if (!val) delete n[label]; else n[label] = val; return n })
  const setGOverride = (label, val) => setGradeOverrides(o => { const n = { ...o }; if (!val) delete n[label]; else n[label] = val; return n })

  // A hand-kept historical sheet often predates anything the club has
  // synced — there's no existing season to match "1972" to, so the Seasons
  // step needs a way to mint one on the spot rather than folding every
  // pre-sync decade into "unassigned".
  async function createSeason(data) {
    const s = await aflApi.importsCreateSeason(data)
    setAllSeasons(prev => [...prev, { id: s.id, name: s.year && !String(s.name).includes(String(s.year)) ? `${s.name} (${s.year})` : s.name }])
    return s
  }

  // "Create seasons for all unmatched" — a sheet like a decades-long club
  // history sheet routinely has 50+ distinct bare-year labels with no
  // matching season; doing each one by hand through the picker doesn't
  // scale. Sequential (not parallel) so two labels that resolve to the same
  // season name don't race each other into a duplicate-name 409.
  const [bulkCreatingSeasons, setBulkCreatingSeasons] = useState(false)
  async function bulkCreateSeasons() {
    const targets = (resolved?.seasons || []).filter(s => s.status === 'none' && !seasonOverrides[s.raw_label])
    if (!targets.length) return
    setBulkCreatingSeasons(true)
    let created = 0, failed = 0
    for (const s of targets) {
      try {
        const season = await createSeason(parseSeasonGuess(s.raw_label))
        setSOverride(s.raw_label, season.id)
        created++
      } catch (e) { failed++ }
    }
    setBulkCreatingSeasons(false)
    toast[failed ? 'error' : 'success'](
      `Created ${created} season${created === 1 ? '' : 's'}` + (failed ? ` — ${failed} couldn't be created (name already exists; pick it from the list instead)` : '')
    )
  }

  const required = ['player_name']
  const mapReady = required.every(f => mappedColumn(f))
  const unresolved = resolved?.totals?.players_unresolved || 0

  async function commit() {
    setCommitting(true)
    try {
      const res = await aflApi.importsCommit({
        rows, mapping, filename,
        player_overrides: playerOverrides, season_overrides: seasonOverrides, grade_overrides: gradeOverrides,
      })
      setCommitted(res)
      loadHistory()
      toast.success(`Imported ${res.players_imported} player${res.players_imported === 1 ? '' : 's'}`)
    } catch (err) { toast.error(err.message) } finally { setCommitting(false) }
  }

  async function toggleBatch(b) {
    if (expandedBatch === b.id) { setExpandedBatch(null); return }
    setExpandedBatch(b.id)
    if (!batchPlayers[b.id]) {
      setLoadingBatchPlayers(true)
      try {
        const r = await aflApi.importsBatchPlayers(b.id)
        setBatchPlayers(bp => ({ ...bp, [b.id]: r }))
      } catch (err) { toast.error(err.message) } finally { setLoadingBatchPlayers(false) }
    }
  }
  async function undo(b) {
    if (!window.confirm(`Undo this import (${b.filename})? Every row it added will be removed.`)) return
    try {
      const r = await aflApi.importsUndo(b.id)
      toast.success(`Removed ${r.rows_removed} imported rows`)
      loadHistory()
    } catch (err) { toast.error(err.message) }
  }

  function reset() {
    setStep('upload'); setFilename(null); setHeaders([]); setRows([]); setMapping({})
    setPlayerOverrides({}); setSeasonOverrides({}); setGradeOverrides({})
    setResolved(null); setCommitted(null)
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Import Stats</SectionTitle>
        {step !== 'upload' && !committed && (
          <button onClick={reset} className="text-xs text-pb-dim hover:text-pb-text underline">Start over</button>
        )}
      </div>
      <p className="text-sm text-pb-dim max-w-2xl -mt-4">
        Bring in historical season stats from a spreadsheet — for seasons PlayHQ's own data doesn't
        cover. Upload, match the columns and players, confirm the season and grade, then import. Where
        your sheet and the synced data overlap for a season, the synced figures win.
      </p>

      {/* Stepper */}
      <div className="flex items-center gap-1 flex-wrap">
        {steps.map((s, i) => {
          const active = s === step
          const done = steps.indexOf(step) > i
          const reachable = headers.length > 0 || s === 'upload'
          return (
            <button key={s} disabled={!reachable}
              onClick={() => reachable && setStep(s)}
              className={`font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border transition-colors ${
                active ? 'text-black border-transparent bg-[var(--pb-accent)]' : done ? 'text-green-300 border-green-300/30' : 'text-pb-faint pb-hairline'
              } ${!reachable ? 'opacity-40 cursor-not-allowed' : 'hover:text-pb-text'}`}>
              {i + 1}. {STEP_LABELS[s]}
            </button>
          )
        })}
        {resolving && <span className="font-mono text-[10px] text-pb-faint ml-2">syncing…</span>}
      </div>

      {/* ── Step: Upload ── */}
      {step === 'upload' && (
        <div className="pb-card p-5">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
            <div>
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">CSV OR EXCEL FILE</label>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm" onChange={onFile} disabled={parsing}
                className="block text-pb-dim text-sm file:bg-pb-surface2 file:border file:pb-hairline file:rounded file:px-3 file:py-1.5 file:mr-3 file:font-mono file:text-[10px] file:text-pb-text file:cursor-pointer" />
            </div>
          </div>
          <p className="font-mono text-[10px] text-pb-faintest mt-3">
            Headers can be anything — we map them in the next step.{' '}
            <a href={aflApi.importsTemplateUrl()} className="text-[var(--pb-accent)] hover:underline">Download a template</a>.
          </p>
        </div>
      )}
      {parsing && <LoadingSpinner message="Parsing file…" />}

      {/* ── Step: Columns ── */}
      {step === 'columns' && headers.length > 0 && (
        <>
          <div className="pb-card p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">MATCH YOUR COLUMNS TO THE RIGHT FIELDS</div>
              <span className="font-mono text-[10px] text-pb-faint">{rows.length} row(s) · {headers.length} columns · {filename}</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-4 pb-3 pb-hairline-b">
              <span className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-green-300/80"></span>BetterFootball field
              </span>
              <span className="text-pb-faintest text-[11px]" aria-hidden>←</span>
              <span className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
                <span className="inline-block w-2.5 h-2.5 rounded-sm bg-pb-text/80 border pb-hairline"></span>your column
              </span>
              <span className="text-pb-faintest text-[10px] sm:ml-1">Leave a field blank if your sheet doesn't have it.</span>
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">IDENTITY</div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 mb-5">
              {IDENTITY_FIELDS.map(f => (
                <FieldRow key={f} field={f} value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence} onMap={setMap} />
              ))}
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">SEASON STATS</div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {STAT_FIELDS.map(f => (
                <FieldRow key={f} field={f} value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence} onMap={setMap} />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!mapReady && <span className="font-mono text-[10px] text-pb-red/70">Map the Player name column to continue.</span>}
            <button onClick={() => setStep('players')} disabled={!mapReady}
              className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
              NEXT: MATCH PLAYERS →
            </button>
          </div>
        </>
      )}

      {/* ── Step: Players ── */}
      {step === 'players' && (
        <PlayerMatch
          rows={resolved?.players || []} sheetStats={sheetStats} allPlayers={allPlayers}
          overrides={playerOverrides} setOverride={setPOverride} setOverridesBulk={setPOverridesBulk}
          loading={resolving}
          nextLabel={hasSeasonCol ? 'NEXT: SEASONS →' : hasGradeCol ? 'NEXT: GRADES →' : 'NEXT: CONFIRM →'}
          onNext={() => setStep(hasSeasonCol ? 'seasons' : hasGradeCol ? 'grades' : 'confirm')}
          onBack={() => setStep('columns')}
        />
      )}

      {/* ── Step: Seasons ── */}
      {step === 'seasons' && (
        <MatchTable
          title="Confirm season data" kind="season"
          subtitle="Match each season label to one of your club's seasons. Anything we can't match defaults to unassigned — those rows still import, just without a season link."
          rows={resolved?.seasons || []}
          allOptions={allSeasons}
          loading={resolving}
          valueFor={r => seasonOverrides[r.raw_label] ?? (r.season_id || (r.is_prior ? '__unassigned__' : ''))}
          onChange={(r, v) => setSOverride(r.raw_label, v)}
          onCreateSeason={createSeason}
          onBulkCreateSeasons={bulkCreateSeasons}
          bulkCreating={bulkCreatingSeasons}
          nextLabel={hasGradeCol ? 'NEXT: GRADES →' : 'NEXT: CONFIRM →'}
          onNext={() => setStep(hasGradeCol ? 'grades' : 'confirm')}
          onBack={() => setStep('players')}
        />
      )}

      {/* ── Step: Grades ── */}
      {step === 'grades' && (
        <MatchTable
          title="Confirm grade data" kind="grade"
          subtitle="Match each grade or team label from your sheet to a grade name we already hold for this club. Leave it as-is if it genuinely predates online records — it's kept as its own historical label rather than matched to the wrong grade."
          rows={resolved?.grades || []}
          allOptions={(resolved?.grade_options || []).map(name => ({ id: name, name }))}
          loading={resolving}
          valueFor={r => gradeOverrides[r.raw_label] ?? (r.grade_name || '__own__')}
          onChange={(r, v) => setGOverride(r.raw_label, v)}
          nextLabel="NEXT: CONFIRM →"
          onNext={() => setStep('confirm')}
          onBack={() => setStep(hasSeasonCol ? 'seasons' : 'players')}
        />
      )}

      {/* ── Step: Confirm ── */}
      {step === 'confirm' && (
        <ReviewStep
          resolved={resolved} resolving={resolving} committing={committing} committed={committed}
          unresolved={unresolved} onCommit={commit}
          onBack={() => setStep(hasGradeCol ? 'grades' : hasSeasonCol ? 'seasons' : 'players')}
          onReset={reset}
        />
      )}

      {step === 'upload' && (
        <PastImports history={history} expandedBatch={expandedBatch} batchPlayers={batchPlayers}
          loadingBatchPlayers={loadingBatchPlayers} onToggle={toggleBatch} onUndo={undo} />
      )}
    </div>
  )
}
