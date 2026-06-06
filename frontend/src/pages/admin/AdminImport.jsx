import { useState, useEffect, useMemo, useCallback } from 'react'
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
          <MatchTable
            title="Match players" subtitle="Each name from your sheet is matched to a player. Confirm the highlighted ones; pick or create the rest. Names that match two players must be merged first."
            rows={(resolved?.players) || []} kind="player" allOptions={allPlayers}
            valueFor={(r) => {
              const ov = playerOverrides[r.raw_name]
              if (ov) return ov
              if (r.player_id) return r.player_id
              return ''
            }}
            onChange={(r, v) => setPOverride(r.raw_name, v)}
            cell={cell}
            nextLabel={granularity === 'season' ? 'NEXT: SEASONS →' : 'NEXT: REVIEW →'}
            onNext={() => setStep(granularity === 'season' ? 'seasons' : 'review')}
            onBack={() => setStep('map')}
          />
        )}

        {/* ── Step: Match seasons ── */}
        {step === 'seasons' && (
          <MatchTable
            title="Match seasons" subtitle="Match each season label to one of your seasons. A catch-all row like “Prior Seasons & Adjustments” should be the Prior/Historical bucket — it becomes the residual that fills in everything online data doesn't have."
            rows={(resolved?.seasons) || []} kind="season" allOptions={allSeasons.map(s => ({ id: s.id, name: s.name }))}
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

// ── shared match table for players + seasons ─────────────────────────────────
function MatchTable({ title, subtitle, rows, kind, allOptions, valueFor, onChange, cell, nextLabel, onNext, onBack }) {
  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">{title}</h2>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">{subtitle}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[600px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">{kind === 'player' ? 'NAME IN SHEET' : 'SEASON LABEL'}</th>
                <th className="py-2 pr-2 w-28">STATUS</th>
                <th className="py-2 pr-2">MATCH TO</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const label = kind === 'player' ? r.raw_name : r.raw_label
                const value = valueFor(r)
                return (
                  <tr key={i} className="pb-hairline-t align-middle">
                    <td className="py-2 pr-2 text-pb-text">
                      {label}
                      {r.note && <div className="text-[10px] text-pb-red/60 mt-0.5">{r.note}</div>}
                    </td>
                    <td className="py-2 pr-2"><StatusBadge status={r.status} /></td>
                    <td className="py-2 pr-2">
                      <select className={`${cell} w-full max-w-md`} value={value} onChange={e => onChange(r, e.target.value)}>
                        <option value="">— Unresolved (skipped) —</option>
                        {(r.candidates || []).length > 0 && (
                          <optgroup label="Suggested">
                            {r.candidates.map(c => (
                              <option key={(kind === 'player' ? c.player_id : c.season_id)} value={kind === 'player' ? c.player_id : c.season_id}>
                                {c.name}{c.confidence != null ? ` (${Math.round(c.confidence * 100)}%)` : ''}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        <optgroup label={kind === 'player' ? 'All players' : 'All seasons'}>
                          {allOptions.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                        </optgroup>
                        {kind === 'player'
                          ? <option value="__new__">+ Create new player</option>
                          : <option value="__prior__">↪ Prior / Historical bucket</option>}
                        <option value="__skip__">Skip this {kind}</option>
                      </select>
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && <tr><td colSpan={3} className="py-4 text-center text-pb-dim text-[12px]">Nothing to match.</td></tr>}
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
            {totals.players_matched} matched · {totals.rows_skipped || 0} skipped{resolving ? ' · syncing…' : ''}
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
              {preview.map(p => (
                <tr key={p.player_id} className="pb-hairline-t">
                  <td className="py-2 pr-2 text-pb-text">{p.player_name}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.club_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(p.gr_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-accent text-right">+{num(p.residual_games)}</td>
                  <td className="py-2 pr-2 font-mono text-[12px] text-pb-text text-right font-semibold">{num(p.final_games)}</td>
                  <td className="py-2 pr-2">{p.gr_exceeds && <span className="font-mono text-[9px] text-pb-amber" title="Online data already shows more than your sheet — we show the higher online figure.">GR HIGHER</span>}</td>
                </tr>
              ))}
              {preview.length === 0 && <tr><td colSpan={6} className="py-4 text-center text-pb-dim">No matched players yet — go back and resolve the matches.</td></tr>}
            </tbody>
          </table>
        </div>
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
