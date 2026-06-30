export default {
  version: 'v8.45.0',
  date: '2026-06-30',
  sortKey: '2026-06-30T09:00:00Z',
  title: 'Import player emails and phones from a spreadsheet',
  items: [
    'Player details can now be filled in from a spreadsheet. Upload a CSV or Excel file from the Players page to set emails and phone numbers in bulk, and add squad, role, batting hand, bowling or gender for anyone you have them for.',
    'Each row is matched to a player by name, the same way the stats importer works. An exact name links straight through, a close one is offered for you to confirm, and a name we have no record of can be created as a new player or pointed at an existing one.',
    'Every change is shown before and after so you can check it before saving. A blank cell is left as it is, so a detail you leave out of the file is never touched.',
    'There are two templates to start from. The Excel one has built-in dropdowns for role, batting hand, bowling and gender, and lists your BetterSelect squads in the Squad column, so you pick the value instead of typing it. A plain CSV is there too if you prefer.',
  ],
}
