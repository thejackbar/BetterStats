import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

/* A floating "back to setup" pill shown on any admin page reached from a
   Setup Wizard link-out (the wizard stamps sessionStorage.bs_setup_return
   with the step it left from — including across a Square/Xero OAuth round
   trip). Mounted in ProtectedRoute beside TrialBanner so it covers every
   admin surface, module layouts included.

   Fixed to the bottom of the viewport rather than a top bar: it can never
   be lost behind the sticky page headers, survives scrolling, and doesn't
   shove any page's own layout around. The ring is the club's primary→
   secondary gradient (via --pb-gradient, which is luminance-guarded), the
   body a normal surface so the text stays readable whatever the club
   colours are. */
export default function SetupReturnBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)

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

  return (
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
              onClick={() => { clear(); setDismissed(true) }}
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
  )
}
