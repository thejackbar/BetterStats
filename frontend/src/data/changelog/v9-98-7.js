export default {
  version: 'v9.98.7',
  date: '2026-10-05',
  // Above v9.98.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-05T16:00:00Z',
  title: 'An entered game’s winner matches its own result',
  items: [
    'A scorecard entered by hand or imported from a spreadsheet could name one team as the winner while its own result line and scores said the other team won. The WON tag and your win/loss record both followed the wrong name. When the result line and the scores agree with each other and the recorded winner does not, the winner is now corrected to match, and the import tells you which games it changed.',
    'Anything less clear cut, such as level scores or a result where the lower score won, is left exactly as you entered it.',
  ],
}
