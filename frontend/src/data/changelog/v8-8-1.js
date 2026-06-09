export default {
  version: 'v8.8.1',
  date: '2026-06-09',
  sortKey: '2026-06-09T16:00:00Z',
  title: 'Consistent stat formatting across the whole app',
  items: [
    'Averages, strike rates and economy rates now always show two decimal places, everywhere they appear (e.g. 58.00, not 58 or 58.5).',
    'Large numbers get thousands separators once they pass a thousand — runs, matches, wickets and the like now read 1,000 / 12,480 instead of 12480.',
    'Overs are shown in proper cricket notation: the decimal is balls (0–5), a whole number of overs no longer trails a “.0” (37, not 37.0), and running totals add up over the six-ball boundary correctly.',
    'Stat lines are spelled out and spaced — “580 runs @ 58.00”, “3 wickets @ 12.00” — instead of cramped “580r@58.00”; no more bare “r”/“w” after a number. Standard cricket shorthand stays (best figures 5/28, scores 145/8).',
    'Recent-form runs now read as figures per game, and percentages (win rate, etc.) show as whole numbers.',
    'Fixed a few spots where bowling economy was computed by adding overs as plain decimals — it now divides by the true ball count, so economy is accurate as well as consistently formatted.',
  ],
}
