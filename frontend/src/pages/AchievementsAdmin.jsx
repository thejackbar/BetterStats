import { useParams } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

const CATEGORY_ICONS = {
  'Club Award': '🏆',
  'Association Award': '🥇',
  'Office Bearer': '👔',
  'Premiership': '🏸',
  'Hall of Fame': '⭐',
  'Life Membership': '🎖',
  'Milestone': '📍',
}

const BASE = import.meta.env.VITE_API_URL || '/api'

// ─── Import panel ───────────────────────────────────────────────────────────────────────

function ImportPanel({ orgId, onImported }) {
  const fileRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleDownloadTemplate = async () => {
    const token = localStorage.getItem('bs_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`${BASE}/achievements/template`, { headers })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'achievements_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setResult(null)
    setError(null)
    try {
      const res = await api.importAchievements(orgId, file)
      setResult(res)
      onImported()
    } catch (err) {
      setError(err.message || 'Import failed')
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="card p-5 mb-6">
      <h2 className="display-heading text-lg text-white mb-4">BULK IMPORT</h2>
      <p className="text-slate-400 text-sm mb-4">
        Download the template, fill in achievements using the column format, then upload. Player names are matched automatically.
        The template includes dropdown validation for the Category column.
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <button onClick={handleDownloadTemplate} className="btn-ghost border border-navy-600 text-sm flex items-center gap-2">
          <span>⬇</span> Download Template (.xlsx)
        </button>
        <label className={clsx('btn-primary text-sm cursor-pointer flex items-center gap-2', importing && 'opacity-50 pointer-events-none')}>
          <span>⬆</span> {importing ? 'Importing…' : 'Upload File (.xlsx / .csv)'}
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={handleImport} />
        </label>
      </div>

      {result && (
        <div className="mt-4 p-4 bg-navy-800 rounded-lg border border-navy-600 text-sm space-y-1">
          <p className="text-green-400 font-semibold">✓ Import complete — {result.created} achievements added</p>
          {result.skipped > 0 && <p className="text-slate-400">Skipped: {result.skipped} rows (empty or invalid)</p>}
          {result.errors?.length > 0 && (
            <div className="text-red-400">
              {result.errors.map((e, i) => <p key={i}>{e}</p>)}
            </div>
          )}
          {result.unmatched_players?.length > 0 && (
            <div>
              <p className="text-yellow-400 font-medium mt-2">⚠ Player names not matched to profiles ({result.unmatched_players.length}):</p>
              <p className="text-slate-400 text-xs mt-1">Achievements still saved — they can be linked manually from the player's profile.</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {result.unmatched_players.map(n => (
                  <span key={n} className="text-xs bg-navy-700 text-yellow-300 px-2 py-0.5 rounded">{n}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-red-400 text-sm">{error}</p>}
    </div>
  )
}

// ─── Add/edit form ────────────────────────────────────────────────────────────────────────────

function AchievementForm({ orgId, initial, onSave, onCancel }) {
  const [form, setForm] = useState(initial || { season: '', category: 'Club Award', subcategory: '', achievement: '', player_name: '', detail: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleSave = async () => {
    if (!form.achievement.trim() || !form.player_name.trim()) {
      setError('Player Name and Achievement are required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (initial?.id) {
        await api.updateAchievement(initial.id, form)
      } else {
        await api.createAchievement({ ...form, org_id: orgId })
      }
      onSave()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-navy-800/60 border border-navy-600 rounded-xl p-5 mb-4">
      <h3 className="text-sm font-semibold text-white mb-3">{initial?.id ? 'Edit Achievement' : 'Add Achievement'}</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label className="section-label mb-1 block">Player Name *</label>
          <input
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
            placeholder="Full name"
            value={form.player_name}
            onChange={e => setForm(f => ({ ...f, player_name: e.target.value }))}
          />
        </div>
        <div>
          <label className="section-label mb-1 block">Season</label>
          <input
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
            placeholder="e.g. 2025_26"
            value={form.season}
            onChange={e => setForm(f => ({ ...f, season: e.target.value }))}
          />
        </div>
        <div>
          <label className="section-label mb-1 block">Category *</label>
          <select
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
            value={form.category}
            onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
          >
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="section-label mb-1 block">Subcategory / Grade</label>
          <input
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
            placeholder="e.g. 1st XI, WASTCA, Executive Committee"
            value={form.subcategory}
            onChange={e => setForm(f => ({ ...f, subcategory: e.target.value }))}
          />
        </div>
        <div>
          <label className="section-label mb-1 block">Achievement *</label>
          <input
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
            placeholder="e.g. Best & Fairest, President, Premiership"
            value={form.achievement}
            onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))}
          />
        </div>
        <div>
          <label className="section-label mb-1 block">Detail</label>
          <input
            className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
            placeholder="e.g. 436 runs at 39.64, captain"
            value={form.detail}
            onChange={e => setForm(f => ({ ...f, detail: e.target.value }))}
          />
        </div>
      </div>
      {error && <p className="text-red-400 text-xs mb-2">{error}</p>}
      <div className="flex gap-2">
        <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">{saving ? 'Saving…' : 'Save'}</button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────────────────

export default function AchievementsAdmin() {
  const { orgId } = useParams()
  const [achievements, setAchievements] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filterSeason, setFilterSeason] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSearch, setFilterSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editItem, setEditItem] = useState(null)

  const load = () => {
    setLoading(true)
    api.listAchievements(orgId).then(data => {
      setAchievements(data)
      setLoading(false)
    }).catch(() => {
      setAchievements([])
      setLoading(false)
    })
  }

  useEffect(() => { load() }, [orgId])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  const handleSaved = () => {
    setShowAdd(false)
    setEditItem(null)
    load()
  }

  if (loading && !achievements) return <LoadingSpinner message="Loading achievements…" />

  const allSeasons = [...new Set((achievements || []).map(a => a.season).filter(Boolean))].sort((a, b) => b.localeCompare(a))

  const filtered = (achievements || []).filter(a => {
    if (filterSeason && a.season !== filterSeason) return false
    if (filterCategory && a.category !== filterCategory) return false
    if (filterSearch) {
      const q = filterSearch.toLowerCase()
      return a.player_name.toLowerCase().includes(q) || a.achievement.toLowerCase().includes(q) || (a.subcategory || '').toLowerCase().includes(q)
    }
    return true
  })

  // Group by season → category
  const grouped = {}
  for (const a of filtered) {
    const s = a.season || 'All Time'
    if (!grouped[s]) grouped[s] = {}
    if (!grouped[s][a.category]) grouped[s][a.category] = []
    grouped[s][a.category].push(a)
  }
  const seasons = Object.keys(grouped).sort((a, b) => {
    if (a === 'All Time') return 1
    if (b === 'All Time') return -1
    return b.localeCompare(a)
  })

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <div className="accent-bar mb-4" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="display-heading text-4xl text-white">ACHIEVEMENTS & HONOURS</h1>
            <p className="text-slate-400 text-sm mt-1">Manage club awards, office bearers, premierships, and milestones</p>
          </div>
          <button onClick={() => { setShowAdd(true); setEditItem(null) }} className="btn-primary text-sm">+ Add Achievement</button>
        </div>
      </div>

      <ImportPanel orgId={orgId} onImported={load} />

      {showAdd && !editItem && (
        <AchievementForm orgId={orgId} onSave={handleSaved} onCancel={() => setShowAdd(false)} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500 w-48"
          placeholder="Search player or award…"
          value={filterSearch}
          onChange={e => setFilterSearch(e.target.value)}
        />
        <select
          className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
          value={filterSeason}
          onChange={e => setFilterSeason(e.target.value)}
        >
          <option value="">All Seasons</option>
          {allSeasons.map(s => <option key={s} value={s}>{s.replace('_', '/')}</option>)}
        </select>
        <select
          className="bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent"
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="text-slate-500 text-sm self-center">{filtered.length} records</span>
      </div>

      {filtered.length === 0 && (
        <div className="card p-10 text-center text-slate-500 text-sm">
          No achievements found. Use the import above or add one manually.
        </div>
      )}

      {seasons.map(season => (
        <div key={season} className="card mb-4 overflow-hidden">
          <div className="px-5 py-3 bg-navy-800/60 border-b border-navy-700">
            <span className="text-accent font-mono font-bold">{season === 'All Time' ? 'All Time' : season.replace('_', '/')}</span>
            <span className="text-slate-500 text-sm ml-3">
              {Object.values(grouped[season]).reduce((sum, arr) => sum + arr.length, 0)} achievements
            </span>
          </div>

          {Object.entries(grouped[season]).map(([cat, items]) => (
            <div key={cat} className="border-b border-navy-700 last:border-0">
              <div className="px-5 py-2 bg-navy-800/20 flex items-center gap-2">
                <span>{CATEGORY_ICONS[cat] || '🎅'}</span>
                <span className="section-label text-xs">{cat.toUpperCase()}</span>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {items.map(a => (
                    <tr key={a.id} className="border-t border-navy-700/50 hover:bg-navy-800/30 group">
                      <td className="px-5 py-2.5 text-white font-medium w-48">{a.player_name}</td>
                      <td className="px-3 py-2.5 text-slate-300">{a.achievement}</td>
                      <td className="px-3 py-2.5 text-slate-500 text-xs">{a.subcategory || ''}</td>
                      <td className="px-3 py-2.5 text-slate-400 text-xs">{a.detail || ''}</td>
                      <td className="px-3 py-2.5 text-right w-24">
                        <div className="flex gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => { setEditItem(a); setShowAdd(false) }}
                            className="text-xs text-slate-400 hover:text-white px-2 py-0.5 rounded hover:bg-navy-700"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(a.id)}
                            className="text-xs text-red-400 hover:text-red-300 px-2 py-0.5 rounded hover:bg-navy-700"
                          >
                            ✕
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {editItem && items.find(i => i.id === editItem.id) && (
                <div className="px-5 py-3 border-t border-navy-700 bg-navy-800/40">
                  <AchievementForm
                    orgId={orgId}
                    initial={editItem}
                    onSave={handleSaved}
                    onCancel={() => setEditItem(null)}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
