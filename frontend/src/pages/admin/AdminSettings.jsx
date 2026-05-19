import { useState, useEffect, useRef } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { BRAND, COLOR_FIELDS, PALETTE_FIELDS, resolveTheme, buildThemeCss } from '../../lib/theme'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'
const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/

const LABEL = 'font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5'

function ColorField({ label, hint, value, fallback, onChange, onReset }) {
  const isDefault = value.toLowerCase() === fallback.toLowerCase()
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</label>
        {!isDefault && (
          <button type="button" onClick={onReset}
            className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">
            Reset
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input type="color" value={HEX_RE.test(value) ? value : fallback}
          onChange={e => onChange(e.target.value)}
          className="w-10 h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer shrink-0" />
        <input type="text" value={value} onChange={e => onChange(e.target.value)}
          className="flex-1 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm font-mono focus:outline-none focus:border-pb-accent" />
      </div>
      {hint && <p className="font-mono text-[10px] text-pb-faintest mt-1">{hint}</p>}
    </div>
  )
}

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState({})
  const [theme, setTheme] = useState(() => resolveTheme(null))
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [logoUrl, setLogoUrl] = useState(null)
  const [logoBusy, setLogoBusy] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      setLogoUrl(s.logo_url || null)
      setTheme(resolveTheme(s.theme_config))
      setForm({
        name: s.name || '',
        contact_email: s.contact_email || '',
        theme_mode: s.theme_mode || 'auto',
        player_name_format: s.player_name_format || 'last_first',
      })
    }).catch(() => {})
  }, [])

  // Live-preview the edited palette while on this page.
  useEffect(() => {
    const style = document.getElementById('admin-theme-preview') || (() => {
      const el = document.createElement('style')
      el.id = 'admin-theme-preview'
      document.head.appendChild(el)
      return el
    })()
    style.textContent = buildThemeCss(theme)
    return () => { document.getElementById('admin-theme-preview')?.remove() }
  }, [theme])

  const flash = (text) => {
    setMsg(text)
    setTimeout(() => setMsg(''), 3000)
  }

  const setColor = (key, val) => setTheme(t => ({ ...t, [key]: val }))
  const setSeries = (i, val) => setTheme(t => ({
    ...t, chart_series: t.chart_series.map((c, idx) => idx === i ? val : c),
  }))
  const setPalette = (mode, key, val) => setTheme(t => ({
    ...t, [mode]: { ...t[mode], [key]: val },
  }))
  const resetAll = () => setTheme(resolveTheme(null))

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
      await api.adminPatchSettings({ ...form, theme_config: theme })
      flash('Settings saved')
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
      <div className="max-w-2xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-6">Club Settings</h1>

        <form onSubmit={save} className="space-y-6">
          {/* --- Identity --- */}
          <div className="space-y-5">
            <div>
              <label className={LABEL}>Club name</label>
              <input type="text" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className={INPUT_CLS} />
            </div>
            <div>
              <label className={LABEL}>Contact email</label>
              <input type="email" value={form.contact_email}
                onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                className={INPUT_CLS} />
            </div>
          </div>

          {/* --- Logo --- */}
          <div>
            <label className={LABEL}>Club logo</label>
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded border pb-hairline bg-pb-surface2 flex items-center justify-center overflow-hidden shrink-0">
                {logoUrl
                  ? <img src={logoUrl} alt="Club logo" className="w-full h-full object-contain" />
                  : <span className="font-mono text-[9px] text-pb-faintest">No logo</span>}
              </div>
              <div className="flex flex-col gap-2 min-w-0">
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => fileRef.current?.click()} disabled={logoBusy}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-50">
                    {logoBusy ? 'Working…' : (logoUrl ? 'Replace logo' : 'Upload logo')}
                  </button>
                  {logoUrl && (
                    <button type="button" onClick={handleLogoRemove} disabled={logoBusy}
                      className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-red transition disabled:opacity-50">
                      Remove
                    </button>
                  )}
                </div>
                <p className="font-mono text-[10px] text-pb-faintest">
                  PNG, JPG, WEBP or GIF · max 2 MB. With a custom logo set, it appears top-left and the BetterStats logo moves to the top-right.
                </p>
              </div>
            </div>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden" onChange={handleLogoSelect} />
          </div>

          {/* --- Theme + branding --- */}
          <div className="pt-5 pb-hairline-t">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide2">Branding & theme</h2>
              <button type="button" onClick={resetAll}
                className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-red transition uppercase">
                Reset all branding
              </button>
            </div>

            <div className="mb-5">
              <label className={LABEL}>Default theme</label>
              <select value={form.theme_mode}
                onChange={e => setForm(f => ({ ...f, theme_mode: e.target.value }))}
                className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
                <option value="auto">Auto (visitor's system preference)</option>
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
              <p className="font-mono text-[10px] text-pb-faintest mt-1">
                Visitors can still flip the theme themselves with the navbar toggle.
              </p>
            </div>

            <div className="grid sm:grid-cols-2 gap-x-4 gap-y-4">
              {COLOR_FIELDS.map(f => (
                <ColorField key={f.key} label={f.label} hint={f.hint}
                  value={theme[f.key]} fallback={BRAND[f.key]}
                  onChange={v => setColor(f.key, v)}
                  onReset={() => setColor(f.key, BRAND[f.key])} />
              ))}
            </div>

            {/* Chart series palette */}
            <div className="mt-5">
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Chart series palette</label>
                <button type="button" onClick={() => setColor('chart_series', [...BRAND.chart_series])}
                  className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">Reset</button>
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mb-2">Used for multi-segment charts such as dismissal breakdowns.</p>
              <div className="flex flex-wrap gap-2">
                {theme.chart_series.map((c, i) => (
                  <input key={i} type="color" value={HEX_RE.test(c) ? c : '#888888'}
                    onChange={e => setSeries(i, e.target.value)}
                    className="w-9 h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer" />
                ))}
              </div>
            </div>

            {/* Per-theme surfaces */}
            {['light', 'dark'].map(mode => (
              <div key={mode} className="mt-5">
                <div className="flex items-center justify-between mb-2">
                  <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{mode} theme — background & text</label>
                  <button type="button"
                    onClick={() => setTheme(t => ({ ...t, [mode]: { ...BRAND[mode] } }))}
                    className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">Reset</button>
                </div>
                <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
                  {PALETTE_FIELDS.map(f => (
                    <div key={f.key} className="flex flex-col items-center gap-1">
                      <input type="color"
                        value={HEX_RE.test(theme[mode][f.key]) ? theme[mode][f.key] : BRAND[mode][f.key]}
                        onChange={e => setPalette(mode, f.key, e.target.value)}
                        className="w-full h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer" />
                      <span className="font-mono text-[8px] text-pb-faintest text-center leading-tight">{f.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* --- Player name format --- */}
          <div className="pt-5 pb-hairline-t">
            <label className={LABEL}>Player name format</label>
            <select value={form.player_name_format}
              onChange={e => setForm(f => ({ ...f, player_name_format: e.target.value }))}
              className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
              <option value="last_first">Last Name, First Name (e.g. Smith, John)</option>
              <option value="first_last">First Name Last Name (e.g. John Smith)</option>
              <option value="first_initial_last">First Initial Last Name (e.g. J. Smith)</option>
              <option value="last_first_initial">Last Name, First Initial (e.g. Smith, J.)</option>
            </select>
            <p className="font-mono text-[10px] text-pb-faintest mt-1">Applies to all player names across the site</p>
          </div>

          <div className="pt-2 flex items-center gap-4">
            <button type="submit" disabled={saving}
              className="px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
              {saving ? 'Saving…' : 'SAVE SETTINGS'}
            </button>
            {msg && <span className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>{msg}</span>}
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
