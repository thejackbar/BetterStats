import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'
import { num, cell, FieldRow, PlayerMatch, SearchSelect, StatusBadge } from './importMatching'

// Import Awards — a club's honour board from a spreadsheet. The third of the
// BetterFootball import tools, on the same wizard pieces as Import Stats and
// Import Results (./importMatching): upload, map the columns, match the
// people, match the awards, review, import.
//
// Two things this step does that the other two don't: an award the club's
// Award Types catalogue doesn't carry yet is ADDED (so the honour board and
// the Awards dropdown end up agreeing), and every row is checked against
// what's already recorded, so re-uploading a corrected sheet adds the new
// rows and leaves the rest alone.

const FIELD_LABEL = {
  player_name: 'Player name', player_ref: "Your sheet's player ID",
  award_name: 'Award / trophy', season_label: 'Season / year', season_end: 'Season (end)',
  category: 'Category', subcategory: 'Subcategory / team', detail: 'Detail',
}
const WHO_FIELDS = ['player_name', 'player_ref']
const WHAT_FIELDS = ['award_name', 'season_label', 'season_end', 'category', 'subcategory', 'detail']
const REQUIRED_FIELDS = new Set(['player_name', 'award_name'])

const STEP_LABELS = { upload: 'Upload', columns: 'Columns', players: 'Players', awards: 'Awards', confirm: 'Review' }
const STEPS = ['upload', 'columns', 'players', 'awards', 'confirm']

const ROW_STATUS = {
  ready: ['READY', 'text-green-300 border-green-300/30'],
  skipped: ['SKIPPED', 'text-pb-faint border-pb-faint/30'],
  blocked: ['BLOCKED', 'text-pb-red/70 border-pb-red/30'],
  duplicate: ['DUPLICATE', 'text-pb-amber border-pb-amber/30'],
  exists: ['ALREADY THERE', 'text-pb-faint border-pb-faint/30'],
}

function RowStatus({ status }) {
  const [label, tone] = ROW_STATUS[status] || [String(status || '—').toUpperCase(), 'text-pb-faint border-pb-faint/30']
  return <span className={`font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-0.5 ${tone}`}>{label}</span>
}

function WarningBox({ kind, children }) {
  const isError = kind === 'sheet_error'
  return (
    <div className={`pb-card p-3 mb-3 border-l-2 ${isError ? 'border-pb-red/50' : 'border-pb-amber/50'}`}>
      <span className={`text-[12px] ${isError ? 'text-pb-red/80' : 'text-pb-amber'}`}>{children}</span>
    </div>
  )
}

// ── Awards step ─────────────────────────────────────────────────────────────
// Each distinct trophy in the sheet, and where it lands in the club's award
// catalogue. An award already in the catalogue keeps ITS filing — the Award
// Types screen owns that, and an upload retyping a category the club set up
// by hand would be the wrong way round. Only an award being created here has
// its category and subcategory editable, and they start from a guess made
// off the award's own name.
const PAGE = 60

