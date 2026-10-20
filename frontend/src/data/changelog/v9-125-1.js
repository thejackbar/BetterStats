export default {
  version: 'v9.125.1',
  date: '2026-10-20',
  // Above v9.125.0's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T09:00:00Z',
  title: 'Card review finds matches the record holds twice',
  items: [
    'Card review has a new first step, Find the doubles. It lists matches that sit in the record twice with nothing linking the copies: a club scorecard (imported, typed in or read from a photo) beside a Cricket Australia match, or two club scorecards of the same match, such as a file imported twice. These count twice on careers, on the Two Day and One Day tabs and on the record boards, and until now no step of Card review could see them.',
    'Each pair shows both copies side by side with the evidence: how many batters have the same score on both, how many days apart they are, whether the opposition names agree, and whether the two copies are filed under different match types. Pairs are sorted strongest first. Two cards that both have batters and share none are never offered, and neither are two club scorecards more than ten days apart.',
    '"Same match: link them" links a club scorecard to the Cricket Australia match and moves it into the other steps. Nothing is deleted and the link can be undone from the match. The site shows the Cricket Australia card when the batters agree. Where the club card has batters and Cricket Australia\'s has none, or they disagree, the club card stays on show until you choose. For two club scorecards there is no link to make, so the extra copy is removed through Manual Entries, where Audit and Undo restores it.',
    '"Different matches" is remembered for that pair, so it is not offered again, and can be put back from the Marked as different tab. Unlinking a pair in the pairing step counts as the same answer.',
    'A new Find a match page looks a fixture up by opposition, player, grade, competition, season or date, and shows every copy the record holds of it, whether or not they are linked. Use it to check a figure someone has questioned on a card. Tick a club-only fixture and a Cricket Australia-only fixture to link them by hand when the scan did not suggest the pair.',
    'The same opposition, player, grade, competition and date filters now sit on every step of Card review (pairings, agree, small differences, scores differ and the doubles), and the words carry from one step to the next in the address bar. A match matches if either copy does, so a player who batted on only one card still finds the pair. Every page has a Find a match button.',
    'Matches imported through the CricketStatz importer are included. The nightly pairing pass leaves a link you made exactly as you set it.',
  ],
}
