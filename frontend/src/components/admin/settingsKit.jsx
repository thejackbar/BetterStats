// Settings controls shared by BetterCricket's and BetterFootball's settings
// pages. Both talk to the shared api client, which is base-aware, so on the
// football app the same calls reach the football backend's own endpoints at the
// same paths. One copy, so the two sports cannot drift on how a font or the
// primary admin is chosen.
import { useState, useEffect, useRef } from 'react'
import { api, rebaseApiUrl } from '../../lib/api'
import {
  buildThemeCss, resolveClubFonts, resolveTheme, DISPLAY_FONT_PRESETS, BODY_FONT_PRESETS, MONO_FONT_PRESETS,
  FONT_WEIGHT_CHOICES, FONT_WEIGHT_DEFAULTS,
} from '../../lib/theme'

const LABEL = 'font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1.5'
const FONT_ALLOWED_EXTS = '.woff2,.woff,.ttf,.otf'

export function FontRoleField({ role, label, hint, presets, config, sampleText, busy, onSelectPreset, onSelectDefault, onUpload, onRemove, onSelectWeight }) {
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

export function PrimaryAdminCard() {
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


const FONT_ROLES = [
  ['display', 'Headings', 'Page titles, navigation, section headers.', DISPLAY_FONT_PRESETS],
  ['body', 'Body text', 'Ordinary paragraph and table text across the site.', BODY_FONT_PRESETS],
  ['mono', 'Numbers & stats', 'Scores, tallies and tabular figures across the site.', MONO_FONT_PRESETS],
]

const fontMetaOf = (s) => Object.fromEntries(['display', 'body', 'mono'].flatMap(r => [
  [`font_${r}_url`, rebaseApiUrl(s?.[`font_${r}_url`] || null)],
  [`font_${r}_format`, s?.[`font_${r}_format`] || null],
]))

/**
 * The whole typography section as one self-contained panel: preset, upload,
 * weight per role, previewed live on this page, saved on its own button. Takes
 * the settings payload it opens on and a ``save(font_config)`` to persist.
 */
export function TypographyPanel({ settings, save, samples = {} }) {
  const [fontConfig, setFontConfig] = useState(settings?.font_config || {})
  const [fontMeta, setFontMeta] = useState(() => fontMetaOf(settings))
  const [busy, setBusy] = useState({})
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    const el = document.getElementById('typography-preview') || (() => {
      const e = document.createElement('style'); e.id = 'typography-preview'; document.head.appendChild(e); return e
    })()
    el.textContent = buildThemeCss(resolveTheme(settings?.theme_config), resolveClubFonts({ font_config: fontConfig, ...fontMeta }))
    return () => { document.getElementById('typography-preview')?.remove() }
  }, [fontConfig, fontMeta, settings?.theme_config])

  const edit = (fn) => { setFontConfig(fn); setDirty(true) }
  const selectPreset = (role, preset) => edit(c => ({ ...c, [role]: { ...(c[role] || {}), source: 'preset', preset } }))
  const selectDefault = (role) => edit(c => {
    const n = { ...c }; const w = c[role]?.weight
    if (w) n[role] = { source: 'default', weight: w }; else delete n[role]
    return n
  })
  const selectWeight = (role, weight) => edit(c => {
    const entry = { ...(c[role] || { source: 'default' }) }
    if (weight === FONT_WEIGHT_DEFAULTS[role]) delete entry.weight; else entry.weight = weight
    if (entry.source === 'default' && !entry.weight) { const n = { ...c }; delete n[role]; return n }
    return { ...c, [role]: entry }
  })
  const upload = async (role, file, family) => {
    setBusy(b => ({ ...b, [role]: true })); setMsg('')
    try {
      const res = await api.adminUploadFont(role, file, family)
      setFontConfig(res.font_config || {}); setFontMeta(fontMetaOf(res)); setMsg('Font uploaded')
    } catch (e) { setMsg(e.message) } finally { setBusy(b => ({ ...b, [role]: false })) }
  }
  const remove = async (role) => {
    setBusy(b => ({ ...b, [role]: true })); setMsg('')
    try {
      const res = await api.adminDeleteFont(role)
      setFontConfig(res.font_config || {})
      setFontMeta(m => ({ ...m, [`font_${role}_url`]: null, [`font_${role}_format`]: null }))
    } catch (e) { setMsg(e.message) } finally { setBusy(b => ({ ...b, [role]: false })) }
  }
  const onSave = async () => {
    setMsg('')
    try { await save(fontConfig); setDirty(false); setMsg('Typography saved') } catch (e) { setMsg(e.message) }
  }

  return (
    <div className="pb-card p-5" data-testid="typography-panel">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Typography</p>
      <p className="text-sm text-pb-dim mb-4 leading-relaxed">
        Pick a built-in font or upload your own (to match your club's website), separately for
        headings, body text and numbers. Font files: woff2, woff, ttf or otf, up to 6 MB.
      </p>
      <div className="space-y-6">
        {FONT_ROLES.map(([role, label, hint, presets]) => (
          <FontRoleField key={role} role={role} label={label} hint={hint} presets={presets}
            config={fontConfig[role]} busy={!!busy[role]} sampleText={samples[role] || label}
            onSelectPreset={p => selectPreset(role, p)} onSelectDefault={() => selectDefault(role)}
            onUpload={(f, fam) => upload(role, f, fam)} onSelectWeight={w => selectWeight(role, w)}
            onRemove={() => remove(role)} />
        ))}
      </div>
      <div className="flex items-center gap-3 mt-5">
        <button type="button" onClick={onSave} disabled={!dirty}
          className="px-4 py-2 rounded font-semibold text-sm bg-[var(--pb-accent)] text-black disabled:opacity-40">
          Save typography
        </button>
        {msg && <span className="text-xs text-pb-dim">{msg}</span>}
      </div>
    </div>
  )
}
