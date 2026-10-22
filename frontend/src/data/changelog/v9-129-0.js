export default {
  version: 'v9.129.0',
  date: '2026-10-23',
  // Above v9.128.14's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T12:00:00Z',
  title: 'Partnerships from a short fall of wickets, and clubs can type the rest in',
  items: [
    'A match where Cricket Australia held only some of the fall of wickets (six wickets fell, four were recorded) used to get no partnerships at all. Now every stand the figures settle is kept. With wickets 1, 3, 4 and 5 recorded you get the 1st, 4th and 5th wicket stands. The 3rd is left out because the 2nd wicket\'s score is missing, so the runs between the 1st and 3rd wickets cannot be split.',
    'Who was at the crease is worked out from the batting order and who was out. Where that depends on a guess, the stand is left out rather than credited to the wrong pair. A score that does not add up, a retirement on the card or a batter who was not out also leaves the innings alone.',
    'A club with a paper scorebook can now type in the fall of wickets for its own innings of a synced match. Open the match, press EDIT on the Fall of Wickets card, enter the score and who was out at each wicket, and save. The partnerships are worked out straight away and reach the records. You can leave a wicket out or leave its batter as "Not sure".',
    'What a club types is kept apart from Cricket Australia\'s figures, so a Full Rebuild does not lose it. "Reset to Cricket Australia" puts the original wickets back. Each save is on the audit trail. Editing needs the Manual stat entry permission, and only your own innings can be edited.',
    'The match page now says "4 of 6 wickets recorded" under a short fall of wickets, so it is clear why some partnerships are missing.',
    'Games already stored with a short fall of wickets get their stands from the existing backfill: python -m app.scripts.backfill_partnerships <club> --apply.',
  ],
}
