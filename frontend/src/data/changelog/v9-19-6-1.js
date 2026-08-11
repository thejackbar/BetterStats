export default {
  version: 'v9.19.6.1',
  date: '2026-08-11',
  sortKey: '2026-08-11T09:00:00Z',
  title: 'Fix: round-from-link fixtures & results found nothing off-season',
  items: [
    'Pasting a match link into Fixtures or Results said "No fixtures/results found for the current season" even for a real match, because the pull was still only searching your club\'s most recent season\'s grades. It now looks up the season the pasted match actually belongs to and pulls that round, whatever season it is.',
    'Fixed a grade sometimes showing two unrelated fixtures under one round. Round numbers aren\'t shared across competitions ("Round 3" can fall on a different weekend in each grade), so matching purely by round name was pulling in a different week\'s game from the same grade. Round matching is now scoped to the pasted match\'s own grade.',
  ],
}
