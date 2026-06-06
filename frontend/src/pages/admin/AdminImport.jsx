import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

// ── field metadata for the column-mapping step ───────────────────────────────
const FIELD_GROUPS = [
  ['Identity', ['player_name', 'season_label', 'grade_label']],
  ['Batting', ['games_played', 'batting_innings', 'batting_runs', 'batting_not_outs', 'batting_balls',
    'batting_high_score', 'batting_average', 'batting_strike_rate', 'batting_fours', 'batting_sixes',
    'batting_fifties', 'batting_hundreds', 'batting_ducks']],
  ['Bowling', ['bowling_innings', 'bowling_overs', 'bowling_balls', 'bowling_maidens', 'bowling_runs',
    'bowling_wickets', 'bowling_average', 'bowling_economy', 'bowling_five_wicket_innings',
    'bowling_best_figures', 'bowling_wides', 'bowling_no_balls']],
  ['Fielding', ['fielding_catches', 'fielding_catches_wk', 'fielding_run_outs', 'fielding_stumpings']],
]
const FIELD_LABEL = {
  player_name: 'Player name', season_label: 'Season', grade_label: 'Grade / Team',
  games_played: 'Games', batting_innings: 'Innings', batting_runs: 'Runs', batting_not_outs: 'Not outs',
  batting_balls: 'Balls faced', batting_high_score: 'High score', batting_average: 'Bat average',
  batting_strike_rate: 'Strike rate', batting_fours: '4s', batting_sixes: '6s', batting_fifties: '50s',
  batting_hundreds: '100s', batting_ducks: 'Ducks', bowling_innings: 'Bowl innings', bowling_overs: 'Overs',
  bowling_balls: 'Bowl balls', bowling_maidens: 'Maidens', bowling_runs: 'Runs conceded',
  bowling_wickets: 'Wickets', bowling_average: 'Bowl average', bowling_economy: 'Economy',
  bowling_five_wicket_innings: '5WI', bowling_best_figures: 'Best bowling', bowling_wides: 'Wides',
  bowling_no_balls: 'No balls', fielding_catches: 'Catches', fielding_catches_wk: 'Catches (wk)',
  fielding_run_outs: 'Run outs', fielding_stumpings: 'Stumpings',
}
const REQUIRED = ['player_name']

const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'
const num = n => Number(n || 0).toLocaleString()

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
    new: ['NEW PLAYER', 'text-pb-accent border-pb-accent/40'],
    skip: ['SKIP', 'text-pb-faint border-pb-faint/30'],
    prior: ['PRIOR/ADJ', 'text-pb-accent border-pb-accent/40'],
  }
  const [label, tone] = map[status] || [status?.toUpperCase() || '—', 'text-pb-faint border-pb-faint/30']
  return <span className={`font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 ${tone}`}>{label}</span>
}

const STEP_LABELS = { upload: 'Upload', map: 'Columns', players: 'Players', seasons: 'Seasons', review: 'Review' }

