import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ZoomableImage from '../../components/marketing/ZoomableImage'
import { CORE_MARKETING, MODULES_MARKETING, HUB_SHOWCASE } from '../../data/modules-marketing'
import { CORE, PRICED_MODULES, ALL_IN } from '../../data/pricing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'

function ModuleCard({ m, delay }) {
  const to = `/modules/${m.slug}`
  return (
    <Reveal delay={delay} className="h-full">
      <Link to={to} className="surface p-7 h-full flex flex-col transition-colors group block"
        style={{ '--card-accent': m.accent }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${m.accent}55` }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = '' }}>
        <div className="flex items-center mb-5">
          <img src={m.logo} alt="" className="w-11 h-11 rounded-xl" />
        </div>
        <h3 className="text-xl font-bold mb-2"><ModuleWordmark name={m.name} accent={m.accent} /></h3>
        <p className="text-sm text-pb-dim leading-relaxed mb-5">{m.tagline}</p>
        {m.highlights && (
          <ul className="space-y-1.5 mb-6">
            {m.highlights.slice(0, 3).map((h) => (
              <li key={h} className="flex items-start gap-2 text-xs text-pb-dim"><span className="mt-0.5" style={{ color: m.accent }}>✓</span>{h}</li>
            ))}
          </ul>
        )}
        <span className="mt-auto pt-4 border-t pb-hairline text-sm font-medium inline-flex items-center gap-1" style={{ color: m.accent }}>
          Explore {m.name} <span className="group-hover:translate-x-0.5 transition-transform">→</span>
        </span>
      </Link>
    </Reveal>
  )
}

function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />The Better platform</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[78px] tracking-tight leading-[0.95] mb-6">
          Built in modules. <span className="gradient-text">Pick what you run.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-2xl mx-auto leading-relaxed">
          Better Cricket is everything your cricket club runs on. Every club starts with BetterStats,
          then adds the parts that fit how the club actually runs.
        </p>
      </div>
    </section>
  )
}

function Showcase() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 pb-12">
      <div className="max-w-[1080px] mx-auto">
        <Reveal>
          <div className="relative">
            <div className="absolute -inset-6 bg-accent/8 blur-[70px] rounded-full pointer-events-none" />
            <div className="relative product-shadow rounded-2xl overflow-hidden border pb-hairline">
              <ZoomableImage
                src={HUB_SHOWCASE}
                alt="The Better admin dashboard, one tile per module"
                caption="The Better admin dashboard, one tile per module"
                className="block w-full h-auto"
              />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

function Grid() {
  const all = [CORE_MARKETING, ...MODULES_MARKETING]
  return (
    <section className="px-4 sm:px-6 lg:px-10 pb-8">
      <div className="max-w-[1200px] mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 items-stretch">
        {all.map((m, i) => (
          <ModuleCard key={m.slug} m={m} delay={(i % 3) * 80} />
        ))}
      </div>
    </section>
  )
}

function PricingStrip() {
  const moduleFrom = Math.min(...PRICED_MODULES.map((m) => m.price))
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20 mt-12">
      <div className="max-w-[1000px] mx-auto text-center">
        <Reveal>
          <p className="pill-neutral inline-flex mb-5">One Core, your modules</p>
          <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">Pick the modules you want.</h2>
          <p className="text-pb-dim max-w-xl mx-auto mb-10">
            Every club starts with BetterStats at ${CORE.price} a year, then adds the modules it wants from ${moduleFrom}. Bundle two or more and save, up to $146 off the full set (${ALL_IN} for the lot).
          </p>
        </Reveal>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-10">
          {[CORE, ...PRICED_MODULES].map((m) => (
            <div key={m.key} className={`surface p-5 ${m.key === 'core' ? 'border-accent/40' : ''}`}>
              <p className="font-display font-bold text-sm mb-1"><ModuleWordmark name={m.name} accent={m.accent} /></p>
              {m.key === 'core' && <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Core</p>}
              <p className="text-2xl font-bold tabular-nums mt-1">${m.price}<span className="text-xs text-pb-faint font-normal">/yr</span></p>
            </div>
          ))}
        </div>
        <Link to="/pricing" className="cta-primary">See full pricing & calculator →</Link>
      </div>
    </section>
  )
}

function CTA() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 relative overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative">
        <div className="surface-strong p-10 lg:p-14 text-center">
          <h2 className="font-display font-bold text-4xl md:text-5xl mb-5 tracking-tight">Start with BetterStats. <span className="gradient-text">Grow into the rest.</span></h2>
          <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">Tell us your club details and we’ll get your site live, then turn on modules whenever you’re ready.</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link to="/contact" className="cta-primary">Request club access →</Link>
            <Link to="/pricing" className="cta-secondary">See pricing</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function Modules() {
  usePageMeta({
    title: 'Modules — BetterSelect, BetterSocials, BetterAdmin & BetterIQ | Better Cricket',
    description:
      'Better Cricket in parts: the BetterStats Core plus four bolt-on modules, BetterSelect (selection), BetterSocials (website & social posts), BetterAdmin (fees, comms & merch) and BetterIQ (analytics & opposition scouting). Start with the BetterStats Core and add the modules you want.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/modules',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Showcase />
        <Grid />
        <PricingStrip />
        <CTA />
      </div>
      <MarketingFooter />
    </div>
  )
}
