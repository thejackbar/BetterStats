// Shared data for the marketing pages.
// Keeping data separated so the JSX files stay focused on layout.

// ── Brand ────────────────────────────────────────────────────────────────────
// BetterCricket is the cricket product of BetterSports (our trading name).
export const BRAND = 'BetterCricket'
export const COMPANY = 'BetterSports'
export const ABN = '32 624 335 397'
export const DOMAIN = 'betterat.cricket'
export const BASE_URL = 'https://betterat.cricket'

export const SUPPORT_EMAIL = 'cricket@bettersports.com.au'

// ── Formspree ────────────────────────────────────────────────────────────────
// Sign up at https://formspree.io, create a form pointed at the support inbox,
// then replace the ID below with the 8-char ID from your form's endpoint URL.
export const FORMSPREE_ID = 'xykvbqpr'

// ============================================================
// FEATURES — 6 high-impact cards for the landing & top of features
// (the deep section list lives inside Features.jsx)
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
    desc: 'A shareable web-publication for every season, auto-populated with stats, honours, photos and editorial.',
    stat: 'Auto-generated',
  },
  {
    n: '04',
    title: 'Awards & Honours',
    desc: 'Log every club award, association honour, hall of fame inductee and office bearer, going back decades.',
    stat: 'Full history',
  },
  {
    n: '05',
    title: 'Match Scorecards',
    desc: 'Every ball, every wicket, every catch: your whole match history, synced automatically and kept current.',
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
    desc: 'You give us your club details and we pull every scrap of available history into BetterCricket automatically, with no spreadsheets to hand over.',
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
// COMPARISONS — one per surface (each marketing page picks its own).
//
// Shape:
//   { eyebrow, heading, sub,
//     columns: [ { key, name, tag, sub?, us? } … ],   // competitors first, "us" last
//     sections: [ { section, rows: [ { feature, tip?, textRow?, billing?, values:{ <colKey>: cell } } ] } ],
//     cta?: { line, label, to } }
//
// Cell shapes (read by ComparisonTable):
//   true  → green tick · false → grey cross
//   'partial' / 'manual' → amber pill
//   '—'   → literal em dash
//   {monthly, annual} → driven by the billing toggle
//   any other string → literal text
//
// BetterIQ is a category of one — see COMPARISON_SOLO below (no table).
// ============================================================
const US_COL = { key: 'us', name: 'BetterCricket', tag: 'One platform', sub: 'Stats, site & the modules that run your club', us: true }

export const COMPARISONS = {
  // Home + one-pager — the whole platform vs the usual patchwork of tools.
  platform: {
    eyebrow: 'Why one platform',
    heading: 'Five tools worth of club admin. One subscription.',
    sub: 'Most clubs run their season on a few spreadsheets, a website builder, a design app, a bulk email tool and a few group chats. BetterCricket replaces all of it, in one central place, fed by one match feed.',
    columns: [
      { key: 'patchwork', name: 'The usual patchwork', tag: 'A spreadsheet + 4 apps', sub: 'Spreadsheets · a DIY site · Canva · Mailchimp · group chats' },
      US_COL,
    ],
    sections: [
      {
        section: 'Everything your club runs on',
        rows: [
          { feature: 'Complete club history & stats', tip: 'Every player, every team, every match, every season, kept forever', values: { patchwork: 'Spreadsheets', us: true } },
          { feature: 'Public, club-branded website', tip: 'Your own URL, your colours, your crest, your sponsors', values: { patchwork: 'Separate site builder', us: true } },
          { feature: 'Availability & team selection', values: { patchwork: 'Group chats', us: true } },
          { feature: 'Net Manager', tip: 'Net attendance, timing and workload', values: { patchwork: 'Spreadsheet + stopwatch', us: true } },
          { feature: 'Match-day social graphics', tip: 'Lineups, scorecards, player of the match', values: { patchwork: 'Canva, by hand', us: true } },
          { feature: 'Fees, membership, comms & merch', values: { patchwork: 'Spreadsheets + Mailchimp', us: true } },
          { feature: 'Opposition scouting & analytics', values: { patchwork: false, us: true } },
        ],
      },
      {
        section: 'How it feels to run',
        rows: [
          { feature: 'Enter your match data once', tip: 'It flows into stats, posts, selection and analytics', values: { patchwork: false, us: true } },
          { feature: 'Built for cricket, not adapted to it', values: { patchwork: 'partial', us: true } },
          { feature: 'Logins & bills to manage', textRow: true, values: { patchwork: '5+ tools', us: 'One subscription' } },
        ],
      },
    ],
    cta: { line: 'Stop stitching five tools together every weekend. Run the whole club from one place.', label: 'See everything BetterCricket does →', to: '/overview' },
  },

  // BetterStats (Core) — the public stats + site, vs dedicated stats tools.
  betterstats: {
    eyebrow: 'Compare',
    heading: 'Your stats deserve better than a spreadsheet.',
    sub: 'BetterStats is included in every plan: your full reconciled history and a public site to be proud of. Here is how it sits next to the dedicated cricket-stats tools.',
    columns: [
      { key: 'clubstats', name: 'ClubStats', tag: 'Stats site', sub: 'clubstats.cricket' },
      { key: 'cstatz', name: 'CricketStatz', tag: 'Stats software', sub: 'Long-running desktop package' },
      US_COL,
    ],
    sections: [
      {
        section: 'Data depth',
        rows: [
          { feature: 'Full career stats, every player', tip: 'Runs, wickets, averages across every season', values: { clubstats: true, cstatz: true, us: true } },
          { feature: 'Decades of historical archive', tip: 'Your whole history, not just recent seasons', values: { clubstats: 'partial', cstatz: 'manual', us: true } },
          { feature: 'Partnership records', values: { clubstats: 'partial', cstatz: true, us: true } },
          { feature: 'Head-to-head player splits', tip: 'How a player has performed versus every club they have played against', values: { clubstats: false, cstatz: 'partial', us: true } },
          { feature: 'Caught-behind & dismissal breakdowns', values: { clubstats: false, cstatz: 'partial', us: true } },
        ],
      },
      {
        section: 'Surface & presentation',
        rows: [
          { feature: 'Public, club-branded website', tip: 'Your own URL, your colours, your crest, your sponsors', values: { clubstats: 'partial', cstatz: false, us: true } },
          { feature: 'Mobile-first, modern design', values: { clubstats: 'partial', cstatz: false, us: true } },
          { feature: 'Auto-generated season yearbook', values: { clubstats: false, cstatz: false, us: true } },
          { feature: 'Shareable social stat cards', tip: 'One-tap export of branded Instagram / X cards', values: { clubstats: false, cstatz: false, us: true } },
        ],
      },
      {
        section: 'Setup & operations',
        rows: [
          { feature: 'Syncs automatically, no data entry', tip: 'Your match history flows in and keeps itself current', values: { clubstats: 'partial', cstatz: false, us: true } },
          { feature: 'Onboarding & migration included', values: { clubstats: false, cstatz: false, us: true } },
          { feature: 'Setup time', textRow: true, values: { clubstats: 'Days', cstatz: '2 to 4 weeks', us: 'Under 1 hour' } },
          { feature: 'Bolt-on club modules', tip: 'Selection, socials, admin and analytics on the same data', values: { clubstats: false, cstatz: false, us: true } },
        ],
      },
    ],
    cta: { line: "It is included in every plan. Get your club's history online in under an hour.", label: 'Get Your Club on BetterCricket today!', to: '/contact' },
  },

  // BetterSocials — vs design + website tools.
  bettersocials: {
    eyebrow: 'Compare',
    heading: 'The designer and website builder that already knows your cricket.',
    sub: 'BetterSocials turns your match data into share-ready posts and runs your public website, with the design and the typing already done for you.',
    columns: [
      { key: 'canva', name: 'Canva', tag: 'Design app', sub: 'Blank-canvas graphics' },
      { key: 'squarespace', name: 'Squarespace', tag: 'Website builder', sub: 'Generic site templates' },
      US_COL,
    ],
    sections: [
      {
        section: 'Match-day graphics',
        rows: [
          { feature: 'Cricket-native post templates', tip: 'Lineups, toss, player of the match, final score, full scorecard', values: { canva: 'manual', squarespace: false, us: true } },
          { feature: 'Auto-fill from your match data', tip: 'No retyping names and figures', values: { canva: false, squarespace: false, us: true } },
          { feature: 'Your crest, colours & display fonts by default', values: { canva: 'manual', squarespace: 'partial', us: true } },
          { feature: 'No design skills needed', values: { canva: false, squarespace: 'partial', us: true } },
          { feature: 'One-tap PNG export', values: { canva: true, squarespace: false, us: true } },
        ],
      },
      {
        section: 'Your club online',
        rows: [
          { feature: 'Public club website included', values: { canva: false, squarespace: true, us: true } },
          { feature: 'Live stats, profiles & ladders built in', tip: 'The website is wired to your match data', values: { canva: false, squarespace: false, us: true } },
          { feature: 'News, galleries, sponsors & honour boards', values: { canva: false, squarespace: true, us: true } },
          { feature: 'Per-club cost', textRow: true, values: { canva: '~$165/yr', squarespace: '~$300/yr', us: 'Included in Better' } },
        ],
      },
    ],
    cta: { line: 'One tool for the website and the posts, both fed by your cricket.', label: 'Explore BetterSocials →', to: '/modules/bettersocials' },
  },

  // BetterSelect — vs group chats + generic team apps.
  betterselect: {
    eyebrow: 'Compare',
    heading: 'Selection that already knows your players.',
    sub: "BetterSelect supports self-service player availability and suggests balanced XIs from form, grade, role and skills, because it is wired into your stats and player achievements across the club. It can optionally surface a player's fee status and net attendance to weigh up during selection.",
    columns: [
      { key: 'chats', name: 'Group chats & sheets', tag: 'The status quo', sub: 'WhatsApp / Facebook + a spreadsheet' },
      { key: 'teamapps', name: 'Generic team apps', tag: 'Availability tools', sub: 'Built for any sport' },
      US_COL,
    ],
    sections: [
      {
        section: 'Collecting availability',
        rows: [
          { feature: 'No player accounts or app install', tip: 'A magic link plus the last 4 of their phone', values: { chats: true, teamapps: false, us: true } },
          { feature: 'One grid for the whole squad', values: { chats: false, teamapps: true, us: true } },
          { feature: 'Players record availability for a range of matches at once', values: { chats: false, teamapps: 'partial', us: true } },
        ],
      },
      {
        section: 'Picking the side',
        rows: [
          { feature: 'Form-aware XI suggestions', tip: 'Ranks players by recent and season-to-date form', values: { chats: false, teamapps: false, us: true } },
          { feature: 'Grade, gender & squad-tier aware', values: { chats: false, teamapps: false, us: true } },
          { feature: 'Knows every player’s stats already', tip: 'No separate roster to maintain', values: { chats: false, teamapps: false, us: true } },
          { feature: 'Pick the XI on numbered batting slots', values: { chats: false, teamapps: false, us: true } },
          { feature: 'Live fixtures & grade ladders', values: { chats: false, teamapps: 'partial', us: true } },
        ],
      },
    ],
    cta: { line: 'Turn the weekly "who’s in?" scramble into a few taps.', label: 'Explore BetterSelect →', to: '/modules/betterselect' },
  },

  // BetterAdmin — the back office, vs email + fee/merch tooling.
  betteradmin: {
    eyebrow: 'Compare',
    heading: 'Your back office, on top of your member list.',
    sub: 'BetterAdmin runs fees, comms and merch off the same player database as your stats, so you are not exporting CSVs between an email tool, a spreadsheet and a payment app.',
    columns: [
      { key: 'mailchimp', name: 'Mailchimp', tag: 'Email tool', sub: 'Newsletters & lists' },
      { key: 'sheets', name: 'Spreadsheets & apps', tag: 'Fees / merch', sub: 'Manual tracking' },
      US_COL,
    ],
    sections: [
      {
        section: 'Money',
        rows: [
          { feature: 'Match fees that auto-allocate', tip: 'A payment settles games oldest-first; status is always correct', values: { mailchimp: false, sheets: 'manual', us: true } },
          { feature: 'Membership tiers & schedules', values: { mailchimp: false, sheets: 'manual', us: true } },
          { feature: 'Credit & waivers handled', values: { mailchimp: false, sheets: 'manual', us: true } },
          { feature: 'Merch stock & sales', tip: 'Coming soon', values: { mailchimp: false, sheets: 'manual', us: 'partial' } },
        ],
      },
      {
        section: 'Comms',
        rows: [
          { feature: 'Bulk email to your members', values: { mailchimp: true, sheets: false, us: true } },
          { feature: 'Contacts come from your player database', tip: 'No list to export and re-import', values: { mailchimp: false, sheets: false, us: true } },
          { feature: 'Spam-Act compliant unsubscribes', values: { mailchimp: true, sheets: false, us: true } },
          { feature: 'One back office, one bill', textRow: true, values: { mailchimp: '~$20+/mo', sheets: 'Free + your time', us: 'Included in Best' } },
        ],
      },
    ],
    cta: { line: 'Stop reconciling three tools every month.', label: 'Explore BetterAdmin →', to: '/modules/betteradmin' },
  },
}

// BetterIQ stands alone — there is no club-platform equivalent to compare it to.
export const COMPARISON_SOLO = {
  betteriq: {
    eyebrow: 'Category of one',
    heading: 'There’s nothing to compare BetterIQ to.',
    sub: 'No other club platform turns your own scorecards into an opposition dossier, a live selection brain and broadcast-grade team analysis. This is match prep most pro teams pay for, built from data you already have.',
    points: [
      'Opposition scouting, danger players and a printable captain’s cheat sheet for any upcoming opponent.',
      'A best-available XI that updates as availability changes, with balance warnings.',
      'Player trends, breakout and decline detection, and milestone forecasts.',
      'Team analysis by innings phase: partnerships, collapses, par scores, how you win and lose.',
    ],
    note: 'Built entirely from your synced scorecards, with no manual entry and no ball-by-ball scoring required.',
    cta: { line: 'The analyst your club never had.', label: 'Explore BetterIQ →', to: '/modules/betteriq' },
  },
}

// ============================================================
// SCREENSHOTS — where to put real images
// Match filenames in /public/marketing/ to swap mocks for screenshots.
// Each path is a fallback that pages check for; mocks display until present.
// ============================================================
export const SCREENSHOT_PATHS = {
  // Landing hero
  landingHeroCard:        '/marketing/hero-career-card.jpg',
  frontPageProfile:       '/marketing/front-page-profile.jpg',
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
  shortOpposition:        '/marketing/feature-opposition.jpg',
  shortGames:             '/marketing/feature-games.jpg',
  // Club branding & back office (sponsors/milestones used directly in the Core gallery)
  featuresWhitelabel:     '/marketing/feature-whitelabel.jpg',
  // About page
  aboutFounder:           '/marketing/founder.jpg',
}