export default function AdminImport() {
  const toast = useToast()

  const [step, setStep] = useState('upload')
  const [file, setFile] = useState(null)
  const [parsing, setParsing] = useState(false)
  const [parsed, setParsed] = useState(null)          // { headers, rows, mapping_suggestions, ... }
  const [mapping, setMapping] = useState({})          // field -> column header
  const [confByField, setConfByField] = useState({})  // field -> confidence (display only)
  const [granularity, setGranularity] = useState('career')
  const [playerOverrides, setPlayerOverrides] = useState({})
  const [seasonOverrides, setSeasonOverrides] = useState({})
  const [resolved, setResolved] = useState(null)
  const [resolving, setResolving] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [allSeasons, setAllSeasons] = useState([])
  const [history, setHistory] = useState([])

  const loadHistory = useCallback(() => {
    api.importList().then(d => setHistory(d.imports || [])).catch(() => {})
  }, [])
  useEffect(() => {
    api.adminListPlayers().then(p => setAllPlayers((p || []).map(x => ({ id: x.id, name: x.display_name || x.name })))).catch(() => {})
    api.adminListSeasons().then(s => setAllSeasons((s || []).filter(x => !x.alias_of))).catch(() => {})
    loadHistory()
  }, [loadHistory])

  const steps = useMemo(
    () => granularity === 'season' ? ['upload', 'map', 'players', 'seasons', 'review'] : ['upload', 'map', 'players', 'review'],
    [granularity],
  )

  // Keep the reconciliation preview fresh whenever the mapping or matches change.
  useEffect(() => {
    if (!parsed) return
    let cancelled = false
    setResolving(true)
    const payload = {
      rows: parsed.rows, mapping, granularity,
      player_overrides: playerOverrides, season_overrides: seasonOverrides,
    }
    const t = setTimeout(() => {
      api.importResolve(payload)
        .then(r => { if (!cancelled) setResolved(r) })
        .catch(e => { if (!cancelled) toast.error(e.message) })
        .finally(() => { if (!cancelled) setResolving(false) })
    }, 200)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parsed, JSON.stringify(mapping), granularity, JSON.stringify(playerOverrides), JSON.stringify(seasonOverrides)])

  // No-match names default to "create new player" — so the No-match bucket is
  // pre-filled and you never scroll past 1,000 players to add one.
  useEffect(() => {
    const ps = resolved?.players
    if (!ps) return
    setPlayerOverrides(prev => {
      let changed = false
      const next = { ...prev }
      for (const p of ps) {
        if (p.auto_status === 'none' && !(p.raw_name in next)) { next[p.raw_name] = '__new__'; changed = true }
      }
      return changed ? next : prev
    })
  }, [resolved?.players])

  // Seasons we couldn't match to a club season default to the "Career summary"
  // bucket (the adjustment residual) — a single place to dump unmatched history.
  useEffect(() => {
    const ss = resolved?.seasons
    if (!ss) return
    setSeasonOverrides(prev => {
      let changed = false
      const next = { ...prev }
      for (const s of ss) {
        if (s.auto_status === 'none' && !(s.raw_label in next)) { next[s.raw_label] = '__prior__'; changed = true }
      }
      return changed ? next : prev
    })
  }, [resolved?.seasons])

  async function runParse() {
    if (!file) return
    setParsing(true); setParsed(null); setResolved(null); setCommitted(null)
    setPlayerOverrides({}); setSeasonOverrides({})
    try {
      const p = await api.importPreview(file)
      const m = {}, c = {}
      Object.entries(p.mapping_suggestions || {}).forEach(([f, v]) => { m[f] = v.column; c[f] = v.confidence })
      setParsed(p); setMapping(m); setConfByField(c); setGranularity(p.granularity_guess || 'career')
      setStep('map')
      toast.success(`Parsed ${p.row_count} row${p.row_count === 1 ? '' : 's'}`)
    } catch (e) { toast.error(e.message) } finally { setParsing(false) }
  }

  function setMap(field, col) {
    setMapping(m => { const n = { ...m }; if (col) n[field] = col; else delete n[field]; return n })
    setConfByField(c => ({ ...c, [field]: undefined }))
  }
  function setPOverride(name, val) {
    setPlayerOverrides(o => { const n = { ...o }; if (val === '' ) delete n[name]; else n[name] = val; return n })
  }
  function setPOverridesBulk(patch) { setPlayerOverrides(o => ({ ...o, ...patch })) }
  function setSOverride(label, val) {
    setSeasonOverrides(o => { const n = { ...o }; if (val === '') delete n[label]; else n[label] = val; return n })
  }

  const mapReady = REQUIRED.every(f => mapping[f])
  const unresolved = (resolved?.totals?.players_unresolved) || 0

  async function commit() {
    setCommitting(true)
    try {
      const res = await api.importCommit({
        rows: parsed.rows, mapping, granularity, filename: file?.name,
        player_overrides: playerOverrides, season_overrides: seasonOverrides,
      })
      setCommitted(res)
      loadHistory()
      toast.success(`Imported ${res.players_imported} player${res.players_imported === 1 ? '' : 's'}`)
    } catch (e) { toast.error(e.message) } finally { setCommitting(false) }
  }

  async function undo(batchId) {
    if (!window.confirm('Remove this import and rebuild the affected players’ stats?')) return
    try {
      const r = await api.importUndo(batchId)
      toast.success(`Removed ${r.rows_removed} imported rows`)
      loadHistory()
    } catch (e) { toast.error(e.message) }
  }

  function reset() {
    setStep('upload'); setFile(null); setParsed(null); setResolved(null); setCommitted(null)
    setMapping({}); setPlayerOverrides({}); setSeasonOverrides({})
  }

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <Link to="/admin" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">← ADMIN</Link>
        <h1 className="font-display font-bold text-2xl text-pb-text mt-2 mb-1">Import historical stats</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed max-w-3xl">
          Pull your online (Grassroots) data first, then upload your club's own spreadsheet — career totals or
          season-by-season, any column layout. We smart-match the columns and reconcile against what's already online:
          where the two overlap, the online data wins, and only the part it's missing is added. <span className="text-pb-dim">A
          player can never be double-counted.</span>
        </p>

        {/* Stepper */}
        <div className="flex items-center gap-1 mb-6 flex-wrap">
          {steps.map((s, i) => {
            const active = s === step
            const done = steps.indexOf(step) > i
            const reachable = parsed || s === 'upload'
            return (
              <button key={s} disabled={!reachable}
                onClick={() => reachable && setStep(s)}
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

        {/* ── Step: Upload ── */}
        {step === 'upload' && (
          <div className="pb-card p-5 mb-6">
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
              <div>
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">CSV OR EXCEL FILE</label>
                <input type="file" accept=".csv,.xlsx,.xlsm,text/csv"
                  onChange={e => setFile(e.target.files?.[0] || null)}
                  className="block text-pb-dim text-sm file:bg-pb-surface2 file:border file:pb-hairline file:rounded file:px-3 file:py-1.5 file:mr-3 file:font-mono file:text-[10px] file:text-pb-text file:cursor-pointer" />
              </div>
              <button onClick={runParse} disabled={!file || parsing}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
                {parsing ? 'PARSING…' : 'PARSE FILE'}
              </button>
            </div>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              Headers can be anything — we map them in the next step. <a href="/api/club-admin/imports/template.csv" className="text-pb-accent hover:underline">Download a template</a>.
            </p>
          </div>
        )}
        {parsing && <PbSpinner message="Parsing file…" />}

        {/* ── Step: Map columns ── */}
        {step === 'map' && parsed && (
          <>
            <div className="pb-card p-5 mb-4">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div>
                  <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">THIS SHEET HOLDS</div>
                  <div className="flex gap-1">
                    {['career', 'season'].map(g => (
                      <button key={g} onClick={() => setGranularity(g)}
                        className={`font-mono text-[10px] tracking-wide2 px-3 py-1.5 rounded border ${granularity === g ? 'text-pb-bg border-transparent' : 'text-pb-faint pb-hairline hover:text-pb-text'}`}
                        style={granularity === g ? { background: 'var(--pb-accent)' } : undefined}>
                        {g === 'career' ? 'CAREER TOTALS' : 'SEASON-BY-SEASON'}
                      </button>
                    ))}
                  </div>
                </div>
                <span className="font-mono text-[10px] text-pb-faint">{parsed.row_count} rows · {parsed.headers.length} columns</span>
              </div>
              {FIELD_GROUPS.map(([group, fields]) => (
                <div key={group} className="mb-4">
                  <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">{group.toUpperCase()}</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {fields.map(f => (
                      <div key={f} className="flex items-center gap-2">
                        <label className="text-[11px] text-pb-dim w-24 shrink-0">
                          {FIELD_LABEL[f]}{REQUIRED.includes(f) && <span className="text-pb-red/70">*</span>}
                        </label>
                        <select className={`${cell} flex-1`} value={mapping[f] || ''} onChange={e => setMap(f, e.target.value)}>
                          <option value="">—</option>
                          {parsed.headers.map(h => <option key={h} value={h}>{h}</option>)}
                        </select>
                        {confByField[f] != null && <Pct score={confByField[f]} />}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3">
              {!mapReady && <span className="font-mono text-[10px] text-pb-red/70">Map the Player name column to continue.</span>}
              <button onClick={() => setStep('players')} disabled={!mapReady}
                className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                NEXT: MATCH PLAYERS →
              </button>
            </div>
          </>
        )}

        {/* ── Step: Match players ── */}
        {step === 'players' && (
          <PlayerMatch
            rows={(resolved?.players) || []} allPlayers={allPlayers}
            overrides={playerOverrides} setOverride={setPOverride} setOverridesBulk={setPOverridesBulk}
            loading={resolving} cell={cell}
            nextLabel={granularity === 'season' ? 'NEXT: SEASONS →' : 'NEXT: REVIEW →'}
            onNext={() => setStep(granularity === 'season' ? 'seasons' : 'review')}
            onBack={() => setStep('map')}
          />
        )}

        {/* ── Step: Match seasons ── */}
        {step === 'seasons' && (
          <MatchTable
            title="Match seasons" subtitle="Match each season label to one of your seasons. Anything we can't match (and catch-all rows like “Prior Seasons & Adjustments”) defaults to Career summary (no season) — a single adjustment bucket that fills in everything online data doesn't already hold."
            rows={(resolved?.seasons) || []} kind="season" allOptions={allSeasons.map(s => ({ id: s.id, name: s.name }))}
            loading={resolving}
            valueFor={(r) => {
              const ov = seasonOverrides[r.raw_label]
              if (ov) return ov
              if (r.is_prior) return '__prior__'
              if (r.season_id) return r.season_id
              return ''
            }}
            onChange={(r, v) => setSOverride(r.raw_label, v)}
            cell={cell}
            nextLabel="NEXT: REVIEW →" onNext={() => setStep('review')} onBack={() => setStep('players')}
          />
        )}

        {/* ── Step: Review & commit ── */}
        {step === 'review' && (
          <ReviewStep
            resolved={resolved} resolving={resolving} committing={committing} committed={committed}
            unresolved={unresolved} onCommit={commit} onBack={() => setStep(granularity === 'season' ? 'seasons' : 'players')}
            onReset={reset} num={num}
          />
        )}

        {/* ── Past imports ── */}
        {history.length > 0 && step === 'upload' && (
          <div className="pb-card p-5">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">PAST IMPORTS</div>
            <table className="w-full text-[12px]">
              <tbody>
                {history.map(h => (
                  <tr key={h.id} className="pb-hairline-t">
                    <td className="py-2 pr-2 text-pb-text">{h.filename || '(unnamed)'}</td>
                    <td className="py-2 pr-2 font-mono text-[10px] text-pb-faint">{h.granularity}</td>
                    <td className="py-2 pr-2 font-mono text-[10px] text-pb-dim">{h.stats_rows} rows</td>
                    <td className="py-2 pr-2 font-mono text-[10px] text-pb-faintest">{h.created_at?.slice(0, 10)}</td>
                    <td className="py-2 pr-2 text-right">
                      {h.undone_at
                        ? <span className="font-mono text-[9px] text-pb-faint">UNDONE</span>
                        : <button onClick={() => undo(h.id)} className="font-mono text-[9px] tracking-wide2 text-pb-red/70 hover:text-pb-red border border-pb-red/30 rounded px-2 py-0.5">UNDO</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}

// ── searchable picker — renders only a handful of options at a time, so it
//    scales to thousands of players without freezing the page ─────────────────
const RESOLVED_STATUSES = ['exact', 'manual', 'matched']
const PAGE_SIZE = 50

function valueLabel(value, idName, kind) {
  if (!value) return '— Unresolved (skipped) —'
  if (value === '__new__') return '+ Create new player'
  if (value === '__skip__') return 'Skip'
  if (value === '__prior__') return '↪ Career summary (no season)'
  return idName.get(value) || '(selected)'
}

function SearchSelect({ value, idName, candidates, options, onChange, kind, cell }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    const base = ql ? options.filter(o => (o.name || '').toLowerCase().includes(ql)) : options
    return base.slice(0, 25)
  }, [q, options])
  const pick = v => { onChange(v); setOpen(false); setQ('') }
  const item = 'block w-full text-left px-2 py-1 text-[12px] text-pb-dim hover:bg-pb-surface2 hover:text-pb-text rounded'
  const unresolved = !value
  return (
    <div className="relative max-w-md" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className={`${cell} w-full text-left flex items-center justify-between ${unresolved ? 'text-pb-amber' : ''}`}>
        <span className="truncate">{valueLabel(value, idName, kind)}</span>
        <span className="text-pb-faint ml-2">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-72 max-h-72 overflow-auto bg-pb-surface border pb-hairline rounded shadow-xl p-1">
          <button className={item} onClick={() => pick(kind === 'player' ? '__new__' : '__prior__')}>
            {kind === 'player' ? '+ Create new player' : '↪ Career summary (no season)'}
          </button>
          <button className={item} onClick={() => pick('__skip__')}>Skip this {kind}</button>
          {(candidates || []).length > 0 && <div className="px-2 pt-2 pb-1 font-mono text-[9px] tracking-wide2 text-pb-faint">SUGGESTED</div>}
          {(candidates || []).map(c => (
            <button key={c.id} className={item} onClick={() => pick(c.id)}>
              {c.name}{c.confidence != null ? <span className="text-pb-faint"> ({Math.round(c.confidence * 100)}%)</span> : ''}
            </button>
          ))}
          <div className="px-1 pt-2 pb-1 sticky top-0">
            <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder={`Search all ${kind === 'player' ? 'players' : 'seasons'}…`}
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent" />
          </div>
          {filtered.map(o => <button key={o.id} className={item} onClick={() => pick(o.id)}>{o.name}</button>)}
          {filtered.length === 0 && <div className="px-2 py-1 text-[11px] text-pb-faint">No matches</div>}
        </div>
      )}
    </div>
  )
}

// ── shared match table for players + seasons (filter + paginate for scale) ────
function MatchTable({ title, subtitle, rows, kind, allOptions, valueFor, onChange, cell, nextLabel, onNext, onBack, loading }) {
  const [onlyReview, setOnlyReview] = useState(true)
  const [page, setPage] = useState(0)

  const idName = useMemo(() => {
    const m = new Map()
    allOptions.forEach(o => m.set(o.id, o.name))
    rows.forEach(r => {
      (r.candidates || []).forEach(c => m.set(kind === 'player' ? c.player_id : c.season_id, c.name))
      if (r.matched_name) m.set(kind === 'player' ? r.player_id : r.season_id, r.matched_name)
    })
    return m
  }, [allOptions, rows, kind])

  const counts = useMemo(() => {
    let resolved = 0, review = 0
    rows.forEach(r => { (RESOLVED_STATUSES.includes(r.status) ? resolved++ : review++) })
    return { resolved, review, total: rows.length }
  }, [rows])

  const shown = useMemo(
    () => onlyReview ? rows.filter(r => !RESOLVED_STATUSES.includes(r.status)) : rows,
    [rows, onlyReview],
  )
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
          <table className="w-full text-[12px] min-w-[600px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">{kind === 'player' ? 'NAME IN SHEET' : 'SEASON LABEL'}</th>
                <th className="py-2 pr-2 w-28">STATUS</th>
                <th className="py-2 pr-2">MATCH TO</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                const label = kind === 'player' ? r.raw_name : r.raw_label
                const value = valueFor(r)
                const candidates = (r.candidates || []).map(c => ({
                  id: kind === 'player' ? c.player_id : c.season_id, name: c.name, confidence: c.confidence,
                }))
                return (
                  <tr key={(label || '') + i} className="pb-hairline-t align-middle">
                    <td className="py-2 pr-2 text-pb-text">
                      {label}
                      {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                    </td>
                    <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                    <td className="py-2 pr-2">
                      <SearchSelect value={value} idName={idName} candidates={candidates} options={allOptions}
                        onChange={v => onChange(r, v)} kind={kind} cell={cell} />
                    </td>
                  </tr>
                )
              })}
              {loading && rows.length === 0 && (
                <tr><td colSpan={3} className="py-8 text-center"><PbSpinner message={`Matching ${kind === 'player' ? 'players' : 'seasons'}…`} /></td></tr>
              )}
              {!loading && rows.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-pb-dim text-[12px]">Nothing to match.</td></tr>}
              {!loading && rows.length > 0 && shown.length === 0 && (
                <tr><td colSpan={3} className="py-4 text-center text-green-300 text-[12px]">All {kind === 'player' ? 'players' : 'seasons'} matched — nothing to review.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>{nextLabel}</button>
      </div>
    </>
  )
}

// ── player matching, in three passes: confirm matched / review close / no-match
function PlayerMatch({ rows, allPlayers, overrides, setOverride, setOverridesBulk, loading, cell, nextLabel, onNext, onBack }) {
  const [tab, setTab] = useState(null)
  const [page, setPage] = useState(0)

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
      if (['exact', 'manual', 'matched'].includes(st)) matched.push(r)
      else if (['fuzzy', 'ambiguous'].includes(st)) close.push(r)
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
  const valueFor = r => { const ov = overrides[r.raw_name]; if (ov) return ov; if (r.player_id) return r.player_id; return '' }

  function confirmAllSuggested() {
    const patch = {}
    buckets.close.forEach(r => { const c = (r.candidates || [])[0]; if (c) patch[r.raw_name] = c.player_id })
    setOverridesBulk(patch)
  }
  function bulkNomatch(val) {
    const patch = {}; buckets.nomatch.forEach(r => { patch[r.raw_name] = val }); setOverridesBulk(patch)
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
          Three quick passes: confirm the exact matches, review the close ones, then anything with no match defaults to a brand-new player.
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
                {buckets.matched.length} name{buckets.matched.length === 1 ? '' : 's'} matched your players exactly — nothing to do unless one looks wrong.
              </p>
            )}
            {active === 'close' && buckets.close.length > 0 && (
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <p className="text-[12px] text-pb-amber">Pick the right player, or leave it to become a new one.</p>
                <button onClick={confirmAllSuggested}
                  className="ml-auto font-mono text-[10px] tracking-wide2 border border-pb-accent/40 text-pb-accent rounded px-3 py-1.5 hover:bg-pb-accent/10">
                  CONFIRM ALL SUGGESTED
                </button>
              </div>
            )}
            {active === 'nomatch' && buckets.nomatch.length > 0 && (
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <p className="text-[12px] text-pb-faint">These default to <span className="text-pb-accent">new players</span>. Change any that already exist, or skip.</p>
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
                    const candidates = (r.candidates || []).map(c => ({ id: c.player_id, name: c.name, confidence: c.confidence }))
                    return (
                      <tr key={r.raw_name + i} className="pb-hairline-t align-middle">
                        <td className="py-2 pr-2 text-pb-text">
                          {r.raw_name}
                          {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                        </td>
                        <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                        <td className="py-2 pr-2">
                          <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates} options={allPlayers}
                            onChange={v => setOverride(r.raw_name, v)} kind="player" cell={cell} />
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
        <button onClick={onNext} className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>{nextLabel}</button>
      </div>
    </>
  )
}

// ── review + commit ──────────────────────────────────────────────────────────
function ReviewStep({ resolved, resolving, committing, committed, unresolved, onCommit, onBack, onReset, num }) {
  if (committed) {
    return (
      <div className="pb-card p-6">
        <div className="font-mono text-[10px] tracking-wide2 text-green-300 mb-2">IMPORT COMPLETE</div>
        <h2 className="font-display font-bold text-xl text-pb-text mb-3">
          {committed.players_imported} players imported{committed.players_created ? `, ${committed.players_created} created` : ''}
        </h2>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed max-w-2xl">
          {committed.rows_written} rows written; the reconciler added {committed.deltas_written} adjustment rows for the part
          online data didn't already hold. {committed.rows_skipped ? `${committed.rows_skipped} unmatched rows were skipped.` : ''}
        </p>
        <div className="flex gap-3">
          <button onClick={onReset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>IMPORT ANOTHER</button>
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
          <h2 className="font-display font-semibold text-lg text-pb-text">Reconciliation preview</h2>
          <span className="font-mono text-[10px] text-pb-faint">
            {totals.players_matched} matched · {totals.players_new || 0} new · {totals.rows_skipped || 0} skipped{resolving ? ' · syncing…' : ''}
          </span>
        </div>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          <span className="text-pb-dim">Final = online (GR) + the residual we add.</span> Where your sheet and online data
          overlap, online wins; the residual is only the part it's missing — so the final can never exceed your club's own total.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[640px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">PLAYER</th>
                <th className="py-2 pr-2 text-right">YOUR SHEET</th>
                <th className="py-2 pr-2 text-right">ONLINE (GR)</th>
                <th className="py-2 pr-2 text-right">+ RESIDUAL</th>
                <th className="py-2 pr-2 text-right">= FINAL GAMES</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {shownPreview.map(p => (
                <tr key={p.player_id || `new:${p.player_name}`} className="pb-hairline-t">
                  <td className="py-2 pr-2 text-pb-text">
                    {p.player_name}
                    {p.new && <span className="ml-2 font-mono text-[8px] tracking-wide2 text-pb-accent border border-pb-accent/40 rounded px-1 py-0.5">NEW</span>}
                  </td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.club_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.gr_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-accent text-right">+{num(p.residual_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[12px] text-pb-text text-right font-semibold">{num(p.final_games)}</td>
                  <td className="py-2 pr-2">{p.gr_exceeds && <span className="font-mono text-[9px] text-pb-amber" title="Online data already shows more than your sheet — we show the higher online figure.">GR HIGHER</span>}</td>
                </tr>
              ))}
              {resolving && preview.length === 0 && <tr><td colSpan={6} className="py-8 text-center"><PbSpinner message="Reconciling…" /></td></tr>}
              {!resolving && preview.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-pb-dim">No matched players yet — go back and resolve the matches.</td></tr>}
            </tbody>
          </table>
        </div>
        {preview.length > shownPreview.length && (
          <p className="font-mono text-[10px] text-pb-faintest mt-2">Showing the top {shownPreview.length} of {preview.length} players by games — all will be imported.</p>
        )}
        {(resolved?.rounding_notes || []).length > 0 && (
          <details className="mt-4">
            <summary className="font-mono text-[10px] tracking-wide2 text-pb-faint cursor-pointer">{resolved.rounding_notes.length} reconstructed value(s) — derived from averages (±1)</summary>
            <ul className="mt-2 text-[11px] text-pb-faint space-y-0.5">
              {resolved.rounding_notes.map((n, i) => <li key={i}>· {n}</li>)}
            </ul>
          </details>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        {unresolved > 0 && <span className="font-mono text-[10px] text-pb-amber">{unresolved} player(s) still unresolved — they'll be skipped.</span>}
        <button onClick={onCommit} disabled={committing || preview.length === 0}
          className="ml-auto px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          {committing ? 'IMPORTING…' : `IMPORT ${preview.length} PLAYER${preview.length === 1 ? '' : 'S'}`}
        </button>
      </div>
    </>
  )
}
