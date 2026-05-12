import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'

const FEATURES = [
  { title: 'Live Stats', desc: 'Player batting, bowling and fielding averages updated after every game via PlayHQ sync.' },
  { title: 'Leaderboards', desc: 'Season and career leaderboards — runs, wickets, economy, strike rate, catches and more.' },
  { title: 'Player Profiles', desc: 'Rich individual profiles with career trends, partnership data, and milestone tracking.' },
  { title: 'Season Records', desc: 'Club and grade records updated automatically — best innings, best figures, partnerships.' },
  { title: 'Awards & Honours', desc: 'Log every club award, association honour, hall of fame inductee, and office bearer.' },
  { title: 'Season Yearbook', desc: 'A shareable, web-based season summary your members will actually read. (Phase 2)' },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 pt-20 pb-16 text-center">
        <div className="inline-block bg-accent/10 border border-accent/20 text-accent text-xs px-3 py-1 rounded-full mb-6">
          Built for Australian cricket clubs
        </div>
        <h1 className="font-display font-bold text-5xl md:text-7xl tracking-tight mb-6">
          Your club's stats,<br />
          <span className="text-accent">done properly.</span>
        </h1>
        <p className="text-slate-300 text-lg md:text-xl max-w-2xl mx-auto mb-10">
          BetterStats turns your PlayHQ data into a beautiful, public stats page your club members will actually use — with player profiles, leaderboards, records, and awards.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLSdTODO/viewform"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary text-base px-6 py-3"
          >
            Request access
          </a>
          <Link to="/features" className="btn-ghost text-base px-6 py-3 text-slate-300">
            See features →
          </Link>
        </div>
      </section>

      {/* Feature grid */}
      <section className="max-w-6xl mx-auto px-4 pb-20">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-navy-900 border border-navy-700 rounded-lg p-5">
              <h3 className="font-medium text-white mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-navy-800 py-16 text-center">
        <h2 className="font-display font-bold text-3xl mb-4">Ready to upgrade your club's stats?</h2>
        <p className="text-slate-400 mb-8">$250/year. Setup included. No lock-in.</p>
        <a
          href="https://docs.google.com/forms/d/e/1FAIpQLSdTODO/viewform"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary text-base px-8 py-3"
        >
          Get started
        </a>
      </section>

      <footer className="border-t border-navy-800 py-8 text-center text-slate-600 text-sm">
        <div className="flex items-center justify-center gap-6 mb-3">
          <Link to="/terms" className="hover:text-slate-400">Terms</Link>
          <Link to="/privacy" className="hover:text-slate-400">Privacy</Link>
          <Link to="/contact" className="hover:text-slate-400">Contact</Link>
        </div>
        © {new Date().getFullYear()} BetterStats
      </footer>
    </div>
  )
}
