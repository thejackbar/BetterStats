export default {
  version: 'v9.54.2',
  date: '2026-08-29',
  sortKey: '2026-08-29T14:00:00Z',
  title: 'An uploaded game brings its own season with it',
  items: [
    'Uploading a scorecard from an era your club has no season for now creates that season, names it the way the rest of your list is named, and files the game under it. A 1974 card at a club whose seasons start in 1996 used to go in under whatever the dropdown happened to offer, and could then be found by no filter.',
    'The grade comes with it. A season made for an old card starts with no grades at all, so the grade named on the card is created inside it rather than the game going in ungraded.',
    'Picking a season the match date does not fall in now says so, naming both the season chosen and the one the date belongs to. It is still allowed, just no longer silent.',
    'Correcting a date the reader misread moves the game to the right season with it.',
    'One rule for which season a date belongs to, applied by the server. The upload screen had its own and the two disagreed about a July or August match.',
    'For games already filed wrongly, a club admin can ask us to run the repair — it moves each one to its own season and carries its grade across.',
  ],
}
