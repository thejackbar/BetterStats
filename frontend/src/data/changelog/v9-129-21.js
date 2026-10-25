export default {
  version: 'v9.129.21',
  date: '2026-10-25',
  // Above v9.129.20's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T08:00:00Z',
  title: 'Fantasy: fix rounds that no longer match the draw',
  items: [
    'Fixed: Applecross\'s games of 24 and 25 October were not counting in any Fantasy round, however often the scores were synced. Round 2 was stored as 10 to 11 Oct and round 3 as 17 to 18 Oct, both already scored, while the draw has round 2 as 10 to 18 Oct and round 3 as 24 Oct to 1 Nov. A game outside every round\'s dates scores for nobody, and a scored round was never rewritten when the draw changed.',
    'New: the Fantasy overview now shows when a scored round\'s dates differ from the draw, with both sets of dates, and a Fix round dates button. A round that only gets longer is scored again with its extra games. A round that moves to different games is taken back out of settlement and shows running points for them.',
    'The button is refused, with the reason, when a chip, transfer, point, queued transfer, head-to-head result or typed-in score hangs off a round it would move. Managers who joined after that round was settled keep their free transfer.',
  ],
}
