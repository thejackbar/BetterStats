export default {
  version: 'v9.22.4',
  date: '2026-08-13',
  sortKey: '2026-08-16T20:00:00Z',
  title: 'BetterScout: linked clubs get their real name, and a shared year is one row',
  items: [
    "Confirming a club a player was found at through search could leave it labelled \"Unknown club\", since the real name from that search was never actually passed through to the club's own record. It's threaded through now, and a club that already got stuck nameless is repaired the next time anyone links it.",
    "A player's season history now merges figures from every linked club into one row per year instead of listing the same year twice with the numbers split across clubs. A year covered by more than one club still names them underneath.",
  ],
}
