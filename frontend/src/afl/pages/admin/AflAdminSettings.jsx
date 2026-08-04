import { useEffect, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'
import { useToast } from '../../../contexts/ToastContext'
import LoadingSpinner from '../../../components/LoadingSpinner'

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

  const load = () => aflApi.getAdminSettings().then(setSettings).catch(e => toast.error(e.message))
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

  if (settings === null) return <LoadingSpinner message="Loading settings…" />

  return (
    <div className="space-y-4 max-w-2xl">
      <SectionTitle>Settings</SectionTitle>

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
