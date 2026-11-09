export default {
  version: 'v9.141.0',
  date: '2026-11-09',
  // Above v9.140.2's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-18T04:00:00Z',
  title: 'Result posts, scorecards and fixtures: a round of club feedback',
  items: [
    'Result (Classic): the grade now sits in its own tag beside RESULT, and "Swap sides" puts the club name and logo on the left and the result on the right. The panel labels (LSC, KLC) can be typed over in the layout elements, so "Spartans" works.',
    'Result posts: games with no winner can now say "Match abandoned", "Abandoned due to wet weather", "No result", a tie, or words you type. An imported abandoned game no longer reads as a tie.',
    'Result posts: a game that was not scored ball by ball no longer prints "(0)" after every score. Dates import as "Sat 7 Nov" instead of capitals.',
    'Style: pick a separate face for player names and scores, and tick "Club names without Cricket Club" to print Leeming Spartan on one line. Both are remembered in your browser.',
    'New result layout, Match Summary: a score bar for each side, with its batters beside the bowlers they faced.',
    'Fixtures and Results lists: tick "vs on every row" to drop the "@", and "Show the club, not the grade team" to print Maddington Cricket Club instead of Maddington Seventh Grade.',
    'Scorecards: both pages now open with the two clubs and their crests. How out reads "c C Cecchi b A Ricci" as it does on PlayCricket. The team panel is measured against the sponsor bar, so long cards no longer run under it.',
    'Scorecards: the match heading box and the team panels have their own colours. Opposition colours can be read from their crest (or picked), and their square can take those colours.',
    'Results Win/Loss Split: a long opponent name no longer pushes the LOST column off the edge of the post.',
    'Club crests: the dropdown now uses a club\'s own crest only when it has one on file, and offers "use official crest" to swap in the Cricket Australia one. An imported result no longer keeps the last opponent\'s crest, opponents are no longer matched to your club on a shared word like "Cricket", and an archived club's old crest is no longer used on posts.',
  ],
}
