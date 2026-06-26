import { useState, useEffect, useRef, useMemo } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import Dropdown from '../Dropdown'

// Super-admin control inside BetterComms: choose whether you're managing a
// club's comms or BetterCricket's own Clubs Directory campaigns. The latter runs
// on a dedicated "outreach" org (a normal org flagged is_marketing_outreach),
// which a super admin switches into via the existing act-as-club mechanism — so
// this bar is really a labelled shortcut plus a first-time designation picker.
// Renders nothing for non-super accounts.
export default function CommsContextBar() {
  const { user, switchClub } = useAuth()
  const [ctx, setCtx] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // First-time designation picker (when no outreach org is set yet).
  const [pickOpen, setPickOpen] = useState(false)
  const [orgs, setOrgs] = useState(null) // null = not loaded
  const [query, setQuery] = useState('')
  const pickRef = useRef(null)

  useEffect(() => {
    if (!user?.can_switch_clubs) return
    api.commsGetContext().then(setCtx).catch(() => {})
  }, [user?.can_switch_clubs])

  useEffect(() => {
    if (!pickOpen || orgs !== null) return
    api.superListClubs()
      .then(rows => setOrgs(Array.isArray(rows) ? rows : []))
      .catch(() => setOrgs([]))
  }, [pickOpen, orgs])

  const filtered = useMemo(() => {
    if (!orgs) return []
    const q = query.trim().toLowerCase()
    if (!q) return orgs
    return orgs.filter(c =>
      (c.name || '').toLowerCase().includes(q) || (c.slug || '').toLowerCase().includes(q))
  }, [orgs, query])

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

  const designate = async (orgId) => {
    setBusy(true); setError('')
    try {
      const res = await api.commsSetMarketingOrg(orgId)
      setPickOpen(false)
      await switchClub(res.marketing_org.id) // straight into it (hard reload)
    } catch (e) {
      setError(e?.message || 'Could not set marketing org'); setBusy(false)
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
          <div className="relative" ref={pickRef}>
            <button disabled={busy} onClick={() => setPickOpen(o => !o)}
              className="px-3 py-1.5 rounded text-xs border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-50">
              Set up BetterCricket marketing…
            </button>
            <Dropdown
              anchorRef={pickRef} open={pickOpen} onClose={() => setPickOpen(false)}
              align="end" width={300} gap={6}
              className="bg-pb-surface border pb-hairline rounded-lg shadow-xl overflow-hidden"
            >
              <div className="px-3 py-2 border-b pb-hairline-b">
                <div className="font-mono text-[9px] tracking-wide3 text-pb-faint uppercase mb-1.5">
                  Pick the BetterCricket marketing org
                </div>
                <input
                  autoFocus value={query} onChange={e => setQuery(e.target.value)}
                  placeholder="Search orgs…"
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent"
                />
              </div>
              <div className="max-h-72 overflow-y-auto">
                {orgs === null && <div className="px-3 py-3 font-mono text-[11px] text-pb-faint">Loading…</div>}
                {orgs !== null && filtered.length === 0 && (
                  <div className="px-3 py-3 font-mono text-[11px] text-pb-faint">No orgs found</div>
                )}
                {filtered.map(o => (
                  <button key={o.id} disabled={busy} onClick={() => designate(o.id)}
                    className="w-full text-left px-3 py-2 hover:bg-pb-surface2 transition-colors disabled:opacity-50">
                    <span className="block text-sm text-pb-text truncate">{o.name}</span>
                    <span className="block font-mono text-[10px] text-pb-faintest truncate">/{o.slug}</span>
                  </button>
                ))}
              </div>
            </Dropdown>
          </div>
        )}
      </div>

      {error && <div className="w-full font-mono text-[10px] text-pb-red">{error}</div>}
    </div>
  )
}
