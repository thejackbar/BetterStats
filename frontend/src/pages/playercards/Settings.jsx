// Settings: the emails Player Cards sends this player. Everything else the page does needs no setting.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import PageHead from './PageHead'
import { usePC } from './context'

const ROWS = [
  ['alert_swaps', 'A swap is asked of me', 'An email when another player asks to swap cards with you, or sends one back changed.'],
  ['alert_wants', 'A card on my wish list is available', 'One email the first time someone could swap you a card on your list. You are not emailed again for that card unless nobody could swap it in between.'],
]

export default function Settings() {
  const { token, club, accent } = usePC()
  const [prefs, setPrefs] = useState(null)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState('')
  useEffect(() => { api.availPublicCardPrefs(token).then(setPrefs).catch(() => setErr('Your settings could not load. Reload to try again.')) }, [token])
  const set = async (key, value) => {
    setErr(''); setSaved('')
    const before = prefs
    setPrefs({ ...prefs, [key]: value })
    try { setPrefs(await api.availPublicSaveCardPrefs(token, { [key]: value })); setSaved('Saved.') } catch (e) { setPrefs(before); setErr(e?.message || 'That did not save. Try again.') }
  }
  if (!prefs && !err) return <div className="text-sm text-pb-faint" data-settings-loading>Loading…</div>
  return (
    <div data-screen="settings">
      <PageHead title="Settings" sub="The emails Player Cards sends you." />
      {err && <div role="alert" className="text-sm mb-3" style={{ color: 'var(--pb-red, #f87171)' }}>{err}</div>}
      {prefs && (
        <>
          {!prefs.club_alerts && <div data-club-alerts-off className="rounded-xl border pb-hairline bg-pb-surface px-4 py-3 mb-3 text-sm">{club?.name || 'Your club'} has switched card emails off, so none are sent whatever you choose here.</div>}
          {!prefs.email_on_file && <div data-no-email className="rounded-xl border pb-hairline bg-pb-surface px-4 py-3 mb-3 text-sm">There is no email address on file for you, so none can be sent. Ask your club to add yours.</div>}
          <div className="flex flex-col gap-3 max-w-xl">
            {ROWS.map(([key, label, help]) => (
              <label key={key} className="flex gap-4 items-start rounded-2xl border pb-hairline bg-pb-surface p-4 cursor-pointer" data-pref={key}>
                <input type="checkbox" checked={prefs[key]} onChange={(e) => set(key, e.target.checked)} className="w-5 h-5 mt-0.5" style={{ accentColor: accent }} />
                <span><span className="block font-semibold">{label}</span><span className="block text-sm text-pb-dim mt-0.5">{help}</span></span>
              </label>
            ))}
          </div>
          {saved && <div role="status" className="text-sm text-pb-dim mt-3" data-saved>{saved}</div>}
        </>
      )}
    </div>
  )
}
