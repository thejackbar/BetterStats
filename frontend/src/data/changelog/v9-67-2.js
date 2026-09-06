export default {
  version: 'v9.67.2',
  date: '2026-09-06',
  sortKey: '2026-09-13T14:00:00Z',
  title: 'A CricketStatz import works out the job before it starts',
  items: [
    'The import now does a first pass to find which seasons your club actually played before it pulls anything, so it can tell you what it found — how many seasons, the years they span, how many matches, and roughly how long it will take.',
    'CricketStatz offers every season back to 1860 whatever the club, so most of that list is empty for anyone. One club came out as 73 seasons played from 167 offered, 1953 to 2025, and 3,556 matches.',
    'Because the real total is known before the pull starts, the progress bar now means something. It used to be measured against a total that grew as fast as it did, so it sat near full from the first season.',
    'Every candidate season is still checked rather than a guessed range. A club can have gaps in its history, and the shortcut of reading the span off the record boards would have missed one club\'s earliest season.',
    'Your history now arrives oldest first.',
  ],
}
