import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'
import { num, FieldRow, MatchTable, parseSeasonGuess } from './importMatching'

// Import Results — a club's own results register (one row per match) brought
// in as real games. Sibling of Import Stats (AflAdminImport.jsx, season
// totals per player) and built on the same wizard pieces from
// ./importMatching.
//
// The review step follows Core's Upload Scorecard reader: show what the
// sheet says, say plainly where it doesn't add up, and let the admin choose
// to fix it or keep the club's own figures — nothing is silently corrected
// and nothing is silently dropped.

const FIELD_LABEL = {
  played_on: 'Match date', season_label: 'Season / year', grade_label: 'Team / grade',
  opponent: 'Opposition club', round_label: 'Round', series_label: 'Series',
  home_away: 'Home or away', venue: 'Venue', start_time: 'Start time',
  external_ref: 'Your game ID',
  our_goals: 'Our goals', our_behinds: 'Our behinds', our_score: 'Our score',
  opp_goals: 'Opposition goals', opp_behinds: 'Opposition behinds', opp_score: 'Opposition score',
  margin: 'Margin', outcome: 'Result column',
}
const MATCH_FIELDS = ['played_on', 'season_label', 'grade_label', 'opponent',
  'round_label', 'series_label', 'home_away', 'venue', 'start_time', 'external_ref']
const SCORE_FIELDS = ['our_goals', 'our_behinds', 'our_score',
  'opp_goals', 'opp_behinds', 'opp_score', 'margin']
const RESULT_FIELDS = ['outcome']
const REQUIRED_FIELDS = new Set(['played_on'])

const STEP_LABELS = { upload: 'Upload', columns: 'Columns', seasons: 'Seasons', teams: 'Teams', confirm: 'Review' }
const STEPS = ['upload', 'columns', 'seasons', 'teams', 'confirm']

const STATUS_TONE = {
  ready: ['READY', 'text-green-300 border-green-300/30'],
  update: ['UPDATE', 'text-green-300 border-green-300/30'],
  skipped: ['SKIPPED', 'text-pb-faint border-pb-faint/30'],
  blocked: ['BLOCKED', 'text-pb-red/70 border-pb-red/30'],
  duplicate: ['DUPLICATE', 'text-pb-amber border-pb-amber/30'],
  synced: ['SYNCED', 'text-pb-faint border-pb-faint/30'],
}

function RowStatus({ status }) {
  const [label, tone] = STATUS_TONE[status] || [String(status || '—').toUpperCase(), 'text-pb-faint border-pb-faint/30']
  return <span className={`font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 ${tone}`}>{label}</span>
}

function ResultTag({ result, category }) {
  if (category === 'bye') return <span className="font-mono text-[10px] text-pb-faint">BYE</span>
  const tone = result === 'W' ? 'text-green-300' : result === 'L' ? 'text-pb-red/70' : 'text-pb-amber'
  return <span className={`font-mono text-[11px] font-semibold ${tone}`}>{result || '—'}</span>
}

const scoreLine = (g, b, s) =>
  (g == null && b == null && s == null) ? '—' : `${g ?? 0}.${b ?? 0} (${s ?? 0})`

// Two warning kinds, same split the scorecard reader uses: the sheet's own
// figures contradicting each other, vs something worth a look.
function WarningBox({ kind, children }) {
  const isError = kind === 'sheet_error'
  return (
    <div className={`pb-card p-3 mb-3 border-l-2 ${isError ? 'border-pb-red/50' : 'border-pb-amber/50'}`}>
      <span className={`text-[12px] ${isError ? 'text-pb-red/80' : 'text-pb-amber'}`}>{children}</span>
    </div>
  )
}

// ── review + commit ─────────────────────────────────────────────────────────
const ROW_PAGE = 100
const ROW_FILTERS = [
  ['importable', 'To import'],
  ['warnings', 'With warnings'],
  ['blocked', 'Blocked'],
  ['skipped', 'Skipped'],
  ['all', 'Everything'],
]

