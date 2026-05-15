import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const CATEGORIES = [
  'Club Award', 'Association Award', 'Office Bearer',
  'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone',
]

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest'
const BTN_CLS = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text transition-colors'
const BTN_PRIMARY_CLS = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg'

// ─── Inline display-name editor ──────────────────────────────────────────────
function InlineEdit({ value, placeholder, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(value || '')
  const inputRef = useRef(null)

  useEffect(() => { setVal(value || '') }, [value])
  useEffect(() => { if (editing) inputRef.current?.focus() }, [editing])

  const commit = () => {
    setEditing(false)
    onSave(val.trim() || null)
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={val}
        onChange={e => setVal(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { setVal(value || ''); setEditing(false) } }}
        placeholder={placeholder}
        className="w-full bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-2 py-1 focus:outline-none focus:border-pb-accent"
      />
    )
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="w-full text-left group flex items-center gap-1.5"
    >
      {value
        ? <span className="text-sm text-pb-text">{value}</span>
        : <span className="text-xs text-pb-faintest italic">Click to set display name…</span>
      }
      <span className="opacity-0 group-hover:opacity-100 text-[10px] text-pb-faintest">✎</span>
    </button>
  )
}

// ─── Add definition form ──────────────────────────────────────────────────────
function AddForm({ orgId, onSaved, onCancel, existingDefs }) {
  const [form, setForm] = useState({
    category: 'Club Award', subcategory: '', achievement: '', display_name: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const subcatSuggestions = [...new Set(
    existingDefs.filter(d => d.category === form.category && d.subcategory).map(d => d.subcategory)
  )]
  const achievementSuggestions = [...new Set(
    existingDefs.filter(d => d.category === form.category && d.subcategory === form.subcategory && d.achievement)
      .map(d => d.achievement)
  )]

  const handleSave = async () => {
    if (!form.category) { setError('Category is required'); return }
    setSaving(true); setError(null)
    try {
      await api.createAwardDefinition({
        org_id: orgId,
        category: form.category,
        subcategory: form.subcategory || null,
        achievement: form.achievement || null,
        display_name: form.display_name || null,
        sort_order: existingDefs.length,
      })
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-pb-surface2/60 border pb-hairline rounded p-4 mb-4">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">ADD AWARD DEFINITION</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Category *</label>
          <select className={INPUT_CLS} value={form.category}
            onChange={e => setForm(f => ({ ...f, category: e.target.value, subcategory: '', achievement: '' }))}>
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Subcategory</label>
          <input
            className={INPUT_CLS}
            list={`subcat-suggestions-${form.category}`}
            value={form.subcategory}
            onChange={e => setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' }))}
            placeholder="e.g. 1st XI, Perpetual"
          />
          <datalist id={`subcat-suggestions-${form.category}`}>
            {subcatSuggestions.map(s => <option key={s} value={s} />)}
          </datalist>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Achievement</label>
          <input
            className={INPUT_CLS}
            list="achievement-suggestions"
            value={form.achievement}
            onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))}
            placeholder="e.g. Best & Fairest"
          />
          <datalist id="achievement-suggestions">
            {achievementSuggestions.map(a => <option key={a} value={a} />)}
          </datalist>
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Display Name</label>
          <input
            className={INPUT_CLS}
            value={form.display_name}
            onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))}
            placeholder="e.g. Mark Hullett Medal"
          />
        </div>
      </div>
      {error && <p className="font-mono text-[10px] text-pb-red mb-2">{error}</p>}
      <div className="flex gap-2">
        <button onClick={handleSave} disabled={saving}
          className={`${BTN_PRIMARY_CLS} disabled:opacity-50`} style={{ background: 'var(--pb-accent)' }}>
          {saving ? 'Saving…' : 'Add'}
        </button>
        <button onClick={onCancel} className={BTN_CLS}>Cancel</button>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function AdminAwardDefinitions() {
  const { user } = useAuth()
  const orgId = user?.org_id
  const [defs, setDefs] = useState(null)
  const [filterCat, setFilterCat] = useState('')
  const [filterSearch, setFilterSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [saving, setSaving] = useState(null)
  const [seeding, setSeeding] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    if (!orgId) return
    api.listAwardDefinitions(orgId).then(data => {
      setDefs(data)
      // Auto-seed from global template if this org has no definitions yet
      if (data.length === 0) {
        api.seedAwardDefinitions(orgId, 'global').then(() => {
          api.listAwardDefinitions(orgId).then(setDefs)
        })
      }
    })
  }

  useEffect(() => { load() }, [orgId])

  const handleUpdateDisplayName = async (id, display_name) => {
    setSaving(id)
    try {
      await api.updateAwardDefinition(id, { display_name })
      setDefs(prev => prev.map(d => d.id === id ? { ...d, display_name } : d))
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(null)
    }
  }

  const handleToggleActive = async (id, active) => {
    setSaving(id)
    try {
      await api.updateAwardDefinition(id, { active })
      setDefs(prev => prev.map(d => d.id === id ? { ...d, active } : d))
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(null)
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this award definition?')) return
    await api.deleteAwardDefinition(id)
    setDefs(prev => prev.filter(d => d.id !== id))
  }

  const handleReseed = async () => {
    if (!window.confirm('This will reset all award definitions to the global template. Any custom display names will be lost. Continue?')) return
    setSeeding(true)
    try {
      await api.seedAwardDefinitions(orgId, 'global')
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSeeding(false)
    }
  }

  if (!defs) return (
    <AdminLayout>
      <PbSpinner message="Loading award definitions…" />
    </AdminLayout>
  )

  const filtered = defs.filter(d => {
    if (filterCat && d.category !== filterCat) return false
    if (filterSearch) {
      const q = filterSearch.toLowerCase()
      return (
        (d.achievement || '').toLowerCase().includes(q) ||
        (d.subcategory || '').toLowerCase().includes(q) ||
        (d.display_name || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  // Group by category for display
  const grouped = {}
  for (const d of filtered) {
    if (!grouped[d.category]) grouped[d.category] = []
    grouped[d.category].push(d)
  }
  const orderedCats = CATEGORIES.filter(c => !filterCat ? grouped[c] : grouped[c])

  return (
    <AdminLayout>
      <div className="max-w-5xl mx-auto">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text tracking-tight">Award Definitions</h1>
            <p className="text-pb-faint text-sm mt-1">
              Configure the award types available at your club. Set a <strong className="text-pb-dim">Display Name</strong> to rename any award — click any name cell to edit inline.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={handleReseed}
              disabled={seeding}
              className={`${BTN_CLS} disabled:opacity-50`}
            >
              {seeding ? 'Resetting…' : '↺ Reset to Standard Template'}
            </button>
            <button
              onClick={() => setShowAdd(s => !s)}
              className={BTN_PRIMARY_CLS}
              style={{ background: 'var(--pb-accent)' }}
            >
              + Add Award Type
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-pb-surface2 border border-pb-red rounded font-mono text-[11px] text-pb-red">
            {error} <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
          </div>
        )}

        {showAdd && (
          <AddForm
            orgId={orgId}
            existingDefs={defs}
            onSaved={() => { setShowAdd(false); load() }}
            onCancel={() => setShowAdd(false)}
          />
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-5">
          <input
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest w-52"
            placeholder="Search award or subcategory…"
            value={filterSearch}
            onChange={e => setFilterSearch(e.target.value)}
          />
          <select
            className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
            value={filterCat}
            onChange={e => setFilterCat(e.target.value)}
          >
            <option value="">All Categories</option>
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
          <span className="self-center font-mono text-[11px] text-pb-faintest">
            {filtered.length} definition{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>

        {orderedCats.length === 0 && (
          <p className="text-pb-faint text-sm py-6">No definitions match your filter.</p>
        )}

        {orderedCats.map(cat => (
          <div key={cat} className="mb-8">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2 px-1">{cat}</div>
            <div className="pb-card overflow-hidden">
              {/* Header */}
              <div className="grid grid-cols-[1fr_1fr_1.4fr_80px] gap-3 px-4 py-2 border-b pb-hairline-b bg-pb-surface2/40">
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest">SUBCATEGORY</span>
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest">ACHIEVEMENT (STORED VALUE)</span>
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest">DISPLAY NAME (SHOWN EVERYWHERE)</span>
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faintest text-right">ACTIVE</span>
              </div>
              {grouped[cat].map((d, idx) => (
                <div
                  key={d.id}
                  className={`grid grid-cols-[1fr_1fr_1.4fr_80px] gap-3 px-4 py-2.5 items-center border-b pb-hairline-b last:border-0 transition-colors ${d.active === false ? 'opacity-40' : ''} hover:bg-pb-surface2/30 group`}
                >
                  <span className="text-sm text-pb-dim font-mono text-[11px]">{d.subcategory || '—'}</span>
                  <span className="text-sm text-pb-dim">{d.achievement || '—'}</span>
                  <div className="min-w-0">
                    <InlineEdit
                      value={d.display_name}
                      placeholder={d.achievement || d.subcategory || ''}
                      onSave={(val) => handleUpdateDisplayName(d.id, val)}
                    />
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={d.active !== false}
                        onChange={e => handleToggleActive(d.id, e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-8 h-4 bg-pb-surface2 rounded-full peer peer-checked:bg-pb-accent transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-4" />
                    </label>
                    <button
                      onClick={() => handleDelete(d.id)}
                      className="opacity-0 group-hover:opacity-100 text-pb-red text-[11px] hover:underline transition-opacity ml-1"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {defs.length > 0 && (
          <p className="text-pb-faintest font-mono text-[10px] text-center py-4">
            {defs.length} total definitions · Click any Display Name cell to rename
          </p>
        )}
      </div>
    </AdminLayout>
  )
}
