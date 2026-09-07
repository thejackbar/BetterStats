export default {
  version: 'v9.67.3.1',
  date: '2026-09-07',
  sortKey: '2026-09-14T09:00:00Z',
  title: 'Signing up says which details are required',
  items: [
    'The mobile number on the club admin step of the trial signup was already mandatory — the registration is refused without one — but nothing on the form said so, so the only way to find out was a CONTINUE button that would not press.',
    'Every field on that step now carries a required marker, with a line above them saying so and naming the mobile among them.',
    'Leaving the mobile blank now says it is required, instead of describing the format of a number nobody had typed yet.',
    'Nothing changed about what is accepted: an Australian mobile, or an international number starting with +. A super admin setting up a club on someone else’s behalf can still leave it blank, same as before.',
  ],
}
