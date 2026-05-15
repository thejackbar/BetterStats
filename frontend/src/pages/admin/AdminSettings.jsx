import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState({})
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [logoUrl, setLogoUrl] = useState(null)
  const [logoBusy, setLogoBusy] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      setLogoUrl(s.logo_url || null)
      setForm({
        name: s.name || '',
        contact_email: s.contact_email || '',
        primary_color: s.primary_color || '#16c784',
        accent_color: s.accent_color || '#243352',
        theme_mode: s.theme_mode || 'auto',
        player_name_format: s.player_name_format || 'last_first',
      })
    }).catch(() => {})
  }, [])

  const flash = (text) => {
    setMsg(text)
    setTimeout(() => setMsg(''), 3000)
  }

  const handleLogoSelect = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setLogoBusy(true)
    setMsg('')
    try {
      const res = await api.adminUploadLogo(file)
      setLogoUrl(res.logo_url)
      flash('Logo updated')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setLogoBusy(false)
    }
  }

  const handleLogoRemove = async () => {
    setLogoBusy(true)
    setMsg('')
    try {
      await api.adminDeleteLogo()
      setLogoUrl(null)
      flash('Logo removed')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setLogoBusy(false)
    }
  }

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
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Club logo</label>
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded border pb-hairline bg-pb-surface2 flex items-center justify-center overflow-hidden shrink-0">
                {logoUrl
                  ? <img src={logoUrl} alt="Club logo" className="w-full h-full object-contain" />
                  : <span className="font-mono text-[9px] text-pb-faintest">No logo</span>}
              </div>
              <div className="flex flex-col gap-2 min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => fileRef.current?.click()}
                    disabled={logoBusy}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-50"
                  >
                    {logoBusy ? 'Working…' : (logoUrl ? 'Replace logo' : 'Upload logo')}
                  </button>
                  {logoUrl && (
                    <button
                      type="button"
                      onClick={handleLogoRemove}
                      disabled={logoBusy}
                      className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-red transition disabled:opacity-50"
                    >
                      Remove
                    </button>
                  )}
                </div>
                <p className="font-mono text-[10px] text-pb-faintest">
                  PNG, JPG, WEBP or GIF · max 2 MB. With a custom logo set, it appears top-left and the BetterStats logo moves to the top-right.
                </p>
              </div>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={handleLogoSelect}
            />
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

          <div>
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5">Player name format</label>
            <select
              value={form.player_name_format}
              onChange={e => setForm(f => ({ ...f, player_name_format: e.target.value }))}
              className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
            >
              <option value="last_first">Last Name, First Name (e.g. Smith, John)</option>
              <option value="first_last">First Name Last Name (e.g. John Smith)</option>
              <option value="first_initial_last">First Initial Last Name (e.g. J. Smith)</option>
              <option value="last_first_initial">Last Name, First Initial (e.g. Smith, J.)</option>
            </select>
            <p className="font-mono text-[10px] text-pb-faintest mt-1">Applies to all player names across the site</p>
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
