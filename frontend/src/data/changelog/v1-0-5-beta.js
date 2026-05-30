export default {
  version: 'v1.0.5 Beta',
  date: '2026-05-30',
  sortKey: '2026-05-30T12:00:00Z',
  title: 'Fix: Social Post export images no longer come out distorted',
  items: [
    "Exporting a Social Post graphic could produce a mangled image — headings overflowing and clipping ('SQUAD' cut to 'SQUA'), names running off the edge, and elements drifting away from where they sat in the editor. The download didn't match the on-screen design.",
    "Root cause 1: the exporter used html2canvas, which re-implements the browser's layout engine in JavaScript and gets boxes, text metrics, and image sizing subtly wrong. Replaced it with modern-screenshot, which captures through the real browser engine (SVG foreignObject), now at 2× resolution for crisp output.",
    "Root cause 2: the condensed display font (Barlow Condensed etc.) was being dropped from the capture. The library can't read the cross-origin Google Fonts stylesheet, so the export fell back to a wide system font and every heading overflowed. We now inline the font files into the capture ourselves, so the export uses the real font. Verified in headless Chrome against live Google Fonts.",
    "Exports are now true JPG files (the button previously produced a PNG despite the label).",
  ],
}
