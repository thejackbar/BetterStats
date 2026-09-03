export default {
  version: 'v9.62.0',
  date: '2026-09-03',
  sortKey: '2026-09-06T11:00:00Z',
  title: 'Matches against another BetterCricket club now count for both clubs',
  items: [
    'When two clubs on BetterCricket play each other, that match is one shared record. It is now counted and classified the same way for both of them, instead of following whichever club happened to load it first.',
    'Those matches were being left out of the Players list, the leaderboards, the record boards and StatLab for the other club, so a player could see one number on the Players list and a higher one on their own profile. Both now read the same.',
    'They were also landing in the wrong grade type, so a senior match could turn up under the Juniors filter as well as under Men’s. Each match now sits in one grade type only.',
    'Picking a season no longer drops them either — a shared match shows under the season it was played in.',
    'On the Competitions panel they are filed under the club’s own competition rather than reading as "Other grades".',
    'Competitions also reads grades the way Manage Grades does: a grade you have merged shows as one row rather than one per old name, and the season count is the number of seasons played rather than one per club involved.',
    'A player’s season-by-season table opens in season order again. A winter season was sorting to the top of the list.',
    'The M column on the Players list and the leaderboards now means matches played, the same as MATCHES on a player’s own profile. It used to count only the matches a player batted, bowled or took a catch in, so the two screens disagreed by every game somebody was picked for and did not get a bat in.',
    'Grades are now grouped into competitions on their own, by a nightly job. An established club used to find its older seasons sitting outside every competition until someone pressed the button on Manage Grades; that happens without anyone asking now, once, and the button stays for anyone who wants it done immediately.',
    'Every club’s existing seasons have been grouped in one pass rather than a few clubs a night, so Manage Grades and the Competitions panel show your full history straight away.',
  ],
}
