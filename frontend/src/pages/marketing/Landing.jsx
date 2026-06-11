import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import CountUp from '../../components/marketing/CountUp'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import DotGrid from '../../components/marketing/DotGrid'
import {
  MockHeritageCard,
  MockLeaderboard,
  MockPlayerProfile,
  MockYearbook,
} from '../../components/marketing/Mockups'
import {
  LANDING_FEATURES,
  TESTIMONIALS,
  HOW_IT_WORKS,
  SCREENSHOT_PATHS,
} from '../../data/marketing'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  // Drive the dot grid straight from the theme tokens so it always matches the
  // site CSS — subtle hairline dots that light up the brand accent near the cursor.
  const dots = useMemo(() => {
    const fallback = { base: '#262d3d', active: '#16c784' }
    if (typeof window === 'undefined') return fallback
    const cs = getComputedStyle(document.documentElement)
    return {
      base: cs.getPropertyValue('--pb-hairline2').trim() || fallback.base,
      active: cs.getPropertyValue('--pb-accent').trim() || fallback.active,
    }
  }, [])
  return (
    <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 z-0 pointer-events-none">
        <DotGrid
          dotSize={4}
          gap={26}
          proximity={120}
          shockRadius={220}
          shockStrength={4}
          baseColor={dots.base}
          activeColor={dots.active}
          className="!p-0"
        />
      </div>
      <div className="absolute inset-0 hero-glow pointer-events-none" />

      <div className="max-w-[1280px] mx-auto relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
        <div className="col-span-12 lg:col-span-6">
          <div className="pill mb-7 inline-flex">
            <span className="dot" />
            For Australian cricket clubs · Since 2026
          </div>
          <h1 className="font-display font-bold text-[52px] sm:text-[68px] lg:text-[88px] tracking-tight leading-[0.92] mb-7">
            We do cricket<span className="text-pb-dim">…</span><br />
            <span className="gradient-text">Better.</span>
          </h1>
          <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-8 max-w-xl">
            Better Cricket is the platform Australian cricket clubs run on. Start with automated stats and a public site worth showing off, then add selection, socials, club admin and analytics, all fed by your club's own match data and synced automatically, so you never enter it by hand.
          </p>

          <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-3 mb-4">
            <Link to="/contact" className="cta-primary">
              Get Your Club on BetterCricket today!
            </Link>
            <a href="#showcase" className="cta-secondary">See it in action</a>
          </div>

          <div className="mb-7">
            <Link to="/overview" className="text-sm text-accent font-medium hover:underline inline-flex items-center gap-1">
              See everything Better Cricket does →
            </Link>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-pb-faint">
            <span className="flex items-center gap-2"><span className="tick">✓</span>Live in under an hour</span>
            <span className="flex items-center gap-2"><span className="tick">✓</span>Simple onboarding</span>
          </div>
        </div>

        <Reveal className="col-span-12 lg:col-span-6">
          <div className="relative">
            <div className="absolute -inset-5 bg-accent/8 blur-[60px] rounded-full" />
            <div className="relative product-shadow rounded-2xl">
              <ScreenshotOrMock
                src={SCREENSHOT_PATHS.landingHeroCard}
                alt="A 22-season career profile on Better Cricket"
                fallback={<MockHeritageCard />}
              />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Logo strip ──────────────────────────────────────────────────────────
function Logos() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-12 border-y pb-hairline bg-black/20">
      <div className="max-w-[1200px] mx-auto flex flex-wrap items-center justify-center gap-x-6 gap-y-3">
        <p className="text-xs text-pb-faint uppercase tracking-wide3 font-medium">Trusted by clubs at</p>
        <Link
          to="/applecross"
          className="flex items-center gap-3 text-base font-semibold text-pb-text/80 hover:text-accent transition-colors"
        >
          <img
            src="/marketing/applecross-cc.webp"
            alt="Applecross Cricket Club"
            className="w-9 h-9 object-contain"
            loading="lazy"
          />
          Applecross Cricket Club
        </Link>
      </div>
    </section>
  )
}

