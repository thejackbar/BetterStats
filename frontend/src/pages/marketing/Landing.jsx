import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import { usePageMeta } from '../../hooks/usePageMeta'

const FEATURES = [
  { title: 'Live Stats', desc: 'Player batting, bowling and fielding averages updated after every game via PlayHQ sync.' },
  { title: 'Leaderboards', desc: 'Season and career leaderboards — runs, wickets, economy, strike rate, catches and more.' },
  { title: 'Player Profiles', desc: 'Rich individual profiles with career trends, partnership data, and milestone tracking.' },
  { title: 'Season Records', desc: 'Club and grade records updated automatically — best innings, best figures, partnerships.' },
  { title: 'Awards & Honours', desc: 'Log every club award, association honour, hall of fame inductee, and office bearer.' },
  { title: 'Season Yearbook', desc: 'A shareable, web-based season summary your members will actually read. (Phase 2)' },
]

export default function Landing() {
  usePageMeta({
    title: 'BetterStats — Cricket Stats Platform for Australian Clubs',
    description: 'Automated club cricket stats, leaderboards, records and season yearbooks — built for Australian cricket clubs. Pulls from PlayHQ and MyCricket; no manual data entry.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-4 pt-24 pb-20 text-center">
        <div className="inline-block border pb-hairline font-mono text-[10px] tracking-wide3 text-pb-faint px-3 py-1 rounded-full mb-8 uppercase">
          Built for Australian cricket clubs
        </div>
        <h1 className="font-display font-bold text-[52px] sm:text-[72px] md:text-[88px] tracking-tight leading-[0.9] text-pb-text mb-8">
          Your club's stats,<br />
          <span style={{ color: 'var(--pb-accent)' }}>done properly.</span>
        </h1>
        <p className="text-pb-dim text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
          BetterStats turns your PlayHQ data into a beautiful, public stats page your club members will actually use — with player profiles, leaderboards, records, and awards.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform?usp=header"
            target="_blank"
            rel="noopener noreferrer"
            className="px-8 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            REQUEST ACCESS
          </a>
          <Link to="/features" className="px-8 py-3 border pb-hairline rounded font-mono text-[11px] tracking-wide3 font-semibold text-pb-dim hover:text-pb-text transition-colors">
            SEE FEATURES →
          </Link>
        </div>
      </section>

      {/* Feature grid */}
      <section className="max-w-5xl mx-auto px-4 pb-24">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <div key={f.title} className="pb-card p-5">
              <p className="font-mono text-[10px] tracking-wide3 mb-2" style={{ color: 'var(--pb-accent)' }}>{f.title.toUpperCase()}</p>
              <p className="text-pb-dim text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="pb-hairline-t py-20 text-center">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4">READY TO UPGRADE?</p>
        <h2 className="font-display font-bold text-4xl text-pb-text mb-3 tracking-tight">Your club deserves better stats.</h2>
        <p className="text-pb-faint font-mono text-[11px] tracking-wide2 mb-8">$250/year. Setup included. No lock-in.</p>
        <a
          href="https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform?usp=header"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block px-10 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          GET STARTED
        </a>
      </section>

      <footer className="pb-hairline-t py-8 text-center">
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 mb-3">
          <Link to="/features" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">FEATURES</Link>
          <Link to="/pricing" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">PRICING</Link>
          <Link to="/faq" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">FAQ</Link>
          <Link to="/about" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">ABOUT</Link>
          <Link to="/contact" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">CONTACT</Link>
          <Link to="/terms" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">TERMS</Link>
          <Link to="/privacy" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">PRIVACY</Link>
        </div>
        <div className="flex items-center justify-center gap-4 mb-3">
          <a href="https://x.com/betterstatsau" target="_blank" rel="noopener noreferrer me" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">X / TWITTER</a>
          <a href="https://www.facebook.com/profile.php?id=61590372751599" target="_blank" rel="noopener noreferrer me" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">FACEBOOK</a>
        </div>
        <p className="font-mono text-[10px] text-pb-faintest">© {new Date().getFullYear()} BETTERSTATS</p>
      </footer>
    </div>
  )
}
