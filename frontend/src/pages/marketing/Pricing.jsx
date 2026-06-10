import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import PricingCalculator from '../../components/marketing/PricingCalculator'
import { CORE, PRICED_MODULES, ALL_IN, COMPETITOR_STACK, COMPETITOR_TOTAL, SAVING, IMPORT_NOTE } from '../../data/pricing'
import { usePageMeta } from '../../hooks/usePageMeta'

// JSON-LD — the Core plus each module as an annual offer, kept for SEO.
const PRICING_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'Product',
  name: 'Better Cricket — Cricket Club Platform',
  description:
    'A modular platform for Australian cricket clubs. The Core (BetterStats) is $400 a year; add BetterSelect, BetterSocials and BetterAdmin for $100 each and BetterIQ for $200, with up to 15% off when you bundle. Annual licence, one price per club.',
  brand: { '@type': 'Brand', name: 'Better Cricket' },
  url: 'https://betterat.cricket/pricing',
  image: 'https://betterat.cricket/og-image.png',
  offers: {
    '@type': 'AggregateOffer',
    priceCurrency: 'AUD',
    lowPrice: String(CORE.price),
    highPrice: String(ALL_IN),
    offerCount: String(1 + PRICED_MODULES.length),
    offers: [CORE, ...PRICED_MODULES].map((m) => ({
      '@type': 'Offer',
      name: `${m.name} — annual`,
      price: String(m.price),
      priceCurrency: 'AUD',
      availability: 'https://schema.org/InStock',
      url: 'https://betterat.cricket/pricing',
    })),
  },
}

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-10 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />Flat per club · 1 team or 50, same price</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-6">
          Pick what you <span className="gradient-text">pay for.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-2xl mx-auto leading-relaxed">
          Every club starts with the Core. Add only the modules you want, with up to 15% off when you
          bundle. One annual price, no per-player or per-team charges.
        </p>
      </div>
    </section>
  )
}

// ─── Calculator (the main pricing tool) ────────────────────────────────────
function Calculator() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 pb-8">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-8">
            <p className="pill-neutral inline-flex mb-5">Plan calculator</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-3 tracking-tight">Build your plan, see the price.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">Tick the modules you want and the annual price updates as you go.</p>
          </div>
        </Reveal>
        <Reveal><PricingCalculator /></Reveal>
      </div>
    </section>
  )
}

