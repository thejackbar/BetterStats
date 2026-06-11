// Marketing copy + helpers for the Better Cricket module ecosystem.
//
// The platform is **Better Cricket** (from BetterSports). Every club gets the
// **Core (BetterStats)** — data ingestion, reconciled stats and the public club
// site — and bolts on the modules below. Public prices live in
// src/data/pricing.js (the modular pricing model + calculator).
//
// The bolt-ons mirror the in-app umbrella tiles: BetterSelect, BetterSocials
// (the post designer + the club website), BetterAdmin (the back office — fees,
// comms and merch) and BetterIQ.

import { MODULE } from '../lib/modules'
import { MODULE_BRAND as BRAND } from '../lib/moduleBrand'

// ── BetterStats — the always-on base module ─────────────────────────────────
// Required for every club and not separately gateable, but marketed as a module
// like the rest. Described here so the Modules hub can introduce it alongside
// the bolt-ons. Its deep feature tour lives on /features.
export const CORE_MARKETING = {
  slug: 'betterstats',
  name: 'BetterStats',
  isCore: true,
  icon: '◆',
  accent: BRAND.stats.accent,
  logo: BRAND.stats.logo,
  key: 'core',
  audience: 'The foundation · every club',
  compareKey: 'betterstats',
  tagline: 'Your club’s memory — every player, every season, kept forever.',
  // The standard module page; its deeper feature tour lives on /features.
  to: '/modules/betterstats',
  deepTour: '/features',
  summary:
    'BetterStats turns your club’s match data into a living history and a public site to be proud of. Connect once and every batting, bowling and fielding stat flows in on its own, reconciled across decades and ready as profiles, leaderboards, records, scorecards, yearbooks and shareable cards.',
  highlights: [
    'Your full match history, imported once',
    'Every stat reconciled and kept forever',
    'A public, club-branded website',
    'Profiles, leaderboards, records and yearbooks',
  ],
  features: [
    { title: 'Automatic stats sync', desc: 'Connect your club once and your whole match history is imported, then every new game flows in on its own. No data entry, no spreadsheets to maintain.' },
    { title: 'Reconciled across decades', desc: 'Names, teams and seasons are matched and de-duplicated, so a player’s whole career reads as one record, back to your earliest digitised season.' },
    { title: 'Rich player profiles', desc: 'Every player gets a profile with career and season batting, bowling and fielding, milestones, club rank badges and a photo.' },
    { title: 'Leaderboards and club records', desc: 'Live leaderboards and all-time records for runs, wickets, catches, partnerships and more, updated after every sync.' },
    { title: 'Scorecards and match archive', desc: 'Full match scorecards and a browsable archive of every game, straight from your synced data.' },
    { title: 'Season yearbooks', desc: 'Publish a polished yearbook for any season, with the standout performances and the year’s awards.' },
    { title: 'Awards and honour boards', desc: 'Record season awards and honour boards, shown on player profiles and across the club site.' },
    { title: 'Shareable stat cards', desc: 'Every player has a clean, club-branded stat card, one tap to share on Instagram, Facebook or X.' },
  ],
  note: 'BetterStats is the base every club runs on. BetterSelect, BetterSocials, BetterAdmin and BetterIQ all bolt straight onto the same data.',
  screenshot: '/marketing/player-profile.jpg',
  gallery: [
    { src: '/marketing/leaderboard.jpg', caption: 'Live club leaderboards' },
    { src: '/marketing/yearbook.jpg', caption: 'Auto-generated season yearbooks' },
    { src: '/marketing/showcase-scorecard.jpg', caption: 'Full match scorecards' },
    { src: '/marketing/hero-career-card.jpg', caption: 'Shareable player stat cards' },
    { src: '/marketing/feature-opposition.jpg', caption: 'Per-player opposition analysis' },
    { src: '/marketing/feature-games.jpg', caption: 'A browsable match archive' },
    { src: '/marketing/feature-whitelabel.jpg', caption: "Make the public site your club's own" },
    { src: '/marketing/feature-sponsors.jpg', caption: 'Your sponsors across the site' },
    { src: '/marketing/feature-milestones.jpg', caption: 'A milestone tracker for the whole club' },
  ],
}

// Showcase image for the Modules hub hero.
export const HUB_SHOWCASE = '/marketing/modules/better-modules.jpg'

