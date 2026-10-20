export default {
  version: 'v9.125.6',
  date: '2026-10-20',
  // Above v9.125.5's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T14:00:00Z',
  title: 'Card review: a Recent changes page with an undo for every change',
  items: [
    'A new Recent changes page lists every switch, link, moved link, unlink and "different matches" answer made in Card review: who did it, which match, what changed, newest first. Anything that can still be undone has an Undo button, or Put back for a "different matches" answer. It has a link in the header of every Card review page.',
    'Only the newest change to a card can be undone, so an older change is never undone by mistake. A bulk switch or bulk fix is still undone as a batch from the Card review overview.',
    'Fixed: the Undo button on a match page did not appear after a link made in Possible doubles. It does now.',
    'Fixed: a pair that was unlinked could not be put back. It dropped out of every list, and Put back only cleared the hidden answer. Undoing an unlink now restores the link, from Recent changes or from the Marked as different tab. If the card has been changed since, it says which change to undo first.',
    'A "different matches" answer is kept under Marked as different on Possible doubles. Open that tab and use Put back to offer the pair again.',
  ],
}
