import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { PbSpinner } from '../../lib/presskit'
import { Note } from '../../components/admin/ui'

export default function AdminMemberPortal() {
  const { user } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.stripeConnectStatus().then(setStatus).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function connect() {
    setBusy(true)
    try {
      const r = await api.stripeConnectConnect()
      window.location.assign(r.url)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function refresh() {
    setBusy(true)
    try { setStatus(await api.stripeConnectRefresh()); toast.success('Status refreshed') }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function openDashboard() {
    try {
      const r = await api.stripeConnectDashboardLink()
      window.open(r.url, '_blank', 'noopener')
    } catch (e) { toast.error(e.message) }
  }

  async function disconnect() {
    if (!confirm('Disconnect Stripe? Members won’t be able to pay fees online until you reconnect.')) return
    try { setStatus(await api.stripeConnectDisconnect()); toast.success('Disconnected') }
    catch (e) { toast.error(e.message) }
  }

  const portalUrl = user?.club_slug ? `${window.location.origin}/portal/${user.club_slug}` : null

  if (status === null) return <BetterClubManagerLayout title="Member Portal" caption="Self-service sign-in for members"><PbSpinner message="Loading…" /></BetterClubManagerLayout>
  return (
    <BetterClubManagerLayout title="Member Portal" caption="Self-service sign-in for members">
      <div className="max-w-2xl">
        {/* Kept from the old page description: this one is a caveat a club has
            to know, not a summary of what the screen already shows. */}
        <Note toneKey="warn" className="mb-4">
          Members sign in with an emailed link rather than a password, to see their own fees and qualifications and
          update their details. This is still in testing, and BetterCricket decides when it goes live for each club.
        </Note>

        {portalUrl && (
          <div className="pb-card p-4 mb-4">
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">MEMBER PORTAL LINK</div>
            <div className="flex items-center gap-2">
              <input readOnly value={portalUrl} onClick={e => e.target.select()}
                className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-[11px] focus:outline-none" />
              <button onClick={() => navigator.clipboard.writeText(portalUrl).then(() => toast.success('Copied'))}
                className="px-2.5 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">
                Copy
              </button>
            </div>
            <p className="text-[12.5px] leading-[1.6] text-pb-faint mt-1.5">
              Share this with members. They'll enter their registered email to request a sign-in link.
            </p>
          </div>
        )}

        <div className="pb-card p-4">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-3">STRIPE CONNECT. ONLINE FEE PAYMENTS</div>
          {!status.connected ? (
            <>
              <p className="text-pb-dim text-sm mb-3">
                Connect the club's own Stripe account so member fee payments land directly in the club's bank
                account. BetterCricket never holds or sees the money.
              </p>
              <button onClick={connect} disabled={busy}
                className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                {busy ? 'Connecting…' : 'Connect stripe'}
              </button>
            </>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3 mb-3">
                {[
                  ['Details submitted', status.details_submitted],
                  ['Charges enabled', status.charges_enabled],
                  ['Payouts enabled', status.payouts_enabled],
                ].map(([label, ok]) => (
                  <div key={label} className="bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
                    <div className="font-mono text-[9px] text-pb-faintest mb-1">{label.toUpperCase()}</div>
                    <div className={`font-mono text-[11px] ${ok ? 'text-pb-accent' : 'text-pb-amber'}`}>{ok ? 'Yes' : 'Not yet'}</div>
                  </div>
                ))}
              </div>
              {!status.charges_enabled && (
                <p className="text-[12.5px] leading-[1.6] text-pb-amber mb-3">
                  Onboarding isn't finished yet. Members can't pay online until charges are enabled.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {!status.details_submitted && (
                  <button onClick={connect} disabled={busy}
                    className="px-3 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                    FINISH ONBOARDING
                  </button>
                )}
                <button onClick={refresh} disabled={busy} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text">
                  Refresh status
                </button>
                {status.details_submitted && (
                  <button onClick={openDashboard} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text">
                    Open Stripe dashboard
                  </button>
                )}
                <button onClick={disconnect} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-red ml-auto">
                  Disconnect
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </BetterClubManagerLayout>
  )
}
