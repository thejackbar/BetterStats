export default {
  version: 'v8.74.0.2',
  date: '2026-07-19',
  sortKey: '2026-07-19T15:00:00Z',
  title: 'BetterComms: fixed the mandatory footer rendering in a different font',
  items: [
    'The sender-id + unsubscribe footer BetterComms injects at the bottom of every email switched to whatever serif font the recipient\'s mail client defaults to, on any full-HTML template. It\'s appended right before </body> as a sibling of the template\'s own content table, so it never actually inherited the template\'s font, only <body> itself, which most templates don\'t set a font on. It now sets an explicit sans-serif font directly, matching the rest of the email.',
  ],
}
