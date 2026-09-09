export default {
  version: 'v9.71.0',
  date: '2026-09-17',
  // Above v9.70.9, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-17T10:00:00Z',
  title: 'The old external CRM is gone; your engagement scores are not',
  items: [
    'BetterCricket used to push a copy of every prospect club into a second, external CRM. That system has been shut down, and every last connection to it has been taken out — the export, the nightly lead and task scan, the credentials and the dashboard widgets.',
    'Nothing you use has been taken with it. Engagement scores, the sales pipeline, Sales Performance, Sales Commissions, the Sales Workspace and the Club Directory all work exactly as before, because all of them read BetterCricket\'s own numbers and always did.',
    'The nightly rescore is fixed and running again. It used to skip any club that had never been pushed to the old CRM, so once that system was switched off it quietly stopped scoring anybody — scores sat frozen wherever they were last touched. Every club in the directory is now rescored each night.',
    'The Club Directory\'s three CRM buttons are one: "Refresh engagement scores". It rescores every club on demand and re-runs the pipeline stage rules, and it is the same sweep the nightly job runs, so the two can never disagree.',
    'On the scoring parameters page, "Raise a Twenty Opportunity at" now reads "Reads as an opportunity at", and says plainly that it is a reporting line — nothing is created or moved by a club crossing it.',
  ],
}
