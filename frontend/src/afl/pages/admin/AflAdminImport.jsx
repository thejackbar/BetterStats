import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'
import {
  num, FieldRow, MatchTable, PlayerMatch, parseSeasonGuess,
} from './importMatching'

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

const STEP_LABELS = { upload: 'Upload', columns: 'Columns', players: 'Players', seasons: 'Seasons', grades: 'Grades', confirm: 'Confirm' }

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
                  <td className="py-2 pr-2">{p.already_synced_overlap && <span className="font-mono text-[9px] text-pb-faint" title="Some season(s) shown here are already synced from PlayHQ. Those rows still import but the synced figures win.">already synced</span>}</td>
                </tr>
              ))}
              {resolving && preview.length === 0 && <tr><td colSpan={8} className="py-8 text-center"><LoadingSpinner message="Reconciling…" /></td></tr>}
              {!resolving && preview.length === 0 && <tr><td colSpan={8} className="py-4 text-center text-pb-dim">No matched players yet. Go back and resolve the matches.</td></tr>}
            </tbody>
          </table>
        </div>
        {preview.length > shownPreview.length && (
          <p className="font-mono text-[10px] text-pb-faintest mt-2">Showing the top {shownPreview.length} of {preview.length} players by games. All will be imported.</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        {unresolved > 0 && <span className="font-mono text-[10px] text-pb-amber">{unresolved} player(s) still unresolved, they'll be skipped.</span>}
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
                            <span className="text-pb-dim">{p.player_name} {p.season_label ? `, ${p.season_label}` : ''} {p.grade_label ? `(${p.grade_label})` : ''}</span>
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

  // Live-reconcile whenever the mapping or any override changes, mirrors
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
      `Created ${created} season${created === 1 ? '' : 's'}` + (failed ? `. ${failed} couldn't be created (name already exists; pick it from the list instead)` : '')
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
        Bring in historical season stats from a spreadsheet, for seasons PlayHQ's own data doesn't
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
            Headers can be anything, we map them in the next step.{' '}
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
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence} onMap={setMap} />
              ))}
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">SEASON STATS</div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {STAT_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence} onMap={setMap} />
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
          rows={resolved?.players || []} sheetLine={r => sheetStatLine(sheetStats[r.raw_name])} allPlayers={allPlayers}
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
          subtitle="Match each season label to one of your club's seasons. Anything we can't match defaults to unassigned. Those rows still import, just without a season link."
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
          subtitle="Match each grade or team label from your sheet to a grade name we already hold for this club. Leave it as-is if it genuinely predates online records. It's kept as its own historical label rather than matched to the wrong grade."
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
