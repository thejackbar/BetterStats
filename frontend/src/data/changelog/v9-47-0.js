export default {
  version: 'v9.47.0',
  date: '2026-08-22',
  sortKey: '2026-08-22T12:00:00Z',
  title: 'Sales Performance says who has been called, and where every club sits',
  items: [
    'The conversion funnel is now a pipeline breakdown, one column per stage: Manual, Target, Contacted, Engaged, Trial (Current), Trial (Expired), Won and Lost, in place of the old cumulative assigned/attempted/contacted view.',
    'Each stage cell carries both figures: every club sitting there, and in brackets the number the rep has actually made contact with. A stage full of clubs nobody has rung now reads differently from one that has been worked.',
    'The first column is "To contact", meaning assigned to that rep and not yet contacted, so it says what is left before they need more clubs.',
    'An Unassigned row shows the pool nobody owns yet, spread across the same stages, and an "All clubs" row totals the table. A rep with nothing assigned gets a row rather than disappearing.',
    'Trial splits into current and expired, the same split the Sales Workspace queue makes. A club with no trial dates at all reads as current, since nothing proves it has lapsed.',
    'New Contact activity table: calls, emails, contacts and distinct clubs per salesperson, today and this week, with an Everyone row. Its totals are the figures in the cards at the top of the page, counted in one pass over the same rows, so the two cannot disagree.',
    'A contact means a logged call, a follow-up recorded, or an email sent. A note is not contact, and a row imported from the old Twenty CRM is somebody else’s work, so neither counts.',
    'Activity counts by who did the work rather than who owns the club, so a call on a club that has since been reassigned still belongs to the rep who made it.',
    'Today and this week now run to Perth time. A UTC day starts at 8am local, so a rep’s morning calls used to read as yesterday’s until lunchtime.',
  ],
}
