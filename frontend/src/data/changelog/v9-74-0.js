export default {
  version: 'v9.74.0',
  date: '2026-09-09',
  // Above v9.73.2's sortKey, which is the highest on origin/main at merge time,
  // or SITE_VERSION never reaches this one. Two entries sharing a sortKey is
  // how the notification bell starts reporting the wrong release.
  sortKey: '2026-09-20T08:00:00Z',
  title: 'Every BetterPosts template fills the 4:5 and 9:16 canvas',
  items: [
    'Picking Portrait or Story used to place the square layout onto the taller canvas, either whole with the background showing past it or scaled up with the edges cropped off. Every built-in template now renders into the canvas itself, so nothing is scaled and nothing is trimmed.',
    'A template\'s own background, texture and edge bars run right to the top and bottom of the post rather than stopping where the square used to end, which is what made a taller post read as a letterboxed square rather than a portrait one.',
    'The artwork keeps its proportions and sits centred, so a 9:16 story leaves room top and bottom — which is where Instagram draws its own profile bar and reply box anyway.',
    'The "fit whole or fill and crop" choice is gone for these templates, because there is no longer anything to fit or crop. The panel says what the size does instead.',
    'Exports name their size, so saving the same post at all three sizes gives three files rather than one overwritten twice.',
    'The full scorecards are unchanged: they are drawn 1920×1080 wide and are still offered the Instagram-squares split rather than a post size.',
  ],
}
