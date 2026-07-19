export default {
  version: 'v8.73.3.1',
  date: '2026-07-19',
  sortKey: '2026-07-19T09:00:00Z',
  title: 'Setup Wizard: fixed the "Assign players to squads" button',
  items: [
    'Clicking ASSIGN PLAYERS on the wizard\'s squad-assignment step errored with "bsSquadAssign is not a function" — the step was calling an API method under the wrong name. It now uses the same call the Squads board does.',
  ],
}
