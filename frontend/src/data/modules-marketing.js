// Marketing copy + helpers for the BetterCricket module ecosystem.
//
// The platform is **BetterCricket** (from BetterSports). Every club gets the
// **Core (BetterStats)** — data ingestion, reconciled stats and the public club
// site — and bolts on the modules below. Public prices live in
// src/data/pricing.js (the modular pricing model + calculator).
//
// The bolt-ons mirror the in-app umbrella tiles: BetterSelect, BetterSocials
// (the post designer + the club website), BetterAdmin (the back office — the
// member directory, fees, comms, merch, volunteers and the committee) and
// BetterIQ. BetterFantasyCricket is a standalone add-on too
// (a club fantasy game scored off your real games), priced on its own in
// pricing.js rather than in the module bundle.

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
    'A public, club-branded stats site',
    'Profiles, leaderboards, records and yearbooks',
  ],
  features: [
    { title: 'Automatic stats sync', desc: 'Connect your club once and your whole match history is imported, then every new game flows in on its own. No data entry, no spreadsheets to maintain.' },
    { title: 'Reconciled across decades', desc: 'Names, teams and seasons are matched and de-duplicated, so a player’s whole career reads as one record, back to your earliest digitised season.' },
    { title: 'Rich player profiles', desc: 'Every player gets a profile with career and season batting, bowling and fielding, milestones, club rank badges and a photo.' },
    { title: 'Leaderboards and club records', desc: 'Live leaderboards and all-time records for runs, wickets, catches, partnerships and more, updated after every sync.' },
    { title: 'Junior grades kept out of senior careers', desc: 'An Under-14 season no longer flatters a senior batting average. Set which grades count towards your club’s figures once, then add juniors, women’s, masters or mixed cricket back in with one tap on any page. A player who has only ever played juniors still opens on their own numbers rather than a page of zeros.' },
    { title: 'Scorecards and match archive', desc: 'Full match scorecards and a browsable archive of every game, straight from your synced data.' },
    { title: 'Season yearbooks', desc: 'Publish a polished yearbook for any season, with the standout performances and the year’s awards.' },
    { title: 'Awards and honour boards', desc: 'Record season awards and honour boards, shown on player profiles and across the club site.' },
    { title: 'Shareable stat cards', desc: 'Every player has a clean, club-branded stat card, one tap to share on Instagram, Facebook or X.' },
  ],
  note: 'BetterStats is the base every club runs on. BetterSelect, BetterSocials, BetterAdmin and BetterIQ all bolt straight onto the same data.',
  screenshot: '/marketing/hero-career-card.jpg',
  // The best four screens, each with a proper write-up. Shown as full
  // text-beside-screenshot sections on the module page; everything else
  // stays in `gallery` below.
  showcase: [
    {
      src: '/marketing/leaderboard.jpg',
      headline: 'Build your own table.',
      body: 'StatLab is a query builder over everything your club has ever recorded. Start from one of 200+ pre-built reports or build your own, sort any of 30+ columns, and save the view once you like it.',
      points: [
        '200+ pre-built reports',
        '30+ sortable columns',
        'Filter by grade, format, opponent or decade',
        'Save reports and export CSV',
      ],
    },
    {
      src: '/marketing/showcase-scorecard.jpg',
      headline: 'Every scorecard, kept for good.',
      body: 'The full card for every synced match: both innings, every dismissal, extras and the result. A 1996 8th-grade game sits in the archive the same way last Saturday does.',
      points: [
        'Batting and bowling for both sides',
        'Dismissals, extras and run rates',
        'Linked from player profiles and yearbooks',
        'Back to your earliest digitised season',
      ],
    },
    {
      src: '/marketing/yearbook.jpg',
      headline: 'A season annual that writes itself.',
      body: 'Pick a season and the yearbook fills itself with the record, the leaders, the awards and the games that decided it. Share the link with members or print it for presentation night.',
      points: [
        "Auto-filled from the season's stats",
        'Honours, awards and top performers',
        'Print-ready layout',
        'A permanent URL for every year',
      ],
    },
    {
      src: '/marketing/player-profile.jpg',
      headline: 'The honour board, off the clubhouse wall.',
      body: "Hall of fame inductions, life memberships, cap numbers, captaincies and every named award, recorded once and kept on the player's profile.",
      points: [
        'Hall of fame and life membership',
        'Cap and player numbers',
        'Committee roles and captaincies',
        'Club and association awards, season by season',
      ],
    },
  ],
  gallery: [
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
      'BetterSelect handles the weekly “who’s in?” across every grade at once. Players set their own availability from a link without creating an account, you build squads and name each XI on a numbered batting order, and form- and grade-aware suggestions help you land on a balanced side. Fixtures, ladders, Thursday net sessions and the season’s best-player votes all sit in the same place, in your club’s colours.',
    highlights: [
      'Availability with no player logins',
      'Drag-and-drop squad boards',
      'Form- and grade-aware selection',
      'Best-player votes, counted for you',
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
      { title: 'Best-player votes', desc: 'Collect 3-2-1 votes after every game from the same link players already use, and the count keeps itself. You set who votes, what each ballot is worth and how ties break.' },
      { title: 'The count, round by round', desc: 'A season leaderboard with every player’s points, their 3s, 2s and 1s, how they have moved since last round and a race chart across the top five. Read it for the whole club or one grade at a time.' },
      { title: 'Presentation mode', desc: 'Put the count on the screen at the awards night and reveal it a round at a time, so the room follows the run home instead of reading the winner off a spreadsheet.' },
      { title: 'Net sessions', desc: 'Run Thursday nets off a rotation timer. Check players in, set the nets and minutes, and it rolls the next group and pings the batters who are up.' },
      { title: 'Fixtures and ladders', desc: 'Your fixtures grouped by round and synced from the association, plus live grade ladders for every team.' },
      { title: 'A card for every player', desc: 'Role, batting and bowling, recent form, availability for the next month and net attendance, all on one editable player card.' },
    ],
    note: 'BetterSelect runs off the same player database as your stats, so your squads, form reads and profiles stay current without exporting anything between tools.',
    screenshot: '/marketing/modules/betterselect-selection.jpg',
    showcase: [
      {
        src: '/marketing/modules/betterselect-team-sheet.jpg',
        headline: 'Name your XI on a proper team sheet.',
        body: 'A numbered batting order with a form read next to every name. Tag the captain and keeper, pick 11, 12, 13 or an open list, and the bat, bowl and keeper count updates as you drag.',
        points: [
          'Numbered, draggable batting order',
          'Form on every player, hot to cold',
          'Captain and keeper tags',
          'Live batting and bowling balance',
        ],
      },
      {
        src: '/marketing/modules/betterselect-self-service.jpg',
        headline: 'Players set their own availability.',
        body: 'Share one club link by QR code or in the group chat. A player opens it, taps the last four digits of their phone number and answers for the weekend. They need nothing beyond the link and their own phone.',
        points: [
          'One link for the whole club, QR included',
          'A last-4-of-phone PIN instead of a login',
          'Answers appear in the matrix straight away',
          'Rotate or switch off the link any time',
        ],
      },
      {
        src: '/marketing/modules/betterselect-availability.jpg',
        headline: 'The whole weekend on one grid.',
        body: 'Every player against every fixture, with a running tally of who is in, who is out and who has gone quiet. When a column fills up, Pick XI takes you straight to selection.',
        points: [
          'All fixtures side by side',
          'Available, maybe, unavailable or silent at a glance',
          'Set one player across a whole date range',
          'Pick XI straight from any fixture',
        ],
      },
      {
        src: '/marketing/modules/betterselect-squads.jpg',
        headline: 'Sixteen squads on one board.',
        body: "Drag players between grades, or let auto-seed copy last season's structure to get you started. Filters cut a 1,500-name history down to the players who have actually fronted up this year.",
        points: [
          'A column for every grade',
          'Auto-seed from last season or auto-assign by grade',
          'Bulk add with recency filters',
          'Availability dots on every player card',
        ],
      },
      {
        src: '/marketing/modules/betterselect-votes.jpg',
        headline: 'The 3-2-1 count, added up as you go.',
        body: 'Players cast their votes from the same club link they use for availability, and the leaderboard keeps the running count. Points, recent form and each player’s 3s, 2s and 1s sit in one table, with a race chart showing how the top five got there.',
        points: [
          'Votes cast from one link, no player logins',
          'Whole club or one grade at a time',
          'Ballot values, voters and tie-breaks are yours to set',
          'Presentation mode reveals the season a round at a time',
        ],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betterselect-overview.jpg', caption: 'Match-day overview for every team' },
      { src: '/marketing/modules/betterselect-selection-overview.jpg', caption: 'Every weekend XI, with a status on each' },
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
    screenshot: '/marketing/modules/bettersocials-lineup-hero.jpg',
    showcase: [
      {
        src: '/marketing/modules/bettersocials-lineup-card.jpg',
        headline: 'Nine lineup designs. One team sheet.',
        body: 'Pick the layout that suits the occasion: a hero shot, a trading-card grid, a brutalist list or a festival poster. Everything comes out in your colours, with your crest, in the display font you choose.',
        points: [
          'Nine lineup layouts',
          'Club colours and crest applied automatically',
          'Display fonts, with a dark or light finish',
          'Downloads as a sharp PNG',
        ],
      },
      {
        src: '/marketing/modules/bettersocials-scorecard-broadcast.jpg',
        headline: 'Paste a link and the scorecard fills itself.',
        body: 'Drop in the match URL and the card builds from the data: both innings, the bowling figures and the result, with your sponsors along the bottom edge.',
        points: [
          'Auto-fills from your match data',
          'Broadcast, brutalist and dashboard layouts',
          'Both innings with bowling figures',
          'Sponsor strip built in',
        ],
      },
      {
        src: '/marketing/modules/bettersocials-potm.jpg',
        headline: "Make Saturday's hero famous by Sunday.",
        body: 'Pick the player and up to four numbers worth shouting about, and the spotlight card builds itself around their photo. The same designer covers announcements, the toss and the final score.',
        points: [
          'Up to four stats per card',
          'Player photo with the club crest',
          'Covers announcements, toss and final score too',
          'One tap to export and post',
        ],
      },
      {
        src: '/marketing/modules/bettersocials-website-home.jpg',
        headline: 'A real club website at a real address.',
        body: 'News, info pages, honour boards, the committee and photo galleries, sitting next to your live stats on your own page. Build it quietly behind the publish switch, then flick it on when it reads right.',
        points: [
          'News, pages, honours, committee and galleries',
          'An editor anyone on the committee can drive',
          'Your ground photo across the top',
          'Publish when it is ready',
        ],
      },
    ],
    gallery: [
      { src: '/marketing/modules/bettersocials-announcement.jpg', caption: 'Appointment & announcement cards' },
      { src: '/marketing/modules/bettersocials-results.jpg', caption: 'Weekend result wraps' },
      { src: '/marketing/modules/bettersocials-fixtures.jpg', caption: 'Fixture announcement cards' },
      { src: '/marketing/modules/bettersocials-scorecard-app.jpg', caption: 'Scorecard, app-style dashboard layout' },
      { src: '/marketing/modules/bettersocials-website-editor.jpg', caption: 'Build pages with a simple editor' },
    ],
  },
  {
    slug: 'betteradmin',
    key: 'admin',
    name: 'BetterAdmin',
    icon: '◉',
    accent: BRAND.admin.accent,
    logo: BRAND.admin.logo,
    audience: 'For the committee, treasurer & secretary',
    compareKey: 'betteradmin',
    tagline: 'Run the whole club: people, money, volunteers and the committee.',
    summary:
      'BetterAdmin is your club’s back office on top of one member directory. Fees that allocate themselves, bulk email, stock, the volunteer roster, committee meetings with minutes and motions, and a season diary of every job that comes around each year. All of it works off the same player database as your stats, so nothing needs exporting between tools.',
    members: ['Directory', 'BetterFees', 'BetterComms', 'BetterMerch', 'Committee', 'Roster', 'Club Diary'],
    highlights: [
      'One member directory for the whole club',
      'Auto-allocating match-fee payments',
      'Volunteer roster and hours',
      'A season diary of the club’s annual jobs',
      'Committee meetings, minutes and motions',
    ],
    features: [
      { title: 'One member directory', desc: 'Every player, parent, life member, volunteer and sponsor contact in one list, built from your stats data rather than typed in again. Filter by membership type, by who is still playing, or by who you are missing an email address for.' },
      { title: 'Automatic fee allocation', desc: 'A recorded payment settles games oldest-first, in full while the money lasts; the boundary game shows part-paid. Edit days played and it re-allocates itself.' },
      { title: 'Always-correct status', desc: 'Per-game Paid / Part-paid / Unpaid is derived on read — there’s no stale flag to keep in sync.' },
      { title: 'Credit & waivers', desc: 'Overpay and the balance rolls forward as credit; waive a match-day fee with a note. Membership and match-fee buckets stay separate.' },
      { title: 'Volunteer roster', desc: 'Roster the canteen, the bar and the gate week by week, track who is available, and confirm the week once it is done. Confirmed shifts post straight to the club’s hours ledger, with paid work kept apart from volunteer work for your grant applications.' },
      { title: 'Committee & meetings', desc: 'Run the meeting from the agenda itself: mark attendance, put motions and votes against the item being discussed, hand out actions with owners, and type the minutes as you go. Agendas group into sections and there are starter templates for an AGM or an ordinary committee meeting.' },
      { title: 'Season club diary', desc: 'The jobs that come around every year, laid out across your season so nothing is remembered the week it was due. Affiliation fees, the AGM, insurance and licence renewals, the tax return and the ground work, each with an owner, a due date and a budget.' },
      { title: 'Committee roles that hand over', desc: 'Positions, terms and who holds what, so the roles carry over at the AGM rather than living in one person’s head. A job can be owned by the seat instead of the person, and it moves with the seat.' },
      { title: 'A strategic plan you can track', desc: 'Group your objectives under the club’s own pillars, give each one an owner, a budget and a due date, and watch the actions serving it report back. A starter plan is one button, so nobody faces a blank page.' },
      { title: 'Committee documents', desc: 'Keep quotes, policies and reports against the meeting or the action that called for them, either as a link or an uploaded file, with uploads readable by your office bearers only if you want it that way.' },
      { title: 'Bulk email (BetterComms)', desc: 'Newsletters and announcements to your member database — contacts come straight from your players, with Spam-Act-compliant unsubscribes.' },
      { title: 'Stock and merch', desc: 'Track playing kit, equipment and canteen stock, what has been issued to who, and what is still owed.' },
    ],
    screenshot: '/marketing/modules/betteradmin-overview.jpg',
    showcase: [
      {
        src: '/marketing/modules/betteradmin-fees-payments.jpg',
        headline: 'Record the payment. The ledger does the rest.',
        body: 'Match days come straight off the scorecards, so the games a player owes for are already listed. A recorded payment settles them oldest first, and anything left over sits as credit against the next one.',
        points: [
          'Match days derived from appearances',
          'Payments settle games oldest first',
          'Overpayment carries forward as credit',
          'Waive a single game with a note',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-fees-schedule.jpg',
        headline: 'Your rate card, season by season.',
        body: 'Set membership tiers with a one-off fee and a per-day match rate. Upfront tiers prepay the summer, standard tiers pay as they play, and what a player owes is always days played times their rate.',
        points: [
          'Membership tiers per season',
          'Standard and upfront payment types',
          'Per-day match-fee rates',
          'Recompute match days in one click',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-fees-reports.jpg',
        headline: "The treasurer's report, already written.",
        body: 'Payable, paid, waived and outstanding across the whole season, split by payment type. The follow-up list shows who still owes, and the full ledger exports for the bookkeeper.',
        points: [
          'Season totals at a glance',
          'Split by payment type',
          'Financial and non-financial member counts',
          'CSV export for the bookkeeper',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-club-diary.jpg',
        headline: 'Every job the club forgets, on one page.',
        body: 'Affiliation fees, the AGM, insurance and licence renewals, the tax return and the pre-season ground work, laid out across your own diary year with an owner and a due date on each. The plan tells you what is overdue, what is holding something else up, and how long the chained work really runs.',
        points: [
          'A season plan across your club’s own diary year',
          'Starter templates for the usual annual jobs',
          'Owners, due dates and budgets on every task',
          'Overdue and blocked work called out up front',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-comms.jpg',
        headline: 'Email the whole club from the same list.',
        body: 'Compose once and greet every member by first name. The audience comes straight from your player database, and you can send a test to yourself before it goes anywhere.',
        points: [
          'Contacts straight from your player list',
          'First-name personalisation',
          'Test send to yourself first',
          'Unsubscribes that meet the Spam Act',
        ],
      },
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
    showcase: [
      {
        src: '/marketing/modules/betteriq-opposition-analysis.jpg',
        headline: '240 meetings of homework in a few seconds.',
        body: 'Pick an opponent and the dossier opens on your full record against them: the all-time ledger, the last meeting, which of your players go well against them and how each venue has treated you.',
        points: [
          'All-time and recent head-to-head',
          'Your best bats and bowlers against them',
          'Venue-by-venue history',
          'Built from scorecards you already hold',
        ],
      },
      {
        src: '/marketing/modules/betteriq-danger-players.jpg',
        headline: 'Know their danger man before the toss.',
        body: 'Their leading run-scorers and wicket-takers, each with last-five form, a record against your club and a suggested plan. Inflated averages get called out as paper tigers.',
        points: [
          'Danger batters and bowlers, ranked',
          'Last-five form on every card',
          'A plan against each threat',
          'Risk and confidence tags on every read',
        ],
      },
      {
        src: '/marketing/modules/betteriq-selection-analysis.jpg',
        headline: 'A second opinion on your XI.',
        body: 'BetterIQ reads the side you saved in BetterSelect and compares it against the best available XI from the same pool. It checks the balance, names the gaps and suggests the swap before the side goes out.',
        points: [
          'Syncs with your BetterSelect lineup',
          'Best-available XI from the same pool',
          'Balance across bats, bowlers, keeper and openers',
          'Plain warnings, like no frontline spinner',
        ],
      },
      {
        src: '/marketing/modules/betteriq-team-batting-analysis.jpg',
        headline: 'How your team actually bats.',
        body: 'Powerplay, middle and death scoring from live-scored games, your average score and boundary percentage, what a good or poor start usually leads to, and the average stand at every wicket.',
        points: [
          'Powerplay, middle and death splits',
          'Average score, high, low and boundary %',
          'Opening stands and what follows them',
          'Average partnership by wicket',
        ],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betteriq-how-to-beat-them.jpg', caption: 'How to beat them: the game plan' },
      { src: '/marketing/modules/betteriq-how-they-win-lose.jpg', caption: 'How they win and lose' },
      { src: '/marketing/modules/betteriq-cheat-sheet.jpg', caption: "The captain's cheat sheet, print-ready" },
      { src: '/marketing/modules/betteriq-selection-assistant.jpg', caption: 'Selection assistant' },
      { src: '/marketing/modules/betteriq-selection-squad.jpg', caption: 'Squad assistant' },
      { src: '/marketing/modules/betteriq-team-analysis.jpg', caption: 'Team analysis' },
    ],
  },
  {
    slug: 'betterfantasy',
    key: MODULE.FANTASY,
    name: 'BetterFantasyCricket',
    icon: '★',
    accent: BRAND.fantasy.accent,
    logo: BRAND.fantasy.logo,
    audience: 'For the whole club & supporters',
    tagline: 'A fantasy cricket comp for your club, scored off your own games.',
    summary:
      'BetterFantasyCricket is your club’s own fantasy game, played by members and supporters over the season and scored off the real scorecards you already sync. Everyone picks a squad from your actual playing list across every grade, captains a star and climbs the club ladder week to week. Run a salary-cap game, a draft, or both. It’s a fun way to keep the whole club switched on all summer, and an easy pre-season fundraiser if you want one.',
    highlights: [
      'Your own players, scored off your real games',
      'Salary cap and draft formats, your call',
      'Members join from one link with a PIN',
      'An easy pre-season club fundraiser',
    ],
    features: [
      { title: 'Played off your real scorecards', desc: 'Points come straight from the games you already sync: batting, bowling, fielding and dismissals across every grade. There’s nothing extra to score and no separate feed to wait on.' },
      { title: 'Pick from your own list', desc: 'The whole club is the player pool. Members build a 12 from your actual players, name a captain for double points, and the best 11 each round count on their own.' },
      { title: 'Salary cap or draft', desc: 'Run a FPL-style salary-cap game where everyone can pick the same stars, a snake or auction draft where each player is owned by one team, or both at once.' },
      { title: 'Transfers, chips and form', desc: 'Prices move on form and ownership through the season. Managers get a free transfer each round, can take a hit for more, and have chips like the wildcard and triple captain up their sleeve.' },
      { title: 'A club ladder and mini-leagues', desc: 'One ladder for the whole club, plus private mini-leagues members set up with a join code, for the grade group or a family rivalry.' },
      { title: 'No app, no account for members', desc: 'Members play from one club link and a PIN they set, shared by QR code or in the group chat. They need nothing beyond the link and their phone.' },
      { title: 'In your club’s colours', desc: 'The whole member experience is white-labelled to your club, with your crest and colours and a light or dark finish.' },
      { title: 'It runs itself', desc: 'Set the season up once and rounds generate from your fixtures, points settle after each weekend’s sync, and the ladder keeps itself current for the rest of the summer.' },
    ],
    fundraiser: {
      eyebrow: 'A pre-season earner',
      headline: 'Turn the comp into a club fundraiser.',
      body: 'Plenty of clubs ask everyone to chip in a small entry fee, say $20 a head, and put a prize up for whoever tops the ladder come season’s end. You raise a few hundred dollars before a ball is bowled, the playing group is talking all summer, and the competition looks after itself off the scores you already sync.',
      points: [
        'Set an entry fee and collect it the way you already take club money. The app never touches the cash, so you stay clear of payment handling.',
        'Put up a prize that suits your club, like a free season, credit on the club card or some club merch.',
        'Members play from one link, the ladder updates after each weekend, and you don’t have to lift a finger once it’s running.',
      ],
      note: 'Entry fees and prizes are run by your club, not through the app. Worth a quick check of the competition and trade-promotion rules in your state or country before you charge to enter.',
    },
    note: 'BetterFantasyCricket runs off the same player database and synced scorecards as your stats, so the player pool and the scoring stay current on their own.',
    screenshot: '/marketing/modules/betterfantasy-my-team.jpg',
    showcase: [
      {
        src: '/marketing/modules/betterfantasy-login.jpg',
        headline: 'No app. No account. Just a link.',
        body: 'Members join from one club link, pick a display name and set a PIN, and they’re playing. It’s the same self-serve pattern as BetterSelect, so supporters who never log into anything else can still get a team in.',
        points: [
          'One club link, shared by QR or group chat',
          'A PIN they set, no app to download',
          'Open to members and supporters, not just players',
          'White-labelled to your club',
        ],
      },
      {
        src: '/marketing/modules/betterfantasy-pick-squad.jpg',
        headline: 'Build your 12 under a salary cap.',
        body: 'Each manager picks a keeper, four batters, three all-rounders and four bowlers inside a fixed budget, then captains one for double points. The best 11 score each round, so a player who misses a week drops out on his own.',
        points: [
          'A 12-player squad inside one budget',
          'Role quotas keep every side balanced',
          'Captain for double points',
          'Prices set from real BetterStats history',
        ],
      },
      {
        src: '/marketing/modules/betterfantasy-transfers.jpg',
        headline: 'Trade your way up the ladder.',
        body: 'Prices drift on form and ownership as the season runs. Managers get a free transfer each round, can take a points hit for more, and bank a transfer to spend later, the FPL rhythm club cricketers already know.',
        points: [
          'A free transfer every round',
          'Prices move on form and ownership',
          'Take a hit for extra moves, or bank one',
          'Chips like the wildcard and triple captain',
        ],
      },
      {
        src: '/marketing/modules/betterfantasy-player-profile.jpg',
        headline: 'Every price backed by real club numbers.',
        body: 'Tap any player and you get their fantasy price, form and ownership next to their real season and career record, the same reconciled stats that run the rest of BetterStats. Managers pick on the numbers, not a hunch.',
        points: [
          'Fantasy price, form and ownership',
          'This-season and career batting and bowling',
          'The same reconciled stats as the club site',
          'One tap to transfer the player in',
        ],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betterfantasy-chips.jpg', caption: 'Chips: the wildcard, triple captain and more' },
    ],
  },
]

export function moduleBySlug(slug) {
  if (slug === CORE_MARKETING.slug) return CORE_MARKETING
  return MODULES_MARKETING.find((m) => m.slug === slug) || null
}
