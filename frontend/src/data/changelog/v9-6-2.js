export default {
  version: 'v9.6.2',
  date: '2026-08-05',
  sortKey: '2026-08-05T20:00:00Z',
  title: 'The roster loads again, and three smaller fixes',
  items: [
    'The Roster failed to load with a server error for any club that had recorded a volunteer\'s available days. The Volunteers screen saves those days by name ("Monday") while the roster expected numbers, and one name was enough to bring down the whole page. It now reads either, and a day it cannot make sense of costs that day rather than the roster.',
    'The left menu jumped back to the top whenever you scrolled down and clicked an item. It stays where you left it.',
    'Club Diary\'s season plan said there were no tasks while the full diary editor showed a full calendar. It was reading the wrong field and quietly showing nothing.',
    'Comms has menu items for Lists, Segments, Templates and Email settings. Audiences has gone from the menu, since an audience is the list or segment you pick while writing an email rather than somewhere you go.',
  ],
}
