import { useParams } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { getSubcategoriesFromDefs, getAchievementsFromDefs, resolveAwardLabel } from '../lib/achievementOptions'
import { PbSpinner } from '../lib/presskit'
import { CATEGORY_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

const BASE = import.meta.env.VITE_API_URL || '/api'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest'

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
    ? players.filter(p => (p.display_name || p.name).toLowerCase().includes(query.trim().toLowerCase())).slice(0, 10)
    : []

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); onChange({ name: e.target.value, id: null }); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Full name"
        className={INPUT_CLS}
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-pb-surface border pb-hairline rounded shadow-xl max-h-52 overflow-y-auto pb-scroll">
          {filtered.map(p => (
            <button
              key={p.id}
              onMouseDown={() => { const dn = p.display_name || p.name; setQuery(dn); onChange({ name: dn, id: p.id }); setOpen(false) }}
              className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
            >
              {p.display_name || p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ImportPanel({ orgId, onImported }) {
  const fileRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [forcing, setForcing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [checkedDupes, setCheckedDupes] = useState({})

  const handleDownloadTemplate = async () => {
    const token = localStorage.getItem('bs_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`${BASE}/achievements/template`, { headers })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'achievements_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setResult(null)
    setError(null)
    setCheckedDupes({})
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

  const toggleDupe = (idx) => setCheckedDupes(prev => ({ ...prev, [idx]: !prev[idx] }))
  const toggleAll = () => {
    const dupes = result?.skipped_duplicates || []
    const allChecked = dupes.every((_, i) => checkedDupes[i])
    setCheckedDupes(allChecked ? {} : Object.fromEntries(dupes.map((_, i) => [i, true])))
  }

  const handleForceImport = async () => {
    const dupes = result?.skipped_duplicates || []
    const rows = dupes.filter((_, i) => checkedDupes[i])
    if (!rows.length) return
    setForcing(true)
    try {
      await api.forceImportAchievements(orgId, rows)
      setResult(prev => ({
        ...prev,
        created: (prev.created || 0) + rows.length,
        skipped_duplicates: dupes.filter((_, i) => !checkedDupes[i]),
      }))
      setCheckedDupes({})
      onImported()
    } catch (err) {
      setError(err.message || 'Force import failed')
    } finally {
      setForcing(false)
    }
  }

  const dupes = result?.skipped_duplicates || []
  const checkedCount = Object.values(checkedDupes).filter(Boolean).length

  return (
    <div className="pb-card p-5 mb-6">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Bulk Import</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Download the CSV template, fill in achievements using the column format, then upload. Player names are matched automatically.
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <button
          onClick={handleDownloadTemplate}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors flex items-center gap-2"
        >
          ⬇ Download Template (.csv)
        </button>
        <label className={`px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition cursor-pointer flex items-center gap-2 text-pb-bg ${importing ? 'opacity-50 pointer-events-none' : ''}`}
          style={{ background: 'var(--pb-accent)' }}>
          ⬆ {importing ? 'Importing…' : 'Upload File (.xlsx / .csv)'}
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={handleImport} />
        </label>
      </div>

      {result && (
        <div className="mt-4 p-4 bg-pb-surface2 rounded border pb-hairline text-sm space-y-1">
          <p className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>✓ Import complete — {result.created} achievements added</p>
          {result.skipped > 0 && <p className="text-pb-faint font-mono text-[10px]">Skipped: {result.skipped} rows (empty or invalid)</p>}
          {result.errors?.length > 0 && (
            <div className="text-pb-red font-mono text-[10px]">{result.errors.map((e, i) => <p key={i}>{e}</p>)}</div>
          )}
          {result.unmatched_players?.length > 0 && (
            <div>
              <p className="text-pb-amber font-mono text-[10px] mt-2">⚠ Player names not matched ({result.unmatched_players.length}) — still saved, can be linked manually</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {result.unmatched_players.map(n => (
                  <span key={n} className="font-mono text-[10px] bg-pb-surface border pb-hairline text-pb-amber px-2 py-0.5 rounded">{n}</span>
                ))}
              </div>
            </div>
          )}

          {dupes.length > 0 && (
            <div className="mt-3 pt-3 border-t pb-hairline">
              <div className="flex items-center justify-between mb-2">
                <p className="font-mono text-[10px] text-pb-amber">
                  ⚠ {dupes.length} duplicate{dupes.length !== 1 ? 's' : ''} skipped — already exist in the database
                </p>
                <button
                  onClick={toggleAll}
                  className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline"
                >
                  {dupes.every((_, i) => checkedDupes[i]) ? 'Deselect all' : 'Select all'}
                </button>
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto pb-scroll">
                {dupes.map((d, i) => (
                  <label key={i} className="flex items-start gap-2 cursor-pointer group py-0.5">
                    <input
                      type="checkbox"
                      checked={!!checkedDupes[i]}
                      onChange={() => toggleDupe(i)}
                      className="mt-0.5 accent-[var(--pb-accent)] flex-shrink-0"
                    />
                    <span className="font-mono text-[10px] text-pb-dim group-hover:text-pb-text leading-relaxed">
                      <span className="text-pb-text">{d.player_name}</span>
                      {d.season && <span className="text-pb-faint"> · {d.season.replace(/_/g, '/')}</span>}
                      {' · '}{d.category}
                      {d.subcategory && <span className="text-pb-faint"> / {d.subcategory}</span>}
                      {' · '}{d.achievement}
                      {d.detail && <span className="text-pb-faint italic"> ({d.detail})</span>}
                    </span>
                  </label>
                ))}
              </div>
              {checkedCount > 0 && (
                <button
                  onClick={handleForceImport}
                  disabled={forcing}
                  className="mt-3 px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  {forcing ? 'Importing…' : `Force import ${checkedCount} selected`}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {error && <p className="mt-3 font-mono text-[11px] text-pb-red">{error}</p>}
    </div>
  )
}

function AchievementFields({ form, setForm, seasons, awardDefs }) {
  const [customSubcat, setCustomSubcat] = useState(false)
  const [customAchievement, setCustomAchievement] = useState(false)

  const subcatOptions = getSubcategoriesFromDefs(awardDefs, form.category)
  const achievementOptions = getAchievementsFromDefs(awardDefs, form.category, form.subcategory)

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
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Season {form.category === 'Office Bearer' ? 'Start' : ''}</label>
        <select className={INPUT_CLS} value={form.season} onChange={e => setForm(f => ({ ...f, season: e.target.value }))}>
          <option value="">— All Time —</option>
          {seasons.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      </div>
      {form.category === 'Office Bearer' && (
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Season End</label>
          <select className={INPUT_CLS} value={form.season_end || ''} onChange={e => setForm(f => ({ ...f, season_end: e.target.value }))}>
            <option value="">— Present —</option>
            {seasons.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
        </div>
      )}
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Category *</label>
        <select className={INPUT_CLS} value={form.category} onChange={e => setCategory(e.target.value)}>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Subcategory / Grade</label>
        {!customSubcat && subcatOptions.length > 0 ? (
          <select className={INPUT_CLS} value={form.subcategory} onChange={e => setSubcat(e.target.value)}>
            <option value="">— Select —</option>
            {subcatOptions.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={INPUT_CLS} placeholder="e.g. 1st XI, WASTCA" value={form.subcategory}
              onChange={e => setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' }))} />
            {customSubcat && <button onClick={() => { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: '' })) }} className="text-pb-faint hover:text-pb-text px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Achievement *</label>
        {!customAchievement && achievementOptions.length > 0 ? (
          <select className={INPUT_CLS} value={form.achievement} onChange={e => setAchievement(e.target.value)}>
            <option value="">— Select —</option>
            {achievementOptions.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={INPUT_CLS} placeholder="e.g. Best & Fairest, President" value={form.achievement}
              onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))} />
            {customAchievement && <button onClick={() => { setCustomAchievement(false); setForm(f => ({ ...f, achievement: '' })) }} className="text-pb-faint hover:text-pb-text px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Detail</label>
        <input className={INPUT_CLS} placeholder="e.g. 436 runs at 39.64, captain"
          value={form.detail} onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} />
      </div>
    </>
  )
}

function AchievementForm({ orgId, initial, players, seasons, awardDefs, onSave, onCancel }) {
  const [form, setForm] = useState(initial || { season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', player_name: '', player_id: null, detail: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

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
    <div className="bg-pb-surface2/60 border pb-hairline rounded p-5 mb-4">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">{initial?.id ? 'EDIT ACHIEVEMENT' : 'ADD ACHIEVEMENT'}</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Player Name *</label>
          <PlayerAutocomplete
            players={players}
            value={form.player_name}
            onChange={({ name, id }) => setForm(f => ({ ...f, player_name: name, player_id: id }))}
          />
        </div>
        <AchievementFields form={form} setForm={setForm} seasons={seasons} awardDefs={awardDefs} />
      </div>
      {error && <p className="font-mono text-[10px] text-pb-red mb-2">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function BulkAddPanel({ orgId, players, seasons, awardDefs, onSave, onCancel }) {
  const [form, setForm] = useState({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
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
    ? players.filter(p => (p.display_name || p.name).toLowerCase().includes(query.trim().toLowerCase()) && !selectedPlayers.find(s => s.id === p.id)).slice(0, 10)
    : []

  const addPlayer = (p) => { setSelectedPlayers(prev => [...prev, p]); setQuery(''); setOpen(false) }
  const removePlayer = (id) => setSelectedPlayers(prev => prev.filter(p => p.id !== id))

  const handleSave = async () => {
    if (!form.achievement.trim()) { setError('Achievement is required'); return }
    if (selectedPlayers.length === 0) { setError('Select at least one player'); return }
    setSaving(true); setError(null)
    try {
      for (const p of selectedPlayers) {
        await api.createAchievement({ ...form, org_id: orgId, player_id: p.id, player_name: p.display_name || p.name })
      }
      onSave()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pb-card p-5 mb-4" style={{ borderColor: 'var(--pb-accent)', borderWidth: '1px' }}>
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">BULK ADD — MULTIPLE PLAYERS, ONE ACHIEVEMENT</p>
      <p className="font-mono text-[10px] text-pb-faintest mb-4">Select an achievement, then add all players who received it. One record is created per player.</p>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        <AchievementFields form={form} setForm={setForm} seasons={seasons} awardDefs={awardDefs} />
      </div>

      <div className="mb-4">
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Players *</label>
        <div ref={ref} className="relative">
          <input
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            placeholder="Search and add players…"
            className={INPUT_CLS}
          />
          {open && filtered.length > 0 && (
            <div className="absolute z-50 mt-1 w-full bg-pb-surface border pb-hairline rounded shadow-xl max-h-52 overflow-y-auto pb-scroll">
              {filtered.map(p => (
                <button key={p.id} onMouseDown={() => addPlayer(p)}
                  className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text">
                  {p.display_name || p.name}
                </button>
              ))}
            </div>
          )}
        </div>
        {selectedPlayers.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {selectedPlayers.map(p => (
              <span key={p.id} className="flex items-center gap-1 bg-pb-surface2 border pb-hairline text-pb-text text-xs px-2.5 py-1 rounded-full">
                {p.display_name || p.name}
                <button onClick={() => removePlayer(p.id)} className="text-pb-faint hover:text-pb-text ml-0.5">×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error && <p className="font-mono text-[10px] text-pb-red mb-2">{error}</p>}
      <div className="flex gap-2 items-center">
        <button
          onClick={handleSave}
          disabled={saving || selectedPlayers.length === 0}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          {saving ? 'Saving…' : `Save ${selectedPlayers.length > 0 ? `${selectedPlayers.length} achievement${selectedPlayers.length !== 1 ? 's' : ''}` : 'achievements'}`}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function AchievementsAdmin({ embeddedOrgId }) {
  const params = useParams()
  const orgId = embeddedOrgId || params.orgId
  const [achievements, setAchievements] = useState(null)
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState(null)
  const [awardDefs, setAwardDefs] = useState([])
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
    api.listAwardDefinitions(orgId).then(data => setAwardDefs(data || [])).catch(() => {})
  }, [orgId])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  const handleSaved = () => { setShowAdd(false); setShowBulk(false); setEditItem(null); load() }

  if ((loading && !achievements) || seasons === null) return <PbSpinner message="Loading achievements…" />

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  const seasonDisplay = (s) => {
    if (!s || s === 'All Time') return 'All Time'
    if (UUID_RE.test(s)) return 'Unknown Season'
    return s.replace(/_/g, '/')
  }

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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display font-bold text-3xl text-pb-text tracking-tight">Achievements & Honours</h1>
            <p className="text-pb-faint text-sm mt-1">Manage club awards, office bearers, premierships, and milestones</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { setShowBulk(true); setShowAdd(false); setEditItem(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors"
            >
              Bulk Add
            </button>
            <button
              onClick={() => { setShowAdd(true); setShowBulk(false); setEditItem(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              + Add Achievement
            </button>
          </div>
        </div>
      </div>

      <ImportPanel orgId={orgId} onImported={load} />

      {showBulk && (
        <BulkAddPanel orgId={orgId} players={players} seasons={seasons} awardDefs={awardDefs} onSave={handleSaved} onCancel={() => setShowBulk(false)} />
      )}

      {showAdd && !editItem && (
        <AchievementForm orgId={orgId} players={players} seasons={seasons} awardDefs={awardDefs} onSave={handleSaved} onCancel={() => setShowAdd(false)} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest w-48"
          placeholder="Search player or award…"
          value={filterSearch}
          onChange={e => setFilterSearch(e.target.value)}
        />
        <select
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
          value={filterSeason}
          onChange={e => setFilterSeason(e.target.value)}
        >
          <option value="">All Seasons</option>
          {allSeasons.map(s => <option key={s} value={s}>{seasonDisplay(s)}</option>)}
        </select>
        <select
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="font-mono text-[11px] text-pb-faint self-center">{filtered.length} records</span>
      </div>

      {filtered.length === 0 && (
        <div className="pb-card p-10 text-center text-pb-faint font-mono text-[11px]">
          No achievements found. Use the import above or add one manually.
        </div>
      )}

      {groupedSeasons.map(season => (
        <div key={season} className="mb-6">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-pb-text font-semibold text-sm">{seasonDisplay(season)}</span>
            <span className="h-px flex-1 bg-pb-hairline" />
            <span className="font-mono text-[10px] text-pb-faintest">
              {Object.values(grouped[season]).reduce((sum, arr) => sum + arr.length, 0)} achievements
            </span>
          </div>

          {Object.entries(grouped[season]).map(([cat, items]) => (
            <div key={cat} className="pb-card mb-3 overflow-hidden">
              <div className="px-4 py-2.5 bg-pb-surface2/40 pb-hairline-b flex items-center gap-2">
                <ThiingIcon src={CATEGORY_ICON_SRC[cat] || thiings.goldMedal} alt="" className="w-5 h-5" />
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">{cat.toUpperCase()}</span>
              </div>

              <div>
                {items.map((a, i) => (
                  <div key={a.id} className={i ? 'pb-hairline-t' : ''}>
                    <div className="px-4 py-2.5 flex items-center gap-2 group hover:bg-pb-surface2 transition-colors">
                      <div className="flex-1 min-w-0 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <span className="text-pb-text text-sm font-medium truncate">{a.player_name}</span>
                        <span className="text-pb-dim text-sm truncate">{resolveAwardLabel(awardDefs, a.category, a.subcategory, a.achievement)}</span>
                        {a.subcategory && <span className="font-mono text-[10px] text-pb-faint">{a.subcategory}</span>}
                        {a.season_end && (
                          <span className="font-mono text-[10px] text-pb-faint">
                            {seasonDisplay(a.season)} — {seasonDisplay(a.season_end)}
                          </span>
                        )}
                        {a.detail && <span className="font-mono text-[10px] text-pb-faint italic">{a.detail}</span>}
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={() => { setEditItem(a); setShowAdd(false); setShowBulk(false) }}
                          className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-0.5 rounded hover:bg-pb-surface2"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(a.id)}
                          className="font-mono text-[10px] text-pb-red/70 hover:text-pb-red px-2 py-0.5 rounded hover:bg-pb-surface2"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                    {editItem?.id === a.id && (
                      <div className="px-4 py-3 pb-hairline-t bg-pb-surface2/20">
                        <AchievementForm
                          orgId={orgId}
                          initial={editItem}
                          players={players}
                          seasons={seasons}
                          awardDefs={awardDefs}
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
