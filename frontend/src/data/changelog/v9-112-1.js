export default {
  version: 'v9.112.1',
  date: '2026-10-14',
  sortKey: '2026-10-14T09:00:00Z',
  title: 'A club with an ended trial gets 7 days straight away when it asks from /trial',
  items: [
    'When a registered club whose trial has ended sends the Request trial extension form on /trial, its BetterStats trial now runs for 7 more days straight away, any add-on module still on trial gets the same, and the club page comes back. The thank-you screen says so and links to the club page.',
    'It happens once per club. A second request is not extended again and is emailed to Jack and Elton as a plain request that says why. A club an admin switched off, or whose BetterStats was cancelled or paid, is also left alone and emailed.',
    'The email to Jack and Elton now says whether the trial was extended and to what date. Each request is saved in the Onboarding list as trial_extension_granted or trial_extension_request.',
  ],
}
