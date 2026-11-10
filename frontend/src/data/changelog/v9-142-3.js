export default {
  version: 'v9.142.3',
  date: '2026-11-10',
  // Above v9.142.2's sortKey (2026-11-19T06:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T07:00:00Z',
  title: 'A club whose trial ended is treated like a new club, not a paused one',
  items: [
    'A club whose free trial ran out (and never subscribed) no longer sees "This club page is paused". Its address now shows the same page a club we have never heard of gets, "Not on BetterCricket yet", with the way to get online.',
    'On the trial page that club no longer shows as already registered, so it can register again. Registering reuses the club it already has, so its players and games are still there and the earlier admins keep their access. The trial starts fresh.',
    'The button on that page now goes straight to the trial page with the club\'s name already in the search box, instead of the contact form. This is the same page any club we cannot find sees. A club staff switched off still gets the contact form.',
    'Clubs staff switched off, clubs with a cancelled or paused subscription, and clubs that pay or have a Stripe subscription still show as paused and still count as registered.',
  ],
}
