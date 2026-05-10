import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

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
      <label className="block text-xs text-slate-500 mb-1">{label}</label>
      <input
        type="text"
        value={query}
        onChange={handleChange}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search player…"
        className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
      />
      {playerId && <p className="text-xs text-slate-600 mt-0.5 font-mono truncate">{playerId}</p>}
      {open && filtered.length > 0 && (
        <div className="absolute z-10 w-full bg-navy-800 border border-navy-600 rounded mt-1 shadow-lg">
          {filtered.map(p => (
            <button
              key={p.id}
              type="button"
              onMouseDown={() => handleSelect(p)}
              className="w-full text-left px-3 py-2 text-sm text-white hover:bg-navy-700"
            >
              {p.display_name}
              {p.playhq_id && <span className="ml-2 text-xs text-slate-600">PHQ: {p.playhq_id}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminPartnershipRecords() {
  const [records, setRecords] = useState([])
  const [players, setPlayers] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    api.adminListPartnershipRecords().then(setRecords).catch(() => {})
    api.adminListPlayers().then(setPlayers).catch(() => {})
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
      const updated = await api.adminListPartnershipRecords()
      setRecords(updated)
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

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-display font-bold text-white">Partnership Records</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="text-sm text-accent">{msg}</span>}
            <button onClick={() => setShowForm(s => !s)} className="btn-primary text-sm">
              {showForm ? 'Cancel' : '+ Add Record'}
            </button>
          </div>
        </div>

        <p className="text-slate-500 text-xs mb-4">
          Manually add historical partnership records that predate PlayHQ sync. These appear in the Records board alongside auto-synced data.
        </p>

        {showForm && (
          <form onSubmit={handleSubmit} className="bg-navy-900 border border-navy-700 rounded-lg p-5 mb-6 space-y-4">
            <h2 className="text-sm font-medium text-white">New Partnership Record</h2>
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
                <label className="block text-xs text-slate-500 mb-1">Runs *</label>
                <input
                  type="number" min="0"
                  value={form.runs}
                  onChange={e => setField('runs', e.target.value)}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Wicket</label>
                <select
                  value={form.wicket_number}
                  onChange={e => setField('wicket_number', e.target.value)}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
                >
                  {ORDINALS.map((o, i) => <option key={i+1} value={i+1}>{o}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Year *</label>
                <input
                  type="number" min="1900" max="2100"
                  value={form.season_year}
                  onChange={e => setField('season_year', e.target.value)}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_not_out}
                    onChange={e => setField('is_not_out', e.target.checked)}
                    className="w-4 h-4 rounded border-navy-600 bg-navy-800 text-accent focus:ring-accent"
                  />
                  <span className="text-sm text-slate-400">Not Out</span>
                </label>
              </div>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Grade *</label>
              <input
                type="text"
                value={form.grade_name}
                onChange={e => setField('grade_name', e.target.value)}
                placeholder="e.g. 1st XI, C Grade, T20"
                className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Notes (optional)</label>
              <input
                type="text"
                value={form.notes}
                onChange={e => setField('notes', e.target.value)}
                placeholder="vs Opponent, ground, etc."
                className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
              />
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={saving} className="btn-primary text-sm">
                {saving ? 'Saving…' : 'Save Record'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-ghost text-sm">Cancel</button>
            </div>
          </form>
        )}

        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          {records.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">No manual records yet</div>
          )}
          {records.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-navy-700">
                  <th className="table-header">Batters</th>
                  <th className="table-header text-right">Runs</th>
                  <th className="table-header text-right">Wkt</th>
                  <th className="table-header">Grade</th>
                  <th className="table-header text-right">Year</th>
                  <th className="table-header"></th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.id} className={`table-row ${i > 0 ? 'border-t border-navy-800' : ''}`}>
                    <td className="table-cell text-white">
                      {r.batter1_name} <span className="text-slate-600">&amp;</span> {r.batter2_name}
                      {r.notes && <span className="block text-xs text-slate-600">{r.notes}</span>}
                    </td>
                    <td className="table-cell stat-number text-right text-accent font-bold">
                      {r.runs}{r.is_not_out ? '*' : ''}
                    </td>
                    <td className="table-cell stat-number text-right text-slate-400">
                      {ORDINALS[r.wicket_number - 1] || r.wicket_number}
                    </td>
                    <td className="table-cell text-slate-400">{r.grade_name}</td>
                    <td className="table-cell stat-number text-right text-slate-500">{r.season_year}</td>
                    <td className="table-cell text-right">
                      <button onClick={() => handleDelete(r.id)} className="text-slate-600 hover:text-red-400 text-xs">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AdminLayout>
  )
}
