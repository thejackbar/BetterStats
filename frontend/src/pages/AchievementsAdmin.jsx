import { useParams } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { ACHIEVEMENT_TREE, getSubcategories, getAchievements } from '../lib/achievementOptions'
import LoadingSpinner from '../components/LoadingSpinner'
import clsx from 'clsx'

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

const CATEGORY_ICONS = {
  'Club Award': '🏆',
  'Association Award': '🥇',
  'Office Bearer': '👔',
  'Premiership': '🏏',
  'Hall of Fame': '⭐',
  'Life Membership': '🎖',
  'Milestone': '📍',
}

const BASE = import.meta.env.VITE_API_URL || '/api'

// ─── Player autocomplete ──────────────────────────────────────────────────────

function PlayerAutocomplete({ players, value, onChange }) {
  const [query, setQuery] = useState(value || '')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => { setQuery(value || '') }, [value])

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = query.trim().length >= 1
    ? players.filter(p => p.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 10)
    : []

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); onChange({ name: e.target.value, id: null }); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Full name"
        className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-navy-800 border border-navy-600 rounded-lg shadow-xl max-h-52 overflow-y-auto">
          {filtered.map(p => (
            <button
              key={p.id}
              onMouseDown={() => { setQuery(p.name); onChange({ name: p.name, id: p.id }); setOpen(false) }}
              className="w-full text-left px-3 py-2 text-sm text-white hover:bg-navy-700 first:rounded-t-lg last:rounded-b-lg"
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Import panel ────────────────────────────────────────────────────────────

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
        The template includes cascading dropdown validation for Category, Subcategory, and Achievement columns.
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
            <div className="text-red-400">{result.errors.map((e, i) => <p key={i}>{e}</p>)}</div>
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

// ─── Shared form fields (category / subcategory / achievement) ────────────────

function AchievementFields({ form, setForm, seasons, inputCls }) {
  const [customSubcat, setCustomSubcat] = useState(false)
  const [customAchievement, setCustomAchievement] = useState(false)

  const subcatOptions = getSubcategories(form.category)
  const achievementOptions = getAchievements(form.category, form.subcategory)

  const setCategory = (cat) => {
    setForm(f => ({ ...f, category: cat, subcategory: '', achievement: '' }))
    setCustomSubcat(false)
    setCustomAchievement(false)
  }

  const setSubcat = (val) => {
    if (val === '__other__') { setCustomSubcat(true); setForm(f => ({ ...f, subcategory: '', achievement: '' })) }
    else { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: val, achievement: '' })); setCustomAchievement(false) }
  }

  const setAchievement = (val) => {
    if (val === '__other__') { setCustomAchievement(true); setForm(f => ({ ...f, achievement: '' })) }
    else { setCustomAchievement(false); setForm(f => ({ ...f, achievement: val })) }
  }

  return (
    <>
      <div>
        <label className="section-label mb-1 block">Season</label>
        <select className={inputCls} value={form.season} onChange={e => setForm(f => ({ ...f, season: e.target.value }))}>
          <option value="">— All Time —</option>
          {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div>
        <label className="section-label mb-1 block">Category *</label>
        <select className={inputCls} value={form.category} onChange={e => setCategory(e.target.value)}>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label className="section-label mb-1 block">Subcategory / Grade</label>
        {!customSubcat && subcatOptions.length > 0 ? (
          <select className={inputCls} value={form.subcategory} onChange={e => setSubcat(e.target.value)}>
            <option value="">— Select —</option>
            {subcatOptions.map(s => <option key={s}>{s}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={inputCls} placeholder="e.g. 1st XI, WASTCA" value={form.subcategory}
              onChange={e => setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' }))} />
            {customSubcat && <button onClick={() => { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: '' })) }} className="text-slate-500 hover:text-white px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="section-label mb-1 block">Achievement *</label>
        {!customAchievement && achievementOptions.length > 0 ? (
          <select className={inputCls} value={form.achievement} onChange={e => setAchievement(e.target.value)}>
            <option value="">— Select —</option>
            {achievementOptions.map(a => <option key={a}>{a}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={inputCls} placeholder="e.g. Best & Fairest, President" value={form.achievement}
              onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))} />
            {customAchievement && <button onClick={() => { setCustomAchievement(false); setForm(f => ({ ...f, achievement: '' })) }} className="text-slate-500 hover:text-white px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="section-label mb-1 block">Detail</label>
        <input className={inputCls} placeholder="e.g. 436 runs at 39.64, captain"
          value={form.detail} onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} />
      </div>
    </>
  )
}

// ─── Add/edit form ────────────────────────────────────────────────────────────

function AchievementForm({ orgId, initial, players, seasons, onSave, onCancel }) {
  const [form, setForm] = useState(initial || { season: '', category: 'Club Award', subcategory: '', achievement: '', player_name: '', player_id: null, detail: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const inputCls = 'w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500'

  const handleSave = async () => {
    if (!form.achievement.trim() || !form.player_name.trim()) { setError('Player Name and Achievement are required'); return }
    setSaving(true); setError(null)
    try {
      if (initial?.id) {
        await api.updateAchievement(initial.id, form)
      } else {
        const payload = { ...form, org_id: orgId }
        if (!payload.player_id) delete payload.player_id
        await api.createAchievement(payload)
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
          <PlayerAutocomplete
            players={players}
            value={form.player_name}
            onChange={({ name, id }) => setForm(f => ({ ...f, player_name: name, player_id: id }))}
          />
        </div>
        <AchievementFields form={form} setForm={setForm} seasons={seasons} inputCls={inputCls} />
      </div>
      {error && <p className="text-red-400 text-xs mb-2">{error}</p>}
      <div className="flex gap-2">
        <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">{saving ? 'Saving…' : 'Save'}</button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  )
}

// ─── Bulk add panel ───────────────────────────────────────────────────────────

function BulkAddPanel({ orgId, players, seasons, onSave, onCancel }) {
  const [form, setForm] = useState({ season: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
  const [selectedPlayers, setSelectedPlayers] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = query.trim().length >= 1
    ? players.filter(p => p.name.toLowerCase().includes(query.trim().toLowerCase()) && !selectedPlayers.find(s => s.id === p.id)).slice(0, 10)
    : []

  const addPlayer = (p) => { setSelectedPlayers(prev => [...prev, p]); setQuery(''); setOpen(false) }
  const removePlayer = (id) => setSelectedPlayers(prev => prev.filter(p => p.id !== id))

  const inputCls = 'w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-accent placeholder-slate-500'

  const handleSave = async () => {
    if (!form.achievement.trim()) { setError('Achievement is required'); return }
    if (selectedPlayers.length === 0) { setError('Select at least one player'); return }
    setSaving(true); setError(null)
    try {
      for (const p of selectedPlayers) {
        await api.createAchievement({ ...form, org_id: orgId, player_id: p.id, player_name: p.name })
      }
      onSave()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-navy-800/60 border border-accent/30 rounded-xl p-5 mb-4">
      <h3 className="text-sm font-semibold text-white mb-1">Bulk Add — Multiple Players, One Achievement</h3>
      <p className="text-slate-500 text-xs mb-4">Select an achievement, then add all players who received it. One record is created per player.</p>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        <AchievementFields form={form} setForm={setForm} seasons={seasons} inputCls={inputCls} />
      </div>

      <div className="mb-4">
        <label className="section-label mb-1 block">Players *</label>
        <div ref={ref} className="relative">
          <input
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            placeholder="Search and add players…"
            className={inputCls}
          />
          {open && filtered.length > 0 && (
            <div className="absolute z-50 mt-1 w-full bg-navy-800 border border-navy-600 rounded-lg shadow-xl max-h-52 overflow-y-auto">
              {filtered.map(p => (
                <button key={p.id} onMouseDown={() => addPlayer(p)}
                  className="w-full text-left px-3 py-2 text-sm text-white hover:bg-navy-700 first:rounded-t-lg last:rounded-b-lg">
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>
        {selectedPlayers.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {selectedPlayers.map(p => (
              <span key={p.id} className="flex items-center gap-1 bg-navy-700 text-white text-xs px-2.5 py-1 rounded-full">
                {p.name}
                <button onClick={() => removePlayer(p.id)} className="text-slate-400 hover:text-white ml-0.5">×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-red-400 text-xs mb-2">{error}</p>}
      <div className="flex gap-2 items-center">
        <button onClick={handleSave} disabled={saving || selectedPlayers.length === 0} className="btn-primary text-xs disabled:opacity-50">
          {saving ? 'Saving…' : `Save ${selectedPlayers.length > 0 ? `${selectedPlayers.length} achievement${selectedPlayers.length !== 1 ? 's' : ''}` : 'achievements'}`}
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AchievementsAdmin() {
  const { orgId } = useParams()
  const [achievements, setAchievements] = useState(null)
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterSeason, setFilterSeason] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSearch, setFilterSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [editItem, setEditItem] = useState(null)

  const load = () => {
    setLoading(true)
    api.listAchievements(orgId).then(data => {
      setAchievements(data)
      setLoading(false)
    }).catch(() => { setAchievements([]); setLoading(false) })
  }

  useEffect(() => {
    load()
    api.listPlayers(orgId).then(data => setPlayers(data || [])).catch(() => {})
    api.getOrgSeasons(orgId).then(data => setSeasons(data || [])).catch(() => {})
  }, [orgId])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  const handleSaved = () => { setShowAdd(false); setShowBulk(false); setEditItem(null); load() }

  if (loading && !achievements) return <LoadingSpinner message="Loading achievements…" />

  // Map season id → display name
  const seasonMap = Object.fromEntries(seasons.map(s => [s.id, s.name]))
  const seasonDisplay = (s) => s === 'All Time' ? 'All Time' : (seasonMap[s] || s.replace(/_/g, '/'))

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

  const grouped = {}
  for (const a of filtered) {
    const s = a.season || 'All Time'
    if (!grouped[s]) grouped[s] = {}
    if (!grouped[s][a.category]) grouped[s][a.category] = []
    grouped[s][a.category].push(a)
  }
  const groupedSeasons = Object.keys(grouped).sort((a, b) => {
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
          <div className="flex gap-2">
            <button onClick={() => { setShowBulk(true); setShowAdd(false); setEditItem(null) }} className="btn-ghost border border-navy-600 text-sm">
              Bulk Add
            </button>
            <button onClick={() => { setShowAdd(true); setShowBulk(false); setEditItem(null) }} className="btn-primary text-sm">
              + Add Achievement
            </button>
          </div>
        </div>
      </div>

      <ImportPanel orgId={orgId} onImported={load} />

      {showBulk && (
        <BulkAddPanel orgId={orgId} players={players} seasons={seasons} onSave={handleSaved} onCancel={() => setShowBulk(false)} />
      )}

      {showAdd && !editItem && (
        <AchievementForm orgId={orgId} players={players} seasons={seasons} onSave={handleSaved} onCancel={() => setShowAdd(false)} />
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
          {allSeasons.map(s => <option key={s} value={s}>{seasonDisplay(s)}</option>)}
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

      {groupedSeasons.map(season => (
        <div key={season} className="mb-6">
          {/* Season header */}
          <div className="flex items-center gap-3 mb-3">
            <span className="text-white font-semibold text-sm">{seasonDisplay(season)}</span>
            <span className="h-px flex-1 bg-navy-700" />
            <span className="text-slate-500 text-xs">
              {Object.values(grouped[season]).reduce((sum, arr) => sum + arr.length, 0)} achievements
            </span>
          </div>

          {/* Categories */}
          {Object.entries(grouped[season]).map(([cat, items]) => (
            <div key={cat} className="card mb-3 overflow-hidden">
              <div className="px-4 py-2.5 bg-navy-800/60 border-b border-navy-700 flex items-center gap-2">
                <span className="text-base">{CATEGORY_ICONS[cat] || '🏅'}</span>
                <span className="section-label text-xs">{cat.toUpperCase()}</span>
              </div>

              <div className="divide-y divide-navy-700/40">
                {items.map(a => (
                  <div key={a.id}>
                    <div className="px-4 py-2.5 flex items-center gap-2 group hover:bg-navy-800/30 transition-colors">
                      <div className="flex-1 min-w-0 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <span className="text-white text-sm font-medium truncate">{a.player_name}</span>
                        <span className="text-slate-300 text-sm truncate">{a.achievement}</span>
                        {a.subcategory && (
                          <span className="text-xs text-slate-500 font-mono">{a.subcategory}</span>
                        )}
                        {a.detail && (
                          <span className="text-xs text-slate-400 italic">{a.detail}</span>
                        )}
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={() => { setEditItem(a); setShowAdd(false); setShowBulk(false) }}
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
                    </div>
                    {editItem?.id === a.id && (
                      <div className="px-4 py-3 border-t border-navy-700 bg-navy-800/40">
                        <AchievementForm
                          orgId={orgId}
                          initial={editItem}
                          players={players}
                          seasons={seasons}
                          onSave={handleSaved}
                          onCancel={() => setEditItem(null)}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
