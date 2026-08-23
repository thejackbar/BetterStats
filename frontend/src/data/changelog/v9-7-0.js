export default {
  version: 'v9.7.0',
  date: '2026-08-05',
  sortKey: '2026-08-06T02:00:00Z',
  title: 'Import Results: a club\'s whole results register, from a spreadsheet',
  items: [
    'BetterFootball has a new Import Results tool. Upload the results register your club already keeps, one row per match, however far back it goes, and it becomes real games sitting alongside the ones synced from PlayHQ, on the results page, in the club\'s win-loss record and in the records.',
    'It reads your headings for you. A sheet that calls its columns "HamGoal", "Opppoints" and "Column1" maps itself, and a results column with no useful heading is picked up from what is in it.',
    'You are shown what we read before anything is saved. Where the sheet does not add up. A score that is not six points a goal, a game recorded as a win with the scores level. The row is flagged with what is wrong. Fix it in your spreadsheet and upload again, or import it as written and keep your club\'s own figures.',
    'Cancelled and unscored rows are skipped. Forfeits come in as the win or loss they were, and byes can be kept on the record without ever counting as a game played.',
    'A game PlayHQ has already synced is left alone. Uploading a corrected sheet updates the same games rather than duplicating them, and the whole upload can be undone in one click.',
    'Seasons and teams from your sheet are matched to the ones your club already has, and the seasons that predate anything online can be created for the whole sheet in one press.',
  ],
}
