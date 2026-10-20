export default {
  version: 'v9.124.0',
  date: '2026-10-19',
  // Above v9.123.9's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-30T10:00:00Z',
  title: 'Card review: choose between the Cricket Australia scorecard and the club scorecard',
  items: [
    'A match that is stored twice, once from Cricket Australia and once from a file, a typed-in entry or a photo of the book, now has a Card review page under Clean your data. It sorts every such match into five groups: scores agree, small differences, scores differ, pairing looks wrong, and no Cricket Australia card. Each group opens as a list with one line per match.',
    'For each match you pick what the site shows: the Cricket Australia scorecard, the club scorecard, or the club numbers with Cricket Australia detail added where it fits. Nothing is deleted when you switch. Both versions stay stored, and every match has its own history with an Undo, on the Card review page and on the match page itself.',
    'The combined choice keeps the club\'s runs, wickets and result. It adds balls faced, bowler credits on dismissals, fall of wickets, partnerships, the opposition card and the "c Smith b Jones" text from Cricket Australia wherever the two cards agree on the batters, and lists whatever it left out. It shows a preview before it changes anything, and a later sync does not undo it.',
    'Where the two cards agree on every batter, wicket and the result, one bulk switch can move all of those matches to Cricket Australia at once. It shows a sample first, runs in batches, and can be undone as a batch. A match someone has chosen by hand, or changed since, is left exactly as they set it.',
    'Card review checks which card holds more. Where the scores agree but the club card holds something Cricket Australia\'s lacks (balls faced, dismissal credits, fall of wickets or partnerships), the match is left out of the bulk switch, marked "Club card holds more", and suggests keeping the club card or the combined choice. The overview says how many were held back and links to them.',
    'The pairing screen shows a better Cricket Australia match for a club card that looks linked to the wrong game, with how many batters the two share. You can re-link it, keep the link, or unlink it.',
    'A spreadsheet of every match with a difference (and every agreeing match the club card holds more of) can be downloaded from the Card review page, with a column for your choice and one for notes.',
  ],
}
