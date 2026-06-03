// Shared data for the marketing pages.
// Keeping data separated so the JSX files stay focused on layout.

export const FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform?usp=header'
export const SUPPORT_EMAIL = 'betterstatsau@gmail.com'

// ── Formspree ────────────────────────────────────────────────────────────────
// Sign up at https://formspree.io, create a form pointed at betterstatsau@gmail.com,
// then replace YOUR_FORM_ID below with the 8-char ID from your form's endpoint URL.
export const FORMSPREE_ID = 'xykvbqpr'

// ============================================================
// FEATURES — 6 high-impact cards for the landing & top of features
// (the deep 11-section list lives inside Features.jsx)
// ============================================================
export const LANDING_FEATURES = [
  {
    n: '01',
    title: 'Live Player Profiles',
    desc: 'Career timelines, batting curves, bowling spells, fielding logs. Every player gets a profile worth visiting.',
    stat: 'Per-player profiles',
  },
  {
    n: '02',
    title: 'Leaderboards & Records',
    desc: 'Season, career and all-time. Filter by grade, format, opponent, decade. Sort by 30+ stat columns.',
    stat: '30+ stat columns',
  },
  {
    n: '03',
    title: 'Season Yearbook',
    desc: 'A shareable web-publication for every season — auto-populated with stats, honours, photos, editorial.',
    stat: 'Auto-generated',
  },
  {
    n: '04',
    title: 'Awards & Honours',
    desc: 'Log every club award, association honour, hall of fame inductee, office bearer — going back decades.',
    stat: 'Full history',
  },
  {
    n: '05',
    title: 'Match Scorecards',
    desc: 'Every ball, every wicket, every catch — from PlayHQ today back as far as your MyCricket archives reach.',
    stat: 'Full history',
  },
  {
    n: '06',
    title: 'Shareable Stat Cards',
    desc: 'One-tap export of beautiful, club-branded share cards for social. Match reports your community will repost.',
    stat: 'Auto-styled',
  },
]

// ============================================================
// TESTIMONIALS
// ============================================================
export const TESTIMONIALS = [
  {
    quote: "At last we have a complete stats package that lets us view the club's entire history across every statistic imaginable — even ones we never thought possible. It brings together tools to merge player profiles, add honours, fill in missing data and build out individual player profiles. It's made pretty much every spreadsheet we had redundant — and we had a lot.",
    name: 'Tristram Fletcher',
    role: 'Secretary · Applecross Cricket Club',
    yrs: '',
  },
]

// ============================================================
// HOW IT WORKS
// ============================================================
export const HOW_IT_WORKS = [
  {
    n: '01',
    title: 'We start your first sync',
    desc: 'You give us your club details and we pull every scrap of available data into BetterStats.',
    mins: '5 minutes',
  },
  {
    n: '02',
    title: 'First sync finished',
    desc: 'Merge duplicate players, add your awards and tidy up the database with our streamlined admin tools.',
    mins: '30 minutes',
  },
  {
    n: '03',
    title: 'Your site is live',
    desc: 'Fully branded and ready for everyone to enjoy. Everything after this is kept up to date automatically.',
    mins: '1 hour',
  },
]

// ============================================================
// COMPARISON — PlayHQ vs CricketStatz vs BetterStats
// Cell types:
//   true  → green tick
//   false → grey dash
//   'partial' → amber pill
//   'manual'  → amber pill
//   '—'   → literal dash text
//   {monthly, annual} → billing-toggle-driven text
//   string → literal text
// ============================================================
export const COMPETITORS = {
  playhq: { name: 'PlayHQ', tag: 'System of record', sub: 'Official AU cricket scoring' },
  cstatz: { name: 'CricketStatz', tag: 'Stats software', sub: 'Long-running stats package' },
  // Generic label used on embedded compare sections (home/features). The dedicated
  // /compare page can opt back into the specific competitor name via prop.
  other:  { name: 'Other Competitors', tag: 'Existing tools', sub: 'Generic stats platforms' },
  us:     { name: 'Better', tag: 'Club platform', sub: 'Core stats + modules' },
}

