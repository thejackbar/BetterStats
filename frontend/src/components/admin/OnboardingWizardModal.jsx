import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'

/**
 * Club onboarding wizard (see docs/self-serve-trial-onboarding-plan.md, Phase
 * 15). Every step points at an existing admin tool — this is a guided
 * checklist, not a re-implementation of any of them. Self-contained: fetches
 * its own state on open and marks itself "opened" (the one-time trigger that
 * stops the auto-reopen-on-sync-complete from firing more than once).
 */
export default function OnboardingWizardModal({ onClose }) {
  const navigate = useNavigate()
  const [state, setState] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const s = await api.getOnboardingWizardState()
        if (!cancelled) setState(s)
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load the setup guide.')
      }
      try {
        await api.markOnboardingWizardOpened()
      } catch {
        // best-effort — worst case the auto-reopen fires once more than intended
      }
    })()
    return () => { cancelled = true }
  }, [])

  const toggleStep = async (key, done) => {
    setState((s) => s && { ...s, steps: s.steps.map((st) => (st.key === key ? { ...st, done } : st)) })
    try {
      await api.setOnboardingWizardStep(key, done)
    } catch {
      // best-effort — a failed toggle just means the checkbox reverts next open
    }
  }

  const goTo = (route) => {
    onClose()
    navigate(route)
  }

  const handleClose = async () => {
    try {
      await api.dismissOnboardingWizard()
    } catch {
      // best-effort — worst case it auto-opens again next login
    }
    onClose()
  }

  const doneCount = state ? state.steps.filter((s) => s.done).length : 0
  const total = state?.steps?.length || 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-wizard-title"
    >
      <div className="pb-card bg-pb-surface w-full max-w-md mt-16 max-h-[80vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b pb-hairline shrink-0">
          <h2 id="onboarding-wizard-title" className="font-display font-bold text-base text-pb-text">
            Get your club set up
          </h2>
          <button
            onClick={handleClose}
            aria-label="Close"
            className="text-pb-faint hover:text-pb-text p-1 rounded hover:bg-pb-surface2 font-mono text-sm"
          >
            ✕
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto space-y-2">
          {error && <p className="font-mono text-[11px] text-pb-red">{error}</p>}
          {!state && !error && <p className="font-mono text-[11px] text-pb-faint">Loading…</p>}
          {state && (
            <>
              <p className="font-mono text-[11px] text-pb-faint mb-2">{doneCount} of {total} done</p>
              <ul className="space-y-1.5">
                {state.steps.map((s) => (
                  <li key={s.key} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={s.done}
                      onChange={(e) => toggleStep(s.key, e.target.checked)}
                    />
                    <button
                      onClick={() => goTo(s.route)}
                      className={`font-mono text-[12px] text-left flex-1 hover:underline ${
                        s.done ? 'text-pb-faintest line-through' : 'text-pb-text'
                      }`}
                    >
                      {s.title}
                    </button>
                  </li>
                ))}
              </ul>
              {!state.sync_ready && (
                <p className="font-mono text-[10px] text-pb-faintest mt-3 pt-3 border-t pb-hairline">
                  A few more setup steps (importing historical stats/honours, merging
                  grades) unlock once your club's first data sync finishes.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
