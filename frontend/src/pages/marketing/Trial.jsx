import { useEffect, useRef, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
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

// The ad-campaign landing page. Search-first: the visitor looks up their club,
// and one of three things happens — it's already on BetterCricket (link to the
// page), it's not (start the self-serve trial pre-seeded with that club), or
// they'd rather we get in touch (a pre-filled enquiry into the same onboarding
// pipeline as the Contact form). A search box converts better than a cold
// "start trial" button, and even a request-for-info is a strong interest signal.

const TRIAL_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: 'Start your club’s free trial | BetterCricket',
  url: 'https://betterat.cricket/trial',
  description:
    'Search for your cricket club to see if it’s on BetterCricket. If not, start '
    + 'a free trial of every module, or ask us for more information. No credit '
    + 'card and no sales call.',
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

// The pre-filled "just want info" form — club name is already known from the
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
      // Browser-side Lead, deduped with the server-side one /public/contact
      // fires (shared eventId) — same pattern as the Contact form.
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
    <form onSubmit={submit} className="mt-3 space-y-2">
      <p className="font-mono text-[11px] text-pb-faint">
        We’ll fill in {orgName(club)} — just add your details and we’ll be in touch.
      </p>
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

export default function Trial() {
  usePageMeta({
    title: 'Start your club’s free trial | BetterCricket',
    description:
      'Search for your cricket club to see if it’s on BetterCricket. If not, start '
      + 'a free trial of every module, or ask us for more information. No credit '
      + 'card and no sales call.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/trial',
    jsonLd: TRIAL_JSONLD,
  })

  const [status, setStatus] = useState(null)   // null = loading, false = unavailable
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardClub, setWizardClub] = useState(null)

  // Search-first hero state.
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searched, setSearched] = useState(false)
  const [infoClubId, setInfoClubId] = useState(null)   // which result's info form is open
  const [doneClubId, setDoneClubId] = useState(null)   // which result's request was sent
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
  // public-page slug, which is what drives the three outcomes below.
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

  const setUpClub = (club) => {
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

        {/* Hero — search-first */}
        <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-[760px] mx-auto relative text-center">
            <p className="pill mb-6 inline-flex"><span className="dot" />No credit card · No sales call</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[56px] lg:text-[68px] tracking-tight leading-[0.95] mb-6">
              Your club&rsquo;s entire history, <span className="gradient-text">live in minutes.</span>
            </h1>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto leading-relaxed mb-8">
              Search for your club to get started. If it&rsquo;s already on BetterCricket we&rsquo;ll
              take you there. If not, set up your {trialDays}-day free trial in a few minutes, or ask
              us for more information.
            </p>

            {status === null ? (
              <p className="font-mono text-xs text-pb-faint">Loading…</p>
            ) : available ? (
              <div className="max-w-xl mx-auto text-left">
                <input
                  value={query}
                  onChange={(e) => { setQuery(e.target.value); setInfoClubId(null); setDoneClubId(null) }}
                  placeholder="Search for your club…"
                  aria-label="Search for your club"
                  autoFocus
                  className={FIELD_CLS}
                />

                <div className="mt-2 space-y-2">
                  {searching && <p className="font-mono text-[11px] text-pb-faint px-1">Searching…</p>}
                  {searchError && <p className="text-xs text-red-400 px-1">{searchError}</p>}

                  {results.map((club) => (
                    <div key={club.id || orgName(club)} className="pb-card p-4">
                      {club.already_registered ? (
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <div>
                            <p className="font-display font-semibold text-sm">{orgName(club)}</p>
                            <p className="font-mono text-[11px] text-emerald-300 mt-0.5">✓ Already on BetterCricket</p>
                          </div>
                          {club.already_registered_slug ? (
                            <a
                              href={`/${club.already_registered_slug}`}
                              className="inline-flex items-center px-4 py-2 rounded-lg font-display font-semibold text-sm border border-pb-accent text-pb-text hover:bg-pb-accent/10 transition"
                            >
                              View club page →
                            </a>
                          ) : (
                            <span className="font-mono text-[11px] text-pb-faint">Contact your club admin to get access</span>
                          )}
                        </div>
                      ) : (
                        <>
                          <p className="font-display font-semibold text-sm">{orgName(club)}</p>
                          {doneClubId === club.id ? (
                            <p className="font-mono text-[11px] text-emerald-300 mt-1">
                              Thanks — we&rsquo;ve got your request and we&rsquo;ll be in touch shortly.
                            </p>
                          ) : infoClubId === club.id ? (
                            <RequestInfoForm
                              club={club}
                              onDone={() => { setDoneClubId(club.id); setInfoClubId(null) }}
                            />
                          ) : (
                            <div className="flex flex-wrap gap-2 mt-2">
                              <button
                                type="button"
                                onClick={() => setUpClub(club)}
                                className="inline-flex items-center px-4 py-2 rounded-lg font-display font-semibold text-sm text-pb-bg transition hover:opacity-90"
                                style={{ background: 'var(--pb-accent)' }}
                              >
                                Set up this club
                              </button>
                              <button
                                type="button"
                                onClick={() => setInfoClubId(club.id)}
                                className="inline-flex items-center px-4 py-2 rounded-lg font-display font-semibold text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 transition"
                              >
                                Request Access
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
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
