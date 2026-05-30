export default {
  version: 'v1.0.5.1 Beta',
  date: '2026-05-30',
  sortKey: '2026-05-30T13:00:00Z',
  title: 'Social Post: 6 more display fonts now actually work',
  items: [
    "The Social Post font picker listed Anton, Bebas Neue, Archivo Black, Teko, Big Shoulders and Antonio, but those six were never loaded — picking them silently fell back to a plain system font in both the editor and the export.",
    "All six are now loaded from Google Fonts, so the full set of eight display fonts renders and exports correctly. Verified each one in headless Chrome.",
    "Also corrected Archivo Black (a single-weight font) showing a slightly distorted faux-bold by using its true weight.",
  ],
}
