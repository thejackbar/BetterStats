export default {
  version: 'v9.72.0',
  date: '2026-09-09',
  // Above v9.71.5, the highest so far, or SITE_VERSION never reaches this one.
  // origin/main checked at merge time — two entries sharing a sortKey is how
  // the notification bell starts reporting the wrong release.
  sortKey: '2026-09-19T05:00:00Z',
  title: 'Meta Ads HQ splits trial signups from webinar registrations',
  items: [
    'The Meta campaign now runs two ads selling two different things — a free trial and a seat at the 21 September webinar — and both landing pages report the same conversion to Meta. Meta Ads HQ now reports the two separately everywhere, so a trial signup and a webinar registration are never added together.',
    'Cost per result is worked out per ad. Each figure divides that ad\'s own spend by its own registrations, where the page used to divide the whole campaign\'s spend by trial signups alone — which quietly charged every trial signup with the webinar\'s spend.',
    'Only a trial signup counts towards revenue. A webinar registration is a form fill worth nothing on the books, so it no longer contributes to any value or return figure.',
    'A webinar registration reaching Meta from our own server was labelled as a trial signup and carried $399 of value it never had. Fixed at the source, so Meta now sees the two conversions as the different things they are.',
    'Every trend chart marks the 8 September restructure, with a note saying what changed. A week-on-week drop printed over a deliberate budget cut is worse than saying nothing.',
    'The last seven days are shaded as still settling. Meta credits a registration to the day of the click and keeps filling those days in for a week, so recent figures only ever go up — and nothing on the page raises an alarm off them.',
    'A new creative table compares ads on the tag in their link, so a creative can be judged across a rebuild in Ads Manager.',
    'The webinar ad\'s link in its own body text carries no tracking, so some genuine registrations arrive with nothing to identify them. The page counts those separately and says so, rather than either claiming them or hiding them.',
    'Budget pacing is measured from the most recent campaign change instead of across it, and an ad that has ended or has not gone live yet no longer breaks the figures around it.',
  ],
}
