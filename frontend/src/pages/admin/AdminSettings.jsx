import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import ImageEditorModal from '../../components/ImageEditorModal'
import {
  BRAND, COLOR_FIELDS, HONOUR_FIELDS, PALETTE_FIELDS, resolveTheme, buildThemeCss,
  deriveDarkPalette, gradientCss, resolveClubFonts, DISPLAY_FONT_PRESETS, BODY_FONT_PRESETS, MONO_FONT_PRESETS,
  FONT_WEIGHT_CHOICES, FONT_WEIGHT_DEFAULTS,
} from '../../lib/theme'
import { validateImageFile } from '../../lib/validation'
import { BASE_URL } from '../../data/marketing'
import { CATEGORY_LABELS } from '../../lib/gradeCategories'

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

const FONT_ALLOWED_EXTS = '.woff2,.woff,.ttf,.otf'
const FONT_ROLE_LABEL = { display: 'Heading', body: 'Body', mono: 'Numbers' }

function FontRoleField({ role, label, hint, presets, config, sampleText, busy, onSelectPreset, onSelectDefault, onUpload, onRemove, onSelectWeight }) {
  const fileRef = useRef(null)
  const source = config?.source
  const weight = config?.weight || FONT_WEIGHT_DEFAULTS[role]

  // Whether this font can actually produce a bold. A font file holds one weight
  // unless it is a variable font, so most uploads cannot — and a bold asked of
  // one gets synthesised by the browser, which reads muddy and too dark. Worth
  // saying out loud on this screen: an admin whose headings stopped looking
  // bold should know it is the font, not a failed upload.
  const preset = source === 'preset' ? presets.find(p => p.key === config.preset) : null
  const metrics = source === 'upload' ? (config.metrics || {}) : null
  const oneWeight = preset ? !!preset.oneWeight : (metrics ? !metrics.variable : false)
  const fileWeight = metrics && !metrics.variable ? metrics.weight : null

  const handlePick = (e) => {
    const value = e.target.value
    if (!value) { onSelectDefault(); return }
    onSelectPreset(value)
  }

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const stem = file.name.replace(/\.[^.]+$/, '')
    const family = window.prompt('Font name (shown in Typography settings)', stem) || stem
    onUpload(file, family)
  }

  return (
    <div>
      <label className={LABEL}>{label}</label>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <select value={source === 'preset' ? config.preset : ''} onChange={handlePick} disabled={busy}
          className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
          <option value="">App default</option>
          {presets.map(p => <option key={p.key} value={p.key}>{p.name}</option>)}
        </select>
        <button type="button" onClick={() => fileRef.current?.click()} disabled={busy}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-50">
          {busy ? 'Uploading…' : 'Upload your own font'}
        </button>
        {source === 'upload' && (
          <button type="button" onClick={onRemove} disabled={busy}
            className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-red transition disabled:opacity-50">
            Remove
          </button>
        )}
      </div>
      <input ref={fileRef} type="file" accept={FONT_ALLOWED_EXTS} className="hidden" onChange={handleFile} />
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <label className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Weight</label>
        <select value={weight} onChange={e => onSelectWeight(Number(e.target.value))} disabled={busy}
          className="bg-pb-surface2 border pb-hairline rounded px-3 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
          {FONT_WEIGHT_CHOICES.map(w => (
            <option key={w.value} value={w.value}>
              {w.label} ({w.value}){w.value === FONT_WEIGHT_DEFAULTS[role] ? ' — default' : ''}
            </option>
          ))}
        </select>
      </div>
      {source === 'upload' && (
        <p className="font-mono text-[10px] text-pb-faint mb-1">Uploaded: {config.family}</p>
      )}
      {oneWeight && (
        <p className="font-mono text-[10px] text-pb-amber mb-1">
          This font has one weight{fileWeight ? ` (${fileWeight})` : ''}, so it can't be bolded.
          We render it as drawn rather than letting the browser fake a bold, which looks heavy and smudged.
        </p>
      )}
      <p className="font-mono text-[10px] text-pb-faintest">{hint}</p>
      <p className="mt-2 text-lg text-pb-text truncate"
        style={{ fontFamily: `var(--pb-font-${role})`, fontWeight: weight }}>
        {sampleText}
      </p>
    </div>
  )
}