export const COMPARISON_3WAY = [
  {
    section: 'Data depth',
    rows: [
      { feature: 'Live match scorecards', tip: 'Ball-by-ball scoring during a match', playhq: true, cstatz: true, us: true },
      { feature: 'Career stats (all-time, per player)', tip: 'Runs, wickets, averages across every season', playhq: false, cstatz: true, us: true },
      { feature: 'Pre-2020 historical archive', tip: 'MyCricket-era scorecards before PlayHQ migration', playhq: false, cstatz: 'manual', us: true },
      { feature: 'Full club history indexed', tip: 'As far back as your PlayHQ + MyCricket data goes', playhq: false, cstatz: 'manual', us: true },
      { feature: 'Partnership records', playhq: false, cstatz: true, us: true },
      { feature: 'Head-to-head player splits', tip: 'How a player has gone vs every club they have played', playhq: false, cstatz: 'partial', us: true },
    ],
  },
  {
    section: 'Surface & presentation',
    rows: [
      { feature: 'Public, club-branded website', tip: 'Your own URL, your colours, your crest, your sponsors', playhq: false, cstatz: false, us: true },
      { feature: 'Mobile-first, modern design', playhq: 'partial', cstatz: false, us: true },
      { feature: 'Auto-generated season yearbook', playhq: false, cstatz: false, us: true },
      { feature: 'Player profile pages (rich)', tip: 'Per-player URL with timeline, milestones, awards', playhq: false, cstatz: 'partial', us: true },
      { feature: 'Honour boards & awards', playhq: false, cstatz: true, us: true },
      { feature: 'Shareable social stat cards', tip: 'One-tap export of branded Instagram / X cards', playhq: false, cstatz: false, us: true },
    ],
  },
  {
    section: 'Setup & operations',
    rows: [
      { feature: 'Automatic sync from PlayHQ', tip: 'Official AU cricket data feed — no manual entry', playhq: true, cstatz: false, us: true },
      { feature: 'Manual data entry required', tip: 'BetterStats pulls everything from PlayHQ — no scorer-to-spreadsheet copy work.', playhq: true, cstatz: true, us: false },
      { feature: 'Setup time', textRow: true, playhq: 'Built-in', cstatz: '2–4 weeks', us: 'Under 1 hour' },
      { feature: 'Onboarding & migration included', playhq: false, cstatz: false, us: true },
      { feature: 'Selection, socials, fees & analytics modules', tip: 'One platform for availability/selection (BetterSelect), branded social posts (BetterSocials), match fees (BetterFees) and analytics + opposition scouting (BetterIQ) — not just stats.', playhq: false, cstatz: false, us: true },
      { feature: 'Cost for a large club', tip: 'CricketStatz figures include their highest-tier subscription plus historical data charges. Better is a flat rate per club across three tiers — same fee for one team or fifty.', textRow: true, billing: true, playhq: '—', cstatz: '~$600/yr + ~$400 historical', us: { monthly: 'From $49 / month', annual: 'From $449 / year · 3 tiers' } },
    ],
  },
]

// ============================================================
// SCREENSHOTS — where to put real images
// Match filenames in /public/marketing/ to swap mocks for screenshots.
// Each path is a fallback that pages check for; mocks display until present.
// ============================================================
export const SCREENSHOT_PATHS = {
  // Landing hero
  landingHeroCard:        '/marketing/hero-career-card.jpg',
  // Landing showcase tabs
  showcaseLeaderboard:    '/marketing/leaderboard.jpg',
  showcaseProfile:        '/marketing/player-profile.jpg',
  showcaseYearbook:       '/marketing/yearbook.jpg',
  showcaseScorecard:      '/marketing/showcase-scorecard.jpg',
  showcaseAnalysis:       '/marketing/showcase-analysis.jpg',
  // Features hero blocks
  featuresProfile:        '/marketing/feature-profile.jpg',
  featuresLeaderboard:    '/marketing/feature-leaderboard.jpg',
  featuresYearbook:       '/marketing/feature-yearbook.jpg',
  featuresMatch:          '/marketing/feature-match.jpg',
  featuresHonours:        '/marketing/feature-honours.jpg',
  featuresCards:          '/marketing/feature-cards.jpg',
  // Features short-section card thumbnails
  shortScorecard:         '/marketing/short-scorecard.jpg',
  shortStatlab:           '/marketing/short-statlab.jpg',
  shortCompare:           '/marketing/short-compare.jpg',
  shortAwards:            '/marketing/short-awards.jpg',
  shortAdmin:             '/marketing/short-admin.jpg',
  // About page
  aboutFounder:           '/marketing/founder.jpg',
}
