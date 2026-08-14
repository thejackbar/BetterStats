export default {
  version: 'v9.23.2.6',
  date: '2026-08-14',
  sortKey: '2026-08-14T18:00:00Z',
  title: "Import Stats didn't recognise a dotted initial as an abbreviation — \"K. Adair\" read as a stranger, not \"Kevin Adair\"",
  items: [
    'A historical stats sheet nearly always writes an abbreviated first name with a trailing dot — "K. Adair", "R.J. Manning" — but the importer\'s abbreviation check only recognised a bare single letter with no punctuation ("K Adair"). The dot made it two characters, so the check silently failed and the row was treated as a brand-new person instead of a likely match for the existing "Kevin Adair".',
    'Checked against a real ~2,100-row club history: roughly half its rows use a dotted initial, and 1,021 of them were falling through this gap — each one on track to mint a new, career-fragment player rather than get offered up as a match to confirm.',
    'Fixed by treating a dot the same as a space before checking for a single-letter initial, matching how the rest of the name-matching already treats dots. Those rows now correctly surface as a close-match candidate to confirm, instead of silently becoming a new player.',
  ],
}
