import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { MODULE_TOGGLES } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import { ProgressBar } from '../ProgressBar'

// BetterStats (core) is mandatory, not a selectable trial — same reasoning as
// the Super Admin per-club module editor this list is shared with.
const SELECTABLE_MODULES = MODULE_TOGGLES.filter((m) => m.key !== 'core')

// Step scaffold for the self-serve trial registration flow (see
// docs/self-serve-trial-onboarding-plan.md). Steps after 'verify' aren't built
// yet — each lands in its own later phase. Keeping the list here now so the
// stepper UI doesn't need reshaping when a step's content arrives.
const STEPS = [
  { key: 'club', label: 'Club' },
  { key: 'admin', label: 'Admin details' },
  { key: 'verify', label: 'Verify email' },
  { key: 'ack', label: 'Acknowledgements' },
  { key: 'submit', label: 'Submit' },
]

const orgName = (org) => org.name || org.shortName || org.organisationName || org.id || ''

const FIELD_CLS = 'w-full bg-pb-surface2 text-pb-text border pb-hairline rounded px-3 py-2 text-sm outline-none focus:border-pb-accent'

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
  const [step, setStep] = useState('club')

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

  // ─── Step 1: club search (Phase 2) ──────────────────────────────────────
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [selectedClub, setSelectedClub] = useState(null)
  const [duplicateClub, setDuplicateClub] = useState(null)
  const debounceRef = useRef(null)

  // ─── Step 1b: club identity preview (Phase 3) ───────────────────────────
  // Prepared server-side (name, short name, slug) the same way the existing
  // "New Club" flow derives them — read-only here, the operator can't edit
  // any of these fields.
  const [preparing, setPreparing] = useState(false)
  const [preparedClub, setPreparedClub] = useState(null)
  const [prepareError, setPrepareError] = useState('')

  useEffect(() => {
    if (!selectedClub) {
      setPreparedClub(null)
      setPrepareError('')
      return
    }
    let alive = true
    setPreparing(true)
    setPrepareError('')
    api.selfServeTrialPrepare({
      org_id: selectedClub.id,
      name: orgName(selectedClub),
      short_name: selectedClub.shortName || '',
    })
      .then((prepared) => { if (alive) setPreparedClub(prepared) })
      .catch((e) => { if (alive) setPrepareError(e?.message || 'Could not prepare this club.') })
      .finally(() => { if (alive) setPreparing(false) })
    return () => { alive = false }
  }, [selectedClub])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (selectedClub) return
    if (!query || query.trim().length < 2) {
      setResults([])
      setShowResults(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      setSearchError('')
      try {
        const data = await api.selfServeTrialSearch(query.trim())
        setResults(Array.isArray(data) ? data : [])
        setShowResults(true)
      } catch (e) {
        setResults([])
        setSearchError(e?.message || 'Club search failed.')
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [query, selectedClub])

  const selectClub = (org) => {
    setShowResults(false)
    if (org.already_registered) {
      setDuplicateClub(org)
      setSelectedClub(null)
      return
    }
    setDuplicateClub(null)
    setSelectedClub(org)
    setQuery(orgName(org))
  }

  const clearClub = () => {
    setSelectedClub(null)
    setDuplicateClub(null)
    setQuery('')
    setResults([])
  }

  // ─── Step 2: Primary Club Admin details (Phase 4) ───────────────────────
  // Password isn't collected here — deliberately deferred to immediately
  // before final submission (a later phase), so a plaintext password spends
  // less time sitting in client state across email verification and
  // acknowledgements.
  const [adminForm, setAdminForm] = useState({
    first_name: '', last_name: '', display_name: '', username: '', email: '', mobile_number: '',
  })
  const [adminErrors, setAdminErrors] = useState({})
  const [adminValidating, setAdminValidating] = useState(false)
  const [adminValid, setAdminValid] = useState(false)
  const adminDebounceRef = useRef(null)

  const setAdminField = (field, value) => setAdminForm((f) => ({ ...f, [field]: value }))

  // Preferred display name and username are predicted from first/last name,
  // but only until the person edits that field directly — after that, typing
  // more of their name doesn't overwrite what they've already changed.
  const [displayNameTouched, setDisplayNameTouched] = useState(false)
  const [usernameTouched, setUsernameTouched] = useState(false)

  const editAdminField = (field, value) => {
    if (field === 'display_name') setDisplayNameTouched(true)
    if (field === 'username') setUsernameTouched(true)
    setAdminField(field, value)
  }

  useEffect(() => {
    const first = adminForm.first_name.trim()
    const last = adminForm.last_name.trim()
    if (!displayNameTouched) {
      const predicted = [first, last].filter(Boolean).join(' ')
      setAdminForm((f) => (f.display_name === predicted ? f : { ...f, display_name: predicted }))
    }
    if (!usernameTouched) {
      const predicted = (first + last).toLowerCase().replace(/[^a-z0-9]/g, '')
      setAdminForm((f) => (f.username === predicted ? f : { ...f, username: predicted }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminForm.first_name, adminForm.last_name, displayNameTouched, usernameTouched])

  useEffect(() => {
    if (step !== 'admin') return
    if (adminDebounceRef.current) clearTimeout(adminDebounceRef.current)
    const hasAnything = Object.values(adminForm).some((v) => v.trim())
    if (!hasAnything) {
      setAdminErrors({})
      setAdminValid(false)
      return
    }
    adminDebounceRef.current = setTimeout(async () => {
      setAdminValidating(true)
      try {
        const result = await api.selfServeTrialValidateAdmin(adminForm)
        setAdminErrors(result?.errors || {})
        setAdminValid(!!result?.valid)
      } catch {
        setAdminValid(false)
      } finally {
        setAdminValidating(false)
      }
    }, 350)
    return () => clearTimeout(adminDebounceRef.current)
  }, [adminForm, step])

  const canContinueFromClub = !!preparedClub && !preparing && !prepareError

  // ─── Step 3: email verification (Phase 6) ───────────────────────────────
  const [codeSent, setCodeSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  const [verifyCode, setVerifyCode] = useState('')
  const [checking, setChecking] = useState(false)
  const [verifyError, setVerifyError] = useState('')
  const [verified, setVerified] = useState(false)

  // Changing the email restarts verification from scratch.
  useEffect(() => {
    setCodeSent(false)
    setSendError('')
    setVerifyCode('')
    setVerifyError('')
    setVerified(false)
  }, [adminForm.email])

  const sendCode = async () => {
    setSending(true)
    setSendError('')
    try {
      await api.selfServeTrialSendCode(adminForm.email)
      setCodeSent(true)
    } catch (e) {
      setSendError(e?.message || 'Could not send the verification email.')
    } finally {
      setSending(false)
    }
  }

  const checkCode = async () => {
    setChecking(true)
    setVerifyError('')
    try {
      await api.selfServeTrialCheckCode(adminForm.email, verifyCode.trim())
      setVerified(true)
    } catch (e) {
      setVerifyError(e?.message || 'Incorrect code.')
    } finally {
      setChecking(false)
    }
  }

  // ─── Step 4: acknowledgements (Phase 7) ─────────────────────────────────
  const [ackTerms, setAckTerms] = useState(false)
  const [ackPrivacy, setAckPrivacy] = useState(false)
  const [ackAuthority, setAckAuthority] = useState(false)
  const [ackSubmitting, setAckSubmitting] = useState(false)
  const [ackError, setAckError] = useState('')
  const [ackAccepted, setAckAccepted] = useState(false)

  const allAckChecked = ackTerms && ackPrivacy && ackAuthority

  const confirmAcknowledgements = async () => {
    setAckSubmitting(true)
    setAckError('')
    try {
      await api.selfServeTrialAcknowledge({
        email: adminForm.email,
        club_name: preparedClub?.name || '',
        accept_terms: ackTerms,
        accept_privacy: ackPrivacy,
        confirm_authority: ackAuthority,
      })
      setAckAccepted(true)
      setStep('submit')
    } catch (e) {
      setAckError(e?.message || 'Could not record acknowledgements.')
    } finally {
      setAckSubmitting(false)
    }
  }

  // ─── Step 5: modules + password + final submission (Phases 8-10) ─────────
  // Password is collected here, not with the rest of the admin details —
  // deliberately deferred to right before submission (Phase 4's original
  // decision), so it spends less time sitting in state. /submit revalidates
  // everything, then creates the real club and admin account.
  // Every club gets every module on trial — not a choice, so there's no
  // selection state to track; the checkboxes below are shown checked and
  // disabled purely to communicate what's included.
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitResult, setSubmitResult] = useState(null)
  const [syncRun, setSyncRun] = useState(null)
  const [loggingInAs, setLoggingInAs] = useState(false)
  const [loginAsError, setLoginAsError] = useState('')
  // Minted once per modal instance and reused across retries — a double
  // click or a retry after a network error replays the same key rather than
  // registering as a second attempt. Lazily initialised so a fresh UUID isn't
  // generated (and discarded) on every render.
  const idempotencyKeyRef = useRef(null)
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
  }

  const passwordChecks = {
    length: password.length >= 10,
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[^A-Za-z0-9]/.test(password),
    match: !!password && password === confirmPassword,
  }
  const passwordValid = Object.values(passwordChecks).every(Boolean)
  const canSubmit = !!preparedClub && adminValid && verified && ackAccepted && passwordValid && !submitting

  const submitRegistration = async () => {
    setSubmitting(true)
    setSubmitError('')
    try {
      const result = await api.selfServeTrialSubmit({
        idempotency_key: idempotencyKeyRef.current,
        org_id: preparedClub.org_id,
        name: preparedClub.name,
        first_name: adminForm.first_name,
        last_name: adminForm.last_name,
        display_name: adminForm.display_name,
        username: adminForm.username,
        email: adminForm.email,
        mobile_number: adminForm.mobile_number,
        password,
        confirm_password: confirmPassword,
        modules: SELECTABLE_MODULES.map((m) => m.key),
      })
      if (result?.status === 'completed') {
        setSubmitResult(result)
        setSubmitted(true)
      }
    } catch (e) {
      setSubmitError(e?.message || 'Could not submit registration.')
    } finally {
      setSubmitting(false)
    }
  }

  // Live sync progress right here — the operator just triggered this club's
  // first sync and shouldn't have to leave the modal (or log in as the new
  // club) to see it land. Same 4s cadence as AdminSync.jsx's own polling;
  // stops once the run is no longer 'running'.
  useEffect(() => {
    if (!submitted || !submitResult?.org_id) return undefined
    let cancelled = false
    let intervalId = null
    const poll = async () => {
      try {
        const logs = await api.getSyncLogs(submitResult.org_id)
        const run = logs.find((r) => r.id === submitResult.run_id) || logs[0] || null
        if (cancelled) return
        setSyncRun(run)
        if (run && run.status !== 'running' && intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
      } catch {
        // best-effort — a polling hiccup shouldn't disrupt the success screen
      }
    }
    poll()
    intervalId = setInterval(poll, 4000)
    return () => { cancelled = true; if (intervalId) clearInterval(intervalId) }
  }, [submitted, submitResult?.org_id, submitResult?.run_id])

  const loginAsNewAdmin = async () => {
    if (!submitResult?.user_id) return
    if (!window.confirm(
      "This will end your Super Admin session and log you in as the new club "
      + "admin instead, so you can see exactly what they'll see. Continue?"
    )) return
    setLoggingInAs(true)
    setLoginAsError('')
    try {
      await api.selfServeTrialLoginAs(submitResult.user_id)
      // Unlike switchClub's hard reload, this one IS a genuine fresh login
      // for the new admin (not a super admin acting-as) — the bell and
      // onboarding wizard auto-open checks should fire for it. They key off
      // AuthContext's justLoggedIn, which only login()/acceptInvite() set;
      // this flow mints the session itself and never calls those, so this
      // marker is what makes the post-reload fetchMe() count as one too.
      try { sessionStorage.setItem('bs_pending_fresh_login', '1') } catch { /* skip */ }
      // Hard reload (not a client-side route change) — matches switchClub's
      // own pattern, so every already-mounted admin page refetches under the
      // new session rather than showing stale super-admin-scoped data.
      window.location.assign('/admin')
    } catch (e) {
      setLoginAsError(e?.message || 'Could not log in as the new admin.')
      setLoggingInAs(false)
    }
  }

  const syncProgressLabel = (s) => {
    const phase = s?.progress_phase || 'Starting'
    if (s?.progress_done != null && s?.progress_total != null) {
      return `${phase} · ${Number(s.progress_done).toLocaleString()} / ${Number(s.progress_total).toLocaleString()}`
    }
    return phase
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4"
      style={{ backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="self-serve-trial-modal-title"
    >
      <div className="pb-card bg-pb-surface w-full max-w-lg mt-6 mb-6 max-h-[92vh] overflow-hidden flex flex-col">
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
          <ol className="flex flex-wrap gap-2">
            {STEPS.map((s, i) => {
              const currentIndex = STEPS.findIndex((x) => x.key === step)
              return (
                <li key={s.key}
                  className={`px-2 py-1 rounded font-mono text-[10px] tracking-wide2 border pb-hairline ${
                    i === currentIndex ? 'text-pb-text' : 'text-pb-faintest'
                  }`}>
                  {i + 1}. {s.label}
                </li>
              )
            })}
          </ol>

          {step === 'club' && (
            <>
              <div className="relative">
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Search for your club</label>
                <input
                  type="text"
                  value={query}
                  disabled={!!selectedClub}
                  onChange={(e) => { setQuery(e.target.value); setDuplicateClub(null) }}
                  onFocus={() => { if (results.length > 0) setShowResults(true) }}
                  placeholder="Start typing your club's name…"
                  className={`${FIELD_CLS} disabled:opacity-60`}
                />

                {showResults && results.length > 0 && !selectedClub && (
                  // Normal flow, not absolute — an absolutely positioned box is
                  // taken out of layout and doesn't expand the scrollable body's
                  // content height, so it silently gets clipped by the modal
                  // card's own height limit regardless of its own max-h. Normal
                  // flow lets the body's scrollbar (below) actually reach it.
                  <div className="mt-1 w-full pb-card bg-pb-surface max-h-[440px] overflow-y-auto">
                    {results.map((org) => {
                      const location = [org.suburb, org.stateName].filter(Boolean).join(', ')
                      return (
                        <button
                          key={org.id}
                          type="button"
                          onClick={() => selectClub(org)}
                          className="w-full text-left px-3 py-2.5 hover:bg-pb-surface2 border-b pb-hairline last:border-b-0"
                        >
                          <div className="text-pb-text text-sm flex items-center justify-between gap-2">
                            <span>{orgName(org)}</span>
                            {org.already_registered && (
                              <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase shrink-0">
                                Registered
                              </span>
                            )}
                          </div>
                          {org.shortName && org.shortName !== org.name && (
                            <div className="text-pb-faint text-xs mt-0.5">{org.shortName}</div>
                          )}
                          {location && (
                            <div className="text-pb-faintest text-xs mt-0.5">{location}</div>
                          )}
                        </button>
                      )
                    })}
                  </div>
                )}

                {showResults && !searching && results.length === 0 && query.trim().length >= 2 && !selectedClub && (
                  <div className="mt-1 w-full pb-card bg-pb-surface px-3 py-2">
                    <p className="font-mono text-[11px] text-pb-faintest">No clubs found for "{query.trim()}".</p>
                  </div>
                )}

                {searching && (
                  <p className="font-mono text-[10px] text-pb-faintest mt-1">Searching…</p>
                )}
                {searchError && (
                  <p className="font-mono text-[10px] text-pb-red mt-1">{searchError}</p>
                )}
              </div>

              {duplicateClub && (
                <div className="pb-card p-4 bg-pb-surface2 border-pb-red/40">
                  <p className="font-mono text-[11px] text-pb-text">
                    {orgName(duplicateClub)} has already been registered in BetterCricket.
                    Please contact your club's administrator or email{' '}
                    <a href={`mailto:${SUPPORT_EMAIL}`} className="underline">{SUPPORT_EMAIL}</a>{' '}
                    if you think your club has been incorrectly registered.
                  </p>
                </div>
              )}

              {selectedClub && (
                <div className="pb-card p-4 bg-pb-surface2 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Selected club</p>
                    <button
                      type="button"
                      onClick={clearClub}
                      className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline shrink-0"
                    >
                      Change
                    </button>
                  </div>

                  {preparing && (
                    <p className="font-mono text-[11px] text-pb-faintest">Preparing club details…</p>
                  )}

                  {!preparing && prepareError && (
                    <p className="font-mono text-[11px] text-pb-red">{prepareError}</p>
                  )}

                  {!preparing && !prepareError && preparedClub && (
                    <dl className="space-y-2">
                      <div>
                        <dt className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Club name</dt>
                        <dd className="text-pb-text text-sm">{preparedClub.name}</dd>
                      </div>
                      {preparedClub.short_name && (
                        <div>
                          <dt className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Short name</dt>
                          <dd className="text-pb-text text-sm">{preparedClub.short_name}</dd>
                        </div>
                      )}
                      <div>
                        <dt className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">URL</dt>
                        <dd className="text-pb-text text-sm">betterat.cricket/{preparedClub.slug}</dd>
                      </div>
                    </dl>
                  )}
                </div>
              )}

              {!selectedClub && (
                <div className="pb-card p-4 bg-pb-surface2">
                  <p className="font-mono text-[11px] text-pb-faint">
                    Search for and select a club to continue.
                  </p>
                </div>
              )}
            </>
          )}

          {step === 'admin' && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-mono text-[10px] text-pb-faint block mb-1">First name</label>
                  <input type="text" value={adminForm.first_name}
                    onChange={(e) => setAdminField('first_name', e.target.value)}
                    className={FIELD_CLS} />
                  {adminErrors.first_name && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.first_name}</p>}
                </div>
                <div>
                  <label className="font-mono text-[10px] text-pb-faint block mb-1">Last name</label>
                  <input type="text" value={adminForm.last_name}
                    onChange={(e) => setAdminField('last_name', e.target.value)}
                    className={FIELD_CLS} />
                  {adminErrors.last_name && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.last_name}</p>}
                </div>
              </div>

              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Preferred display name</label>
                <input type="text" value={adminForm.display_name}
                  onChange={(e) => editAdminField('display_name', e.target.value)}
                  className={FIELD_CLS} />
                {adminErrors.display_name && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.display_name}</p>}
              </div>

              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Username</label>
                <input type="text" value={adminForm.username}
                  onChange={(e) => editAdminField('username', e.target.value)}
                  className={FIELD_CLS} />
                {adminErrors.username && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.username}</p>}
              </div>

              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Email address</label>
                <input type="email" value={adminForm.email}
                  onChange={(e) => setAdminField('email', e.target.value)}
                  className={FIELD_CLS} />
                {adminErrors.email && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.email}</p>}
              </div>

              <div>
                <label className="font-mono text-[10px] text-pb-faint block mb-1">Mobile number</label>
                <input type="tel" value={adminForm.mobile_number}
                  onChange={(e) => setAdminField('mobile_number', e.target.value)}
                  placeholder="04XX XXX XXX"
                  className={FIELD_CLS} />
                {adminErrors.mobile_number && <p className="font-mono text-[10px] text-pb-red mt-1">{adminErrors.mobile_number}</p>}
              </div>

              {adminValidating && (
                <p className="font-mono text-[10px] text-pb-faintest">Checking…</p>
              )}
              {!adminValidating && adminValid && (
                <p className="font-mono text-[10px] text-emerald-400">✓ All details valid</p>
              )}

              <div className="pb-card p-4 bg-pb-surface2">
                <p className="font-mono text-[11px] text-pb-faint">
                  Password isn't set here. You'll set it once email verification and
                  acknowledgements are confirmed.
                </p>
              </div>
            </div>
          )}

          {step === 'verify' && (
            <div className="space-y-3">
              <p className="font-mono text-[11px] text-pb-faint">
                We'll send a 4-digit code to <span className="text-pb-text">{adminForm.email}</span>.
                It's valid for 24 hours.
              </p>

              {verified ? (
                <div className="pb-card p-4 bg-pb-surface2">
                  <p className="font-mono text-[11px] text-emerald-400">✓ Email verified</p>
                </div>
              ) : (
                <>
                  {!codeSent ? (
                    <button
                      type="button"
                      onClick={sendCode}
                      disabled={sending}
                      className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
                      style={{ background: 'var(--pb-accent)' }}
                    >
                      {sending ? 'Sending…' : 'SEND CODE'}
                    </button>
                  ) : (
                    <>
                      <div>
                        <label className="font-mono text-[10px] text-pb-faint block mb-1">4-digit code</label>
                        <input
                          type="text"
                          inputMode="numeric"
                          maxLength={4}
                          value={verifyCode}
                          onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 4))}
                          className={`${FIELD_CLS} tracking-[0.5em] text-center`}
                        />
                        {verifyError && <p className="font-mono text-[10px] text-pb-red mt-1">{verifyError}</p>}
                      </div>
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={checkCode}
                          disabled={checking || verifyCode.length !== 4}
                          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
                          style={{ background: 'var(--pb-accent)' }}
                        >
                          {checking ? 'Checking…' : 'VERIFY'}
                        </button>
                        <button
                          type="button"
                          onClick={sendCode}
                          disabled={sending}
                          className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline disabled:opacity-40"
                        >
                          {sending ? 'Sending…' : 'Resend code'}
                        </button>
                      </div>
                    </>
                  )}
                  {sendError && <p className="font-mono text-[10px] text-pb-red">{sendError}</p>}
                </>
              )}

            </div>
          )}

          {step === 'ack' && (
            <div className="space-y-3">
              <label className="flex items-start gap-2 font-mono text-[11px] text-pb-faint">
                <input type="checkbox" className="mt-0.5" checked={ackTerms}
                  onChange={(e) => setAckTerms(e.target.checked)} />
                <span>
                  I accept the{' '}
                  <a href="/terms" target="_blank" rel="noopener noreferrer" className="underline text-pb-text">
                    BetterCricket Terms of Service
                  </a>
                </span>
              </label>

              <label className="flex items-start gap-2 font-mono text-[11px] text-pb-faint">
                <input type="checkbox" className="mt-0.5" checked={ackPrivacy}
                  onChange={(e) => setAckPrivacy(e.target.checked)} />
                <span>
                  I accept the{' '}
                  <a href="/privacy" target="_blank" rel="noopener noreferrer" className="underline text-pb-text">
                    Privacy Policy
                  </a>
                </span>
              </label>

              <label className="flex items-start gap-2 font-mono text-[11px] text-pb-faint">
                <input type="checkbox" className="mt-0.5" checked={ackAuthority}
                  onChange={(e) => setAckAuthority(e.target.checked)} />
                <span>
                  I confirm that I am associated with {preparedClub?.name || 'this club'} and I
                  understand that this is a request to evaluate BetterCricket for my club.
                </span>
              </label>

              {ackError && <p className="font-mono text-[10px] text-pb-red">{ackError}</p>}
            </div>
          )}

          {step === 'submit' && (
            <div className="space-y-3">
              {submitted ? (
                <div className="pb-card p-4 bg-pb-surface2">
                  <p className="font-mono text-[11px] text-emerald-400">
                    ✓ Club and admin account created — sync started
                  </p>

                  <div className="mt-3 pt-3 border-t pb-hairline">
                    <ProgressBar
                      pct={syncRun?.status === 'success' ? 100 : (syncRun?.stats?.progress_pct ?? 0)}
                      label={
                        syncRun?.status === 'success' ? 'Sync complete'
                          : syncRun?.status === 'error' ? `Sync failed — ${syncRun.error || 'unknown error'}`
                          : syncProgressLabel(syncRun?.stats)
                      }
                      color={syncRun?.status === 'error' ? 'var(--pb-red, #ef4444)' : undefined}
                    />
                  </div>

                  <div className="mt-3 pt-3 border-t pb-hairline">
                    <button
                      onClick={loginAsNewAdmin}
                      disabled={loggingInAs}
                      className="font-mono text-[11px] px-3 py-1.5 rounded border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-50"
                    >
                      {loggingInAs ? 'Logging in…' : 'Log in as new admin'}
                    </button>
                    {loginAsError && <p className="font-mono text-[10px] text-pb-red mt-1">{loginAsError}</p>}
                  </div>
                </div>
              ) : (
                <>
                  <div>
                    <p className="font-mono text-[10px] text-pb-faint block mb-1">Modules to trial</p>
                    <p className="font-mono text-[10px] text-pb-faintest mb-2">
                      Every club gets every module on trial — nothing to choose here.
                    </p>
                    {MODULE_TOGGLES.map((m) => (
                      <div key={m.key} className="flex items-center gap-2 mb-1.5">
                        <img src={moduleBrand(m.key).logo} alt="" className="w-5 h-5 rounded shrink-0" />
                        <span className="font-mono text-[11px] text-pb-faint flex-1">{m.label}</span>
                        <input type="checkbox" checked disabled />
                      </div>
                    ))}
                  </div>

                  <div>
                    <label className="font-mono text-[10px] text-pb-faint block mb-1">Password</label>
                    <div className="relative">
                      <input type={showPassword ? 'text' : 'password'} value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="new-password"
                        className={`${FIELD_CLS} pr-14`} />
                      <button type="button" onClick={() => setShowPassword((s) => !s)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
                        {showPassword ? 'HIDE' : 'SHOW'}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="font-mono text-[10px] text-pb-faint block mb-1">Repeat password</label>
                    <div className="relative">
                      <input type={showConfirmPassword ? 'text' : 'password'} value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        autoComplete="new-password"
                        className={`${FIELD_CLS} pr-14`} />
                      <button type="button" onClick={() => setShowConfirmPassword((s) => !s)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
                        {showConfirmPassword ? 'HIDE' : 'SHOW'}
                      </button>
                    </div>
                  </div>

                  <ul className="font-mono text-[10px] space-y-0.5">
                    <li className={passwordChecks.length ? 'text-emerald-400' : 'text-pb-faintest'}>
                      {passwordChecks.length ? '✓' : '·'} At least 10 characters
                    </li>
                    <li className={passwordChecks.upper ? 'text-emerald-400' : 'text-pb-faintest'}>
                      {passwordChecks.upper ? '✓' : '·'} One uppercase letter
                    </li>
                    <li className={passwordChecks.digit ? 'text-emerald-400' : 'text-pb-faintest'}>
                      {passwordChecks.digit ? '✓' : '·'} One number
                    </li>
                    <li className={passwordChecks.special ? 'text-emerald-400' : 'text-pb-faintest'}>
                      {passwordChecks.special ? '✓' : '·'} One special character
                    </li>
                    <li className={passwordChecks.match ? 'text-emerald-400' : 'text-pb-faintest'}>
                      {passwordChecks.match ? '✓' : '·'} Passwords match
                    </li>
                  </ul>

                  {submitError && <p className="font-mono text-[10px] text-pb-red">{submitError}</p>}
                </>
              )}
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t pb-hairline shrink-0 flex items-center justify-between gap-2">
          <div>
            {step === 'admin' && (
              <button
                onClick={() => setStep('club')}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Back
              </button>
            )}
            {step === 'verify' && (
              <button
                onClick={() => setStep('admin')}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Back
              </button>
            )}
            {step === 'ack' && (
              <button
                onClick={() => setStep('verify')}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Back
              </button>
            )}
            {step === 'submit' && (
              <button
                onClick={() => setStep('ack')}
                className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
              >
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
            >
              Cancel
            </button>
            {step === 'club' && (
              <button
                onClick={() => setStep('admin')}
                disabled={!canContinueFromClub}
                title={canContinueFromClub ? '' : 'Select an unregistered club first'}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                CONTINUE
              </button>
            )}
            {step === 'admin' && (
              <button
                onClick={() => setStep('verify')}
                disabled={!adminValid}
                title={adminValid ? '' : 'Fix the highlighted fields first'}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                CONTINUE
              </button>
            )}
            {step === 'verify' && (
              <button
                onClick={() => setStep('ack')}
                disabled={!verified}
                title={verified ? '' : 'Verify your email first'}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                CONTINUE
              </button>
            )}
            {step === 'ack' && (
              <button
                onClick={confirmAcknowledgements}
                disabled={!allAckChecked || ackSubmitting}
                title={allAckChecked ? '' : 'Accept all three to continue'}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                {ackSubmitting ? 'Recording…' : 'CONTINUE'}
              </button>
            )}
            {step === 'submit' && (
              <button
                onClick={submitRegistration}
                disabled={!canSubmit || submitted}
                title={canSubmit || submitted ? '' : 'Fix the highlighted requirements first'}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                {submitted ? 'CREATED' : submitting ? 'PROCESSING…' : `START ${defaultTrialDays} DAY FREE TRIAL`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
