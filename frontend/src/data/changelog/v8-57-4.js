export default {
  version: 'v8.57.4',
  date: '2026-07-04',
  sortKey: '2026-07-04T17:00:00Z',
  title: 'Meta Conversions API, server-side Lead redundancy',
  items: [
    'A Lead enquiry (full Contact form or the CTA\'s short form) now also sends server-side to Meta via the Conversions API, alongside the existing browser pixel: so ad blockers, iOS tracking prevention, or a failed pixel load no longer drop the lead from Meta\'s reporting.',
    'Both copies share one event ID so Meta counts each enquiry once, not twice.',
    'It\'s configured entirely through server env vars, blank by default, so CAPI is skipped quietly and the form and browser pixel keep working unaffected.',
  ],
}
