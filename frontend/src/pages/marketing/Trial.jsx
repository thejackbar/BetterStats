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

// The ad-campaign landing page. Search-first: the visitor looks up their club
// and CLICKS it (a real selection signal we can record, unlike a half-typed
// query they abandon). Clicking either takes them to their existing page (if
// already on BetterCricket) or opens a modal to Set Up Club or Request Access.
// The "request access" path feeds the same onboarding pipeline as the Contact
// form. A product screenshot sits above the search so the offer is concrete,
// with the search box kept within reach on every device.

const TRIAL_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: 'Start your club’s free trial | BetterCricket',
  url: 'https://betterat.cricket/trial',
  description:
    'Search for your cricket club to see if it’s on BetterCricket. If not, start '
    + 'a free trial of every module, or request access. No credit card and no sales call.',
}

const STEPS = [
  ['Find Your Club', 'Simple search to ensure you sync the correct Australian cricket club.'],
  ['Enter Your Details', 'Set up your admin profile.'],
  ['Complete Setup Wizard', 'We take you through your initial set up step-by-step to customise BetterCricket to your club and clean up your data.'],
]

const FAQS = [
  ['Do I need a credit card?', 'No. The trial needs your name, email and mobile number. Payment only comes up if you decide to subscribe after seeing your club’s data.'],
  ['What’s included in the trial?', 'Everything. BetterStats plus every add-on module (BetterSelect, BetterSocials, BetterAdmin, BetterIQ and BetterFantasy), all on at once, so your committee can judge the whole platform.'],
  ['What happens when the trial ends?', 'Your club’s page comes offline, but we don’t delete your stats. Everything stays safely stored, so you can come back online whenever your club is ready. Nothing is charged automatically.'],
  ['How much history do you import?', 'Everything Cricket Australia holds for your club, imported automatically in the background. There’s no limit on how far back it goes. And if your club has old spreadsheets, we can bring those into BetterCricket too.'],
  ['Who should register the club?', 'Someone with the authority to evaluate software for the club, typically a committee member, secretary or captain. You’ll confirm that during signup.'],
]

const FIELD_CLS = 'w-full bg-pb-surface2 text-pb-text border pb-hairline rounded-lg px-4 py-3 text-base outline-none focus:border-pb-accent'
const orgName = (o) => o.name || o.shortName || o.organisationName || o.id || ''