function PrimaryAdminCard() {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const load = () => api.getPrimaryAdmin().then(setData).catch(() => setData(null))
  useEffect(() => { load() }, [])

  if (!data || !data.admins?.length) return null

  const primary = data.admins.find(a => a.is_primary_admin)
  const others = data.admins.filter(a => !a.is_primary_admin)

  const transfer = async (userId) => {
    if (!userId) return
    const to = data.admins.find(a => a.user_id === userId)
    if (!window.confirm(`Make ${to?.display_name || to?.username} the primary admin? Only the primary admin can request paid subscriptions.`)) return
    setBusy(true)
    setMsg('')
    try {
      await api.transferPrimaryAdmin(userId)
      setMsg('Primary admin updated')
      await load()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-5 mb-6">
      <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide2 mb-1">Primary admin</h2>
      <p className="text-pb-faint text-sm mb-3">
        The primary admin is the club's owner account. Only they can request a paid subscription
        to a module; any club admin can request a trial.
      </p>
      <p className="text-sm text-pb-text mb-3">
        Current: <span className="font-medium">{primary ? (primary.display_name || primary.username) : '— none —'}</span>
        {primary?.is_me && <span className="text-pb-faint"> (you)</span>}
      </p>
      {data.can_transfer ? (
        others.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="font-mono text-[10px] text-pb-faint">Transfer to</label>
            <select
              defaultValue=""
              disabled={busy}
              onChange={e => transfer(e.target.value)}
              className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent disabled:opacity-50"
            >
              <option value="" disabled>Choose an admin…</option>
              {others.map(a => (
                <option key={a.user_id} value={a.user_id}>{a.display_name || a.username}</option>
              ))}
            </select>
          </div>
        ) : (
          <p className="font-mono text-[10px] text-pb-faintest">Add another club admin to be able to hand this over.</p>
        )
      ) : (
        <p className="font-mono text-[10px] text-pb-faintest">Only the current primary admin can reassign this.</p>
      )}
      {msg && <p className="font-mono text-[11px] mt-2" style={{ color: 'var(--pb-accent)' }}>{msg}</p>}
    </div>
  )
}

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [form, setForm] = useState({})
  const [theme, setTheme] = useState(() => resolveTheme(null))
  const [msg, setMsg] = useState('')
  const [msgKind, setMsgKind] = useState('success') // 'success' | 'error'
  const [saving, setSaving] = useState(false)
  const [logoUrl, setLogoUrl] = useState(null)
  const [logoBusy, setLogoBusy] = useState(false)
  const [logoEditorSource, setLogoEditorSource] = useState(null)
  const [pinInput, setPinInput] = useState('')
  const [fontConfig, setFontConfig] = useState({})
  const [fontMeta, setFontMeta] = useState({})
  const [fontBusy, setFontBusy] = useState({ display: false, body: false, mono: false })
  const fileRef = useRef(null)

  useEffect(() => {
    api.adminGetSettings().then(s => {
      setSettings(s)
      setLogoUrl(s.logo_url || null)
      setTheme(resolveTheme(s.theme_config))
      setFontConfig(s.font_config || {})
      setFontMeta({
        font_display_url: s.font_display_url, font_display_format: s.font_display_format,
        font_body_url: s.font_body_url, font_body_format: s.font_body_format,
        font_mono_url: s.font_mono_url, font_mono_format: s.font_mono_format,
      })
      setForm({
        name: s.name || '',
        contact_email: s.contact_email || '',
        theme_mode: s.theme_mode || 'auto',
        player_name_format: s.player_name_format || 'last_first',
        dormancy_months: s.dormancy_months ?? 24,
        select_show_age: !!s.select_show_age,
        // null (not 0/'') is "every player" — the PATCH reads presence, so a
        // null here genuinely clears any age limit the club had set.
        select_show_age_under: s.select_show_age_under ?? null,
        public_show_role: !!s.public_show_role,
        public_show_batting: !!s.public_show_batting,
        public_show_bowling: !!s.public_show_bowling,
        public_show_opening: !!s.public_show_opening,
        public_show_gender: !!s.public_show_gender,
        include_fill_ins_in_stats: !!s.include_fill_ins_in_stats,
        stats_grade_categories: s.effective_stats_grade_categories || [],
        stats_auto_show_played_grades: s.stats_auto_show_played_grades !== false,
        public_header_logo: !!s.public_header_logo,
        password_protected: !!s.password_protected,
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
    const fonts = resolveClubFonts({ font_config: fontConfig, ...fontMeta })
    style.textContent = buildThemeCss(theme, fonts)
    return () => { document.getElementById('admin-theme-preview')?.remove() }
  }, [theme, fontConfig, fontMeta])

  const flash = (text) => {
    setMsg(text)
    setMsgKind('success')
    setTimeout(() => setMsg(''), 3000)
  }
  const flashError = (text) => {
    setMsg(text)
    setMsgKind('error')
  }

  const publicUrl = settings?.slug ? `${BASE_URL}/${settings.slug}` : ''
  const copyPublicUrl = async () => {
    if (!publicUrl) return
    try {
      await navigator.clipboard.writeText(publicUrl)
      flash('Link copied')
    } catch {
      flashError('Could not copy link — select and copy manually')
    }
  }

  const setColor = (key, val) => setTheme(t => ({ ...t, [key]: val }))
  const setSeries = (i, val) => setTheme(t => ({
    ...t, chart_series: t.chart_series.map((c, idx) => idx === i ? val : c),
  }))
  const setPalette = (mode, key, val) => setTheme(t => ({
    ...t, [mode]: { ...t[mode], [key]: val },
  }))
  const resetAll = () => setTheme(resolveTheme(null))

  const handleLogoSelect = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const err = validateImageFile(file)
    if (err) {
      flashError(err)
      return
    }
    setLogoEditorSource(file)
  }

  const handleLogoUpload = async (file) => {
    setLogoEditorSource(null)
    setLogoBusy(true)
    setMsg('')
    try {
      const res = await api.adminUploadLogo(file)
      setLogoUrl(res.logo_url)
      flash('Logo updated')
    } catch (err) {
      flashError(err.message)
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
      flashError(err.message)
    } finally {
      setLogoBusy(false)
    }
  }

  // The chosen weight survives a change of family — it is a separate decision,
  // and losing it every time someone tries another font would be maddening.
  const selectFontPreset = (role, preset) =>
    setFontConfig(c => ({ ...c, [role]: { ...(c[role] || {}), source: 'preset', preset } }))
  const selectFontDefault = (role) =>
    setFontConfig((c) => {
      const weight = c[role]?.weight
      const n = { ...c }
      if (weight) n[role] = { source: 'default', weight }
      else delete n[role]
      return n
    })
  const selectFontWeight = (role, weight) =>
    setFontConfig((c) => {
      const entry = { ...(c[role] || { source: 'default' }) }
      if (weight === FONT_WEIGHT_DEFAULTS[role]) delete entry.weight
      else entry.weight = weight
      if (entry.source === 'default' && !entry.weight) {
        const n = { ...c }
        delete n[role]
        return n
      }
      return { ...c, [role]: entry }
    })

  const uploadFont = async (role, file, family) => {
    setFontBusy(b => ({ ...b, [role]: true }))
    setMsg('')
    try {
      const res = await api.adminUploadFont(role, file, family)
      setFontConfig(res.font_config || {})
      setFontMeta({
        font_display_url: res.font_display_url, font_display_format: res.font_display_format,
        font_body_url: res.font_body_url, font_body_format: res.font_body_format,
        font_mono_url: res.font_mono_url, font_mono_format: res.font_mono_format,
      })
      flash(`${FONT_ROLE_LABEL[role] || role} font updated`)
    } catch (err) {
      flashError(err.message)
    } finally {
      setFontBusy(b => ({ ...b, [role]: false }))
    }
  }

  const removeFont = async (role) => {
    setFontBusy(b => ({ ...b, [role]: true }))
    setMsg('')
    try {
      const res = await api.adminDeleteFont(role)
      setFontConfig(res.font_config || {})
      setFontMeta(m => ({ ...m, [`font_${role}_url`]: null, [`font_${role}_format`]: null }))
      flash(`${FONT_ROLE_LABEL[role] || role} font removed`)
    } catch (err) {
      flashError(err.message)
    } finally {
      setFontBusy(b => ({ ...b, [role]: false }))
    }
  }

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMsg('')
    try {
      const payload = { ...form, theme_config: theme, font_config: fontConfig }
      if (/^\d{4}$/.test(pinInput)) payload.access_pin = pinInput
      await api.adminPatchSettings(payload)
      setPinInput('')
      flash('Settings saved')
      api.adminGetSettings().then(setSettings).catch(() => {})
    } catch (err) {
      flashError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const canEnablePasswordProtect = settings && ['trial', 'active'].includes(settings.subscription_status)

  if (!settings) return (
    <AdminLayout>
      <div className="font-mono text-[11px] text-pb-faint">Loading…</div>
    </AdminLayout>
  )

  return (
    <AdminLayout>
      <div className="max-w-2xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-6">Club Settings</h1>

        <PrimaryAdminCard />

        <form onSubmit={save} className="space-y-6">
          {/* --- Identity --- */}
          <div className="space-y-5">
            <div>
              <label className={LABEL}>Club name</label>
              <input type="text" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className={INPUT_CLS} />
              {publicUrl && (
                <div className="flex items-center gap-2 mt-1.5">
                  <a
                    href={publicUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[11px] hover:underline transition-colors truncate"
                    style={{ color: 'var(--pb-accent)' }}
                  >
                    {publicUrl}
                  </a>
                  <button
                    type="button"
                    onClick={copyPublicUrl}
                    title="Copy link"
                    aria-label="Copy public club link"
                    className="text-pb-faint hover:text-pb-text transition-colors shrink-0"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                      <rect x="9" y="9" width="11" height="11" rx="2" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 15V5a2 2 0 012-2h10" />
                    </svg>
                  </button>
                </div>
              )}
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
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => fileRef.current?.click()} disabled={logoBusy}
                    className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-50">
                    {logoBusy ? 'Working…' : (logoUrl ? 'Replace logo' : 'Upload logo')}
                  </button>
                  {logoUrl && (
                    <button type="button" onClick={() => setLogoEditorSource(logoUrl)} disabled={logoBusy}
                      className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-text hover:bg-pb-surface2 transition disabled:opacity-50">
                      Edit (crop / remove background)
                    </button>
                  )}
                  {logoUrl && (
                    <button type="button" onClick={handleLogoRemove} disabled={logoBusy}
                      className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-red transition disabled:opacity-50">
                      Remove
                    </button>
                  )}
                </div>
                <p className="font-mono text-[10px] text-pb-faintest">
                  PNG, JPG, WEBP or GIF · max 15 MB. Use Edit to crop or remove the background on the existing logo. With a custom logo set, it appears top-left and the BetterCricket logo moves to the top-right.
                </p>
                <label className="flex items-start gap-2.5 mt-3 cursor-pointer">
                  <input type="checkbox" checked={!!form.public_header_logo}
                    onChange={e => setForm(f => ({ ...f, public_header_logo: e.target.checked }))}
                    className="mt-0.5 w-4 h-4 accent-pb-accent shrink-0" />
                  <span>
                    <span className="text-sm text-pb-text">Show the logo on your club dashboard</span>
                    <span className="block font-mono text-[10px] text-pb-faintest mt-0.5">
                      Puts the crest beside your club name at the top of the public dashboard, as well as in the menu bar.
                    </span>
                  </span>
                </label>
              </div>
            </div>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden" onChange={handleLogoSelect} />
            <ImageEditorModal
              open={!!logoEditorSource}
              source={logoEditorSource}
              title="Edit Club Logo"
              aspect={null}
              outputType="image/png"
              outputName="club-logo.png"
              onCancel={() => setLogoEditorSource(null)}
              onApply={handleLogoUpload}
            />
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

            {/* Gradient preview — shows how the two accents pair up */}
            <div className="mt-4 rounded-md border pb-hairline overflow-hidden">
              <div className="h-9" style={{ background: gradientCss(theme.accent, theme.accent2) }} />
              <p className="font-mono text-[10px] text-pb-faintest px-2.5 py-1.5">
                Accent → secondary gradient, used on banners, share cards and the dashboard header.
              </p>
            </div>

            {/* Honour category colours */}
            <div className="mt-6">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1">Honour categories</label>
              <p className="font-mono text-[10px] text-pb-faintest mb-3">Colour-codes achievement badges and the pills under a player's name.</p>
              <div className="grid sm:grid-cols-2 gap-x-4 gap-y-4">
                {HONOUR_FIELDS.map(f => (
                  <ColorField key={f.key} label={f.label} hint={f.hint}
                    value={theme[f.key]} fallback={BRAND[f.key]}
                    onChange={v => setColor(f.key, v)}
                    onReset={() => setColor(f.key, BRAND[f.key])} />
                ))}
              </div>
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

            {/* Light theme surfaces — bg / cards / text picked individually */}
            <div className="mt-5">
              <div className="flex items-center justify-between mb-2">
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">light theme — background &amp; text</label>
                <button type="button"
                  onClick={() => setTheme(t => ({ ...t, light: { ...BRAND.light } }))}
                  className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">Reset</button>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {PALETTE_FIELDS.map(f => (
                  <div key={f.key} className="flex flex-col gap-1">
                    <input type="color"
                      value={HEX_RE.test(theme.light[f.key]) ? theme.light[f.key] : BRAND.light[f.key]}
                      onChange={e => setPalette('light', f.key, e.target.value)}
                      className="w-full h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer" />
                    <span className="font-mono text-[9px] text-pb-faintest leading-tight">{f.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Dark theme — pick one base colour; cards/panels/borders derive from it */}
            <div className="mt-5">
              <div className="flex items-center justify-between mb-2">
                <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">dark theme — background</label>
                <button type="button"
                  onClick={() => setTheme(t => ({ ...t, dark: { ...BRAND.dark } }))}
                  className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-accent transition">Reset</button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1">
                  <input type="color"
                    value={HEX_RE.test(theme.dark.bg) ? theme.dark.bg : BRAND.dark.bg}
                    onChange={e => setTheme(t => ({ ...t, dark: deriveDarkPalette(e.target.value, t.dark) }))}
                    className="w-full h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer" />
                  <span className="font-mono text-[9px] text-pb-faintest leading-tight">Base background</span>
                </div>
                <div className="flex flex-col gap-1">
                  <input type="color"
                    value={HEX_RE.test(theme.dark.text) ? theme.dark.text : BRAND.dark.text}
                    onChange={e => setPalette('dark', 'text', e.target.value)}
                    className="w-full h-9 rounded border pb-hairline bg-pb-surface2 cursor-pointer" />
                  <span className="font-mono text-[9px] text-pb-faintest leading-tight">Text</span>
                </div>
              </div>
              {/* Derived ramp: base → cards → borders, so the operator sees the cohesion */}
              <div className="flex items-center gap-1.5 mt-2">
                {['bg', 'surface', 'surface2', 'hairline', 'hairline2'].map(k => (
                  <span key={k} title={k} className="h-5 flex-1 rounded border pb-hairline"
                    style={{ background: theme.dark[k] }} />
                ))}
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mt-1.5">
                Cards, panels and borders are derived from the base so a custom dark colour (navy, maroon…) stays cohesive.
              </p>
            </div>
          </div>

          {/* --- Typography --- */}
          <div className="pt-5 pb-hairline-t">
            <h2 className="font-display font-bold text-sm text-pb-text uppercase tracking-wide2 mb-1">Typography</h2>
            <p className="font-mono text-[10px] text-pb-faintest mb-4">
              Pick a built-in font or upload your own (e.g. to match your club's own website) — separately for headings and body text.
            </p>
            <div className="space-y-6">
              <FontRoleField role="display" label="Headings" hint="Page titles, navigation, section headers. Font files: woff2, woff, ttf or otf, max 6 MB."
                presets={DISPLAY_FONT_PRESETS} config={fontConfig.display} busy={fontBusy.display}
                sampleText="The Applecross Cricket Club"
                onSelectPreset={p => selectFontPreset('display', p)}
                onSelectDefault={() => selectFontDefault('display')}
                onUpload={(file, family) => uploadFont('display', file, family)}
                onSelectWeight={w => selectFontWeight('display', w)}
                onRemove={() => removeFont('display')} />
              <FontRoleField role="body" label="Body text" hint="Ordinary paragraph and table text across the site. Font files: woff2, woff, ttf or otf, max 6 MB."
                presets={BODY_FONT_PRESETS} config={fontConfig.body} busy={fontBusy.body}
                sampleText="Season averages, records and match reports."
                onSelectPreset={p => selectFontPreset('body', p)}
                onSelectDefault={() => selectFontDefault('body')}
                onUpload={(file, family) => uploadFont('body', file, family)}
                onSelectWeight={w => selectFontWeight('body', w)}
                onRemove={() => removeFont('body')} />
              <FontRoleField role="mono" label="Numbers & stats" hint="Scores, averages and tabular figures across the site. Font files: woff2, woff, ttf or otf, max 6 MB."
                presets={MONO_FONT_PRESETS} config={fontConfig.mono} busy={fontBusy.mono}
                sampleText="1,234 runs · 56 wickets · 89.4 avg"
                onSelectPreset={p => selectFontPreset('mono', p)}
                onSelectDefault={() => selectFontDefault('mono')}
                onUpload={(file, family) => uploadFont('mono', file, family)}
                onSelectWeight={w => selectFontWeight('mono', w)}
                onRemove={() => removeFont('mono')} />
            </div>
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

          {/* --- BetterSelect settings moved to their own screen ---
               The dormant-player window, default side size and age display now
               live with the association rules they belong to, under
               BetterSelect → Setup, which is gated on MANAGE_SELECTIONS —
               the person picking sides, rather than whoever edits the club's
               colours. Nothing else on this page changed. */}
          <div className="pt-5 pb-hairline-t">
            <label className={LABEL}>BetterSelect</label>
            <p className="font-mono text-[10px] text-pb-faintest mb-3">
              The dormant-player window, default side size and whether ages show on the selection
              board have moved in with your association's selection rules.
            </p>
            <Link to="/admin/betterselect/rules"
              className="inline-flex items-center gap-1.5 text-sm text-pb-accent hover:underline">
              Selection rules &amp; settings →
            </Link>
          </div>

          {/* --- Public profile: visible player attributes --- */}
          <div className="pt-5 pb-hairline-t">
            <label className={LABEL}>Public profile — visible attributes</label>
            <p className="font-mono text-[10px] text-pb-faintest mb-3">
              Choose which descriptive player attributes appear on the public player profile. Overseas status is always shown.
            </p>
            <div className="space-y-2.5">
              {[
                ['public_show_role', 'Player role', 'e.g. All Rounder, Wicketkeeper-Batter'],
                ['public_show_batting', 'Batting hand', 'Right / left handed'],
                ['public_show_bowling', 'Bowling style', 'e.g. Right-arm fast, Off spin'],
                ['public_show_opening', 'Opening batter', 'Shows an OPENER badge under the name'],
                ['public_show_gender', 'Gender', 'Male / female'],
              ].map(([key, label, hint]) => (
                <label key={key} className="flex items-start gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={!!form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.checked }))}
                    className="accent-pb-accent mt-0.5 shrink-0" />
                  <span className="leading-tight">
                    <span className="text-pb-text text-sm">{label}</span>
                    <span className="font-mono text-[10px] text-pb-faintest block">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* --- Fill-in players on the scorecard --- */}
          <div className="pt-5 pb-hairline-t">
            <label className={LABEL}>Fill-in players</label>
            <p className="font-mono text-[10px] text-pb-faintest mb-3">
              A borrowed player's runs and wickets always show on a game's batting/bowling
              card. This decides whether they also show by name in the partnerships and
              fielding cards on that same scorecard, or are left out of those two. Never
              affects club records — a fill-in never counts toward an all-time record either way.
            </p>
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input type="checkbox" checked={!!form.include_fill_ins_in_stats}
                onChange={e => setForm(f => ({ ...f, include_fill_ins_in_stats: e.target.checked }))}
                className="accent-pb-accent mt-0.5 shrink-0" />
              <span className="leading-tight">
                <span className="text-pb-text text-sm">Show fill-ins in partnerships &amp; fielding</span>
                <span className="font-mono text-[10px] text-pb-faintest block">Off shows those two cards with registered players only</span>
              </span>
            </label>
          </div>

          {/* --- Which grades count towards stats --- */}
          {(settings.available_grade_categories || []).length > 1 && (
            <div className="pt-5 pb-hairline-t">
              <label className={LABEL}>Stats by grade</label>
              <p className="font-mono text-[10px] text-pb-faintest mb-3">
                Which of your grades count towards career totals, leaderboards and club
                records. Junior grades are left out by default, so an Under-14 season
                doesn't sit inside a senior batting average — a player who made 200
                against other 14-year-olds and 50 in first grade reads as a first-grade
                batsman.
              </p>
              <p className="font-mono text-[10px] text-pb-faintest mb-3">
                This is what a visitor sees first, not a wall. Every stats page has an
                Include row for switching a category back on, and nothing is deleted or
                hidden — the figures come straight back. Picking a specific grade from a
                Grade dropdown always shows that grade, whatever is ticked here.
              </p>
              <div className="space-y-2">
                {(settings.available_grade_categories || []).map(key => (
                  <label key={key} className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      disabled={key === 'senior'}
                      checked={(form.stats_grade_categories || []).includes(key)}
                      onChange={e => setForm(f => {
                        const cur = f.stats_grade_categories || []
                        return {
                          ...f,
                          stats_grade_categories: e.target.checked
                            ? [...cur, key]
                            : cur.filter(c => c !== key),
                        }
                      })}
                      className="accent-pb-accent mt-0.5 shrink-0 disabled:opacity-50" />
                    <span className="leading-tight">
                      <span className="text-pb-text text-sm">{CATEGORY_LABELS[key] || key} grades count by default</span>
                      {key === 'senior' && (
                        <span className="font-mono text-[10px] text-pb-faintest block">
                          Always counted — it's the baseline the others are added to
                        </span>
                      )}
                    </span>
                  </label>
                ))}
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mt-2">
                A grade's category is set on the Grades screen, under Merge Grades. A grade
                nobody has classified is worked out from its name, so Under 14s, Colts and
                Year 7 are picked up without anyone labelling them. Untick everything here
                to go back to the standard default.
              </p>

              <label className="flex items-start gap-2.5 cursor-pointer mt-4 pt-4 pb-hairline-t">
                <input
                  type="checkbox"
                  checked={!!form.stats_auto_show_played_grades}
                  onChange={e => setForm(f => ({ ...f, stats_auto_show_played_grades: e.target.checked }))}
                  className="accent-pb-accent mt-0.5 shrink-0" />
                <span className="leading-tight">
                  <span className="text-pb-text text-sm">Show a player the grades they actually played</span>
                  <span className="font-mono text-[10px] text-pb-faintest block mt-1">
                    A 13-year-old who has only ever played junior cricket would otherwise
                    open their own profile on a page of zeroes. With this on, a profile
                    that would have nothing to show counts the grades that player did play
                    and says so at the top. It only changes what loads first — anyone can
                    still switch a category on or off themselves, and it never affects the
                    Leaderboard or Records.
                  </span>
                </span>
              </label>
            </div>
          )}

          {/* --- Password protection --- */}
          <div className="pt-5 pb-hairline-t">
            <label className={LABEL}>Password protection</label>
            <p className="font-mono text-[10px] text-pb-faintest mb-3">
              Make your public page private behind a 4-digit PIN — share it internally
              (committee, teammates) without it being publicly visible. This doesn't
              affect your own admin login.
            </p>
            <label className={`flex items-start gap-2.5 ${canEnablePasswordProtect || form.password_protected ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'}`}>
              <input type="checkbox" checked={!!form.password_protected}
                disabled={!canEnablePasswordProtect && !form.password_protected}
                onChange={e => setForm(f => ({ ...f, password_protected: e.target.checked }))}
                className="accent-pb-accent mt-0.5 shrink-0" />
              <span className="leading-tight">
                <span className="text-pb-text text-sm">Password protect this page</span>
                <span className="font-mono text-[10px] text-pb-faintest block">
                  {settings?.password_protect_reason === 'trial_ended'
                    ? "Currently locked by BetterCricket (trial ended) — get in touch to unlock."
                    : 'Visitors must enter the PIN below to view your public page'}
                </span>
              </span>
            </label>
            {!canEnablePasswordProtect && !form.password_protected && (
              <p className="font-mono text-[10px] text-pb-faintest mt-2">
                Only available while your club is on a trial or an active subscription.
              </p>
            )}
            <div className="mt-3 max-w-[220px]">
              <label className={LABEL}>{settings?.has_pin ? 'Change PIN' : 'Set a 4-digit PIN'}</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={4}
                value={pinInput}
                onChange={e => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 4))}
                placeholder={settings?.has_pin ? '••••' : '0000'}
                className={INPUT_CLS + ' font-mono tracking-[0.3em] text-center'}
              />
              {settings?.has_pin && !pinInput && (
                <p className="font-mono text-[10px] text-pb-faintest mt-1">Leave blank to keep the current PIN</p>
              )}
            </div>
          </div>

          <div className="pt-2 flex items-center gap-4">
            <button type="submit" disabled={saving}
              className="px-5 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
              {saving ? 'Saving…' : 'SAVE SETTINGS'}
            </button>
            {msg && (
              <span
                className="font-mono text-[11px]"
                style={{ color: msgKind === 'error' ? 'var(--pb-negative)' : 'var(--pb-accent)' }}
              >
                {msg}
              </span>
            )}
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
