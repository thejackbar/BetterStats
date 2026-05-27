import MarketingNav from '../../components/MarketingNav'
import { Link } from 'react-router-dom'
import { usePageMeta } from '../../hooks/usePageMeta'

const SECTIONS = [
  {
    title: 'Automatic Stats Sync',
    desc: 'Connect your club once and BetterStats handles everything from there. After first sync your full history is imported — decades of data, automatically. Stats update after every match with no manual effort.',
    points: [
      'Full historical data imported on first sync — going back to the early 2000s',
      'Batting, bowling, and fielding stats captured per player per game',
      'Season aggregates and career totals computed automatically',
      'Weekly scheduled sync runs overnight — nothing to trigger',
      'Admin-triggered hard refresh available for on-demand updates',
    ],
  },
  {
    title: 'Player Profiles',
    desc: 'Every player gets a rich, public profile page with their full career stats, season history, and achievements — automatically kept up to date.',
    points: [
      'Career batting, bowling, and fielding totals with animated stat counters',
      'Season-by-season breakdown with colour-coded best/worst seasons',
      'Career progression charts — runs over time, averages by season',
      'Dismissal breakdown chart showing how they typically got out',
      'Partnership data and batting position analysis',
      'Achievements tab: milestone badges (500 runs, 50 wickets, 100 games…)',
      'Honours tab: club awards, hall of fame, caps, and association honours',
      'Player photo support with shareable stat card for social media',
    ],
  },
  {
    title: 'Leaderboards',
    desc: 'Live club leaderboards across every batting, bowling, and fielding category. Filter by season and grade to find exactly who led the club.',
    points: [
      'Batting: most runs, average (min. 500 runs), high score, fifties, centuries, sixes, fours, ducks',
      'Bowling: wickets, economy (min. 100 overs), average (min. 50 wickets), best figures, five-fors, maidens',
      'Fielding: catches, run-outs, stumpings',
      'Filter by any season or grade combination',
      'Rank badges with colour coding (gold, silver, bronze)',
      'All leaderboards update automatically after each sync',
    ],
  },
  {
    title: 'Club Records',
    desc: 'All-time and season-best records across batting, bowling, partnerships, all-rounders, and team achievements — always current.',
    points: [
      'Batting records: most career runs, highest individual score, best average, most hundreds/fifties',
      'Bowling records: most career wickets, best innings figures, best economy, most five-fors',
      'Partnership records: all-time records at every wicket position, top 25 cross-grade partnerships',
      'All-rounder records: combined batting and bowling thresholds (min. 1,000 runs & 100 wickets)',
      'Team records: most matches played, most seasons represented',
      '"NEW" badge flags records set in the current season',
    ],
  },
  {
    title: 'Season Yearbooks',
    desc: 'A proper, shareable digital season publication for every year. Auto-populated with stats, honours, and results — then topped up with editorial content by your admin team.',
    points: [
      'Overview tab: season W/L/D record, win rate, season progression chart',
      'Batting, bowling, and fielding honours auto-populated from season stats',
      'All-rounder honours and partnership records per season',
      'Results tab: every match result by grade with scores',
      'Photo gallery: upload team and event photos',
      "Editorial sections: add President's Report, Coach's Report, Sponsor's Message, and more",
      'Honour board: record club positions and holders (President, Captain, Treasurer…)',
      'AI-assisted season narrative generator to kick-start the write-up',
      'Awards section: pull from the awards admin or add season-specific winners',
      "Publish/unpublish control — draft until you're ready",
    ],
  },
  {
    title: 'Match Scorecards',
    desc: 'Full scorecards for every game — batting, bowling, fall of wickets, and partnerships — linked directly from player profiles.',
    points: [
      'Both innings displayed side-by-side with full batting and bowling details',
      'Fall of wickets as badge pills per innings',
      'Partnership data: runs, batters involved, and contribution split',
      'Result displayed prominently with winning team highlighted',
      'Date, venue, toss, and umpire details where available',
      'Every player name links back to their full profile',
      'Responsive layout — reads well on mobile',
    ],
  },
  {
    title: 'StatLab',
    desc: 'A custom query builder for power users. Build your own leaderboards with any combination of metrics, filters, and thresholds.',
    points: [
      'Career or season mode',
      'Sort by any of 50+ metrics: runs, wickets, averages, economy, strike rate, catches, and more',
      'Add multiple filters with operators (at least, more than, exactly, at most, less than)',
      'Quick preset queries: Run Scorers, Wicket Takers, All-Rounders, Five-for Club, Batting Averages',
      'Results table supports up to 500 rows with client-side column sorting',
      'Filter by season and grade combination',
    ],
  },
  {
    title: 'Player Comparison',
    desc: 'Head-to-head side-by-side comparison of any two players across their full careers.',
    points: [
      'Batting: innings, runs, average, strike rate, high score, fifties, centuries, sixes, fours, ducks',
      'Bowling: wickets, average, economy, best figures, five-fors, maidens',
      'Fielding: catches, run-outs, stumpings, total dismissals',
      'Animated comparison bars clearly show who leads each stat',
      'Superior stat highlighted in club accent colour',
      'Both player names link back to their full profiles',
    ],
  },
  {
    title: 'Shareable Player Cards',
    desc: 'Every player profile has a shareable stat card — a clean, branded snapshot that looks great on social media.',
    points: [
      'Career or season stats view selectable',
      'Batting and bowling highlights on a single card',
      'Club rank badges (e.g. #1 Runs, #2 Wickets)',
      'Milestone indicators (centuries, five-fors)',
      'Player photo or club logo fallback',
      'Native share API support — one tap to share on mobile',
    ],
  },
  {
    title: 'Awards & Honours',
    desc: "Your club's full honours history in one place — annual awards, hall of fame, office bearers, association honours, and premierships.",
    points: [
      'Create award definitions once, assign winners each season',
      "Awards appear on the recipient's player profile automatically",
      'Hall of fame, life membership, and career honour tracking',
      'Office bearer history: President, Captain, Treasurer, and custom positions',
      'Premiership records with grade and year',
      'CSV bulk import for back-filling historical award data',
      'Browse all-time award history by category',
    ],
  },
  {
    title: 'Admin Tools',
    desc: 'A full-featured admin panel for your stats volunteers. No technical skills required — just a login.',
    points: [
      'Duplicate player detection and one-click merge tool — handles all historical stats correctly',
      'Display name overrides for cosmetic corrections without breaking data',
      'Grade display name overrides (rename a grade without losing game history)',
      'CSV import and export for players, awards, and stats',
      'Manual sync trigger with live progress feed',
      'Sync run history with success/error reporting',
      'Multiple admin logins — share access with committee members',
      'Player photo upload via admin panel',
    ],
  },
]

export default function Features() {
  usePageMeta({
    title: 'Features — Automated Cricket Club Stats | BetterStats',
    description: 'Every feature included with BetterStats: automatic PlayHQ/MyCricket sync, rich player profiles, leaderboards, all-time records, partnership records, season yearbooks, StatLab custom queries, awards & honours management, and admin tools.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/features',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />

      <div id="main-content" tabIndex="-1" className="max-w-4xl mx-auto px-4 py-16">
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
                        <span className="mt-0.5 font-mono shrink-0" style={{ color: 'var(--pb-accent)' }}>✓</span>
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
