import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import {
  HOW_IT_WORKS,
  TESTIMONIALS,
  FORM_URL,
  COMPARISON_SOLO,
} from '../../data/marketing'
import {
  CORE_MARKETING,
  MODULES_MARKETING,
  TIER_INFO,
  TIER_ORDER,
  modulesInTier,
} from '../../data/modules-marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// What every club runs today vs what Better Cricket replaces.
const PROBLEMS = [
  {
    problem: 'Your history lives in spreadsheets only one volunteer understands — and dies the day they step away.',
    solution: 'Your full club history, online and automatic. Every player, every season, kept forever and updated after each match.',
  },
  {
    problem: 'A separate website builder that nobody updates, with stats that are always out of date.',
    solution: 'A public, club-branded site wired straight to your match data — profiles, leaderboards, records and yearbooks that keep themselves current.',
  },
  {
    problem: 'Selection by group chat. Fees in a spreadsheet. Posts made by hand in Canva. Email in a separate tool.',
    solution: 'One platform for availability and selection, match-day graphics, fees, membership and member comms — all on the same player list.',
  },
  {
    problem: 'No idea who the dangerous opposition batter is until they’ve put you to the sword.',
    solution: 'An opposition scout and a selection brain built from your own scorecards — the match prep most pro teams pay for.',
  },
]

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative z-10 text-center">
        <div className="pill mb-7 inline-flex">
          <span className="dot" />
          The one-page tour · Better Cricket
        </div>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-7">
          Everything your club runs on.<br />
          <span className="gradient-text">In one place.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim leading-relaxed mb-9 max-w-2xl mx-auto">
          Better Cricket turns your match history into a public club site worth showing off — then adds team selection, match-day socials, club admin and broadcast-grade analytics. One platform, one login, fed by one match feed. No spreadsheets, no data entry.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-7">
          <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Request club access →</a>
          <Link to="/pricing" className="cta-secondary">See pricing</Link>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-pb-faint">
          <span className="flex items-center gap-2"><span className="tick">✓</span>Live in under an hour</span>
          <span className="flex items-center gap-2"><span className="tick">✓</span>Flat price per club</span>
          <span className="flex items-center gap-2"><span className="tick">✓</span>Built by cricketers</span>
        </div>
      </div>
    </section>
  )
}

