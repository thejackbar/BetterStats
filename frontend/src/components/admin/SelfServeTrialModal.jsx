import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { SUPPORT_EMAIL } from '../../data/marketing'

// Step scaffold for the self-serve trial registration flow (see
// docs/self-serve-trial-onboarding-plan.md). Steps after 'club' aren't built yet —
// each lands in its own later phase. Keeping the list here now so the stepper UI
// doesn't need reshaping when a step's content arrives.
const STEPS = [
  { key: 'club', label: 'Club' },
  { key: 'admin', label: 'Admin details' },
  { key: 'verify', label: 'Verify email' },
  { key: 'ack', label: 'Acknowledgements' },
  { key: 'submit', label: 'Submit' },
]

const orgName = (org) => org.name || org.shortName || org.organisationName || org.id || ''

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

          <div className="relative">
            <label className="font-mono text-[10px] text-pb-faint block mb-1">Search for your club</label>
            <input
              type="text"
              value={query}
              disabled={!!selectedClub}
              onChange={(e) => { setQuery(e.target.value); setDuplicateClub(null) }}
              onFocus={() => { if (results.length > 0) setShowResults(true) }}
              placeholder="Start typing your club's name…"
              className="w-full bg-pb-surface2 text-pb-text border pb-hairline rounded px-3 py-2 text-sm outline-none focus:border-pb-accent disabled:opacity-60"
            />

            {showResults && results.length > 0 && !selectedClub && (
              <div className="absolute z-10 mt-1 w-full pb-card bg-pb-surface max-h-64 overflow-y-auto">
                {results.map((org) => (
                  <button
                    key={org.id}
                    type="button"
                    onClick={() => selectClub(org)}
                    className="w-full text-left px-3 py-2 hover:bg-pb-surface2 border-b pb-hairline last:border-b-0"
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
                  </button>
                ))}
              </div>
            )}

            {showResults && !searching && results.length === 0 && query.trim().length >= 2 && !selectedClub && (
              <div className="absolute z-10 mt-1 w-full pb-card bg-pb-surface px-3 py-2">
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
                  <div>
                    <dt className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Source club ID</dt>
                    <dd className="text-pb-faint text-xs font-mono">{preparedClub.org_id}</dd>
                  </div>
                </dl>
              )}
            </div>
          )}

          {!selectedClub && (
            <div className="pb-card p-4 bg-pb-surface2">
              <p className="font-mono text-[11px] text-pb-faint">
                The rest of registration (admin details, email verification,
                acknowledgements, submission) isn't built yet — it lands in later
                phases of docs/self-serve-trial-onboarding-plan.md.
              </p>
            </div>
          )}
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
            title="Not wired up yet — the remaining registration steps land in later phases."
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
