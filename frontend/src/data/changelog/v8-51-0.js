export default {
  version: 'v8.51.0',
  date: '2026-07-02',
  sortKey: '2026-07-02T12:00:00Z',
  title: 'Twenty CRM: Leads and follow-up Tasks',
  items: [
    'Telemetry now raises a Lead in Twenty for each targeted club that shows real interest (requested a trial, in a trial, or active in the sales cycle), instead of jumping straight to an opportunity. A Lead is a triage item; you turn it into a deal in Twenty by setting the modules to pursue.',
    'Follow-up Tasks are created in Twenty for the things that must not be missed: an outstanding module request, a trial about to expire, and a paid subscription coming up for renewal. Each Task is raised once and stays until it is done.',
    'A new "Refresh Twenty leads/tasks" button on the Club Directory runs all of this on demand. It also runs each morning, and the first run backfills whatever already qualifies.',
    'Leads and Tasks only cover clubs already exported to Twenty, and re-running is safe: nothing is duplicated.',
  ],
}
