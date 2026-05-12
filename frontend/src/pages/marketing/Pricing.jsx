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
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="font-display font-bold text-4xl md:text-5xl mb-4">Simple pricing</h1>
          <p className="text-slate-300 text-lg">One plan. Everything included. No surprises.</p>
        </div>

        <div className="max-w-sm mx-auto">
          <div className="bg-navy-900 border border-accent/30 rounded-2xl p-8 text-center">
            <div className="text-slate-400 text-sm mb-2">Annual subscription</div>
            <div className="font-display font-bold text-6xl text-white mb-1">$250</div>
            <div className="text-slate-400 text-sm mb-8">per club per year</div>

            <ul className="text-left space-y-3 mb-8">
              {INCLUDED.map(item => (
                <li key={item} className="flex items-start gap-2 text-sm text-slate-300">
                  <span className="text-accent mt-0.5 shrink-0">✓</span>
                  {item}
                </li>
              ))}
            </ul>

            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSdTODO/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary w-full block text-center py-3"
            >
              Request access
            </a>
            <p className="text-slate-500 text-xs mt-3">
              Setup and onboarding included. Jack handles the technical side.
            </p>
          </div>
        </div>

        <div className="mt-16 text-center">
          <h2 className="font-display font-bold text-2xl mb-4">Got questions?</h2>
          <p className="text-slate-400 mb-6">
            Not sure if BetterStats is right for your club? Get in touch and we'll figure it out together.
          </p>
          <Link to="/contact" className="btn-ghost text-slate-300">Contact us →</Link>
        </div>
      </div>
    </div>
  )
}
