import { useState, useEffect, useRef, useMemo, Fragment } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'

const EMPTY_FORM = {
  batter1_name: '',
  batter1_id: '',
  batter2_name: '',
  batter2_id: '',
  grade_name: '',
  season_year: new Date().getFullYear(),
  wicket_number: 1,
  runs: '',
  is_not_out: false,
  notes: '',
}

function PlayerSearch({ label, name, playerId, onSelect, players }) {
  const [query, setQuery] = useState(name)
  const [open, setOpen] = useState(false)

  const filtered = query.length >= 2
    ? players.filter(p => p.display_name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  const handleSelect = (p) => {
    setQuery(p.display_name)
    setOpen(false)
    onSelect({ name: p.display_name, id: p.id })
  }

  const handleChange = (e) => {
    setQuery(e.target.value)
    setOpen(true)
    onSelect({ name: e.target.value, id: '' })
  }

  return (
    <div className="relative">
      <label className="font-mono text-[10px] text-pb-faint block mb-1">{label}</label>
      <input
        type="text"
        value={query}
        onChange={handleChange}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search player…"
        className={INPUT_CLS}
      />
      {playerId && <p className="font-mono text-[10px] text-pb-faintest mt-0.5 truncate">{playerId}</p>}
      {open && filtered.length > 0 && (
        <div className="absolute z-10 w-full bg-pb-surface border pb-hairline rounded mt-1 shadow-lg">
          {filtered.map(p => (
            <button
              key={p.id}
              type="button"
              onMouseDown={() => handleSelect(p)}
              className="w-full text-left px-3 py-2 text-sm text-pb-text hover:bg-pb-surface2"
            >
              {p.display_name}
              {p.playhq_id && <span className="ml-2 font-mono text-[10px] text-pb-faintest">PHQ: {p.playhq_id}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ImportPanel({ onImported }) {
  const fileRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState(null)

  const handleDownloadTemplate = async () => {
    const res = await api.adminDownloadPartnershipTemplate()
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'partnership_records_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setError(null)
    try {
      const result = await api.adminImportPartnershipRecords(file)
      if (result.detail) throw new Error(result.detail)
      onImported(result)
    } catch (err) {
      setError(err.message || 'Import failed')
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="pb-card p-5 mb-4">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Bulk Import</p>
      <p className="font-mono text-[10px] text-pb-faint mb-4 leading-relaxed">
        Download the CSV template, fill in partnership records, then upload. Player names are matched automatically and potential GR duplicates are flagged for review.
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <button
          onClick={handleDownloadTemplate}
          className="border pb-hairline text-pb-faint hover:text-pb-text px-4 py-2 rounded font-mono text-[10px] tracking-wide2 transition-colors flex items-center gap-2"
        >
          ⬇ Download Template (.csv)
        </button>
        <label className={`px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition cursor-pointer flex items-center gap-2 text-pb-bg${importing ? ' opacity-50 pointer-events-none' : ''}`}
          style={{ background: 'var(--pb-accent)' }}
        >
          ⬆ {importing ? 'Importing…' : 'Upload File (.xlsx / .csv)'}
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={handleFileChange} />
        </label>
      </div>
      {error && <p className="mt-3 font-mono text-[11px] text-pb-red">{error}</p>}
    </div>
  )
}

function GradeMatchPanel({ records, onRecordsRenamed }) {
  const [open, setOpen] = useState(false)
  const [syncedGrades, setSyncedGrades] = useState([])
  const [loading, setLoading] = useState(false)
  const [renames, setRenames] = useState({})
  const [saving, setSaving] = useState(null)
  const [msg, setMsg] = useState('')

  const uniqueGrades = useMemo(
    () => [...new Set(records.map(r => r.grade_name))].sort(),
    [records],
  )
  const syncedSet = useMemo(() => new Set(syncedGrades), [syncedGrades])
  const mismatchCount = useMemo(
    () => uniqueGrades.filter(g => !syncedSet.has(g)).length,
    [uniqueGrades, syncedSet],
  )

  const handleToggle = async () => {
    if (!open && syncedGrades.length === 0) {
      setLoading(true)
      const grades = await api.adminListGrades().catch(() => [])
      setSyncedGrades(grades)
      setLoading(false)
    }
    setOpen(o => !o)
  }

  const handleApply = async (oldName) => {
    const newName = renames[oldName]?.trim()
    if (!newName || newName === oldName) return
    setSaving(oldName)
    setMsg('')
    try {
      const res = await api.adminRenamePartnershipGrade(oldName, newName)
      onRecordsRenamed(oldName, newName)
      setRenames(r => { const n = { ...r }; delete n[oldName]; return n })
      setMsg(`"${oldName}" → "${newName}" (${res.updated} record${res.updated !== 1 ? 's' : ''} updated)`)
      setTimeout(() => setMsg(''), 4000)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="pb-card mb-4">
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-pb-text">Grade Match</span>
          {records.length > 0 && syncedGrades.length > 0 && mismatchCount > 0 && (
            <span className="font-mono text-[10px] text-pb-amber">{mismatchCount} unmatched</span>
          )}
          {records.length > 0 && syncedGrades.length > 0 && mismatchCount === 0 && (
            <span className="font-mono text-[10px]" style={{ color: 'var(--pb-accent)' }}>All matched</span>
          )}
          {records.length === 0 && (
            <span className="font-mono text-[10px] text-pb-faintest">No records</span>
          )}
        </div>
        <span className="text-pb-faint text-sm">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="pb-hairline-t px-5 pb-5 pt-4">
          <p className="font-mono text-[10px] text-pb-faint mb-4 leading-relaxed">
            Match grade names in manual records to the synced grade names from your club's data.
          </p>
          {loading && <p className="font-mono text-[11px] text-pb-faint">Loading synced grades…</p>}
          {!loading && uniqueGrades.length === 0 && (
            <p className="font-mono text-[11px] text-pb-faint">No manual records yet.</p>
          )}
          {!loading && uniqueGrades.length > 0 && (
            <>
              <datalist id="synced-grades-list">
                {syncedGrades.map(g => <option key={g} value={g} />)}
              </datalist>
              <div className="space-y-3">
                {uniqueGrades.map(gradeName => {
                  const isMatched = syncedSet.has(gradeName)
                  const count = records.filter(r => r.grade_name === gradeName).length
                  return (
                    <div key={gradeName} className="flex items-center gap-3 flex-wrap">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-sm shrink-0 ${isMatched ? 'text-pb-accent' : 'text-pb-amber'}`}
                          style={isMatched ? { color: 'var(--pb-accent)' } : {}}
                        >
                          {isMatched ? '✓' : '⚠'}
                        </span>
                        <span className="text-pb-text text-sm">{gradeName}</span>
                        <span className="font-mono text-[10px] text-pb-faintest shrink-0">
                          {count} record{count !== 1 ? 's' : ''}
                        </span>
                      </div>
                      {!isMatched && (
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-pb-faintest text-xs">→</span>
                          <input
                            type="text"
                            value={renames[gradeName] || ''}
                            onChange={e => setRenames(r => ({ ...r, [gradeName]: e.target.value }))}
                            list="synced-grades-list"
                            placeholder="Pick or type new name…"
                            className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs w-48 focus:outline-none focus:border-pb-accent"
                          />
                          <button
                            onClick={() => handleApply(gradeName)}
                            disabled={!renames[gradeName]?.trim() || renames[gradeName]?.trim() === gradeName || saving === gradeName}
                            className="px-3 py-1 rounded font-mono text-[10px] font-semibold transition disabled:opacity-40 text-pb-bg"
                            style={{ background: 'var(--pb-accent)' }}
                          >
                            {saving === gradeName ? 'Saving…' : 'Apply'}
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}
          {msg && <p className="mt-3 font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</p>}
        </div>
      )}
    </div>
  )
}

function ImportWizard({ result, players, onClose, onRecordDeleted }) {
  const { created, skipped, errors, records } = result

  const needsAttention = records.filter(r => r.batter1_unmatched || r.batter2_unmatched || r.gr_duplicate)
  const clean = records.filter(r => !r.batter1_unmatched && !r.batter2_unmatched && !r.gr_duplicate)

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-8 px-4 overflow-y-auto">
      <div className="bg-pb-surface border pb-hairline rounded-xl w-full max-w-3xl mb-8">
        <div className="flex items-center justify-between px-5 py-4 pb-hairline-b">
          <div>
            <h2 className="text-pb-text font-semibold">Import Complete — Review Results</h2>
            <p className="font-mono text-[10px] text-pb-faint mt-0.5">
              {created} record{created !== 1 ? 's' : ''} imported
              {skipped > 0 ? `, ${skipped} skipped` : ''}
            </p>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text text-xl leading-none">×</button>
        </div>

        {errors?.length > 0 && (
          <div className="px-5 py-3 pb-hairline-b space-y-1">
            {errors.map((e, i) => <p key={i} className="font-mono text-[11px] text-pb-red">{e}</p>)}
          </div>
        )}

        {needsAttention.length === 0 && (
          <div className="px-5 py-6 text-center font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>
            All {created} records imported cleanly — no issues to review.
          </div>
        )}

        {needsAttention.length > 0 && (
          <div className="px-5 py-4">
            <p className="font-mono text-[10px] text-pb-amber mb-3">
              {needsAttention.length} record{needsAttention.length !== 1 ? 's need' : ' needs'} attention
            </p>
            <div className="space-y-3">
              {needsAttention.map(r => (
                <WizardRow
                  key={r.id}
                  record={r}
                  players={players}
                  onDeleted={() => onRecordDeleted(r.id)}
                />
              ))}
            </div>
          </div>
        )}

        {clean.length > 0 && needsAttention.length > 0 && (
          <div className="px-5 pb-4">
            <p className="font-mono text-[10px] text-pb-faintest">{clean.length} other record{clean.length !== 1 ? 's' : ''} imported without issues.</p>
          </div>
        )}

        <div className="px-5 py-4 pb-hairline-t flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}

function WizardRow({ record, players, onDeleted }) {
  const [deleted, setDeleted] = useState(false)
  const [b1Id, setB1Id] = useState(record.batter1_id || '')
  const [b2Id, setB2Id] = useState(record.batter2_id || '')
  const [linking, setLinking] = useState(false)
  const [linked, setLinked] = useState(false)

  if (deleted) return null

  const handleDelete = async () => {
    await api.adminDeletePartnershipRecord(record.id)
    setDeleted(true)
    onDeleted()
  }

  const handleLink = async () => {
    setLinking(true)
    const patch = {}
    if (record.batter1_unmatched && b1Id) patch.batter1_id = b1Id
    if (record.batter2_unmatched && b2Id) patch.batter2_id = b2Id
    await api.adminPatchPartnershipRecord(record.id, patch)
    setLinking(false)
    setLinked(true)
  }

  const canLink = (record.batter1_unmatched && b1Id) || (record.batter2_unmatched && b2Id)

  return (
    <div className="pb-card p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-pb-text text-sm font-medium">
            {record.batter1_name} <span className="text-pb-faintest">&amp;</span> {record.batter2_name}
            <span className="ml-2 font-mono text-[10px] text-pb-faintest font-normal">
              {record.runs}{record.is_not_out ? '*' : ''} — {ORDINALS[record.wicket_number - 1]} wkt — {record.grade_name} {record.season_year}
            </span>
          </p>

          {record.gr_duplicate && (
            <div className="mt-2 flex items-center gap-3 p-2 bg-pb-amber/10 border border-pb-amber/30 rounded text-xs">
              <span className="text-pb-amber font-medium shrink-0">⚠ GR duplicate found</span>
              <span className="text-pb-dim">
                This partnership ({record.gr_duplicate.runs} runs, {ORDINALS[(record.gr_duplicate.wicket_number || 1) - 1]} wkt, {record.gr_duplicate.season_year}) already exists in game data.
              </span>
              <button
                onClick={handleDelete}
                className="shrink-0 font-mono text-[10px] text-pb-red hover:opacity-80 border border-pb-red/30 rounded px-2 py-1"
              >
                Delete this record
              </button>
            </div>
          )}

          {(record.batter1_unmatched || record.batter2_unmatched) && !linked && (
            <div className="mt-2 space-y-2">
              {record.batter1_unmatched && (
                <UnmatchedPlayerRow
                  label={`Batter 1: "${record.batter1_name}" not matched`}
                  players={players}
                  value={b1Id}
                  onChange={setB1Id}
                />
              )}
              {record.batter2_unmatched && (
                <UnmatchedPlayerRow
                  label={`Batter 2: "${record.batter2_name}" not matched`}
                  players={players}
                  value={b2Id}
                  onChange={setB2Id}
                />
              )}
              {canLink && (
                <button
                  onClick={handleLink}
                  disabled={linking}
                  className="font-mono text-[10px] px-3 py-1 rounded font-semibold transition text-pb-bg mt-1"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  {linking ? 'Linking…' : 'Link Player'}
                </button>
              )}
            </div>
          )}
          {linked && <p className="mt-1 font-mono text-[10px]" style={{ color: 'var(--pb-accent)' }}>Player linked successfully.</p>}
        </div>
      </div>
    </div>
  )
}

function UnmatchedPlayerRow({ label, players, value, onChange }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)

  const filtered = query.length >= 2
    ? players.filter(p => p.display_name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  const handleSelect = (p) => {
    setQuery(p.display_name)
    setOpen(false)
    onChange(p.id)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] text-pb-amber shrink-0">{label}</span>
      <div className="relative flex-1 max-w-xs">
        <input
          type="text"
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); if (!e.target.value) onChange('') }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Link to player…"
          className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-xs focus:outline-none focus:border-pb-accent"
        />
        {open && filtered.length > 0 && (
          <div className="absolute z-20 w-full bg-pb-surface border pb-hairline rounded mt-1 shadow-lg max-h-40 overflow-y-auto">
            {filtered.map(p => (
              <button
                key={p.id}
                type="button"
                onMouseDown={() => handleSelect(p)}
                className="w-full text-left px-2 py-1.5 text-xs text-pb-text hover:bg-pb-surface2"
              >
                {p.display_name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EditRow({ record, players, syncedGrades, onSaved, onCancel }) {
  const [form, setForm] = useState({
    batter1_name: record.batter1_name,
    batter1_id: record.batter1_id || '',
    batter2_name: record.batter2_name,
    batter2_id: record.batter2_id || '',
    runs: record.runs,
    wicket_number: record.wicket_number,
    season_year: record.season_year,
    is_not_out: record.is_not_out,
    grade_name: record.grade_name,
    notes: record.notes || '',
  })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    if (!form.batter1_name || !form.batter2_name || !form.grade_name) {
      setErr('Batter names and grade are required')
      return
    }
    setSaving(true)
    setErr('')
    try {
      await api.adminPatchPartnershipRecord(record.id, {
        batter1_id: form.batter1_id || null,
        batter1_name: form.batter1_name,
        batter2_id: form.batter2_id || null,
        batter2_name: form.batter2_name,
        grade_name: form.grade_name,
        season_year: Number(form.season_year),
        wicket_number: Number(form.wicket_number),
        runs: Number(form.runs),
        is_not_out: form.is_not_out,
        notes: form.notes || null,
      })
      onSaved({
        ...record,
        batter1_name: form.batter1_name,
        batter1_id: form.batter1_id || null,
        batter2_name: form.batter2_name,
        batter2_id: form.batter2_id || null,
        grade_name: form.grade_name,
        season_year: Number(form.season_year),
        wicket_number: Number(form.wicket_number),
        runs: Number(form.runs),
        is_not_out: form.is_not_out,
        notes: form.notes || null,
      })
    } catch (e) {
      setErr(e.message)
      setSaving(false)
    }
  }

  return (
    <tr className="bg-pb-surface2/30">
      <td colSpan={6} className="px-5 py-4 pb-hairline-t">
        <div className="space-y-3 max-w-2xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <PlayerSearch
              label="Batter 1"
              name={form.batter1_name}
              playerId={form.batter1_id}
              players={players}
              onSelect={({ name, id }) => setForm(f => ({ ...f, batter1_name: name, batter1_id: id }))}
            />
            <PlayerSearch
              label="Batter 2"
              name={form.batter2_name}
              playerId={form.batter2_id}
              players={players}
              onSelect={({ name, id }) => setForm(f => ({ ...f, batter2_name: name, batter2_id: id }))}
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Runs</label>
              <input type="number" min="0" value={form.runs} onChange={e => setField('runs', e.target.value)}
                className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Wicket</label>
              <select value={form.wicket_number} onChange={e => setField('wicket_number', Number(e.target.value))}
                className={INPUT_CLS}>
                {ORDINALS.map((o, i) => <option key={i + 1} value={i + 1}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Year</label>
              <input type="number" min="1900" max="2100" value={form.season_year} onChange={e => setField('season_year', e.target.value)}
                className={INPUT_CLS} />
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Grade</label>
              <input type="text" value={form.grade_name} onChange={e => setField('grade_name', e.target.value)}
                list="edit-row-grades"
                className={INPUT_CLS} />
              <datalist id="edit-row-grades">
                {syncedGrades.map(g => <option key={g} value={g} />)}
              </datalist>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.is_not_out} onChange={e => setField('is_not_out', e.target.checked)}
                  className="w-4 h-4 rounded" />
                <span className="text-sm text-pb-faint">Not Out</span>
              </label>
            </div>
          </div>
          <div>
            <label className="font-mono text-[10px] text-pb-faint block mb-1">Notes</label>
            <input type="text" value={form.notes} onChange={e => setField('notes', e.target.value)}
              className={INPUT_CLS} />
          </div>
          {err && <p className="font-mono text-[11px] text-pb-red">{err}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
            <button
              onClick={onCancel}
              className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </td>
    </tr>
  )
}

export default function AdminPartnershipRecords() {
  const [records, setRecords] = useState([])
  const [players, setPlayers] = useState([])
  const [syncedGrades, setSyncedGrades] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [importResult, setImportResult] = useState(null)

  const loadRecords = () => {
    api.adminListPartnershipRecords().then(setRecords).catch(() => {})
  }

  useEffect(() => {
    loadRecords()
    api.adminListPlayers().then(setPlayers).catch(() => {})
    api.adminListGrades().then(setSyncedGrades).catch(() => {})
  }, [])

  const setField = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.batter1_name || !form.batter2_name || !form.runs || !form.grade_name) {
      setMsg('Fill in all required fields')
      return
    }
    setSaving(true)
    try {
      await api.adminCreatePartnershipRecord({
        batter1_id: form.batter1_id || null,
        batter1_name: form.batter1_name,
        batter2_id: form.batter2_id || null,
        batter2_name: form.batter2_name,
        grade_name: form.grade_name,
        season_year: Number(form.season_year),
        wicket_number: Number(form.wicket_number),
        runs: Number(form.runs),
        is_not_out: form.is_not_out,
        notes: form.notes || null,
      })
      loadRecords()
      setForm(EMPTY_FORM)
      setShowForm(false)
      setMsg('Saved')
      setTimeout(() => setMsg(''), 2500)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this partnership record?')) return
    try {
      await api.adminDeletePartnershipRecord(id)
      setRecords(rs => rs.filter(r => r.id !== id))
    } catch (err) {
      setMsg(err.message)
    }
  }

  const handleImported = (result) => {
    loadRecords()
    setImportResult(result)
  }

  const handleRecordsRenamed = (oldName, newName) => {
    setRecords(rs => rs.map(r => r.grade_name === oldName ? { ...r, grade_name: newName } : r))
  }

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="font-display font-bold text-2xl text-pb-text">Partnership Records</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <button
              onClick={() => { setShowForm(s => !s); setEditingId(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showForm ? 'CANCEL' : '+ ADD RECORD'}
            </button>
          </div>
        </div>

        <p className="font-mono text-[10px] text-pb-faint mb-5 leading-relaxed">
          Manually add historical partnership records that predate PlayHQ sync. These appear in the Records board alongside auto-synced data.
        </p>

        <ImportPanel onImported={handleImported} />
        <GradeMatchPanel records={records} onRecordsRenamed={handleRecordsRenamed} />

        {showForm && (
          <form onSubmit={handleSubmit} className="pb-card p-5 mb-6 space-y-4">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">New Partnership Record</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <PlayerSearch
                label="Batter 1 *"
                name={form.batter1_name}
                playerId={form.batter1_id}
                players={players}
                onSelect={({ name, id }) => setForm(f => ({ ...f, batter1_name: name, batter1_id: id }))}
              />
              <PlayerSearch
                label="Batter 2 *"
                name={form.batter2_name}
                playerId={form.batter2_id}
                players={players}
                onSelect={({ name, id }) => setForm(f => ({ ...f, batter2_name: name, batter2_id: id }))}
              />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Runs *</label>
                <input type="number" min="0" value={form.runs}
                  onChange={e => setField('runs', e.target.value)}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Wicket</label>
                <select value={form.wicket_number}
                  onChange={e => setField('wicket_number', e.target.value)}
                  className={INPUT_CLS}>
                  {ORDINALS.map((o, i) => <option key={i + 1} value={i + 1}>{o}</option>)}
                </select>
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Year *</label>
                <input type="number" min="1900" max="2100" value={form.season_year}
                  onChange={e => setField('season_year', e.target.value)}
                  className={INPUT_CLS} />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={form.is_not_out}
                    onChange={e => setField('is_not_out', e.target.checked)}
                    className="w-4 h-4 rounded" />
                  <span className="text-sm text-pb-faint">Not Out</span>
                </label>
              </div>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Grade *</label>
              <input type="text" value={form.grade_name}
                onChange={e => setField('grade_name', e.target.value)}
                list="add-form-grades"
                placeholder="e.g. 1st XI, C Grade, T20"
                className={INPUT_CLS} />
              <datalist id="add-form-grades">
                {syncedGrades.map(g => <option key={g} value={g} />)}
              </datalist>
            </div>
            <div>
              <label className="font-mono text-[10px] text-pb-faint block mb-1">Notes (optional)</label>
              <input type="text" value={form.notes}
                onChange={e => setField('notes', e.target.value)}
                placeholder="vs Opponent, ground, etc."
                className={INPUT_CLS} />
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={saving}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                {saving ? 'Saving…' : 'SAVE RECORD'}
              </button>
              <button type="button" onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        <div className="pb-card overflow-hidden">
          {records.length === 0 && (
            <div className="px-5 py-8 text-center font-mono text-[11px] text-pb-faint">No manual records yet</div>
          )}
          {records.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint bg-pb-surface2/40">
                  <th className="font-medium py-2.5 pl-5 text-left">BATTERS</th>
                  <th className="font-medium py-2.5 px-3 text-right">RUNS</th>
                  <th className="font-medium py-2.5 px-3 text-right">WKT</th>
                  <th className="font-medium py-2.5 px-3 text-left">GRADE</th>
                  <th className="font-medium py-2.5 px-3 text-right">YEAR</th>
                  <th className="font-medium py-2.5 pr-5"></th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <Fragment key={r.id}>
                    <tr className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 align-top`}>
                      <td className="py-2.5 pl-5 text-pb-text">
                        {r.batter1_name} <span className="text-pb-faintest">&amp;</span> {r.batter2_name}
                        {r.notes && <span className="block font-mono text-[10px] text-pb-faintest">{r.notes}</span>}
                      </td>
                      <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>
                        {r.runs}{r.is_not_out ? '*' : ''}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-sm text-pb-faint text-right">
                        {ORDINALS[r.wicket_number - 1] || r.wicket_number}
                      </td>
                      <td className="py-2.5 px-3 text-pb-faint">{r.grade_name}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faintest text-right">{r.season_year}</td>
                      <td className="py-2.5 pr-5 text-right">
                        <div className="flex items-center justify-end gap-3">
                          <button
                            onClick={() => setEditingId(id => id === r.id ? null : r.id)}
                            className="font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
                          >
                            {editingId === r.id ? 'Cancel' : 'Edit'}
                          </button>
                          <button
                            onClick={() => handleDelete(r.id)}
                            className="font-mono text-[10px] text-pb-faint hover:text-pb-red transition-colors"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                    {editingId === r.id && (
                      <EditRow
                        record={r}
                        players={players}
                        syncedGrades={syncedGrades}
                        onSaved={(updated) => {
                          setRecords(rs => rs.map(x => x.id === r.id ? updated : x))
                          setEditingId(null)
                        }}
                        onCancel={() => setEditingId(null)}
                      />
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {importResult && (
        <ImportWizard
          result={importResult}
          players={players}
          onClose={() => setImportResult(null)}
          onRecordDeleted={(id) => {
            setRecords(rs => rs.filter(r => r.id !== id))
            setImportResult(prev => ({
              ...prev,
              records: prev.records.filter(r => r.id !== id),
              created: prev.created - 1,
            }))
          }}
        />
      )}
    </AdminLayout>
  )
}
