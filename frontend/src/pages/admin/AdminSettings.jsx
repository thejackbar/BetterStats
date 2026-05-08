import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState({})
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      setForm({
        name: s.name || '',
        contact_email: s.contact_email || '',
        primary_color: s.primary_color || '#16c784',
        accent_color: s.accent_color || '#243352',
        theme_mode: s.theme_mode || 'auto',
      })
    }).catch(() => {})
  }, [])

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      await api.adminPatchSettings(form)
      setMsg('Settings saved')
      setTimeout(() => setMsg(''), 3000)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!settings) return (
    <AdminLayout>
      <div className="text-slate-400 text-sm">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <div className="max-w-lg">
        <h1 className="text-xl font-display font-bold text-white mb-6">Club Settings</h1>

        <form onSubmit={save} className="space-y-5">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Club name</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Contact email</label>
            <input
              type="email"
              value={form.contact_email}
              onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
              className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm text-slate-400 mb-1">Primary colour</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={form.primary_color}
                  onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                  className="w-10 h-8 rounded border border-navy-600 bg-navy-800 cursor-pointer"
                />
                <input
                  type="text"
                  value={form.primary_color}
                  onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                  className="flex-1 bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-accent"
                />
              </div>
            </div>
            <div className="flex-1">
              <label className="block text-sm text-slate-400 mb-1">Accent colour</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={form.accent_color}
                  onChange={e => setForm(f => ({ ...f, accent_color: e.target.value }))}
                  className="w-10 h-8 rounded border border-navy-600 bg-navy-800 cursor-pointer"
                />
                <input
                  type="text"
                  value={form.accent_color}
                  onChange={e => setForm(f => ({ ...f, accent_color: e.target.value }))}
                  className="flex-1 bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-accent"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Theme mode</label>
            <select
              value={form.theme_mode}
              onChange={e => setForm(f => ({ ...f, theme_mode: e.target.value }))}
              className="bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
            >
              <option value="auto">Auto (system)</option>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </div>

          <div className="pt-2 flex items-center gap-4">
            <button type="submit" disabled={saving} className="btn-primary disabled:opacity-50">
              {saving ? 'Saving…' : 'Save settings'}
            </button>
            {msg && <span className="text-sm text-accent">{msg}</span>}
          </div>
        </form>

        <div className="mt-8 pt-6 border-t border-navy-800">
          <div className="text-sm text-slate-500">
            <div className="mb-1">Club slug: <span className="font-mono text-slate-300">{settings.slug}</span></div>
            <div>Club ID: <span className="font-mono text-slate-500 text-xs">{settings.id}</span></div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
