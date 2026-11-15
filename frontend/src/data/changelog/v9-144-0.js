export default {
  version: 'v9.144.0',
  date: '2026-11-15',
  // Above v9.143.12's sortKey (2026-11-20T20:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T21:00:00Z',
  title: 'Stock dashboard and Excel export for BetterMerch',
  items: [
    'New Stock dashboard under Stock in BetterAdmin. It shows what is on the shelf now, how stock has moved over time, and what is selling and what is not, on one page.',
    'Charts: stock on hand over time (units or value at cost), what went out each day or week (sold and issued to players, units or revenue), best sellers, apparel by size and by colour, and where the money is sitting by category.',
    'Four lists that need a look: out of stock, low stock against each item\'s reorder point, running low (fewer than four weeks left at its recent selling rate), and not selling (on the books 30 days or more with no sales in the window, with the cost tied up).',
    'A table of every item with units on hand, sold, selling rate per week, weeks left, value and revenue. Search it, filter it by type or status, sort it, and open a row to see each size and colour with when it last sold.',
    'Pick the window: last 30 days, 90 days, 6 months or 12 months. Stock figures are always as of today; sales and rates cover the window. Values use each item\'s cost and price as they are set now.',
    'Export to an Excel workbook with a sheet each for the summary, every stock line, sales by item, size, colour, stock over time and every movement. There is also a CSV of all stock movements.',
    'The history charts are worked back from today\'s count through the movements you have recorded, so a stocktake typed in today shows a short history. It fills in as you record sales, deliveries and stocktakes, or sync Square.',
    'Items with no cost or no sell price, and sales with no price recorded, are listed on the page so you can see why a figure is lower than expected.',
  ],
}
