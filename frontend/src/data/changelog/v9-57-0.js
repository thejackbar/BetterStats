export default {
  version: 'v9.57.0',
  date: '2026-09-01',
  sortKey: '2026-09-01T16:00:00Z',
  title: 'An audience says how many clubs it reaches',
  items: [
    'Internal: the live readout under a List and under a Segment now ends with the number of distinct clubs behind the contacts — "79 contacts match · 79 reachable by email · 12 clubs".',
    'Counted among the contacts an email would actually reach, so it answers how many clubs would hear from you.',
    'A club emailing its own members sees nothing new: every contact is the one club, so the figure would say nothing and is not drawn.',
    'Fixed while here: a segment matching more than 5,000 contacts under-reported how many were reachable, because that figure was worked out from the capped preview list rather than the whole audience. All three numbers are now exact.',
  ],
}
