import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import Dropdown from '../../components/Dropdown'
import { formatSeason } from '../../lib/cricketFormat'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const BTN_PRIMARY = 'inline-flex items-center px-4 py-2 bg-pb-accent text-white text-sm font-semibold rounded hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed'
const BTN_SECONDARY = 'inline-flex items-center px-3 py-1.5 border pb-hairline text-pb-text text-xs rounded hover:bg-pb-surface2'
const BTN_DANGER = 'inline-flex items-center px-3 py-1.5 border border-red-400/40 text-red-300 text-xs rounded hover:bg-red-500/10'

const TABS = [
  { key: 'season', label: 'Adjustments', hint: 'Add or correct a player\'s totals. Leave season blank to apply as a career-only adjustment.' },
  { key: 'game', label: 'Manual Games', hint: 'Add full or partial historical scorecards' },
  { key: 'audit', label: 'Audit & Undo', hint: 'Reverse any previous change' },
]

function ConfirmModal({ open, title, body, confirmLabel = 'Save changes', danger = false, onConfirm, onCancel }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={onCancel}>
      <div className="bg-pb-surface border pb-hairline rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-pb-text mb-2">{title}</h3>
        <div className="text-sm text-pb-faint mb-4 whitespace-pre-line">{body}</div>
        <div className="flex justify-end gap-2">
          <button className={BTN_SECONDARY} onClick={onCancel}>Cancel</button>
          <button
            className={danger ? BTN_DANGER : BTN_PRIMARY}
            onClick={onConfirm}
          >{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

function ComboInput({ value, onChange, suggestions = [], placeholder, allowNew = true }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const q = (value || '').toLowerCase().trim()
  const filtered = q.length === 0
    ? suggestions.slice(0, 12)
    : suggestions.filter(s => s.toLowerCase().includes(q)).slice(0, 12)
  const exactMatch = suggestions.some(s => s.toLowerCase() === q)
  const isNew = value && value.trim().length > 0 && !exactMatch

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={value || ''}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={INPUT_CLS}
      />
      <Dropdown
        anchorRef={ref}
        open={open && filtered.length > 0}
        onClose={() => setOpen(false)}
        maxHeight={224}
        className="bg-pb-surface border pb-hairline rounded shadow-lg"
      >
        {filtered.map(s => (
          <button
            key={s}
            type="button"
            onMouseDown={() => { onChange(s); setOpen(false) }}
            className="w-full text-left px-3 py-1.5 text-sm text-pb-text hover:bg-pb-surface2"
          >{s}</button>
        ))}
      </Dropdown>
      {isNew && allowNew && (
        <p className="text-[10px] text-amber-300 mt-0.5">
          ⚠ New value — not in existing data. Double-check the spelling before saving.
        </p>
      )}
    </div>
  )
}

function PlayerPicker({ players, value, onChange, placeholder = 'Search player…' }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const selected = players.find(p => p.id === value)
  const displayValue = open ? query : (selected ? selected.display_name : '')

  const filtered = query.length >= 2
    ? players.filter(p => p.display_name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={displayValue}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => { setQuery(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={INPUT_CLS}
      />
      <Dropdown
        anchorRef={ref}
        open={open && filtered.length > 0}
        onClose={() => setOpen(false)}
        maxHeight={256}
        className="bg-pb-surface border pb-hairline rounded shadow-lg"
      >
        {filtered.map(p => (
          <button
            key={p.id}
            type="button"
            onMouseDown={() => { onChange(p.id); setOpen(false); setQuery('') }}
            className="w-full text-left px-3 py-2 text-sm text-pb-text hover:bg-pb-surface2"
          >{p.display_name}</button>
        ))}
      </Dropdown>
    </div>
  )
}

const EMPTY_AGG = {
  games_played: 0,
  batting_innings: 0, batting_runs: 0, batting_not_outs: 0, batting_balls: 0,
  batting_fours: 0, batting_sixes: 0, batting_fifties: 0, batting_hundreds: 0,
  batting_ducks: 0, batting_high_score: '', batting_high_score_not_out: false,
  bowling_innings: 0, bowling_overs: 0, bowling_balls: 0, bowling_maidens: 0,
  bowling_runs: 0, bowling_wickets: 0, bowling_five_wicket_innings: 0,
  bowling_best_wickets: '', bowling_best_figures: '',
  fielding_catches: 0, fielding_catches_wk: 0, fielding_run_outs: 0, fielding_stumpings: 0,
  notes: '',
}

const EMPTY_SEASON_FORM = {
  player_id: '', season_id: '', grade_id: '',
  ...EMPTY_AGG,
  bowling_wides: 0, bowling_no_balls: 0,
}
const EMPTY_CAREER_FORM = { player_id: '', ...EMPTY_AGG }

function NumberField({ label, value, onChange, step = 1, min = 0, allowDecimal = false }) {
  return (
    <div>
      <label className={LABEL_CLS}>{label}</label>
      <input
        type="number"
        step={allowDecimal ? '0.1' : step}
        min={min}
        value={value === '' || value === null || value === undefined ? '' : value}
        onChange={e => {
          const v = e.target.value
          if (v === '') return onChange('')
          onChange(allowDecimal ? parseFloat(v) : parseInt(v, 10))
        }}
        className={INPUT_CLS + ' no-spinner'}
      />
    </div>
  )
}

// A season/grade dropdown with a "+ New" inline form, for historical data with
// no CA equivalent (e.g. a pre-2000 season) — the sync never creates these, so
// without this an admin has no way to enter a match from an era that isn't
// already in the season list.
function SeasonSelect({ seasons, value, onChange, onCreated, emptyLabel = '— Choose a season —' }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [year, setYear] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async () => {
    const n = name.trim()
    if (!n) { setErr('Name is required'); return }
    setBusy(true); setErr(null)
    try {
      const s = await api.adminCreateManualSeason({ name: n, year: year ? parseInt(year, 10) : null })
      onCreated(s)
      onChange(s.id)
      setAdding(false); setName(''); setYear('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (adding) {
    return (
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <input
            autoFocus placeholder="e.g. Summer 1962/63" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={SMALL_INPUT} style={{ maxWidth: 170 }}
          />
          <input
            placeholder="Year" value={year}
            onChange={e => setYear(e.target.value.replace(/\D/g, '').slice(0, 4))}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={SMALL_INPUT} style={{ maxWidth: 70 }}
          />
          <button type="button" onClick={submit} disabled={busy} className={BTN_SECONDARY}>{busy ? 'Adding…' : 'Add'}</button>
          <button type="button" onClick={() => { setAdding(false); setErr(null) }} className={BTN_SECONDARY}>Cancel</button>
        </div>
        {err && <p className="text-[10px] text-red-400 mt-1">{err}</p>}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <select className={INPUT_CLS} value={value} onChange={e => onChange(e.target.value)}>
        <option value="">{emptyLabel}</option>
        {seasons.map(s => (<option key={s.id} value={s.id}>{formatSeason(s)}</option>))}
      </select>
      <button type="button" onClick={() => setAdding(true)} className="text-[11px] text-pb-accent whitespace-nowrap hover:underline">+ New</button>
    </div>
  )
}

function GradeSelect({ grades, seasonId, value, onChange, onCreated, emptyLabel = 'All grades (any)' }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async () => {
    const n = name.trim()
    if (!n) { setErr('Name is required'); return }
    setBusy(true); setErr(null)
    try {
      const g = await api.adminCreateManualGrade({ season_id: seasonId, name: n })
      onCreated(g)
      onChange(g.id)
      setAdding(false); setName('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (adding) {
    return (
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <input
            autoFocus placeholder="e.g. 3rd Grade" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={SMALL_INPUT} style={{ maxWidth: 170 }}
          />
          <button type="button" onClick={submit} disabled={busy} className={BTN_SECONDARY}>{busy ? 'Adding…' : 'Add'}</button>
          <button type="button" onClick={() => { setAdding(false); setErr(null) }} className={BTN_SECONDARY}>Cancel</button>
        </div>
        {err && <p className="text-[10px] text-red-400 mt-1">{err}</p>}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <select className={INPUT_CLS} value={value} onChange={e => onChange(e.target.value)} disabled={!seasonId}>
        <option value="">{emptyLabel}</option>
        {grades.map(g => (<option key={g.id} value={g.id}>{g.name}</option>))}
      </select>
      <button type="button" onClick={() => setAdding(true)} disabled={!seasonId} className="text-[11px] text-pb-accent whitespace-nowrap hover:underline disabled:opacity-30 disabled:pointer-events-none">+ New</button>
    </div>
  )
}

function AggregateFieldGrid({ form, setForm, includeWidesNoBalls = false }) {
  const set = (k) => (v) => setForm({ ...form, [k]: v === '' ? '' : v })
  return (
    <>
      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Match counts</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Games played" value={form.games_played} onChange={set('games_played')} />
          <NumberField label="Batting innings" value={form.batting_innings} onChange={set('batting_innings')} />
          <NumberField label="Bowling innings" value={form.bowling_innings} onChange={set('bowling_innings')} />
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Batting</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Runs" value={form.batting_runs} onChange={set('batting_runs')} />
          <NumberField label="Not outs" value={form.batting_not_outs} onChange={set('batting_not_outs')} />
          <NumberField label="Balls faced" value={form.batting_balls} onChange={set('batting_balls')} />
          <NumberField label="High score" value={form.batting_high_score} onChange={set('batting_high_score')} />
          <NumberField label="50s" value={form.batting_fifties} onChange={set('batting_fifties')} />
          <NumberField label="100s" value={form.batting_hundreds} onChange={set('batting_hundreds')} />
          <NumberField label="Ducks" value={form.batting_ducks} onChange={set('batting_ducks')} />
          <NumberField label="Fours" value={form.batting_fours} onChange={set('batting_fours')} />
          <NumberField label="Sixes" value={form.batting_sixes} onChange={set('batting_sixes')} />
          <label className="flex items-center gap-2 text-xs text-pb-text mt-5">
            <input
              type="checkbox"
              checked={!!form.batting_high_score_not_out}
              onChange={e => setForm({ ...form, batting_high_score_not_out: e.target.checked })}
            />
            HS was not out
          </label>
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Bowling</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Overs" value={form.bowling_overs} onChange={set('bowling_overs')} allowDecimal />
          <NumberField label="Balls" value={form.bowling_balls} onChange={set('bowling_balls')} />
          <NumberField label="Maidens" value={form.bowling_maidens} onChange={set('bowling_maidens')} />
          <NumberField label="Runs conceded" value={form.bowling_runs} onChange={set('bowling_runs')} />
          <NumberField label="Wickets" value={form.bowling_wickets} onChange={set('bowling_wickets')} />
          <NumberField label="5-wicket innings" value={form.bowling_five_wicket_innings} onChange={set('bowling_five_wicket_innings')} />
          <NumberField label="Best — wickets" value={form.bowling_best_wickets} onChange={set('bowling_best_wickets')} />
          <div>
            <label className={LABEL_CLS}>Best figures (e.g. 4-13)</label>
            <input type="text" value={form.bowling_best_figures || ''} onChange={e => setForm({ ...form, bowling_best_figures: e.target.value })} className={INPUT_CLS} />
          </div>
          {includeWidesNoBalls && <>
            <NumberField label="Wides" value={form.bowling_wides} onChange={set('bowling_wides')} />
            <NumberField label="No-balls" value={form.bowling_no_balls} onChange={set('bowling_no_balls')} />
          </>}
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Fielding</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Catches" value={form.fielding_catches} onChange={set('fielding_catches')} />
          <NumberField label="WK catches" value={form.fielding_catches_wk} onChange={set('fielding_catches_wk')} />
          <NumberField label="Run-outs" value={form.fielding_run_outs} onChange={set('fielding_run_outs')} />
          <NumberField label="Stumpings" value={form.fielding_stumpings} onChange={set('fielding_stumpings')} />
        </div>
      </div>

      <div className="mt-3">
        <label className={LABEL_CLS}>Notes (optional — visible only to club admins)</label>
        <textarea
          rows={2}
          value={form.notes || ''}
          onChange={e => setForm({ ...form, notes: e.target.value })}
          className={INPUT_CLS}
          placeholder="Source / reference / anything worth tracking"
        />
      </div>
    </>
  )
}

// ─── Inline spreadsheet (season aggregates, single season at a time) ───────

const SPREADSHEET_COLS = [
  { key: 'games_played', label: 'M', section: 'matches' },
  { key: 'batting_innings', label: 'I', section: 'batting' },
  { key: 'batting_runs', label: 'Runs', section: 'batting' },
  { key: 'batting_not_outs', label: 'NO', section: 'batting' },
  { key: 'batting_high_score', label: 'HS', nullable: true, section: 'batting' },
  { key: 'batting_fifties', label: '50s', section: 'batting' },
  { key: 'batting_hundreds', label: '100s', section: 'batting' },
  { key: 'batting_ducks', label: 'Ducks', section: 'batting' },
  { key: 'bowling_innings', label: 'BowlI', section: 'bowling' },
  { key: 'bowling_overs', label: 'Overs', decimal: true, section: 'bowling' },
  { key: 'bowling_wickets', label: 'Wkts', section: 'bowling' },
  { key: 'bowling_runs', label: 'BowlRuns', section: 'bowling' },
  { key: 'bowling_maidens', label: 'Mdns', section: 'bowling' },
  { key: 'bowling_best_figures', label: 'Best', text: true, section: 'bowling' },
  { key: 'fielding_catches', label: 'C', section: 'fielding' },
  { key: 'fielding_catches_wk', label: 'WK C', section: 'fielding' },
  { key: 'fielding_run_outs', label: 'RO', section: 'fielding' },
  { key: 'fielding_stumpings', label: 'St', section: 'fielding' },
]

const SPREADSHEET_SECTIONS = [
  { key: 'all', label: 'All' },
  { key: 'matches', label: 'Matches' },
  { key: 'batting', label: 'Batting' },
  { key: 'bowling', label: 'Bowling' },
  { key: 'fielding', label: 'Fielding' },
]

function emptySpreadsheetRow() {
  const r = { player_id: '' }
  SPREADSHEET_COLS.forEach(c => { r[c.key] = c.text ? '' : 0 })
  return r
}

function InlineSpreadsheet({ players, seasons, grades, onImported, onPending, onSeasonCreated, onGradeCreated }) {
  const [seasonId, setSeasonId] = useState('')
  const [gradeId, setGradeId] = useState('')
  const [section, setSection] = useState('all')
  const [rows, setRows] = useState([emptySpreadsheetRow(), emptySpreadsheetRow(), emptySpreadsheetRow()])
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const seasonGrades = useMemo(() => (grades || []).filter(g => g.season_id === seasonId), [grades, seasonId])
  const visibleCols = useMemo(
    () => section === 'all' ? SPREADSHEET_COLS : SPREADSHEET_COLS.filter(c => c.section === section),
    [section],
  )
  const season = seasons.find(s => s.id === seasonId)
  const grade = (grades || []).find(g => g.id === gradeId)

  const updateCell = (rowIdx, key, value) => {
    const next = [...rows]
    next[rowIdx] = { ...next[rowIdx], [key]: value }
    setRows(next)
  }

  // Paste handler — split clipboard text on tab/newline, fill cells starting
  // from the targeted row+column. Lets the user copy a range out of Excel
  // and paste it straight in. Column indexing is in VISIBLE-column space so
  // pasting under the Batting section fills the batting columns in order.
  const handlePaste = (e, rowIdx, visibleColIdx) => {
    const text = e.clipboardData?.getData('text/plain')
    if (!text || (!text.includes('\t') && !text.includes('\n'))) return
    e.preventDefault()
    const lines = text.replace(/\r/g, '').split('\n').filter(l => l.length > 0)
    const next = [...rows]
    lines.forEach((line, i) => {
      const cells = line.split('\t')
      const targetRow = rowIdx + i
      while (next.length <= targetRow) next.push(emptySpreadsheetRow())
      cells.forEach((raw, j) => {
        const target = visibleCols[visibleColIdx + j]
        if (!target) return
        let v = raw.trim()
        if (target.text) {
          next[targetRow] = { ...next[targetRow], [target.key]: v }
        } else if (v === '') {
          next[targetRow] = { ...next[targetRow], [target.key]: target.nullable ? '' : 0 }
        } else {
          const num = target.decimal ? parseFloat(v) : parseInt(v, 10)
          if (!Number.isNaN(num)) next[targetRow] = { ...next[targetRow], [target.key]: num }
        }
      })
    })
    setRows(next)
  }

  const handleSubmit = () => {
    setErr(null); setResult(null)
    if (!seasonId) return setErr('Choose a season at the top')
    const validRows = rows.filter(r => r.player_id)
    if (validRows.length === 0) return setErr('Add at least one row with a player selected')

    const playerById = new Map((players || []).map(p => [p.id, p.display_name]))
    onPending({
      title: `Save ${validRows.length} adjustment${validRows.length === 1 ? '' : 's'}?`,
      body: `Season: ${season?.name}${grade ? ` · ${grade.name}` : ''}\nPlayers: ${validRows.map(r => playerById.get(r.player_id) || '?').join(', ')}\n\nAll changes are reversible from the Audit tab.`,
      confirmLabel: 'Save all',
      action: async () => {
        setBusy(true)
        try {
          // Build a CSV in memory and POST through the import endpoint —
          // same upsert semantics, same audit log entry as a CSV upload.
          const headerCols = [
            'player_name', 'season_name', 'grade_name',
            ...SPREADSHEET_COLS.map(c => c.key),
          ]
          const out = [headerCols.join(',')]
          validRows.forEach(r => {
            const name = playerById.get(r.player_id) || ''
            const cells = [csvEscape(name), csvEscape(season?.name || ''), csvEscape(grade?.name || '')]
            SPREADSHEET_COLS.forEach(c => { cells.push(csvEscape(r[c.key] ?? '')) })
            out.push(cells.join(','))
          })
          const blob = new Blob([out.join('\n')], { type: 'text/csv' })
          const file = new File([blob], 'inline.csv', { type: 'text/csv' })
          const res = await api.adminImportSeasonAdjustments(file)
          setResult(res)
          if (!res.errors) {
            setRows([emptySpreadsheetRow(), emptySpreadsheetRow(), emptySpreadsheetRow()])
          }
          onImported && onImported(res)
        } catch (e) {
          setErr(e.message)
        } finally {
          setBusy(false)
        }
      },
    })
  }

  return (
    <div className="bg-pb-surface border pb-hairline rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
        <div>
          <h4 className="text-sm font-semibold text-pb-text">Spreadsheet mode — bulk add for one season</h4>
          <p className="text-[11px] text-pb-faintest">Choose a season + grade once, then one row per player. Paste a range from Excel into any cell to fill multiple rows at once.</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label className={LABEL_CLS}>Season</label>
          <SeasonSelect
            seasons={seasons}
            value={seasonId}
            onChange={id => { setSeasonId(id); setGradeId('') }}
            onCreated={onSeasonCreated}
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Grade (optional)</label>
          <GradeSelect
            grades={seasonGrades}
            seasonId={seasonId}
            value={gradeId}
            onChange={setGradeId}
            onCreated={onGradeCreated}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-1 mb-2 border-b pb-hairline">
        {SPREADSHEET_SECTIONS.map(s => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={`px-3 py-1.5 text-xs font-semibold border-b-2 transition-colors -mb-px ${section === s.key ? 'border-pb-accent text-pb-text' : 'border-transparent text-pb-faint hover:text-pb-text'}`}
          >{s.label}</button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="text-xs border-collapse">
          <thead>
            <tr>
              <th className="text-left p-1 font-mono text-[10px] text-pb-faint">Player</th>
              {visibleCols.map(c => (
                <th key={c.key} className="text-left p-1 font-mono text-[10px] text-pb-faint">{c.label}</th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={rowIdx}>
                <td className="p-0.5 min-w-[180px]">
                  <PlayerPicker players={players} value={row.player_id} onChange={v => updateCell(rowIdx, 'player_id', v)} placeholder="Player…" />
                </td>
                {visibleCols.map((c, colIdx) => (
                  <td key={c.key} className="p-0.5">
                    <input
                      type="text"
                      inputMode={c.text ? undefined : (c.decimal ? 'decimal' : 'numeric')}
                      value={row[c.key] === null || row[c.key] === undefined ? '' : row[c.key]}
                      onChange={e => {
                        const v = e.target.value
                        if (c.text) return updateCell(rowIdx, c.key, v)
                        // Allow every in-progress typing state (empty, a bare "-",
                        // a trailing ".") through untouched — coercing to a final
                        // number happens on blur. Coercing on every keystroke was
                        // what made a "-" get wiped the instant it was typed.
                        const partial = c.decimal ? /^-?\d*\.?\d*$/ : /^-?\d*$/
                        if (v === '' || partial.test(v)) updateCell(rowIdx, c.key, v)
                      }}
                      onBlur={() => {
                        if (c.text) return
                        const v = row[c.key]
                        if (v === '' || v === '-' || v === null || v === undefined) {
                          return updateCell(rowIdx, c.key, c.nullable ? '' : 0)
                        }
                        if (typeof v === 'number') return
                        const num = c.decimal ? parseFloat(v) : parseInt(v, 10)
                        updateCell(rowIdx, c.key, Number.isNaN(num) ? (c.nullable ? '' : 0) : num)
                      }}
                      onPaste={e => handlePaste(e, rowIdx, colIdx)}
                      className="w-16 bg-pb-surface2 border pb-hairline text-pb-text text-xs rounded px-1 py-1 focus:outline-none focus:border-pb-accent no-spinner"
                    />
                  </td>
                ))}
                <td className="p-0.5">
                  <button className="text-red-300 text-[10px] hover:underline" onClick={() => setRows(rows.filter((_, i) => i !== rowIdx))}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2 mt-2">
        <button className={BTN_SECONDARY} onClick={() => setRows([...rows, emptySpreadsheetRow()])}>+ Add row</button>
        <button className={BTN_PRIMARY} onClick={handleSubmit} disabled={busy}>
          {busy ? 'Saving…' : `Save ${rows.filter(r => r.player_id).length} row${rows.filter(r => r.player_id).length === 1 ? '' : 's'}`}
        </button>
      </div>

      {err && <p className="text-sm text-red-400 mt-2">{err}</p>}
      {result && (
        <div className="mt-3 text-xs text-pb-text font-mono">
          created: <b>{result.created || 0}</b> · updated: <b>{result.updated || 0}</b>
          {result.errors > 0 && <span className="text-red-300"> · errors: <b>{result.errors}</b></span>}
        </div>
      )}
    </div>
  )
}

function csvEscape(v) {
  if (v === null || v === undefined) return ''
  const s = String(v)
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"'
  }
  return s
}

// ─── Bulk CSV import panel (reusable) ───────────────────────────────────────

function ImportPanel({ kind, downloadFn, importFn, onImported }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)

  const handleTemplate = async () => {
    try {
      const res = await downloadFn()
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${kind}_template.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr(e.message) }
  }

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setErr('Please upload a .csv file. (Export from Excel via Save As → CSV.)')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setErr(`File is ${(file.size / 1024 / 1024).toFixed(1)} MB — must be 5 MB or smaller.`)
      return
    }
    setBusy(true); setErr(null); setResult(null)
    try {
      const r = await importFn(file)
      if (r.detail) throw new Error(typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail))
      setResult(r)
      onImported && onImported(r)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-pb-surface border pb-hairline rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h4 className="text-sm font-semibold text-pb-text">Bulk CSV import</h4>
          <p className="text-[11px] text-pb-faintest">
            Download the template, fill it in (Excel / Sheets), save as CSV, then upload here.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className={BTN_SECONDARY} onClick={handleTemplate}>Download template</button>
          <label className={BTN_PRIMARY + ' cursor-pointer'}>
            {busy ? 'Uploading…' : 'Upload CSV'}
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={handleFile} disabled={busy} />
          </label>
        </div>
      </div>
      {err && <p className="text-sm text-red-400 mt-2">{err}</p>}
      {result && (
        <div className="mt-3 text-xs text-pb-text">
          <div className="font-mono">
            {result.created !== undefined && <span className="mr-3">created: <b>{result.created}</b></span>}
            {result.updated !== undefined && <span className="mr-3">updated: <b>{result.updated}</b></span>}
            {result.games_created !== undefined && <span className="mr-3">games created: <b>{result.games_created}</b></span>}
            {result.errors > 0
              ? <span className="text-red-300">errors: <b>{result.errors}</b></span>
              : <span className="text-pb-faint">no errors</span>}
          </div>
          {result.errors_detail && result.errors_detail.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-red-300">Show error details ({result.errors_detail.length}{result.errors > result.errors_detail.length ? ` of ${result.errors}` : ''})</summary>
              <ul className="mt-1 list-disc pl-5 text-pb-faint font-mono text-[10px] max-h-64 overflow-y-auto">
                {result.errors_detail.map((er, i) => (
                  <li key={i}>row {er.row}: {er.error}</li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-pb-faintest text-[10px] mt-1">
            All imports are reversible from the Audit tab (look for the "import" entry).
          </p>
        </div>
      )}
    </div>
  )
}

// Fields that map to Optional[str] on the backend — empty form value must go as null, not 0.
const STRING_FIELDS = new Set(['notes', 'bowling_best_figures'])
// Fields that map to Optional[int] — empty form value must go as null.
const OPTIONAL_INT_FIELDS = new Set(['batting_high_score', 'bowling_best_wickets'])

function normalizeAggregatePayload(form) {
  const out = {}
  for (const [k, v] of Object.entries(form)) {
    if (v === '' || v === undefined) {
      if (STRING_FIELDS.has(k)) out[k] = null
      else if (OPTIONAL_INT_FIELDS.has(k)) out[k] = null
      else out[k] = 0
    } else {
      out[k] = v
    }
  }
  return out
}

// ─── Season adjustments tab ─────────────────────────────────────────────────

function SeasonAdjustmentsTab({ players, seasons, grades, refreshAll, onPending, onSeasonCreated, onGradeCreated }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_SEASON_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      // Career adjustments live in their own table but are surfaced here too:
      // they're just "adjustments with no season". Merge both lists, mark
      // each entry's kind so edit/delete dispatches to the right endpoint.
      const [seasonRows, careerRows] = await Promise.all([
        api.adminListSeasonAdjustments(),
        api.adminListCareerAdjustments(),
      ])
      const merged = [
        ...(seasonRows || []).map(r => ({ ...r, kind: 'season' })),
        ...(careerRows || []).map(r => ({ ...r, kind: 'career', season_name: 'Career (no season)' })),
      ].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      setList(merged)
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_SEASON_FORM); setEditingId(null); setErr(null) }

  const seasonGrades = useMemo(
    () => (grades || []).filter(g => g.season_id === form.season_id),
    [grades, form.season_id]
  )

  const isCareerMode = !form.season_id
  const editingKind = editingId?.kind  // null | 'season' | 'career'

  const handleSubmit = () => {
    setErr(null)
    if (!form.player_id) return setErr('Choose a player')
    const payload = normalizeAggregatePayload(form)
    if (!payload.grade_id) payload.grade_id = null

    const isCareer = !form.season_id
    // Career adjustments don't have season_id / grade_id fields, strip them.
    const careerPayload = { ...payload }
    delete careerPayload.season_id
    delete careerPayload.grade_id
    delete careerPayload.bowling_wides
    delete careerPayload.bowling_no_balls

    onPending({
      title: editingId ? 'Update adjustment?' : isCareer ? 'Save career-only adjustment?' : 'Save season adjustment?',
      body: isCareer
        ? 'This will apply across the player\'s career totals (no specific season). It appears on the player profile lifetime view but NOT in season leaderboards. Reversible from the Audit tab.'
        : 'This adds to (or overrides) what BetterStats already has for this player in this season. Every change is logged and can be undone from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) {
            if (editingKind === 'career') {
              await api.adminPatchCareerAdjustment(editingId.id, careerPayload)
            } else {
              await api.adminPatchSeasonAdjustment(editingId.id, payload)
            }
          } else {
            if (isCareer) {
              await api.adminCreateCareerAdjustment(careerPayload)
            } else {
              await api.adminCreateSeasonAdjustment(payload)
            }
          }
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = (row) => {
    setEditingId({ id: row.id, kind: row.kind })
    setForm({
      ...EMPTY_SEASON_FORM,
      ...row,
      season_id: row.kind === 'career' ? '' : (row.season_id || ''),
      grade_id: row.grade_id || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this adjustment?',
      body: `Remove the adjustment for ${row.player_name} in ${row.season_name}. This is logged and can be undone from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try {
          if (row.kind === 'career') await api.adminDeleteCareerAdjustment(row.id)
          else await api.adminDeleteSeasonAdjustment(row.id)
          await refresh(); refreshAll()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="space-y-6">
      <ImportPanel
        kind="season_adjustments"
        downloadFn={api.adminDownloadSeasonAdjustmentTemplate}
        importFn={api.adminImportSeasonAdjustments}
        onImported={() => { refresh(); refreshAll() }}
      />

      <InlineSpreadsheet
        players={players}
        seasons={seasons}
        grades={grades}
        onImported={() => { refresh(); refreshAll() }}
        onPending={onPending}
        onSeasonCreated={onSeasonCreated}
        onGradeCreated={onGradeCreated}
      />

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit season adjustment' : 'New season adjustment'}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={LABEL_CLS}>Player</label>
            <PlayerPicker players={players} value={form.player_id} onChange={(id) => setForm({ ...form, player_id: id })} />
          </div>
          <div>
            <label className={LABEL_CLS}>Season (optional)</label>
            <SeasonSelect
              seasons={seasons}
              value={form.season_id}
              onChange={id => setForm({ ...form, season_id: id, grade_id: '' })}
              onCreated={onSeasonCreated}
              emptyLabel="— Career only (no specific season) —"
            />
            {isCareerMode && (
              <p className="text-[10px] text-pb-faint mt-1">Will save as a career-only adjustment.</p>
            )}
          </div>
          <div>
            <label className={LABEL_CLS}>Grade (optional)</label>
            <GradeSelect
              grades={seasonGrades}
              seasonId={form.season_id}
              value={form.grade_id || ''}
              onChange={id => setForm({ ...form, grade_id: id })}
              onCreated={onGradeCreated}
            />
            {form.season_id && seasonGrades.length === 0 && (
              <p className="text-[10px] text-pb-faintest mt-1">No grades defined for this season yet.</p>
            )}
          </div>
        </div>

        <AggregateFieldGrid form={form} setForm={setForm} includeWidesNoBalls />

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update adjustment' : 'Save adjustment'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing season adjustments</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No season adjustments yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                    <th className="text-left py-2 pr-3">Player</th>
                    <th className="text-left py-2 pr-3">Season</th>
                    <th className="text-right py-2 pr-3">Games</th>
                    <th className="text-right py-2 pr-3">Runs</th>
                    <th className="text-right py-2 pr-3">Wkts</th>
                    <th className="text-right py-2 pr-3">Catches</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {list.map(r => (
                    <tr key={r.id} className="border-b pb-hairline">
                      <td className="py-2 pr-3 text-pb-text">{r.player_name}</td>
                      <td className="py-2 pr-3 text-pb-faint">{formatSeason(r.season_name)}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.games_played}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.batting_runs}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.bowling_wickets}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.fielding_catches}{r.fielding_catches_wk ? <span className="text-pb-faintest"> ({r.fielding_catches_wk} wk)</span> : ''}</td>
                      <td className="py-2 text-right">
                        <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                        <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  )
}

// ─── Career adjustments tab ─────────────────────────────────────────────────

function CareerAdjustmentsTab({ players, refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_CAREER_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListCareerAdjustments() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_CAREER_FORM); setEditingId(null); setErr(null) }

  const handleSubmit = () => {
    setErr(null)
    if (!form.player_id) return setErr('Choose a player')
    const payload = normalizeAggregatePayload(form)
    onPending({
      title: editingId ? 'Update career adjustment?' : 'Save career adjustment?',
      body: 'Career adjustments apply ONLY to a player\'s career-total view (player profile lifetime totals). They don\'t affect any season leaderboard. Every change is logged and reversible from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await api.adminPatchCareerAdjustment(editingId, payload)
          else await api.adminCreateCareerAdjustment(payload)
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = (row) => {
    setEditingId(row.id)
    setForm({ ...EMPTY_CAREER_FORM, ...row })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this career adjustment?',
      body: `Remove the career-only delta for ${row.player_name}. This is logged and can be undone from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try { await api.adminDeleteCareerAdjustment(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit career adjustment' : 'New career adjustment'}
        </h3>
        <p className="text-xs text-pb-faint mb-3">
          Use this only when you have career totals (e.g. from a club history book) with no season-by-season detail. Career adjustments do NOT appear in season leaderboards.
        </p>
        <div className="max-w-xs">
          <label className={LABEL_CLS}>Player</label>
          <PlayerPicker players={players} value={form.player_id} onChange={(id) => setForm({ ...form, player_id: id })} />
        </div>

        <AggregateFieldGrid form={form} setForm={setForm} />

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update adjustment' : 'Save adjustment'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing career adjustments</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No career adjustments yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">Player</th>
                  <th className="text-right py-2 pr-3">Games</th>
                  <th className="text-right py-2 pr-3">Runs</th>
                  <th className="text-right py-2 pr-3">Wkts</th>
                  <th className="text-right py-2 pr-3">Catches</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-text">{r.player_name}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.games_played}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.batting_runs}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.bowling_wickets}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.fielding_catches}{r.fielding_catches_wk ? <span className="text-pb-faintest"> ({r.fielding_catches_wk} wk)</span> : ''}</td>
                    <td className="py-2 text-right">
                      <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                      <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}

// ─── Manual games tab ───────────────────────────────────────────────────────

function emptyBattingRow() {
  return { player_id: '', innings_number: 1, batting_position: '', runs: 0, balls: '', fours: 0, sixes: 0, dismissal_type: '', not_out: false, did_not_bat: false }
}
function emptyBowlingRow() {
  return { player_id: '', innings_number: 1, overs: 0, maidens: 0, runs: 0, wickets: 0, wides: 0, no_balls: 0 }
}
function emptyFieldingRow() {
  return { player_id: '', catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 }
}

const EMPTY_GAME_FORM = {
  season_id: '', grade_id: '', played_at: '', home_team: '', away_team: '', opposition: '',
  venue: '', result: '', winning_team: '', is_final: false, match_format: '', notes: '',
  batting_innings: [], bowling_spells: [], fielding_stats: [],
}

const GAME_FORM_SECTIONS = [
  { key: 'match', label: 'Match Info' },
  { key: 'batting', label: 'Batting' },
  { key: 'bowling', label: 'Bowling' },
  { key: 'fielding', label: 'Fielding' },
]

function ManualGamesTab({ players, seasons, grades, knownValues, refreshAll, onPending, onSeasonCreated, onGradeCreated }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_GAME_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)
  const [formSection, setFormSection] = useState('match')

  const seasonGrades = useMemo(
    () => (grades || []).filter(g => g.season_id === form.season_id),
    [grades, form.season_id]
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListManualGames() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_GAME_FORM); setEditingId(null); setErr(null) }

  const buildPayload = () => {
    const sanitize = (rows, mapFn) => rows
      .filter(r => r.player_id)
      .map(r => {
        const out = mapFn(r)
        Object.keys(out).forEach(k => { if (out[k] === '') out[k] = null })
        return out
      })
    return {
      season_id: form.season_id,
      grade_id: form.grade_id || null,
      played_at: form.played_at || null,
      home_team: form.home_team || null,
      away_team: form.away_team || null,
      opposition: form.opposition || null,
      venue: form.venue || null,
      result: form.result || null,
      winning_team: form.winning_team || null,
      is_final: !!form.is_final,
      match_format: form.match_format || null,
      notes: form.notes || null,
      batting_innings: sanitize(form.batting_innings, r => ({ ...r, runs: r.runs || 0, fours: r.fours || 0, sixes: r.sixes || 0 })),
      bowling_spells: sanitize(form.bowling_spells, r => ({ ...r, overs: r.overs || 0, runs: r.runs || 0, wickets: r.wickets || 0 })),
      fielding_stats: sanitize(form.fielding_stats, r => r),
    }
  }

  const handleSubmit = () => {
    setErr(null)
    if (!form.season_id) return setErr('Choose a season')
    const payload = buildPayload()
    if (payload.batting_innings.length === 0 && payload.bowling_spells.length === 0 && payload.fielding_stats.length === 0) {
      return setErr('Add at least one batting, bowling or fielding row.')
    }
    onPending({
      title: editingId ? 'Update manual game?' : 'Save manual game?',
      body: 'A manual game appears in stats aggregations like any other match. Every change is logged and reversible from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await api.adminPatchManualGame(editingId, payload)
          else await api.adminCreateManualGame(payload)
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = async (row) => {
    try {
      const full = await api.adminGetManualGame(row.id)
      setEditingId(row.id)
      setForm({
        ...EMPTY_GAME_FORM,
        ...full,
        grade_id: full.grade_id || '',
        played_at: full.played_at ? full.played_at.split('T')[0] : '',
        batting_innings: (full.batting_innings || []).map(r => ({ ...r, batting_position: r.batting_position || '' })),
        bowling_spells: (full.bowling_spells || []),
        fielding_stats: (full.fielding_stats || []),
      })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { setErr(e.message) }
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this manual game?',
      body: `Remove the manual game from ${row.played_at || 'date unknown'}${row.opposition ? ` vs ${row.opposition}` : ''}. Reversible from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try { await api.adminDeleteManualGame(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  const updateChild = (collection, idx, key, value) => {
    const arr = [...(form[collection] || [])]
    arr[idx] = { ...arr[idx], [key]: value }
    setForm({ ...form, [collection]: arr })
  }
  const addChild = (collection, blankFn) => setForm({ ...form, [collection]: [...(form[collection] || []), blankFn()] })
  const removeChild = (collection, idx) => {
    const arr = [...(form[collection] || [])]
    arr.splice(idx, 1)
    setForm({ ...form, [collection]: arr })
  }

  return (
    <div className="space-y-6">
      <ImportPanel
        kind="manual_games"
        downloadFn={api.adminDownloadManualGamesTemplate}
        importFn={api.adminImportManualGames}
        onImported={() => { refresh(); refreshAll() }}
      />

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit manual game' : 'New manual game'}
        </h3>
        <p className="text-xs text-pb-faint mb-3">
          Date, opposition and venue can be left blank if unknown. At least one batting / bowling / fielding row is required.
          {' '}Got a typed or printed scorecard to photograph instead of typing it in?{' '}
          <Link to="/admin/upload-scorecard" className="text-pb-accent underline hover:opacity-80">
            Upload Historical Scorecard
          </Link>{' '}
          reads it for you.
        </p>

        <div className="flex flex-wrap gap-1 mb-3 border-b pb-hairline">
          {GAME_FORM_SECTIONS.map(s => {
            const count = s.key === 'match' ? null
              : s.key === 'batting' ? (form.batting_innings || []).length
              : s.key === 'bowling' ? (form.bowling_spells || []).length
              : (form.fielding_stats || []).length
            return (
              <button
                key={s.key}
                onClick={() => setFormSection(s.key)}
                className={`px-3 py-1.5 text-xs font-semibold border-b-2 transition-colors -mb-px ${formSection === s.key ? 'border-pb-accent text-pb-text' : 'border-transparent text-pb-faint hover:text-pb-text'}`}
              >
                {s.label}{count !== null && count > 0 && <span className="ml-1.5 text-pb-faintest font-mono">({count})</span>}
              </button>
            )
          })}
        </div>

        {formSection === 'match' && <><div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={LABEL_CLS}>Season *</label>
            <SeasonSelect
              seasons={seasons}
              value={form.season_id}
              onChange={id => setForm({ ...form, season_id: id, grade_id: '' })}
              onCreated={onSeasonCreated}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Grade (optional)</label>
            <GradeSelect
              grades={seasonGrades}
              seasonId={form.season_id}
              value={form.grade_id || ''}
              onChange={id => setForm({ ...form, grade_id: id })}
              onCreated={onGradeCreated}
              emptyLabel="— None —"
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Date (optional)</label>
            <input type="date" value={form.played_at || ''} onChange={e => setForm({ ...form, played_at: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Opposition (optional)</label>
            <ComboInput
              value={form.opposition}
              onChange={v => setForm({ ...form, opposition: v })}
              suggestions={knownValues?.oppositions || []}
              placeholder="Start typing…"
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Home team</label>
            <input type="text" value={form.home_team || ''} onChange={e => setForm({ ...form, home_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Away team</label>
            <input type="text" value={form.away_team || ''} onChange={e => setForm({ ...form, away_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Venue</label>
            <ComboInput
              value={form.venue}
              onChange={v => setForm({ ...form, venue: v })}
              suggestions={knownValues?.venues || []}
              placeholder="Start typing…"
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Result</label>
            <input type="text" value={form.result || ''} onChange={e => setForm({ ...form, result: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Winning team</label>
            <input type="text" value={form.winning_team || ''} onChange={e => setForm({ ...form, winning_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Match format</label>
            <input type="text" value={form.match_format || ''} onChange={e => setForm({ ...form, match_format: e.target.value })} placeholder="T20 / 40-over / 2-day" className={INPUT_CLS} />
          </div>
          <label className="flex items-center gap-2 text-xs text-pb-text mt-5">
            <input type="checkbox" checked={!!form.is_final} onChange={e => setForm({ ...form, is_final: e.target.checked })} />
            Final
          </label>
        </div>

        <div className="mt-3">
          <label className={LABEL_CLS}>Notes (admin only)</label>
          <textarea rows={2} value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })} className={INPUT_CLS} />
        </div>
        </>}

        {/* Batting */}
        {formSection === 'batting' && <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Batting</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('batting_innings', emptyBattingRow)}>+ Add batting row</button>
          </div>
          {(form.batting_innings || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('batting_innings', idx, 'player_id', v)} />
              </div>
              <div className="col-span-1"><NumberField label="Pos" value={row.batting_position} onChange={v => updateChild('batting_innings', idx, 'batting_position', v)} /></div>
              <div className="col-span-1"><NumberField label="Runs" value={row.runs} onChange={v => updateChild('batting_innings', idx, 'runs', v)} /></div>
              <div className="col-span-1"><NumberField label="Balls" value={row.balls} onChange={v => updateChild('batting_innings', idx, 'balls', v)} /></div>
              <div className="col-span-1"><NumberField label="4s" value={row.fours} onChange={v => updateChild('batting_innings', idx, 'fours', v)} /></div>
              <div className="col-span-1"><NumberField label="6s" value={row.sixes} onChange={v => updateChild('batting_innings', idx, 'sixes', v)} /></div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>How out</label>
                <input type="text" value={row.dismissal_type || ''} onChange={e => updateChild('batting_innings', idx, 'dismissal_type', e.target.value)} placeholder="b Smith / c Jones b Smith / not out" className={INPUT_CLS} />
              </div>
              <div className="col-span-1 flex flex-col gap-1 pb-1">
                <label className="flex items-center gap-1 text-[10px] text-pb-text">
                  <input type="checkbox" checked={!!row.not_out} onChange={e => updateChild('batting_innings', idx, 'not_out', e.target.checked)} />NO
                </label>
                <label className="flex items-center gap-1 text-[10px] text-pb-text">
                  <input type="checkbox" checked={!!row.did_not_bat} onChange={e => updateChild('batting_innings', idx, 'did_not_bat', e.target.checked)} />DNB
                </label>
              </div>
              <div className="col-span-12 -mt-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('batting_innings', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>}

        {/* Bowling */}
        {formSection === 'bowling' && <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Bowling</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('bowling_spells', emptyBowlingRow)}>+ Add bowling row</button>
          </div>
          {(form.bowling_spells || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('bowling_spells', idx, 'player_id', v)} />
              </div>
              <div className="col-span-1"><NumberField label="Overs" value={row.overs} onChange={v => updateChild('bowling_spells', idx, 'overs', v)} allowDecimal /></div>
              <div className="col-span-1"><NumberField label="M" value={row.maidens} onChange={v => updateChild('bowling_spells', idx, 'maidens', v)} /></div>
              <div className="col-span-1"><NumberField label="Runs" value={row.runs} onChange={v => updateChild('bowling_spells', idx, 'runs', v)} /></div>
              <div className="col-span-1"><NumberField label="Wkts" value={row.wickets} onChange={v => updateChild('bowling_spells', idx, 'wickets', v)} /></div>
              <div className="col-span-1"><NumberField label="Wd" value={row.wides} onChange={v => updateChild('bowling_spells', idx, 'wides', v)} /></div>
              <div className="col-span-1"><NumberField label="Nb" value={row.no_balls} onChange={v => updateChild('bowling_spells', idx, 'no_balls', v)} /></div>
              <div className="col-span-2 pb-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('bowling_spells', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>}

        {/* Fielding */}
        {formSection === 'fielding' && <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Fielding</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('fielding_stats', emptyFieldingRow)}>+ Add fielding row</button>
          </div>
          {(form.fielding_stats || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('fielding_stats', idx, 'player_id', v)} />
              </div>
              <div className="col-span-2"><NumberField label="Catches" value={row.catches} onChange={v => updateChild('fielding_stats', idx, 'catches', v)} /></div>
              <div className="col-span-2"><NumberField label="WK catches" value={row.catches_wk} onChange={v => updateChild('fielding_stats', idx, 'catches_wk', v)} /></div>
              <div className="col-span-1"><NumberField label="RO" value={row.run_outs} onChange={v => updateChild('fielding_stats', idx, 'run_outs', v)} /></div>
              <div className="col-span-1"><NumberField label="St" value={row.stumpings} onChange={v => updateChild('fielding_stats', idx, 'stumpings', v)} /></div>
              <div className="col-span-2 pb-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('fielding_stats', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>}

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update manual game' : 'Save manual game'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing manual games</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No manual games yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">Date</th>
                  <th className="text-left py-2 pr-3">Opposition</th>
                  <th className="text-left py-2 pr-3">Season</th>
                  <th className="text-right py-2 pr-3">Players</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-text">{r.played_at ? r.played_at.split('T')[0] : '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint">{r.opposition || '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint">{formatSeason(r.season_name)}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.batting_count}</td>
                    <td className="py-2 text-right">
                      <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                      <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}

// ─── Audit tab ──────────────────────────────────────────────────────────────

function AuditTab({ refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListManualEntryAudit() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const handleUndo = (row) => {
    onPending({
      title: 'Undo this change?',
      body: `Reverse: ${row.summary}\n\nThis will reapply the prior state and mark the entry as undone.`,
      confirmLabel: 'Undo',
      danger: true,
      action: async () => {
        try { await api.adminUndoManualEntry(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-pb-text">Manual entry audit log</h3>
        <button className={BTN_SECONDARY} onClick={refresh}>Refresh</button>
      </div>
      {err && <p className="text-sm text-red-400 mb-2">{err}</p>}
      {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
        list.length === 0 ? (
          <p className="text-sm text-pb-faint">No manual edits yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">When</th>
                  <th className="text-left py-2 pr-3">By</th>
                  <th className="text-left py-2 pr-3">Action</th>
                  <th className="text-left py-2 pr-3">Summary</th>
                  <th className="text-left py-2 pr-3">Status</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-faint font-mono text-[11px]">
                      {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-2 pr-3 text-pb-text text-xs">{r.user_name || '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint text-xs uppercase font-mono">{r.action}</td>
                    <td className="py-2 pr-3 text-pb-text">{r.summary}</td>
                    <td className="py-2 pr-3">
                      {r.undone_at
                        ? <span className="text-[11px] text-pb-faint">undone</span>
                        : <span className="text-[11px] text-pb-text">live</span>}
                    </td>
                    <td className="py-2 text-right">
                      {!r.undone_at && (
                        <button className={BTN_DANGER} onClick={() => handleUndo(r)}>Undo</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

// ─── Main page ──────────────────────────────────────────────────────────────

export default function AdminManualEntries() {
  const [activeTab, setActiveTab] = useState(() => {
    return window.location.hash.replace('#', '') || 'season'
  })
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState([])
  const [grades, setGrades] = useState([])
  const [knownValues, setKnownValues] = useState({ oppositions: [], venues: [] })
  const [pending, setPending] = useState(null)
  const [tick, setTick] = useState(0)

  const refreshAll = useCallback(() => setTick(t => t + 1), [])
  // Update the shared season/grade lists in place (no tick bump — bumping
  // tick remounts the active tab via its `key`, which would wipe whatever
  // the admin is mid-typing in the rest of the form they just created a
  // season/grade from).
  const onSeasonCreated = useCallback((s) => setSeasons(prev => [...prev, s]), [])
  const onGradeCreated = useCallback((g) => setGrades(prev => [...prev, g]), [])

  useEffect(() => {
    ;(async () => {
      try {
        const [p, s, g, kv] = await Promise.all([
          api.adminListPlayers(),
          api.adminListSeasons(),
          api.adminListGradesBySeason(),
          api.adminListManualEntryKnownValues(),
        ])
        setPlayers((p || []).filter(x => x.is_player !== false))
        setSeasons(s || [])
        setGrades(g || [])
        setKnownValues(kv || { oppositions: [], venues: [] })
      } catch {}
    })()
  }, [])

  useEffect(() => {
    window.location.hash = activeTab
  }, [activeTab])

  const onPending = (p) => setPending(p)
  const confirmPending = async () => {
    if (!pending) return
    const action = pending.action
    setPending(null)
    if (action) await action()
  }

  return (
    <BetterStatsLayout>
      <div className="p-4 md:p-6 max-w-6xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-pb-text mb-1">Manual stat entries</h1>
          <p className="text-sm text-pb-faint max-w-2xl">
            Add historical games and stats that aren't in the upstream feed.
            Every change is logged and reversible — sync never touches this data.
          </p>
        </div>

        <div className="border-b pb-hairline mb-5 flex flex-wrap gap-x-6">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`pb-3 -mb-px text-sm font-semibold border-b-2 transition-colors ${activeTab === t.key ? 'border-pb-accent text-pb-text' : 'border-transparent text-pb-faint hover:text-pb-text'}`}
            >{t.label}</button>
          ))}
        </div>

        <p className="text-xs text-pb-faintest mb-4">{TABS.find(t => t.key === activeTab)?.hint}</p>

        {activeTab === 'season' && (
          <SeasonAdjustmentsTab key={tick + ':season'} players={players} seasons={seasons} grades={grades} refreshAll={refreshAll} onPending={onPending} onSeasonCreated={onSeasonCreated} onGradeCreated={onGradeCreated} />
        )}
        {activeTab === 'game' && (
          <ManualGamesTab key={tick + ':game'} players={players} seasons={seasons} grades={grades} knownValues={knownValues} refreshAll={refreshAll} onPending={onPending} onSeasonCreated={onSeasonCreated} onGradeCreated={onGradeCreated} />
        )}
        {activeTab === 'audit' && (
          <AuditTab key={tick + ':audit'} refreshAll={refreshAll} onPending={onPending} />
        )}

        <ConfirmModal
          open={!!pending}
          title={pending?.title || 'Confirm'}
          body={pending?.body || ''}
          confirmLabel={pending?.confirmLabel || 'Confirm'}
          danger={pending?.danger}
          onConfirm={confirmPending}
          onCancel={() => setPending(null)}
        />
      </div>
    </BetterStatsLayout>
  )
}
