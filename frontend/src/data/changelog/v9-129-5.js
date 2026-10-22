export default {
  version: 'v9.129.5',
  date: '2026-10-22',
  // Above v9.129.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T20:00:00Z',
  title: 'Selection Whiteboard: move players in and out of locked sides',
  items: [
    'You can now move players to and from a locked side on the Selection Whiteboard. Before, the drag looked like it worked and then the team showed "Not saving".',
    'The first change to a locked side asks "this side is locked, are you sure you want to change it?". Say yes and that side is unlocked and the change goes through. Say no and nothing moves.',
    'Moving a player between a locked and an open team only asks about the locked one. Once a side is unlocked, further changes to it do not ask again.',
    'Confirm locks the side again, the same as before. Locked teams now carry a Locked tag in their header.',
  ],
}