// ─── Module price list ─────────────────────────────────────────────────────
function PriceList() {
  const items = [CORE, ...PRICED_MODULES]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-14 border-t pb-hairline">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-8">
            <p className="pill-neutral inline-flex mb-5">The building blocks</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-3 tracking-tight">One Core, then your modules.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">
              Annual prices, AUD. Add any two modules for 10% off, or all four for 15% (the full set comes to ${ALL_IN}).
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
                {m.key === 'core' && <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1">Core</p>}
                <p className="text-2xl font-bold tabular-nums mt-1">${m.price}</p>
                <p className="text-[11px] text-pb-faint">/ year</p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Competitor comparison (replace the whole stack) ───────────────────────
function ReplacesStack() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">One platform, one bill</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">One platform. One price.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">
              To cover the same ground with separate tools, a club pays for each of these and retypes its
              cricket into all of them. Better Cricket does the lot for one flat price.
            </p>
          </div>
        </Reveal>
        <Reveal>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
            {/* The usual stack of separate subscriptions */}
            <div className="surface p-6 lg:p-7 flex flex-col">
              <p className="text-[10px] uppercase tracking-wide3 font-mono text-pb-faint mb-4">The usual stack</p>
              <div className="flex-1">
                {COMPETITOR_STACK.map((c) => (
                  <div key={c.tool} className="flex items-start justify-between gap-4 py-3 border-b pb-hairline">
                    <div>
                      <p className="text-sm font-semibold">{c.tool}{c.plan ? <span className="text-pb-faint font-normal"> · {c.plan}</span> : null}</p>
                      <p className="text-xs text-pb-dim">{c.forJob}</p>
                    </div>
                    <p className="text-sm font-semibold tabular-nums whitespace-nowrap">${c.cost}<span className="text-[11px] text-pb-faint font-normal">/yr</span></p>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between mt-4 pt-4 border-t pb-hairline">
                <p className="text-sm font-bold">{COMPETITOR_STACK.length} separate subscriptions</p>
                <p className="text-2xl font-bold tabular-nums text-pb-dim">${COMPETITOR_TOTAL}<span className="text-xs text-pb-faint font-normal">/yr</span></p>
              </div>
              <p className="text-[11px] text-pb-faint mt-3">Plus ClubStats charges {IMPORT_NOTE} to load your history, a one-off fee Better Cricket doesn't.</p>
            </div>

            {/* Better Cricket — one price + the saving */}
            <div className="surface-strong p-6 lg:p-7 border-accent/40 bg-gradient-to-b from-accent/[0.07] to-transparent flex flex-col">
              <p className="text-[10px] uppercase tracking-wide3 font-mono text-accent mb-4">Better Cricket, all in</p>
              <div className="flex-1 flex flex-col justify-center text-center py-4">
                <div className="flex items-baseline justify-center gap-1.5">
                  <span className="text-6xl font-bold tabular-nums">${ALL_IN}</span>
                  <span className="text-sm text-pb-faint">/ year</span>
                </div>
                <p className="text-sm text-pb-dim mt-3 max-w-xs mx-auto">
                  The Core and all four modules, one login, fed by your own cricket data. Your full history loaded, with no import fee and no retyping.
                </p>
              </div>
              <div className="mt-4 rounded-xl bg-accent/10 border border-accent/30 px-5 py-4 text-center">
                <p className="text-[10px] uppercase tracking-wide3 font-mono text-accent mb-1">Switch and save</p>
                <p className="text-3xl font-bold tabular-nums text-accent">${SAVING}<span className="text-sm font-normal text-pb-dim"> / year</span></p>
              </div>
            </div>
          </div>
        </Reveal>
        <p className="text-center text-xs text-pb-faint mt-5 max-w-2xl mx-auto">
          Competitor prices are each tool's own published rate (AUD; Pitchero converted from GBP) on a
          representative plan, and scale with club size. CricketStatz, the desktop stats package, is another
          stats option at $199 to $798 a year. Better Cricket loads your full history for free, where ClubStats
          charges a one-off import fee. BetterIQ has no off-the-shelf equivalent.
        </p>
      </div>
    </section>
  )
}

// ─── Pricing FAQ ─────────────────────────────────────────────────────────
function PricingFAQ() {
  const [open, setOpen] = useState(0)
  const faqs = [
    { q: 'How much does it cost?', a: "The Core (BetterStats) is $400 a year and includes your public stats site. BetterSelect, BetterSocials and BetterAdmin are $100 a year each, and BetterIQ is $200. Take any two modules for 10% off, or all four for 15%, which brings the Core plus every module to $765 a year." },
    { q: 'Does the price change based on club size?', a: "No. Every price is a flat rate per club. One team or fifty teams, juniors and seniors, men's and women's, the price is the same. There's no per-team, per-player or per-grade pricing." },
    { q: 'Can I add a single module?', a: "Yes. For a small additional annual charge, any single module can be added to your current subscription." },
    { q: 'Monthly or annual?', a: "Better Cricket is an annual licence, billed once a year." },
    { q: 'Can we add modules later?', a: "Yes. You can add new modules at any time and the entitlements switch on immediately. Adding a module is an annual commitment." },
    { q: 'Are there any setup or migration fees?', a: "Up to two hours of dedicated support is included in your first year on the Core. If all of your club's match history is already uploaded, you should be up and running in no time, and we'll guide you through merging players and grades if needed." },
    { q: 'Do you offer a free trial?', a: "Yes. We offer a 14-day free trial of every Better Cricket module, so you can try the lot before you commit." },
    { q: 'Do you offer discounts for junior-only clubs?', a: "Yes. A junior club linked to a senior club that's currently subscribed to Better Cricket gets a discount. Contact us for the code." },
    { q: 'How do we pay?', a: "Right now it's bank transfer or PayID. Most clubs don't have a card and we don't want to put financial pressure on volunteers. Card payments are on the roadmap." },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[900px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">Pricing FAQ</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl tracking-tight">Questions on price.</h2>
          </div>
        </Reveal>
        <div className="space-y-2">
          {faqs.map((f, i) => (
            <div key={f.q} className="surface overflow-hidden">
              <button onClick={() => setOpen(open === i ? -1 : i)} className="w-full flex items-center justify-between gap-6 p-5 text-left">
                <span className="text-base md:text-lg font-semibold">{f.q}</span>
                <span className="w-8 h-8 rounded-full bg-pb-surface2 flex items-center justify-center text-accent text-lg flex-shrink-0">{open === i ? '−' : '+'}</span>
              </button>
              <div className={`overflow-hidden transition-all duration-500 ${open === i ? 'max-h-72' : 'max-h-0'}`}>
                <p className="px-5 pb-5 text-sm text-pb-dim leading-relaxed">{f.a}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="text-center mt-8">
          <Link to="/faq" className="text-sm text-accent hover:underline">See all FAQs →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Pricing() {
  usePageMeta({
    title: 'Pricing — modular plans for cricket clubs | Better Cricket',
    description:
      'Modular, flat-rate pricing for Australian cricket clubs. The Core (BetterStats) is $400 a year; add BetterSelect, BetterSocials and BetterAdmin for $100 each and BetterIQ for $200, with up to 15% off when you bundle. One annual price per club, whatever the size.',
    image: 'https://betterat.cricket/og-image.png',
    url: 'https://betterat.cricket/pricing',
    jsonLd: PRICING_JSONLD,
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Calculator />
        <PriceList />
        <ReplacesStack />
        <PricingFAQ />
      </div>
      <MarketingFooter />
    </div>
  )
}
