export default {
  version: 'v9.133.1',
  date: '2026-10-28',
  // Above v9.133.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-10T12:00:00Z',
  title: 'Player Cards: make a pack in a minute, and Match Day packs only on match days',
  items: [
    'New: admins can make a pack in a minute. Name it, pick how good it is, choose how many each player gets and who gets them (everyone, or players you pick), and they are in players\' hands the next time they open their page.',
    'New: pack quality. Six steps from Standard to Legendary. Each step guarantees more Rare or better cards, leans harder to Epic and Legendary, and turns up special cards more often. Scheduled packs, like each day of a Test match, take a quality too.',
    'The make-a-pack form replaces the old Scheduled packs form. Scheduling is still there: choose "on a day" and pick the days.',
    'Fixed: Match Day packs went out on days that were not match days. A game played over two Saturdays counted the days in between. They now go out only on a fixture\'s own days, the first and the last.',
  ],
}
