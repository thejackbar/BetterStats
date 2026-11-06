export default {
  version: 'v9.139.8',
  date: '2026-11-06',
  // Above v9.139.7's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-16T04:00:00Z',
  title: 'Pick your club on /trial and go straight to its season page; club pictures draw themselves',
  items: [
    'On /trial, picking a club from the search now opens that club\'s season page when we have one, with the claim button on it. A club we have no page for, one that is already on BetterCricket, and a lookup that fails all behave as they did before.',
    'Club Directory, teaser panel: a new "Draw pictures automatically" tick. When it is on, the club pictures for emails and ads are drawn a batch at a time as the crawl finishes with each club, and it carries on after a restart. A club that cannot be drawn is left alone for six hours rather than retried every few minutes.',
    'Pictures are only drawn for clubs the crawl has finished with. A club still on the old snapshot is counted as waiting on the crawl, because its picture would be thrown away when the club is re-pulled.',
    'Drawing is faster: the three sizes for a club are taken together, and two clubs at a time, with at most four pages open at once.',
  ],
}
