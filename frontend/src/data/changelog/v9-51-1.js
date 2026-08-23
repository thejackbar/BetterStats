export default {
  version: 'v9.51.1',
  date: '2026-08-22',
  sortKey: '2026-08-23T05:00:00Z',
  title: 'Fixed: the Committee search box lost the cursor after every character',
  items: [
    'Typing in the search field on Meetings, Plans, Documents or Calendar threw the cursor out of the box after the first character, so nothing you typed landed. The row holding it was being rebuilt from scratch on every keystroke, which took the field with it. Fixed, and the suite now types character by character and checks the caret is still in the field after each one.',
  ],
}