// ── Bolt-on modules ─────────────────────────────────────────────────────────
export const MODULES_MARKETING = [
  {
    slug: 'betterselect',
    key: MODULE.SELECT,
    name: 'BetterSelect',
    icon: '◎',
    accent: BRAND.select.accent,
    logo: BRAND.select.logo,
    audience: 'For captains & selectors',
    compareKey: 'betterselect',
    tagline: 'Availability and team selection, sorted for every grade in minutes.',
    summary:
      'BetterSelect handles the weekly “who’s in?” across every grade at once. Players set their own availability from a link without creating an account, you build squads and name each XI on a numbered batting order, and form- and grade-aware suggestions help you land on a balanced side. Fixtures, ladders and Thursday net sessions sit in the same place, in your club’s colours.',
    highlights: [
      'Availability with no player logins',
      'Drag-and-drop squad boards',
      'Form- and grade-aware selection',
      'Net session timer and live ladders',
    ],
    features: [
      { title: 'Match-day overview', desc: 'A weekend snapshot for every team: who is available, who has not replied yet, and which keeper or selection still needs a chase.' },
      { title: 'Availability, set in a tap', desc: 'Mark players in, out or maybe across every fixture, or set someone available over a whole date range in one go. Tapping a status saves on the spot.' },
      { title: 'A link players answer themselves', desc: 'Players set their own availability from one club link and a four-digit PIN. Share it by QR code or in the team group chat; a player opens it, taps their PIN and sets their weekend in a few seconds.' },
      { title: 'Squad boards', desc: 'Drag players between squads, one for each grade. Auto-seed from last season or auto-assign by grade to start, then move people by hand.' },
      { title: 'Smart selection', desc: 'Pick on a numbered batting order or a dual rail of pool and XI. Each player carries a form read from hot to cold, and autofill or last week’s side gives you a starting point.' },
      { title: 'Captain, keeper and balance', desc: 'Set the captain and keeper, watch the bat, bowl and keeper mix update as you go, and choose your lineup size. Selection flags a side with no keeper or a short attack.' },
      { title: 'Every team in one view', desc: 'All your upcoming XIs in one list, each marked not started, in progress, ready or needs attention, so nothing gets missed on a busy weekend.' },
      { title: 'Net sessions', desc: 'Run Thursday nets off a rotation timer. Check players in, set the nets and minutes, and it rolls the next group and pings the batters who are up.' },
      { title: 'Fixtures and ladders', desc: 'Your fixtures grouped by round and synced from the association, plus live grade ladders for every team.' },
      { title: 'A card for every player', desc: 'Role, batting and bowling, recent form, availability for the next month and net attendance, all on one editable player card.' },
    ],
    note: 'BetterSelect runs off the same player database as your stats, so your squads, form reads and profiles stay current without exporting anything between tools.',
    screenshot: '/marketing/modules/betterselect-selection.jpg',
    gallery: [
      { src: '/marketing/modules/betterselect-overview.jpg', caption: 'Match-day overview for every team' },
      { src: '/marketing/modules/betterselect-selection-overview.jpg', caption: 'Every weekend XI, with a status on each' },
      { src: '/marketing/modules/betterselect-team-sheet.jpg', caption: 'Name the order, captain and keeper on one team sheet' },
      { src: '/marketing/modules/betterselect-availability.jpg', caption: 'Availability across every fixture at a glance' },
      { src: '/marketing/modules/betterselect-self-service.jpg', caption: 'A self-service link players open with a PIN' },
      { src: '/marketing/modules/betterselect-squads.jpg', caption: 'Drag players between squad boards' },
      { src: '/marketing/modules/betterselect-players.jpg', caption: 'A player card with form, availability and net attendance' },
      { src: '/marketing/modules/betterselect-nets.jpg', caption: 'A net session timer that rolls the batting order' },
      { src: '/marketing/modules/betterselect-fixtures.jpg', caption: 'Fixtures grouped by round, synced from the association' },
      { src: '/marketing/modules/betterselect-ladders.jpg', caption: 'Live grade ladders for every team' },
    ],
  },
  {
    slug: 'bettersocials',
    key: MODULE.SOCIALS,
    name: 'BetterSocials',
    icon: '◈',
    accent: BRAND.socials.accent,
    logo: BRAND.socials.logo,
    audience: 'For the social-media manager',
    compareKey: 'bettersocials',
    tagline: 'Your public website plus match-day posts your community actually reposts.',
    summary:
      'BetterSocials runs your club’s public website and a post designer that turns your match data into share-ready graphics — lineups, announcements, player-of-the-match, scorecards and more. Pick a layout, and your scorecard fills itself from your own data. Download a crisp PNG.',
    highlights: [
      'Your public, club-branded website',
      'Lineups, announcements, scorecards & POTM',
      'Scorecards auto-fill from your match data',
      'Your club colours, crest & display fonts',
    ],
    features: [
      { title: 'Your club website', desc: 'A fast, modern, club-branded public site — news, galleries, sponsors, honour boards and your live stats, all in one place.' },
      { title: 'Six post types', desc: 'Lineup, announcement, toss, player of the match, final score and a full match scorecard — one designer for the whole match day.' },
      { title: 'A layout for every post', desc: 'Multiple designs per type — hero lineups, trading-card grids, side-numbered XIs, broadcast or app-style scorecards, festival posters and more.' },
      { title: 'Auto-fill from the match', desc: 'Your scorecard fills itself from your own synced match data — no retyping names and figures.' },
      { title: 'On-brand by default', desc: 'Your crest and club colours, a choice of display fonts, and a dark or light finish.' },
      { title: 'One-tap export', desc: 'Download a crisp PNG, ready to post to Instagram, Facebook or X.' },
    ],
    comingSoon: ['Scheduled & auto-posting after a result', 'Auto-generated match summaries'],
    screenshot: '/marketing/modules/bettersocials-lineup-3.jpg',
    gallery: [
      { src: '/marketing/modules/bettersocials-announcement.jpg', caption: 'Appointment & announcement cards' },
      { src: '/marketing/modules/bettersocials-potm.jpg', caption: 'Player-of-the-match spotlight' },
      { src: '/marketing/modules/bettersocials-scorecard-1.jpg', caption: 'Broadcast scorecard, auto-filled from your match data' },
      { src: '/marketing/modules/bettersocials-scorecard-3.jpg', caption: 'Scorecard — app-style dashboard layout' },
      { src: '/marketing/modules/bettersocials-lineup-1.jpg', caption: 'Team lineup — hero layout' },
      { src: '/marketing/modules/bettersocials-lineup-3b.jpg', caption: 'Team lineup — side-numbered' },
    ],
  },
  {
    slug: 'betteradmin',
    key: 'admin',
    name: 'BetterAdmin',
    icon: '◉',
    accent: BRAND.admin.accent,
    logo: BRAND.admin.logo,
    audience: 'For the treasurer & secretary',
    compareKey: 'betteradmin',
    tagline: 'Run the back office — fees, comms and merch in one place.',
    summary:
      'BetterAdmin is your club’s back office on top of your member list. Auto-allocating match fees, membership, bulk email to your members and merch tracking — all working off the same player database as your stats, so nothing needs exporting between tools.',
    members: ['BetterFees', 'BetterComms', 'BetterMerch (soon)'],
    highlights: [
      'Auto-allocating match-fee payments',
      'Live Paid / Part-paid / Unpaid',
      'Bulk email to your member database',
      'Merch stock & sales (coming soon)',
    ],
    features: [
      { title: 'Automatic fee allocation', desc: 'A recorded payment settles games oldest-first, in full while the money lasts; the boundary game shows part-paid. Edit days played and it re-allocates itself.' },
      { title: 'Always-correct status', desc: 'Per-game Paid / Part-paid / Unpaid is derived on read — there’s no stale flag to keep in sync.' },
      { title: 'Credit & waivers', desc: 'Overpay and the balance rolls forward as credit; waive a match-day fee with a note. Membership and match-fee buckets stay separate.' },
      { title: 'Membership & schedules', desc: 'Set membership tiers and match-day fee schedules per season, with clean financial reports for the committee.' },
      { title: 'Bulk email (BetterComms)', desc: 'Newsletters and announcements to your member database — contacts come straight from your players, with Spam-Act-compliant unsubscribes.' },
      { title: 'Merch (coming soon)', desc: 'Track merchandise stock and sales alongside the rest of the back office.' },
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
    icon: '◇',
    accent: BRAND.iq.accent,
    logo: BRAND.iq.logo,
    audience: 'For the coach & captain',
    compareKey: 'betteriq',
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
  if (slug === CORE_MARKETING.slug) return CORE_MARKETING
  return MODULES_MARKETING.find((m) => m.slug === slug) || null
}
