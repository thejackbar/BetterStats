import { Link } from 'react-router-dom'
import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ScreenshotOrMock from '../../components/marketing/ScreenshotOrMock'
import ZoomableImage from '../../components/marketing/ZoomableImage'
import Comparison3Way from '../../components/marketing/Comparison3Way'
import SelfServeTrialModal from '../../components/admin/SelfServeTrialModal'
import {
  MockLeaderboard,
  MockPlayerProfile,
  MockYearbook,
  MockHeritageCard,
} from '../../components/marketing/Mockups'
import { SCREENSHOT_PATHS } from '../../data/marketing'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { usePageMeta } from '../../hooks/usePageMeta'
import { useSelfServeTrialGate } from '../../hooks/useSelfServeTrialGate'

// ============================================================
// SECTIONS — preserves the existing detailed content for SEO,
// reorganised into hero blocks (first 6 features have visuals)
// and a tight list for the long tail.
// ============================================================
const HERO_SECTIONS = [
  {
    n: '01',
    eyebrow: 'Automatic Stats Sync',
    title: 'Connect once. Sync forever.',
    desc: 'Connect your club once and your whole match history is imported. From then on every new game flows in on its own from PlayHQ or Play-Cricket. Stats stay current after every match, with zero data entry and no spreadsheets to keep up.',
    bullets: [
      'Connect once and your full match history is imported automatically from PlayHQ or Play-Cricket',
      'Old spreadsheets, scorebooks and stat exports merged in alongside your live sync, included in the plan',
      'Simple CSV templates to fill any gaps in older data',
      'Batting, bowling, and fielding stats captured per player per game',
      'Season aggregates and career totals computed automatically',
      'Stays current after every match, with nothing to trigger and no data entry',
      'Admin-triggered hard refresh available for on-demand updates',
    ],
    src: SCREENSHOT_PATHS.featuresLeaderboard,
    mock: <MockLeaderboard />,
  },
  {
    n: '02',
    eyebrow: 'Player Profiles',
    title: 'A career page worth visiting.',
    desc: "Every player gets a public profile page with their full career stats, season history, and achievements, automatically kept up to date.",
    bullets: [
      'Career batting, bowling, and fielding totals with animated stat counters',
      'Season-by-season breakdown with colour-coded best/worst seasons',
      'Career progression charts: runs over time, averages by season',
      'Dismissal breakdown chart showing how they typically got out',
      'Partnership data and batting position analysis',
      'Achievements: milestone badges (500 runs, 50 wickets, 100 games…)',
      'Honours: club awards, hall of fame, caps, association honours',
      'Junior seasons left out of a senior career by default, with a tap to add them back',
      'Player photo support with shareable stat card for social',
    ],
    src: SCREENSHOT_PATHS.featuresProfile,
    mock: <MockHeritageCard />,
  },
  {
    n: '03',
    eyebrow: 'Player Merge Tool',
    title: 'One player. One profile. Stats stop splitting.',
    desc: "Duplicate profiles for the same player used to scatter stats across two or three records. The Player Merge Tool fixes that and keeps it fixed.",
    bullets: [
      'Smart sorting suggests which profiles likely belong to the same player',
      'One click to merge: all batting, bowling, fielding history combines',
      'Just as easy to undo if you change your mind',
      'Every future sync routes new matches into the merged profile',
      'No more career averages spread across two records',
    ],
    src: SCREENSHOT_PATHS.featuresMatch,
    mock: <MockPlayerProfile />,
  },
  {
    n: '04',
    eyebrow: 'Leaderboards',
    title: 'Live club leaderboards. Every category.',
    desc: 'Live club leaderboards across every batting, bowling, and fielding category. Filter by season and grade to find exactly who led the club.',
    bullets: [
      'Batting: runs, average (min. 500 runs), high score, fifties, centuries, sixes, fours, ducks',
      'Bowling: wickets, economy (min. 100 overs), average (min. 50 wickets), best figures, five-fors, maidens',
      'Fielding: catches, run-outs, stumpings',
      'Filter by any season or grade combination',
      'Count or leave out junior, women’s, masters and mixed grades, club-wide or page by page',
      'Rank badges with colour coding (gold, silver, bronze)',
      'All leaderboards update automatically after each sync',
    ],
    src: SCREENSHOT_PATHS.featuresLeaderboard,
    mock: <MockLeaderboard />,
  },
  {
    n: '05',
    eyebrow: 'Season Yearbooks',
    title: 'The annual that writes itself.',
    desc: "A proper, shareable digital season publication for every year. Auto-populated with stats, honours, and results, then topped up with editorial content by your admin team.",
    bullets: [
      'Overview tab: season W/L/D record, win rate, progression chart',
      'Batting, bowling, fielding, all-rounder honours auto-populated',
      'Partnership records per season',
      'Results: every match by grade with scores',
      'Photo gallery: team and event photos',
      "Editorial sections: President's Report, Coach's Report, Sponsor's Message",
      'Honour board: record club positions and holders',
      'AI-assisted season narrative generator',
      "Publish/unpublish control: draft until you're ready",
    ],
    src: SCREENSHOT_PATHS.featuresYearbook,
    mock: <MockYearbook />,
  },
  {
    n: '06',
    eyebrow: 'Club Records',
    title: 'All-time records. Always current.',
    desc: 'All-time and season-best records across batting, bowling, partnerships, all-rounders, and team achievements, always kept current.',
    bullets: [
      'Batting: most career runs, highest individual score, best average, most hundreds/fifties',
      'Bowling: most career wickets, best innings figures, best economy, most five-fors',
      'Partnerships: all-time records at every wicket position, top 25 cross-grade',
      'All-rounder records: combined batting and bowling thresholds',
      'Team records: most matches played, most seasons represented',
      '"NEW" badge flags records set in the current season',
    ],
    src: SCREENSHOT_PATHS.featuresHonours,
    mock: <MockPlayerProfile />,
  },
  {
    n: '07',
    eyebrow: 'Player Comparison',
    title: 'Side-by-side, head-to-head.',
    desc: "Compare any two players over their full careers, then use the same view as a form indicator when you've got a tough selection to make.",
    bullets: [
      'Batting, bowling and fielding compared row by row',
      'Career totals and per-season splits side by side',
      'Recent-form view to support selection conversations',
      'Dismissal patterns and opposition history per player',
      'Shareable link so the whole selection panel sees the same numbers',
    ],
    src: SCREENSHOT_PATHS.shortCompare,
    mock: <MockPlayerProfile />,
  },
  {
    n: '08',
    eyebrow: 'Club Branding & Admin',
    title: "Make it your club's own.",
    desc: 'BetterStats runs your public site in your colours and looks after the back office behind it. Set your crest, palette and fonts, place your sponsors across the site, and keep the database clean without touching a spreadsheet.',
    bullets: [
      'White-label the public site: your crest, club colours and display fonts, in dark or light',
      'Place your sponsors across the site and in every season yearbook',
      'Merge duplicate players or rename a grade in a couple of clicks',
      'A milestone tracker so nobody’s 100th game slips by',
      'A notification centre for syncs, new milestones and pending requests',
      'Trigger a manual sync any time, with separate logins for your committee',
    ],
    src: SCREENSHOT_PATHS.featuresWhitelabel,
    mock: <MockPlayerProfile />,
  },
]

