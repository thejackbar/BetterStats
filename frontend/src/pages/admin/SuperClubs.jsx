import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

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
        <div className="flex items-center justify-between mb-5">
          <h1 className="font-display font-bold text-2xl text-pb-text">All Clubs</h1>
          <div className="flex items-center gap-3">
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
            <button
              onClick={() => setShowCreate(s => !s)}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {showCreate ? 'CANCEL' : '+ NEW CLUB'}
            </button>
          </div>
        </div>

        {showCreate && (
          <form onSubmit={createClub} className="pb-card p-4 mb-5 space-y-3">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Create New Club</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Club name *</label>
                <input required type="text" value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Slug * (URL identifier)</label>
                <input required type="text" value={form.slug}
                  onChange={e => setForm(f => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                  placeholder="e.g. applecross"
                  className={INPUT_CLS + ' font-mono'} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Short name</label>
                <input type="text" value={form.short_name}
                  onChange={e => setForm(f => ({ ...f, short_name: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Contact email</label>
                <input type="email" value={form.contact_email}
                  onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                  className={INPUT_CLS} />
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Creating…' : 'CREATE CLUB'}
            </button>
          </form>
        )}

        <div className="pb-card overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
            <span>CLUB</span>
            <span className="mr-8">STATUS</span>
            <span>CREATED</span>
          </div>
          {clubs.length === 0 && (
            <div className="px-5 py-6 text-center font-mono text-[11px] text-pb-faint">No clubs yet</div>
          )}
          {clubs.map((club, i) => (
            <div key={club.id} className={`grid grid-cols-[1fr_auto_auto] items-center px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
              <div>
                <span className="text-pb-text text-sm">{club.name}</span>
                <span className="font-mono text-[10px] text-pb-faintest ml-2">/{club.slug}</span>
              </div>
              <button
                onClick={() => toggleActive(club)}
                className={`font-mono text-[10px] px-2 py-1 rounded mr-8 border transition-colors ${
                  club.is_active
                    ? 'border-pb-accent/30 text-pb-accent bg-pb-accent/10'
                    : 'border-pb-hairline text-pb-faint bg-pb-surface2'
                }`}
                style={club.is_active ? { color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : {}}
              >
                {club.is_active ? 'Active' : 'Inactive'}
              </button>
              <span className="font-mono text-[10px] text-pb-faintest">
                {club.created_at ? new Date(club.created_at).toLocaleDateString('en-AU') : '—'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AdminLayout>
  )
}
