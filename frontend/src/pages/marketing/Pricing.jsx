import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'

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

export default function Pricing() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Transparent pricing</p>
          <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Simple pricing.</h1>
          <p className="text-pb-dim text-lg">One plan. Everything included. No surprises.</p>
        </div>

        <div className="max-w-sm mx-auto">
          <div className="pb-card p-8 text-center" style={{ borderColor: 'var(--pb-accent)', borderWidth: '1px' }}>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Annual subscription</p>
            <div className="font-display font-bold text-[72px] text-pb-text leading-none mb-1">$250</div>
            <p className="font-mono text-[11px] tracking-wide2 text-pb-faint mb-8">PER CLUB PER YEAR</p>

            <ul className="text-left space-y-3 mb-8">
              {INCLUDED.map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-pb-dim">
                  <span className="mt-0.5 shrink-0 font-mono" style={{ color: 'var(--pb-accent)' }}>✓</span>
                  {item}
                </li>
              ))}
            </ul>

            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform"
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
