export default {
  version: 'v9.71.2',
  date: '2026-09-08',
  // Above v9.71.1, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-08T12:00:00Z',
  title: 'The demo registration asks for a phone number',
  items: [
    'The webinar registration page now asks for a phone number alongside the name, email and club. An email address on its own is a thin way to reach a club officer, and a registration is a lead somebody follows up.',
    'It is stored exactly as it was typed, spaces and brackets and all. A landline is as good a number to ring a secretary on as a mobile, so the page accepts either rather than insisting on one.',
    'The number shows on the super-admin registration list as a link you can ring straight from the row, and it is in the CSV export.',
    'It also travels, hashed, with the conversion already sent to Meta. A conversion carrying an email and a phone matches back to whoever saw the ad more often than one carrying an email alone, so the ad set learns from more of the registrations it earned.',
    'A registration taken before this shipped simply reads as having no phone, rather than an invented blank.',
  ],
}
