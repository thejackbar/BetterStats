export default {
  version: 'v8.41.1',
  date: '2026-06-28',
  sortKey: '2026-06-28T02:00:00Z',
  title: 'Clubs Directory shows who visited the site from their UTM link',
  items: [
    'When someone follows a link from a club\'s outreach email and lands on the public site, that visit is now noted against the club in the Clubs Directory. A "visited" badge shows how many views it has had, and opening the club shows the full trail: total views, separate visitors, first and last seen, and which pages they looked at.',
    'A "Visited the site" filter narrows the directory to clubs someone has clicked through to, so you can follow up with the clubs already showing interest.',
    'A visit is tied to a club whether the code arrived as utm_id or utm_source, and also when someone lands straight on the club\'s own page, so a link like /gosnells-cricket-club?utm_source=camsawatzky still counts even though the tag is the rep\'s name.',
    'New UTM matching panel: lists every UTM value visits have arrived with and lets you map the odd ones to a club by hand (a campaign source like "executive" that doesn\'t match the club\'s code), or mark noise like "meta" as ignored. Mapped values then count towards that club\'s visits everywhere.',
  ],
}
