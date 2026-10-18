export default {
  version: 'v9.122.0',
  date: '2026-10-24',
  // Above v9.121.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-24T20:00:00Z',
  title: 'Choose exactly which menu items someone can open, and whether they can change them',
  items: [
    'On Club Users, the Primary Admin now has a third choice for each person: Choose items. Every menu item is Off, View or Manage, grouped by module. Each module also has All off, All view and All manage buttons.',
    'View lets someone open a screen and look without changing anything. Manage lets them change it as well. In BetterSelect the screens show up read only for a View person. In the other modules the screen still shows its buttons, and saving is refused with a message that says they have view only access.',
    'BetterSelect is now split into the pieces you see in its menu: Squads and ladders, Availability, Selection, Nets, Fines, Settings and selection rules, Audit history, Fixtures and Votes. A person can have Availability without Fines, or look at Votes without managing them.',
    'Some items need another to work. Choosing Selection also turns Availability on at View, and the screen tells you before you save. An item that another chosen item needs stays on.',
    'A person with chosen items sees a tile for each module they can open something in, and nothing else on the dashboard. They still cannot see Settings, Users or Plan & Billing.',
    'Everyone still starts with access to everything, and nothing changes for anyone until the Primary Admin limits them. Only the Primary Admin, or BetterCricket support, can change what someone can open.',
    'Known gaps: Ask BetterIQ and the import and email previews count as changes, so a person with only View of those cannot use them yet. Fees, Emails and Import Stats each open several screens from one switch.',
  ],
}
