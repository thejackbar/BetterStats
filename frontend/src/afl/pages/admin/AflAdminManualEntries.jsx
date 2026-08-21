import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'

// Manual stat entries — the football twin of BetterStats' Adjustments tab.
//
// A club's history reaches BetterFootball three ways: the PlayHQ sync, an
// Import Stats / Import Results upload, and this. The first two are bulk and
// all-or-nothing; this is the one place a single figure gets corrected.
//
// Everything entered here is a DELTA, added on top of what the sync and the
// imports already hold — so correcting a season means entering the shortfall,
// and every screen says so rather than leaving it to be discovered.
//
// There is deliberately no per-game entry here: football's answer to "type a
// match in" is Import Results, which writes real games rows from the club's
// own register.

const INPUT = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent'
const LABEL = 'font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1'
const BTN = 'font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1.5 text-black bg-[var(--pb-accent)] disabled:opacity-50'
const BTN2 = 'font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1.5 bg-pb-surface2 border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-50'
const BTN_LINK = 'font-mono text-[10px] text-pb-dim hover:text-pb-text underline'

const TABS = [
  { key: 'adjustments', label: 'Adjustments' },
  { key: 'audit', label: 'Audit & undo' },
]

// The stat columns an adjustment carries, in the order they read on screen.
// Mirrors STAT_FIELDS in routers/afl/manual_entries.py — a column added there
// needs adding here, to SPREADSHEET_COLS below, and to the CSV template.
const STAT_FIELDS = [
  { key: 'games_played', label: 'Games' },
  { key: 'goals', label: 'Goals' },
  { key: 'behinds', label: 'Behinds' },
  { key: 'bog_count', label: 'Best on ground' },
  { key: 'captain_games', label: 'Games as captain' },
  { key: 'club_bf_votes', label: 'Club B&F votes' },
  { key: 'comp_bf_votes', label: 'Comp B&F votes' },
]

const EMPTY_FORM = {
  player_id: '', season_id: '', grade_id: '', notes: '',
  ...Object.fromEntries(STAT_FIELDS.map(f => [f.key, 0])),
}

