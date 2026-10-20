export default {
  version: 'v9.106.33',
  date: '2026-10-06',
  sortKey: '2026-10-06T16:00:00Z',
  title: 'Club Admins can switch between linked clubs',
  items: [
    'Super Admins have a new Linked Clubs page under Better HQ, in Clubs & Data. Pick two clubs and link them, add a third to the same group, or unlink a club. Linking and unlinking are written to each club\'s activity log.',
    'A Club Admin whose club is linked sees a "Your clubs" panel on their dashboard and a club switcher in the top bar (in the menu on a phone). Picking a club reloads the admin app inside that club. A banner on every page says which club you are working in, with a link back to your own.',
    'Clubs that are not linked to another club see none of this. Club Members do not get the switcher, only Club Admins.',
    'Each club keeps its own trials and subscription. Working in a linked club, you get that club\'s modules and nothing from your own club\'s plan. If that club\'s trial has ended, it is paused, or its BetterStats trial has lapsed, you are held to that. Starting a trial, changing the plan or changing how the club pays can only be done by the club\'s own admins.',
    'An unlinked, deactivated or archived club drops you back to your own club on the very next request. Linking gives every Club Admin of one club full Club Admin access to the others in the group, so link clubs only when the same people run both.',
    'Fixed: a club admin\'s account menu could show a module whose trial had just ended until the nightly check ran. The menu now matches what the server allows straight away. Also fixed a StatLab error for admins working outside their home club.',
  ],
}
