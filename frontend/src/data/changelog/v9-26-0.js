export default {
  version: 'v9.26.0',
  date: '2026-08-17',
  sortKey: '2026-08-20T03:00:00Z',
  title: 'Filter the club dashboard by grade type and match type',
  items: [
    'The club dashboard\'s Gender filter is now Grade Type — Men\'s, Juniors, Women\'s, Masters — which is how the grade is classified rather than how a player is recorded. A woman playing in a men\'s grade no longer reads as women\'s cricket, and a grade does not disappear because someone\'s gender was never filled in.',
    'A new Match Type filter beside it: Two Day, One Day, T20. Pick a grade type and a match type together to get, say, the women\'s one-day figures.',
    'Both filters move the whole dashboard together — the win rate, runs, wickets and player counts, the top batters and bowlers, and the recent games list.',
    'The Captain filter is gone from the dashboard.',
    'A grade can now be several things at once on Admin → Grades. "Women\'s T20 Grade 2" is a women\'s grade and a T20 grade; an Under 14 girls\' side is both juniors and women\'s. Tick as many as apply on each row.',
    'Match type is worked out from the matches already played in each grade, so most clubs will find their grades are already labelled correctly. A grade we cannot place is left out of the Match Type filter rather than guessed into the wrong one.',
    'Fixed: grade names written the way clubs actually write them — "Under 14s", "U14s", "Year 9s", "Over 40s" — were being read as senior grades. Those junior and masters seasons were landing inside senior career averages. The singular spellings always worked, which is why it went unnoticed.',
    'Tidied up: the Gender and Captain filters also appeared on Players, Games and Ladders, where they had never been connected to anything. They are gone from those pages too.',
  ],
}