function csvEscape(v) {
  if (v === null || v === undefined) return ''
  const s = String(v)
  return /[,"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

function Confirm({ open, title, body, confirmLabel = 'Confirm', danger, onConfirm, onCancel }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={onCancel}>
      <div className="pb-card bg-pb-surface p-5 max-w-md w-full" onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-pb-text mb-2">{title}</h3>
        <p className="text-[12px] text-pb-dim mb-4 whitespace-pre-line">{body}</p>
        <div className="flex justify-end gap-2">
          <button className={BTN2} onClick={onCancel}>Cancel</button>
          <button
            className={danger
              ? 'font-mono text-[10px] tracking-wide2 font-semibold rounded px-2.5 py-1.5 border border-pb-red/40 text-pb-red hover:bg-pb-red/10'
              : BTN}
            onClick={onConfirm}
          >{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

function PlayerPicker({ players, value, onChange, placeholder = 'Search player…' }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const selected = players.find(p => p.id === value)
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    if (ql.length < 2) return []
    return players.filter(p => (p.display_name || '').toLowerCase().includes(ql)).slice(0, 8)
  }, [q, players])

  return (
    <div className="relative">
      <input
        type="text"
        value={open ? q : (selected ? selected.display_name : '')}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => { setQ(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={INPUT}
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-20 left-0 right-0 mt-1 max-h-56 overflow-y-auto pb-card bg-pb-surface">
          {filtered.map(p => (
            <button
              key={p.id}
              type="button"
              onMouseDown={() => { onChange(p.id); setOpen(false); setQ('') }}
              className="block w-full text-left px-2 py-1.5 text-[12px] text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
            >{p.display_name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// A season/grade dropdown with an inline "+ New" — a pre-PlayHQ era has
// neither, and the sync will never create one, so without this an admin can't
// enter the history they're here to enter.
function SeasonSelect({ seasons, value, onChange, onCreated }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [year, setYear] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit() {
    const n = name.trim()
    if (!n) { setErr('Name is required'); return }
    setBusy(true); setErr(null)
    try {
      const s = await aflApi.importsCreateSeason({ name: n, year: year ? parseInt(year, 10) : null })
      onCreated(s); onChange(s.id)
      setAdding(false); setName(''); setYear('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (adding) {
    return (
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <input autoFocus placeholder="e.g. 1994" value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={INPUT} style={{ maxWidth: 150 }} />
          <input placeholder="Year" value={year}
            onChange={e => setYear(e.target.value.replace(/\D/g, '').slice(0, 4))}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={INPUT} style={{ maxWidth: 70 }} />
          <button type="button" onClick={submit} disabled={busy} className={BTN2}>{busy ? 'ADDING…' : 'ADD'}</button>
          <button type="button" onClick={() => { setAdding(false); setErr(null) }} className={BTN_LINK}>Cancel</button>
        </div>
        {err && <p className="text-[11px] text-pb-red mt-1">{err}</p>}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <select className={INPUT} value={value} onChange={e => onChange(e.target.value)}>
        <option value="">— Career only (no season) —</option>
        {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <button type="button" onClick={() => setAdding(true)} className="text-[11px] text-[var(--pb-accent)] whitespace-nowrap hover:underline">+ New</button>
    </div>
  )
}

function GradeSelect({ grades, seasonId, value, onChange, onCreated }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function submit() {
    const n = name.trim()
    if (!n) { setErr('Name is required'); return }
    setBusy(true); setErr(null)
    try {
      const g = await aflApi.manualCreateGrade({ season_id: seasonId, name: n })
      onCreated(g); onChange(g.id)
      setAdding(false); setName('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (adding) {
    return (
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <input autoFocus placeholder="e.g. Reserves" value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit() }}
            className={INPUT} style={{ maxWidth: 170 }} />
          <button type="button" onClick={submit} disabled={busy} className={BTN2}>{busy ? 'ADDING…' : 'ADD'}</button>
          <button type="button" onClick={() => { setAdding(false); setErr(null) }} className={BTN_LINK}>Cancel</button>
        </div>
        {err && <p className="text-[11px] text-pb-red mt-1">{err}</p>}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <select className={INPUT} value={value} onChange={e => onChange(e.target.value)} disabled={!seasonId}>
        <option value="">Whole season (any grade)</option>
        {grades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
      </select>
      <button type="button" onClick={() => setAdding(true)} disabled={!seasonId}
        className="text-[11px] text-[var(--pb-accent)] whitespace-nowrap hover:underline disabled:opacity-30 disabled:pointer-events-none">+ New</button>
    </div>
  )
}

function NumberField({ label, value, onChange }) {
  return (
    <div>
      <label className={LABEL}>{label}</label>
      <input
        type="number"
        min={0}
        value={value === '' || value === null || value === undefined ? '' : value}
        onChange={e => {
          const v = e.target.value
          onChange(v === '' ? '' : parseInt(v, 10))
        }}
        className={INPUT}
      />
    </div>
  )
}

function ImportPanel({ onImported }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      toast.error('Please upload a .csv file (Excel: Save As → CSV).')
      return
    }
    setBusy(true); setResult(null)
    try {
      const r = await aflApi.adjustmentsImport(file)
      setResult(r)
      onImported()
    } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 space-y-2">
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-sm font-semibold text-pb-text">Bulk CSV import</h3>
          <p className="text-[12px] text-pb-dim mt-0.5 max-w-2xl">
            Download the template, fill it in, save as CSV and upload it here. A row for a
            player and season that already has an adjustment REPLACES that adjustment
            rather than adding a second one, so a corrected sheet can be re-uploaded.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a href={aflApi.adjustmentsTemplateUrl()} className={BTN2}>DOWNLOAD TEMPLATE</a>
          <label className={BTN + ' cursor-pointer'}>
            {busy ? 'UPLOADING…' : 'UPLOAD CSV'}
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={handleFile} disabled={busy} />
          </label>
        </div>
      </div>
      {result && (
        <div className="text-[12px] text-pb-text font-mono">
          created: <b>{result.created || 0}</b> · updated: <b>{result.updated || 0}</b>
          {result.errors > 0 && <span className="text-pb-red"> · errors: <b>{result.errors}</b></span>}
          {result.errors_detail?.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-pb-red">Show error details</summary>
              <ul className="mt-1 list-disc pl-5 text-pb-faint text-[10px] max-h-56 overflow-y-auto">
                {result.errors_detail.map((er, i) => <li key={i}>row {er.row}: {er.error}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

const SPREADSHEET_COLS = STAT_FIELDS.map(f => ({
  key: f.key,
  label: { games_played: 'G', goals: 'Goals', behinds: 'Beh', bog_count: 'BOG',
           captain_games: 'Capt', club_bf_votes: 'Club B&F', comp_bf_votes: 'Comp B&F' }[f.key],
}))

const emptyRow = () => ({ player_id: '', ...Object.fromEntries(SPREADSHEET_COLS.map(c => [c.key, 0])) })

// One season, one row per player. Posts through the CSV import endpoint —
// same upsert rule, same audit entry, so there is one definition of what a
// bulk write does rather than a second write path to keep in step.
function Spreadsheet({ players, seasons, grades, onSaved, onPending, onSeasonCreated, onGradeCreated }) {
  const toast = useToast()
  const [seasonId, setSeasonId] = useState('')
  const [gradeId, setGradeId] = useState('')
  const [rows, setRows] = useState([emptyRow(), emptyRow(), emptyRow()])
  const [busy, setBusy] = useState(false)
  const seasonGrades = useMemo(() => grades.filter(g => g.season_id === seasonId), [grades, seasonId])
  const season = seasons.find(s => s.id === seasonId)
  const grade = grades.find(g => g.id === gradeId)
  const filled = rows.filter(r => r.player_id)

  const setCell = (i, key, value) => setRows(prev => {
    const next = [...prev]
    next[i] = { ...next[i], [key]: value }
    return next
  })

  // Paste a range straight out of Excel — split on tab/newline and fill from
  // the targeted cell onwards, adding rows as needed.
  function handlePaste(e, rowIdx, colIdx) {
    const text = e.clipboardData?.getData('text/plain')
    if (!text || (!text.includes('\t') && !text.includes('\n'))) return
    e.preventDefault()
    const lines = text.replace(/\r/g, '').split('\n').filter(Boolean)
    setRows(prev => {
      const next = [...prev]
      lines.forEach((line, i) => {
        const target = rowIdx + i
        while (next.length <= target) next.push(emptyRow())
        line.split('\t').forEach((raw, j) => {
          const col = SPREADSHEET_COLS[colIdx + j]
          if (!col) return
          const n = parseInt(raw.trim(), 10)
          next[target] = { ...next[target], [col.key]: Number.isNaN(n) ? 0 : n }
        })
      })
      return next
    })
  }

  function submit() {
    if (!seasonId) { toast.error('Choose a season first'); return }
    if (filled.length === 0) { toast.error('Add at least one row with a player'); return }
    const nameById = new Map(players.map(p => [p.id, p.display_name]))
    onPending({
      title: `Save ${filled.length} adjustment${filled.length === 1 ? '' : 's'}?`,
      body: `${season?.name}${grade ? ` · ${grade.name}` : ''}\n`
        + `${filled.map(r => nameById.get(r.player_id) || '?').join(', ')}\n\n`
        + 'These add to what the sync and any import already hold. Reversible from Audit & undo.',
      confirmLabel: 'Save all',
      action: async () => {
        setBusy(true)
        try {
          const header = ['player_name', 'season_name', 'grade_name', ...SPREADSHEET_COLS.map(c => c.key), 'notes']
          const out = [header.join(',')]
          filled.forEach(r => {
            out.push([
              csvEscape(nameById.get(r.player_id) || ''),
              csvEscape(season?.name || ''),
              csvEscape(grade?.name || ''),
              ...SPREADSHEET_COLS.map(c => csvEscape(r[c.key] ?? 0)),
              '',
            ].join(','))
          })
          const file = new File([new Blob([out.join('\n')], { type: 'text/csv' })], 'inline.csv', { type: 'text/csv' })
          const res = await aflApi.adjustmentsImport(file)
          if (res.errors > 0) {
            toast.error(`${res.errors} row(s) couldn't be saved: ${res.errors_detail?.[0]?.error || ''}`)
          } else {
            toast.success(`Saved — ${res.created} added, ${res.updated} updated`)
            setRows([emptyRow(), emptyRow(), emptyRow()])
          }
          onSaved()
        } catch (e) { toast.error(e.message) } finally { setBusy(false) }
      },
    })
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-pb-text">Spreadsheet mode — one season at a time</h3>
        <p className="text-[12px] text-pb-dim mt-0.5 max-w-2xl">
          Pick the season and grade once, then a row per player. Paste a range from Excel
          into any cell to fill several rows at once.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl">
        <div>
          <label className={LABEL}>Season</label>
          <SeasonSelect seasons={seasons} value={seasonId}
            onChange={id => { setSeasonId(id); setGradeId('') }} onCreated={onSeasonCreated} />
        </div>
        <div>
          <label className={LABEL}>Grade (optional)</label>
          <GradeSelect grades={seasonGrades} seasonId={seasonId} value={gradeId}
            onChange={setGradeId} onCreated={onGradeCreated} />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="text-[12px] border-collapse">
          <thead>
            <tr className="font-mono text-[10px] tracking-wide2 text-pb-faint text-left">
              <th className="p-1">PLAYER</th>
              {SPREADSHEET_COLS.map(c => <th key={c.key} className="p-1">{c.label}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="p-0.5 min-w-[180px]">
                  <PlayerPicker players={players} value={row.player_id}
                    onChange={v => setCell(i, 'player_id', v)} placeholder="Player…" />
                </td>
                {SPREADSHEET_COLS.map((c, j) => (
                  <td key={c.key} className="p-0.5">
                    <input
                      inputMode="numeric"
                      value={row[c.key] ?? ''}
                      onChange={e => {
                        const v = e.target.value
                        if (v === '' || /^\d+$/.test(v)) setCell(i, c.key, v)
                      }}
                      onBlur={() => {
                        const v = row[c.key]
                        if (typeof v === 'number') return
                        const n = parseInt(v, 10)
                        setCell(i, c.key, Number.isNaN(n) ? 0 : n)
                      }}
                      onPaste={e => handlePaste(e, i, j)}
                      className="w-16 bg-pb-surface2 border pb-hairline rounded px-1 py-1 text-[12px] text-pb-text focus:outline-none focus:border-pb-accent"
                    />
                  </td>
                ))}
                <td className="p-0.5">
                  <button className="text-pb-red/70 hover:text-pb-red text-[11px]"
                    onClick={() => setRows(rows.filter((_, k) => k !== i))}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2">
        <button className={BTN2} onClick={() => setRows([...rows, emptyRow()])}>+ ADD ROW</button>
        <button className={BTN} onClick={submit} disabled={busy}>
          {busy ? 'SAVING…' : `SAVE ${filled.length} ROW${filled.length === 1 ? '' : 'S'}`}
        </button>
      </div>
    </div>
  )
}

function AdjustmentsTab({ players, seasons, grades, onPending, onSeasonCreated, onGradeCreated }) {
  const toast = useToast()
  const [list, setList] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const formRef = useRef(null)

  const refresh = useCallback(() => aflApi.adjustmentsList()
    .then(setList).catch(e => toast.error(e.message)), [toast])
  useEffect(() => { refresh() }, [refresh])

  const seasonGrades = useMemo(
    () => grades.filter(g => g.season_id === form.season_id), [grades, form.season_id])
  const isCareer = !form.season_id
  const reset = () => { setForm(EMPTY_FORM); setEditingId(null) }

  function submit() {
    if (!form.player_id) { toast.error('Choose a player'); return }
    const payload = {
      player_id: form.player_id,
      season_id: form.season_id || null,
      grade_id: form.season_id ? (form.grade_id || null) : null,
      notes: form.notes || null,
      ...Object.fromEntries(STAT_FIELDS.map(f => [f.key, form[f.key] === '' ? 0 : form[f.key]])),
    }
    onPending({
      title: editingId ? 'Update this adjustment?' : isCareer ? 'Save a career-only adjustment?' : 'Save this adjustment?',
      body: isCareer
        ? 'This lands in the player\'s career totals only — it has no season, so it can never appear on a season leaderboard or a season record. Reversible from Audit & undo.'
        : 'These figures are ADDED to whatever the sync and any import already hold for this player and season. To correct a figure, enter the shortfall, not the final total. Reversible from Audit & undo.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await aflApi.adjustmentsUpdate(editingId, payload)
          else await aflApi.adjustmentsCreate(payload)
          toast.success(editingId ? 'Adjustment updated' : 'Adjustment saved')
          reset()
          refresh()
        } catch (e) { toast.error(e.message) }
      },
    })
  }

  function edit(row) {
    setEditingId(row.id)
    setForm({
      ...EMPTY_FORM,
      ...Object.fromEntries(STAT_FIELDS.map(f => [f.key, row[f.key] ?? 0])),
      player_id: row.player_id,
      season_id: row.season_id || '',
      grade_id: row.grade_id || '',
      notes: row.notes || '',
    })
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function remove(row) {
    onPending({
      title: 'Delete this adjustment?',
      body: `Removes the adjustment for ${row.player_name} (${row.season_name || 'career only'}). `
        + 'This is logged and can be undone from Audit & undo.',
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try {
          await aflApi.adjustmentsDelete(row.id)
          toast.success('Adjustment deleted')
          if (editingId === row.id) reset()
          refresh()
        } catch (e) { toast.error(e.message) }
      },
    })
  }

  return (
    <div className="space-y-4">
      <ImportPanel onImported={refresh} />

      <Spreadsheet players={players} seasons={seasons} grades={grades}
        onSaved={refresh} onPending={onPending}
        onSeasonCreated={onSeasonCreated} onGradeCreated={onGradeCreated} />

      <div className="pb-card p-4 space-y-3" ref={formRef}>
        <h3 className="text-sm font-semibold text-pb-text">
          {editingId ? 'Edit adjustment' : 'New adjustment'}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={LABEL}>Player</label>
            <PlayerPicker players={players} value={form.player_id}
              onChange={id => setForm({ ...form, player_id: id })} />
          </div>
          <div>
            <label className={LABEL}>Season</label>
            <SeasonSelect seasons={seasons} value={form.season_id}
              onChange={id => setForm({ ...form, season_id: id, grade_id: '' })}
              onCreated={onSeasonCreated} />
            {isCareer && (
              <p className="text-[11px] text-pb-faintest mt-1">
                Saves as career-only — career totals see it, season boards never do.
              </p>
            )}
          </div>
          <div>
            <label className={LABEL}>Grade (optional)</label>
            <GradeSelect grades={seasonGrades} seasonId={form.season_id} value={form.grade_id}
              onChange={id => setForm({ ...form, grade_id: id })} onCreated={onGradeCreated} />
            {form.season_id && seasonGrades.length === 0 && (
              <p className="text-[11px] text-pb-faintest mt-1">No grades in this season yet.</p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {STAT_FIELDS.map(f => (
            <NumberField key={f.key} label={f.label} value={form[f.key]}
              onChange={v => setForm({ ...form, [f.key]: v })} />
          ))}
        </div>

        <div>
          <label className={LABEL}>Notes (admins only)</label>
          <input type="text" value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
            placeholder="Where the figures came from — a club record book, a premiership program"
            className={INPUT} />
        </div>

        <div className="flex justify-end gap-2">
          {editingId && <button className={BTN2} onClick={reset}>CANCEL EDIT</button>}
          <button className={BTN} onClick={submit}>{editingId ? 'UPDATE' : 'SAVE ADJUSTMENT'}</button>
        </div>
      </div>

      <div className="pb-card p-4">
        <h3 className="text-sm font-semibold text-pb-text mb-3">Adjustments on file</h3>
        {list === null ? <LoadingSpinner message="Loading adjustments…" /> : list.length === 0 ? (
          <p className="text-[12px] text-pb-dim">Nothing adjusted yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                  <th className="py-2 pr-2">PLAYER</th>
                  <th className="py-2 pr-2">SEASON</th>
                  <th className="py-2 pr-2 text-right">GAMES</th>
                  <th className="py-2 pr-2 text-right">GOALS</th>
                  <th className="py-2 pr-2 text-right">BEHINDS</th>
                  <th className="py-2 pr-2 text-right">BOG</th>
                  <th className="py-2 pr-2 text-right"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="pb-hairline-t align-middle">
                    <td className="py-2 pr-2 text-pb-text">{r.player_name}</td>
                    <td className="py-2 pr-2 text-pb-dim">
                      {r.season_name || <span className="text-pb-faint">Career only</span>}
                      {r.grade_name && <span className="text-pb-faint"> · {r.grade_name}</span>}
                    </td>
                    <td className="py-2 pr-2 text-right font-mono text-[11px]">{r.games_played}</td>
                    <td className="py-2 pr-2 text-right font-mono text-[11px]">{r.goals}</td>
                    <td className="py-2 pr-2 text-right font-mono text-[11px]">{r.behinds}</td>
                    <td className="py-2 pr-2 text-right font-mono text-[11px]">{r.bog_count}</td>
                    <td className="py-2 pr-2 text-right whitespace-nowrap">
                      <button className={BTN_LINK + ' mr-3'} onClick={() => edit(r)}>Edit</button>
                      <button className="font-mono text-[10px] text-pb-red/70 hover:text-pb-red underline"
                        onClick={() => remove(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function AuditTab({ onPending }) {
  const toast = useToast()
  const [list, setList] = useState(null)

  const refresh = useCallback(() => aflApi.manualAudit()
    .then(setList).catch(e => toast.error(e.message)), [toast])
  useEffect(() => { refresh() }, [refresh])

  function undo(row) {
    onPending({
      title: 'Undo this change?',
      body: `${row.summary}\n\nThe earlier state is put back and this entry is marked undone.`,
      confirmLabel: 'Undo',
      danger: true,
      action: async () => {
        try {
          await aflApi.manualUndo(row.id)
          toast.success('Change undone')
          refresh()
        } catch (e) { toast.error(e.message) }
      },
    })
  }

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-pb-text">Manual entry audit log</h3>
        <button className={BTN2} onClick={refresh}>REFRESH</button>
      </div>
      {list === null ? <LoadingSpinner message="Loading the log…" /> : list.length === 0 ? (
        <p className="text-[12px] text-pb-dim">No manual edits yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left">
                <th className="py-2 pr-2">WHEN</th>
                <th className="py-2 pr-2">BY</th>
                <th className="py-2 pr-2">ACTION</th>
                <th className="py-2 pr-2">SUMMARY</th>
                <th className="py-2 pr-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {list.map(r => (
                <tr key={r.id} className="pb-hairline-t align-middle">
                  <td className="py-2 pr-2 font-mono text-[11px] text-pb-faint whitespace-nowrap">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-2 pr-2 text-pb-dim">{r.user_name || '—'}</td>
                  <td className="py-2 pr-2 font-mono text-[10px] uppercase text-pb-faint">{r.action}</td>
                  <td className="py-2 pr-2 text-pb-text">{r.summary}</td>
                  <td className="py-2 pr-2 text-right whitespace-nowrap">
                    {r.undone_at
                      ? <span className="font-mono text-[10px] text-pb-faint">undone</span>
                      : (
                        <button className="font-mono text-[10px] text-pb-red/70 hover:text-pb-red underline"
                          onClick={() => undo(r)}>Undo</button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function AflAdminManualEntries() {
  const toast = useToast()
  const [tab, setTab] = useState(() => {
    const hash = window.location.hash.replace('#', '')
    return TABS.some(t => t.key === hash) ? hash : 'adjustments'
  })
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState([])
  const [grades, setGrades] = useState([])
  const [pending, setPending] = useState(null)

  useEffect(() => {
    Promise.all([aflApi.adminListPlayers(), aflApi.importsSeasons(), aflApi.manualGrades()])
      .then(([p, s, g]) => { setPlayers(p || []); setSeasons(s || []); setGrades(g || []) })
      .catch(e => toast.error(e.message))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { window.location.hash = tab }, [tab])

  // Added in place rather than by re-fetching: a season or grade is created
  // from inside a form somebody is halfway through filling in, and reloading
  // the lists must not disturb it.
  const onSeasonCreated = useCallback(s => setSeasons(prev => [...prev, s]), [])
  const onGradeCreated = useCallback(g => setGrades(prev => [...prev, g]), [])

  async function confirmPending() {
    const action = pending?.action
    setPending(null)
    if (action) await action()
  }

  return (
    <div className="space-y-4 max-w-5xl">
      <SectionTitle>Manual stat entries</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl -mt-2">
        Add or correct a player's totals where PlayHQ and your imports fall short — an
        old premiership season, a goal tally the feed got wrong, a career that predates
        anything online. What you enter is ADDED to what's already held, every change is
        logged, and the sync never touches it.
      </p>

      <div className="flex flex-wrap gap-x-5 pb-hairline-b">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`pb-2 -mb-px text-sm font-semibold border-b-2 transition-colors ${
              tab === t.key
                ? 'border-[var(--pb-accent)] text-pb-text'
                : 'border-transparent text-pb-faint hover:text-pb-text'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'adjustments' && (
        <AdjustmentsTab players={players} seasons={seasons} grades={grades}
          onPending={setPending}
          onSeasonCreated={onSeasonCreated} onGradeCreated={onGradeCreated} />
      )}
      {tab === 'audit' && <AuditTab onPending={setPending} />}

      <Confirm
        open={!!pending}
        title={pending?.title || 'Confirm'}
        body={pending?.body || ''}
        confirmLabel={pending?.confirmLabel || 'Confirm'}
        danger={pending?.danger}
        onConfirm={confirmPending}
        onCancel={() => setPending(null)}
      />
    </div>
  )
}