// Club logo, same idea as elsewhere in BetterCricket: show the club's crest
// when we have one (PlayHQ search results carry it for many clubs), and fall
// back to an initials badge otherwise — never a broken image.
function ClubLogo({ club, size = 'w-9 h-9' }) {
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

// The pre-filled "request access" form — club name is already known from the
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

// Shown when a not-yet-registered club is clicked: choose Set Up Club (the
// self-serve trial wizard, pre-seeded) or Request Access (the enquiry form).
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
              Request access and we&rsquo;ll help you get {orgName(club)} onto BetterCricket.
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
              Get {orgName(club)} onto BetterCricket. Set it up yourself with a free trial, or request
              access and we&rsquo;ll help you get started.
            </p>
            <div className="space-y-2">
              <button
                onClick={() => onSetUp(club)}
                className="w-full px-4 py-2.5 rounded-lg font-display font-semibold text-sm text-pb-bg transition hover:opacity-90"
                style={{ background: 'var(--pb-accent)' }}
              >
                Set Up Club
              </button>
              <button
                onClick={() => setMode('request')}
                className="w-full px-4 py-2.5 rounded-lg font-display font-semibold text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 transition"
              >
                Request Access
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
    title: 'Start your club’s free trial | BetterCricket',
    description:
      'Search for your cricket club to see if it’s on BetterCricket. If not, start '
      + 'a free trial of every module, or request access. No credit card and no sales call.',
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

  // Clicking a club is a real, trackable selection (unlike a half-typed query
  // someone abandons). An already-registered club goes straight to its page; a
  // new one records the pick (so a prospect who then backs out of the modal is
  // still captured) and opens the Set Up / Request Access choice.
  const handleClubClick = (club) => {
    if (club.already_registered && club.already_registered_slug) {
      navigate(`/${club.already_registered_slug}`)
      return
    }
    api.publicSelfServeTrackStep('club_prepared', getVisitorId(), {
      name: orgName(club), org_id: club.id,
    }).catch(() => {})
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

        {/* Hero — screenshot + search, kept tight so the search box stays in
            reach on phones (the image is capped in viewport height). */}
        <section className="relative pt-24 pb-14 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-[760px] mx-auto relative text-center">
            <p className="pill mb-4 inline-flex"><span className="dot" />No credit card · No sales call</p>
            <h1 className="font-display font-bold text-[30px] sm:text-[42px] lg:text-[54px] tracking-tight leading-[0.98] mb-4">
              Your club&rsquo;s entire history, <span className="gradient-text">live in minutes.</span>
            </h1>
            <p className="text-base sm:text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed mb-5">
              Find your club to get started — free {trialDays}-day trial, no credit card.
            </p>

            {/* A real set-up club, so the offer is concrete. Height-capped so the
                search below never drops off the first screen on any device. */}
            <div className="mb-6 mx-auto max-w-xl">
              <img
                src="/marketing/front-page-profile.jpg"
                alt="A club’s player profile on BetterCricket"
                loading="eager"
                className="w-full rounded-xl border pb-hairline shadow-lg object-contain max-h-[26vh] sm:max-h-[32vh]"
              />
            </div>

            {status === null ? (
              <p className="font-mono text-xs text-pb-faint">Loading…</p>
            ) : available ? (
              <div className="max-w-xl mx-auto text-left">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search for your club…"
                  aria-label="Search for your club"
                  autoFocus
                  className={FIELD_CLS}
                />

                <div className="mt-2 space-y-2">
                  {searching && <p className="font-mono text-[11px] text-pb-faint px-1">Searching…</p>}
                  {searchError && <p className="text-xs text-red-400 px-1">{searchError}</p>}

                  {results.map((club) => (
                    <button
                      key={club.id || orgName(club)}
                      type="button"
                      onClick={() => handleClubClick(club)}
                      className="w-full pb-card p-3 flex items-center gap-3 text-left hover:border-accent/40 transition"
                    >
                      <ClubLogo club={club} />
                      <span className="flex-1 min-w-0">
                        <span className="block font-display font-semibold text-sm truncate">{orgName(club)}</span>
                        {club.already_registered ? (
                          <span className="block font-mono text-[10px] text-emerald-300 mt-0.5">✓ Already on BetterCricket — view page</span>
                        ) : (
                          <span className="block font-mono text-[10px] text-pb-faint mt-0.5">Set up or request access</span>
                        )}
                      </span>
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
                          Start the full wizard
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
                  Prefer to just dive in?{' '}
                  <button type="button" onClick={openWizardBlank} className="underline hover:text-pb-text">
                    Start the free trial wizard
                  </button>
                </p>
              </div>
            ) : null}

            <p className="font-mono text-[11px] text-pb-faintest mt-6">
              Quick and Easy Setup · Every Module Included · No Obligation
            </p>
          </div>
        </section>

        {/* How it works */}
        <section className="px-4 sm:px-6 lg:px-10 pb-16">
          <div className="max-w-[1000px] mx-auto grid grid-cols-1 sm:grid-cols-3 gap-4">
            {STEPS.map(([title, body], i) => (
              <Reveal key={title} delay={i * 80}>
                <div className="pb-card p-6 h-full">
                  <p className="font-mono text-[11px] tracking-wide3 text-pb-faint uppercase mb-2">Step {i + 1}</p>
                  <h3 className="font-display font-bold text-lg mb-2">{title}</h3>
                  <p className="text-sm text-pb-dim leading-relaxed">{body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* Modules — same cards as the homepage, each clicking through */}
        <section className="px-4 sm:px-6 lg:px-10 pb-16">
          <div className="max-w-[1200px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">
              Then you&rsquo;re free to explore everything BetterCricket has to offer
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
              After the trial, keep only what your club wants, from $399/yr for BetterStats.{' '}
              <Link to="/pricing" className="underline hover:text-pb-text">See pricing</Link>.
            </p>
          </div>
        </section>

        {/* Mini FAQ */}
        <section className="px-4 sm:px-6 lg:px-10 pb-20">
          <div className="max-w-[800px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">Free Trial FAQs</h2>
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
