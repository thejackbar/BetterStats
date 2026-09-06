export default {
  version: 'v9.64.1',
  date: '2026-09-07',
  sortKey: '2026-09-08T14:00:00Z',
  title: 'Fewer notes, and the grade grid keeps the matches it should',
  items: [
    'A club with a junior programme has a grade filter on by default. Yesterday that made six tabs carry a note about a filter nobody had turned on, on every visit. The notes now appear only once you pick something yourself; the default is already said once, in the header.',
    'Matches by grade was dropping Cricket Australia\'s counted matches for any season the moment a filter was on, even for a player with nothing to filter out. It now keeps them for a season where every match was inside the filter, and says how many seasons were left to the scorecards alone.',
    'Teammates and Captain now follow the filter like the rest of the profile. "Men\'s teammates" and "matches captained in one competition" are real questions, and they had been quietly ignoring the bar above them.',
    'A small mark on a tab label now tells you before you open it that the filter you picked will not narrow what is inside.',
    'The season table was being sent the grade type and match type and never the competition. It gets all three now.',
  ],
}
