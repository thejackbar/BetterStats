import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'
import {
  BRAND, deriveDarkPalette, gradientCss, resolveTheme,
} from '../../../lib/theme'

const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/

/** A colour swatch + hex field + reset, matching BetterCricket's ColorField. */
function ColorField({ label, hint, value, fallback, onChange }) {
  const shown = HEX_RE.test(value || '') ? value : fallback
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</label>
        {value && value !== fallback && (
          <button type="button" onClick={() => onChange(fallback)}
            className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-[var(--pb-accent)]">
            Reset
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input type="color" value={shown} onChange={e => onChange(e.target.value)}
          className="w-10 h-9 rounded border border-pb-hairline bg-pb-surface2 cursor-pointer shrink-0" />
        <input type="text" value={shown} onChange={e => onChange(e.target.value)}
          className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm font-mono w-28" />
      </div>
      {hint && <p className="text-[11px] text-pb-faintest mt-1 leading-snug">{hint}</p>}
    </div>
  )
}

function Toggle({ label, hint, checked, onChange, disabled }) {
  return (
    <label className="flex items-start gap-3 py-3 pb-hairline-b last:border-0 cursor-pointer">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)}
        className="mt-1 h-4 w-4 accent-[var(--pb-accent)]" />
      <div>
        <div className="text-sm text-pb-text">{label}</div>
        {hint && <div className="text-xs text-pb-faint mt-0.5">{hint}</div>}
      </div>
    </label>
  )
}

