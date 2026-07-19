export default {
  version: 'v8.74.0.1',
  date: '2026-07-19',
  sortKey: '2026-07-19T14:00:00Z',
  title: 'BetterComms: Preview now shows the merged Subject line',
  items: [
    'Preview mode was already merging {{first_name}}/{{club}}/etc into the email body for the real recipient it was showing, but it never showed the Subject line at all. Preview now shows the merged Subject above the body, so a Subject using {{club}} reads correctly per contact.',
    'The {{key}} merge-variable matcher now tolerates any amount of spacing inside the braces (e.g. {{  first_name  }}), not just none or exactly one space either side.',
  ],
}
