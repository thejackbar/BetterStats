import { useState, useEffect } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'

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
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <div className="max-w-lg">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-6">Club Settings</h1>

        <form onSubmit={save} className="space-y-5">
          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Club name</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className={INPUT_CLS}
            />
          </div>

          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Contact email</label>
            <input
              type="email"
              value={form.contact_email}
              onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
              className={INPUT_CLS}
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Primary colour</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={form.primary_color}
                  onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                  className="w-10 h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer"
                />
                <input
                  type="text"
                  value={form.primary_color}
                  onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                  className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-accent"
                />
              </div>
            </div>
            <div className="flex-1">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Accent colour</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={form.accent_color}
                  onChange={e => setForm(f => ({ ...f, accent_color: e.target.value }))}
                  className="w-10 h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer"
                />
                <input
                  type="text"
                  value={form.accent_color}
                  onChange={e => setForm(f => ({ ...f, accent_color: e.target.value }))}
                  className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-accent"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Theme mode</label>
            <select
              value={form.theme_mode}
              onChange={e => setForm(f => ({ ...f, theme_mode: e.target.value }))}
              className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
            >
              <option value="auto">Auto (system)</option>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </div>

          <div className="pt-2 flex items-center gap-4">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {saving ? 'Saving…' : 'SAVE SETTINGS'}
            </button>
            {msg && <span className="font-mono text-[11px] text-pb-accent" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
          </div>
        </form>

        <div className="mt-8 pt-6 pb-hairline-t">
          <div className="font-mono text-[10px] text-pb-faint space-y-1">
            <div>Club slug: <span className="text-pb-dim">{settings.slug}</span></div>
            <div>Club ID: <span className="text-pb-faintest">{settings.id}</span></div>
          </div>
        </div>
      </div>
    </AdminLayout>
  )
}