export default function AflAdminSettings() {
  const toast = useToast()
  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(false)
  // Colours are edited as a draft and saved on a button, unlike the toggles
  // below: a colour input fires continuously while the picker is dragged, so
  // autosaving it would be one request per pixel of movement.
  const [theme, setTheme] = useState(null)
  const [themeMode, setThemeMode] = useState('dark')
  const [themeDirty, setThemeDirty] = useState(false)
  const [savingTheme, setSavingTheme] = useState(false)

  const load = () => aflApi.getAdminSettings().then(s => {
    setSettings(s)
    setTheme(resolveTheme(s.theme_config))
    setThemeMode(s.theme_mode || 'dark')
    setThemeDirty(false)
  }).catch(e => toast.error(e.message))
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function toggle(field, value) {
    setSettings(s => ({ ...s, [field]: value }))
    setSaving(true)
    try {
      await aflApi.patchAdminSettings({ [field]: value })
    } catch (e) {
      toast.error(e.message)
      setSettings(s => ({ ...s, [field]: !value })) // revert on failure
    } finally { setSaving(false) }
  }

  const setColor = (key, value) => {
    setTheme(t => ({ ...t, [key]: value }))
    setThemeDirty(true)
  }
  // A dark background is one pick, not five: the cards, panels and hairlines
  // are derived from it, the same way BetterCricket's settings page does it.
  const setDarkBg = (value) => {
    setTheme(t => ({ ...t, dark: deriveDarkPalette(value, t.dark) }))
    setThemeDirty(true)
  }
  const setLightBg = (value) => {
    setTheme(t => ({ ...t, light: { ...t.light, bg: value } }))
    setThemeDirty(true)
  }

  async function saveTheme() {
    setSavingTheme(true)
    try {
      // Top-level keys this form doesn't show (chart series, category
      // colours) are carried through untouched; the two palettes are owned by
      // this form, so they're rebuilt rather than merged — otherwise "Reset
      // to default" would leave the old background behind.
      const { light: _l, dark: _d, ...rest } = settings.theme_config || {}
      const theme_config = { ...rest, accent: theme.accent, accent2: theme.accent2 }
      // A palette is only stored once it's actually been changed. Saving the
      // default background too would pin this club to a copy of today's
      // values, so a later change to the BetterFootball default would skip
      // every club that had ever opened this page.
      if (theme.light.bg !== BRAND.light.bg) theme_config.light = { bg: theme.light.bg }
      if (theme.dark.bg !== BRAND.dark.bg) theme_config.dark = { ...theme.dark }
      await aflApi.patchAdminSettings({ theme_config, theme_mode: themeMode })
      toast.success('Branding saved. Your public site updates on the next page load.')
      await load()
    } catch (e) {
      toast.error(e.message)
    } finally { setSavingTheme(false) }
  }

  function resetTheme() {
    setTheme(t => ({
      ...t,
      accent: BRAND.accent, accent2: BRAND.accent2,
      light: { ...t.light, bg: BRAND.light.bg },
      dark: { ...BRAND.dark },
    }))
    setThemeDirty(true)
  }

  if (settings === null || theme === null) return <LoadingSpinner message="Loading settings…" />

  return (
    <div className="space-y-4 max-w-2xl">
      <SectionTitle>Settings</SectionTitle>

      <div className="pb-card p-5">
        <div className="flex items-center justify-between mb-1">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Branding &amp; theme</p>
          <button type="button" onClick={resetTheme}
            className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-red uppercase">
            Reset to default
          </button>
        </div>
        <p className="text-sm text-pb-dim mb-4 leading-relaxed">
          Your club's colours across the public site — headings, charts, buttons and the page
          background.
        </p>

        <div className="mb-5">
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1">
            Default theme
          </label>
          <select
            value={themeMode}
            onChange={e => { setThemeMode(e.target.value); setThemeDirty(true) }}
            className="bg-pb-surface2 border border-pb-hairline rounded px-3 py-2 text-sm text-pb-text"
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
            <option value="auto">Auto (follow the visitor's device)</option>
          </select>
          <p className="text-[11px] text-pb-faintest mt-1">
            Visitors can still flip this themselves with the sun icon in the navbar, so set the
            background for both.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-x-4 gap-y-4">
          <ColorField
            label="Primary colour" fallback={BRAND.accent} value={theme.accent}
            hint="Goal figures, links, buttons and the first chart series."
            onChange={v => setColor('accent', v)}
          />
          <ColorField
            label="Secondary colour" fallback={BRAND.accent2} value={theme.accent2}
            hint="Your second club colour — the games chart and the bar beside your club name."
            onChange={v => setColor('accent2', v)}
          />
          <ColorField
            label="Dark background" fallback={BRAND.dark.bg} value={theme.dark.bg}
            hint="Cards, panels and borders are worked out from this."
            onChange={setDarkBg}
          />
          <ColorField
            label="Light background" fallback={BRAND.light.bg} value={theme.light.bg}
            hint="Used when a visitor is on the light theme."
            onChange={setLightBg}
          />
        </div>

        <div className="mt-4 rounded-md border border-pb-hairline overflow-hidden">
          <div className="h-9" style={{ background: gradientCss(theme.accent, theme.accent2) }} />
          <div className="flex" style={{ background: theme.dark.bg }}>
            <span className="flex-1 px-2.5 py-2 font-mono text-[10px]" style={{ color: theme.dark.text }}>Dark</span>
            <span className="px-2.5 py-2 font-mono text-[10px] font-bold" style={{ color: theme.accent }}>128 goals</span>
          </div>
          <div className="flex" style={{ background: theme.light.bg }}>
            <span className="flex-1 px-2.5 py-2 font-mono text-[10px]" style={{ color: theme.light.text }}>Light</span>
            <span className="px-2.5 py-2 font-mono text-[10px] font-bold" style={{ color: theme.accent }}>128 goals</span>
          </div>
        </div>

        <button
          type="button" onClick={saveTheme} disabled={!themeDirty || savingTheme}
          className="mt-4 px-4 py-2 rounded text-sm font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {savingTheme ? 'Saving…' : themeDirty ? 'Save branding' : 'Saved'}
        </button>
      </div>

      <div className="pb-card p-5">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Public leaderboard</p>
        <p className="text-sm text-pb-dim mb-2 leading-relaxed">
          Games and Goals always show. Choose which of the other leaderboard categories your public site
          also offers — a club with no Best on Ground data recorded, or that would rather keep vote counts
          private, can switch any of these off.
        </p>
        <Toggle
          label="Best on Ground"
          hint="A flat count of games named Best on Ground."
          checked={!!settings.public_show_bog_leaderboard}
          disabled={saving}
          onChange={v => toggle('public_show_bog_leaderboard', v)}
        />
        <Toggle
          label="Club Best & Fairest votes"
          hint="Lifetime votes in your club's own internal Best & Fairest count — only ever comes from an Import Stats upload."
          checked={!!settings.public_show_club_bf_leaderboard}
          disabled={saving}
          onChange={v => toggle('public_show_club_bf_leaderboard', v)}
        />
        <Toggle
          label="Competition Best & Fairest votes"
          hint="Lifetime votes in the wider association/league's Best & Fairest count — also only from an Import Stats upload."
          checked={!!settings.public_show_comp_bf_leaderboard}
          disabled={saving}
          onChange={v => toggle('public_show_comp_bf_leaderboard', v)}
        />
      </div>
    </div>
  )
}
