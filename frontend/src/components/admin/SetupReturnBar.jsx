import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

/* A slim "back to setup" strip shown on any admin page reached from a Setup
   Wizard link-out (the wizard stamps sessionStorage.bs_setup_return with the
   step it left from). Mounted in ProtectedRoute beside TrialBanner so it
   covers every admin surface, module layouts included. Dismissable; returning
   to the wizard clears it too. */
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
    navigate(`/admin/setup/${stepKey}`)
    clear()
  }

  return (
    <div className="bg-pb-surface border-b pb-hairline-b">
      <div className="max-w-7xl mx-auto px-4 py-1.5 flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">
          YOU'RE IN THE MIDDLE OF CLUB SETUP
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={goBack}
            className="font-mono text-[10px] tracking-wide2 rounded px-3 py-1 text-white"
            style={{ background: 'var(--pb-accent)' }}
          >
            BACK TO SETUP →
          </button>
          <button
            onClick={() => { clear(); setDismissed(true) }}
            aria-label="Dismiss"
            className="font-mono text-[11px] text-pb-faint hover:text-pb-text px-1"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}
