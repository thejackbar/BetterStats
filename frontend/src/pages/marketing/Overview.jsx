import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import {
  MockHeritageCard,
  MockLeaderboard,
  MockPlayerProfile,
  MockYearbook,
} from '../../components/marketing/Mockups'
import {
  HOW_IT_WORKS,
  TESTIMONIALS,
  FORM_URL,
  COMPARISON_SOLO,
  SCREENSHOT_PATHS,
} from '../../data/marketing'
import {
  CORE_MARKETING,
  MODULES_MARKETING,
  TIER_INFO,
} from '../../data/modules-marketing'
import { CORE, PRICED_MODULES } from '../../data/pricing'
import { usePageMeta } from '../../hooks/usePageMeta'

// Old way vs Better Cricket — kept tight and scannable.
const PROBLEMS = [
  { old: 'History trapped in a spreadsheet only one volunteer understands.', fix: 'Your full history online — every player, every season, kept forever.' },
  { old: 'A DIY website nobody updates, with stats that are always stale.', fix: 'A club-branded site wired to your match data. Always current.' },
  { old: 'Selection by group chat. Posts by hand. Fees in a spreadsheet.', fix: 'Selection, socials, fees and comms — one platform, one player list.' },
  { old: 'No clue who the danger batter is until they’ve hurt you.', fix: 'An opposition scout built from your own scorecards.' },
]

// Simple branded fallback for the module rows (real screenshots exist; this
// only shows if an image 404s).
function Placeholder({ icon, accent, label }) {
  return (
    <div className="rounded-2xl border pb-hairline bg-pb-surface2/40 aspect-[16/10] flex flex-col items-center justify-center gap-3">
      <span className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl text-navy-950" style={{ background: accent }}>{icon}</span>
      <p className="text-sm text-pb-faint font-mono">{label}</p>
    </div>
  )
}

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow pointer-events-none" />
      <div className="max-w-[1280px] mx-auto relative z-10 grid grid-cols-12 gap-10 items-center">
        <div className="col-span-12 lg:col-span-6">
          <div className="pill mb-7 inline-flex"><span className="dot" />The one-page tour</div>
          <h1 className="font-display font-bold text-[44px] sm:text-[58px] lg:text-[76px] tracking-tight leading-[0.92] mb-6">
            Run your whole club.<br />
            <span className="gradient-text">From one place.</span>
          </h1>
          <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-7 max-w-xl">
            Stats. A public site. Selection. Socials. Admin. Analytics. <span className="text-pb-text">Better Cricket is all of it</span> — one login, fed by one match feed. No spreadsheets. No data entry.
          </p>
          <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-3 mb-6">
            <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Request club access →</a>
            <a href="#showcase" className="cta-secondary">See it in action</a>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-pb-faint">
            <span className="flex items-center gap-2"><span className="tick">✓</span>Live in under an hour</span>
            <span className="flex items-center gap-2"><span className="tick">✓</span>Flat price per club</span>
            <span className="flex items-center gap-2"><span className="tick">✓</span>Built by cricketers</span>
          </div>
        </div>
        <Reveal className="col-span-12 lg:col-span-6">
          <div className="relative">
            <div className="absolute -inset-5 bg-accent/8 blur-[60px] rounded-full" />
            <div className="relative product-shadow rounded-2xl">
              <ScreenshotOrMock
                src={SCREENSHOT_PATHS.landingHeroCard}
                alt="A full career profile on Better Cricket"
                fallback={<MockHeritageCard />}
              />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Visual showcase strip ───────────────────────────────────────────────
