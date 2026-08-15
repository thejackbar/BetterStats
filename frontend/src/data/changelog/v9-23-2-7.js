export default {
  version: 'v9.23.2.7',
  date: '2026-08-15',
  sortKey: '2026-08-15T09:00:00Z',
  title: 'Undoing a large historical import looked like it wasn\'t doing anything',
  items: [
    'UNDO ALL and UNDO JUST THIS PLAYER on Import Stats\' past-imports list gave no feedback while working — for a big import (hundreds or thousands of rows), the request checking every affected player before it\'s safe to remove them can take a real few seconds, and with nothing on screen it read as broken.',
    'Both buttons now show a spinner and disable themselves while the undo is running, so a slow-but-working undo looks like one.',
  ],
}
