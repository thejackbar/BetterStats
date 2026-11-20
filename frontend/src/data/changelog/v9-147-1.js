export default {
  version: 'v9.147.1',
  date: '2026-11-20',
  // Above v9.147.0's sortKey (2026-11-21T16:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-21T17:00:00Z',
  title: 'Association Socials: club crests, winners and Team of the Week cap',
  items: [
    'Association workspaces keep a crest library. The first time a pull names a club, its crest is fetched once, the plain background behind it is taken off and the picture is trimmed to the crest. Every later post uses the kept copy.',
    'Club crests in the Data step: check each club once, go back to the original picture, set the club colour, or put in your own crest (cut out in the image editor). A later pull never changes those choices.',
    'Fixtures and Results crests are much bigger in a workspace and are drawn on their own, without the disc around them. They size themselves to the number of matches in the round.',
    'Final Score and Scorecard now show both clubs\' crests from a match link. Scorecard panels take each club\'s colour from its crest instead of the stock blue and red.',
    'Workspace Results posts no longer say WON or LOST. Both clubs are named with their crest and score, and the winner is picked out with a WIN tag. Wrap + Leaders shows the top two run scorers and wicket takers from both sides, each with their club\'s crest.',
    'Team of the Week: the per-club cap now holds in a set make-up as well as best performers. A cap the round\'s clubs cannot fill a team with is greyed out with the reason, and if one is picked before the pull it is raised to the smallest cap that works. Past the cap, clubs take turns for the places left.',
    'Lineups in a workspace keep the association\'s crest as the background watermark, with its strength slider. The featured club\'s crest sits where the hero photo goes until you add one.',
    'A background set in BetterPosts is now saved for the club or workspace, with its photo, tint, texture, crest watermark and background word. It carries to every post type and every admin.',
    'For clubs, a Scorecard post now shows an opponent\'s Cricket Australia crest when the opponent is not on BetterCricket. It used to fall back to letters.',
  ],
}
