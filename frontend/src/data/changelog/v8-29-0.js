export default {
  version: 'v8.29.0',
  date: '2026-06-26',
  sortKey: '2026-06-26T14:30:00Z',
  title: 'Usage page rebuilt around visitors and leads',
  items: [
    'The Usage page is now a Visitors & Leads view. It tracks returning visitors with a stable first-party id, so the same person is recognised across visits even when their IP changes.',
    'Every visit now records where it came from. UTM tags and ad-click ids (an fbclid is a Facebook share, a gclid is a Google click) are read from the link and bucketed into a source, and a club’s own outreach UTM code resolves back to that club.',
    'Each anonymous visitor gets a likely club worked out from the club pages they browse, alongside their source, location and device. Click a visitor to read their full page journey.',
    'Contact-form enquiries now link to the browsing behind them, so you can see a lead came via Facebook, read the pricing page, then got in touch. Visits to the pricing and contact pages are flagged as warm leads.',
    'The heavier detail (charts, geography, the raw event log, signed-in users) sits in collapsible sections that stay shut until you open them. The default view is the last 24 hours of anonymous page views.',
  ],
}
