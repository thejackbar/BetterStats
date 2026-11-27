export default {
  version: 'v9.163.0',
  date: '2026-11-28',
  // Above v9.162.1's sortKey (2026-11-28T23:30:00Z). Check origin/main at merge time.
  sortKey: '2026-11-28T23:50:00Z',
  title: 'Teamwear ordering in BetterAdmin',
  items: [
    'New in BetterAdmin under Stock: Teamwear. Run each kit order round as a campaign, from shop setup through to packing bags for collection.',
    'Set up the shop range with supplier codes, sizes, pictures and the RRP. The price members see is the RRP plus your club markup (10% to start), rounded up to the next dollar. You can set your own price on any item.',
    'Members order on their Player Dashboard. One order covers the whole family, and an item can be for anyone with a typed name. Playing shirts take a number and name, training shirts a number and initials, all stored in capitals.',
    'A requested number is checked against the club register. A clash is flagged for the kit coordinator, and approving it writes the number to the player.',
    'After ordering closes, triage the round on a live table. Each product needs 10 units across all sizes; add club top-ups by size, and anything needing 9 or more top-ups per member unit is flagged as a suggested cut.',
    'Record the committee sign-off of the whole plan. Cut items come off every order and members see Not available this round. Change the plan later and the sign-off is cleared until you record it again.',
    'Payment requests go out with the amount, the due date and a SURNAME TEAMWEAR bank reference. Members can also pay by card through Stripe or a Square payment link.',
    'Upload your bank CSV and payments match on the reference. Reminders go on the days you choose, and an unpaid order is never cancelled for you.',
    'Once every order is paid or decided, lock the round and download the supplier order form: quantities by product code and size, plus a names sheet for each personalised item.',
    'When the kit arrives, the top-ups go into club stock in Inventory. Tick bags as packed and email members to collect. In-stock kit can also be sold through the shop at any time.',
  ],
}
