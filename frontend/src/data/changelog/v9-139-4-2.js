export default {
  version: 'v9.139.4.2',
  date: '2026-11-04',
  // Above v9.139.4.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T23:45:00Z',
  title: 'Modules you add part way through the year renew with BetterStats',
  items: [
    'Changed: when a club that already has BetterStats buys another module on the Account page, the price is prorated up to its BetterStats renewal date, and the module then renews on that date each year. Before, it was quoted a full year from the day of payment. The quote shows the days it covers and the renewal date. Modules added this way take no discount code.',
    'This works whether the club first took BetterStats alone or several modules by bank transfer and had a Super Admin set them Active. Pay-by-invoice clubs get the same part-year price on their invoice.',
    'New: when a Super Admin sets a module Active for a club by hand, its renewal date now defaults to the club\'s BetterStats renewal date, and the page tells you the prorated fee to collect (list price before GST, no bundle discount or code). Set several modules and they all land on the one date. A renewal date you pick yourself is kept, and a module that is already Active keeps its date.',
    'If BetterStats has no renewal date, or it has already passed, the module is still set Active and the page says it could not be lined up, so you can set the date by hand.',
  ],
}
