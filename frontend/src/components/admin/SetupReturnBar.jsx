import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'

/* A floating "back to setup" pill shown on any admin page reached from a
   Setup Wizard same-tab redirect (the step stamps
   sessionStorage.bs_setup_return before leaving — today that's the
   Square/Xero OAuth round trips; ordinary link-out steps open in a new tab
   and don't stamp it, since the wizard stays open in its own tab). Mounted
   in ProtectedRoute beside TrialBanner so it covers every admin surface,
   module layouts included.

   Fixed to the bottom of the viewport rather than a top bar: it can never
   be lost behind the sticky page headers, survives scrolling, and doesn't
   shove any page's own layout around. The ring is the club's primary→
   secondary gradient (via --pb-gradient, which is luminance-guarded), the
   body a normal surface so the text stays readable whatever the club
   colours are.

   The ✕ is a PERMANENT dismissal, confirmed by a modal that points at the
   sidebar's Setup Wizard item as the way back — it clears the return flag
   AND records the wizard as dismissed server-side (best-effort), so a
   half-finished setup stops chasing the admin around. */
export default function SetupReturnBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)
  const [confirming, setConfirming] = useState(false)

  let stepKey = null
  try { stepKey = sessionStorage.getItem('bs_setup_return') } catch { /* private mode */ }

  if (!stepKey || dismissed) return null
  if (!location.pathname.startsWith('/admin') || location.pathname.startsWith('/admin/setup')) return null

  const clear = () => {
    try { sessionStorage.removeItem('bs_setup_return') } catch { /* ignore */ }
  }
  const goBack = () => {
    clear()
    navigate(`/admin/setup/${stepKey}`)
  }
  const dismissForGood = () => {
    clear()
    setConfirming(false)
    setDismissed(true)
    // Also stop the wizard auto-reopening on a later login — progress itself
    // is untouched, the sidebar item picks it straight back up.
    api.dismissOnboardingWizard().catch(() => {})
  }

  return (
    <>
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[70] w-[calc(100%-2rem)] max-w-md">
        <div className="rounded-full p-[2px] shadow-lg" style={{ background: 'var(--pb-gradient)' }}>
          <div className="rounded-full bg-pb-surface flex items-center justify-between gap-3 pl-4 pr-2 py-2">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faint truncate">
              CLUB SETUP IN PROGRESS
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={goBack}
                className="font-mono text-[10px] tracking-wide2 rounded-full px-3.5 py-1.5 text-white"
                style={{ background: 'var(--pb-accent)' }}
              >
                BACK TO SETUP →
              </button>
              <button
                onClick={() => setConfirming(true)}
                aria-label="Dismiss"
                title="Dismiss"
                className="font-mono text-[12px] text-pb-faint hover:text-pb-text w-7 h-7 rounded-full hover:bg-pb-surface2"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
      </div>

      {confirming && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setConfirming(false) }}
          role="dialog" aria-modal="true" aria-labelledby="setup-dismiss-title"
        >
          <div className="pb-card bg-pb-surface w-full max-w-sm p-5 space-y-3">
            <h3 id="setup-dismiss-title" className="font-display font-bold text-base text-pb-text">
              Put setup away for now?
            </h3>
            <p className="text-sm text-pb-dim leading-relaxed">
              No worries, your progress is saved. Whenever you want to pick it back up,
              open <span className="text-pb-text font-medium">Setup Wizard</span> from the
              side menu, it's at the top, right under Dashboard.
            </p>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                onClick={() => setConfirming(false)}
                className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3.5 py-2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2"
              >
                KEEP GOING
              </button>
              <button
                onClick={dismissForGood}
                className="font-mono text-[10px] tracking-wide2 rounded px-3.5 py-2 text-white"
                style={{ background: 'var(--pb-accent)' }}
              >
                GOT IT, DISMISS
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
