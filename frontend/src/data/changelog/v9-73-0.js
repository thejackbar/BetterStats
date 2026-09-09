export default {
  version: 'v9.73.0',
  date: '2026-09-09',
  // Above v9.72.1's sortKey, which is the highest of the releases so far, or
  // SITE_VERSION never reaches this one. Check origin/main at merge time.
  sortKey: '2026-09-20T06:00:00Z',
  title: 'BetterPosts: post sizes, a real preview, and background removal on any image',
  items: [
    'A post can now be made at 1080×1350 portrait or 1080×1920 story as well as the square, picked under Design. The blank canvas is genuinely that shape; a built-in layout is drawn at a fixed 1080×1080, so it is placed onto the taller canvas whole (the default) or scaled up and cropped, with the panel saying which is happening.',
    'The bands either side of a fitted layout carry the club\'s own colour rather than reading as an unfinished export, and a background texture from Brand covers them entirely.',
    'A new Preview shows the finished post with none of the editing chrome on it — and every page of a carousel at once, which the canvas could only ever show one at a time.',
    'Any image on a post can now be cropped or have its background removed in place: select it and press Edit. Every picture in the club library has the same Edit on hover, so a logo that arrived on a solid white background can be cut out once and reused.',
    'The Layers panel says what Forward and Backward can reach on a built-in layout — blocks you add sit on top of it, because a layout is one fixed design rather than a stack — and points at the layouts that open as movable blocks, or the blank canvas where everything is its own layer.',
    'A layout with no hero-photo slot now names the layouts that have one, instead of the Hero Image panel silently not being there.',
    'Saving now says where the thing went. "Save to Club Room" adds the finished picture to the Club Room TV slideshow and links to it; "Save as template" says it is under Design → Your templates, and that templates live on that browser only.',
    'The Photos panel header names the club library and counts what is in it.',
  ],
}
