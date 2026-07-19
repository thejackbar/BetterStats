export default {
  version: 'v8.74.0.4',
  date: '2026-07-19',
  sortKey: '2026-07-19T17:00:00Z',
  title: 'Meta Ads HQ now counts real trial registrations, not Meta\'s Lead/CompleteRegistration actions',
  items: [
    'The "Meta-attributed conversions" tile on /admin/super/marketing summed Meta\'s own Lead and CompleteRegistration action types, which fire the moment someone reaches or submits the trial form and can double-count across the pixel/CAPI split — a campaign showing "2 conversions" turned out to be one prospect counted twice, and zero of them had actually finished registering.',
    'The tile (now "Free trial registrations") is built from our own ground truth instead: clubs in the self-serve signups table whose campaign/creative tag matches one of the current campaign\'s own ads. Meta\'s raw number is kept as a secondary reference figure only.',
    'The footer note explains the distinction: a signup tagged with a different campaign (an EDM send, "national-launch", organic) is a real registration but isn\'t counted against this Meta campaign\'s spend.',
  ],
}
