export default {
  version: 'v9.141.1',
  date: '2026-11-09',
  // Above v9.141.0's sortKey (2026-11-18T04:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T01:00:00Z',
  title: 'The email picture is now the club\'s own dashboard',
  items: [
    'The picture in the club season email is now a picture of the same season page a club sees after picking itself on /trial: the menu bar, the crest, the header, the tiles, Top batters, Top bowlers and Season best, in the club\'s colours and on a light or dark page to suit its logo. It replaces the BetterCricket season card in emails.',
    'Link previews (when the page is shared in a chat or on social media) keep the card, because the card has the shape those previews need. The two Meta ad sizes are unchanged and still show no player names.',
    'The picture drawer now also redraws any club marked as drawn whose email picture is missing from the media volume (for example after this change, a restore, or an unmounted volume), once nothing else is due. A club that keeps failing is left alone for six hours between tries.',
    'Each club now has four pictures drawn instead of three, about 10% more space on the media volume.',
  ],
}
