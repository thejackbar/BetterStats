export default {
  version: 'v9.113.7.1',
  date: '2026-10-15',
  sortKey: '2026-10-15T16:00:00Z',
  title: 'Photos survive a merge',
  items: [
    'Fixed: a player\'s photo disappeared when a hand-added player was merged into the record that came from Cricket Australia. The picture was kept, but the address saved with it still pointed at the record that had just been merged away, so every screen showed no photo. The merge now points the photo at the player who keeps it, for the headshot and the action photo.',
    'A kept player whose photo address leads nowhere no longer blocks the real photo from being carried across in a merge.',
    'Photos already hit by this are put right by a one-off repair for the club, so nobody has to upload them again. A photo whose picture was never stored cannot be recovered and needs uploading once more.',
  ],
}
