export default {
  version: 'v9.142.0',
  date: '2026-11-09',
  // Above v9.141.3's sortKey (2026-11-19T03:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T04:00:00Z',
  title: 'Nets by time slot: a grid of nets, filled as people check in',
  items: [
    'A net session can now run as a grid, like the sheet clubs already keep: one column per net, one row per time slot (4:45, 4:52, 4:59). When you start a session, choose "Batting queue" (as before) or "Time slots".',
    'Set up the nets once: the first net time, how long each slot is, an optional finish time, and which squads use which net. A net can take several squads (1st and 2nd XI), and one net can be "Everyone else" for juniors, guests and anyone whose squad has no net. A player in two squads goes to the net of their higher squad.',
    'People are placed as they check in, from the admin screen or the QR link. The first arrivals fill the column from the top. Someone who walks in at 5:08 gets the next slot that has not started, not a gap behind the clock. The running slot says NOW.',
    'Drag a name by its grip to another slot or net, or tap a name and tap a cell. Dropping on a taken cell swaps the two. People you move by hand stay where you put them when the plan changes.',
    'With a finish time, anyone who does not fit is named under their net instead of silently running late. Turn on second go and free slots at the bottom of a net repeat its order. Someone not batting holds no slot, and coming back gives them one.',
    'Existing sessions and the batting queue are unchanged.',
  ],
}
