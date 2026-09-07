export default {
  version: 'v9.67.4',
  date: '2026-09-06',
  sortKey: '2026-09-13T18:00:00Z',
  title: 'A CricketStatz import no longer duplicates players you already have',
  items: [
    'The import was matching names by exact spelling only. Clubs hold their players surname-first ("Quinsee, Brad") while CricketStatz writes them the other way round, so it matched none of them and created a second record for every player already on your list — each with half a career, and both showing on your leaderboard.',
    'It now matches names the same way every other import page does, which reads "Quinsee, Brad" and "Brad Quinsee" as one person, and "Michael B. White" as your "Michael White".',
    'It will not merge on a guess. A bare initial is not an identity, and two of your own records sharing a name is usually a father and son, so those get their own record and are listed in the import notes for you to settle in Merge Duplicates.',
    'If you have already run an import and have duplicates, they can be merged in one pass — the club record you already had is the one kept, and it is undoable from Merge Duplicates.',
  ],
}
