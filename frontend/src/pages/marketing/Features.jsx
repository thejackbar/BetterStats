import MarketingNav from '../../components/MarketingNav'
import { Link } from 'react-router-dom'

const SECTIONS = [
  {
    title: 'Live PlayHQ Sync',
    desc: 'Connect your PlayHQ organisation once, and BetterStats keeps your stats automatically updated after every match. No manual data entry required.',
    points: [
      'Weekly automatic sync, runs overnight',
      'Batting, bowling, and fielding stats per player per game',
      'Season aggregates computed automatically',
      'Works with any PlayHQ-registered club in Australia',
    ],
  },
  {
    title: 'Player Profiles',
    desc: 'Every registered player gets a rich profile page with their full career history, season breakdowns, and notable performances.',
    points: [
      'Career batting, bowling, and fielding totals',
      'Season-by-season comparison',
      'Milestone tracking (500 runs, 50 wickets, 100 games…)',
      'Partnership data and batting position analysis',
    ],
  },
  {
    title: 'Leaderboards & Records',
    desc: "See who's leading the club in every stat category, filterable by season and grade.",
    points: [
      'Batting: runs, average, strike rate, centuries, fifties',
      'Bowling: wickets, economy, average, five-fors',
      'Fielding: catches, run-outs, stumpings',
      'Club and season records updated automatically',
    ],
  },
  {
    title: 'Awards & Honours',
    desc: "Log your club's annual awards, association honours, office bearers, hall of fame inductees, and premierships in one place.",
    points: [
      'Attach awards to player profiles',
      'Browse all-time award history by category',
      'CSV bulk import for historical data',
      'Separate season and career award views',
    ],
  },
  {
    title: 'Admin Tools',
    desc: "A full-featured admin section for your stats volunteers — no technical skills needed.",
    points: [
      'Duplicate player detection and merge tool',
      'Display name overrides for cosmetic corrections',
      'CSV import and export for all data',
      'Username/password login — shareable with committee members',
    ],
  },
  {
    title: 'Season Yearbook (Phase 2)',
    desc: 'A shareable, web-based season summary with auto-generated modules and admin-written prose.',
    points: [
      'Season summary, top performers, match results',
      'Admin-written intro and closing sections',
      'Toggle which modules appear',
      'Publish/unpublish control',
    ],
  },
]

export default function Features() {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">What's included</p>
        <h1 className="font-display font-bold text-[48px] md:text-[60px] tracking-tight text-pb-text mb-4 leading-tight">Features.</h1>
        <p className="text-pb-dim text-lg mb-16">Everything your cricket club needs to run a proper stats platform.</p>

        <div className="space-y-0">
          {SECTIONS.map((s, i) => (
            <div key={s.title} className="pb-hairline-t py-10">
              <div className="grid md:grid-cols-[1fr_2fr] gap-8">
                <div>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">{String(i + 1).padStart(2, '0')}</p>
                  <h2 className="font-display font-bold text-[22px] text-pb-text leading-tight">{s.title}</h2>
                </div>
                <div>
                  <p className="text-pb-dim mb-5 leading-relaxed">{s.desc}</p>
                  <ul className="space-y-2">
                    {s.points.map(p => (
                      <li key={p} className="flex items-start gap-2.5 text-sm text-pb-dim">
                        <span className="mt-0.5 font-mono" style={{ color: 'var(--pb-accent)' }}>✓</span>
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-16 text-center pb-hairline-t pt-10">
          <Link
            to="/pricing"
            className="inline-block px-8 py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            SEE PRICING →
          </Link>
        </div>
      </div>
    </div>
  )
}