function AwardMatch({ rows, options, categories, overrides, meta, setOverride, setMeta,
                     loading, nextLabel, onNext, onBack }) {
  const [onlyReview, setOnlyReview] = useState(false)
  const [page, setPage] = useState(0)

  const idName = useMemo(() => {
    const m = new Map()
    options.forEach(o => m.set(o.id, o.name))
    rows.forEach(r => (r.candidates || []).forEach(c => m.set(c.definition_id, c.name)))
    return m
  }, [options, rows])

  const counts = useMemo(() => ({
    matched: rows.filter(r => r.status === 'matched' || r.status === 'manual').length,
    creating: rows.filter(r => r.status === 'new' || r.status === 'fuzzy').length,
    skipped: rows.filter(r => r.status === 'skip').length,
  }), [rows])

  const shown = useMemo(
    () => onlyReview ? rows.filter(r => r.status !== 'matched' && r.status !== 'manual') : rows,
    [rows, onlyReview])
  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE))
  const safe = Math.min(page, pageCount - 1)
  const pageRows = shown.slice(safe * PAGE, safe * PAGE + PAGE)
  useEffect(() => { setPage(0) }, [onlyReview, rows.length])

  const valueFor = r => overrides[r.key] ?? (r.definition_id || '__new__')

  return (
    <>
      <div className="pb-card p-5 mb-4">
        <h2 className="font-display font-semibold text-lg text-pb-text mb-1">Match the awards</h2>
        <p className="text-pb-faint text-[12px] mb-4 leading-relaxed max-w-3xl">
          Every trophy your sheet names, and where it goes. Ones your club already has an award type for
          are matched and keep their existing category. Anything else is added to your Award Types as part
          of this import. Check the category it's filed under, or point it at an award you already have.
        </p>

        {loading && rows.length === 0 ? (
          <div className="py-10 text-center"><LoadingSpinner message="Matching awards…" /></div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <span className="font-mono text-[10px] text-green-300">{counts.matched} already in your Award Types</span>
              <span className="font-mono text-[10px] text-[var(--pb-accent)]">{counts.creating} will be added</span>
              {counts.skipped > 0 && <span className="font-mono text-[10px] text-pb-faint">{counts.skipped} not importing</span>}
              <button onClick={() => setOnlyReview(v => !v)}
                className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-2.5 py-1 text-pb-faint hover:text-pb-text">
                {onlyReview ? `SHOW ALL ${rows.length}` : 'NEW ONES ONLY'}
              </button>
              {pageCount > 1 && (
                <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-pb-faint">
                  <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={safe === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
                  {safe + 1} / {pageCount}
                  <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={safe >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
                </span>
              )}
            </div>

            <div className="overflow-x-auto overflow-y-visible">
              <table className="w-full text-[12px] min-w-[760px]">
                <thead>
                  <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                    <th className="py-2 pr-2">AWARD IN YOUR SHEET</th>
                    <th className="py-2 pr-2 w-16 text-right">WON</th>
                    <th className="py-2 pr-2 w-28">STATUS</th>
                    <th className="py-2 pr-2">AWARD TYPE</th>
                    <th className="py-2 pr-2">FILED UNDER</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map(r => {
                    const creating = r.status === 'new' || r.status === 'fuzzy'
                    const candidates = (r.candidates || []).map(c => ({
                      id: c.definition_id, name: c.name, confidence: c.confidence,
                    }))
                    const m = meta[r.key] || {}
                    return (
                      <tr key={r.key} className="pb-hairline-t align-middle">
                        <td className="py-2 pr-2 text-pb-text">{r.name}</td>
                        <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim text-right">{num(r.rows)}</td>
                        <td className="py-2 pr-2"><StatusBadge status={creating ? 'new_award' : r.status} /></td>
                        <td className="py-2 pr-2">
                          <SearchSelect value={valueFor(r)} idName={idName} candidates={candidates}
                            options={options} onChange={v => setOverride(r.key, v)} kind="award" />
                        </td>
                        <td className="py-2 pr-2">
                          {creating ? (
                            <div className="flex items-center gap-1.5">
                              <select className={`${cell} w-32`} value={m.category ?? r.category ?? 'Club Award'}
                                onChange={e => setMeta(r.key, { ...m, category: e.target.value })}>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                              </select>
                              <input className={`${cell} w-24`} placeholder="Season"
                                value={m.subcategory ?? r.subcategory ?? ''}
                                onChange={e => setMeta(r.key, { ...m, subcategory: e.target.value })} />
                            </div>
                          ) : r.status === 'skip' ? (
                            <span className="text-[11px] text-pb-faintest">—</span>
                          ) : (
                            <span className="text-[11px] text-pb-faint">
                              {r.category}{r.subcategory ? ` › ${r.subcategory}` : ''}
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                  {!loading && shown.length === 0 && (
                    <tr><td colSpan={5} className="py-4 text-center text-green-300 text-[12px]">Every award in your sheet is already an award type.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              An award type you already have keeps the category it's filed under on the{' '}
              <Link to="/admin/award-definitions" className="text-[var(--pb-accent)] hover:underline">Award Types</Link> screen.
            </p>
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

// ── Review + commit ─────────────────────────────────────────────────────────
const ROW_PAGE = 100
const ROW_FILTERS = [
  ['importable', 'To import'],
  ['exists', 'Already recorded'],
  ['blocked', 'Blocked'],
  ['skipped', 'Skipped'],
  ['all', 'Everything'],
]

function ReviewStep({ resolved, resolving, committing, committed, onCommit, onBack, onReset }) {
  const [filter, setFilter] = useState('importable')
  const [page, setPage] = useState(0)
  useEffect(() => { setPage(0) }, [filter, resolved?.totals?.rows])

  const rows = resolved?.rows || []
  const shown = useMemo(() => {
    if (filter === 'all') return rows
    if (filter === 'importable') return rows.filter(r => r.status === 'ready')
    if (filter === 'exists') return rows.filter(r => r.status === 'exists' || r.status === 'duplicate')
    if (filter === 'blocked') return rows.filter(r => r.status === 'blocked')
    return rows.filter(r => r.status === 'skipped')
  }, [rows, filter])

  if (committed) {
    return (
      <div className="pb-card p-6">
        <div className="font-mono text-[10px] tracking-wide2 text-green-300 mb-2">IMPORT COMPLETE</div>
        <h2 className="font-display font-bold text-xl text-pb-text mb-3">
          {num(committed.awards_created)} award{committed.awards_created === 1 ? '' : 's'} on the honour board
        </h2>
        <p className="text-pb-faint text-sm mb-4 leading-relaxed max-w-2xl">
          {committed.definitions_created
            ? `${num(committed.definitions_created)} new award type${committed.definitions_created === 1 ? '' : 's'} added to your catalogue. `
            : ''}
          {committed.players_created
            ? `${num(committed.players_created)} player${committed.players_created === 1 ? '' : 's'} created. `
            : ''}
          {committed.already_recorded ? `${num(committed.already_recorded)} were already recorded and were left alone. ` : ''}
          {committed.rows_skipped ? `${num(committed.rows_skipped)} row(s) skipped.` : ''}
        </p>
        <div className="flex gap-3 flex-wrap">
          <button onClick={onReset} className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)]">IMPORT ANOTHER</button>
          <Link to="/admin/awards" className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text">VIEW AWARDS</Link>
          <Link to="/admin/award-definitions" className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text">VIEW AWARD TYPES</Link>
        </div>
      </div>
    )
  }

  const t = resolved?.totals || {}
  const pageCount = Math.max(1, Math.ceil(shown.length / ROW_PAGE))
  const safe = Math.min(page, pageCount - 1)
  const pageRows = shown.slice(safe * ROW_PAGE, safe * ROW_PAGE + ROW_PAGE)

  return (
    <>
      {(resolved?.warnings || []).map((w, i) => <WarningBox key={i} kind={w.kind}>{w.text}</WarningBox>)}

      <div className="pb-card p-5 mb-4">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="font-display font-semibold text-lg text-pb-text">Review the honour board</h2>
          <span className="font-mono text-[10px] text-pb-faint">
            {num(t.rows || 0)} row(s) read{resolving ? ' · reading…' : ''}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          {[
            ['To import', t.importable, 'text-green-300'],
            ['Already recorded', t.exists, 'text-pb-faint'],
            ['No award named', t.skipped, 'text-pb-faint'],
            ['Blocked', t.blocked, 'text-pb-red/70'],
          ].map(([label, value, tone]) => (
            <div key={label} className="rounded border pb-hairline px-3 py-2">
              <div className="font-mono text-[9px] tracking-wide2 text-pb-faint">{label.toUpperCase()}</div>
              <div className={`font-mono text-lg font-semibold ${tone}`}>{num(value || 0)}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mb-4 pb-3 pb-hairline-b font-mono text-[10px] text-pb-faint">
          <span>{num(t.players_matched || 0)} players matched</span>
          <span>{num(t.players_new || 0)} to be created</span>
          <span>{num(t.awards_matched || 0)} award types matched</span>
          <span className="text-[var(--pb-accent)]">{num(t.awards_new || 0)} award types to be added</span>
        </div>

        {(resolved?.award_summary || []).length > 0 && (
          <div className="mb-5">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">WHAT'S COMING IN</div>
            <div className="overflow-x-auto max-h-72 overflow-y-auto">
              <table className="w-full text-[12px] min-w-[420px]">
                <thead className="sticky top-0 bg-pb-surface">
                  <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                    <th className="py-1.5 pr-2">AWARD</th>
                    <th className="py-1.5 pr-2">CATEGORY</th>
                    <th className="py-1.5 pr-2 text-right">TIMES WON</th>
                    <th className="py-1.5 pr-2">YEARS</th>
                  </tr>
                </thead>
                <tbody>
                  {resolved.award_summary.map(s => (
                    <tr key={s.achievement} className="pb-hairline-t">
                      <td className="py-1.5 pr-2 text-pb-text">
                        {s.achievement}
                        {s.creates && <span className="ml-1.5 font-mono text-[9px] text-[var(--pb-accent)]">NEW</span>}
                      </td>
                      <td className="py-1.5 pr-2 text-[11px] text-pb-faint">{s.category}</td>
                      <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-text text-right font-semibold">{num(s.count)}</td>
                      <td className="py-1.5 pr-2 font-mono text-[10px] text-pb-faint">
                        {s.first ? (s.first === s.last ? s.first : `${s.first}–${s.last}`) : '—'}
                      </td>
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
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={safe === 0} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">←</button>
              {safe + 1} / {pageCount}
              <button onClick={() => setPage(p => Math.min(pageCount - 1, p + 1))} disabled={safe >= pageCount - 1} className="border pb-hairline rounded px-2 py-0.5 disabled:opacity-40">→</button>
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[720px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2 w-20">SEASON</th>
                <th className="py-2 pr-2">PLAYER</th>
                <th className="py-2 pr-2">AWARD</th>
                <th className="py-2 pr-2">FILED UNDER</th>
                <th className="py-2 pr-2 w-32">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map(r => (
                <Fragment key={r.index}>
                  <tr className="pb-hairline-t align-middle">
                    <td className="py-1.5 pr-2 font-mono text-[11px] text-pb-dim">{r.season || '—'}</td>
                    <td className="py-1.5 pr-2 text-pb-text">
                      {r.player_name || '—'}
                      {r.creates_player && <span className="ml-1.5 font-mono text-[9px] text-[var(--pb-accent)]">NEW</span>}
                    </td>
                    <td className="py-1.5 pr-2 text-pb-dim">{r.achievement || '—'}</td>
                    <td className="py-1.5 pr-2 text-[11px] text-pb-faint">
                      {r.category || '—'}{r.subcategory ? ` › ${r.subcategory}` : ''}
                    </td>
                    <td className="py-1.5 pr-2"><RowStatus status={r.status} /></td>
                  </tr>
                  {r.status_note && filter !== 'skipped' && (
                    <tr><td colSpan={5} className="pb-1.5 pl-2 pr-2 text-[10px] text-pb-faint">{r.status_note}</td></tr>
                  )}
                </Fragment>
              ))}
              {resolving && rows.length === 0 && <tr><td colSpan={5} className="py-8 text-center"><LoadingSpinner message="Reading the sheet…" /></td></tr>}
              {!resolving && shown.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-pb-dim">Nothing in this view.</td></tr>}
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
        {t.blocked > 0 && (
          <span className="font-mono text-[10px] text-pb-red/70">
            {num(t.blocked)} row(s) still need a player match, they won't import.
          </span>
        )}
        <button onClick={onCommit} disabled={committing || !(t.importable > 0)}
          className="ml-auto px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-black bg-[var(--pb-accent)] disabled:opacity-50">
          {committing ? 'IMPORTING…' : `IMPORT ${num(t.importable || 0)} AWARD${t.importable === 1 ? '' : 'S'}`}
        </button>
      </div>
    </>
  )
}

function PastImports({ history, expanded, awards, loadingAwards, onToggle, onUndo }) {
  if (!history.length) return null
  return (
    <div className="pb-card p-5">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">PAST AWARD IMPORTS</div>
      <table className="w-full text-[12px]">
        <tbody>
          {history.map(b => (
            <Fragment key={b.id}>
              <tr className="pb-hairline-t">
                <td className="py-2 pr-2 text-pb-text">
                  {!b.undone_at && (
                    <button onClick={() => onToggle(b)} className="text-pb-faint hover:text-pb-text mr-1.5 font-mono text-[10px]" title="Show the awards in this import">
                      {expanded === b.id ? '▾' : '▸'}
                    </button>
                  )}
                  {b.filename || '(unnamed)'}
                </td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-dim">{num(b.created_count)} awards</td>
                <td className="py-2 pr-2 font-mono text-[10px] text-pb-faintest">{String(b.created_at || '').slice(0, 10)}</td>
                <td className="py-2 pr-2 text-right">
                  {b.undone_at
                    ? <span className="font-mono text-[9px] text-pb-faint">UNDONE</span>
                    : <button onClick={() => onUndo(b)} className="font-mono text-[9px] tracking-wide2 text-pb-red/70 hover:text-pb-red border border-pb-red/30 rounded px-2 py-0.5">UNDO</button>}
                </td>
              </tr>
              {expanded === b.id && (
                <tr>
                  <td colSpan={4} className="pb-2 pl-6 pr-2">
                    {loadingAwards && !awards[b.id] ? (
                      <div className="font-mono text-[10px] text-pb-faint py-1">loading awards…</div>
                    ) : (
                      <div className="rounded border pb-hairline divide-y pb-hairline-t max-h-72 overflow-y-auto">
                        {(awards[b.id] || []).map(a => (
                          <div key={a.id} className="flex items-center justify-between gap-3 px-2 py-1.5">
                            <span className="text-pb-dim truncate">
                              <span className="font-mono text-[10px] text-pb-faintest mr-2">{a.season || '—'}</span>
                              {a.player_name}
                              <span className="text-pb-faintest"> · {a.achievement}</span>
                            </span>
                            <span className="font-mono text-[10px] text-pb-faintest shrink-0">{a.category}</span>
                          </div>
                        ))}
                        {(awards[b.id] || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest px-2 py-1.5">No awards.</div>}
                      </div>
                    )}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      <p className="font-mono text-[10px] text-pb-faintest mt-3">
        Undo removes the awards this upload added. Players and award types it created are left in place, 
        deleting a person, or a catalogue entry the club may already be using, does more harm than leaving
        a row that's easy to remove by hand.
      </p>
    </div>
  )
}

export default function AflAdminAwardsImport() {
  const toast = useToast()

  const [step, setStep] = useState('upload')
  const fileRef = useRef(null)
  const [parsing, setParsing] = useState(false)
  const [filename, setFilename] = useState(null)
  const [headers, setHeaders] = useState([])
  const [rows, setRows] = useState([])
  const [mapping, setMapping] = useState({})

  const [playerOverrides, setPlayerOverrides] = useState({})
  const [awardOverrides, setAwardOverrides] = useState({})
  const [awardMeta, setAwardMeta] = useState({})
  const [resolved, setResolved] = useState(null)
  const [resolving, setResolving] = useState(false)

  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(null)

  const [allPlayers, setAllPlayers] = useState([])
  const [history, setHistory] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [batchAwards, setBatchAwards] = useState({})
  const [loadingAwards, setLoadingAwards] = useState(false)

  const loadHistory = () => { aflApi.awardImportsList().then(setHistory).catch(() => {}) }
  useEffect(() => {
    aflApi.adminListPlayers().then(ps => setAllPlayers((ps || []).map(p => ({
      id: p.id, name: p.display_name || p.name, games: p.games, goals: p.goals,
    })))).catch(() => {})
    loadHistory()
  }, [])

  // Live-reconcile whenever the mapping or an override changes, same as the
  // other two wizards — the review stays current as you work instead of
  // needing a recalculate press.
  useEffect(() => {
    if (!headers.length || !mapping.player_name?.column || !mapping.award_name?.column) return
    let cancelled = false
    setResolving(true)
    const body = {
      rows, mapping,
      player_overrides: playerOverrides, award_overrides: awardOverrides, award_meta: awardMeta,
    }
    const t = setTimeout(() => {
      aflApi.awardImportsResolve(body)
        .then(r => { if (!cancelled) setResolved(r) })
        .catch(e => { if (!cancelled) toast.error(e.message) })
        .finally(() => { if (!cancelled) setResolving(false) })
    }, 250)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headers, JSON.stringify(mapping), JSON.stringify(playerOverrides),
      JSON.stringify(awardOverrides), JSON.stringify(awardMeta)])

  async function onFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setParsing(true)
    setHeaders([]); setRows([]); setMapping({}); setResolved(null); setCommitted(null)
    setPlayerOverrides({}); setAwardOverrides({}); setAwardMeta({})
    try {
      const res = await aflApi.awardImportsPreview(f)
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
  const setPOverride = (key, val) => setPlayerOverrides(o => { const n = { ...o }; if (!val) delete n[key]; else n[key] = val; return n })
  const setAOverride = (key, val) => setAwardOverrides(o => { const n = { ...o }; if (!val) delete n[key]; else n[key] = val; return n })
  const setAMeta = (key, val) => setAwardMeta(m => ({ ...m, [key]: val }))

  const mapReady = [...REQUIRED_FIELDS].every(f => mappedColumn(f))
  const unresolved = resolved?.totals?.players_unresolved || 0

  // One line of context per name on the Players step: what this person is
  // claiming out of the sheet, so a close match can be judged without
  // leaving the page.
  const sheetAwards = useMemo(() => {
    const out = {}
    for (const r of (resolved?.rows || [])) {
      if (!r.player_key || !r.award_raw) continue
      const o = out[r.player_key] || (out[r.player_key] = { awards: 0, first: null, last: null })
      o.awards++
      const y = (r.season || '').trim()
      if (y) {
        o.first = o.first === null ? y : (y < o.first ? y : o.first)
        o.last = o.last === null ? y : (y > o.last ? y : o.last)
      }
    }
    return out
  }, [resolved?.rows])

  function sheetLine(r) {
    const s = sheetAwards[r.key]
    if (!s) return 'no awards in this sheet'
    const years = s.first ? (s.first === s.last ? s.first : `${s.first}–${s.last}`) : null
    return `${s.awards} award${s.awards === 1 ? '' : 's'}${years ? ` · ${years}` : ''}`
  }

  async function commit() {
    setCommitting(true)
    try {
      const res = await aflApi.awardImportsCommit({
        rows, mapping, filename,
        player_overrides: playerOverrides, award_overrides: awardOverrides, award_meta: awardMeta,
      })
      setCommitted(res)
      loadHistory()
      toast.success(`Imported ${res.awards_created} award(s)`)
    } catch (err) { toast.error(err.message) } finally { setCommitting(false) }
  }

  async function toggleBatch(b) {
    if (expanded === b.id) { setExpanded(null); return }
    setExpanded(b.id)
    if (!batchAwards[b.id]) {
      setLoadingAwards(true)
      try {
        const r = await aflApi.awardImportsBatchAwards(b.id)
        setBatchAwards(a => ({ ...a, [b.id]: r }))
      } catch (err) { toast.error(err.message) } finally { setLoadingAwards(false) }
    }
  }
  async function undo(b) {
    if (!window.confirm(`Undo this import (${b.filename})? Every award it added will be removed from the honour board.`)) return
    try {
      const r = await aflApi.awardImportsUndo(b.id)
      toast.success(`Removed ${r.awards_removed} award(s)`)
      setBatchAwards(a => { const n = { ...a }; delete n[b.id]; return n })
      loadHistory()
    } catch (err) { toast.error(err.message) }
  }

  function reset() {
    setStep('upload'); setFilename(null); setHeaders([]); setRows([]); setMapping({})
    setPlayerOverrides({}); setAwardOverrides({}); setAwardMeta({}); setResolved(null); setCommitted(null)
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <SectionTitle>Import Awards</SectionTitle>
        {step !== 'upload' && !committed && (
          <button onClick={reset} className="text-xs text-pb-dim hover:text-pb-text underline">Start over</button>
        )}
      </div>
      <p className="text-sm text-pb-dim max-w-3xl -mt-4">
        Bring in your club's honour board. One row per award won, going back as far as your records do.
        Upload it, match the columns and the names, then review what we read before anything is saved.
        An award your club doesn't have an award type for yet is added as part of the import, a name we
        can't find on your roster becomes a new player, and the whole upload can be undone in one click.
      </p>

      <div className="flex items-center gap-1 flex-wrap">
        {STEPS.map((s, i) => {
          const active = s === step
          const done = STEPS.indexOf(step) > i
          const reachable = headers.length > 0 || s === 'upload'
          return (
            <button key={s} disabled={!reachable} onClick={() => reachable && setStep(s)}
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
            One row per award. Headers can be anything, we map them in the next step. A row that names no
            award is skipped, so a sheet that also lists the seasons someone played is fine as it is.{' '}
            <a href={aflApi.awardImportsTemplateUrl()} className="text-[var(--pb-accent)] hover:underline">Download a template</a>.
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

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">WHO WON IT</div>
            <p className="text-[11px] text-pb-faintest mb-2 max-w-2xl">
              If your sheet carries its own player ID, map it. It's what tells two spellings of one name
              apart from two different people who share one, and a register kept for decades has both.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-5">
              {WHO_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence}
                  matchedOn={mapping[f]?.matched_on} onMap={setMap} />
              ))}
            </div>

            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">THE AWARD</div>
            <p className="text-[11px] text-pb-faintest mb-2 max-w-2xl">
              The trophy name is all we need. Category and subcategory are worked out from it where your
              sheet doesn't say, and you can change any of them on the next step but one.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
              {WHAT_FIELDS.map(f => (
                <FieldRow key={f} field={f} label={FIELD_LABEL[f]} required={REQUIRED_FIELDS.has(f)}
                  value={mappedColumn(f)} headers={headers} conf={mapping[f]?.confidence}
                  matchedOn={mapping[f]?.matched_on} onMap={setMap} />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!mapReady && <span className="font-mono text-[10px] text-pb-red/70">Map the player name and the award column to continue.</span>}
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
          rows={resolved?.players || []} allPlayers={allPlayers} sheetLine={sheetLine}
          overrides={playerOverrides} setOverride={setPOverride} setOverridesBulk={setPlayerOverrides}
          loading={resolving}
          subtitle="Three quick passes: confirm the exact matches, review the close ones, then anything with no match defaults to a brand-new player. A name your sheet uses for two different people is never matched for you, those come up under Review close for you to split."
          nextLabel="NEXT: AWARDS →"
          onNext={() => setStep('awards')}
          onBack={() => setStep('columns')}
        />
      )}

      {/* ── Step: Awards ── */}
      {step === 'awards' && (
        <AwardMatch
          rows={resolved?.awards || []}
          options={(resolved?.award_options || []).map(o => ({ id: o.id, name: o.name }))}
          categories={resolved?.categories || []}
          overrides={awardOverrides} meta={awardMeta}
          setOverride={setAOverride} setMeta={setAMeta}
          loading={resolving}
          nextLabel="NEXT: REVIEW →"
          onNext={() => setStep('confirm')}
          onBack={() => setStep('players')}
        />
      )}

      {/* ── Step: Review ── */}
      {step === 'confirm' && (
        <>
          {unresolved > 0 && (
            <WarningBox kind="sheet_error">
              {unresolved} name(s) still need a match. Their awards won't import until you set them on the
              Players step.
            </WarningBox>
          )}
          <ReviewStep
            resolved={resolved} resolving={resolving} committing={committing} committed={committed}
            onCommit={commit} onBack={() => setStep('awards')} onReset={reset}
          />
        </>
      )}

      {step === 'upload' && (
        <PastImports history={history} expanded={expanded} awards={batchAwards}
          loadingAwards={loadingAwards} onToggle={toggleBatch} onUndo={undo} />
      )}
    </div>
  )
}