const SHORT_SECTIONS = [
  {
    title: 'Match Scorecards',
    desc: 'Full scorecards for every game (batting, bowling, fall of wickets, and partnerships) linked directly from player profiles.',
    src: SCREENSHOT_PATHS.shortScorecard,
  },
  {
    title: 'StatLab',
    desc: 'A custom query builder for power users. Build your own leaderboards with any combination of metrics, filters, and thresholds. 50+ sortable metrics, multiple filter operators, preset queries.',
    src: SCREENSHOT_PATHS.shortStatlab,
  },
  {
    title: 'Shareable Player Cards',
    desc: 'Every player profile has a clean, branded stat card: career or season view, club rank badges, milestone indicators, one-tap native share.',
    src: SCREENSHOT_PATHS.featuresCards,
  },
  {
    title: 'Awards & Honours',
    desc: "Your club's full honours history in one place: annual awards, hall of fame, office bearers, association honours, and premierships. CSV bulk import for back-filling.",
    src: SCREENSHOT_PATHS.shortAwards,
  },
  {
    title: 'Admin Tools',
    desc: 'Everything your stats volunteers need: display name overrides, grade renames, CSV import/export, manual sync trigger, and multiple admin logins.',
    src: SCREENSHOT_PATHS.shortAdmin,
  },
  {
    title: 'Opposition Analysis',
    desc: "Every player's record broken down by opponent, so you can see who they pile runs on and who has had their number. Handy reading before a big game.",
    src: SCREENSHOT_PATHS.shortOpposition,
  },
  {
    title: 'Match Archive',
    desc: 'Browse every game the club has played, filter by season and grade, and open the full scorecard for any one of them.',
    src: SCREENSHOT_PATHS.shortGames,
  },
]