function Showcase() {
  const shots = [
    { src: SCREENSHOT_PATHS.showcaseLeaderboard, alt: 'Live leaderboards', label: 'Leaderboards', mock: <MockLeaderboard /> },
    { src: SCREENSHOT_PATHS.showcaseProfile, alt: 'Player profiles', label: 'Player profiles', mock: <MockPlayerProfile /> },
    { src: SCREENSHOT_PATHS.showcaseYearbook, alt: 'Season yearbook', label: 'Season yearbook', mock: <MockYearbook /> },
    { src: SCREENSHOT_PATHS.showcaseScorecard, alt: 'Full scorecards', label: 'Scorecards', mock: <MockLeaderboard /> },
  ]
  return (
    <section id="showcase" className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1280px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">What your members see</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              A club site they’ll <span className="gradient-text">actually open.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Every player, every record, every season — live, mobile, and branded as yours.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {shots.map((s, i) => (
            <Reveal key={s.label} delay={(i % 4) * 70}>
              <figure className="group">
                <div className="product-shadow rounded-2xl overflow-hidden">
                  <ScreenshotOrMock src={s.src} alt={s.alt} fallback={s.mock} />
                </div>
                <figcaption className="mt-3 text-center text-xs font-mono uppercase tracking-wide3 text-pb-faint group-hover:text-accent transition-colors">{s.label}</figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Problem → Solution ──────────────────────────────────────────────────
function ProblemSolution() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">The problem</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Five jobs. Five tools. <span className="gradient-text">One headache.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Most clubs stitch together a spreadsheet, a site builder, a design app, an email tool and a few group chats. We replaced the lot.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {PROBLEMS.map((p, i) => (
            <Reveal key={i} delay={(i % 2) * 80}>
              <div className="surface p-6 h-full">
                <p className="flex items-start gap-3 text-sm text-pb-dim leading-relaxed mb-4">
                  <span className="text-pb-faintest font-bold flex-shrink-0">✗</span>{p.old}
                </p>
                <p className="flex items-start gap-3 text-sm text-pb-text leading-relaxed pt-4 border-t pb-hairline">
                  <span className="text-accent font-bold flex-shrink-0">✓</span>{p.fix}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Core feature block ──────────────────────────────────────────────────
function Core() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 pt-8 pb-12">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">The whole platform</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Start with the Core. <span className="gradient-text">Add what you need.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Every club gets BetterStats. The modules bolt straight on — same data, one login.
            </p>
          </div>
        </Reveal>
        <Reveal>
          <div className="surface p-6 lg:p-8 border-accent/30 bg-gradient-to-b from-accent/[0.05] to-transparent">
            <div className="grid grid-cols-12 gap-8 items-center">
              <div className="col-span-12 lg:col-span-5">
                <div className="flex items-center gap-3 mb-4">
                  <img src={CORE_MARKETING.logo} alt="" className="w-11 h-11 rounded-xl" />
                  <div>
                    <p className="text-xl font-bold">BetterStats</p>
                    <p className="text-[11px] font-mono uppercase tracking-wide3 text-accent">The Core · every club</p>
                  </div>
                </div>
                <p className="text-pb-dim leading-relaxed mb-5">
                  Your club’s full reconciled history and a public site to be proud of — profiles, leaderboards, records, scorecards, yearbooks, awards and shareable stat cards. All automatic.
                </p>
                <Link to={CORE_MARKETING.to} className="inline-flex items-center gap-1 text-sm text-accent font-medium">Tour the Core →</Link>
              </div>
              <div className="col-span-12 lg:col-span-7">
                <div className="product-shadow rounded-2xl">
                  <ScreenshotOrMock src={SCREENSHOT_PATHS.featuresProfile || SCREENSHOT_PATHS.showcaseProfile} alt="BetterStats player profile" fallback={<MockPlayerProfile />} />
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Module rows (alternating, screenshot-led) ───────────────────────────
function ModuleRow({ m, flip }) {
  const isIQ = m.slug === 'betteriq'
  const solo = isIQ ? COMPARISON_SOLO.betteriq : null
  const bullets = isIQ ? solo.points.slice(0, 4) : (m.highlights || []).slice(0, 4)
  return (
    <Reveal>
      <div className="grid grid-cols-12 gap-8 lg:gap-12 items-center">
        <div className={`col-span-12 lg:col-span-6 ${flip ? 'lg:order-2' : ''}`}>
          <div className="product-shadow rounded-2xl">
            <ScreenshotOrMock src={m.screenshot} alt={`${m.name} — ${m.tagline}`} fallback={<Placeholder icon={m.icon} accent={m.accent} label={m.name} />} />
          </div>
        </div>
        <div className={`col-span-12 lg:col-span-6 ${flip ? 'lg:order-1' : ''}`}>
          <div className="flex items-center gap-2.5 mb-4">
            <img src={m.logo} alt="" className="w-10 h-10 rounded-xl" />
            <span className="text-xl font-bold">{m.name}</span>
            {isIQ
              ? <span className="pill inline-flex !text-[10px]"><span className="dot" />Category of one</span>
              : <span className="pill-neutral text-[10px]">{TIER_INFO[m.tier].label} tier</span>}
          </div>
          <h3 className="text-2xl lg:text-3xl font-bold leading-tight mb-3 tracking-tight">{m.tagline}</h3>
          <p className="text-pb-dim leading-relaxed mb-5">{isIQ ? solo.sub : m.summary}</p>
          <ul className="space-y-2 mb-6">
            {bullets.map((b) => (
              <li key={b} className="flex items-start gap-2.5 text-sm text-pb-dim"><span className="tick mt-0.5">✓</span>{b}</li>
            ))}
          </ul>
          <Link to={`/modules/${m.slug}`} className="inline-flex items-center gap-1 text-sm text-accent font-medium">Explore {m.name} →</Link>
        </div>
      </div>
    </Reveal>
  )
}

function ModuleRows() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-16">
      <div className="max-w-[1200px] mx-auto space-y-20 lg:space-y-28">
        {MODULES_MARKETING.map((m, i) => (
          <ModuleRow key={m.slug} m={m} flip={i % 2 === 1} />
        ))}
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

// ─── Pricing snapshot ────────────────────────────────────────────────────
function PricingSnapshot() {
  const items = [CORE, ...PRICED_MODULES]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">Pricing</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Pick what you <span className="gradient-text">pay for.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              One flat price per club, the same fee for one team or fifty. Start with the Core and add the
              modules you want, with up to 10% off when you bundle.
            </p>
          </div>
        </Reveal>
        <Reveal>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {items.map((m) => (
              <div key={m.key} className={`surface p-5 text-center ${m.key === 'core' ? 'border-accent/40' : ''}`}>
                <span
                  className="w-10 h-10 rounded-lg flex items-center justify-center text-lg mx-auto mb-3 border"
                  style={{ color: m.accent, borderColor: `${m.accent}55`, background: `${m.accent}14` }}
                >
                  {m.icon}
                </span>
                <p className="text-sm font-semibold">{m.name}</p>
                {m.key === 'core' && <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent">Core</p>}
                <p className="text-2xl font-bold tabular-nums mt-1">${m.price}<span className="text-xs text-pb-faint font-normal">/yr</span></p>
              </div>
            ))}
          </div>
        </Reveal>
        <div className="text-center mt-10">
          <Link to="/pricing" className="cta-secondary">Build your plan →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Testimonial ─────────────────────────────────────────────────────────
function Testimonial() {
  const t = TESTIMONIALS[0]
  if (!t) return null
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1000px] mx-auto">
        <Reveal>
          <figure className="surface p-8 lg:p-12">
            <div className="flex gap-1 mb-5 text-accent text-lg">★★★★★</div>
            <blockquote className="text-2xl md:text-3xl font-semibold leading-snug mb-7">&ldquo;{t.quote}&rdquo;</blockquote>
            <figcaption className="flex items-center gap-4 pt-6 border-t pb-hairline">
              <div className="w-12 h-12 rounded-full bg-white/95 border border-accent/30 flex items-center justify-center overflow-hidden">
                <img src="/marketing/applecross-cc.webp" alt="Applecross Cricket Club" className="w-9 h-9 object-contain" loading="lazy" />
              </div>
              <div>
                <p className="font-semibold">{t.name}</p>
                <p className="text-sm text-pb-dim">{t.role}</p>
              </div>
            </figcaption>
          </figure>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Final CTA ───────────────────────────────────────────────────────────
function FinalCTA() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 relative overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative">
        <div className="surface-strong p-10 lg:p-14 text-center relative overflow-hidden">
          <div className="absolute inset-0 dot-grid opacity-30 pointer-events-none" />
          <div className="relative">
            <p className="pill mb-6 mx-auto"><span className="dot" />Limited onboarding spots</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-5 tracking-tight leading-[1.05]">
              One platform. <span className="gradient-text">Your whole club.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">
              Tell us about your club and we’ll get your site live, fast — with your history already loaded.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-5">
              <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Request club access →</a>
              <Link to="/contact" className="cta-secondary">Talk to us</Link>
            </div>
            <p className="text-xs text-pb-faint">From $400/yr · One Core, your modules · Flat rate per club</p>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Overview() {
  usePageMeta({
    title: 'Overview — Everything Better Cricket does | The cricket club platform',
    description: 'A one-page tour of Better Cricket: automated stats and a public club site (BetterStats), plus BetterSelect, BetterSocials, BetterAdmin and BetterIQ. The whole platform Australian cricket clubs run on — no manual data entry.',
    image: 'https://betterat.cricket/og-image.png',
    url: 'https://betterat.cricket/overview',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Showcase />
        <ProblemSolution />
        <Core />
        <ModuleRows />
        <Comparison3Way which="platform" showCTA={false} />
        <HowItWorks />
        <PricingSnapshot />
        <Testimonial />
        <FinalCTA />
      </div>
      <MarketingFooter />
    </div>
  )
}
