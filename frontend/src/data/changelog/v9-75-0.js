export default {
  version: 'v9.75.0',
  date: '2026-09-09',
  // Above v9.74.0's sortKey, or SITE_VERSION never reaches this one. Check
  // origin/main at merge time.
  sortKey: '2026-09-22T06:00:00Z',
  title: 'BetterPosts: a portrait design for every layout, not a square one stretched',
  items: [
    'Every layout now has its own design for the taller posts. Where the last release made each one draw itself at 1080×1350 and 1080×1920, this one decides per layout where the extra height should go, so a portrait post reads as a portrait design rather than a square one with the middle pulled apart.',
    'Mastheads and sponsor strips keep their share of a taller post instead of shrinking to a tenth of it, and rows and figures step up with the slot they sit in — a fixture in a 200px row is no longer set at the size it was in a 60px one.',
    'Lists and panels that used to stop where the square ended now run down to the footer: the batting order, the top-performer panels on a result post, and the milestone poster, which had a dead band above its squad list.',
    'The trading-card and mosaic lineups reshape their grids on a story so the cards stay card shaped instead of stretching into letterboxes, the gig-poster lineup re-sets its billing across five lines, and the squad list on the hero lineup is set as one block rather than spread 130px apart.',
    'Fixed a colour-block event poster whose lower panel overlapped its own colour band on any post taller than a square, and a lineup whose background gradient stopped two thirds of the way down a story.',
    'Long names now shrink to fit properly on layouts with padded panels. They were allowed to run over the edge by exactly the width of the padding, which is what put the lineup poster’s names off the side of the post.',
    'Square posts come out as they did. Every measurement in the new designs is exact at 1080×1080, checked by re-making all 48 square posts on the old and new versions and comparing them. Two square posts did change, both because they were already broken: the batting order now fits all 13 names above the footer instead of the last one landing on top of it, and the gig-poster lineup keeps its names inside the poster.',
  ],
}
