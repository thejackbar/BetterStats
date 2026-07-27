import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import { api } from '../../lib/api'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { getVisitorId } from '../../lib/visitor'
import { getMetaEventContext } from '../../lib/metaPixel'

// The ad-campaign landing page. Search-first, and nothing else in the way: the
// giant search box sits directly under the header so the one thing we want a
// visitor to do — look up their club — is unmissable. Clicking a result either
// opens their existing club page (if already on BetterCricket) or a small
// choose-modal that offers to set the club up now (free, no card) or have us
// reach out. We deliberately keep any trial framing OFF the landing page — the
// goal is to get people inputting their club with no thinking; the "it's a free
// trial" reassurance only appears once they've picked a club that isn't set up.

const TRIAL_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: 'Find your cricket club | BetterCricket',
  url: 'https://betterat.cricket/trial',
  description:
    'Search for your cricket club and bring its entire history to life on '
    + 'BetterCricket. If it’s not set up yet, get it going in minutes or ask us to reach out.',
}

const FAQS = [
  ['Is it free to get started?', 'Yes. Setting your club up is free and we never ask for a credit card. Add your name, email and mobile and your club goes live.'],
  ['What’s included?', 'Everything. BetterStats plus every add-on module (BetterSelect, BetterSocials, BetterAdmin, BetterIQ and BetterFantasy), all on at once, so your committee can judge the whole platform.'],
  ['How much history do you import?', 'Everything Cricket Australia holds for your club, imported automatically in the background. There’s no limit on how far back it goes. And if your club has old spreadsheets, we can bring those into BetterCricket too.'],
  ['Who should register the club?', 'Someone with the authority to evaluate software for the club, typically a committee member, secretary or captain. You’ll confirm that during signup.'],
]

const FIELD_CLS = 'w-full bg-pb-surface2 text-pb-text border pb-hairline rounded-lg px-4 py-3 text-base outline-none focus:border-pb-accent'
const orgName = (o) => o.name || o.shortName || o.organisationName || o.id || ''

// Club logo, same idea as elsewhere in BetterCricket: show the club's crest
// when we have one (PlayHQ search results carry it for many clubs), and fall
// back to an initials badge otherwise — never a broken image.
function ClubLogo({ club, size = 'w-10 h-10' }) {
  const [ok, setOk] = useState(true)
  const src = club.logoUrl
    || (typeof club.logo === 'string' ? club.logo : club.logo?.url)
    || club.imageUrl || club.logo_url
  const initials = orgName(club).split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase()
  if (src && ok) {
    return (
      <img
        src={src}
        alt=""
        onError={() => setOk(false)}
        className={`${size} rounded-lg object-contain bg-pb-surface2 shrink-0`}
      />
    )
  }
  return (
    <span className={`${size} rounded-lg bg-pb-surface2 border pb-hairline shrink-0 flex items-center justify-center font-display font-bold text-[11px] text-pb-dim`}>
      {initials || '\u{1F3CF}'}
    </span>
  )
}

