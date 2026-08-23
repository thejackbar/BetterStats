export default {
  version: 'v9.24.5',
  date: '2026-08-15',
  sortKey: '2026-08-15T06:30:00Z',
  title: 'Sales Workspace, Sales Lists',
  items: [
    'A new Sales Lists screen (Sales → Sales Lists) for importing a batch of clubs into the workspace in one go, and seeing where each one currently stands.',
    '"Import to Sales List" on Clubs Searched or Selected in the Wizard turns a filtered selection into a list: every matched club gets an open deal so it shows up in the queue immediately, matched to the Club Directory the same guid-first, name-fallback way that page already does.',
    'A list is a thin label, not a second record of a club: assignment, calls, notes and stage all still live on the one deal, so a club can sit in several lists and reads the same wherever it\'s viewed from. Re-importing a club already further along a deal (e.g. already Engaged from an earlier call) never pushes it back to Target.',
    'The Sales Workspace queue can be filtered to one list (?list_id=…), so assigning it is just: open the list, jump to the filtered queue, select, assign. Reusing the existing bulk-assign action rather than a second one.',
  ],
}
