import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'

// Super-admin control inside BetterComms: choose whether you're managing a club's
// comms or BetterCricket's own Clubs Directory campaigns. BetterCricket marketing
// runs on a dedicated platform org (not a real club). If that org doesn't exist
// yet, "Set up" mints it; otherwise this switches into it via the act-as-club
// mechanism. Renders nothing for non-super accounts.
export default function CommsContextBar() {
  const { user, switchClub } = useAuth()
  const [ctx, setCtx] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user?.can_switch_clubs) return
    api.commsGetContext().then(setCtx).catch(() => {})
  }, [user?.can_switch_clubs])

  if (!user?.can_switch_clubs || !ctx) return null

  const onMarketing = !!ctx.current?.is_marketing
  const mk = ctx.marketing_org

  const go = async (clubId) => {
    setBusy(true); setError('')
    try {
      await switchClub(clubId) // hard-reloads on success
    } catch (e) {
      setError(e?.message || 'Could not switch'); setBusy(false)
    }
  }

  const setup = async () => {
    setBusy(true); setError('')
    try {
      const res = await api.commsEnsureMarketingOrg() // creates the dedicated org if needed
      await switchClub(res.marketing_org.id)          // then switch straight into it
    } catch (e) {
      setError(e?.message || 'Could not set up BetterCricket marketing'); setBusy(false)
    }
  }

  return (
    <div className="pb-card p-3 mb-4 flex items-center justify-between gap-3 flex-wrap">
      <div className="text-sm min-w-0">
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mr-2">Comms context</span>
        {onMarketing ? (
          <>
            <span className="text-pb-text font-medium">BetterCricket Clubs Directory</span>
            <a href="/admin/marketing" className="ml-2 text-xs underline" style={{ color: 'var(--pb-accent)' }}>
              open Clubs Directory
            </a>
          </>
        ) : (
          <span className="text-pb-text font-medium truncate">{ctx.current?.name}</span>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {onMarketing ? (
          <button disabled={busy} onClick={() => go(null)}
            className="px-3 py-1.5 rounded text-xs border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
            ↩ Return to {user.home_club_name || 'home club'}
          </button>
        ) : mk ? (
          <button disabled={busy} onClick={() => go(mk.id)}
            className="px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-60"
            style={{ background: 'var(--pb-accent)' }}>
            Manage BetterCricket Clubs Directory →
          </button>
        ) : (
          <button disabled={busy} onClick={setup}
            className="px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-60"
            style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'Setting up…' : 'Set up BetterCricket Clubs Directory →'}
          </button>
        )}
      </div>

      {error && <div className="w-full font-mono text-[10px] text-pb-red">{error}</div>}
    </div>
  )
}
