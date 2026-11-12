export default {
  version: 'v9.143.6',
  date: '2026-11-12',
  // Above v9.143.5.3's sortKey (2026-11-20T02:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T03:00:00Z',
  title: 'StatLab: who plays, bowls and fields together',
  items: [
    "StatLab has a new Teammates & Pairs group. Most games played together ranks every pair of players by matches in the same side, with their wins, losses, draws and win percentage. Best win rate together ranks the same pairs by how often the side won, with a minimum games setting so a pair who won their only match does not top it.",
    "Bowler and fielder dismissals lists who takes the catches and stumpings off whose bowling. A new Fielder setting narrows it to the wicketkeeper (stumpings and catches behind) or to everyone who was not keeping. It replaces Top bowler/fielder combinations, which only counted catches. Old saved reports of that one still open.",
    "Opening bowling pairs shows who took the new ball together, and Opening batting pairs shows who shared the first-wicket stand, with the runs they put on.",
    "Pick a player on any of these and you get only the pairs they are in, so you can see who someone plays with most, or whose bowling they catch off.",
    "Games together count a match the same way each player's own Matches figure does. Wins and losses cover games where the side is known, so a hand-typed or imported match with no team named counts as a game together but not as a win or a loss. Keeper catches are a floor: a catch saved before keeper catches were tracked only shows under All fielders.",
  ],
}
