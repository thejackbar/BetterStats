export default {
  version: 'v9.67.3',
  date: '2026-09-06',
  sortKey: '2026-09-13T16:00:00Z',
  title: 'A CricketStatz preview that does not guess your earliest season',
  items: [
    'The preview was reporting the wrong first season — it read the earliest date out of a list CricketStatz caps at 999 matches, so for a busy club it only reached back about a decade. One club showed 2014 when its history starts in 1953.',
    'It now reads your all-time record boards instead, which reach across your whole history, and says "back to at least" that year rather than stating one it cannot know. The first pass then reports exactly what it found.',
    'Grades brought in from CricketStatz are now classified as they are created, the same as every other import page. Without it your imported junior grades would have counted inside your senior careers.',
    'Imported seasons and grades are marked as not having come from a sync, which is what the rest of the app expects of anything entered or imported by a club.',
  ],
}
