import { useEffect, useRef } from 'react'

// Step scaffold for the self-serve trial registration flow (see
// docs/self-serve-trial-onboarding-plan.md). Only the shell exists so far —
// each step lands in its own later phase. Keeping the list here now so the
// stepper UI doesn't need reshaping when a step's content arrives.
const STEPS = [
  { key: 'club', label: 'Club' },
  { key: 'admin', label: 'Admin details' },
  { key: 'verify', label: 'Verify email' },
  { key: 'ack', label: 'Acknowledgements' },
  { key: 'submit', label: 'Submit' },
]

/**
 * The self-serve club trial registration modal shell. Internal-only for now —
 * opened from the Super Admin "Self-Serve Trial (Internal)" page, never from a
 * public surface. Closes on backdrop click, the close button, or Escape;
 * restores focus to whatever triggered it, matching the convention in
 * components/marketing/Lightbox.jsx.
 *
 * Controlled — render only while open:
 *   {open && <SelfServeTrialModal defaultTrialDays={14} onClose={() => setOpen(false)} />}
 */
export default function SelfServeTrialModal({ defaultTrialDays, onClose }) {
  const closeBtnRef = useRef(null)
  const previouslyFocused = useRef(null)

  useEffect(() => {
    previouslyFocused.current = document.activeElement
    closeBtnRef.current?.focus()

    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      if (previouslyFocused.current?.focus) previouslyFocused.current.focus()
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4"
      style={{ backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="self-serve-trial-modal-title"
    >
      <div className="pb-card bg-pb-surface w-full max-w-lg mt-10 mb-8 max-h-[86vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b pb-hairline shrink-0">
          <h2 id="self-serve-trial-modal-title" className="font-display font-bold text-base text-pb-text">
            Start your club's {defaultTrialDays} Day Free Trial
          </h2>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            aria-label="Close"
            className="text-pb-faint hover:text-pb-text p-1 rounded hover:bg-pb-surface2 font-mono text-sm"
          >
            ✕
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto space-y-4">
          <p className="font-mono text-[11px] text-pb-faintest">
            Internal preview — not yet reachable from the public site. This registers a
            real club and admin account, exactly like the eventual public flow will,
            for testing before launch.
          </p>

          <ol className="flex flex-wrap gap-2">
            {STEPS.map((s, i) => (
              <li key={s.key}
                className={`px-2 py-1 rounded font-mono text-[10px] tracking-wide2 border pb-hairline ${
                  i === 0 ? 'text-pb-text' : 'text-pb-faintest'
                }`}>
                {i + 1}. {s.label}
              </li>
            ))}
          </ol>

          <div className="pb-card p-4 bg-pb-surface2">
            <p className="font-mono text-[11px] text-pb-faint">
              Club search isn't built yet — it lands in the next phase of
              docs/self-serve-trial-onboarding-plan.md.
            </p>
          </div>
        </div>

        <div className="px-5 py-3 border-t pb-hairline shrink-0 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
          >
            Cancel
          </button>
          <button
            disabled
            title="Not wired up yet — club search and the rest of the registration steps land in later phases."
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            START FREE TRIAL
          </button>
        </div>
      </div>
    </div>
  )
}
