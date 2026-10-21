export default {
  version: 'v9.128.6.3',
  date: '2026-10-21',
  // Above v9.128.6.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T23:00:00Z',
  title: 'Fix: Draw pictures stopped after about 40 clubs',
  items: [
    'Drawing pictures stopped part way through a batch, because the page that each picture is taken from was being limited like a public visitor (120 reads an hour). The picture drawer now identifies itself and is not limited. The limit for everyone else is unchanged.',
    'When a picture cannot be drawn, the message now says why: the page was refused or not found, was still waiting for its data, or never settled. It used to say only that it timed out.',
    'A club logo that never answers no longer holds a picture up. After five seconds the picture is drawn with the club\'s crest of initials instead.',
  ],
}
