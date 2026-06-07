export default {
  version: 'v1.4.4 Beta',
  date: '2026-06-07',
  sortKey: '2026-06-07T14:00:00Z',
  title: 'Import Stats — clearer column & player matching',
  items: [
    'The “match your columns” step now spells every field out in full (e.g. “Catches (wicketkeeper)”, “No balls”, “Five-wicket innings”) instead of cramped abbreviations, so it’s obvious what each row maps to.',
    'Colour-coded each row so it reads left-to-right: the green name is the BetterStats field, the white dropdown is your column. A matched row turns green.',
    'Season now lives in its own block and only appears when you choose “Season by season” — for career totals it’s clearly marked as not needed, with a one-click switch. Season is required (and prompts you) when importing season-by-season.',
    'Player matching now understands “Surname Initial” sheets (e.g. “Camarda F”): it matches on an exact surname plus first-name initial, so these land in “Review close” to confirm instead of all defaulting to brand-new players. Middle names on our side still match, and a surname with no matching initial correctly stays a new player.',
    'New one-click “Confirm single matches” button in Review close — accepts every row that has exactly one suggested player in one go (often hundreds), and leaves the rows with more than one option for you to pick. Big time-saver when matching a large roster.',
    'No fields were missing — Wides, No balls, wicketkeeper catches and run-outs were always there; they’re just easier to find now.',
  ],
}
