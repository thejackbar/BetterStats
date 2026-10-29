export default {
  version: 'v9.129.33',
  date: '2026-10-26',
  // Above v9.129.32.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T23:30:00Z',
  title: 'Fantasy My Team as player cards, a tidier player share card, and saved cards keep their fonts',
  items: [
    'New: My Team has a Sheet / Cards switch. Cards shows one card per player, grouped by role, with their photo, price and the points for the round. Tap a card for the same captain, vice and profile buttons the sheet has. Your choice is remembered.',
    'Changed: the player share card is redrawn. The front is a black-framed card in the club colour with the name and best club ranking up top and a band of the headline figures along the bottom. A hero photo fills the card, and a headshot sits smaller and centred in a ring. The back is a player details sheet with every figure in rows.',
    'Fixed: the share card read "Barendse," over "JACK". A name stored as "Last, First" now shows the first name over the SURNAME, and the saved image and share text use "First Last". The back no longer cuts off a long name or the club name.',
    'Fixed: saved card images (the new cards, the gameweek result and the invites) now carry the club fonts. They were being drawn in a plain fallback font because the exporter could not read the web fonts.',
  ],
}
