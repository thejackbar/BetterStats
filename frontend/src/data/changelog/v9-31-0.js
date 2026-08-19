export default {
  version: 'v9.31.0',
  date: '2026-08-19',
  sortKey: '2026-08-29T09:00:00Z',
  title: 'Sales: a note is not a call, and who earned a club is now tracked',
  items: [
    'Logging an outcome of "General Note" was marking the club as called, which dropped it out of the calling queue and, on a Target club, quietly moved it to Contacted. A general note claims nothing about the club, so it is filed as a note now. The club stays in the queue and its stage stays put. Adding a note in the club\'s Notes box never had this problem and still does not.',
    'A club is now recorded as earned by the first sales rep who does real work on it: logs a call outcome, or emails one of its contacts. A note, a General Note and simply being assigned the club do not count. Clubs already worked have been backfilled from what is on record, so nothing has to be re-entered.',
    'Who earned a club and who is assigned it are separate. A super admin can still move a club to another rep or back to the unassigned pool whenever they like, but if a rep has earned it they are asked to confirm first, by name. The same prompt covers the club drawer, the bulk assign action and the deal card in the Sales Pipeline.',
    'The club drawer and the deal card both show who earned a club, so it is visible before anything is moved rather than only in the prompt.',
  ],
}
