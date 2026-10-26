export default {
  version: 'v9.129.30',
  date: '2026-10-26',
  // Above v9.129.29's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T18:00:00Z',
  title: 'The player page link no longer picks a name for the next person',
  items: [
    'If you opened your own player page from a "My page" link or a vote reminder and then copied the address from your browser to share it, that address had your name in it, so everyone who opened it landed on your sign-in and had to tap "This isn\'t me".',
    'The player page now clears your name from the address bar as soon as it has used it. Copying the address after that gives the plain club link, which picks nobody and asks each person to find their own name.',
    'In BetterSelect, Availability, Self-service link, the shareable link now says it is the one to share, and to copy it from there and not from the address bar.',
  ],
}
