// Marketing copy + helpers for the Better module ecosystem.
//
// The platform is **Better**. Every club gets the **Core (BetterStats)** — data
// ingestion, reconciled stats and the public club site — and bolts on the
// modules below. Prices live in src/lib/modules.js (TIER_INFO) so the public
// pages and the in-app entitlement system never drift apart.

import { MODULE, TIER, TIER_INFO, TIER_ORDER } from '../lib/modules'

// ── The Core (sold as the "Good" tier) ──────────────────────────────────────
// Not a gateable module, but described here so the Modules hub can introduce it
// alongside the bolt-ons. Its deep feature tour lives on /features.
export const CORE_MARKETING = {
  slug: 'betterstats',
  name: 'BetterStats',
  isCore: true,
  tier: TIER.GOOD,
  icon: '◆',
  accent: '#34d399',
  tagline: 'Your club’s memory — every player, every season, kept forever.',
  to: '/features',
}

// Showcase image for the Modules hub hero (the uploaded "Better Modules" shot).
export const HUB_SHOWCASE = '/marketing/modules/better-modules.jpg'

// ── Bolt-on modules ─────────────────────────────────────────────────────────
export const MODULES_MARKETING = [
  {
    slug: 'betterselect',
    key: MODULE.SELECT,
    name: 'BetterSelect',
    tier: TIER.BETTER,
    icon: '◎',
    accent: '#34d399',
    audience: 'For captains & selectors',
    tagline: 'Availability and smart team selection — sort your weekend XI in minutes.',
    summary:
      'BetterSelect turns the weekly “who’s in?” scramble into a few taps. Collect availability, build squads, and let form- and grade-aware autofill suggest your best-balanced side — all in your club’s colours.',
    highlights: [
      'Availability with whole date-range periods',
      'Drag-and-drop squad boards',
      'Form-, grade- and gender-aware autofill',
      'Pick the XI on numbered batting slots',
    ],
    features: [
      { title: 'Availability tracking', desc: 'Players mark themselves in or out, and you can set someone available or unavailable across a whole date range in one go.' },
      { title: 'Squad boards', desc: 'Drag and drop players into selection pools that feed the autofill suggestions.' },
      { title: 'Smart autofill', desc: 'Ranks players by a composite form score (recent + season-to-date), respects grade and gender boundaries, and tiers by squad with a 12-month activity wall.' },
      { title: 'Pick the XI', desc: 'Name your side on numbered batting-order slots, with a suggestion for every position.' },
      { title: 'Fixtures & ladders', desc: 'Your weekend fixtures grouped by round, plus live grade ladders.' },
      { title: 'One filter bar everywhere', desc: 'Search, multi-select filters and removable chips on every screen — stored in the URL, so a view is shareable and survives the back button.' },
      { title: 'Wears your colours', desc: 'BetterSelect uses your accent colour, crest and club name, and remembers your default lineup size.' },
    ],
    screenshot: '/marketing/modules/betterselect-selection.jpg',
    gallery: [
      { src: '/marketing/modules/betterselect-squads.jpg', caption: 'Drag-and-drop squad boards' },
      { src: '/marketing/modules/betterselect-availability.jpg', caption: 'Availability grid with date-range periods' },
      { src: '/marketing/modules/betterselect-player-profiles.jpg', caption: 'Rich, shared player profiles' },
    ],
  },
  {
    slug: 'bettersocials',
    key: MODULE.SOCIALS,
    name: 'BetterSocials',
    tier: TIER.BETTER,
    icon: '◈',
    accent: '#38bdf8',
    audience: 'For the social-media manager',
    tagline: 'Turn match data into posts your community actually reposts.',
    summary:
      'A club-branded post designer that turns your match data into share-ready graphics — lineups, announcements, player-of-the-match, scorecards and more. Paste a PlayCricket link to auto-fill a scorecard, pick a layout, and download a crisp PNG.',
    highlights: [
      'Lineups, announcements, scorecards & POTM',
      'Auto-fill scorecards from PlayCricket',
      'Your club colours, crest & display fonts',
      'One-tap PNG download',
    ],
    features: [
      { title: 'Six post types', desc: 'Lineup, announcement, toss, player of the match, final score and a full match scorecard — one designer for the whole match day.' },
      { title: 'A layout for every post', desc: 'Multiple designs per type — hero lineups, trading-card grids, side-numbered XIs, broadcast or app-style scorecards, festival posters and more.' },
      { title: 'Auto-fill from the match', desc: 'Paste a PlayCricket match link and the scorecard fills itself — no retyping names and figures.' },
      { title: 'On-brand by default', desc: 'Your crest and club colours, a choice of display fonts, and a dark or light finish.' },
      { title: 'One-tap export', desc: 'Download a crisp PNG, ready to post to Instagram, Facebook or X.' },
    ],
    comingSoon: ['Scheduled & auto-posting after a result', 'Auto-generated match summaries'],
    screenshot: '/marketing/modules/bettersocials-lineup-3.jpg',
    gallery: [
      { src: '/marketing/modules/bettersocials-announcement.jpg', caption: 'Appointment & announcement cards' },
      { src: '/marketing/modules/bettersocials-potm.jpg', caption: 'Player-of-the-match spotlight' },
      { src: '/marketing/modules/bettersocials-scorecard-1.jpg', caption: 'Broadcast scorecard, auto-filled from PlayCricket' },
      { src: '/marketing/modules/bettersocials-scorecard-3.jpg', caption: 'Scorecard — app-style dashboard layout' },
      { src: '/marketing/modules/bettersocials-lineup-1.jpg', caption: 'Team lineup — hero layout' },
      { src: '/marketing/modules/bettersocials-lineup-3b.jpg', caption: 'Team lineup — side-numbered' },
    ],
  },
  {
    slug: 'betterfees',
    key: MODULE.FEES,
    name: 'BetterFees',
    tier: TIER.BEST,
    icon: '◉',
    accent: '#fbbf24',
    audience: 'For the treasurer',
    tagline: 'Match fees and membership, finally under control.',
    summary:
      'Record a payment and BetterFees settles a member’s games automatically — oldest first — and keeps a live, always-correct picture of who’s paid, who’s part-paid and who still owes.',
    highlights: [
      'Auto-allocating match-fee payments',
      'Live Paid / Part-paid / Unpaid',
      'Overpayments roll forward as credit',
      'Waive a fee with a note',
    ],
    features: [
      { title: 'Automatic allocation', desc: 'A recorded payment settles games oldest-first, in full while the money lasts; the boundary game shows part-paid. Edit days played and it re-allocates itself.' },
      { title: 'Always-correct status', desc: 'Per-game Paid / Part-paid / Unpaid is derived on read — there’s no stale flag to keep in sync.' },
      { title: 'Credit tracking', desc: 'Overpay and the balance rolls forward as credit; membership and match-fee buckets stay separate.' },
      { title: 'Waivers', desc: 'Waive a match-day fee with an optional note; it settles immediately and stays out of payment totals.' },
      { title: 'Membership & schedules', desc: 'Set membership tiers and match-day fee schedules per season.' },
      { title: 'Bulk & import', desc: 'Record payments in bulk, or import them straight from a CSV.' },
      { title: 'Financial reports', desc: 'A clean summary with waived totals and a per-tier breakdown for the committee.' },
    ],
    screenshot: '/marketing/modules/betterfees-player-payments.jpg',
    gallery: [
      { src: '/marketing/modules/betterfees-structure.jpg', caption: 'Fee schedules & membership tiers' },
      { src: '/marketing/modules/betterfees-reports.jpg', caption: 'Financial reports with waived totals' },
    ],
  },
  {
    slug: 'betteriq',
    key: MODULE.IQ,
    name: 'BetterIQ',
    tier: TIER.BEST,
    icon: '◇',
    accent: '#a78bfa',
    audience: 'For the coach & captain',
    tagline: 'Broadcast-grade analytics and an opposition scout for your club.',
    summary:
      'BetterIQ reads your own scorecards — no extra data entry — and turns them into an opposition dossier, a live selection brain and deep player and team analysis. The kind of match prep most pro teams pay for.',
    highlights: [
      'Opposition scouting & cheat sheet',
      'Live best-available XI',
      'Player trends & deep dives',
      'Team analysis by innings phase',
    ],
    features: [
      { title: 'Scout the opposition', desc: 'Danger batters and bowlers, recent form, head-to-head history and a rule-based game plan for any upcoming opponent.' },
      { title: 'Opposition players', desc: 'Per-player profiles with wagon wheels, radars, editable scouting tags and their record against you.' },
      { title: 'Match preview & cheat sheet', desc: 'A lean match preview, plus a print-ready captain’s cheat sheet for the car park.' },
      { title: 'Live selection', desc: 'A best-available XI that updates as availability changes, with balance warnings — and it syncs with BetterSelect.' },
      { title: 'Player trends', desc: 'Season-by-season trajectories, breakout and decline detection, milestone forecasts and per-player deep dives.' },
      { title: 'Team analysis', desc: 'Batting, bowling and fielding profiles, partnerships, collapses, par scores and how-you-win/lose — filterable by season and grade.' },
      { title: 'Match review', desc: 'A post-match breakdown of what actually changed the game.' },
      { title: 'Innings phases', desc: 'Powerplay / Middle / Death splits, radars, gauges and wagon wheels — a full broadcast-style viz kit.' },
    ],
    note: 'Built entirely from your synced scorecards — no manual entry and no ball-by-ball scoring required.',
    screenshot: '/marketing/modules/betteriq-overview.jpg',
    gallery: [
      { src: '/marketing/modules/betteriq-opposition-analysis.jpg', caption: 'Opposition scouting dossier' },
      { src: '/marketing/modules/betteriq-danger-players.jpg', caption: 'Danger-player cards' },
      { src: '/marketing/modules/betteriq-how-to-beat-them.jpg', caption: 'How to beat them — game plan' },
      { src: '/marketing/modules/betteriq-how-they-win-lose.jpg', caption: 'How they win & lose' },
      { src: '/marketing/modules/betteriq-selection-analysis.jpg', caption: 'Live best-available XI' },
      { src: '/marketing/modules/betteriq-team-analysis.jpg', caption: 'Team analysis' },
      { src: '/marketing/modules/betteriq-team-batting-analysis.jpg', caption: 'Team batting analysis' },
    ],
  },
]

export function moduleBySlug(slug) {
  return MODULES_MARKETING.find((m) => m.slug === slug) || null
}

const tierIndex = (tier) => Math.max(0, TIER_ORDER.indexOf(tier))

// The lowest tier that unlocks every module in `selectedKeys`.
// No modules selected → Good (Core only).
export function requiredTierForModules(selectedKeys) {
  let idx = 0
  for (const key of selectedKeys || []) {
    const m = MODULES_MARKETING.find((x) => x.key === key)
    if (m) idx = Math.max(idx, tierIndex(m.tier))
  }
  return TIER_ORDER[idx]
}

// The modules a tier bundles (drives the tier cards on /pricing).
export function modulesInTier(tier) {
  const ti = tierIndex(tier)
  return MODULES_MARKETING.filter((m) => tierIndex(m.tier) <= ti)
}

export { TIER, TIER_INFO, TIER_ORDER }
