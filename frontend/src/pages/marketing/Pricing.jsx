import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import PricingCalculator from '../../components/marketing/PricingCalculator'
import { FORM_URL } from '../../data/marketing'
import { TIER_INFO, TIER_ORDER, modulesInTier } from '../../data/modules-marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// JSON-LD — three tier offers (annual), kept for SEO.
const PRICING_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'Product',
  name: 'Better — Cricket Club Platform',
  description:
    'A modular platform for Australian cricket clubs. Core stats and a public club site (BetterStats) plus bolt-on modules for selection, socials, fees and analytics. Sold as Good / Better / Best tiers.',
  brand: { '@type': 'Brand', name: 'Better' },
  url: 'https://betterstats.cricket/pricing',
  image: 'https://betterstats.cricket/og-image.png',
  offers: TIER_ORDER.map((key) => {
    const t = TIER_INFO[key]
    return {
      '@type': 'Offer',
      name: `${t.label} — annual`,
      price: String(t.annual),
      priceCurrency: 'AUD',
      availability: 'https://schema.org/InStock',
      url: 'https://betterstats.cricket/pricing',
      priceSpecification: { '@type': 'UnitPriceSpecification', price: String(t.annual), priceCurrency: 'AUD', unitText: 'ANN' },
    }
  }),
}

const annualSaving = (t) => t.monthly * 12 - t.annual

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-12 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />Flat per club · 1 team or 50, same price</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-6">
          Good. Better. <span className="gradient-text">Best.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-2xl mx-auto leading-relaxed">
          Every club gets the Core. Add the modules that run your season and your club —
          one flat price, no per-player or per-team charges.
        </p>
      </div>
    </section>
  )
}

// ─── Tier cards ────────────────────────────────────────────────────────────
function TierCard({ tierKey, billing }) {
  const t = TIER_INFO[tierKey]
  const isAnnual = billing === 'annual'
  const recommended = tierKey === 'better'
  const modules = modulesInTier(tierKey)
  const includeLines = [
    tierKey === 'good' ? 'Everything in BetterStats (Core)' : 'BetterStats (Core)',
    ...modules.map((m) => m.name),
  ]
  return (
    <div className={`relative surface p-7 lg:p-8 flex flex-col h-full ${recommended ? 'border-accent/40 bg-gradient-to-b from-accent/[0.06] to-transparent' : ''}`}>
      {recommended && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-accent text-navy-950 rounded-full whitespace-nowrap">
          <span className="text-[10px] font-bold uppercase tracking-wide3">★ Most popular</span>
        </div>
      )}
      <p className="font-display font-bold text-2xl mb-1">{t.label}</p>
      <p className="text-sm text-pb-dim mb-5 min-h-[40px]">{t.tagline}</p>

      <div className="flex items-baseline gap-1.5 mb-1">
        <span className="text-4xl font-bold tabular-nums">${isAnnual ? t.annual : t.monthly}</span>
        <span className="text-sm text-pb-faint">/ {isAnnual ? 'year' : 'month'} AUD</span>
      </div>
      <p className="text-xs text-accent font-semibold mb-6 h-4">
        {isAnnual ? `Save $${annualSaving(t)} vs monthly` : `or $${t.annual}/year`}
      </p>

      <p className="text-[10px] uppercase tracking-wide3 font-mono text-pb-faint mb-3">What’s included</p>
      <ul className="space-y-2 mb-7 flex-1">
        {includeLines.map((line) => (
          <li key={line} className="flex items-center gap-2.5 text-sm"><span className="tick">✓</span>{line}</li>
        ))}
      </ul>

      <a
        href={FORM_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={`${recommended ? 'cta-primary' : 'cta-secondary'} w-full justify-center`}
      >
        Get {t.label} →
      </a>
    </div>
  )
}

function Tiers({ billing, setBilling }) {
  const isAnnual = billing === 'annual'
  return (
    <section className="px-4 sm:px-6 lg:px-10 pb-8">
      <div className="max-w-[1100px] mx-auto">
        <div className="flex justify-center mb-10">
          <div className="tabbar">
            <button className={billing === 'monthly' ? 'active' : ''} onClick={() => setBilling('monthly')}>Monthly</button>
            <button className={isAnnual ? 'active' : ''} onClick={() => setBilling('annual')}>
              Annual <span className="ml-1 text-[10px] font-bold opacity-80">2 MONTHS FREE</span>
            </button>
          </div>
        </div>
        <Reveal>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 items-stretch">
            {TIER_ORDER.map((key) => (
              <TierCard key={key} tierKey={key} billing={billing} />
            ))}
          </div>
        </Reveal>
        <p className="text-center text-xs text-pb-faint mt-6 max-w-2xl mx-auto">
          Annual is billed once and works out cheaper — it also rides out the April–September off-season.
          Want just one module on a lower tier? À-la-carte add-ons are available — <Link to="/contact" className="text-accent hover:underline">ask us</Link>.
        </p>
      </div>
    </section>
  )
}

