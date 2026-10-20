export default {
  version: 'v9.108.6',
  date: '2026-10-08',
  sortKey: '2026-10-08T13:00:00Z',
  title: 'A person who asked to be hidden is now kept hidden by the database itself',
  items: [
    'The hide belongs to the person, not to any one club, so it is now enforced where every club\'s player rows live. A row for a person on the removal list is hidden the moment it is created, whichever importer, sync or screen creates it, and it cannot be switched back on by an edit.',
    'This also covers any code written later. Before, each creator of a player had to remember to check the list; now none can forget.',
    'Anyone who had slipped through before is hidden on the next start. Putting someone back on request still works and restores every club\'s record.',
    'One limit stays: a hand-typed player has no participant id, so the database cannot tell who they are. Those are still caught by the name masking on public pages.',
  ],
}
