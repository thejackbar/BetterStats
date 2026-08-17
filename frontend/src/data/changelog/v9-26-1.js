export default {
  version: 'v9.26.1',
  date: '2026-08-17',
  sortKey: '2026-08-20T04:00:00Z',
  title: 'Merge Duplicates finds short first names and initials',
  items: [
    'Merge Duplicates now suggests players whose records use a shorter first name or an initial, so "Brad K Mant" and "Mant, Bradley" are offered as the same person instead of sitting on the list as two separate players.',
    'These suggestions are labelled with what makes them a match and always need you to confirm them by hand. Two brothers, or a father and son, look exactly like this, so Bulk Approve still only ever merges pairs whose names are identical.',
    'A player you have renamed is now matched on the name shown on screen as well as the name that came from Play.Cricket, so a duplicate of a renamed player no longer goes unlisted.',
  ],
}
