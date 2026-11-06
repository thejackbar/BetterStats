export default {
  version: 'v9.140.0',
  date: '2026-11-06',
  // Above v9.139.9.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T09:00:00Z',
  title: 'A club picking itself on /trial now sees its own dashboard',
  items: [
    'The season page a visitor reaches from /trial or an email now looks like the club dashboard a paying club has: the same menu bar, the club crest, a header with the season, tiles, Top batters, Top bowlers, and a Season best card with the highest score, best bowling figures and fielding.',
    'The page takes the club\'s colours. The accent comes from the main colour in its logo, and the page sits on a light or dark background depending on the logo. A club whose logo has no colour keeps the BetterCricket green on dark. Visitors can flip light and dark themselves.',
    'Every menu item, tile and row opens a short card saying what that part of the site holds for the club, with the Claim button. Nothing links to a screen we have no data for.',
    'The line "Every player\'s career, back to 1975" is gone. It came from the first season Play-Cricket lists, which is not what the line meant.',
    'New script backfill_club_teaser_themes reads each already-pulled club\'s logo once (dry run by default, paced, honours the Stop switch, --ignore-stop to run anyway). New pulls do this themselves. It changes no snapshot and no picture.',
  ],
}