// ─── Problem → Solution ──────────────────────────────────────────────────
function ProblemSolution() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">The problem</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Running a club is <span className="gradient-text">five jobs and five tools.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Most clubs stitch together a spreadsheet, a website builder, a design app, an email tool and a few group chats. Better Cricket is all of it — and it actually talks to itself.
            </p>
          </div>
        </Reveal>
        <div className="space-y-4">
          {PROBLEMS.map((p, i) => (
            <Reveal key={i} delay={(i % 2) * 80}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-px rounded-xl overflow-hidden border pb-hairline">
                <div className="bg-pb-surface2/40 p-6 flex gap-4">
                  <span className="text-pb-faintest font-bold text-lg flex-shrink-0">✗</span>
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1.5">The old way</p>
                    <p className="text-sm text-pb-dim leading-relaxed">{p.problem}</p>
                  </div>
                </div>
                <div className="bg-accent/[0.05] p-6 flex gap-4">
                  <span className="text-accent font-bold text-lg flex-shrink-0">✓</span>
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1.5">With Better Cricket</p>
                    <p className="text-sm text-pb-text leading-relaxed">{p.solution}</p>
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── The stack: Core + modules ───────────────────────────────────────────
function TheStack() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">The whole platform</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              The Core, plus the parts that <span className="gradient-text">run your club.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              Every club starts with the Core. Add the modules that fit how your club actually runs — they all bolt onto the same data.
            </p>
          </div>
        </Reveal>

        {/* Core */}
        <Reveal>
          <Link
            to={CORE_MARKETING.to}
            className="surface p-8 lg:p-10 mb-5 block hover:border-accent/40 transition-colors group border-accent/30 bg-gradient-to-b from-accent/[0.05] to-transparent"
          >
            <div className="grid grid-cols-12 gap-6 items-center">
              <div className="col-span-12 md:col-span-7">
                <div className="flex items-center gap-3 mb-4">
                  <span className="w-11 h-11 rounded-xl flex items-center justify-center text-xl text-navy-950" style={{ background: CORE_MARKETING.accent }}>{CORE_MARKETING.icon}</span>
                  <div>
                    <p className="text-xl font-bold group-hover:text-accent transition-colors">BetterStats</p>
                    <p className="text-[11px] font-mono uppercase tracking-wide3 text-accent">The Core · every club</p>
                  </div>
                </div>
                <p className="text-pb-dim leading-relaxed mb-2">
                  Your club’s full reconciled history and a public site to be proud of — automated stats, player profiles, leaderboards, club records, partnerships, match scorecards, season yearbooks, awards & honours, StatLab and shareable stat cards.
                </p>
              </div>
              <div className="col-span-12 md:col-span-5">
                <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-2">
                  {['Player profiles', 'Leaderboards', 'Club records', 'Season yearbooks', 'Match scorecards', 'Share cards'].map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-pb-dim"><span className="tick">✓</span>{f}</li>
                  ))}
                </ul>
                <span className="mt-5 inline-flex items-center gap-1 text-sm text-accent font-medium">Tour the Core <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
              </div>
            </div>
          </Link>
        </Reveal>

        {/* Modules */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {MODULES_MARKETING.map((m, i) => (
            <Reveal key={m.slug} delay={(i % 2) * 90} className="h-full">
              <Link to={`/modules/${m.slug}`} className="surface p-7 h-full flex flex-col hover:border-accent/30 transition-colors group block">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <span className="w-11 h-11 rounded-xl flex items-center justify-center text-lg text-navy-950" style={{ background: m.accent }}>{m.icon}</span>
                    <div>
                      <p className="text-lg font-bold group-hover:text-accent transition-colors">{m.name}</p>
                      <p className="text-[11px] text-pb-faint">{m.audience}</p>
                    </div>
                  </div>
                  <span className="pill-neutral text-[10px]">{TIER_INFO[m.tier].label}</span>
                </div>
                <p className="text-sm text-pb-dim leading-relaxed mb-4">{m.summary}</p>
                {m.members && (
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {m.members.map((sub) => (
                      <span key={sub} className="text-[10px] font-mono px-2 py-0.5 rounded border pb-hairline text-pb-dim">{sub}</span>
                    ))}
                  </div>
                )}
                <ul className="space-y-1.5 mb-5 mt-auto">
                  {m.highlights.slice(0, 4).map((h) => (
                    <li key={h} className="flex items-center gap-2 text-sm text-pb-dim"><span className="tick">✓</span>{h}</li>
                  ))}
                </ul>
                <span className="inline-flex items-center gap-1 text-sm text-accent font-medium">Explore {m.name} <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
              </Link>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── BetterIQ: category of one ───────────────────────────────────────────
function CategoryOfOne() {
  const solo = COMPARISON_SOLO.betteriq
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1000px] mx-auto">
        <Reveal>
          <div className="surface-strong p-8 lg:p-12 relative overflow-hidden">
            <div className="absolute inset-0 dot-grid opacity-20 pointer-events-none" />
            <div className="relative">
              <p className="pill-neutral inline-flex mb-5">{solo.eyebrow}</p>
              <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight leading-[1.05]">
                {solo.heading}
              </h2>
              <p className="text-lg text-pb-dim max-w-2xl mb-8">{solo.sub}</p>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 mb-8">
                {solo.points.map((p) => (
                  <li key={p} className="flex items-start gap-3 text-sm text-pb-dim leading-relaxed"><span className="tick mt-0.5">✓</span>{p}</li>
                ))}
              </ul>
              <p className="text-xs text-pb-faint mb-7 max-w-2xl">{solo.note}</p>
              <Link to={solo.cta.to} className="cta-primary">{solo.cta.label}</Link>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── How it works ────────────────────────────────────────────────────────
function HowItWorks() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24">
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
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <p className="pill-neutral inline-flex mb-5">Pricing</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              Good. Better. <span className="gradient-text">Best.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              One flat price per club — the same fee for one team or fifty. No per-player or per-team charges.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {TIER_ORDER.map((tierKey, i) => {
            const tier = TIER_INFO[tierKey]
            const mods = modulesInTier(tierKey)
            const featured = tierKey === 'better'
            return (
              <Reveal key={tierKey} delay={i * 90} className="h-full">
                <div className={`surface p-7 h-full flex flex-col ${featured ? 'border-accent/40 bg-gradient-to-b from-accent/[0.05] to-transparent' : ''}`}>
                  {featured && <p className="pill inline-flex mb-4 self-start"><span className="dot" />Most popular</p>}
                  <p className="text-sm font-mono uppercase tracking-wide3 text-accent mb-2">{tier.label}</p>
                  <p className="text-4xl font-bold tabular-nums mb-1">${tier.annual}<span className="text-base text-pb-faint font-normal">/yr</span></p>
                  <p className="text-xs text-pb-faint mb-4">or ${tier.monthly}/mo · 2 months free annually</p>
                  <p className="text-sm text-pb-dim leading-relaxed mb-5">{tier.tagline}</p>
                  <ul className="space-y-2 mb-6 mt-auto">
                    <li className="flex items-center gap-2 text-sm text-pb-dim"><span className="tick">✓</span>Everything in BetterStats (Core)</li>
                    {mods.map((m) => (
                      <li key={m.slug} className="flex items-center gap-2 text-sm text-pb-dim"><span className="tick">✓</span>{m.name}</li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            )
          })}
        </div>
        <div className="text-center mt-10">
          <Link to="/pricing" className="cta-secondary">See full pricing →</Link>
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
              Run your whole club from <span className="gradient-text">one place.</span>
            </h2>
            <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">
              Tell us about your club and we’ll get your site live, fast — with your history already loaded.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-5">
              <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Request club access →</a>
              <Link to="/contact" className="cta-secondary">Talk to us</Link>
            </div>
            <p className="text-xs text-pb-faint">From $449/yr · Good · Better · Best · Flat rate per club</p>
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
        <ProblemSolution />
        <TheStack />
        <Comparison3Way which="platform" showCTA={false} />
        <CategoryOfOne />
        <HowItWorks />
        <PricingSnapshot />
        <Testimonial />
        <FinalCTA />
      </div>
      <MarketingFooter />
    </div>
  )
}
