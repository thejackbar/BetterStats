import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

const FIELD_CLS = 'w-full bg-pb-surface2 text-pb-text border pb-hairline rounded px-3 py-2 text-sm outline-none focus:border-pb-accent'

// The public trial asks only for first name and email (v9.144.2). This card,
// at the top of the dashboard, offers the rest: last name, the name shown on
// the club's pages, and a mobile. It is never a gate. It shows only while the
// server says the prompt is pending (set at self-serve registration), and
// saving or closing it retires it for good (PATCH /club-admin/account/profile).
export default function ProfileNudge() {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({ last_name: '', display_name: '', mobile_number: '' })
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    let alive = true
    api.getOwnProfile()
      .then((p) => {
        if (!alive || !p) return
        setProfile(p)
        setForm({ last_name: p.last_name || '', display_name: p.display_name || '', mobile_number: p.mobile_number || '' })
      })
      .catch(() => { /* no card is the right answer when this fails */ })
    return () => { alive = false }
  }, [])

  if (!profile?.nudge && !done) return null

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const save = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    setErrors({})
    try {
      const body = {
        last_name: form.last_name,
        mobile_number: form.mobile_number,
        ...(form.display_name.trim() ? { display_name: form.display_name } : {}),
      }
      setProfile(await api.patchOwnProfile(body))
      setDone(true)
    } catch (err) {
      const fieldErrors = err?.detail?.errors
      if (fieldErrors && typeof fieldErrors === 'object' && !Array.isArray(fieldErrors)) setErrors(fieldErrors)
      else setError(err?.message || 'Could not save that just now.')
    } finally {
      setSaving(false)
    }
  }

  const close = async () => {
    setProfile((p) => ({ ...p, nudge: false }))
    setDone(false)
    try { await api.patchOwnProfile({ dismiss_nudge: true }) } catch { /* it shows again next visit */ }
  }

  if (done) {
    return (
      <div className="pb-card p-4 mb-5 bg-pb-surface2" role="status" data-testid="profile-nudge-done">
        <p className="text-sm text-pb-text">Saved. Thanks{profile?.first_name ? `, ${profile.first_name}` : ''}.</p>
        <button type="button" onClick={() => setDone(false)} className="mt-2 font-mono text-[10px] text-pb-faint underline hover:text-pb-text">
          Close
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={save} className="pb-card p-4 mb-5 bg-pb-surface2 space-y-3" data-testid="profile-nudge">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display font-semibold text-sm text-pb-text">Finish your profile</p>
          <p className="text-xs text-pb-faint mt-0.5">
            Optional. Your trial is already running.
            {profile?.username && <> You sign in with <span className="text-pb-text" style={{ overflowWrap: 'anywhere' }}>{profile.username}</span>.</>}
          </p>
        </div>
        <button type="button" onClick={close} aria-label="Close" className="shrink-0 text-pb-faint hover:text-pb-text font-mono text-sm p-1">✕</button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="min-w-0">
          <label htmlFor="pn-last" className="font-mono text-[10px] text-pb-faint block mb-1">Last name</label>
          <input id="pn-last" value={form.last_name} onChange={set('last_name')} autoComplete="family-name" className={FIELD_CLS} />
          {errors.last_name && <p className="font-mono text-[10px] text-pb-red mt-1">{errors.last_name}</p>}
        </div>
        <div className="min-w-0">
          <label htmlFor="pn-display" className="font-mono text-[10px] text-pb-faint block mb-1">Name shown on the club's pages</label>
          <input id="pn-display" value={form.display_name} onChange={set('display_name')} autoComplete="name" className={FIELD_CLS} />
          {errors.display_name && <p className="font-mono text-[10px] text-pb-red mt-1">{errors.display_name}</p>}
        </div>
        <div className="min-w-0 sm:col-span-2">
          <label htmlFor="pn-mobile" className="font-mono text-[10px] text-pb-faint block mb-1">Mobile (so we can help if you get stuck)</label>
          <input id="pn-mobile" type="tel" value={form.mobile_number} onChange={set('mobile_number')} autoComplete="tel" placeholder="04XX XXX XXX" className={FIELD_CLS} />
          {errors.mobile_number && <p className="font-mono text-[10px] text-pb-red mt-1">{errors.mobile_number}</p>}
        </div>
      </div>
      {error && <p className="font-mono text-[10px] text-pb-red" role="alert">{error}</p>}
      <div className="flex items-center gap-3">
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}>
          {saving ? 'SAVING…' : 'SAVE'}
        </button>
        <button type="button" onClick={close} className="font-mono text-[10px] text-pb-faint underline hover:text-pb-text">
          Not now
        </button>
      </div>
    </form>
  )
}