// ─── Value props (three audiences) ───────────────────────────────────────
function ValueProps() {
  const cards = [
    {
      eyebrow: '01 · For the Committee',
      title: 'Replace your club site, honour board and history project in one weekend.',
      desc: 'A public, branded club website that updates itself. Stop wrangling WordPress. Stop nagging the captain for scorecards.',
      stat: 'Under 1 hour to set up',
    },
    {
      eyebrow: '02 · For the Statistician',
      title: 'Every ball, every wicket, every catch, as far back as your data goes.',
      desc: 'We bring in your full history, as far back as it goes, with career, season and all-time views. Filter, sort and export across 30+ stat columns.',
      stat: 'Decades of indexed cricket data',
    },
    {
      eyebrow: '03 · For the Players',
      title: 'A career page worth bragging about.',
      desc: 'Real profiles with form charts and milestone alerts, plus one-tap stat cards your players will actually repost.',
      stat: 'Per-player profile pages',
    },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">Why clubs sign up</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              One platform. <span className="gradient-text">Three audiences.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Built so the committee, the statistician and the players all open it every week.
            </p>
          </div>
        </Reveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 items-stretch">
          {cards.map((c, i) => (
            <Reveal key={c.eyebrow} delay={i * 100} className="h-full">
              <div className="surface p-7 h-full flex flex-col hover:border-accent/30 transition-colors group">
                <p className="text-xs font-mono uppercase tracking-wide3 text-accent mb-5">{c.eyebrow}</p>
                <h3 className="text-2xl font-bold leading-tight mb-3 group-hover:text-accent transition-colors">{c.title}</h3>
                <p className="text-sm text-pb-dim leading-relaxed mb-6">{c.desc}</p>
                <div className="mt-auto pt-5 border-t pb-hairline flex items-center justify-between">
                  <span className="text-xs font-medium text-accent">{c.stat}</span>
                  <span className="text-accent opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
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
      headline: 'Every stat your club has ever produced.',
      body: 'Career, season and all-time leaderboards. 30+ sortable columns. Filter by grade, format, opponent, decade.',
      features: ['30+ sortable columns', 'Career + season views', 'Side-by-side compare', 'CSV + print export'],
      src: SCREENSHOT_PATHS.showcaseLeaderboard,
      mock: <MockLeaderboard />,
    },
    {
      id: 'profile',
      label: 'Profiles',
      headline: 'A full career, on one page.',
      body: 'Timeline charts. Batting curves. Partnership records. Milestone tracking. Per-format breakdowns.',
      features: ['Career timeline charts', 'Partnership records', 'Milestone tracking', 'Head-to-head splits'],
      src: SCREENSHOT_PATHS.showcaseProfile,
      mock: <MockPlayerProfile />,
    },
    {
      id: 'yearbook',
      label: 'Yearbook',
      headline: 'The annual that writes itself.',
      body: 'A shareable publication, auto-populated each season with honours, top performers and biggest moments. Permanent URL.',
      features: ['Auto-populated each season', 'Honours & awards', 'Print-ready PDF', 'Permanent URL per year'],
      src: SCREENSHOT_PATHS.showcaseYearbook,
      mock: <div className="max-w-md mx-auto"><MockYearbook /></div>,
    },
    {
      id: 'scorecard',
      label: 'Scorecards',
      headline: 'Every ball. Every wicket. Going back decades.',
      body: 'Full scorecards for every match: batting lineups, dismissals, fall of wickets and partnerships. Linked from player profiles and yearbooks.',
      features: ['Batting & bowling per match', 'Fall of wickets by innings', 'Partnership records per game', 'Linked from player profiles'],
      src: SCREENSHOT_PATHS.showcaseScorecard,
      mock: <MockLeaderboard />,
    },
    {
      id: 'analysis',
      label: 'Analysis',
      headline: 'Deeper stats for the curious.',
      body: 'Dismissal breakdowns, runs by grade, bowling analysis by wicket position, opposition stats, and StatLab, a custom query builder for any question your statistician can dream up.',
      features: ['Dismissal type breakdown charts', 'Runs & wickets by grade', 'Opposition analysis per player', 'StatLab custom query builder'],
      src: SCREENSHOT_PATHS.showcaseAnalysis,
      mock: <MockLeaderboard />,
    },
  ]
  const [tab, setTab] = useState(tabs[0].id)
  const current = tabs.find(t => t.id === tab)

  return (
    <section id="showcase" className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1280px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">The product</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Everything your club needs.<br />
              <span className="gradient-text">Nothing it doesn't.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Automated for your convenience.
            </p>
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
          <Reveal className="col-span-12 lg:col-span-5">
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
          <Reveal className="col-span-12 lg:col-span-7">
            <div className="product-shadow rounded-2xl">
              <ScreenshotOrMock src={current.src} alt={current.label} fallback={current.mock} />
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

// ─── Feature grid (6 high-impact cards) ──────────────────────────────────
function Features() {
  return (
    <section id="features" className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">In every plan</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Every club starts with <span className="gradient-text">BetterStats.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              BetterStats: your reconciled history and a public site to be proud of. Included in every plan.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {LANDING_FEATURES.map((f, i) => (
            <Reveal key={f.n} delay={(i % 3) * 80}>
              <div className="surface p-6 h-full hover:border-accent/30 transition-colors group">
                <div className="icon-tile mb-5">{f.n}</div>
                <h3 className="text-lg font-semibold mb-2 group-hover:text-accent transition-colors">{f.title}</h3>
                <p className="text-sm text-pb-dim leading-relaxed mb-4">{f.desc}</p>
                <p className="text-xs font-medium text-accent">{f.stat}</p>
              </div>
            </Reveal>
          ))}
        </div>
        <div className="text-center mt-10">
          <Link to="/features" className="cta-secondary">See all features →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Modules teaser ──────────────────────────────────────────────────────
function ModulesTeaser() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">The Better platform</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Then add the parts that <span className="gradient-text">run your club.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Four modules bolt straight onto BetterStats: selection, socials, club admin and analytics. Turn on what you need.
            </p>
          </div>
        </Reveal>
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
        <div className="text-center mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/overview" className="cta-secondary">See everything Better Cricket does →</Link>
          <Link to="/modules" className="text-sm text-accent hover:underline">Tour all modules →</Link>
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

// ─── Promise (player-first + Aussie-only) ────────────────────────────────
function Promise_() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1100px] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-stretch">
          <Reveal className="col-span-12 md:col-span-7">
            <div className="surface p-8 lg:p-10 h-full border-accent/30 bg-gradient-to-b from-accent/[0.05] to-transparent">
              <div className="flex items-center gap-3 mb-5">
                <div className="icon-tile">★</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-accent">Our commitment</p>
              </div>
              <h2 className="text-3xl lg:text-4xl font-bold leading-tight mb-4 tracking-tight">
                Player-first. <span className="gradient-text">Built by cricketers.</span>
              </h2>
              <p className="text-pb-dim leading-relaxed mb-5">
                Better Cricket is built by people who play. We listen to the captains, the committee members, the statisticians and the kids who just want to see their own century on a profile page.
              </p>
              <p className="text-pb-text font-medium mb-5">
                If something is missing, tell us. If it's important to you, it's important to us.
              </p>
              <Link to="/contact" className="inline-flex items-center gap-2 text-accent text-sm font-medium hover:underline">
                Send us a feature request →
              </Link>
            </div>
          </Reveal>

          <Reveal delay={120} className="col-span-12 md:col-span-5">
            <div className="surface p-8 h-full">
              <div className="flex items-center gap-3 mb-5">
                <div className="icon-tile">🇦🇺</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-pb-faint">Where we're at</p>
              </div>
              <h3 className="text-xl font-bold mb-3 tracking-tight">
                Australian clubs, for now.
              </h3>
              <p className="text-sm text-pb-dim leading-relaxed mb-4">
                Better Cricket currently supports Australian cricket clubs. We're already looking at new regions and want to bring the same platform to leagues elsewhere soon.
              </p>
              <p className="text-sm text-pb-dim leading-relaxed">
                Outside Australia and want this for your league? <Link to="/contact" className="text-accent hover:underline">Let us know</Link>. It helps us prioritise where to head next.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}

// ─── Final CTA ───────────────────────────────────────────────────────────
function FinalCTA() {
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
              <Link to="/contact" className="cta-primary">Request club access →</Link>
              <Link to="/pricing" className="cta-secondary">See pricing</Link>
            </div>
            <p className="text-xs text-pb-faint">From $399/yr · One Core, your modules · Flat rate per club</p>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Landing() {
  usePageMeta({
    title: 'Better Cricket — The platform Australian cricket clubs run on',
    description: "The platform Australian cricket clubs run on: automated stats and a public club site (BetterStats core), plus BetterSelect, BetterSocials, BetterAdmin and BetterIQ analytics, all fed by your club's own match data and synced automatically, with no manual data entry.",
    image: 'https://betterat.cricket/og-image.png',
    url: 'https://betterat.cricket/',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Logos />
        <ValueProps />
        <StatBanner />
        <Showcase />
        <Features />
        <ModulesTeaser />
        <Comparison3Way />
        <Testimonials />
        <HowItWorks />
        <Promise_ />
        <FinalCTA />
      </div>
      <MarketingFooter />
    </div>
  )
}
