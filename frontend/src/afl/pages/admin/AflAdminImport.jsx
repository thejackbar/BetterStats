import { Fragment, useEffect, useRef, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

const STEPS = ['Upload', 'Columns', 'Players', 'Seasons', 'Grades', 'Confirm']

const FIELD_LABELS = {
  player_name: 'Player name', season_label: 'Season', grade_label: 'Grade / team',
  games_played: 'Games', goals: 'Goals', behinds: 'Behinds', bog_count: 'Best on Ground', captain_games: 'Captain games',
  club_bf_votes: 'Club B&F votes', comp_bf_votes: 'Competition B&F votes',
}
const FIELD_ORDER = ['player_name', 'season_label', 'grade_label', 'games_played', 'goals', 'behinds', 'bog_count', 'captain_games', 'club_bf_votes', 'comp_bf_votes']
const REQUIRED_FIELDS = new Set(['player_name'])

function Stepper({ step }) {
  const idx = STEPS.indexOf(step)
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs font-mono uppercase">
      {STEPS.map((s, i) => (
        <span key={s} className={`px-2 py-1 rounded ${i === idx ? 'bg-[var(--pb-accent)] text-black font-semibold'
          : i < idx ? 'text-[var(--pb-positive)]' : 'text-pb-faint'}`}>
          {i + 1}. {s}
        </span>
      ))}
    </div>
  )
}

