import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import CountUp from '../../components/marketing/CountUp'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import Aurora from '../../components/marketing/Aurora'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import TrustedByStrip from '../../components/marketing/TrustedByStrip'
import { DemoBand, WatchDemoLink } from '../../components/marketing/DemoLinks'
import {
  MockHeritageCard,
  MockLeaderboard,
  MockPlayerProfile,
  MockYearbook,
} from '../../components/marketing/Mockups'
import {
  TESTIMONIALS,
  HOW_IT_WORKS,
  SCREENSHOT_PATHS,
} from '../../data/marketing'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'
import { useSelfServeTrialGate } from '../../hooks/useSelfServeTrialGate'

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero({ onCta }) {
  // Aurora in the brand colours, read from the theme tokens so it always
  // matches the site CSS: the brand green, then the blue, then back to green.
  const stops = useMemo(() => {
    const fallback = ['#16c784', '#3b82f6', '#16c784']
    if (typeof window === 'undefined') return fallback
    const cs = getComputedStyle(document.documentElement)
    const accent = cs.getPropertyValue('--pb-accent').trim() || fallback[0]
    const accent2 = cs.getPropertyValue('--pb-accent-2').trim() || fallback[1]
    return [accent, accent2, accent]
  }, [])
  return (
    <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-10 overflow-hidden">
      {/* A glow along the top edge, faded out before the copy so it never fights the text */}
      <div
        className="absolute inset-x-0 top-0 h-[520px] sm:h-[600px] z-0 pointer-events-none"
        style={{
          WebkitMaskImage: 'linear-gradient(to bottom, #000 35%, transparent 100%)',
          maskImage: 'linear-gradient(to bottom, #000 35%, transparent 100%)',
        }}
      >
        <Aurora
          colorStops={stops}
          amplitude={0.9}
          blend={0.55}
          speed={0.6}
          height={0.36}
          glow={0.55}
          brightness={0.9}
          opacity={0.95}
          layers={2}
          dpr={1.5}
        />
      </div>
      <div className="absolute inset-0 hero-glow pointer-events-none" />

      <div className="max-w-[1280px] mx-auto relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        <div className="col-span-1 lg:col-span-5">
          <div className="pill mb-7 inline-flex">
            <span className="dot" />
            For Australian cricket clubs · Since 2026
          </div>
          <h1 className="font-display font-bold text-[52px] sm:text-[68px] lg:text-[88px] tracking-tight leading-[0.92] mb-7">
            We do cricket<span className="text-pb-dim">…</span><br />
            <span className="gradient-text">Better.</span>
          </h1>
          <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-8 max-w-xl">
            BetterCricket is the platform Australian cricket clubs run on. Your whole history on a site worth showing off, then selection, socials, admin and analytics on top.
          </p>

          <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-3 mb-4">
            <button type="button" onClick={onCta} className="cta-primary">
              Get Your Club on BetterCricket today!
            </button>
            <a href="#showcase" className="cta-secondary">See it in action</a>
          </div>

          <div className="mb-7 flex flex-col sm:flex-row sm:items-center gap-x-6 gap-y-2 items-center">
            <WatchDemoLink placement="hero">Watch the full demo</WatchDemoLink>
            <Link to="/overview" className="text-sm text-accent font-medium hover:underline inline-flex items-center gap-1">
              See everything BetterCricket does →
            </Link>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-pb-faint">
            <span className="flex items-center gap-2"><span className="tick">✓</span>Live in under an hour</span>
            <span className="flex items-center gap-2"><span className="tick">✓</span>Simple onboarding</span>
          </div>
        </div>

        <Reveal className="col-span-1 lg:col-span-7">
          <div className="relative">
            <div className="absolute -inset-5 bg-accent/10 blur-[60px] rounded-full" />
            <div className="relative product-shadow rounded-2xl overflow-hidden">
              <ScreenshotOrMock
                src={SCREENSHOT_PATHS.clubDashboard}
                alt="A club dashboard on BetterCricket"
                fallback={<MockHeritageCard />}
              />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Stat banner ─────────────────────────────────────────────────────────
function StatBanner() {
  const stats = [
    { v: 4500, suffix: '+', label: 'Australian cricket clubs ready to set up' },
    { display: '1M', suffix: '+', label: 'players ready for active profiles' },
    { v: 200, suffix: '+', label: 'pre-built reports in StatLab' },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-16 border-y pb-hairline relative overflow-hidden bg-black/20">
      <div className="absolute inset-0 dot-grid opacity-30" />
      <div className="max-w-[1100px] mx-auto relative grid grid-cols-1 md:grid-cols-3 gap-10">
        {stats.map((s, i) => (
          <Reveal key={s.label} delay={i * 80}>
            <div className="text-center">
              <p className="text-4xl md:text-5xl lg:text-6xl font-bold tabular-nums gradient-text">
                {s.display ? s.display : <CountUp to={s.v} />}{s.suffix}
              </p>
              <p className="text-sm text-pb-dim mt-1">{s.label}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

// ─── Showcase with tabs ──────────────────────────────────────────────────
function Showcase() {
  const tabs = [
    {
      id: 'leaderboard',
      label: 'Leaderboards',
      headline: 'The ladder, for every category.',
      body: 'Every batting, bowling and fielding leaderboard, by season, grade and competition.',
      features: ['Every category, every grade', 'Competition and match type filters', 'Rank badges on every player'],
      src: SCREENSHOT_PATHS.shortCompetition,
      mock: <MockLeaderboard />,
    },
    {
      id: 'profile',
      label: 'Profiles',
      headline: 'A whole career on one page.',
      body: 'Career and season figures, charts, milestones and honours, back to a player’s first game.',
      features: ['Career and season totals', 'Milestones and honours', 'A shareable stat card'],
      src: SCREENSHOT_PATHS.landingHeroCard,
      mock: <MockHeritageCard />,
    },
    {
      id: 'records',
      label: 'Records',
      headline: 'The record books, always current.',
      body: 'All-time and season bests across the club, flagged the week they are set.',
      features: ['Batting, bowling and partnerships', 'A record at every wicket', 'New records flagged'],
      src: SCREENSHOT_PATHS.featuresHonours,
      mock: <MockPlayerProfile />,
    },
    {
      id: 'scorecard',
      label: 'Scorecards',
      headline: 'Every scorecard, kept for good.',
      body: 'Both innings, every dismissal and the result, going back as far as your history does.',
      features: ['Batting and bowling for both sides', 'Fall of wickets and partnerships', 'Linked from every profile'],
      src: SCREENSHOT_PATHS.showcaseScorecard,
      mock: <MockLeaderboard />,
    },
    {
      id: 'yearbook',
      label: 'Yearbooks',
      headline: 'A season annual that writes itself.',
      body: 'Pick a season and the yearbook fills in the record, the leaders and the awards.',
      features: ['Filled in from the season’s stats', 'Honours and top performers', 'A permanent link for every year'],
      src: SCREENSHOT_PATHS.showcaseYearbook,
      mock: <div className="max-w-md mx-auto"><MockYearbook /></div>,
    },
    {
      id: 'cards',
      label: 'Player Cards',
      headline: 'Every player is a card.',
      body: 'Rated 1 to 99 from career figures. Weekly packs, swaps and sets keep players coming back.',
      features: ['Packs for runs, wickets and wins', 'Special cards for centuries and five-fors', 'No paid packs'],
      src: '/marketing/player-cards-book.jpg',
      mock: <MockPlayerProfile />,
    },
  ]
  const [tab, setTab] = useState(tabs[0].id)
  const current = tabs.find(t => t.id === tab)

  return (
    <section id="showcase" className="px-4 sm:px-6 lg:px-10 py-16">
      <div className="max-w-[1280px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">BetterStats · in every plan</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Your whole history. <span className="gradient-text">One tap away.</span>
            </h2>
          </div>
        </Reveal>

        <div className="flex justify-center mb-10 overflow-x-auto pb-1">
          <div className="tabbar flex-shrink-0">
            {tabs.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)} className={tab === t.id ? 'active' : ''}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start" key={tab}>
          <Reveal className="col-span-1 lg:col-span-5">
            <div className="lg:sticky lg:top-24">
              <h3 className="text-3xl lg:text-4xl font-bold leading-tight mb-4">{current.headline}</h3>
              <p className="text-pb-dim leading-relaxed mb-6">{current.body}</p>
              <ul className="space-y-2.5 mb-7">
                {current.features.map((f) => (
                  <li key={f} className="flex items-center gap-3 text-sm"><span className="tick">✓</span>{f}</li>
                ))}
              </ul>
              <Link to="/contact" className="cta-primary">Try on your club →</Link>
            </div>
          </Reveal>
          <Reveal className="col-span-1 lg:col-span-7">
            <div className="product-shadow rounded-2xl">
              <ScreenshotOrMock src={current.src} alt={current.label} fallback={current.mock} />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

// ─── Modules teaser ──────────────────────────────────────────────────────
function ModulesTeaser() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">The Better platform</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Then run the <span className="gradient-text">whole club.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Add selection, socials, admin and analytics when you are ready, all on the same player list.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {MODULES_MARKETING.map((m, i) => (
            <Reveal key={m.slug} delay={(i % 3) * 70} className="h-full">
              <Link to={`/modules/${m.slug}`} className="surface overflow-hidden h-full flex flex-col hover:border-accent/30 transition-colors group block">
                <div className="border-b pb-hairline overflow-hidden aspect-[16/9] bg-black/20">
                  <img src={m.screenshot} alt={`${m.name} screenshot`} loading="lazy" className="w-full h-full object-cover object-top group-hover:scale-[1.02] transition-transform duration-500" />
                </div>
                <div className="p-5 flex flex-col flex-1">
                  <div className="flex items-center gap-2.5 mb-2">
                    <img src={m.logo} alt="" className="w-7 h-7 rounded-lg" />
                    <h3 className="text-lg font-semibold"><ModuleWordmark name={m.name} accent={m.accent} /></h3>
                  </div>
                  <p className="text-sm text-pb-dim leading-relaxed mb-4 flex-1">{m.tagline}</p>
                  <span className="text-sm font-medium inline-flex items-center gap-1" style={{ color: m.accent }}>Explore <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
        <div className="text-center mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/overview" className="cta-secondary">See everything BetterCricket does →</Link>
          <Link to="/pricing" className="text-sm text-accent hover:underline">See modular pricing →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Testimonials ────────────────────────────────────────────────────────
function Testimonials() {
  const t = TESTIMONIALS[0]
  if (!t) return null
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1000px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">From the clubs</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl tracking-tight leading-[1.05]">What clubs are saying.</h2>
          </div>
        </Reveal>

        <Reveal>
          <figure className="surface p-8 lg:p-12">
            <div className="flex gap-1 mb-5 text-accent text-lg">★★★★★</div>
            <blockquote className="text-2xl md:text-3xl font-semibold leading-snug mb-7">&ldquo;{t.quote}&rdquo;</blockquote>
            <figcaption className="flex items-center gap-4 pt-6 border-t pb-hairline">
              <div className="w-12 h-12 rounded-full bg-white/95 border border-accent/30 flex items-center justify-center overflow-hidden">
                <img
                  src="/marketing/applecross-cc.webp"
                  alt="Applecross Cricket Club"
                  className="w-9 h-9 object-contain"
                  loading="lazy"
                />
              </div>
              <div>
                <p className="font-semibold">{t.name}</p>
                <p className="text-sm text-pb-dim">{t.role}{t.yrs ? ` · ${t.yrs}` : ''}</p>
              </div>
            </figcaption>
          </figure>
        </Reveal>
      </div>
    </section>
  )
}

// ─── How it works ────────────────────────────────────────────────────────
function HowItWorks() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">How it works</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Live in under an hour. <span className="gradient-text">No data entry.</span>
            </h2>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 relative">
          <div className="hidden md:block absolute top-12 left-[12%] right-[12%] h-px bg-gradient-to-r from-transparent via-accent/30 to-transparent" />
          {HOW_IT_WORKS.map((s, i) => (
            <Reveal key={s.n} delay={i * 120}>
              <div className="relative surface p-7 h-full">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/40 flex items-center justify-center text-accent font-bold">{s.n}</div>
                  <span className="text-xs font-mono text-pb-faint">{s.mins}</span>
                </div>
                <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
                <p className="text-sm text-pb-dim leading-relaxed">{s.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Final CTA ───────────────────────────────────────────────────────────
function FinalCTA({ onCta }) {
  return (
    <section id="cta" className="px-4 sm:px-6 lg:px-10 py-24 relative overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative">
        <div className="surface-strong p-10 lg:p-14 text-center relative overflow-hidden">
          <div className="absolute inset-0 dot-grid opacity-30 pointer-events-none" />
          <div className="relative">
            <p className="pill mb-6 mx-auto"><span className="dot" />Limited onboarding spots</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-5 tracking-tight leading-[1.05]">
              Your club's history is <br className="hidden md:block" /><span className="gradient-text">waiting to be told.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">
              Tell us about your club. We'll get your site live fast, with your history already loaded.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-5">
              <button type="button" onClick={onCta} className="cta-primary">Request club access →</button>
              <Link to="/pricing" className="cta-secondary">See pricing</Link>
            </div>
            <p className="text-xs text-pb-faint mb-4">From $399/yr · One Core, your modules · Flat rate per club</p>
            <p className="text-sm text-pb-dim">
              Not ready yet? <WatchDemoLink placement="final_cta">Watch the full demo first</WatchDemoLink>
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Landing() {
  usePageMeta({
    title: 'BetterCricket — The platform Australian cricket clubs run on',
    description: "The platform Australian cricket clubs run on: automated stats and a public club site (BetterStats core), plus BetterSelect, BetterSocials, BetterAdmin and BetterIQ analytics, all fed by your club's own match data and synced automatically, with no manual data entry.",
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/',
  })
  const { trigger: triggerTrial, modalOpen: trialModalOpen, setModalOpen: setTrialModalOpen, defaultTrialDays } = useSelfServeTrialGate()
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero onCta={triggerTrial} />
        <TrustedByStrip />
        <Showcase />
        <StatBanner />
        <ModulesTeaser />
        <DemoBand />
        <Comparison3Way />
        <Testimonials />
        <HowItWorks />
        <FinalCTA onCta={triggerTrial} />
      </div>
      <MarketingFooter />
      {trialModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setTrialModalOpen(false)}
        />
      )}
    </div>
  )
}
