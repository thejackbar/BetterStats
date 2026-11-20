import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import AdminLayout from '../../components/admin/AdminLayout'

// Super Admin → Association Socials. An association workspace is an organisation
// with no club behind it and only BetterSocials switched on: it holds a brand
// (name, crest, colours, sponsors) and builds posts for a whole grade from a
// pasted play.cricket.com.au link (backend: services/social_competition.py).
// It never syncs, has no public site and is kept off All Clubs.

const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.BASE_URL + 'api')
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const INPUT_CLS = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'

export default function SuperAssociationWorkspaces() {
  const { switchClub } = useAuth()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ name: '', short_name: '', primary_color: '#16c784', accent_color: '#243352' })
  const [saving, setSaving] = useState(false)
  const [opening, setOpening] = useState('')

  const load = () => api.superListAssociationWorkspaces()
    .then((d) => setRows(d.workspaces || []))
    .catch((e) => { setError(e.message); setRows([]) })
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.name.trim()) { setError('Give the workspace a name.'); return }
    setSaving(true)
    try {
      await api.superCreateAssociationWorkspace(form)
      setForm({ name: '', short_name: '', primary_color: '#16c784', accent_color: '#243352' })
      await load()
    } catch (err) {
      setError(err.message || 'Could not create the workspace')
    } finally {
      setSaving(false)
    }
  }

  const open = async (id, landOn) => {
    setOpening(id)
    setError('')
    try {
      await switchClub(id, landOn) // hard-reloads on success
    } catch (err) {
      setError(err.message || 'Could not open the workspace')
      setOpening('')
    }
  }

  return (
    <AdminLayout>
      <div className="max-w-3xl mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Association Socials</h1>
          <p className="text-sm text-pb-dim mt-1 leading-relaxed">
            A workspace for an association or competition, with its own name, crest, colours and sponsors and no club behind it.
            Its posts come from a play.cricket.com.au match or grade link and cover every club in that grade: fixtures, results,
            team of the week, lineups, scorecards and player of the match. It never syncs, has no public site and does not show on All Clubs.
          </p>
        </div>

        {error && <div className="mb-4 p-3 rounded border border-pb-red/40 bg-pb-red/10 text-sm text-pb-red">{error}</div>}

        <div className="pb-card p-4 mb-6">
          <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Workspaces</h2>
          {rows === null && <p className="text-sm text-pb-faint">Loading…</p>}
          {rows?.length === 0 && <p className="text-sm text-pb-faint">No association workspaces yet. Create one below.</p>}
          <div className="flex flex-col gap-2">
            {(rows || []).map((w) => (
              <div key={w.id} className="flex flex-wrap items-center gap-3 p-3 rounded border pb-hairline bg-pb-surface2" data-testid="assoc-workspace">
                <div className="w-10 h-10 rounded shrink-0 grid place-items-center overflow-hidden" style={{ background: w.primary_color || '#243352' }}>
                  {w.logo_url
                    ? <img src={`${API_BASE}/images/organisations/${w.id}/logo`} alt="" className="w-full h-full object-contain" />
                    : <span className="font-mono text-xs text-white">{(w.short_name || w.name).slice(0, 2).toUpperCase()}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-pb-text truncate">{w.name}</div>
                  <div className="font-mono text-[10px] text-pb-faint">{w.archived_at ? 'Archived' : (w.short_name || 'No short name')}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => open(w.id, 'admin/social-post')} disabled={!!opening || !!w.archived_at}
                    className="px-3 py-1.5 rounded text-xs font-mono tracking-wide2 disabled:opacity-50"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
                    {opening === w.id ? 'Opening…' : 'Open BetterPosts'}
                  </button>
                  <button onClick={() => open(w.id, 'admin/settings')} disabled={!!opening || !!w.archived_at}
                    className="px-3 py-1.5 rounded border pb-hairline text-xs font-mono tracking-wide2 text-pb-text disabled:opacity-50">
                    Branding
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={create} className="pb-card p-4">
          <h2 className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">New workspace</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className={LABEL_CLS}>Name</span>
              <input className={INPUT_CLS} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="WASTCA" />
            </label>
            <label className="block">
              <span className={LABEL_CLS}>Short name (optional)</span>
              <input className={INPUT_CLS} value={form.short_name} onChange={(e) => setForm({ ...form, short_name: e.target.value })} placeholder="WASTCA" />
            </label>
            <label className="block">
              <span className={LABEL_CLS}>Primary colour</span>
              <input type="color" className="h-10 w-full rounded border pb-hairline bg-pb-surface2" value={form.primary_color} onChange={(e) => setForm({ ...form, primary_color: e.target.value })} />
            </label>
            <label className="block">
              <span className={LABEL_CLS}>Accent colour</span>
              <input type="color" className="h-10 w-full rounded border pb-hairline bg-pb-surface2" value={form.accent_color} onChange={(e) => setForm({ ...form, accent_color: e.target.value })} />
            </label>
          </div>
          <p className="text-[11px] text-pb-faint mt-3 leading-relaxed">Upload the crest, fonts and sponsors from Branding once it is created.</p>
          <button type="submit" disabled={saving}
            className="mt-3 px-4 py-2 rounded text-xs font-mono tracking-wide2 disabled:opacity-50"
            style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
            {saving ? 'Creating…' : 'Create workspace'}
          </button>
        </form>
      </div>
    </AdminLayout>
  )
}
