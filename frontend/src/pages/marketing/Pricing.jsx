import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import { FORM_URL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

// Existing JSON-LD — preserved for SEO
const PRICING_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'Product',
  name: 'BetterStats — Cricket Club Stats Platform',
  description: 'Automated club cricket statistics platform with player profiles, leaderboards, records, partnerships, season yearbooks, awards and shareable stat cards. PlayHQ and MyCricket sync included.',
  brand: { '@type': 'Brand', name: 'BetterStats' },
  url: 'https://betterstats.cricket/pricing',
  image: 'https://betterstats.cricket/og-image.png',
  offers: [
    { '@type': 'Offer', name: 'Monthly subscription', price: '49', priceCurrency: 'AUD', availability: 'https://schema.org/InStock', url: 'https://betterstats.cricket/pricing', priceSpecification: { '@type': 'UnitPriceSpecification', price: '49', priceCurrency: 'AUD', unitText: 'MONTH' } },
    { '@type': 'Offer', name: 'Annual subscription', price: '400', priceCurrency: 'AUD', availability: 'https://schema.org/InStock', url: 'https://betterstats.cricket/pricing', priceSpecification: { '@type': 'UnitPriceSpecification', price: '400', priceCurrency: 'AUD', unitText: 'ANN' } },
  ],
}

const PLAN_BENEFITS = [
  'Unlimited players and seasons',
  'Automatic data sync',
  'Full historical sync — as far back as your data goes',
  'Full public stats page',
  'Player profiles and leaderboards',
  'Season yearbook',
  'Awards and honours management',
  'Duplicate player merge tool',
  'Player comparison',
  'StatLab — 200+ pre-built reports',
  'Custom branding & crest',
  'Sponsor placement',
  'Admin logins for your stats volunteers',
  'CSV import and export',
  'Responsive support',
]

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />No hidden tiers · No per-seat fees</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-6">
          One price. <span className="gradient-text">Everything in.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-2xl mx-auto leading-relaxed">
          Less than the post-game round at the bar. All features, all clubs.
        </p>
      </div>
    </section>
  )
}

