// Feature changelog — newest first.
// Frontend reads this to determine "What's New" since the user's last seen version.
// Add an entry whenever SITE_VERSION is bumped in src/version.js.

export const CHANGELOG = [
  {
    version: 'v7.8.5',
    date: '2026-05-25',
    title: 'Mobile layout — Scorecards, StatLab, Yearbook & Forms',
    items: [
      'Match Scorecard hero (Home / Result / Away strip) now fits on 390px-wide phones — scores and team names scale down on mobile so 3-digit totals no longer overflow the column',
      'StatLab target tabs use horizontal scroll instead of flex-wrap (avoids the underline-indicator misalignment that wrap causes)',
      'Yearbook hero callouts (Players · Runs · Wickets · Record · Win Rate) shrink from text-5xl to text-3xl on mobile so "21W 5D 6L" no longer overflows',
      'Yearbook "By the Numbers" stat groups: 2 columns on mobile (was 4) — labels and values now have breathing room',
      'Yearbook tab strip picks up the pb-no-scrollbar treatment for clean horizontal scroll',
      'iOS form auto-zoom fix: inputs, selects and textareas now render at 16px on touch devices, so tapping a login field, search box or modal input no longer triggers a jarring zoom',
    ],
  },
  {
    version: 'v7.8.4',
    date: '2026-05-25',
    title: 'Mobile layout — Player Profile & Compare',
    items: [
      'All tab bars (Records, PlayerProfile, Analysis sub-tabs, Comparison) now scroll horizontally on mobile instead of overflowing — avoids the broken-indicator bug that flex-wrap would cause',
      'Player Comparison: search box goes full-width on mobile, "Filter" label hidden on mobile to give filter chips more room',
    ],
  },
  {
    version: 'v7.8.3',
    date: '2026-05-25',
    title: 'Mobile layout — Leaderboard & Records',
    items: [
      'Records tab bar (Batting / Bowling / Partnerships / All-Rounders / Team) now wraps on narrow screens instead of overflowing',
      'Grade filter label hidden on mobile across Leaderboard and Records — only the dropdown shows, saving horizontal space',
    ],
  },
  {
    version: 'v7.8.2',
    date: '2026-05-25',
    title: 'Mobile layout polish',
    items: [
      'Players page search bar now takes full width on mobile before filters wrap below it',
      'Season/Grade/Gender/Games/Captain filter labels hidden on mobile — controls are self-descriptive and the space goes back to the chips',
      'Navbar version badge now correctly tracks the live version (re-export fix)',
    ],
  },
  {
    version: 'v7.8',
    date: '2026-05-25',
    title: 'SEO & AEO Discoverability Overhaul',
    items: [
      'New /faq page with structured FAQ schema — answers the questions clubs and AI assistants ask about BetterStats',
      'Dynamic XML sitemap at /sitemap.xml covering marketing pages, every active club section, and every player profile',
      'robots.txt published with a clear allow policy plus the sitemap pointer',
      'Per-route titles, descriptions and canonical URLs on every marketing and club page — Google now sees a different page for each route',
      'JSON-LD structured data added: Organization, SoftwareApplication, Product/Offer (pricing), FAQPage (faq), SportsTeam (clubs) and Person (players)',
      'Search-engine crawlers (Googlebot, bingbot) now get the real SPA — previously they were silently routed to the empty OG-preview shell',
      'Social previews (Facebook, X, LinkedIn, Slack, WhatsApp) keep the per-route OG-preview path and now include canonical + JSON-LD too',
      'Favicon, theme-color and twitter summary_large_image card added',
    ],
  },
  {
    version: 'v7.7.3',
    date: '2026-05-24',
    title: 'Notification Centre',
    items: [
      'Bell icon in the admin header shows upcoming milestones, sync results, and pending requests at a glance',
      'What\'s New panel highlights features shipped since your last login',
      'Notifications auto-clear when you dismiss the panel',
    ],
  },
  {
    version: 'v7.7.2',
    date: '2026-05-22',
    title: 'Sync & Data Quality Fixes',
    items: [
      'Hard Rebuild now correctly marks sync runs as completed (was stuck at "running" forever)',
      'Absent and Did Not Bat dismissals no longer counted as batting innings — fixes inflated per-game innings counts',
      'Merge history now resolves multi-step redirects correctly — stats no longer silently drop for merged players',
      'Aggregate sync merge map filtered to active (non-undone) merges only — fixes poisoned redirects from reversed merges',
    ],
  },
  {
    version: 'v7.7',
    date: '2026-05-20',
    title: 'Full Historical Game Data',
    items: [
      'Game-level scorecards now load all the way back to the 1970s — every season, every grade',
      'Home and away team names now correctly populate for all historical games',
      'Duplicate batting/bowling rows from overlapping sync paths eliminated',
      'PlayHQ Partner sync path removed — Grassroots covers all seasons including 2025/26 with fewer gaps',
      'Player stats from scorecards now correctly attributed through merged player IDs',
    ],
  },
]
