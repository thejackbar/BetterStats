export default {
  version: 'v9.108.8',
  date: '2026-10-08',
  sortKey: '2026-10-08T17:00:00Z',
  title: 'Super Admin can download a PDF of the personal information we hold about a person',
  items: [
    'A new Super Admin screen, Privacy Requests (under Clubs and Data), finds a person by name or player id across every club and shows where they stand: on the public site, hidden by the club, removed at their request, or held because the name matches someone who was.',
    'Download PDF creates a plain-English report for that person: each club\'s record of them with their details, their membership record, email list entries, sign-in account, other names, a count of their cricket records and a list of the matches they are recorded in. It also says whether their removal request has been acted on.',
    'It leaves out what should not leave without a person reading it: other family members\' details, free-text notes, and the amounts and dates of fee and payment records, which are counted only. Passwords and internal ids are never printed.',
    'The PDF is never cached, only a Super Admin can get it, and each download is written to the club\'s activity log.',
  ],
}