// Card with optional screenshot thumbnail at top
function ShortCard({ s, delay }) {
  const [imgFailed, setImgFailed] = useState(false)
  return (
    <Reveal delay={delay}>
      <div className="surface h-full overflow-hidden">
        {s.src && !imgFailed && (
          <div className="border-b pb-hairline overflow-hidden h-44 rounded-t-[calc(1rem-1px)]">
            <ZoomableImage
              src={s.src}
              alt={s.title}
              caption={s.desc}
              className="w-full h-full object-cover object-top"
              wrapperClassName="h-full"
              onError={() => setImgFailed(true)}
            />
          </div>
        )}
        <div className="p-6">
          <h3 className="text-lg font-semibold mb-2">{s.title}</h3>
          <p className="text-sm text-pb-dim leading-relaxed">{s.desc}</p>
        </div>
      </div>
    </Reveal>
  )
}

// ─── Hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative pt-32 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative text-center">
        <p className="pill mb-6 inline-flex"><span className="dot" />In every plan</p>
        <h1 className="font-display font-bold text-[44px] sm:text-[60px] lg:text-[80px] tracking-tight leading-[0.95] mb-6">
          <span className="gradient-text">BetterStats.</span>
        </h1>
        <p className="text-lg lg:text-xl text-pb-dim max-w-xl mx-auto leading-relaxed">
          Your club’s reconciled history and a public site to be proud of, included in every BetterCricket plan. Here’s everything it does.
        </p>
      </div>
    </section>
  )
}

// ─── The other modules ────────────────────────────────────────────────────
function BeyondCore() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">The other modules</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">There’s more than stats.</h2>
            <p className="text-pb-dim max-w-xl mx-auto">Everything above is BetterStats. Bolt on the modules that run your season and your club.</p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {MODULES_MARKETING.map((m, i) => (
            <Reveal key={m.slug} delay={(i % 4) * 70} className="h-full">
              <Link to={`/modules/${m.slug}`} className="surface p-6 h-full flex flex-col hover:border-accent/30 transition-colors group block">
                <div className="flex items-center mb-4">
                  <img src={m.logo} alt="" className="w-10 h-10 rounded-xl" />
                </div>
                <h3 className="text-lg font-semibold mb-1.5"><ModuleWordmark name={m.name} accent={m.accent} /></h3>
                <p className="text-sm text-pb-dim leading-relaxed mb-4 flex-1">{m.tagline}</p>
                <span className="text-sm font-medium inline-flex items-center gap-1" style={{ color: m.accent }}>Explore <span className="group-hover:translate-x-0.5 transition-transform">→</span></span>
              </Link>
            </Reveal>
          ))}
        </div>
        <div className="text-center mt-10">
          <Link to="/modules" className="cta-secondary">Tour all modules →</Link>
        </div>
      </div>
    </section>
  )
}

