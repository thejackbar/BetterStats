// Shared data for the marketing pages.
// Keeping data separated so the JSX files stay focused on layout.

export const FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeDdUcFct4NzBYSTuzC03yZ9021cLxQmV77mi6-z9fHCcYGrQ/viewform?usp=header'
export const SUPPORT_EMAIL = 'betterstatsau@gmail.com'

// ── Formspree ────────────────────────────────────────────────────────────────
// Sign up at https://formspree.io, create a form pointed at betterstatsau@gmail.com,
// then replace YOUR_FORM_ID below with the 8-char ID from your form's endpoint URL.
export const FORMSPREE_ID = 'YOUR_FORM_ID'

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
// TESTIMONIALS (currently placeholders — swap with real quotes)
// ============================================================
export const TESTIMONIALS = [
  {
    quote: "BetterStats brought back seasons of scorecards we thought were lost. Our club's history is now searchable, sortable, and the kids can finally see their grandfathers' stats.",
    name: 'Mike Eastwood',
    role: 'Committee · Applecross CC',
    yrs: 'Volunteer · 12 seasons',
  },
  {
    quote: "It's the only cricket platform I've used that respects the data. Old players get found. Merges get tracked. Aggregates actually add up. It feels like it was built by someone who keeps a scorebook.",
    name: 'Sarah Pendlebury',
    role: 'Statistician · Booragoon DCC',
    yrs: '12 years on committee',
  },
  {
    quote: "Replaced our crusty WordPress site, our spreadsheet honour board, and the captain's nagging — all in a weekend. The yearbook alone is worth the subscription.",
    name: 'David Ng',
    role: 'Captain · 1st Grade',
    yrs: '180 games',
  },
]

// ============================================================
// HOW IT WORKS
// ============================================================
export const HOW_IT_WORKS = [
  {
    n: '01',
    title: 'Share your PlayHQ club ID',
    desc: 'A 5-minute form. We do the rest from there.',
    mins: '5 minutes',
  },
  {
    n: '02',
    title: 'We sync everything',
    desc: 'Every match, every season. PlayHQ today, MyCricket archives going back as far as your data does. Nightly refresh from then on.',
    mins: '24–48 hours',
  },
  {
    n: '03',
    title: 'Your site goes live',
    desc: 'Branded with your club colours and crest. Public URL. Yearbook auto-built. Share-cards ready.',
    mins: 'Live by next match',
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
  us:     { name: 'BetterStats', tag: 'Public club site', sub: 'Pulls PlayHQ into a club website' },
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
      { feature: 'Cost for a large club', tip: 'CricketStatz figures include their highest-tier subscription plus historical data charges.', textRow: true, billing: true, playhq: '—', cstatz: '~$600/yr + ~$400 historical', us: { monthly: '$49 / month', annual: '$400 / year' } },
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
