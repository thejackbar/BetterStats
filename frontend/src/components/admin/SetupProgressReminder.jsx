import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

/* A periodic, bottom-right nudge back to the Setup Wizard — fires even for
   an admin who already dismissed the wizard, so a half-finished setup
   doesn't get forgotten forever. Shown by AdminLayout every 5th visit to the
   bare /admin dashboard while any step is still neither done nor skipped;
   auto-hides itself after a while, and dismissing just clears THIS toast —
   it reappears on the next 5th-visit tick, unlike the wizard's own
   permanent dismiss. */
export default function SetupProgressReminder({ progress, onDone }) {
  const navigate = useNavigate()
  const [closing, setClosing] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setClosing(true), 12000)
    return () => clearTimeout(id)
  }, [])

  useEffect(() => {
    if (!closing) return
    const id = setTimeout(onDone, 250) // let the fade-out play first
    return () => clearTimeout(id)
  }, [closing, onDone])

  // Skipped steps count as still-to-do here — skipping parks a step, it
  // doesn't complete it.
  const left = progress?.total ? progress.total - progress.done : null

  return (
    <div
      className={`fixed bottom-4 right-4 z-[70] w-full max-w-xs transition-all duration-300 ${
        closing ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'
      }`}
    >
      <div className="rounded-xl p-[1.5px] shadow-lg" style={{ background: 'var(--pb-gradient)' }}>
        <div className="rounded-[10px] bg-pb-surface p-4 space-y-2.5">
          <div className="flex items-start justify-between gap-2">
            <p className="font-display font-bold text-sm text-pb-text leading-tight">Still setting up?</p>
            <button
              onClick={() => setClosing(true)}
              aria-label="Dismiss"
              className="shrink-0 font-mono text-[12px] text-pb-faint hover:text-pb-text w-6 h-6 rounded-full hover:bg-pb-surface2 -mt-1 -mr-1"
            >
              ✕
            </button>
          </div>
          <p className="font-mono text-[11px] text-pb-faint leading-relaxed">
            {left != null && left > 0
              ? `${left} setup step${left === 1 ? '' : 's'} left to get your club fully set up.`
              : 'You have some club setup left to finish.'}
          </p>
          <button
            onClick={() => { setClosing(true); navigate('/admin/setup') }}
            className="w-full font-mono text-[10px] tracking-wide2 rounded-lg px-3.5 py-2 text-white"
            style={{ background: 'var(--pb-accent)' }}
          >
            CONTINUE SETUP →
          </button>
        </div>
      </div>
    </div>
  )
}
