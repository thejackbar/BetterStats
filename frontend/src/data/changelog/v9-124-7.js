export default {
  version: 'v9.124.7',
  date: '2026-10-20',
  // Above v9.124.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-02T14:00:00Z',
  title: 'Photo background removal is quicker and no longer locks up the page',
  items: [
    'The "Remove background (photo)" button could stall or fail, and was slow even when it worked. Each use downloaded about 100MB of model files from a third-party site. Those files now come from our own server and your browser keeps them after the first time.',
    'The cut-out now runs without freezing the page, shows how far the download has got, and starts loading while you crop. Browsers with WebGPU use the graphics chip, which is much quicker. Everywhere else it takes roughly the same time per photo as before, but you can keep scrolling while it works.',
  ],
}
