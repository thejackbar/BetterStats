/* Club Setup Wizard — /admin/setup and /admin/setup/:stepKey.

   A full-page, step-by-step walk through getting a club properly set up
   across the whole platform: data in, data tidied, then each module the club
   holds. The step list, grouping, completion detection and skip state all
   come from GET /club-admin/onboarding-wizard/flow — this page renders it,
   hosts the inline actions, and deep-links to the heavyweight tools.

   Navigation: Back / Skip / Continue, a group rail with per-group progress,
   and every step addressable by URL so a link-out and return lands you back
   where you were. Vital steps warn before they can be skipped. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import AdminLayout from '../../../components/admin/AdminLayout'
import { ProgressBar } from '../../../components/ProgressBar'
import { Notice, WizardButton } from './setupUi'
import { BrandingStep, FullRebuildStep, SponsorsStep } from './SetupInlineSteps'
import {
  AssignPlayersStep, CommsStep, FantasyPoolStep, FantasySeasonStep,
  FixturesStep, IqPrewarmStep, SelfServeStep, SquadsStep, SquareStep,
  WebsiteStep, XeroStep,
} from './SetupModuleSteps'

const INLINE_STEPS = {
  full_rebuild: FullRebuildStep,
  branding: BrandingStep,
  sponsors: SponsorsStep,
  fixtures: FixturesStep,
  squads: SquadsStep,
  assign_players: AssignPlayersStep,
  self_serve: SelfServeStep,
  website: WebsiteStep,
  square: SquareStep,
  xero: XeroStep,
  comms: CommsStep,
  iq_prewarm: IqPrewarmStep,
  fantasy_season: FantasySeasonStep,
  fantasy_pool: FantasyPoolStep,
}

// What actually goes wrong if a vital step is skipped — shown in the skip
// confirmation so the warning is concrete, not a vague "are you sure".
const VITAL_SKIP_WARNINGS = {
  full_rebuild:
    'Almost everything else needs your playing history: merging players, squads, records, analytics, the fantasy pool. Without the first sync your club will look empty.',
  merge_players:
    'Unmerged duplicates split a player\'s career across two records, so career totals, milestones and records read wrong on your public pages. Most clubs have at least a few.',
  merge_grades:
    'Unmerged grades split season history under different names, so season-by-season comparisons and grade records read wrong.',
}

export default function SetupWizard() {
  const { stepKey } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [flow, setFlow] = useState(null)
  const [error, setError] = useState('')
  const [confirmSkip, setConfirmSkip] = useState(null) // step object pending skip confirmation
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const f = await api.getSetupFlow()
      setFlow(f)
      setError('')
      return f
    } catch (e) {
      setError(
        user?.role === 'super_admin'
          ? 'Pick a club with the club switcher up top first, then run setup for that club.'
          : (e?.message || 'The setup wizard is not available right now.')
      )
      return null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
    api.markOnboardingWizardOpened().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Link-out steps open in a new tab, so the work happens away from this
  // page. Re-run the flow (and its auto-detection) whenever this tab regains
  // focus, so steps tick themselves off the moment the admin comes back.
  useEffect(() => {
    const onFocus = () => { load() }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [load])

  // Flat step list in display order, each carrying its group.
  const steps = useMemo(() => {
    if (!flow) return []
    return flow.groups.flatMap((g) => g.steps.map((s) => ({ ...s, group: g })))
  }, [flow])

  const currentIndex = useMemo(() => {
    if (!steps.length) return 0
    if (stepKey === 'done') return steps.length // the finish screen
    const idx = steps.findIndex((s) => s.key === stepKey)
    if (idx >= 0) return idx
    // No (or unknown) step in the URL — resume at the first unaddressed step.
    const firstOpen = steps.findIndex((s) => !s.done && !s.skipped && !s.na && !s.group.locked)
    return firstOpen >= 0 ? firstOpen : 0
  }, [steps, stepKey])

  // Keep the URL in sync so refresh/link-out-and-return lands on the same step.
  useEffect(() => {
    if (!steps.length) return
    const wanted = currentIndex >= steps.length ? 'done' : steps[currentIndex].key
    if (stepKey !== wanted) navigate(`/admin/setup/${wanted}`, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps.length, currentIndex])

  const goTo = (idx) => {
    if (idx >= steps.length) navigate('/admin/setup/done')
    else navigate(`/admin/setup/${steps[Math.max(0, idx)].key}`)
  }

  const setStep = async (key, body) => {
    setBusy(true)
    try {
      await api.setSetupStep(key, body)
      await load()
    } catch { /* the next flow load re-syncs state */ } finally {
      setBusy(false)
    }
  }

  const step = currentIndex < steps.length ? steps[currentIndex] : null

  const markDoneAndContinue = async () => {
    if (step && !step.done) await setStep(step.key, { done: true })
    goTo(currentIndex + 1)
  }

  const requestSkip = () => {
    if (!step) return
    if (step.vital && !step.done) setConfirmSkip(step)
    else doSkip(step)
  }

  const doSkip = async (s) => {
    setConfirmSkip(null)
    await setStep(s.key, { skipped: true })
    goTo(currentIndex + 1)
  }

  // "Doesn't apply" — only offered on steps flagged optional (Connect
  // Square for a club with no Square, and so on). Unlike a skip, this drops
  // the step out of the counts entirely; it's reversible from the step card.
  const markNa = async (s, na = true) => {
    await setStep(s.key, { not_applicable: na })
    if (na) goTo(currentIndex + 1)
  }

  const openTool = (s) => {
    // New tab, so the wizard keeps its place here. No bs_setup_return stamp —
    // that pill exists to bring an admin back from a same-tab redirect (the
    // Square/Xero OAuth round trips still use it); with the wizard still open
    // in this tab there's nothing to come back from.
    window.open(s.route, '_blank', 'noopener')
  }

  const exitWizard = async () => {
    try { await api.dismissOnboardingWizard() } catch { /* best-effort */ }
    try { sessionStorage.removeItem('bs_setup_return') } catch { /* ignore */ }
    navigate('/admin')
  }

  const progress = flow?.progress
  // Progress is DONE steps only — a skipped step is parked, not completed,
  // so it must never move the bar or the counts.
  const pct = progress?.total ? Math.round((progress.done / progress.total) * 100) : 0

  return (
    <AdminLayout>
      <div className="max-w-3xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="font-display font-bold text-xl text-pb-text">Club setup</h1>
            <p className="font-mono text-[11px] text-pb-faint mt-1">
              Work through each step and {flow?.club?.name || 'your club'} will be properly set up
              across all of BetterCricket. Every step can be skipped and finished later.
            </p>
          </div>
          <button
            onClick={exitWizard}
            className="shrink-0 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5"
          >
            EXIT SETUP
          </button>
        </div>

        {error && (
          <div className="pb-card bg-pb-surface p-5">
            <Notice tone="warn">{error}</Notice>
          </div>
        )}

        {!flow && !error && (
          <div className="pb-card bg-pb-surface p-5">
            <p className="font-mono text-[11px] text-pb-faint">Loading your setup…</p>
          </div>
        )}

        {flow && (
          <>
            {/* Overall progress */}
            <div className="pb-card bg-pb-surface p-4 space-y-3">
              <ProgressBar
                pct={pct}
                color="var(--pb-gradient)"
                label={`${progress.done} done${progress.addressed > progress.done ? `, ${progress.addressed - progress.done} skipped` : ''} of ${progress.total} steps`}
              />
              {/* Group rail */}
              <div className="flex flex-wrap gap-1.5">
                {flow.groups.map((g) => {
                  // Done only — skipped steps stay out of the count, so a
                  // "skip for now" never reads as progress; a group whose
                  // remaining steps are all skips goes amber, not green.
                  // Not-applicable steps leave the denominator entirely.
                  const counted = g.steps.filter((s) => !s.na)
                  const gDone = counted.filter((s) => s.done).length
                  const gAddressed = counted.filter((s) => s.done || s.skipped).length
                  const active = step && step.group.key === g.key
                  const firstIdx = steps.findIndex((s) => s.group.key === g.key)
                  return (
                    <button
                      key={g.key}
                      onClick={() => goTo(firstIdx)}
                      className={`font-mono text-[10px] tracking-wide2 rounded px-2.5 py-1 border transition-colors ${
                        active
                          ? 'text-white border-transparent'
                          : gDone === counted.length
                            ? 'text-pb-positive border-pb-positive/40'
                            : gAddressed === counted.length
                              ? 'text-pb-amber border-pb-amber/40'
                              : 'text-pb-faint pb-hairline hover:text-pb-text'
                      }`}
                      style={active ? { background: 'var(--pb-accent)' } : undefined}
                    >
                      {g.title.toUpperCase()} {gDone}/{counted.length}{g.locked ? ' 🔒' : ''}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Step card / finish screen */}
            {step ? (
              <div className="pb-card bg-pb-surface p-5 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase">
                      {step.group.title} · Step {currentIndex + 1} of {steps.length}
                      {step.minutes ? ` · ≈ ${step.minutes} min` : ''}
                    </p>
                    <h2 className="font-display font-bold text-lg text-pb-text mt-0.5">{step.title}</h2>
                  </div>
                  {step.done && (
                    <span className="font-mono text-[10px] tracking-wide2 text-pb-positive border border-pb-positive/40 rounded px-2 py-1 shrink-0">DONE ✓</span>
                  )}
                  {step.skipped && (
                    <span className="font-mono text-[10px] tracking-wide2 text-pb-amber border border-pb-amber/40 rounded px-2 py-1 shrink-0">SKIPPED</span>
                  )}
                  {step.na && (
                    <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-1 shrink-0">DOESN'T APPLY</span>
                  )}
                </div>

                <p className="text-sm text-pb-dim leading-relaxed">{step.blurb}</p>

                {step.group.locked ? (
                  <LockedSyncNotice
                    onRefresh={load}
                    goToSync={() => goTo(steps.findIndex((s) => s.key === 'full_rebuild'))}
                  />
                ) : (
                  <StepBody step={step} onRefresh={load} onOpenTool={openTool} />
                )}

                {/* Footer nav. Every non-vital step can be marked done by
                    hand (auto-detection is a convenience, not a gate, e.g.
                    Net Manager might be "done enough" without saving
                    settings); vital steps (first sync, the merges) only
                    complete when the wizard can actually see the result, so
                    they get NEXT STEP with no manual mark. Optional steps
                    add DOESN'T APPLY, which is reversible from this card. */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t pb-hairline">
                  <WizardButton variant="secondary" onClick={() => goTo(currentIndex - 1)} disabled={currentIndex === 0}>
                    ← BACK
                  </WizardButton>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    {step.group.locked ? (
                      <WizardButton onClick={() => goTo(currentIndex + 1)}>NEXT →</WizardButton>
                    ) : step.done ? (
                      <WizardButton onClick={() => goTo(currentIndex + 1)}>CONTINUE →</WizardButton>
                    ) : step.na ? (
                      <>
                        <WizardButton variant="secondary" onClick={() => markNa(step, false)} disabled={busy}>
                          ACTUALLY, THIS APPLIES
                        </WizardButton>
                        <WizardButton onClick={() => goTo(currentIndex + 1)}>NEXT →</WizardButton>
                      </>
                    ) : (
                      <>
                        <WizardButton variant="secondary" onClick={requestSkip} disabled={busy}>
                          {step.skipped ? 'SKIP AGAIN' : 'SKIP FOR NOW'}
                        </WizardButton>
                        {step.optional && (
                          <WizardButton variant="secondary" onClick={() => markNa(step)} disabled={busy}>
                            DOESN'T APPLY TO US
                          </WizardButton>
                        )}
                        {step.vital ? (
                          <WizardButton onClick={() => goTo(currentIndex + 1)}>NEXT STEP →</WizardButton>
                        ) : (
                          <>
                            <WizardButton variant="secondary" onClick={() => goTo(currentIndex + 1)}>NEXT →</WizardButton>
                            <WizardButton onClick={markDoneAndContinue} disabled={busy}>
                              MARK DONE & NEXT →
                            </WizardButton>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>
                {step.vital && step.auto && !step.done && !step.group.locked && (
                  <p className="font-mono text-[10px] text-pb-faintest text-right -mt-2">
                    This step ticks itself off once the work's done, no need to mark anything.
                  </p>
                )}
              </div>
            ) : (
              <FinishScreen flow={flow} onExit={exitWizard} goTo={goTo} steps={steps} />
            )}
          </>
        )}

        {/* Vital-step skip confirmation */}
        {confirmSkip && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            onClick={(e) => { if (e.target === e.currentTarget) setConfirmSkip(null) }}
            role="dialog" aria-modal="true"
          >
            <div className="pb-card bg-pb-surface w-full max-w-md p-5 space-y-3">
              <h3 className="font-display font-bold text-base text-pb-text">Skip "{confirmSkip.title}"?</h3>
              <Notice tone="warn">
                {VITAL_SKIP_WARNINGS[confirmSkip.key] || 'This step matters for a well set up club.'}
              </Notice>
              <p className="font-mono text-[11px] text-pb-faint">You can come back to it any time from the Setup guide.</p>
              <div className="flex items-center justify-end gap-2 pt-1">
                <WizardButton variant="secondary" onClick={() => setConfirmSkip(null)}>GO BACK</WizardButton>
                <WizardButton variant="danger" onClick={() => doSkip(confirmSkip)}>SKIP ANYWAY</WizardButton>
              </div>
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}

/* Locked "Tidy your data" steps used to dead-end at "needs your first full
   sync". If that sync is actually running right now, show its live progress
   here instead, and refresh the flow the moment it finishes so the locks
   lift without the admin doing anything. Same poll shape as FullRebuildStep. */
function LockedSyncNotice({ onRefresh, goToSync }) {
  const { user } = useAuth()
  const [run, setRun] = useState(null)
  const wasRunning = useRef(false)

  useEffect(() => {
    if (!user?.club_id) return undefined
    let cancelled = false
    const poll = async () => {
      try {
        const logs = await api.getSyncLogs(user.club_id)
        if (cancelled) return
        const latest = (logs || [])[0]
        const running = latest && latest.status === 'running' ? latest : null
        setRun(running)
        if (wasRunning.current && !running) {
          wasRunning.current = false
          onRefresh() // the sync just finished — the group lock may lift now
        }
        if (running) wasRunning.current = true
      } catch { /* silent — the notice just stays static */ }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => { cancelled = true; clearInterval(id) }
  }, [user?.club_id, onRefresh])

  return (
    <div className="space-y-3">
      <Notice tone="warn">
        This step needs your first full sync to finish before it has anything to work
        with.{' '}
        {!run && (
          <button className="underline" onClick={goToSync}>
            Go to the sync step
          </button>
        )}
      </Notice>
      {run && (
        <div className="space-y-1">
          <ProgressBar
            pct={run?.stats?.progress_pct ?? 0}
            label={run?.stats?.progress_phase || 'Your first full sync is running…'}
          />
          <p className="font-mono text-[10px] text-pb-faintest">
            These steps unlock on their own the moment it finishes, feel free to keep
            moving through the others.
          </p>
        </div>
      )}
    </div>
  )
}

function StepBody({ step, onRefresh, onOpenTool }) {
  const Inline = INLINE_STEPS[step.key]
  if (Inline) return <Inline step={step} onRefresh={onRefresh} onOpenTool={onOpenTool} />
  // Link-out step: the tool is a full page in its own right.
  return (
    <div className="space-y-3">
      <WizardButton onClick={() => onOpenTool(step)}>
        OPEN {step.title.toUpperCase()} ↗
      </WizardButton>
      <p className="font-mono text-[11px] text-pb-faintest">
        {step.auto
          ? 'Opens in a new tab so you keep your place here. The step ticks itself off once it can see the result, just come back to this tab.'
          : 'Opens in a new tab so you keep your place here. Mark the step done once you\'re happy with it.'}
      </p>
    </div>
  )
}

function FinishScreen({ flow, onExit, goTo, steps }) {
  const [copied, setCopied] = useState(false)
  // Not-applicable steps aren't outstanding — they're off the club's list.
  const skippedSteps = steps.filter((s) => s.skipped)
  const openSteps = steps.filter((s) => !s.done && !s.skipped && !s.na)
  const allDone = openSteps.length === 0 && skippedSteps.length === 0

  // A plain-text rundown of where setup landed, for pasting into a committee
  // group chat or handover email.
  const copySummary = async () => {
    const line = (s) => `- ${s.title}`
    const sections = [
      [`${flow?.club?.name || 'Club'}. BetterCricket setup (${flow?.progress?.done ?? 0}/${flow?.progress?.total ?? steps.length} steps done)`],
      ...(openSteps.length ? [['Still to do:', ...openSteps.map(line)]] : []),
      ...(skippedSteps.length ? [['Skipped for now:', ...skippedSteps.map(line)]] : []),
      [(allDone ? 'Everything else is done.' : 'Everything else is done or marked not applicable.')],
    ]
    try {
      await navigator.clipboard.writeText(sections.map((sec) => sec.join('\n')).join('\n\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="pb-card bg-pb-surface p-6 space-y-4 text-center">
      <div className="text-4xl">🏏</div>
      <h2 className="font-display font-bold text-xl text-pb-text">
        {allDone ? 'Your club is fully set up' : 'Setup wrapped up'}
      </h2>
      <p className="text-sm text-pb-dim max-w-md mx-auto">
        {allDone
          ? `${flow?.club?.name || 'Your club'} is ready to go across the whole platform. Nice work.`
          : 'You can pick up anything you skipped from the Setup Wizard in the side menu, any time.'}
      </p>
      {(skippedSteps.length > 0 || openSteps.length > 0) && (
        <div className="max-w-md mx-auto text-left space-y-1">
          {[...openSteps, ...skippedSteps].map((s) => (
            <button
              key={s.key}
              onClick={() => goTo(steps.findIndex((x) => x.key === s.key))}
              className="w-full flex items-center justify-between font-mono text-[11px] border pb-hairline rounded px-3 py-2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2"
            >
              <span>{s.title}</span>
              <span className={s.skipped ? 'text-pb-amber' : 'text-pb-faintest'}>{s.skipped ? 'SKIPPED' : 'NOT DONE'}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center justify-center gap-2 pt-2">
        <WizardButton variant="secondary" onClick={copySummary}>
          {copied ? 'COPIED ✓' : 'COPY SUMMARY'}
        </WizardButton>
        <WizardButton onClick={onExit}>GO TO YOUR DASHBOARD →</WizardButton>
      </div>
    </div>
  )
}