// ─── Feature Block (alternating layout) ──────────────────────────────────
function FeatureBlock({ f, idx, onCta }) {
  const flip = idx % 2 === 1
  return (
    <section className={`px-4 sm:px-6 lg:px-10 py-20 ${idx % 2 === 1 ? 'bg-black/20 border-y pb-hairline' : ''}`}>
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className={`grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center ${flip ? 'lg:flex-row-reverse lg:[direction:rtl]' : ''}`}>
            <div className="col-span-1 lg:col-span-5 lg:[direction:ltr]">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-xl bg-accent/15 border border-accent/40 flex items-center justify-center text-accent font-bold">{f.n}</div>
                <p className="text-sm font-mono uppercase tracking-wide3 text-accent">{f.eyebrow}</p>
              </div>
              <h2 className="text-3xl lg:text-5xl font-bold leading-tight mb-6 tracking-tight">{f.title}</h2>
              <p className="text-pb-dim text-lg mb-6 leading-relaxed">{f.desc}</p>
              <ul className="space-y-3 mb-7">
                {f.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-3 text-pb-dim">
                    <span className="tick mt-0.5">✓</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={onCta} className="cta-primary !text-sm !py-2.5 !px-5">Get Your Club on BetterCricket today!</button>
            </div>
            <div className="col-span-1 lg:col-span-7 lg:[direction:ltr]">
              <div className="relative product-shadow rounded-2xl">
                <ScreenshotOrMock src={f.src} alt={f.eyebrow} fallback={f.mock} />
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

// ─── Short feature list (long-tail tools) ────────────────────────────────
function ShortFeatures() {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-20 border-t pb-hairline bg-black/20">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <p className="pill-neutral inline-flex mb-5">And the rest</p>
            <h2 className="font-display font-bold text-3xl md:text-5xl mb-4 tracking-tight">More tools your committee will use.</h2>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SHORT_SECTIONS.map((s, i) => (
            <ShortCard key={s.title} s={s} delay={(i % 3) * 80} />
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── CTA ─────────────────────────────────────────────────────────────────
function FeaturesCTA({ onCta }) {
  return (
    <section className="px-4 sm:px-6 lg:px-10 py-24 relative overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[900px] mx-auto relative">
        <div className="surface-strong p-10 lg:p-14 text-center">
          <p className="pill mb-6 mx-auto"><span className="dot" />In every plan</p>
          <h2 className="font-display font-bold text-4xl md:text-5xl mb-5 tracking-tight">BetterStats, <span className="gradient-text">in every plan.</span></h2>
          <p className="text-lg text-pb-dim max-w-xl mx-auto mb-8">
            Everything on this page is BetterStats, from $399 a year, flat rate per club. Add modules whenever you’re ready.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button type="button" onClick={onCta} className="cta-primary">Request club access →</button>
            <Link to="/pricing" className="cta-secondary">See pricing</Link>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────
export default function Features() {
  usePageMeta({
    title: 'Features: Automated Cricket Club Stats | BetterCricket',
    description: 'Automatic stats sync, rich player profiles, leaderboards, records and season yearbooks, the foundation of every BetterCricket plan. Plus partnership records, StatLab custom queries, awards & honours management, and admin tools.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/features',
  })
  const { trigger: triggerTrial, modalOpen: trialModalOpen, setModalOpen: setTrialModalOpen, defaultTrialDays } = useSelfServeTrialGate()
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <Hero />
        {HERO_SECTIONS.map((f, i) => (
          <FeatureBlock key={f.n} f={f} idx={i} onCta={triggerTrial} />
        ))}
        <ShortFeatures />
        <Comparison3Way which="betterstats" />
        <BeyondCore />
        <FeaturesCTA onCta={triggerTrial} />
      </div>
      <MarketingFooter />
      {trialModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setTrialModalOpen(false)}
        />
      )}
    </div>
  )
}
