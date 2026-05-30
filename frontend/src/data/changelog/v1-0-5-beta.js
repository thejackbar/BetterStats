export default {
  version: 'v1.0.5 Beta',
  date: '2026-05-30',
  sortKey: '2026-05-30T12:00:00Z',
  title: 'Fix: Social Post export images no longer come out distorted',
  items: [
    "Exporting a Social Post graphic could produce a mangled image — text shifted out of place, photos stretched, and elements drifting away from where they sat in the editor. The downloaded image didn't match the on-screen design.",
    "Root cause: the exporter used html2canvas, which re-implements the browser's layout engine in JavaScript and gets boxes, text metrics, and image sizing subtly wrong. It's also effectively unmaintained.",
    "Replaced it with modern-screenshot, which captures the design through the real browser engine (SVG foreignObject). The export now matches the editor exactly — no text drift, no stretched images — and renders at 2× resolution for crisp output.",
    "Exports are now true JPG files (the button previously produced a PNG despite the label).",
  ],
}
