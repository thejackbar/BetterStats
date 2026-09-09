export default {
  version: 'v9.72.1',
  date: '2026-09-09',
  // Above v9.72.0's sortKey, which is the highest of the releases so far, or
  // SITE_VERSION never reaches this one. origin/main checked at merge time —
  // two entries sharing a sortKey is how the notification bell starts
  // reporting the wrong release.
  sortKey: '2026-09-19T06:00:00Z',
  title: 'Meta Ads HQ measures each stream since the restructure, not across it',
  items: [
    'Each stream card now carries its cost per result SINCE the 8 September restructure alongside its all-time one. The trial\'s lifetime figure is mostly the campaign that ran before the change (A$50/day, broad targeting, all placements); the webinar has no history before it at all, so reading one lifetime figure against the other was comparing two different campaigns.',
    'Spend since the change is summed per stream from the daily per-ad rows, and the results behind it are windowed by when the club actually signed up, so both streams are measured over the same stretch of calendar.',
    'The all-time figures now say they are all time. Left unlabelled beside a since-the-change one, the larger number reads as the current cost.',
    'A figure that cannot be stood behind is withheld with the reason rather than printed: a window our daily history does not fully cover would understate the cost, and a stream with no results yet is not an infinitely expensive one.',
    'Results still inside Meta\'s 7-day click window are marked provisional, because spend settles the day it happens and conversions keep arriving for a week — so the cost per result there is a ceiling that comes down.',
    'An attributed trial signup we hold no signup date for is reported as a known gap. It counts in the all-time figure and in neither since-the-change one, so a short since count reads as a gap rather than as the ads having stopped working.',
  ],
}