// ─── Pricing cards ───────────────────────────────────────────────────────
function PricingCards() {
  const [billing, setBilling] = useState('annual')
  const isAnnual = billing === 'annual'
  return (
    <section className="px-4 sm:px-6 lg:px-10 pb-20">
      <div className="max-w-[900px] mx-auto">
        {/* Toggle */}
        <div className="flex justify-center mb-10">
          <div className="tabbar">
            <button className={billing === 'monthly' ? 'active' : ''} onClick={() => setBilling('monthly')}>Monthly</button>
            <button className={isAnnual ? 'active' : ''} onClick={() => setBilling('annual')}>
              Annual <span className="ml-1 text-[10px] font-bold opacity-80">SAVE $188</span>
            </button>
          </div>
        </div>

        <Reveal>
          <div className={`relative surface p-8 lg:p-10 max-w-2xl mx-auto ${isAnnual ? 'border-accent/40 bg-gradient-to-b from-accent/[0.06] to-transparent' : ''}`}>
            {isAnnual && (
              <div className="absolute -top-3 left-8 px-3 py-1 bg-accent text-navy-950 rounded-full">
                <span className="text-[10px] font-bold uppercase tracking-wide3">★ Most clubs · save $188</span>
              </div>
            )}
            <p className={`text-sm font-semibold mb-3 ${isAnnual ? 'text-accent' : 'text-pb-dim'}`}>
              {isAnnual ? 'Recommended · Annual' : 'Try it out · Monthly'}
            </p>
            <div className="flex items-baseline gap-2 mb-2">
              <span className="text-5xl font-bold tabular-nums">{isAnnual ? '$400' : '$49'}</span>
              <span className="text-sm text-pb-faint">/ {isAnnual ? 'year' : 'month'} AUD</span>
            </div>
            <p className="text-sm text-pb-dim mb-7">
              {isAnnual
                ? 'Works out to $33 a month. Best value for clubs running a full season.'
                : 'For clubs trialling the platform. Cancel any time during a monthly term — your data is kept, the public page goes offline.'}
            </p>
            <p className="text-xs uppercase tracking-wide3 font-mono text-pb-faint mb-4">What's included</p>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2.5 mb-7">
              {PLAN_BENEFITS.map((b) => (
                <li key={b} className="flex items-center gap-3 text-sm"><span className="tick">✓</span>{b}</li>
              ))}
            </ul>
            <a
              href={FORM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={`${isAnnual ? 'cta-primary' : 'cta-secondary'} w-full justify-center`}
            >
              {isAnnual ? 'Get annual access →' : 'Start monthly'}
            </a>
            <p className="text-xs text-pb-faint mt-4 text-center">
              {isAnnual
                ? 'Onboarding is not bundled, but our support is responsive — we\'ll get you set up and help you navigate the platform.'
                : 'Cancel any time. Your data stays safe with us; only the public page comes down.'}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Value table ─────────────────────────────────────────────────────────
function ValueTable() {
  const rows = [
    ['Branded public club site', 'Saves your committee', '~$1,200 in dev fees'],
    ['Nightly PlayHQ sync', "Saves your statistician", '~3 hr/week'],
    ['Historical sync — as far back as your data goes', 'Saves the archive project', 'Hours of work, once'],
    ['Auto-built season yearbook', 'Saves your committee', '~2 weekends/yr'],
    ['Shareable stat cards', 'Saves your social manager', '~30 min/week'],
    ['Honour boards & awards', 'Saves the committee', 'A migraine'],
  ]
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
      <div className="max-w-[1100px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">$400 in context</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">What you stop paying for.</h2>
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
            <p className="text-base font-bold">Total annual cost</p>
            <p className="text-base text-pb-dim">BetterStats Annual</p>
            <p className="text-base font-bold text-accent text-right">$400 / year</p>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── DeepAnalytics teaser (preserved) ────────────────────────────────────
function DeepAnalytics() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20">
      <div className="max-w-[1100px] mx-auto">
        <div className="surface p-8 lg:p-10 border-pb-faint" style={{ borderStyle: 'dashed' }}>
          <div className="flex items-center justify-between gap-4 mb-6 flex-wrap">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">Coming soon</p>
              <h2 className="font-display font-bold text-2xl md:text-3xl tracking-tight">DeepAnalytics</h2>
            </div>
            <span className="pill-neutral">In development</span>
          </div>
          <p className="text-pb-dim mb-6 max-w-3xl">
            Cross-club intelligence for serious cricket. DeepAnalytics gives your club access to aggregated stats from across the competition — so you can make smarter selections, prepare better for opposition, and benchmark your players against the rest of the league.
          </p>
          <ul className="space-y-2.5 mb-6 grid grid-cols-1 md:grid-cols-2 gap-x-6">
            {[
              'Opposition analysis — batting and bowling tendencies by player',
              'Cross-club leaderboards and percentile rankings',
              'Selection insights — compare your squad against the competition',
              'Grade-wide averages and benchmarking',
            ].map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-sm text-pb-dim">
                <span className="mt-0.5 shrink-0 font-mono text-pb-faint">◦</span>
                {item}
              </li>
            ))}
          </ul>
          <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-secondary">Register interest</a>
        </div>
      </div>
    </section>
  )
}

// ─── Pricing FAQ ─────────────────────────────────────────────────────────
function PricingFAQ() {
  const [open, setOpen] = useState(0)
  const faqs = [
    { q: 'Are there any setup or migration fees?', a: "There's no flat setup fee. We do a short consultation, look at how much historical data your club has and how much clean-up it'll need, then work out a low-cost plan that fits." },
    { q: 'Can we change plans?', a: 'Yes. Move from monthly to annual any time. Switch back at the end of an annual term.' },
    { q: 'What if we cancel?', a: "On monthly, you can cancel any time — when you do, the public page comes down but your data isn't lost. The annual plan runs to the end of its term." },
    { q: 'Do you offer discounts for junior-only clubs?', a: 'Yes — junior-only clubs get a discount, but only if the senior club is already onboarded with BetterStats. Contact us for the discount code.' },
    { q: 'How do we pay?', a: "Right now it's bank transfer / PayID. Most clubs don't have a card and we don't want to put financial pressure on volunteers. Card payments are on the roadmap." },
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
              <div className={`overflow-hidden transition-all duration-500 ${open === i ? 'max-h-60' : 'max-h-0'}`}>
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
    title: 'Pricing — $49/mo or $400/yr per club | BetterStats',
    description: 'Simple, transparent cricket stats pricing for Australian clubs. $49 AUD per month or $400 AUD per year per club — unlimited players, full historical sync, season yearbooks, admin panel and responsive support included.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/pricing',
    jsonLd: PRICING_JSONLD,
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        <PricingCards />
        <DeepAnalytics />
        <ValueTable />
        <PricingFAQ />
      </div>
      <MarketingFooter />
    </div>
  )
}
