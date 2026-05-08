import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function SuperClubs() {
  const [clubs, setClubs] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', short_name: '', contact_email: '' })
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => api.superListClubs().then(setClubs).catch(() => {})
  useEffect(() => { load() }, [])

  const toggleActive = async (club) => {
    try {
      await api.superPatchClub(club.id, { is_active: !club.is_active })
      load()
    } catch (err) {
      setMsg(err.message)
    }
  }

  const createClub = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      await api.superCreateClub(form)
      setMsg('Club created')
      setShowCreate(false)
      setForm({ name: '', slug: '', short_name: '', contact_email: '' })
      load()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-display font-bold text-white">All Clubs</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="text-sm text-accent">{msg}</span>}
            <button onClick={() => setShowCreate(s => !s)} className="btn-primary text-sm">
              {showCreate ? 'Cancel' : '+ New Club'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createClub} className="bg-navy-900 border border-navy-700 rounded-lg p-4 mb-4 space-y-3">
            <h2 className="text-sm font-medium text-white">Create New Club</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Club name *</label>
                <input required type="text" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Slug * (URL identifier)</label>
                <input required type="text" value={form.slug} onChange={e => setForm(f => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                  placeholder="e.g. applecross"
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm font-mono focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Short name</label>
                <input type="text" value={form.short_name} onChange={e => setForm(f => ({ ...f, short_name: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Contact email</label>
                <input type="email" value={form.contact_email} onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                  className="w-full bg-navy-800 border border-navy-600 rounded px-2 py-1.5 text-white text-sm focus:outline-none focus:border-accent" />
              </div>
            </div>
            <button type="submit" disabled={saving} className="btn-primary text-sm">
              {saving ? 'Creating…' : 'Create Club'}
            </button>
          </form>
        )}

        <div className="bg-navy-900 border border-navy-700 rounded-lg overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto] text-xs text-slate-500 px-4 py-2 border-b border-navy-800">
            <span>Club</span>
            <span className="mr-8">Status</span>
            <span>Created</span>
          </div>
          {clubs.length === 0 && (
            <div className="px-4 py-6 text-center text-slate-500 text-sm">No clubs yet</div>
          )}
          {clubs.map((club, i) => (
            <div key={club.id} className={`grid grid-cols-[1fr_auto_auto] items-center px-4 py-3 ${i > 0 ? 'border-t border-navy-800' : ''}`}>
              <div>
                <span className="text-white text-sm">{club.name}</span>
                <span className="text-slate-500 text-xs ml-2 font-mono">/{club.slug}</span>
              </div>
              <button
                onClick={() => toggleActive(club)}
                className={`text-xs px-2 py-1 rounded mr-8 ${club.is_active ? 'bg-accent/20 text-accent' : 'bg-navy-800 text-slate-400'}`}
              >
                {club.is_active ? 'Active' : 'Inactive'}
              </button>
              <span className="text-slate-500 text-xs">
                {club.created_at ? new Date(club.created_at).toLocaleDateString('en-AU') : '—'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
