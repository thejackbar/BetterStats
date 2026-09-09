export default {
  version: 'v9.71.3',
  date: '2026-09-09',
  // Above v9.71.2, or SITE_VERSION never reaches this release.
  sortKey: '2026-09-09T12:00:00Z',
  title: 'Four fixes to the demo registration page',
  items: [
    'The demo page was telling everyone to watch a recording of a demo that has not happened yet. Its browser tab, and every Facebook, LinkedIn and WhatsApp preview of the link, said "Watch the BetterCricket demo" while the page itself correctly said "See BetterCricket in action". Both now come from the same place as the headline, so the page turns itself over on the night and the share card turns over with it.',
    'The phone number is optional again. It was added as a required field last week; on a page that paid traffic lands on cold, a compulsory phone number is the most expensive thing you can ask for, and it reads as a promise to ring somebody. We still ask, and a number that is typed in is still checked — it just no longer stops anybody registering.',
    'The StreamYard link is no longer part of the page you download. It used to be built into the site\'s own code, so anyone reading the source could skip the form. It comes from the server now.',
    'The demo and free-trial pages were drawing two headers on top of each other, so the BetterCricket logo overlapped its own name. Both pages were being treated as a club page as well as a BetterCricket one; now they are one or the other.',
  ],
}
