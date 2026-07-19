export default {
  version: 'v8.74.0.6',
  date: '2026-07-19',
  sortKey: '2026-07-19T19:00:00Z',
  title: 'Usage page: real presence detection, plus an interactive visitor map',
  items: [
    '"Active now" and the green dot in the live feed used to be a guess based on how recently someone\'s last page load landed, so they could stay lit for minutes after a visitor had actually left. The site now pings every 25 seconds while a tab is open and in view, so both now reflect someone genuinely having the page open right now, and go dark the moment they close it or switch tabs.',
    'Added a Visitor map to the Usage page: an interactive, pannable map of Australia with a dot per city, sized by visitor count and lit green while someone from that city is active. Locations come from the same IP-to-city lookup already used for the "Perth", "Melbourne" labels elsewhere on the page, so they land at city precision, not an exact address or device location.',
  ],
}
