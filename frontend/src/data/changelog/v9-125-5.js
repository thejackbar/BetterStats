export default {
  version: 'v9.125.5',
  date: '2026-10-20',
  // Above v9.125.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T13:00:00Z',
  title: 'Card review: wrong links are found even where a card was chosen by hand',
  items: [
    'Possible doubles skipped a club scorecard linked to the wrong game if someone had already chosen which card the site shows for it. Choosing a card does not say the link was right, so those are now offered too, and moving the link keeps the choice that was made. Only a link someone confirmed as "the same match" is left alone.',
    'This corrects v9.125.4, which said any link chosen by hand was left alone. The bulk fix now includes these as well.',
  ],
}