function PastImports({ refreshKey }) {
  const [batches, setBatches] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [players, setPlayers] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { aflApi.importsList().then(setBatches).catch(() => setBatches([])) }, [refreshKey])

  const toggle = async (b) => {
    if (expanded === b.id) { setExpanded(null); return }
    setExpanded(b.id)
    setPlayers(null)
    aflApi.importsBatchPlayers(b.id).then(setPlayers).catch(() => setPlayers([]))
  }

  const undo = async (b) => {
    if (!window.confirm(`Undo this import (${b.filename})? Every row it added will be removed.`)) return
    setBusy(true)
    try {
      await aflApi.importsUndo(b.id)
      aflApi.importsList().then(setBatches).catch(() => {})
    } catch (err) {
      window.alert(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (batches === null || batches.length === 0) return null

  return (
    <div className="pb-card p-4">
      <SectionTitle>Past imports</SectionTitle>
      <table className="w-full text-sm">
        <tbody>
          {batches.map(b => (
            <Fragment key={b.id}>
              <tr className="pb-hairline-b last:border-0">
                <td className="px-2 py-1.5">{b.filename || 'Untitled'}</td>
                <td className="px-2 py-1.5 text-pb-faint">{(b.committed_at || b.created_at || '').replace('T', ' ').slice(0, 16)}</td>
                <td className="px-2 py-1.5 text-right pb-num">{b.row_count} rows</td>
                <td className="px-2 py-1.5 text-right">
                  <button onClick={() => toggle(b)} className="text-xs text-pb-dim hover:text-pb-text underline mr-3">
                    {expanded === b.id ? 'Hide' : 'Show players'}
                  </button>
                  {b.status === 'undone'
                    ? <span className="text-xs text-pb-faint">Undone</span>
                    : <button disabled={busy} onClick={() => undo(b)} className="text-xs text-[var(--pb-negative)] hover:opacity-80 underline">Undo</button>}
                </td>
              </tr>
              {expanded === b.id && (
                <tr>
                  <td colSpan={4} className="px-2 pb-3">
                    {players === null ? <span className="text-xs text-pb-faint">Loading…</span> : (
                      <div className="pb-card p-2 space-y-1">
                        {players.map((p, i) => (
                          <div key={i} className="text-xs flex justify-between">
                            <span>{p.player_name} {p.season_label ? `— ${p.season_label}` : ''} {p.grade_label ? `(${p.grade_label})` : ''}</span>
                            <span className="text-pb-faint">
                              {p.games_played}g {p.goals}gl {p.behinds}b
                              {(p.club_bf_votes || p.comp_bf_votes) ? ` · ${p.club_bf_votes || 0} club/${p.comp_bf_votes || 0} comp votes` : ''}
                            </span>
                          </div>
                        ))}
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
  const [step, setStep] = useState('Upload')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [historyKey, setHistoryKey] = useState(0)
  const fileRef = useRef(null)
  const [filename, setFilename] = useState(null)

  const [headers, setHeaders] = useState([])
  const [rows, setRows] = useState([])
  const [mapping, setMapping] = useState({})

  const [playerOverrides, setPlayerOverrides] = useState({})
  const [seasonOverrides, setSeasonOverrides] = useState({})
  const [gradeOverrides, setGradeOverrides] = useState({})
  const [resolved, setResolved] = useState(null)

  const [result, setResult] = useState(null)

  const reset = () => {
    setStep('Upload'); setHeaders([]); setRows([]); setMapping({})
    setPlayerOverrides({}); setSeasonOverrides({}); setGradeOverrides({})
    setResolved(null); setResult(null); setFilename(null)
  }

  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const res = await aflApi.importsPreview(file)
      setHeaders(res.headers)
      setRows(res.rows)
      setMapping(res.mapping)
      setFilename(file.name)
      setStep('Columns')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const mappedColumn = (field) => mapping[field]?.column || ''
  const setMappedColumn = (field, column) => {
    setMapping(m => column ? { ...m, [field]: { column, confidence: 1 } } : (() => { const n = { ...m }; delete n[field]; return n })())
  }

  const doResolve = async (extraOverrides = {}) => {
    setBusy(true)
    setError(null)
    try {
      const body = {
        rows, mapping,
        player_overrides: { ...playerOverrides, ...(extraOverrides.player_overrides || {}) },
        season_overrides: { ...seasonOverrides, ...(extraOverrides.season_overrides || {}) },
        grade_overrides: { ...gradeOverrides, ...(extraOverrides.grade_overrides || {}) },
      }
      const res = await aflApi.importsResolve(body)
      setResolved(res)
      return res
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setBusy(false)
    }
  }

  const confirmColumns = async () => {
    if (!mappedColumn('player_name')) { setError('Map a column to Player name before continuing.'); return }
    await doResolve()
    setStep('Players')
  }

  const setPlayerChoice = (name, choice) => {
    setPlayerOverrides(o => ({ ...o, [name]: choice }))
  }
  const bulkApprovePlayers = () => {
    const next = { ...playerOverrides }
    for (const p of resolved?.players || []) {
      if ((p.status === 'exact' || p.status === 'auto') && p.player_id) next[p.raw_name] = p.player_id
    }
    setPlayerOverrides(next)
  }
  const continueToSeasons = async () => {
    await doResolve()
    setStep('Seasons')
  }

  const setSeasonChoice = (label, choice) => setSeasonOverrides(o => ({ ...o, [label]: choice }))
  const continueToGrades = async () => {
    await doResolve()
    setStep(headers.some(h => mappedColumn('grade_label') === h) ? 'Grades' : 'Confirm')
  }

  const setGradeChoice = (label, choice) => setGradeOverrides(o => ({ ...o, [label]: choice }))
  const continueToConfirm = async () => {
    await doResolve()
    setStep('Confirm')
  }

  const doCommit = async () => {
    setBusy(true)
    setError(null)
    try {
      const body = {
        rows, mapping, filename,
        player_overrides: playerOverrides, season_overrides: seasonOverrides, grade_overrides: gradeOverrides,
      }
      const res = await aflApi.importsCommit(body)
      setResult(res)
      setHistoryKey(k => k + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Import Stats</SectionTitle>
        {step !== 'Upload' && !result && (
          <button onClick={reset} className="text-xs text-pb-dim hover:text-pb-text underline">Start over</button>
        )}
      </div>
      <p className="text-sm text-pb-dim max-w-2xl">
        Bring in historical season stats from a spreadsheet — for seasons PlayHQ's
        own data doesn't cover. Upload, match the columns and players, confirm the
        season and grade, then import.
      </p>

      {!result && <Stepper step={step} />}
      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}

      {result && (
        <div className="pb-card p-4 space-y-3">
          <p className="text-sm text-[var(--pb-positive)]">
            Imported {result.players_imported} player{result.players_imported === 1 ? '' : 's'}, {result.rows_written} row{result.rows_written === 1 ? '' : 's'}
            {result.players_created ? ` (${result.players_created} new player${result.players_created === 1 ? '' : 's'} created)` : ''}.
            {result.rows_skipped ? ` ${result.rows_skipped} row(s) skipped.` : ''}
          </p>
          <button onClick={reset} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black">
            Import another file
          </button>
        </div>
      )}

      {!result && step === 'Upload' && (
        <div className="pb-card p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <a href={aflApi.importsTemplateUrl()} className="text-sm text-pb-dim underline hover:text-pb-text">Download CSV template</a>
            <label className="px-4 py-2 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black cursor-pointer">
              {busy ? 'Reading…' : 'Choose CSV file'}
              <input ref={fileRef} type="file" accept=".csv,.xlsx" onChange={onFile} disabled={busy} className="hidden" />
            </label>
          </div>
        </div>
      )}

      {!result && step === 'Columns' && (
        <div className="pb-card p-4 space-y-3">
          <SectionTitle>Match your columns to the right fields</SectionTitle>
          <p className="text-xs text-pb-faint">{rows.length} row(s) found in {filename}.</p>
          <div className="grid grid-cols-2 gap-3 max-w-xl">
            {FIELD_ORDER.map(field => (
              <label key={field} className="text-xs text-pb-faint">
                {FIELD_LABELS[field]}{REQUIRED_FIELDS.has(field) && ' *'}
                <select value={mappedColumn(field)} onChange={e => setMappedColumn(field, e.target.value)}
                        className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm">
                  <option value="">— not in file —</option>
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
            ))}
          </div>
          <button disabled={busy} onClick={confirmColumns} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Matching…' : 'Continue'}
          </button>
        </div>
      )}

      {!result && step === 'Players' && resolved && (
        <div className="pb-card p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <SectionTitle>Match player names</SectionTitle>
            <button onClick={bulkApprovePlayers} className="px-3 py-1.5 rounded text-xs border border-pb-hairline text-pb-text hover:bg-pb-surface2">
              Bulk-approve exact/close matches
            </button>
          </div>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {resolved.players.map(p => {
              const chosen = playerOverrides[p.raw_name] ?? p.player_id
              return (
                <div key={p.raw_name} className="flex items-center justify-between gap-3 text-sm pb-hairline-b pb-2">
                  <span className="min-w-0 truncate">{p.raw_name}</span>
                  <select value={chosen === true ? '__new__' : (chosen || '')}
                          onChange={e => setPlayerChoice(p.raw_name, e.target.value)}
                          className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs shrink-0 max-w-[240px]">
                    <option value="">Skip this name</option>
                    <option value="__new__">Add as new player</option>
                    {p.player_id && !p.candidates?.length && (
                      <option value={p.player_id}>{p.matched_name} ({p.status})</option>
                    )}
                    {(p.candidates || []).map(c => (
                      <option key={c.player_id} value={c.player_id}>{c.name} ({Math.round((c.confidence || 0) * 100)}%)</option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
          <button disabled={busy} onClick={continueToSeasons} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Working…' : 'Continue'}
          </button>
        </div>
      )}

      {!result && step === 'Seasons' && resolved && (
        <div className="pb-card p-4 space-y-3">
          <SectionTitle>Confirm season data</SectionTitle>
          {resolved.seasons.length === 0 && <p className="text-sm text-pb-faint">No season column mapped — every row imports as season-unassigned.</p>}
          <div className="space-y-2">
            {resolved.seasons.map(s => (
              <div key={s.raw_label} className="flex items-center justify-between gap-3 text-sm pb-hairline-b pb-2">
                <span>{s.raw_label}</span>
                <select value={seasonOverrides[s.raw_label] ?? (s.season_id || (s.is_prior ? '__unassigned__' : ''))}
                        onChange={e => setSeasonChoice(s.raw_label, e.target.value)}
                        className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                  <option value="__unassigned__">No matching season — import unassigned</option>
                  {s.season_id && <option value={s.season_id}>{s.matched_name}</option>}
                </select>
              </div>
            ))}
          </div>
          <button disabled={busy} onClick={continueToGrades} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Working…' : 'Continue'}
          </button>
        </div>
      )}

      {!result && step === 'Grades' && resolved && (
        <div className="pb-card p-4 space-y-3">
          <SectionTitle>Confirm grade data</SectionTitle>
          <div className="space-y-2">
            {resolved.grades.map(g => (
              <div key={g.raw_label} className="flex items-center justify-between gap-3 text-sm pb-hairline-b pb-2">
                <span>{g.raw_label}</span>
                <select value={gradeOverrides[g.raw_label] ?? (g.grade_name || '__own__')}
                        onChange={e => setGradeChoice(g.raw_label, e.target.value)}
                        className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs">
                  <option value="__own__">Use this label as-is</option>
                  {resolved.grade_options.map(name => <option key={name} value={name}>{name}</option>)}
                </select>
              </div>
            ))}
            {resolved.grades.length === 0 && <p className="text-sm text-pb-faint">No grade column mapped.</p>}
          </div>
          <button disabled={busy} onClick={continueToConfirm} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Working…' : 'Continue'}
          </button>
        </div>
      )}

      {!result && step === 'Confirm' && resolved && (
        <div className="pb-card p-4 space-y-3">
          <SectionTitle>Confirm import</SectionTitle>
          {resolved.warnings.map((w, i) => (
            <p key={i} className="text-xs text-[var(--pb-amber)]">{w}</p>
          ))}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="pb-hairline-b">
                <tr>{['Player', 'Rows', 'Games', 'Goals', 'Behinds', 'Club B&F', 'Comp B&F', ''].map(h => (
                  <th key={h} className="px-2 py-1.5 text-left font-mono text-[10px] uppercase text-pb-faint">{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {resolved.preview.map((p, i) => (
                  <tr key={i} className="pb-hairline-b last:border-0">
                    <td className="px-2 py-1.5">{p.player_name}{p.new && <span className="ml-2 text-[9px] text-[var(--pb-accent)]">NEW</span>}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.rows}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.games}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.goals}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.behinds}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.club_bf_votes || 0}</td>
                    <td className="px-2 py-1.5 text-right pb-num">{p.comp_bf_votes || 0}</td>
                    <td className="px-2 py-1.5 text-right">
                      {p.already_synced_overlap && <span className="text-[9px] text-pb-faint">already synced</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button disabled={busy} onClick={doCommit} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Importing…' : `Import ${resolved.totals.players_matched + resolved.totals.players_new} player(s)`}
          </button>
        </div>
      )}

      <PastImports refreshKey={historyKey} />
    </div>
  )
}