function SearchIcon({ className = 'w-6 h-6' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

// The pre-filled "reach out" form — club name is already known from the
// search, so it only asks for a name and email, then posts into the same
// onboarding-request pipeline the Contact form uses (super-admin Onboarding
// list + a Hot lead into the CRM).
function RequestInfoForm({ club, onDone }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim() || !email.trim()) { setError('Add your name and email.'); return }
    setSubmitting(true)
    setError('')
    try {
      const meta = getMetaEventContext()
      await api.submitOnboarding({
        club: orgName(club),
        name: name.trim(),
        email: email.trim(),
        source: 'trial_search_request',
        visitorId: getVisitorId(),
        meta,
      })
      if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
        window.fbq('track', 'Lead', {
          content_name: 'Trial info request',
          content_category: 'self_serve_trial',
        }, { eventID: meta?.eventId })
      }
      onDone()
    } catch (err) {
      setError(err?.message || 'Could not send that just now. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-2 space-y-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Your name"
        className={FIELD_CLS}
      />
      <input
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        type="email"
        placeholder="Your email"
        className={FIELD_CLS}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
      <button
        type="submit"
        disabled={submitting}
        className="w-full px-4 py-2.5 rounded-lg font-display font-semibold text-sm text-pb-bg transition hover:opacity-90 disabled:opacity-50"
        style={{ background: 'var(--pb-accent)' }}
      >
        {submitting ? 'Sending…' : 'Send my request'}
      </button>
    </form>
  )
}

// Shown when a not-yet-registered club is clicked. This is the one place trial
// reassurance lives: set the club up now (free, no credit card) or ask us to
// reach out (the enquiry form).
function ClubActionModal({ club, onSetUp, onClose }) {
  const [mode, setMode] = useState('choose')   // choose | request | done

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div className="w-full max-w-md pb-card p-6 relative bg-pb-bg" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3 text-pb-faint hover:text-pb-text text-lg leading-none"
        >
          ✕
        </button>
        <div className="flex items-center gap-3 mb-4">
          <ClubLogo club={club} size="w-11 h-11" />
          <h3 className="font-display font-bold text-lg leading-tight">{orgName(club)}</h3>
        </div>

        {mode === 'done' ? (
          <p className="font-mono text-[12px] text-emerald-300">
            Thanks — we&rsquo;ve got your request and we&rsquo;ll be in touch shortly.
          </p>
        ) : mode === 'request' ? (
          <>
            <p className="text-sm text-pb-dim mb-1">
              Leave your details and we&rsquo;ll help get {orgName(club)} onto BetterCricket.
            </p>
            <RequestInfoForm club={club} onDone={() => setMode('done')} />
            <button
              onClick={() => setMode('choose')}
              className="mt-3 font-mono text-[11px] text-pb-faint underline hover:text-pb-text"
            >
              ← Back
            </button>
          </>
        ) : (
          <>
            <p className="text-sm text-pb-dim mb-4">
              {orgName(club)} isn&rsquo;t on BetterCricket yet. Set it up yourself now — it&rsquo;s
              free and we never ask for a credit card — or ask us to reach out and we&rsquo;ll help
              get you started.
            </p>
            <div className="space-y-2">
              <button
                onClick={() => onSetUp(club)}
                className="w-full px-4 py-2.5 rounded-lg font-display font-semibold text-sm text-pb-bg transition hover:opacity-90"
                style={{ background: 'var(--pb-accent)' }}
              >
                Set up my club
              </button>
              <p className="text-center font-mono text-[10px] text-pb-faintest">Free · No credit card</p>
              <button
                onClick={() => setMode('request')}
                className="w-full px-4 py-2.5 rounded-lg font-display font-semibold text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 transition"
              >
                Ask us to reach out
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function Trial() {
  usePageMeta({
    title: 'Find your cricket club | BetterCricket',
    description:
      'Search for your cricket club and bring its entire history to life on '
      + 'BetterCricket. If it’s not set up yet, get it going in minutes or ask us to reach out.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/trial',
    jsonLd: TRIAL_JSONLD,
  })

  const navigate = useNavigate()

  const [status, setStatus] = useState(null)   // null = loading, false = unavailable
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardClub, setWizardClub] = useState(null)
  const [actionClub, setActionClub] = useState(null)   // club whose choose-modal is open

  // Search-first hero state.
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searched, setSearched] = useState(false)
  const debounceRef = useRef(null)

  useEffect(() => {
    let alive = true
    api.publicSelfServeStatus()
      .then((s) => { if (alive) setStatus(s || false) })
      .catch(() => { if (alive) setStatus(false) })   // 404 while the flag is off
    return () => { alive = false }
  }, [])

  // A deeper intent signal than the global PageView: this pageview came from
  // someone the ads sent to the trial offer specifically. Ref-guarded so the
  // event fires once per visit regardless of StrictMode's double-effects.
  const viewTracked = useRef(false)
  useEffect(() => {
    if (viewTracked.current) return
    viewTracked.current = true
    if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
      window.fbq('track', 'ViewContent', {
        content_name: 'Self-serve trial landing',
        content_category: 'self_serve_trial',
      })
    }
  }, [])

  const available = !!status?.enabled

  // Debounced club search (min 2 chars), hitting the same public search the
  // wizard uses — results carry `already_registered` + the existing club's
  // public-page slug (and often a logo), which drive the click behaviour below.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      setSearched(false)
      setSearchError('')
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      setSearchError('')
      try {
        const data = await api.publicSelfServeSearch(q)
        setResults(Array.isArray(data) ? data : [])
        setSearched(true)
      } catch (e) {
        setResults([])
        setSearchError(e?.message || 'Club search failed. Try again in a moment.')
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [query])

  const trialDays = status?.default_trial_days || 14

  // While the self_serve_registration_enabled flag is off (the status call
  // 404s), anyone landing here is redirected to the Contact page — the flag is
  // the single switch. Flipping it on makes the page AND signup live, no deploy.
  if (status === false) return <Navigate to="/contact" replace />

  // Every result row looks identical, so clicking one is a real "this is my
  // club" signal — recorded for ALL clubs (live or not), not only when a
  // prospect commits, so the interest data is captured properly. Then route by
  // status: a live club opens its page, a new one opens the Set Up / reach-out
  // choice. The beacon is fire-and-forget and survives the client-side navigate
  // (no page unload), so the click is logged either way.
  const handleClubClick = (club) => {
    api.publicSelfServeTrackStep('club_prepared', getVisitorId(), {
      name: orgName(club), org_id: club.id,
    }).catch(() => {})
    if (club.already_registered && club.already_registered_slug) {
      navigate(`/${club.already_registered_slug}`)
      return
    }
    setActionClub(club)
  }

  const onSetUp = (club) => {
    setActionClub(null)
    setWizardClub(club)
    setWizardOpen(true)
  }
  const openWizardBlank = () => {
    if (!available) return
    setWizardClub(null)
    setWizardOpen(true)
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">

        {/* Hero — the giant search sits right under the header so it's the first
            and most obvious thing to do. No trial/credit-card framing here. */}
        <section className="relative pt-24 pb-10 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-3xl mx-auto relative text-center">
            <h1 className="font-display font-bold text-[28px] sm:text-[40px] lg:text-[50px] tracking-tight leading-[1.02] mb-3">
              Find your club. See its <span className="gradient-text">entire history</span> come to life.
            </h1>
            <p className="text-base sm:text-lg text-pb-dim max-w-xl mx-auto leading-relaxed mb-7">
              Every player, season and record your club has ever had — search for it below.
            </p>

            {status === null ? (
              <p className="font-mono text-xs text-pb-faint">Loading…</p>
            ) : available ? (
              <div className="max-w-2xl mx-auto text-left">
                <div className="relative">
                  <span className="absolute left-5 sm:left-6 top-1/2 -translate-y-1/2 text-pb-faint pointer-events-none">
                    <SearchIcon className="w-6 h-6 sm:w-7 sm:h-7" />
                  </span>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search for your club…"
                    aria-label="Search for your club"
                    autoFocus
                    className="w-full bg-pb-surface2 text-pb-text rounded-2xl pl-14 sm:pl-16 pr-5 py-5 sm:py-6 text-lg sm:text-2xl font-display font-semibold outline-none shadow-xl border-2 transition focus:shadow-2xl"
                    style={{ borderColor: 'var(--pb-accent)' }}
                  />
                </div>

                <div className="mt-3 space-y-2">
                  {searching && <p className="font-mono text-[11px] text-pb-faint px-1">Searching…</p>}
                  {searchError && <p className="text-xs text-red-400 px-1">{searchError}</p>}

                  {results.map((club) => (
                    <button
                      key={club.id || orgName(club)}
                      type="button"
                      onClick={() => handleClubClick(club)}
                      className="w-full pb-card p-4 flex items-center gap-3 text-left hover:border-accent/40 transition"
                    >
                      <ClubLogo club={club} />
                      <span className="flex-1 min-w-0 font-display font-semibold text-base truncate">{orgName(club)}</span>
                      <span className="text-pb-faint shrink-0">→</span>
                    </button>
                  ))}

                  {searched && !searching && results.length === 0 && !searchError && (
                    <div className="pb-card p-4">
                      <p className="text-sm text-pb-dim">
                        No clubs matched &ldquo;{query.trim()}&rdquo;.
                      </p>
                      <div className="flex flex-wrap gap-2 mt-2">
                        <button
                          type="button"
                          onClick={openWizardBlank}
                          className="inline-flex items-center px-4 py-2 rounded-lg font-display font-semibold text-sm text-pb-bg transition hover:opacity-90"
                          style={{ background: 'var(--pb-accent)' }}
                        >
                          Set up your club anyway
                        </button>
                        <a
                          href={`mailto:${SUPPORT_EMAIL}`}
                          className="inline-flex items-center px-4 py-2 rounded-lg font-display font-semibold text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 transition"
                        >
                          Email us
                        </a>
                      </div>
                    </div>
                  )}
                </div>

                <p className="font-mono text-[11px] text-pb-faintest mt-4 text-center">
                  Can&rsquo;t find your club?{' '}
                  <button type="button" onClick={openWizardBlank} className="underline hover:text-pb-text">
                    Set it up yourself
                  </button>
                </p>
              </div>
            ) : null}
          </div>
        </section>

        {/* A real club home page, so the offer is concrete. Sits below the
            search (the search stays the first thing a visitor sees). */}
        <section className="px-4 sm:px-6 lg:px-10 pb-14">
          <div className="max-w-4xl mx-auto">
            <img
              src="/marketing/club-home.png"
              alt="A club’s home page on BetterCricket"
              loading="lazy"
              className="w-full rounded-xl border pb-hairline shadow-2xl"
            />
            <p className="text-center font-mono text-[11px] text-pb-faintest mt-3">
              A real club, live on BetterCricket.
            </p>
          </div>
        </section>

        {/* Modules — brought up so visitors can see everything BetterCricket
            does. Same cards as the homepage, each clicking through. */}
        <section className="px-4 sm:px-6 lg:px-10 pb-16">
          <div className="max-w-[1200px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">
              Everything BetterCricket does for your club
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {MODULES_MARKETING.map((m, i) => (
                <Reveal key={m.slug} delay={(i % 4) * 70} className="h-full">
                  <Link to={`/modules/${m.slug}`} className="surface p-6 h-full flex flex-col hover:border-accent/30 transition-colors group block">
                    <div className="flex items-center justify-between mb-4">
                      <img src={m.logo} alt="" className="w-10 h-10 rounded-xl" />
                    </div>
                    <h3 className="text-lg font-semibold mb-1.5"><ModuleWordmark name={m.name} accent={m.accent} /></h3>
                    <p className="text-sm text-pb-dim leading-relaxed mb-4 flex-1">{m.tagline}</p>
                    <span className="text-sm font-medium inline-flex items-center gap-1" style={{ color: m.accent }}>Explore <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
                  </Link>
                </Reveal>
              ))}
            </div>
            <p className="font-mono text-[11px] text-pb-faintest mt-6 text-center">
              Keep only the modules your club wants, from $399/yr for BetterStats.{' '}
              <Link to="/pricing" className="underline hover:text-pb-text">See pricing</Link>.
            </p>
          </div>
        </section>

        {/* Mini FAQ */}
        <section className="px-4 sm:px-6 lg:px-10 pb-20">
          <div className="max-w-[800px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">Questions</h2>
            <div className="space-y-3">
              {FAQS.map(([q, a]) => (
                <details key={q} className="pb-card p-5 group">
                  <summary className="font-display font-semibold cursor-pointer list-none flex items-center justify-between gap-3">
                    {q}
                    <span className="font-mono text-pb-faint group-open:rotate-45 transition-transform shrink-0">+</span>
                  </summary>
                  <p className="text-sm text-pb-dim leading-relaxed mt-3">{a}</p>
                </details>
              ))}
            </div>
            <p className="text-center font-mono text-[11px] text-pb-faintest mt-8">
              Something else on your mind? <a href={`mailto:${SUPPORT_EMAIL}`} className="underline hover:text-pb-text">{SUPPORT_EMAIL}</a>
            </p>
          </div>
        </section>
      </div>
      <MarketingFooter />

      {actionClub && (
        <ClubActionModal
          club={actionClub}
          onSetUp={onSetUp}
          onClose={() => setActionClub(null)}
        />
      )}

      {wizardOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={trialDays}
          initialClub={wizardClub}
          onClose={() => { setWizardOpen(false); setWizardClub(null) }}
        />
      )}
    </div>
  )
}
