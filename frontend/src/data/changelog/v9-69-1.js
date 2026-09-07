export default {
  version: 'v9.69.1',
  date: '2026-09-14',
  // Above main's v9.69.0 (2026-09-14T12:00:00Z), or SITE_VERSION never
  // reaches this release — the folder's highest sortKey is what it reads.
  sortKey: '2026-09-14T13:00:00Z',
  title: 'Shirt numbers, kit sizes, and minutes on your own letterhead',
  items: [
    'A player now has a shirt number, on their profile and in the Directory. It is stored exactly as you write it, so “07” stays “07”, and it is part of BetterStats — every club has one.',
    'Shirt size and pants size are recorded against the person in the Directory, so a coach, a scorer or a canteen volunteer can hold a polo size too. They are free text: “Youth 12”, “2XL” and “34” are all fine.',
    'Shirt numbers can be filled in from a spreadsheet through Import Player Details, alongside everything else on the profile.',
    'The Directory\u2019s own CSV import takes shirt size, pants size and shirt number too. A number goes to the player of that name \u2014 the preview says which one it found, or why it found none, before you commit.',
    'A sheet of kit sizes no longer adds a second record for a player you already hold: a new person row is linked to the player of that name.',
    'Committee minutes downloaded as Word or PDF are now headed by your club: a band in your own colours and your crest above the club name. A club with no crest gets the band on its own.',
  ],
}
