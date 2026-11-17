export default {
  version: 'v9.145.0',
  date: '2026-11-17',
  // Above v9.144.3.3's sortKey (2026-11-21T05:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T06:00:00Z',
  title: 'Unbroken and retired partnerships, and tagging premierships',
  items: [
    'Fall of wickets editor: tick "Last partnership unbroken" and the stand between the two batters still in is recorded against the match, scored off the card\'s total unless you type the end score.',
    'Fall of wickets editor: add a retirement with the score, the batter and how many wickets were down. The partnership ends there and the next batter comes in, so every stand after it pairs the right batters. A retired batter comes back once everyone else has batted.',
    'Where Cricket Australia wrote a retirement as a wicket (common on women\'s cards), the editor opens with it already moved into the retirements.',
    'Unbroken partnerships show with a * on the match page and the Records board, and open their match like any other stand.',
    'New admin page, Premierships: paste a play.cricket.com.au match link and tag the match as a grand final, a final or a normal game. A grand final your side won gives everyone on the team sheet the flag, linked to the match. Tick "We won" for a final washed out and taken on the ladder.',
    'The match page has a Premiers tick for club admins that does the same in one click.',
    'Tag a match as a final or a normal game to stop it counting as a grand final when the round name says otherwise.',
    'Partnership Records: a hand-typed record can now hold its match link, so it opens the scorecard from the Records board.',
  ],
}
