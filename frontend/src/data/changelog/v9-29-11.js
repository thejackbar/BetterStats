export default {
  version: 'v9.29.11',
  date: '2026-08-18',
  sortKey: '2026-08-25T22:00:00Z',
  title: 'Sales rep templates: rename freely in Comms without breaking the link',
  items: [
    'Renaming a template in BetterAdmin -> Comms -> Templates used to silently break the Sales Workspace\'s Send an email dropdown for it, and the next visit to Templates would reseed a fresh duplicate under the old name. The dropdown now links to the template by a stable id, not by its name, so it can be renamed however you like.',
    'A template linked to a Sales Workspace dropdown entry now shows which one, right there in Comms -> Templates, so it\'s always clear what a row is for regardless of what it\'s called.',
  ],
}
