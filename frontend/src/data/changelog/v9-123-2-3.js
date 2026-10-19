export default {
  version: 'v9.123.2.3',
  date: '2026-10-19',
  // Above v9.123.2.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T12:00:00Z',
  title: 'Games no longer pile up on one player when Cricket Australia hides a player\'s id',
  items: [
    'Fixed a sync problem where one player could be credited with other players\' games. Cricket Australia gives every hidden player (usually juniors) the same placeholder id. If a hidden player\'s name matched one of your players, sync linked the placeholder to that player and then gave them every hidden player\'s innings and team sheet entries. One player at a club read 48 games when Cricket Australia had 12.',
    'The placeholder id is now never linked to anyone, so this stops happening on new games. Players still link by full name when their id is a real one.',
    'Games already attached to the wrong player stay until they are cleaned up. If a player\'s games or career look too high, tell us the name and we will check it and fix it.',
  ],
}
