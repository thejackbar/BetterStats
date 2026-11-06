// Marketing copy + helpers for the BetterCricket module ecosystem.
//
// The platform is **BetterCricket** (from BetterSports). Every club gets the
// **Core (BetterStats)**: data ingestion, reconciled stats and the public club
// site. It then bolts on the modules below. Public prices live in
// src/data/pricing.js (the modular pricing model + calculator).
//
// House rule for this file: the screenshots are the hook, so copy stays short.
// A showcase entry is a headline, one or two sentences and three points. A
// feature is a title and one line. Lead with the club's history and the
// leaderboards; the detail lives in the FAQ and the changelog.
//
// The bolt-ons mirror the in-app umbrella tiles: BetterSelect, BetterSocials
// (the post designer + the club website), BetterAdmin (the back office) and
// BetterIQ. BetterFantasyCricket is a standalone add-on, priced on its own in
// pricing.js rather than in the module bundle.

import { MODULE } from '../lib/modules'
import { MODULE_BRAND as BRAND } from '../lib/moduleBrand'

// ── BetterStats: the always-on base module ──────────────────────────────────
// Required for every club and not separately gateable, but marketed as a module
// like the rest. Its deeper tour lives on /features.
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
  tagline: 'Every player, every season, kept forever.',
  to: '/modules/betterstats',
  deepTour: '/features',
  summary:
    'Your full match history on a public club site that updates itself after every game: leaderboards, profiles, records, scorecards and yearbooks.',
  // Four only: Overview and the highlight strip both show four.
  highlights: [
    'Your full history, kept forever',
    'Leaderboards and all-time records',
    'A career page for every player',
    'A public site in your colours',
  ],
  features: [
    { title: 'Automatic sync', desc: 'Connect once. Every new game flows in on its own.' },
    { title: 'Decades reconciled', desc: 'Names, teams and seasons matched, so a career reads as one record.' },
    { title: 'Leaderboards', desc: 'Every batting, bowling and fielding category, by season, grade and competition.' },
    { title: 'Club records', desc: 'All-time and season bests, updated after every sync.' },
    { title: 'Player profiles', desc: 'Career and season figures, milestones, rank badges and a photo.' },
    { title: 'Competition filters', desc: 'Read stats by competition, grade type and match type.' },
    { title: 'Juniors kept apart', desc: 'Junior seasons stay out of senior careers, and come back with one tap.' },
    { title: 'Scorecards', desc: 'Every game kept, with a choice of which scorecard the site shows.' },
    { title: 'Bring your history', desc: 'One spreadsheet, CricketStatz or the scorebook, merged without doubling up.' },
    { title: 'Premierships and honours', desc: 'Flags fill in from grand final scorecards, beside awards and honour boards.' },
    { title: 'Season yearbooks', desc: 'A season annual that fills itself.' },
    { title: 'Player Dashboard', desc: 'Each player’s season, plus availability, Fantasy and fees if you run them.' },
    { title: 'Player Cards', desc: 'A collectable card for every player. Weekly packs, swaps and sets.' },
    { title: 'Club Room Mode', desc: 'A TV slideshow for the clubhouse, fed by your own records.' },
    { title: 'Sponsor tiers', desc: 'A tier decides where each sponsor shows across the site.' },
    { title: 'Milestones and privacy', desc: 'Choose your milestone steps, and hide players or juniors from the public site.' },
  ],
  screenshot: '/marketing/hero-career-card.jpg',
  // History and leaderboards first, then the player-facing pages.
  showcase: [
    {
      src: '/marketing/stats-by-competition.jpg',
      headline: 'The ladder, for every category.',
      body: 'Leaderboards for every batting, bowling and fielding category. Read them by season, grade, competition or match type.',
      points: ['Every category, every grade', 'Filter by competition and match type', 'Updated after every sync'],
    },
    {
      src: '/marketing/hero-career-card.jpg',
      headline: 'A whole career on one page.',
      body: 'Career and season batting, bowling and fielding, milestones, honours and a photo, back to a player’s first game.',
      points: ['Career and season totals', 'Milestones and honours', 'Format and grade splits'],
    },
    {
      src: '/marketing/feature-honours.jpg',
      headline: 'The record books, always current.',
      body: 'All-time and season-best records across batting, bowling, partnerships and team feats, flagged the week they are set.',
      points: ['Batting, bowling and partnerships', 'A record at every wicket', 'New records flagged'],
    },
    {
      src: '/marketing/showcase-scorecard.jpg',
      headline: 'Every scorecard, kept for good.',
      body: 'Both innings, every dismissal, extras and the result. A 1996 8th-grade game sits in the archive the same way last Saturday does.',
      points: ['Batting and bowling for both sides', 'Fall of wickets and partnerships', 'Back to your earliest season'],
    },
    {
      src: '/marketing/yearbook.jpg',
      headline: 'A season annual that writes itself.',
      body: 'Pick a season and the yearbook fills in the record, the leaders and the awards. Share the link or print it.',
      points: ['Filled in from the season’s stats', 'Honours and top performers', 'A permanent link for every year'],
    },
    {
      src: '/marketing/player-dashboard.jpg',
      headline: 'A page for every player.',
      body: 'One club link and a four-digit PIN open each player’s season and cards, plus availability, Fantasy and fees where you run them.',
      points: ['Batting, bowling and fielding panels', 'Last five innings and spells', 'Works without BetterSelect'],
    },
    {
      src: '/marketing/player-cards-book.jpg',
      headline: 'Every player is a card.',
      body: 'Cards are rated 1 to 99 from career figures. Weekly packs, swaps and sets keep players coming back.',
      points: ['Packs for runs, wickets and wins', 'Special cards for centuries and five-fors', 'No paid packs'],
    },
  ],
  gallery: [
    { src: '/marketing/leaderboard.jpg', caption: 'StatLab: build your own table' },
    { src: '/marketing/statlab-team-records.jpg', caption: 'Team records, such as biggest successful chases' },
    { src: '/marketing/premierships.jpg', caption: 'Premierships, filled in from grand final scorecards' },
    { src: '/marketing/player-profile.jpg', caption: 'Honour boards on every profile' },
    { src: '/marketing/club-room-stage.jpg', caption: 'Club Room Mode on the clubhouse TV' },
    { src: '/marketing/sponsors-major-slot.jpg', caption: 'A major sponsor slot on the club dashboard' },
    { src: '/marketing/card-review.jpg', caption: 'Card review: choose which scorecard the site shows' },
    { src: '/marketing/player-dashboard-phone.jpg', caption: 'The player dashboard on a phone' },
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
      'Players set their own availability from a link, you name the XI for every team on one board, and the votes count themselves.',
    highlights: [
      'Availability with no player logins',
      'The Selection Whiteboard',
      'Form- and grade-aware picks',
      'Votes, nets and fines in one place',
    ],
    features: [
      { title: 'Availability link', desc: 'Players answer from one club link and a four-digit PIN. No accounts.' },
      { title: 'Match-day overview', desc: 'See who has answered and which team still needs a keeper.' },
      { title: 'Selection Whiteboard', desc: 'Every team for the day side by side, with a pool of unpicked players.' },
      { title: 'Smart selection', desc: 'A numbered batting order with form on every name and a live balance check.' },
      { title: 'Locked sides and undo', desc: 'Confirm locks a side. Undo and History track every change.' },
      { title: 'Two-day games', desc: 'Answers by weekend, with a colour for players who are half available.' },
      { title: 'Squads', desc: 'Drag players between squads. One squad can cover several teams.' },
      { title: 'Selection rules', desc: 'Write your competition’s limits down once, as warnings or bars.' },
      { title: 'Email the side', desc: 'Send the confirmed XI to the captain and the players.' },
      { title: 'Best-player votes', desc: 'Several medals, weighted by grade, counted from one voting link.' },
      { title: 'Nets', desc: 'QR check-in and a rotation timer that runs on every device.' },
      { title: 'Fines', desc: 'A pot, a tracker and a PDF report for the season.' },
      { title: 'Junior Rotation', desc: 'Fair batting orders and fielding spots for the kids.' },
      { title: 'Fixtures and ladders', desc: 'Synced from the association, with live ladders for every team.' },
    ],
    screenshot: '/marketing/modules/betterselect-selection.jpg',
    showcase: [
      {
        src: '/marketing/modules/betterselect-whiteboard.jpg',
        headline: 'Every team for the day on one board.',
        body: 'Each team playing that day is a column beside everyone not yet picked. Drag a player across, and every team saves as a draft until you confirm.',
        points: ['Every team side by side', 'Locked sides ask before they change', 'W1 and W2 markers for two-day games'],
      },
      {
        src: '/marketing/modules/betterselect-self-service.jpg',
        headline: 'Players set their own availability.',
        body: 'Share one club link by QR code or group chat. Players tap the last four digits of their phone and answer for the weekend.',
        points: ['No logins or apps', 'Answers appear in the grid straight away', 'Rotate or switch off the link any time'],
      },
      {
        src: '/marketing/modules/betterselect-team-sheet.jpg',
        headline: 'Name your XI on a proper team sheet.',
        body: 'A numbered batting order with form beside every name. Tag the captain and keeper and watch the balance update.',
        points: ['Draggable batting order', 'Form from hot to cold', 'Live bat, bowl and keeper count'],
      },
      {
        src: '/marketing/modules/betterselect-votes.jpg',
        headline: 'The 3-2-1 count, added up as you go.',
        body: 'Players vote from the same link they use for availability. The leaderboard keeps points, form and each player’s 3s, 2s and 1s.',
        points: ['Several medals at once', 'Whole club or one grade', 'Presentation mode for awards night'],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betterselect-availability.jpg', caption: 'The whole weekend on one grid' },
      { src: '/marketing/modules/betterselect-squads.jpg', caption: 'Every squad on one board' },
      { src: '/marketing/modules/betterselect-locked-history.jpg', caption: 'Selection History: every confirm, lock and change' },
      { src: '/marketing/modules/betterselect-rules.jpg', caption: 'Selection rules, set as warnings or bars' },
      { src: '/marketing/modules/betterselect-votes-medals.jpg', caption: 'Several medals, each with its own ballot' },
      { src: '/marketing/modules/betterselect-nets.jpg', caption: 'A net session timer that rolls the batting order' },
      { src: '/marketing/modules/betterselect-players.jpg', caption: 'A player card with form and availability' },
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
    tagline: 'Posts your community reposts, and a club website to go with them.',
    summary:
      'Pick a layout and the post fills itself from your match data, with your crest, colours and sponsors already on it.',
    highlights: [
      'Lineups, results, scorecards and more',
      'Fills itself from your match data',
      'Square, portrait and story sizes',
      'Your club website included',
    ],
    features: [
      { title: 'A post for every job', desc: 'Lineups, fixtures, results, scorecards, player of the match, milestones and more.' },
      { title: 'Dozens of layouts', desc: 'Thirteen lineup designs alone, from hero shots to a full-height Team Sheet.' },
      { title: 'Square, portrait or story', desc: 'Each layout has a design for every size.' },
      { title: 'Fills itself', desc: 'Paste one match link and every grade’s game that weekend comes in.' },
      { title: 'Team of the Week', desc: 'The best performers across every grade, on one post.' },
      { title: 'Milestones and debuts', desc: 'Celebrate a 100th game or a first cap in a tap.' },
      { title: 'Sponsors on every post', desc: 'Your sponsor strip is on the post before you start.' },
      { title: 'Layers', desc: 'Move, reorder and recolour every part of a layout.' },
      { title: 'Your own photos or Canva', desc: 'Cut a player out of a photo, or bring in a Canva design.' },
      { title: 'Your club website', desc: 'News, pages, honours and galleries beside your live stats.' },
    ],
    comingSoon: ['Scheduled & auto-posting after a result', 'Auto-generated match summaries'],
    screenshot: '/marketing/modules/bettersocials-lineup-hero.jpg',
    showcase: [
      {
        src: '/marketing/modules/bettersocials-lineup-card.jpg',
        headline: 'Thirteen lineup designs. One team sheet.',
        body: 'Pick the look for the occasion. Everything comes out in your colours, with your crest and your sponsors.',
        points: ['Thirteen lineup layouts', 'Club colours, crest and fonts applied', 'Downloads as a sharp PNG'],
      },
      {
        src: '/marketing/modules/bettersocials-sizes.jpg',
        headline: 'Square, portrait or story.',
        body: 'Make the same post at three sizes. Each layout has its own design for the taller ones, not a square stretched.',
        points: ['Three sizes from one layout', 'Sponsor strip added for you', 'A scorecard can split into two squares'],
      },
      {
        src: '/marketing/modules/bettersocials-scorecard-broadcast.jpg',
        headline: 'Paste a link and the scorecard fills itself.',
        body: 'Drop in the match link and the card builds from the data: both innings, the bowling and the result.',
        points: ['Broadcast, brutalist and dashboard layouts', 'Both innings with bowling figures', 'Sponsor strip built in'],
      },
      {
        src: '/marketing/modules/bettersocials-website-home.jpg',
        headline: 'A real club website at a real address.',
        body: 'News, pages, honours, the committee and galleries beside your live stats. Build it quietly, then publish when it reads right.',
        points: ['An editor anyone on the committee can use', 'Honours, committee and galleries', 'Publish when it is ready'],
      },
    ],
    gallery: [
      { src: '/marketing/modules/bettersocials-potm.jpg', caption: 'Player of the match' },
      { src: '/marketing/modules/bettersocials-totw.jpg', caption: 'Team of the Week, scored from every grade' },
      { src: '/marketing/modules/bettersocials-milestones.jpg', caption: 'A Milestones post' },
      { src: '/marketing/modules/bettersocials-layers.jpg', caption: 'Every part of a layout is a layer' },
      { src: '/marketing/modules/bettersocials-results.jpg', caption: 'Weekend result wraps' },
      { src: '/marketing/modules/bettersocials-fixtures.jpg', caption: 'Fixture announcement cards' },
      { src: '/marketing/modules/bettersocials-announcement.jpg', caption: 'Appointment and announcement cards' },
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
      'One member directory with fees, email, rosters, meetings and the club diary on top, all from the same player list as your stats.',
    members: ['Directory', 'BetterFees', 'BetterComms', 'BetterMerch', 'Committee', 'Roster', 'Club Diary'],
    highlights: [
      'One member directory',
      'Fees that allocate themselves',
      'Volunteer roster and committee',
      'A season diary and strategic plan',
    ],
    features: [
      { title: 'Member directory', desc: 'Players, parents, life members and volunteers in one list, built from your stats.' },
      { title: 'Automatic fees', desc: 'A payment settles games oldest first, and status is always correct.' },
      { title: 'Credit and waivers', desc: 'Overpayments roll forward. Waive a game with a note.' },
      { title: 'Accounts', desc: 'See who owes membership and who owes match fees, with a CSV.' },
      { title: 'Volunteer roster', desc: 'Roster the canteen, bar and gate, and post confirmed hours to a ledger.' },
      { title: 'Committee meetings', desc: 'Agenda, attendance, motions, votes and minutes in one place.' },
      { title: 'Strategic plan', desc: 'Objectives under your own pillars, with progress against time and budget.' },
      { title: 'Season club diary', desc: 'Affiliation fees, the AGM and renewals, each with an owner and a due date.' },
      { title: 'Committee roles', desc: 'Positions and terms that hand over at the AGM.' },
      { title: 'Bulk email', desc: 'Newsletters to your own member list, with Spam Act unsubscribes.' },
      { title: 'Stock and assets', desc: 'Kit, canteen stock and one register for equipment.' },
      { title: 'Permissions', desc: 'Give each person one module, or set every menu item to View or Manage.' },
    ],
    screenshot: '/marketing/modules/betteradmin-overview.jpg',
    showcase: [
      {
        src: '/marketing/modules/betteradmin-fees-payments.jpg',
        headline: 'Record the payment. The ledger does the rest.',
        body: 'Match days come straight off the scorecards. A payment settles the oldest games first, and anything left over becomes credit.',
        points: ['Match days derived from appearances', 'Payments settle oldest first', 'Waive a single game with a note'],
      },
      {
        src: '/marketing/modules/betteradmin-roster-coverage.jpg',
        headline: 'See which shifts are still open.',
        body: 'Coverage lists every unfilled shift for the days you pick, each with a best-fit volunteer ready to assign.',
        points: ['A button for each day', 'Roles with their own qualifications', 'Confirmed shifts post to the hours ledger'],
      },
      {
        src: '/marketing/modules/betteradmin-meeting-room.jpg',
        headline: 'Run the meeting from one screen.',
        body: 'Mark attendance, work down the agenda and record motions as they happen. Minutes download as Word or PDF.',
        points: ['Mover, seconder and a vote table', 'Actions handed out with owners', 'Minutes as Word or PDF'],
      },
      {
        src: '/marketing/modules/betteradmin-strategic-plan.jpg',
        headline: 'See how the plan is actually going.',
        body: 'Every theme, objective and action shows how far the work has got and how the money is going.',
        points: ['A schedule bar and a budget bar', 'A mark for where it should be by now', 'A starter plan in one button'],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betteradmin-fees-schedule.jpg', caption: 'Your rate card, season by season' },
      { src: '/marketing/modules/betteradmin-fees-reports.jpg', caption: 'The treasurer’s report, already written' },
      { src: '/marketing/modules/betteradmin-club-diary.jpg', caption: 'Every annual job on one page' },
      { src: '/marketing/modules/betteradmin-comms.jpg', caption: 'Email the whole club from the same list' },
      { src: '/marketing/modules/betteradmin-permissions.jpg', caption: 'Choose what each person can open' },
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
    tagline: 'Know the opposition before the toss.',
    summary:
      'Your own scorecards become an opposition dossier, a live selection brain and deep team analysis. No extra data entry.',
    highlights: [
      'Opposition scouting and cheat sheet',
      'Their named side, with form',
      'Ask IQ, in plain words',
      'Team analysis by innings phase',
    ],
    features: [
      { title: 'Scout the opposition', desc: 'Danger players, form, head-to-head and a game plan.' },
      { title: 'Your grade, not the club', desc: 'Scouting follows the grade you are playing.' },
      { title: 'Who they have named', desc: 'Their team list, set against what you know about each player.' },
      { title: 'Opposition players', desc: 'Wagon wheels, radars and their record against you.' },
      { title: 'Cheat sheet', desc: 'A print-ready captain’s sheet for the car park.' },
      { title: 'Live selection', desc: 'A best-available XI that updates as availability changes.' },
      { title: 'Ask IQ', desc: 'Ask who to pick or how to win, and it asks back when it matters.' },
      { title: 'Player trends', desc: 'Breakouts, declines and milestone forecasts.' },
      { title: 'Team analysis', desc: 'Powerplay, middle and death splits, partnerships and par scores.' },
    ],
    screenshot: '/marketing/modules/betteriq-overview.jpg',
    showcase: [
      {
        src: '/marketing/modules/betteriq-opposition-analysis.jpg',
        headline: '240 meetings of homework in a few seconds.',
        body: 'Pick an opponent and the dossier opens on your full record against them, the last meeting and each venue.',
        points: ['All-time and recent head-to-head', 'Your best bats and bowlers against them', 'Built from scorecards you already hold'],
      },
      {
        src: '/marketing/modules/betteriq-danger-players.jpg',
        headline: 'Know their danger man before the toss.',
        body: 'Their leading run-scorers and wicket-takers, each with last-five form, a record against you and a suggested plan.',
        points: ['Danger batters and bowlers, ranked', 'Last-five form on every card', 'A plan against each threat'],
      },
      {
        src: '/marketing/modules/betteriq-selection-analysis.jpg',
        headline: 'A second opinion on your XI.',
        body: 'BetterIQ reads the side you saved in BetterSelect and compares it with the best available XI from the same pool.',
        points: ['Syncs with your BetterSelect lineup', 'Balance across bats, bowlers and keeper', 'Plain warnings, like no frontline spinner'],
      },
      {
        src: '/marketing/modules/betteriq-team-batting-analysis.jpg',
        headline: 'How your team actually bats.',
        body: 'Powerplay, middle and death scoring, what a good start leads to, and the average stand at every wicket.',
        points: ['Powerplay, middle and death splits', 'Opening stands and what follows them', 'Average partnership by wicket'],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betteriq-ask-iq.jpg', caption: 'Ask IQ asks a question back when it matters' },
      { src: '/marketing/modules/betteriq-how-to-beat-them.jpg', caption: 'How to beat them: the game plan' },
      { src: '/marketing/modules/betteriq-how-they-win-lose.jpg', caption: 'How they win and lose' },
      { src: '/marketing/modules/betteriq-cheat-sheet.jpg', caption: 'The captain’s cheat sheet, print-ready' },
      { src: '/marketing/modules/betteriq-selection-assistant.jpg', caption: 'Selection assistant' },
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
      'Members pick a squad from your real players and climb a club ladder all season, scored off the scorecards you already sync.',
    highlights: [
      'Your own players, your real games',
      'Salary cap, draft or both',
      'Members join from one link',
      'An easy pre-season fundraiser',
    ],
    features: [
      { title: 'Scored off real games', desc: 'Points come from the scorecards you already sync.' },
      { title: 'Your own player list', desc: 'Members build a 12 from your actual players and name a captain.' },
      { title: 'Salary cap or draft', desc: 'Run a salary-cap game, a snake or auction draft, or both.' },
      { title: 'Transfers and chips', desc: 'A free transfer each round, plus the wildcard and triple captain.' },
      { title: 'Prices that move', desc: 'Prices rise and fall after every round, with arrows to show the movers.' },
      { title: 'Live while games are on', desc: 'Scores and the ladder update every ten minutes during play.' },
      { title: 'Ladder and mini-leagues', desc: 'One club ladder, plus private leagues with a join code.' },
      { title: 'See every team', desc: 'Once a round locks, open any team’s side from the ladder.' },
      { title: 'No app, no account', desc: 'Members play from one club link and a PIN.' },
      { title: 'It runs itself', desc: 'Rounds build from your draw, and points settle after each weekend.' },
    ],
    fundraiser: {
      eyebrow: 'A pre-season earner',
      headline: 'Turn the comp into a club fundraiser.',
      body: 'Plenty of clubs ask for a small entry fee, say $20 a head, and put up a prize for whoever tops the ladder. You raise a few hundred dollars before a ball is bowled, and the comp runs itself off scores you already sync.',
      points: [
        'Set an entry fee and collect it the way you already take club money. The app never touches the cash.',
        'Put up a prize that suits your club, like a free season or some club merch.',
        'Members play from one link and the ladder updates after each weekend.',
      ],
      note: 'Entry fees and prizes are run by your club, not through the app. Check the competition and trade-promotion rules in your state or country before you charge to enter.',
    },
    screenshot: '/marketing/modules/betterfantasy-my-team.jpg',
    showcase: [
      {
        src: '/marketing/modules/betterfantasy-login.jpg',
        headline: 'No app. No account. Just a link.',
        body: 'Members join from one club link, pick a display name and set a PIN. Supporters who never log into anything else can play.',
        points: ['One club link, shared by QR or group chat', 'Open to members and supporters', 'In your club’s colours'],
      },
      {
        src: '/marketing/modules/betterfantasy-pick-squad.jpg',
        headline: 'Build your 12 under a salary cap.',
        body: 'Pick a keeper, four batters, three all-rounders and four bowlers inside one budget, then captain one for double points.',
        points: ['Role quotas keep every side balanced', 'The best 11 score each round', 'Prices set from real BetterStats history'],
      },
      {
        src: '/marketing/modules/betterfantasy-transfers.jpg',
        headline: 'Trade your way up the ladder.',
        body: 'Prices move with form. Take a free transfer each round, or a points hit for more, and bank one to spend later.',
        points: ['A free transfer every round', 'Chips like the wildcard and triple captain', 'Sell several players at once'],
      },
      {
        src: '/marketing/modules/betterfantasy-player-profile.jpg',
        headline: 'Every price backed by real club numbers.',
        body: 'Tap any player for their fantasy price and form beside their real season and career record.',
        points: ['Price, form and ownership', 'Season and career batting and bowling', 'One tap to transfer the player in'],
      },
    ],
    gallery: [
      { src: '/marketing/modules/betterfantasy-teams-cards.jpg', caption: 'My Team as player cards' },
      { src: '/marketing/modules/betterfantasy-insights.jpg', caption: 'Round Insights: top players, trades and price movers' },
      { src: '/marketing/modules/betterfantasy-chips.jpg', caption: 'Chips: the wildcard, triple captain and more' },
    ],
  },
]

export function moduleBySlug(slug) {
  if (slug === CORE_MARKETING.slug) return CORE_MARKETING
  return MODULES_MARKETING.find((m) => m.slug === slug) || null
}
