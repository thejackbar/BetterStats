export default {
  version: 'v9.25.2',
  date: '2026-08-17',
  sortKey: '2026-08-20T02:00:00Z',
  title: 'Two-day matches are charged as two days again, and Accounts stays on the season you picked',
  items: [
    'Every match was being charged as a one-dayer. The sync never recorded a game\'s format, so a two-day fixture looked the same as a T20 to BetterFees, which falls back to one day when it can\'t tell. Applecross\'s 5th Grade alone was short 26 match days for 2025/26.',
    'The format is now read from Cricket Australia per FIXTURE, not per grade, which is the only way it can be right: 5th Grade played 32 one-day and 26 two-day matches in the same season, so no single setting on the grade could have covered both.',
    'Existing seasons are corrected on the next Sync Now — the sync fills in the format for the games it already holds, not only new ones. Then press "Sync Match Days" on the Accounts page to rebuild the fee rows. A match day you have edited by hand, or one already paid, is left exactly as it is.',
    'The per-grade format breakdown on the Membership tiers page now reads "One Day×32 · Two Day×26" instead of "Unknown", so you can see what each grade actually plays before tagging it.',
    'Accounts no longer jumps to the newest season. Opening a member and coming back keeps you on the season you were working in, and the season is now part of the page address, so it survives a refresh and can be shared.',
  ],
}
