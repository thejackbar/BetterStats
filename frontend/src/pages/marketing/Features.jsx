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
    <div className="min-h-screen bg-navy-950 text-white">
      <MarketingNav />

      <div className="max-w-4xl mx-auto px-4 py-16">
        <h1 className="font-display font-bold text-4xl md:text-5xl mb-4">Features</h1>
        <p className="text-slate-300 text-lg mb-12">Everything your cricket club needs to run a proper stats platform.</p>

        <div className="space-y-12">
          {SECTIONS.map(s => (
            <div key={s.title} className="border-t border-navy-800 pt-10">
              <h2 className="font-display font-bold text-2xl text-white mb-3">{s.title}</h2>
              <p className="text-slate-300 mb-4">{s.desc}</p>
              <ul className="space-y-2">
                {s.points.map(p => (
                  <li key={p} className="flex items-start gap-2 text-sm text-slate-400">
                    <span className="text-accent mt-0.5">✓</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-16 text-center">
          <Link to="/pricing" className="btn-primary text-base px-8 py-3">See pricing →</Link>
        </div>
      </div>
    </div>
  )
}
