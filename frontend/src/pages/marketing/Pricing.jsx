import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'

const PRICING_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'Product',
  name: 'BetterStats — Cricket Club Stats Platform',
  description: 'Automated club cricket statistics platform with player profiles, leaderboards, records, partnerships, season yearbooks, awards and shareable stat cards. PlayHQ and MyCricket sync included.',
  brand: { '@type': 'Brand', name: 'BetterStats' },
  url: 'https://betterstats.cricket/pricing',
  image: 'https://betterstats.cricket/og-image.png',
  offers: [
    {
      '@type': 'Offer',
      name: 'Monthly subscription',
      price: '49',
      priceCurrency: 'AUD',
      availability: 'https://schema.org/InStock',
      url: 'https://betterstats.cricket/pricing',
      priceSpecification: {
        '@type': 'UnitPriceSpecification',
        price: '49',
        priceCurrency: 'AUD',
        unitText: 'MONTH',
      },
    },
    {
      '@type': 'Offer',
      name: 'Annual subscription',
      price: '400',
      priceCurrency: 'AUD',
      availability: 'https://schema.org/InStock',
      url: 'https://betterstats.cricket/pricing',
      priceSpecification: {
        '@type': 'UnitPriceSpecification',
        price: '400',
        priceCurrency: 'AUD',
        unitText: 'ANN',
      },
    },
  ],
}

const INCLUDED = [
  'Unlimited players and seasons',
  'Automatic PlayHQ data sync',
  'Full public stats page',
  'Player profiles and leaderboards',
  'Awards and honours management',
  'Admin login for your stats volunteers',
  'CSV import and export',
  'Duplicate player merge tool',
  'Season yearbook (Phase 2)',
  'Email support',
]

const FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform'

export default function Pricing() {
  usePageMeta({
    title: 'Pricing — $49/mo or $400/yr per club | BetterStats',
    description: 'Simple, transparent cricket stats pricing for Australian clubs. $49 AUD per month or $400 AUD per year per club — unlimited players, full historical sync, season yearbooks, admin panel and email support included. No lock-in.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/pricing',
    jsonLd: PRICING_JSONLD,
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Transparent pricing</p>
          <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Simple pricing.</h1>
          <p className="text-pb-dim text-lg">One plan. Everything included. No surprises.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto">
          {/* Monthly */}
          <div className="pb-card p-8 text-center">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Monthly</p>
            <div className="font-display font-bold text-[64px] text-pb-text leading-none mb-1">$49</div>
            <p className="font-mono text-[11px] tracking-wide2 text-pb-faint mb-8">PER CLUB PER MONTH</p>

            <ul className="text-left space-y-3 mb-8">
              {INCLUDED.map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-pb-dim">
                  <span className="mt-0.5 shrink-0 font-mono" style={{ color: 'var(--pb-accent)' }}>✓</span>
                  {item}
                </li>
              ))}
            </ul>

            <a
              href={FORM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-text text-center border pb-hairline hover:text-pb-text"
            >
              REQUEST ACCESS
            </a>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              No lock-in. Cancel anytime.
            </p>
          </div>

          {/* Annual */}
          <div className="pb-card p-8 text-center" style={{ borderColor: 'var(--pb-accent)', borderWidth: '1px' }}>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Annual</p>
            <div className="font-display font-bold text-[64px] text-pb-text leading-none mb-1">$400</div>
            <p className="font-mono text-[11px] tracking-wide2 text-pb-faint mb-1">PER CLUB PER YEAR</p>
            <p className="font-mono text-[10px] tracking-wide2 mb-8" style={{ color: 'var(--pb-accent)' }}>SAVE $188 vs MONTHLY</p>

            <ul className="text-left space-y-3 mb-8">
              {INCLUDED.map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-pb-dim">
                  <span className="mt-0.5 shrink-0 font-mono" style={{ color: 'var(--pb-accent)' }}>✓</span>
                  {item}
                </li>
              ))}
            </ul>

            <a
              href={FORM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg text-center"
              style={{ background: 'var(--pb-accent)' }}
            >
              REQUEST ACCESS
            </a>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              Setup and onboarding included. Jack handles the technical side.
            </p>
          </div>
        </div>

        {/* DeepAnalytics — Coming Soon */}
        <div className="mt-16 max-w-2xl mx-auto">
          <div className="pb-card p-8 opacity-75" style={{ borderStyle: 'dashed', borderWidth: '1px', borderColor: 'var(--pb-faint)' }}>
            <div className="flex items-center justify-between mb-6">
              <div>
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Coming soon</p>
                <h2 className="font-display font-bold text-2xl text-pb-text tracking-tight">DeepAnalytics</h2>
              </div>
              <span className="font-mono text-[10px] tracking-wide3 px-3 py-1 rounded-full border" style={{ borderColor: 'var(--pb-faint)', color: 'var(--pb-faint)' }}>
                IN DEVELOPMENT
              </span>
            </div>
            <p className="text-pb-dim text-sm mb-6">
              Cross-club intelligence for serious cricket. DeepAnalytics gives your club access to aggregated stats from across the competition — so you can make smarter selections, prepare better for opposition, and benchmark your players against the rest of the league.
            </p>
            <ul className="space-y-3 mb-6">
              {[
                'Opposition analysis — batting and bowling tendencies by player',
                'Cross-club leaderboards and percentile rankings',
                'Selection insights — compare your squad against the competition',
                'Grade-wide averages and benchmarking',
              ].map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-pb-dim">
                  <span className="mt-0.5 shrink-0 font-mono text-pb-faint">◦</span>
                  {item}
                </li>
              ))}
            </ul>
            <a
              href={FORM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block px-6 py-2.5 border rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors"
              style={{ borderColor: 'var(--pb-faint)' }}
            >
              REGISTER INTEREST
            </a>
          </div>
        </div>

        <div className="mt-20 pb-hairline-t pt-12 text-center">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4">GOT QUESTIONS?</p>
          <h2 className="font-display font-bold text-3xl text-pb-text mb-4 tracking-tight">Not sure if it's right for you?</h2>
          <p className="text-pb-dim mb-8">Get in touch and we'll figure it out together.</p>
          <Link
            to="/contact"
            className="inline-block px-8 py-3 border pb-hairline rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors"
          >
            CONTACT US →
          </Link>
        </div>
      </div>
    </div>
  )
}