// ─── Calculator ──────────────────────────────────────────────────────────
function Calculator({ billing }) {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-16 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-8">
            <p className="pill-neutral inline-flex mb-5">Plan calculator</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-3 tracking-tight">Not sure which tier?</h2>
            <p className="text-pb-dim max-w-xl mx-auto">Tick the modules you want — we’ll tell you the tier and the price.</p>
          </div>
        </Reveal>
        <Reveal><PricingCalculator billing={billing} /></Reveal>
      </div>
    </section>
  )
}

// ─── Value table (what the Core replaces) ──────────────────────────────────
function ValueTable() {
  const rows = [
    ['Branded public club site', 'Saves your committee', '~$1,200 in dev fees'],
    ['Nightly PlayHQ sync', 'Saves your statistician', '~3 hr/week'],
    ['Historical sync — as far back as your data goes', 'Saves the archive project', 'Hours of work, once'],
    ['Auto-built season yearbook', 'Saves your committee', '~2 weekends/yr'],
    ['Shareable stat cards', 'Saves your social manager', '~30 min/week'],
    ['Honour boards & awards', 'Saves the committee', 'A migraine'],
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">The Core, in context</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">What the entry tier replaces.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">Before you even add a module, the Good tier pays for itself.</p>
          </div>
        </Reveal>
        <div className="surface overflow-hidden">
          <div className="grid grid-cols-[1.5fr,1fr,1fr] gap-4 px-6 py-4 border-b pb-hairline bg-pb-surface2/20">
            <p className="text-xs font-medium text-pb-faint uppercase tracking-wide3">What you get</p>
            <p className="text-xs font-medium text-pb-faint uppercase tracking-wide3">Replaces</p>
            <p className="text-xs font-medium text-accent uppercase tracking-wide3 text-right">Annual saving</p>
          </div>
          {rows.map((r, i) => (
            <div key={r[0]} className={`grid grid-cols-[1.5fr,1fr,1fr] gap-4 px-6 py-4 items-center ${i < rows.length - 1 ? 'border-b pb-hairline' : ''}`}>
              <p className="text-sm font-medium">{r[0]}</p>
              <p className="text-sm text-pb-dim">{r[1]}</p>
              <p className="text-sm text-accent font-semibold text-right">{r[2]}</p>
            </div>
          ))}
          <div className="grid grid-cols-[1.5fr,1fr,1fr] gap-4 px-6 py-5 bg-accent/[0.05]">
            <p className="text-base font-bold">Good tier — the Core</p>
            <p className="text-base text-pb-dim">BetterStats Annual</p>
            <p className="text-base font-bold text-accent text-right">${TIER_INFO.good.annual} / year</p>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Pricing FAQ ─────────────────────────────────────────────────────────
function PricingFAQ() {
  const [open, setOpen] = useState(0)
  const faqs = [
    { q: 'What’s the difference between the tiers?', a: 'Good is the Core — BetterStats stats and your public club site. Better adds BetterSelect (availability + selection) and BetterSocials (branded social posts) to run your season. Best adds BetterFees (treasury) and BetterIQ (analytics + opposition scouting) to run the whole club.' },
    { q: 'Does the price change based on club size?', a: 'No. Every tier is a flat rate — one team or fifty teams, juniors and seniors, men’s and women’s, the fee is the same. No per-team, per-player or per-grade pricing.' },
    { q: 'Can I add a single module without moving up a tier?', a: 'Yes — any one module can be bolted onto a lower tier à-la-carte. We price add-ons so that two of them cost more than simply moving up a tier, so for most clubs the tier is the better deal. Get in touch and we’ll sort it.' },
    { q: 'Monthly or annual?', a: 'Either. Annual is billed once and works out to roughly two months free — and it carries you through the April–September off-season without a monthly bill landing on a club with no fixtures.' },
    { q: 'Can we change tiers later?', a: 'Yes. Move up or down at any time; entitlements flip the moment your plan changes.' },
    { q: 'Are there any setup or migration fees?', a: 'There’s no flat setup fee. We do a short consultation, look at how much historical data your club has and how much clean-up it’ll need, then work out a low-cost plan that fits.' },
    { q: 'Do you offer discounts for junior-only clubs?', a: 'Yes — junior-only clubs get a discount, but only if the senior club is already onboarded. Contact us for the discount code.' },
    { q: 'How do we pay?', a: 'Right now it’s bank transfer / PayID — most clubs don’t have a card and we don’t want to put financial pressure on volunteers. Card payments are on the roadmap.' },
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
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
  const [billing, setBilling] = useState('annual')
  usePageMeta({
    title: 'Pricing — Good / Better / Best tiers for cricket clubs | Better',
    description:
      'Simple, flat-rate pricing for Australian cricket clubs. Good $449/yr (Core stats + public site), Better $649/yr (+ selection & socials), Best $999/yr (+ fees & BetterIQ analytics). One price per club regardless of size, billed monthly or annually.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/pricing',
    jsonLd: PRICING_JSONLD,
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <Tiers billing={billing} setBilling={setBilling} />
        <Calculator billing={billing} />
        <ValueTable />
        <PricingFAQ />
      </div>
      <MarketingFooter />
    </div>
  )
}
