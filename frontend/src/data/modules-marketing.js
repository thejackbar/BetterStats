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
    'BetterStats turns your club’s match data into a living history and a public site to be proud of. Connect once and every batting, bowling and fielding stat flows in on its own, reconciled across decades and ready as profiles, leaderboards, records, scorecards, yearbooks and shareable cards. Every player also gets their own dashboard and a collectable card, and the club room gets a TV slideshow.',
  highlights: [
    'Your full history, imported once and kept forever',
    'A public, club-branded website',
    'Profiles, leaderboards, records and yearbooks',
    'A dashboard and collectable cards for every player',
  ],
  features: [
    { title: 'Automatic stats sync', desc: 'Connect your club once and your whole match history is imported, then every new game flows in on its own. No data entry, no spreadsheets to maintain.' },
    { title: 'Reconciled across decades', desc: 'Names, teams and seasons are matched and de-duplicated, so a player’s whole career reads as one record, back to your earliest digitised season.' },
    { title: 'Rich player profiles', desc: 'Every player gets a profile with career and season batting, bowling and fielding, milestones, club rank badges and a photo.' },
    { title: 'Leaderboards and club records', desc: 'Live leaderboards and all-time records for runs, wickets, catches, partnerships and more, updated after every sync.' },
    { title: 'Junior grades kept out of senior careers', desc: 'An Under-14 season no longer flatters a senior batting average. Set which grades count towards your club’s figures once, then add juniors, women’s, masters or mixed cricket back in with one tap on any page. A player who has only ever played juniors still opens on their own numbers rather than a page of zeros.' },
    { title: 'Stats by competition, grade type and match type', desc: 'Read the club, a team or a player one competition at a time, then narrow by grade type (men’s, women’s, juniors, masters) and by match type (two day, one day, T20). A club that plays in several associations in the one season no longer has them added together, and every profile has a format tab that sets the three formats side by side.' },
    { title: 'Scorecards and match archive', desc: 'Full match scorecards and a browsable archive of every game, straight from your synced data. Where a game is also on a spreadsheet or in the scorebook, Card review lets you choose which scorecard the site shows, with an undo on every change.' },
    { title: 'Bring in everything you already have', desc: 'Load a whole club history from one spreadsheet, bring your records across from CricketStatz, or type in games from the scorebook. For a match you already hold, choose between importing only the new ones or overwriting. A hand-entered game is never overwritten by a sync.' },
    { title: 'Season yearbooks', desc: 'Publish a polished yearbook for any season, with the standout performances and the year’s awards.' },
    { title: 'Awards, premierships and honour boards', desc: 'Record season awards and honour boards, shown on player profiles and across the club site. A Premierships page lists each flag as the squad that won it, and when you win a grand final the premiership is added to every player in the side from the scorecard.' },
    { title: 'Shareable stat cards', desc: 'Every player has a clean, club-branded stat card, one tap to share on Instagram, Facebook or X.' },
    { title: 'A dashboard for every player', desc: 'Each player opens their own page from one club link and the last four digits of their mobile. It has their photo, shirt number and squads, a season dashboard with batting, bowling and fielding panels and their last five innings and spells, and the club’s cards. If your club runs BetterSelect, BetterFantasyCricket or fees, answering games, the Fantasy round and fees paid sit on the same page. You switch it on from BetterStats, and it works without BetterSelect.' },
    { title: 'Player Cards', desc: 'Every player at the club has a collectable card with a rarity from 1 to 99, built from their career figures. Players open a pack of five each week, earn more for runs, wickets and dismissals, and get a Winner Winner pack the day after a win. Centuries, five-fors, hat-tricks, debuts and club awards each earn a special card. Players swap with each other, work through sets and challenges, and share their cards. There are no paid packs, and nothing is ever taken from a collection.' },
    { title: 'Club Room Mode', desc: 'Build a playlist and leave it running full-screen on the club room TV: sponsors, upcoming fixtures and lineups, leaderboards, club records, your honour boards and premiership squads, saved social posts and your own images. It reads the same records as the website, so the TV and the site agree.' },
    { title: 'Sponsors that know their place', desc: 'Give each sponsor a tier (Major, Gold, Silver or Supporter, renamed to suit) and the tier decides where they show: a major sponsor slot on the club dashboard, the bottom bar and a full sponsor list. Link a sponsor to a section and its logo shows as Presented by under the menu, and you can rename that section to match.' },
    { title: 'Milestones your way', desc: 'Pick how often runs and wickets are marked (runs every 250, 500 or 1,000, wickets every 25, 50 or 100). The choice applies on the Records page, player profiles, the dashboard and the milestone emails.' },
    { title: 'Privacy under your control', desc: 'Hide a player from the public site and they drop out of profiles, search, leaderboards and records. Turn on Hide juniors from public stats to keep junior-only players off the site. A player who asks to be removed is hidden everywhere, and stays that way after later syncs.' },
  ],
  note: 'BetterStats is the base every club runs on. BetterSelect, BetterSocials, BetterAdmin and BetterIQ all bolt straight onto the same data.',
  screenshot: '/marketing/hero-career-card.jpg',
  // The best four screens, each with a proper write-up. Shown as full
  // text-beside-screenshot sections on the module page; everything else
  // stays in `gallery` below.
  showcase: [
    {
      src: '/marketing/player-dashboard.jpg',
      headline: 'A page for every player, from one link.',
      body: 'Each player opens their own page with the last four digits of their mobile. It has their photo and squads, a season dashboard with batting, bowling and fielding panels and their last five innings and spells, and the club’s cards. Where your club runs the modules, they also answer games, see when the next Fantasy round locks and check fees paid, all from the same page.',
      points: [
        'One club link and a four-digit PIN',
        'Batting, bowling and fielding panels with club rank',
        'Last five innings and last five spells',
        'Switched on from BetterStats, and it works without BetterSelect',
      ],
    },
    {
      src: '/marketing/player-cards-book.jpg',
      headline: 'Every player is a card. Collect the club.',
      body: 'Each player has a card rated 1 to 99 from their career figures. Packs of five arrive every week and for runs, wickets and wins, and a century, five-for, debut or club award earns a special card. Players swap with each other, work towards sets and take on challenges, and the club decides what is switched on.',
      points: [
        'Weekly packs, plus packs for runs, wickets and wins',
        'Special cards for centuries, five-fors, debuts and awards',
        'Swaps, sets, challenges and a collectors board',
        'No paid packs, and nothing is ever taken from a collection',
      ],
    },
    {
      src: '/marketing/leaderboard.jpg',
      headline: 'Build your own table.',
      body: 'StatLab is a query builder over everything your club has ever recorded. Start from one of 200+ pre-built reports or build your own, sort any of 30+ columns, and save the view once you like it. Team records are in there too, such as your biggest successful chases, the lowest totals you defended and your closest wins by runs and by wickets.',
      points: [
        '200+ pre-built reports',
        'Team records, with a link to each scorecard',
        'Pick several seasons, grades or results at once',
        'Filter by grade type, match type, opponent or decade',
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
    { src: '/marketing/club-room-stage.jpg', caption: 'Club Room Mode, full-screen on the clubhouse TV' },
    { src: '/marketing/stats-by-competition.jpg', caption: 'Read the club by competition, grade type and match type' },
    { src: '/marketing/premierships.jpg', caption: 'Premierships, filled in from grand final scorecards' },
    { src: '/marketing/sponsors-major-slot.jpg', caption: 'A major sponsor slot on the club dashboard' },
    { src: '/marketing/sponsors-tiers.jpg', caption: 'Sponsor tiers, and sections renamed to carry a sponsor' },
    { src: '/marketing/statlab-team-records.jpg', caption: 'StatLab team records, such as biggest successful chases' },
    { src: '/marketing/card-review.jpg', caption: 'Card review: choose which scorecard the site shows' },
    { src: '/marketing/player-dashboard-phone.jpg', caption: 'The player dashboard on a phone' },
    { src: '/marketing/feature-opposition.jpg', caption: 'Per-player opposition analysis' },
    { src: '/marketing/feature-games.jpg', caption: 'A browsable match archive' },
    { src: '/marketing/feature-whitelabel.jpg', caption: "Make the public site your club's own" },
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
      'BetterSelect handles the weekly “who’s in?” across every grade at once. Players set their own availability from a link without creating an account, you build squads and name each XI on a numbered batting order, and form- and grade-aware suggestions help you land on a balanced side. The Selection Whiteboard puts every team playing that day side by side, so you can see the whole club’s weekend in one place. Fixtures, ladders, net sessions, fines and the season’s best-player votes all sit alongside, in your club’s colours.',
    highlights: [
      'Availability with no player logins',
      'Selection Whiteboard: every team for the day side by side',
      'Form- and grade-aware selection',
      'Two-day games handled weekend by weekend',
      'Best-player votes, counted for you',
      'Net check-in, fines and junior rotation',
    ],
    features: [
      { title: 'Match-day overview', desc: 'A weekend snapshot for every team: who is available, who has not replied yet, and which keeper or selection still needs a chase.' },
      { title: 'Availability, set in a tap', desc: 'Mark players in, out or maybe across every fixture, or set someone available over a whole date range in one go. Tapping a status saves on the spot.' },
      { title: 'A link players answer themselves', desc: 'Players set their own availability from one club link and a four-digit PIN. Share it by QR code or in the team group chat; a player opens it, taps their PIN and sets their weekend in a few seconds.' },
      { title: 'Squad boards', desc: 'Drag players between squads, one for each grade. Auto-seed from last season or auto-assign by grade to start, then move people by hand.' },
      { title: 'Smart selection', desc: 'Pick on a numbered batting order or a dual rail of pool and XI. Each player carries a form read from hot to cold, and autofill or last week’s side gives you a starting point.' },
      { title: 'Captain, keeper and balance', desc: 'Set the captain and keeper, watch the bat, bowl and keeper mix update as you go, and choose your lineup size. Selection flags a side with no keeper or a short attack.' },
      { title: 'Every team in one view', desc: 'All your upcoming XIs in one list, each marked not started, in progress, ready or needs attention, so nothing gets missed on a busy weekend.' },
      { title: 'Selection Whiteboard', desc: 'Every team playing that day is a column, with a pool of the players nobody has picked yet beside them. Drag a player from one team to another to swap them, or onto a team to fill its next open spot. Each team saves as its own draft, and Confirm all writes every team that changed, top team first. On an iPhone or iPad you tap instead of drag, and the Pool and each team are pages you swipe between.' },
      { title: 'Locked sides, undo and history', desc: 'Confirm locks a side so it stays as it went out until someone with selection access unlocks it. Undo steps back one change (or Ctrl or Cmd and Z), History lists who confirmed, locked or changed a side and lets you load any version back, and Audit History records every change to selection, squads and availability with the date and who made it. Moving a player in or out of a locked side asks first.' },
      { title: 'Drafts that save as you go', desc: 'Every change on the selection board is kept as a draft, so you can leave and come back. Nothing shows on Lineups, votes or BetterIQ until you confirm. When you confirm an XI, that team’s next game opens with the same side as a starting point.' },
      { title: 'Two-day games, weekend by weekend', desc: 'A two-day game shows both of its dates. Players answer for both weeks, week one only, week two only or not available, and a player free for one weekend gets their own colour on the Selection board, the Whiteboard and the matchday overview. A player can also be picked for two games on the same day when the start times do not clash.' },
      { title: 'Your competition’s rules, written down once', desc: 'Set what your competition requires: who is old enough for each division (measured from a date you choose), how many overseas players may be named, how many overs a young quick may bowl, what qualifies a player for a final. Make each rule a warning or a bar, and give a cleared player a permit against one rule.' },
      { title: 'Email the confirmed side', desc: 'Send the confirmed XI to the captain as a team sheet in batting order, with each player’s mobile, and tell each selected player the match details. Switch on the automatic send and it goes out when a side is confirmed, once only. Players under 18 are not emailed directly.' },
      { title: 'Squads that cover several teams', desc: 'One squad can serve the 1st and 2nd XI, the next the 3rds, and so on, with each game ranked by its own team’s XI number. Export every squad as a CSV or a one-page PDF to print, and scroll back through a team’s earlier sides on Past Lineups.' },
      { title: 'Best-player votes', desc: 'Collect votes after every game from the same link players already use, and the count keeps itself. Run as many medals as you like, such as a Club Champion on 3-2-1 beside a Colts Medal on 5-4-3-2-1. Each has its own voters, ballot, tie rules and closing time, and you can weight votes by grade so a 12 game grade and an 18 game grade are fair against each other.' },
      { title: 'The count, round by round', desc: 'A season leaderboard with every player’s points, their 3s, 2s and 1s, how they have moved since last round and a race chart across the top five. Read it for the whole club or one grade at a time.' },
      { title: 'Presentation mode', desc: 'Put the count on the screen at the awards night and reveal it a round at a time, so the room follows the run home instead of reading the winner off a spreadsheet.' },
      { title: 'One voting link', desc: 'A player opens the voting link, finds their name, enters their PIN and lands on the next game they played that is open for voting. After each ballot it offers the next one. A captain can hand the counting for a team to someone else, and a level week is settled on countback.' },
      { title: 'Net sessions', desc: 'Run Thursday nets off a rotation timer. A session runs on every device it is open on, so the phone by the nets and the laptop in the clubroom show the same queue and clock. Players check themselves in by scanning a QR code or tapping an NFC tag on the way in, and you can set a session to one or more squads.' },
      { title: 'Fixtures and ladders', desc: 'Your fixtures grouped by round and synced from the association, plus live grade ladders for every team.' },
      { title: 'A card for every player', desc: 'Role, batting and bowling, recent form, availability for the next month and net attendance, all on one editable player card.' },
      { title: 'Fines', desc: 'Switch Fines on for a squad and enter the session after a game, picking from your own fine list. A dashboard shows the pot, what is still to collect and who owes most. Set a maximum per player per session, record payments, and download a PDF report for any period. Players see their balance and how to pay on their own page.' },
      { title: 'Junior Rotation', desc: 'Save a group of kids by name and it hands you a batting order and fielding positions every game, leaning towards whoever has had fewer turns so it evens out over the season. Edit anything by hand, lock the game, print a one-page sheet for the clipboard and share it with parents on a link. It works for tee ball sides that are not on Cricket Australia, and a coach can be given Junior Rotation without the rest of BetterSelect.' },
    ],
    note: 'BetterSelect runs off the same player database as your stats, so your squads, form reads and profiles stay current without exporting anything between tools.',
    screenshot: '/marketing/modules/betterselect-selection.jpg',
    showcase: [
      {
        src: '/marketing/modules/betterselect-whiteboard.jpg',
        headline: 'Every team for the day on one board.',
        body: 'Each team playing that day is a column beside a pool of everyone not yet picked. Drag a player from one team to another, or into and out of the pool, and every team saves as its own draft until you confirm. Two-day games show who is free for each weekend.',
        points: [
          'Every team side by side with the pool',
          'Drag between teams, or tap on an iPhone or iPad',
          'Locked sides are tagged and ask before they change',
          'W1 and W2 markers for two-day games',
        ],
      },
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
      { src: '/marketing/modules/betterselect-locked-history.jpg', caption: 'Selection History: every confirm, lock and change' },
      { src: '/marketing/modules/betterselect-rules.jpg', caption: 'Selection rules, set as warnings or bars' },
      { src: '/marketing/modules/betterselect-votes-medals.jpg', caption: 'Several medals, each with its own ballot and weighting' },
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
      'BetterSocials runs your club’s public website and a post designer that turns your match data into share-ready graphics: lineups, fixtures, results, scorecards, player of the match, team of the week, milestones and more. Pick a layout and the post fills itself from your own data, with your sponsors already on it. Make it square, portrait or a story, and download a crisp PNG.',
    highlights: [
      'Your public, club-branded website',
      'Lineups, fixtures, results, scorecards & more',
      'Posts auto-fill from your match data',
      'Square, portrait and story sizes',
      'Your club colours, crest, fonts & sponsors',
    ],
    features: [
      { title: 'Your club website', desc: 'A fast, modern, club-branded public site — news, galleries, sponsors, honour boards and your live stats, all in one place.' },
      { title: 'A post for every match-day job', desc: 'Lineup, fixtures, results, final score, full scorecard, player of the match, team of the week, milestones, announcement, toss and events. One designer for the whole weekend.' },
      { title: 'A layout for every post', desc: 'Dozens of designs across the types: hero lineups, trading-card grids, side-numbered XIs, the Team Sheet, Split Poster, Match Day Card and Round Cover lineups, broadcast or app-style scorecards, Glass Card results, Giant Type announcements and more.' },
      { title: 'Square, portrait or story', desc: 'Make a post at 1080 by 1080, 1080 by 1350 or 1080 by 1920. Each layout has its own portrait and story design, so a tall post reads as a tall design and not a square one stretched.' },
      { title: 'Auto-fill from the match', desc: 'Your scorecard fills itself from your own synced match data. Build a Final Score from your Games page, or paste one match link into a fixtures or results post and every grade’s game that weekend comes in. No retyping of names and figures.' },
      { title: 'Team of the Week and Team of the Round', desc: 'Score every completed match in a period with the same points as Player of the Match and put the best performers on one post, for juniors, seniors or all teams. Team of the Round also counts games still being played, so you can post before the last game ends.' },
      { title: 'Milestones and debuts', desc: 'Tick the milestones you want from everything your club has recorded, such as a 100th game, 1,000 career runs or a 50th wicket, and they go on one post. Lineups can tag a player as making their debut, checked against the club’s records.' },
      { title: 'Your sponsors on every post', desc: 'Every new post starts with your sponsors along the bottom, resized to fit however many logos there are. Tick sponsors on or off, choose a light, dark or no backing panel, and give a team its own.' },
      { title: 'Layers you can move', desc: 'Every part of a layout is a layer: the headline, the sponsor strip, the crest and your own photos and logos. Reorder them, drop a photo behind the headline or over the crest, and give each element its own colour and words.' },
      { title: 'Your own photos and designs', desc: 'Cut a player out of a photo to remove the background, frame a hero photo inside the post, or upload your own background and it shows as it is. Prefer Canva? Bring in a design or a template from the BetterCricket Canva app and the live club data fills it in, for any post type.' },
      { title: 'On-brand by default', desc: 'Your crest and club colours, a choice of display fonts including your own, and a dark or light finish.' },
      { title: 'One-tap export', desc: 'Download a crisp PNG, ready to post to Instagram, Facebook or X. A scorecard can also split into two square posts, one for each team. Send any post to the club room TV with one button.' },
    ],
    comingSoon: ['Scheduled & auto-posting after a result', 'Auto-generated match summaries'],
    screenshot: '/marketing/modules/bettersocials-lineup-hero.jpg',
    showcase: [
      {
        src: '/marketing/modules/bettersocials-lineup-card.jpg',
        headline: 'Thirteen lineup designs. One team sheet.',
        body: 'Pick the layout that suits the occasion: a hero shot, a trading-card grid, a brutalist list, a festival poster or a full-height Team Sheet. Everything comes out in your colours, with your crest and your sponsors, in the display font you choose.',
        points: [
          'Thirteen lineup layouts',
          'Club colours and crest applied automatically',
          'Display fonts, with a dark or light finish',
          'Downloads as a sharp PNG',
        ],
      },
      {
        src: '/marketing/modules/bettersocials-sizes.jpg',
        headline: 'Square, portrait or story.',
        body: 'Make the same post at 1080 by 1080, 1080 by 1350 or 1080 by 1920. Each layout has its own portrait and story design, so a tall post reads as a tall design and not a square one stretched. Your sponsors are already on the post when you open it.',
        points: [
          'Three sizes from one layout',
          'A design for each size',
          'Sponsor strip added for you',
          'A scorecard can split into two squares',
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
      { src: '/marketing/modules/bettersocials-totw.jpg', caption: 'Team of the Week, scored from every grade’s scorecard' },
      { src: '/marketing/modules/bettersocials-milestones.jpg', caption: 'A Milestones post from the ones your club has recorded' },
      { src: '/marketing/modules/bettersocials-layers.jpg', caption: 'Every part of a layout is a layer you can move' },
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
      'BetterAdmin is your club’s back office on top of one member directory. Fees that allocate themselves, bulk email, stock and assets, the volunteer roster, committee meetings with minutes and motions, a strategic plan you can track, and a season diary of every job that comes around each year. All of it works off the same player database as your stats, so nothing needs exporting between tools.',
    members: ['Directory', 'BetterFees', 'BetterComms', 'BetterMerch', 'Committee', 'Roster', 'Club Diary'],
    highlights: [
      'One member directory for the whole club',
      'Auto-allocating match-fee payments',
      'Volunteer roster, coverage and hours',
      'A season diary of the club’s annual jobs',
      'Committee meetings, minutes and motions',
      'A strategic plan tracked against the work',
    ],
    features: [
      { title: 'One member directory', desc: 'Every player, parent, life member, volunteer and sponsor contact in one list, built from your stats data rather than typed in again. A person can be several kinds of member at once, such as a senior player and a parent. Filter by membership type, gender, squad or tier, by who is still playing, or by who you are missing an email address for. Shirt numbers and kit sizes sit on the person.' },
      { title: 'Automatic fee allocation', desc: 'A recorded payment settles games oldest-first, in full while the money lasts; the boundary game shows part-paid. Edit days played and it re-allocates itself.' },
      { title: 'Always-correct status', desc: 'Per-game Paid / Part-paid / Unpaid is derived on read — there’s no stale flag to keep in sync.' },
      { title: 'Credit & waivers', desc: 'Overpay and the balance rolls forward as credit; waive a match-day fee with a note. Membership and match-fee buckets stay separate, and Accounts lists who owes membership and who owes match fees on their own, with a CSV of whoever is listed.' },
      { title: 'Volunteer roster', desc: 'Roster the canteen, the bar and the gate week by week, track who is available, and confirm the week once it is done. An area holds several roles, such as umpires, scorers and team managers, each with its own qualification. A Coverage view shows how many shifts are still open on the days you care about, with a best-fit volunteer ready to assign, and a Match day board shows one day at a time. Confirmed shifts post straight to the club’s hours ledger, with paid work kept apart from volunteer work for your grant applications.' },
      { title: 'Committee & meetings', desc: 'Run the meeting from the agenda itself: mark attendance, put motions and votes against the item being discussed, hand out actions with owners, and type the minutes as you go. A motion records who moved it, who seconded it and the vote as it happens. Download the minutes as a Word document or a PDF on your own letterhead. Agendas group into sections and there are starter templates for an AGM or an ordinary committee meeting.' },
      { title: 'Season club diary', desc: 'The jobs that come around every year, laid out across your season so nothing is remembered the week it was due. Affiliation fees, the AGM, insurance and licence renewals, the tax return and the ground work, each with an owner, a due date and a budget.' },
      { title: 'Committee roles that hand over', desc: 'Positions, terms and who holds what, so the roles carry over at the AGM rather than living in one person’s head. A job can be owned by the seat instead of the person, and it moves with the seat.' },
      { title: 'A strategic plan you can track', desc: 'Group your objectives under the club’s own pillars, give each one an owner, a budget and a due date, and watch the actions serving it report back. Every theme, objective and action shows how far the work has got and how the money is going, each against where it should be by now. A starter plan is one button, so nobody faces a blank page.' },
      { title: 'Committee documents', desc: 'Keep quotes, policies and reports against the meeting or the action that called for them, either as a link or an uploaded file, with uploads readable by your office bearers only if you want it that way.' },
      { title: 'Bulk email (BetterComms)', desc: 'Newsletters and announcements to your member database — contacts come straight from your players, with Spam-Act-compliant unsubscribes.' },
      { title: 'Stock, assets and facilities', desc: 'Track playing kit and canteen stock, what has been issued to who, and what is still owed. Equipment lives in one asset register with its purchase cost and service dates, and the club diary, events and facilities calendars have a Year view.' },
      { title: 'Certificates and notifications', desc: 'A lapsing certificate or accreditation gets a notice when it enters the notice period, a final reminder close to the date and another the day it lapses. A Notifications screen lets the club choose what it is told about, by email, in the app or both.' },
      { title: 'Give each person only what they need', desc: 'The Primary Admin can limit a colleague to one module, or choose every menu item as Off, View or Manage. A treasurer can be given Fees alone, and a coach can be given a screen to look at without changing anything.' },
    ],
    screenshot: '/marketing/modules/betteradmin-overview.jpg',
    showcase: [
      {
        src: '/marketing/modules/betteradmin-roster-coverage.jpg',
        headline: 'See which shifts are still open.',
        body: 'The Coverage view lists every unfilled shift for the days you pick, each with a best-fit volunteer ready to assign in one tap. Areas hold several roles, such as umpires, scorers and team managers, and each role can need its own qualification.',
        points: [
          'A button for each day, or the full week',
          'A best-fit volunteer ready to assign',
          'Roles with their own qualifications',
          'Confirmed shifts post to the hours ledger',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-meeting-room.jpg',
        headline: 'Run the meeting from one screen.',
        body: 'Mark attendance, work down the agenda and put motions and votes against the item being discussed. A motion records who moved it, who seconded it and the vote as it happens, and the minutes download as a Word document or a PDF.',
        points: [
          'Attendance, agenda and minutes together',
          'Mover, seconder and a vote table on every motion',
          'Actions handed out with owners',
          'Minutes as Word or PDF',
        ],
      },
      {
        src: '/marketing/modules/betteradmin-strategic-plan.jpg',
        headline: 'See how the plan is actually going.',
        body: 'Every theme, objective and action shows two bars: how far the work has got, and how the money is going against it. An upright mark shows where each should be by now, so a bar short of its mark is behind.',
        points: [
          'A schedule bar and a budget bar on every line',
          'A mark for where it should be by now',
          'Themes, objectives and actions in one tree',
          'A starter plan in one button',
        ],
      },
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
    gallery: [
      { src: '/marketing/modules/betteradmin-permissions.jpg', caption: 'Choose what each person can open: Off, View or Manage' },
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
      { title: 'Scouts the grade you are playing', desc: 'Open a 3rd grade fixture and you get their 3rd XI, not their whole club with the 1st XI’s numbers mixed in. Grade type and match type filters apply, and the game plan names the filters it was counted under.' },
      { title: 'Who they have named', desc: 'BetterIQ reads the opposition’s team list for the game and sets each named player against what you have already scouted: runs, wickets and form, and their record in that grade and the one beside it. It tells you whether their danger player is in the side, and flags a player coming up from a lower side.' },
      { title: 'Ask IQ', desc: 'Ask a question in plain words, such as who to pick or how to beat a side. Ask IQ reads the XI you have confirmed in BetterSelect, can judge a game that has been played and give you a 3-2-1, and asks you a question back when the answer would change the numbers, like which grade or which format.' },
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
      { src: '/marketing/modules/betteriq-ask-iq.jpg', caption: 'Ask IQ asks you a question back when the answer depends on it' },
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
      { title: 'It runs itself', desc: 'Set the season up once and rounds build themselves from your draw, across the men’s and women’s programs, and a fixture added or moved later shows up on its own. Points settle after each weekend’s sync, and the ladder keeps itself current for the rest of the summer.' },
      { title: 'Live while the games are on', desc: 'Scores update every 10 minutes during the day, so each player’s points, each team’s round score and the ladder move as the games are played. A Live chip says which round it is and when the scores were last checked.' },
      { title: 'See everyone’s team once a round locks', desc: 'Rounds lock one hour before the first match, in the club’s own timezone. After that, tap any team on the ladder or in a league to see the side it locked, with each player’s points, the captain and any chip played, or flick through every team as a stack of cards.' },
      { title: 'Prices that move with performance', desc: 'A player who scores well goes up after the round and one with a quiet round goes down. A green or red arrow beside the price shows the movers, and an Insights screen lists the top players, the most traded and the biggest risers and fallers for any round.' },
      { title: 'Round winners and sharing', desc: 'The ladder has a Round winners tab showing who won each scored round and how many each team has won. My Team can be read as player cards, and any team or player card can be shared as an image.' },
      { title: 'You choose what counts', desc: 'Pick which competitions and grades count towards scoring, let late joiners start level with the lowest team and score from the next round, and take back a round that was settled by mistake.' },
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
      { src: '/marketing/modules/betterfantasy-teams-cards.jpg', caption: 'My Team as player cards' },
      { src: '/marketing/modules/betterfantasy-insights.jpg', caption: 'Round Insights: top players, trades and price movers' },
    ],
  },
]

export function moduleBySlug(slug) {
  if (slug === CORE_MARKETING.slug) return CORE_MARKETING
  return MODULES_MARKETING.find((m) => m.slug === slug) || null
}
