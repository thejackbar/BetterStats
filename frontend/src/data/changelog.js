// Feature changelog — newest first.
// Frontend reads this to determine "What's New" since the user's last seen version.
// Add an entry whenever SITE_VERSION is bumped in src/version.js.

export const CHANGELOG = [
  {
    version: 'v7.12.1',
    date: '2026-05-25',
    title: 'Wire up the missing notification bell',
    items: [
      'The bell icon + notification panel was built in v7.7.3 but never actually rendered in the admin header. Fixed: bell now appears top-right of every admin page, polls every 60s, auto-opens after login when there are unseen items, and writes "seen" timestamp on close',
    ],
  },
  {
    version: 'v7.12',
    date: '2026-05-25',
    title: 'Finer-grained admin roles + Club Users page',
    items: [
      'New Admin → Users page lets a club Main Admin invite club members and toggle 11 fine-grained capabilities per user: settings, players, merges, yearbooks, awards, sponsors, social posts, milestones, run sync, run hard refresh, manage users',
      'Existing club_admin users keep full access (treated as "Main Admin" — all capabilities implicit). New "club_member" role gets only what is explicitly granted',
      'Sensitive endpoints now enforce capabilities server-side (merges, settings, logo upload, sync, hard refresh, user management). The nav hides links a user can\'t use',
      'Audit log records user-management actions too (create / update / remove)',
    ],
  },
  {
    version: 'v7.11',
    date: '2026-05-25',
    title: 'Activity Log + form validation polish',
    items: [
      'New Admin → Activity Log page records every sensitive admin action — player merges (and undo), grade merges, season merges, settings changes — with who did it, when, and what changed. Append-only; useful for diagnosing "wait, where did that come from?" moments',
      'Image uploads (club logo, player photo, sponsor logo) now fail fast on the client with a clear error when the file is too big or the wrong format — no more 30-second upload + cryptic 400 from the server',
      'CSV / XLSX imports (achievements, partnership records) get the same pre-flight checks: format + 5 MB cap with a helpful message',
      'AdminSettings save status now shows in red when something failed instead of the default accent green — was previously indistinguishable from a success',
    ],
  },
  {
    version: 'v7.10',
    date: '2026-05-25',
    title: 'Sync-failure alerts + rate limiting on expensive endpoints',
    items: [
      'Bell icon turns red when any scheduled sync has failed since your last visit. The notification panel now shows a "Sync Failures" callout at the top with the latest error and a one-click jump to Admin → Sync',
      'Rate limits: Hard Refresh is capped at 1 per hour per club, narrative generation at 5 per hour per club. Server returns 429 with a Retry-After header if exceeded — protects against accidental button-mashing and runaway costs',
    ],
  },
  {
    version: 'v7.9.1',
    date: '2026-05-25',
    title: 'Merge Seasons — long-tail coverage (yearbook, statlab, achievements)',
    items: [
      'Yearbook stats roll up correctly when viewing a merged season — picking "2025/26" in a yearbook now shows the combined Summer+Winter overview, batting/bowling/fielding leaders, partnerships, etc.',
      'StatLab queries with a season filter now include any aliased seasons in the result set — custom queries respect merges the same way leaderboards already do',
      'Achievements list filtered by season now also surfaces achievements recorded under merged-away variants of that season',
    ],
  },
  {
    version: 'v7.9',
    date: '2026-05-25',
    title: 'Merge Seasons — combine split-year seasons into one',
    items: [
      'Admin → Seasons has a new "Merge Seasons" tool. Pick a variant (e.g. "Summer 2025/26"), pick the canonical to keep ("2025/26"), merge. The variant is hidden from the public season dropdown and its stats roll up into the canonical everywhere — leaderboards, player profiles, career stats, records page',
      'Soft merge: no rows are rewritten, the per-season data stays exactly where it is, the merge is a thin alias mapping. Fully reversible from the Merge History panel — undo and the variant reappears with all stats intact',
      'Player profile season-by-season now collapses merged seasons into a single row with summed counts and recomputed averages, so "2025/26" shows one combined row instead of two rows for Summer/Winter',
    ],
  },
  {
    version: 'v7.8.7',
    date: '2026-05-25',
    title: 'Share Card — mobile-friendly + fielding peers batting/bowling',
    items: [
      'Share Card now fills the viewport on mobile up to a 600px max — the whole card fits in a phone screenshot instead of being clipped at 600px',
      'Fielding section is now a 4-column grid (Ct · Ct WK · RO · Stumps) matching the bowling layout — fielding sits at the same visual weight as batting and bowling',
      'Player name, padding, photo, stat font sizes scale down on screens narrower than 640px so the card stays readable without overflowing',
    ],
  },
  {
    version: 'v7.8.6',
    date: '2026-05-25',
    title: 'Hotfix — blank pages',
    items: [
      'Navbar.jsx was re-exporting SITE_VERSION from version.js but not importing it locally, so the JSX reference threw a ReferenceError and crashed every page that mounts the navbar. Now imports and re-exports.',
    ],
  },
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
