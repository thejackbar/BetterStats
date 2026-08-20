import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'

// The club ⇄ BetterCricket-internal switch, in the BetterAdmin sidebar
// footer. Restores what CommsContextBar used to do inside BetterComms, which
// went dead in the BetterAdmin merge — the mechanism (a dedicated outreach
// organisation, reached through the act-as-club switch) never went anywhere,
// only the way in did.
//
// ⚠ Super admins only, and structurally so: the component returns null for
// anyone without `can_switch_clubs`, the endpoints behind it are
// require_super_admin, and — the part that matters — nothing here loads
// BetterCricket's own field sets or copy into a club admin's session. A club
// build must never carry the platform surface, not behind a dropdown and not
// greyed out. See docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
export default function ClubhouseContextControl() {
  const { user, switchClub } = useAuth()
  const [marketingOrg, setMarketingOrg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Which mode we are in comes off /auth/me, not a fetch — the shell needs it
  // synchronously to decide the nav, and a flicker there would be a real
  // hazard (the whole point is that you always know which mode you are in).
  const internal = !!user?.is_marketing_org

  useEffect(() => {
    // Only needed to learn WHERE to switch to. In internal mode we already know.
    if (!user?.can_switch_clubs || internal) return
    api.commsGetContext().then(c => setMarketingOrg(c?.marketing_org || null)).catch(() => {})
  }, [user?.can_switch_clubs, internal])

  if (!user?.can_switch_clubs) return null

  const go = async (clubId) => {
    setBusy(true); setError('')
    try {
      await switchClub(clubId)   // hard-reloads on success
    } catch (e) {
      setError(e?.message || 'Could not switch'); setBusy(false)
    }
  }

  const setUp = async () => {
    setBusy(true); setError('')
    try {
      const res = await api.commsEnsureMarketingOrg()   // mints the org if there isn't one
      await switchClub(res.marketing_org.id)
    } catch (e) {
      setError(e?.message || 'Could not set up BetterCricket internal'); setBusy(false)
    }
  }

  const btn = 'w-full text-left px-2 py-1.5 rounded text-[11.5px] font-medium disabled:opacity-55 transition-colors'

  return (
    <div className="mb-2.5 pb-2.5 border-b pb-hairline">
      <div className="font-mono text-[9px] tracking-[0.12em] uppercase text-pb-faintest mb-1.5">Working on</div>
      <div className="text-[12.5px] text-pb-text font-medium truncate mb-1.5"
        title={internal ? 'BetterCricket internal' : (user.club_name || user.club_slug)}>
        {internal ? 'BetterCricket internal' : (user.club_name || user.club_slug || 'Your club')}
      </div>
      {internal ? (
        <button disabled={busy} onClick={() => go(null)}
          className={`${btn} border pb-hairline text-pb-faint hover:text-pb-text`}>
          {busy ? 'Switching…' : `↩ Back to ${user.home_club_name || 'your club'}`}
        </button>
      ) : marketingOrg ? (
        <button disabled={busy} onClick={() => go(marketingOrg.id)}
          className={`${btn} text-pb-bg`} style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
          {busy ? 'Switching…' : 'BetterCricket internal →'}
        </button>
      ) : (
        <button disabled={busy} onClick={setUp}
          className={`${btn} border pb-hairline text-pb-faint hover:text-pb-text`}>
          {busy ? 'Setting up…' : 'Set up BetterCricket internal →'}
        </button>
      )}
      {error && <div className="font-mono text-[9.5px] text-pb-red mt-1.5 break-words">{error}</div>}
    </div>
  )
}
