import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import { api } from '../../lib/api'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// The ad-campaign landing page: one job, one CTA. Paid traffic lands here and
// either starts the self-serve trial wizard (SelfServeTrialModal in
// publicMode) or leaves — so unlike the other marketing pages there's no
// second pitch, no pricing calculator, no competing links above the fold.
// The nav and footer stay: Terms/Privacy/Contact one click away is a trust
// signal when the ask is "give us your email", not clutter.

const TRIAL_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: 'Start your club’s free trial | BetterCricket',
  url: 'https://betterat.cricket/trial',
  description:
    'Register your cricket club yourself and start a free trial of every '
    + 'BetterCricket module. No credit card and no sales call. Pick your club '
    + 'from the Cricket Australia register and you’re in.',
}

const STEPS = [
  ['Find your club', 'Search the Cricket Australia register and pick your club. If it’s on PlayHQ, we know it.'],
  ['Verify your email', 'A 4-digit code proves you’re a real person at a real mailbox. That’s the whole identity check.'],
  ['You’re in', 'Your club site goes live and we start importing your full playing history automatically, often decades of it.'],
]

const FAQS = [
  ['Do I need a credit card?', 'No. The trial needs your name, email and mobile number. Payment only comes up if you decide to subscribe after seeing your club’s data.'],
  ['What’s included in the trial?', 'Everything. BetterStats plus every add-on module (BetterSelect, BetterSocials, BetterAdmin, BetterIQ and BetterFantasy), all on at once, so your committee can judge the whole platform.'],
  ['What happens when the trial ends?', 'Nothing dramatic. Your data stays put and you choose which modules (if any) your club wants to keep. Nothing is charged automatically.'],
  ['How much history do you import?', 'Everything Cricket Australia holds for your club. For many clubs that’s every scorecard back to the 1970s or earlier, imported automatically in the background.'],
  ['Who should register the club?', 'Someone with the authority to evaluate software for the club, typically a committee member, secretary or captain. You’ll confirm that during signup.'],
]

export default function Trial() {
  usePageMeta({
    title: 'Start your club’s free trial | BetterCricket',
    description:
      'Register your cricket club yourself and start a free trial of every '
      + 'BetterCricket module. No credit card and no sales call. Pick your club '
      + 'from the Cricket Australia register and you’re in.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/trial',
    jsonLd: TRIAL_JSONLD,
  })

  const [status, setStatus] = useState(null)   // null = loading, false = unavailable
  const [wizardOpen, setWizardOpen] = useState(false)

  useEffect(() => {
    let alive = true
    api.publicSelfServeStatus()
      .then((s) => { if (alive) setStatus(s || false) })
      .catch(() => { if (alive) setStatus(false) })   // 404 while the flag is off
    return () => { alive = false }
  }, [])

  // A deeper intent signal than the global PageView: this pageview came from
  // someone the ads sent to the trial offer specifically. Ref-guarded so the
  // event fires once per visit regardless of StrictMode's double-effects —
  // ad metrics shouldn't depend on React dev/prod effect semantics.
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

  const trialDays = status?.default_trial_days || 14
  const available = !!status?.enabled

  // The page is public; only the SIGNUP is gated. While the
  // self_serve_registration_enabled flag is off (the status call 404s), the
  // hero swaps the wizard button for the "leave your details" Contact CTA —
  // flipping the flag on makes the real self-serve button live with no
  // deploy. (Per direct request: page on, self-serve button off for now.)
  const openWizard = () => {
    if (available) setWizardOpen(true)
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">

        {/* Hero — single CTA */}
        <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
          <div className="max-w-[900px] mx-auto relative text-center">
            <p className="pill mb-6 inline-flex"><span className="dot" />No credit card · No sales call</p>
            <h1 className="font-display font-bold text-[42px] sm:text-[58px] lg:text-[72px] tracking-tight leading-[0.95] mb-6">
              Your club&rsquo;s entire history, <span className="gradient-text">live in minutes.</span>
            </h1>
            <p className="text-lg lg:text-xl text-pb-dim max-w-2xl mx-auto leading-relaxed mb-10">
              Register your club yourself and start a {trialDays}-day free trial of the whole
              BetterCricket platform: stats, selection, club website, admin and analytics.
              Pick your club from the Cricket Australia register and you&rsquo;re in.
            </p>
            {status === null ? (
              <p className="font-mono text-xs text-pb-faint">Loading…</p>
            ) : available ? (
              <button
                type="button"
                onClick={openWizard}
                className="inline-flex items-center px-8 py-4 rounded-lg font-display font-bold text-lg text-pb-bg transition hover:opacity-90"
                style={{ background: 'var(--pb-accent)' }}
              >
                Start your free trial
              </button>
            ) : (
              <div className="max-w-md mx-auto">
                <p className="text-pb-dim mb-4">
                  Self-serve registration isn&rsquo;t open just yet. Leave your details and
                  we&rsquo;ll set your club up personally.
                </p>
                <Link
                  to="/contact"
                  className="inline-flex items-center px-8 py-4 rounded-lg font-display font-bold text-lg text-pb-bg transition hover:opacity-90"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  Get your club on BetterCricket
                </Link>
              </div>
            )}
            <p className="font-mono text-[11px] text-pb-faintest mt-5">
              Takes about 3 minutes · Every module included · Cancel nothing, because nothing is charged
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

        {/* What you get */}
        <section className="px-4 sm:px-6 lg:px-10 pb-16">
          <div className="max-w-[1000px] mx-auto pb-card p-8">
            <h2 className="font-display font-bold text-2xl mb-4">The whole platform, switched on</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm text-pb-dim">
              <p><span className="text-pb-text font-semibold">BetterStats</span>: your full playing history as a live public club site: profiles, records, leaderboards, yearbooks.</p>
              <p><span className="text-pb-text font-semibold">BetterSelect</span>: player availability with no app, and a selection board that suggests a balanced XI.</p>
              <p><span className="text-pb-text font-semibold">BetterSocials</span>: match-day graphics and your club website, generated from real scorecards.</p>
              <p><span className="text-pb-text font-semibold">BetterAdmin</span>: fees that reconcile themselves, bulk club email, merch and stock tracking.</p>
              <p><span className="text-pb-text font-semibold">BetterIQ</span>: opposition scouting dossiers and team analytics built from your own scorecards.</p>
              <p><span className="text-pb-text font-semibold">BetterFantasy</span>: a club fantasy comp scored off your real games. Pre-season fundraiser sorted.</p>
            </div>
            <p className="font-mono text-[11px] text-pb-faintest mt-6">
              After the trial, keep only what your club wants, from $399/yr for BetterStats.{' '}
              <Link to="/pricing" className="underline hover:text-pb-text">See pricing</Link>.
            </p>
          </div>
        </section>

        {/* Mini FAQ */}
        <section className="px-4 sm:px-6 lg:px-10 pb-20">
          <div className="max-w-[800px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">Fair questions</h2>
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
          onClose={() => setWizardOpen(false)}
        />
      )}
    </div>
  )
}