function ReviewStep({ resolved, resolving, committing, committed, clubSlug,
                      includeByes, includeForfeits, onToggleByes, onToggleForfeits,
                      onCommit, onBack, onReset }) {
  const [filter, setFilter] = useState('importable')
  const [page, setPage] = useState(0)
  useEffect(() => { setPage(0) }, [filter, resolved?.totals?.rows])

  // Every hook has to run before the committed-screen early return below —
  // a useMemo underneath it would only be reached on some renders.
  const rows = resolved?.rows || []
  const shown = useMemo(() => {
    if (filter === 'all') return rows
    if (filter === 'importable') return rows.filter(r => r.status === 'ready' || r.status === 'update')
    if (filter === 'warnings') return rows.filter(r => (r.warnings || []).length)
    if (filter === 'blocked') return rows.filter(r => r.status === 'blocked')
    return rows.filter(r => r.status === 'skipped' || r.status === 'duplicate' || r.status === 'synced')
  }, [rows, filter])

  if (committed) {
    const total = committed.games_created + committed.games_updated
    return (
      <div className="pb-card p-6">
        <div className="font-mono text-[10px] tracking-wide2 text-green-300 mb-2">IMPORT COMPLETE</div>
        <h2 className="font-display font-bold text-xl text-pb-text mb-3">
          {num(total)} result{total === 1 ? '' : 's'} imported
        </h2>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed max-w-2xl">
          {num(committed.games_created)} new, {num(committed.games_updated)} updated, across{' '}
          {num(committed.grades_touched)} team{committed.grades_touched === 1 ? '' : 's'}.
          {committed.rows_skipped ? ` ${num(committed.rows_skipped)} row(s) skipped.` : ''}
          {committed.rows_blocked ? ` ${num(committed.rows_blocked)} couldn't be imported.` : ''}
          {committed.already_synced ? ` ${num(committed.already_synced)} already came from PlayHQ and were left alone.` : ''}
        </p>
        <div className="flex gap-3 flex-wrap">
          <button onClick={onReset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)]">IMPORT ANOTHER</button>
          {clubSlug && (
            <Link to={`/${clubSlug}/games`} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text">VIEW RESULTS</Link>
          )}
        </div>
      </div>
    )
  }

  const t = resolved?.totals || {}
  const pageCount = Math.max(1, Math.ceil(shown.length / ROW_PAGE))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = shown.slice(safePage * ROW_PAGE, safePage * ROW_PAGE + ROW_PAGE)
  const cat = t.by_category || {}

  return (
    <>
      {(resolved?.warnings || []).map((w, i) => <WarningBox key={i} kind={w.kind}>{w.text}</WarningBox>)}

      <div className="pb-card p-5 mb-4">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="font-display font-semibold text-lg text-pb-text">Review the results</h2>
          <span className="font-mono text-[10px] text-pb-faint">
            {num(t.rows || 0)} row(s) read{resolving ? ' · reading…' : ''}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          {[
            ['To import', t.importable, 'text-green-300'],
            ['Skipped', t.skipped, 'text-pb-faint'],
            ['Blocked', t.blocked, 'text-pb-red/70'],
            ["Don't add up", t.sheet_errors, 'text-pb-amber'],
          ].map(([label, value, tone]) => (
            <div key={label} className="rounded border pb-hairline px-3 py-2">
              <div className="font-mono text-[9px] tracking-wide2 text-pb-faint">{label.toUpperCase()}</div>
              <div className={`font-mono text-lg font-semibold ${tone}`}>{num(value || 0)}</div>
            </div>
          ))}
        </div>

        {/* What the club's own result column said, and what we're doing with it. */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-4 pb-3 pb-hairline-b">
          <span className="font-mono text-[10px] text-pb-faint">
            {num(cat.result || 0)} results · {num(cat.forfeit || 0)} forfeits · {num(cat.bye || 0)} byes ·{' '}
            {num((cat.cancelled || 0) + (cat.no_score || 0))} cancelled or unscored
          </span>
          <label className="flex items-center gap-1.5 text-[12px] text-pb-dim cursor-pointer">
            <input type="checkbox" checked={includeForfeits} onChange={e => onToggleForfeits(e.target.checked)} />
            Import forfeits as wins and losses
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-pb-dim cursor-pointer"
            title="A bye is kept on the record but never counts as a game played, and never as a win, loss or draw.">
            <input type="checkbox" checked={includeByes} onChange={e => onToggleByes(e.target.checked)} />
            Keep byes on the record
          </label>
          <span className="font-mono text-[10px] text-pb-faintest">
            Cancelled and unscored rows are always skipped.
          </span>
        </div>

        {(resolved?.season_summary || []).length > 0 && (
          <div className="mb-5">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">BY SEASON</div>
            <div className="overflow-x-auto max-h-64 overflow-y-auto">
              <table className="w-full text-[12px] min-w-[420px]">
                <thead className="sticky top-0 bg-pb-surface">
                  <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                    <th className="py-1.5 pr-2">SEASON</th>
                    <th className="py-1.5 pr-2 text-right">GAMES</th>
                    <th className="py-1.5 pr-2 text-right">W</th>
                    <th className="py-1.5 pr-2 text-right">L</th>
                    <th className="py-1.5 pr-2 text-right">D</th>
                    <th className="py-1.5 pr-2">TEAMS</th>
                  </tr>
                </thead>
                <tbody>
                  {resolved.season_summary.map(s => (
                    <tr key={s.season_label} className="pb-hairline-t">
                      <td className="py-1.5 pr-2 text-pb-text">{s.season_label}</td>
                      <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-text text-right font-semibold">{num(s.games)}</td>
                      <td className="py-1.5 pr-2 font-mono text-[11px] text-green-300 text-right">{num(s.wins)}</td>
                      <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-red/70 text-right">{num(s.losses)}</td>
                      <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-amber text-right">{num(s.draws)}</td>
                      <td className="py-1.5 pr-2 text-[11px] text-pb-faint truncate max-w-[220px]">{s.grades.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 mb-3">
          {ROW_FILTERS.map(([key, label]) => (
            <button key={key} onClick={() => setFilter(key)}
              className={`font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded border transition-colors ${
                filter === key ? 'text-black border-transparent bg-[var(--pb-accent)]' : 'text-pb-faint pb-hairline hover:text-pb-text'}`}>
              {label}
            </button>
          ))}
          {pageCount > 1 && (
            <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-pb-faint">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={safePage === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
              {safePage + 1} / {pageCount}
              <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={safePage >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[860px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">DATE</th>
                <th className="py-2 pr-2">ROUND</th>
                <th className="py-2 pr-2">TEAM</th>
                <th className="py-2 pr-2">H/A</th>
                <th className="py-2 pr-2">OPPOSITION</th>
                <th className="py-2 pr-2 text-right">US</th>
                <th className="py-2 pr-2 text-right">THEM</th>
                <th className="py-2 pr-2 text-center">RES</th>
                <th className="py-2 pr-2">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map(r => (
                <Fragment key={r.index}>
                  <tr className="pb-hairline-t align-middle">
                    <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-dim">{r.played_on || '—'}</td>
                    <td className="py-1.5 pr-2 text-pb-faint">
                      {r.round_name || '—'}{r.is_final && <span className="ml-1 font-mono text-[8px] text-[var(--pb-accent)]">F</span>}
                    </td>
                    <td className="py-1.5 pr-2 text-pb-dim">{r.grade_name || r.grade_label || '—'}</td>
                    <td className="py-1.5 pr-2 font-mono text-[10px] text-pb-faint">
                      {r.category === 'bye' ? '—' : r.our_side ? r.our_side[0] : 'N'}
                    </td>
                    <td className="py-1.5 pr-2 text-pb-text">{r.opponent || '—'}</td>
                    <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-text text-right">{scoreLine(r.our_goals, r.our_behinds, r.our_score)}</td>
                    <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-dim text-right">{scoreLine(r.opp_goals, r.opp_behinds, r.opp_score)}</td>
                    <td className="py-1.5 pr-2 text-center"><ResultTag result={r.result} category={r.category} /></td>
                    <td className="py-1.5 pr-2"><RowStatus status={r.status} /></td>
                  </tr>
                  {(r.warnings?.length > 0 || r.status_note) && (
                    <tr>
                      <td colSpan={9} className="pb-1.5 pl-2 pr-2">
                        {r.status_note && <div className="text-[10px] text-pb-faint">{r.status_note}</div>}
                        {(r.warnings || []).map((w, i) => (
                          <div key={i} className={`text-[10px] ${w.kind === 'sheet_error' ? 'text-pb-red/70' : 'text-pb-amber'}`}>
                            {w.kind === 'sheet_error' ? '⚠ ' : '· '}{w.text}
                          </div>
                        ))}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {resolving && rows.length === 0 && <tr><td colSpan={9} className="py-8 text-center"><LoadingSpinner message="Reading the sheet…" /></td></tr>}
              {!resolving && shown.length === 0 && <tr><td colSpan={9} className="py-4 text-center text-pb-dim">Nothing in this view.</td></tr>}
            </tbody>
          </table>
        </div>
        {resolved?.rows_truncated > 0 && (
          <p className="font-mono text-[10px] text-pb-faintest mt-2">
            Listing the first {num(rows.length)} rows. The counts above, and the import itself,
            cover all {num(t.rows || 0)}.
          </p>
        )}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={onBack} className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text">← BACK</button>
        {t.sheet_errors > 0 && (
          <span className="font-mono text-[10px] text-pb-amber">
            {num(t.sheet_errors)} row(s) don't add up — importing keeps them exactly as the sheet has them.
          </span>
        )}
        <button onClick={onCommit} disabled={committing || !(t.importable > 0)}
          className="ml-auto px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
          {committing ? 'IMPORTING…' : t.sheet_errors > 0
            ? `IMPORT ${num(t.importable || 0)}, KEEP AS WRITTEN`
            : `IMPORT ${num(t.importable || 0)} RESULT${t.importable === 1 ? '' : 'S'}`}
        </button>
      </div>
    </>
  )
}

function PastImports({ history, expanded, games, loadingGames, onToggle, onUndo }) {
  if (!history.length) return null
  return (
    <div className="pb-card p-5">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">PAST RESULT IMPORTS</div>
      <table className="w-full text-[12px]">
        <tbody>
          {history.map(b => (
            <Fragment key={b.id}>
              <tr className="pb-hairline-t">
                <td className="py-2 pr-2 text-pb-text">
                  {!b.undone_at && (
                    <button onClick={() => onToggle(b)} className="text-pb-faint hover:text-pb-text mr-1.5 font-mono text-[10px]" title="Show the games in this import">
                      {expanded === b.id ? '▾' : '▸'}
                    </button>
                  )}
                  {b.filename || '(unnamed)'}
                </td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-dim">{num(b.row_count)} rows</td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-faintest">{(b.committed_at || b.created_at || '').slice(0, 10)}</td>
                <td className="py-2 pr-2 text-right">
                  {b.undone_at
                    ? <span className="font-mono text-[9px] text-pb-faint">UNDONE</span>
                    : <button onClick={() => onUndo(b)} className="font-mono text-[9px] tracking-wide2 text-pb-red/70 hover:text-pb-red border border-pb-red/30 rounded px-2 py-0.5">UNDO</button>}
                </td>
              </tr>
              {expanded === b.id && (
                <tr>
                  <td colSpan={4} className="pb-2 pl-6 pr-2">
                    {loadingGames && !games[b.id] ? (
                      <div className="font-mono text-[10px] text-pb-faint py-1">loading games…</div>
                    ) : (
                      <div className="rounded border pb-hairline divide-y pb-hairline-t max-h-72 overflow-y-auto">
                        {(games[b.id] || []).map(g => (
                          <div key={g.id} className="flex items-center justify-between gap-3 px-2 py-1.5">
                            <span className="text-pb-dim truncate">
                              <span className="font-mono text-[10px] text-pb-faintest mr-2">{g.played_at || ''}</span>
                              {g.is_bye ? `Bye — ${g.grade_name}` : `${g.home_team} v ${g.away_team}`}
                              <span className="text-pb-faintest"> · {g.grade_name}</span>
                            </span>
                            <span className="font-mono text-[10px] text-pb-faintest shrink-0">
                              {g.is_bye ? 'BYE' : `${g.home_score ?? 0}–${g.away_score ?? 0} · ${g.result || '—'}`}
                              {g.is_forfeit ? ' · forfeit' : ''}
                            </span>
                          </div>
                        ))}
                        {(games[b.id] || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest px-2 py-1.5">No games.</div>}
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

export default function AflAdminResultsImport() {
  const toast = useToast()

  const [step, setStep] = useState('upload')
  const fileRef = useRef(null)
  const [parsing, setParsing] = useState(false)
  const [filename, setFilename] = useState(null)
  const [headers, setHeaders] = useState([])
  const [rows, setRows] = useState([])
  const [mapping, setMapping] = useState({})

  const [seasonOverrides, setSeasonOverrides] = useState({})
  const [gradeOverrides, setGradeOverrides] = useState({})
  const [includeByes, setIncludeByes] = useState(false)
  const [includeForfeits, setIncludeForfeits] = useState(true)
  const [resolved, setResolved] = useState(null)
  const [resolving, setResolving] = useState(false)

  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(null)

  const [allSeasons, setAllSeasons] = useState([])
  const [clubSlug, setClubSlug] = useState(null)
  const [history, setHistory] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [batchGames, setBatchGames] = useState({})
  const [loadingGames, setLoadingGames] = useState(false)

  const loadHistory = () => { aflApi.resultImportsList().then(setHistory).catch(() => {}) }
  const loadSeasons = () => {
    // Same club-seasons endpoint Import Stats uses — one list, one create
    // path, no second copy to keep in step.
    aflApi.importsSeasons().then(ss => setAllSeasons((ss || []).map(s => ({
      id: s.id, name: (s.year && !String(s.name).includes(String(s.year))) ? `${s.name} (${s.year})` : s.name,
    })))).catch(() => {})
  }
  useEffect(() => {
    loadSeasons()
    loadHistory()
    aflApi.getAdminSettings().then(s => setClubSlug(s?.slug || null)).catch(() => {})
  }, [])

  // Live-reconcile whenever the mapping, an override or an include toggle
  // changes — the review stays current as you work rather than needing a
  // "recalculate" press.
  useEffect(() => {
    if (!headers.length || !mapping.played_on?.column) return
    let cancelled = false
    setResolving(true)
    const body = {
      rows, mapping,
      season_overrides: seasonOverrides, grade_overrides: gradeOverrides,
      include_byes: includeByes, include_forfeits: includeForfeits,
    }
    const t = setTimeout(() => {
      aflApi.resultImportsResolve(body)
        .then(r => { if (!cancelled) setResolved(r) })
        .catch(e => { if (!cancelled) toast.error(e.message) })
        .finally(() => { if (!cancelled) setResolving(false) })
    }, 250)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, JSON.stringify(mapping), JSON.stringify(seasonOverrides), JSON.stringify(gradeOverrides),
      includeByes, includeForfeits])

  // A results register that goes back decades has no season row to match for
  // most of its life. Rather than block, an unmatched label defaults to
  // "unassigned" — and because a game has to hang off a season, the review
  // step then reports those rows as blocked with the fix named ("create one
  // on the Seasons step"), which the bulk-create button does in one press.
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

  async function onFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setParsing(true)
    setHeaders([]); setRows([]); setMapping({}); setResolved(null); setCommitted(null)
    setSeasonOverrides({}); setGradeOverrides({})
    try {
      const res = await aflApi.resultImportsPreview(f)
      setHeaders(res.headers); setRows(res.rows); setMapping(res.mapping); setFilename(f.name)
      setStep('columns')
      toast.success(`Read ${res.row_count} row${res.row_count === 1 ? '' : 's'}`)
    } catch (err) { toast.error(err.message) } finally {
      setParsing(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const mappedColumn = field => mapping[field]?.column || ''
  const setMap = (field, column) => {
    setMapping(m => column ? { ...m, [field]: { column, confidence: 1 } } : (() => { const n = { ...m }; delete n[field]; return n })())
  }
  const setSOverride = (label, val) => setSeasonOverrides(o => { const n = { ...o }; if (!val) delete n[label]; else n[label] = val; return n })
  const setGOverride = (label, val) => setGradeOverrides(o => { const n = { ...o }; if (!val) delete n[label]; else n[label] = val; return n })

  async function createSeason(data) {
    const s = await aflApi.importsCreateSeason(data)
    setAllSeasons(prev => [...prev, { id: s.id, name: s.year && !String(s.name).includes(String(s.year)) ? `${s.name} (${s.year})` : s.name }])
    return s
  }

  const [bulkCreatingSeasons, setBulkCreatingSeasons] = useState(false)
  async function bulkCreateSeasons() {
    const targets = (resolved?.seasons || []).filter(s => s.status === 'none' || s.status === 'unassigned')
    if (!targets.length) return
    setBulkCreatingSeasons(true)
    let created = 0, failed = 0
    // Sequential, not parallel — two labels that resolve to the same season
    // name would otherwise race each other into a duplicate-name 409.
    for (const s of targets) {
      try {
        const season = await createSeason(parseSeasonGuess(s.raw_label))
        setSOverride(s.raw_label, season.id)
        created++
      } catch (e) { failed++ }
    }
    setBulkCreatingSeasons(false)
    toast[failed ? 'error' : 'success'](
      `Created ${created} season${created === 1 ? '' : 's'}`
      + (failed ? ` — ${failed} couldn't be created (that name already exists; pick it from the list instead)` : '')
    )
  }

  const mapReady = REQUIRED_FIELDS.size === 0 || [...REQUIRED_FIELDS].every(f => mappedColumn(f))

  async function commit() {
    setCommitting(true)
    try {
      const res = await aflApi.resultImportsCommit({
        rows, mapping, filename,
        season_overrides: seasonOverrides, grade_overrides: gradeOverrides,
        include_byes: includeByes, include_forfeits: includeForfeits,
      })
      setCommitted(res)
      loadHistory()
      toast.success(`Imported ${res.games_created + res.games_updated} result(s)`)
    } catch (err) { toast.error(err.message) } finally { setCommitting(false) }
  }

  async function toggleBatch(b) {
    if (expanded === b.id) { setExpanded(null); return }
    setExpanded(b.id)
    if (!batchGames[b.id]) {
      setLoadingGames(true)
      try {
        const r = await aflApi.resultImportsBatchGames(b.id)
        setBatchGames(g => ({ ...g, [b.id]: r }))
      } catch (err) { toast.error(err.message) } finally { setLoadingGames(false) }
    }
  }
  async function undo(b) {
    if (!window.confirm(`Undo this import (${b.filename})? Every game it added will be removed. Games synced from PlayHQ are never touched.`)) return
    try {
      const r = await aflApi.resultImportsUndo(b.id)
      toast.success(`Removed ${r.games_removed} imported game(s)`)
      setBatchGames(g => { const n = { ...g }; delete n[b.id]; return n })
      loadHistory()
    } catch (err) { toast.error(err.message) }
  }

  function reset() {
    setStep('upload'); setFilename(null); setHeaders([]); setRows([]); setMapping({})
    setSeasonOverrides({}); setGradeOverrides({}); setResolved(null); setCommitted(null)
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Import Results</SectionTitle>
        {step !== 'upload' && !committed && (
          <button onClick={reset} className="text-xs text-pb-dim hover:text-pb-text underline">Start over</button>
        )}
      </div>
      <p className="text-sm text-pb-dim max-w-3xl -mt-4">
        Bring in your club's own results register — one row per match, going back as far as your records
        do. Upload it, match the columns and the season and team names, then review what we read before
        anything is saved. Imported results sit alongside your synced games on the results page and in
        the club record. A game PlayHQ has already synced is never overwritten, and the whole upload can
        be undone in one click.
      </p>

      {/* Stepper */}
      <div className="flex items-center gap-1 flex-wrap">
        {STEPS.map((s, i) => {
          const active = s === step
          const done = STEPS.indexOf(step) > i
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
        {resolving && <span className="font-mono text-[10px] text-pb-faint ml-2">reading…</span>}
      </div>

      {/* ── Step: Upload ── */}
      {step === 'upload' && (
        <div className="pb-card p-5">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">CSV OR EXCEL FILE</label>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm" onChange={onFile} disabled={parsing}
            className="block text-pb-dim text-sm file:bg-pb-surface2 file:border file:pb-hairline file:rounded file:px-3 file:py-1.5 file:mr-3 file:font-mono file:text-[10px] file:text-pb-text file:cursor-pointer" />
          <p className="font-mono text-[10px] text-pb-faintest mt-3">
            One row per match. Headers can be anything — we map them in the next step.{' '}
            <a href={aflApi.resultImportsTemplateUrl()} className="text-[var(--pb-accent)] hover:underline">Download a template</a>.
          </p>
        </div>
      )}
      {parsing && <LoadingSpinner message="Reading file…" />}

      {/* ── Step: Columns ── */}
      {step === 'columns' && headers.length > 0 && (
        <>
          <div className="pb-card p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
              <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">MATCH YOUR COLUMNS TO THE RIGHT FIELDS</div>
              <span className="font-mono text-[10px] text-pb-faint">{num(rows.length)} row(s) · {headers.length} columns · {filename}</span>
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

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">THE MATCH</div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 mb-5">
              {MATCH_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence}
                  matchedOn={mapping[f]?.matched_on} onMap={setMap} />
              ))}
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">SCORES</div>
            <p className="text-[11px] text-pb-faintest mb-2 max-w-2xl">
              Goals and behinds are enough — we work the total out at six points a goal where your sheet
              doesn't carry one, and say so if the two disagree.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 mb-5">
              {SCORE_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence}
                  matchedOn={mapping[f]?.matched_on} onMap={setMap} />
              ))}
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">RESULT</div>
            <p className="text-[11px] text-pb-faintest mb-2 max-w-2xl">
              Whatever your sheet writes in its result column — "Won", "Loss", "Drawn Game", "Bye",
              "Cancel", "Won on Forfeit". Where it's blank we work the result out from the scores and
              flag the row so you can check it.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {RESULT_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence}
                  matchedOn={mapping[f]?.matched_on} onMap={setMap} />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!mapReady && <span className="font-mono text-[10px] text-pb-red/70">Map the match date column to continue.</span>}
            <button onClick={() => setStep('seasons')} disabled={!mapReady}
              className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
              NEXT: SEASONS →
            </button>
          </div>
        </>
      )}

      {/* ── Step: Seasons ── */}
      {step === 'seasons' && (
        <MatchTable
          title="Confirm the seasons" kind="season"
          subtitle="Every result needs a season to sit in. Match each label from your sheet to one of your club's seasons, or create the ones that predate anything synced — the button below does the whole unmatched list in one go."
          rows={resolved?.seasons || []}
          allOptions={allSeasons}
          loading={resolving}
          valueFor={r => seasonOverrides[r.raw_label] ?? (r.season_id || (r.is_prior ? '__unassigned__' : ''))}
          onChange={(r, v) => setSOverride(r.raw_label, v)}
          onCreateSeason={createSeason}
          onBulkCreateSeasons={bulkCreateSeasons}
          bulkCreating={bulkCreatingSeasons}
          nextLabel="NEXT: TEAMS →"
          onNext={() => setStep('teams')}
          onBack={() => setStep('columns')}
        />
      )}

      {/* ── Step: Teams ── */}
      {step === 'teams' && (
        <MatchTable
          title="Confirm the teams" kind="grade" labelHeading="TEAM LABEL IN SHEET"
          subtitle="Your sheet's team names (Seniors, Reserves, Under 17s) become the grade each result belongs to. Match one to a grade you already hold and the results join it; leave it as-is and the label becomes its own grade for that season, which you can merge later from Merge Grades."
          rows={resolved?.grades || []}
          allOptions={(resolved?.grade_options || []).map(name => ({ id: name, name }))}
          loading={resolving}
          valueFor={r => gradeOverrides[r.raw_label] ?? (r.grade_name || '__own__')}
          onChange={(r, v) => setGOverride(r.raw_label, v)}
          nextLabel="NEXT: REVIEW →"
          onNext={() => setStep('confirm')}
          onBack={() => setStep('seasons')}
        />
      )}

      {/* ── Step: Review ── */}
      {step === 'confirm' && (
        <ReviewStep
          resolved={resolved} resolving={resolving} committing={committing} committed={committed}
          clubSlug={clubSlug}
          includeByes={includeByes} includeForfeits={includeForfeits}
          onToggleByes={setIncludeByes} onToggleForfeits={setIncludeForfeits}
          onCommit={commit} onBack={() => setStep('teams')} onReset={reset}
        />
      )}

      {step === 'upload' && (
        <PastImports history={history} expanded={expanded} games={batchGames}
          loadingGames={loadingGames} onToggle={toggleBatch} onUndo={undo} />
      )}
    </div>
  )
}
