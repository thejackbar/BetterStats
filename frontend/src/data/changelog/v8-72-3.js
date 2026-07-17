export default {
  version: 'v8.72.3',
  date: '2026-07-17',
  sortKey: '2026-07-17T14:00:00Z',
  title: 'Em dashes are now actually stripped from AI text, not just asked nicely',
  items: [
    'The prompt instruction alone wasn\'t enough. Claude kept slipping "—" into yearbook narratives and BetterIQ Ask answers even when told not to.',
    'Both now run through a cleanup step that swaps any em or en dash for a comma before the text is saved or shown, so none reach the page regardless of what the model actually wrote.',
  ],
}
