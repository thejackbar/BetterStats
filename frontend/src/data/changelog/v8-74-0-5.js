export default {
  version: 'v8.74.0.5',
  date: '2026-07-19',
  sortKey: '2026-07-19T18:00:00Z',
  title: 'Usage page: live-feed dot matches "Active now", plus mobile admin menu no longer needs scrolling',
  items: [
    'The green dot next to the newest row in "Live page views" used to fade after 15 seconds, while the "Active now" count above it stays lit for 5 minutes. That made the two look out of sync even when nothing was wrong. The dot now uses the same 5-minute window as the count it sits under.',
    '"Visitors" on the Usage page already counts unique people, not raw page loads: a return visit from the same browser is not counted a second time.',
    'On a phone, the admin header used to run wider than the screen, so the menu button sat off to the right and needed a scroll to reach. The header now shows only the logo and menu button on mobile; club switching, notifications, "view public page", "setup guide" and log out moved into the slide-out menu itself, so no admin screen needs horizontal scrolling any more.',
  ],
}
