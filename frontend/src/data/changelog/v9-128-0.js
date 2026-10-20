export default {
  version: 'v9.128.0',
  date: '2026-10-20',
  sortKey: '2026-10-20T12:00:00Z',
  title: 'A picture of every club\'s season, for emails and ads',
  items: [
    'Each club with a season snapshot can now have a picture: the club, the season, the top run-scorer or wicket-taker and up to three supporting facts. It is drawn in three sizes: a wide card for emails and link previews, and a feed size and a story size for ads. A club with no logo gets a crest of its initials.',
    'The email card names the player behind the lead figure. The two ad sizes never print a player\'s name, so nothing about an individual goes into paid creative unless the club chooses it.',
    'Club Directory: the teaser crawl panel shows how many pictures are drawn and how many are waiting, with a Draw pictures button that does a batch of 50 in the background. The same run is available from the server as render_club_teasers.',
    'BetterComms: two new merge variables for outreach emails. {{teaser_url}} is the recipient club\'s own season page. {{teaser_image_url}} is its picture, for an image inside a link to that page. Both are blank for a club with no snapshot, and the picture is blank until it has been drawn.',
    'BetterComms: a new "Club season snapshot" template for the BetterCricket outreach library, and a new audience choice, "Snapshot and picture ready", under "Club has a teaser snapshot", so a send only reaches clubs that have a picture.',
    'A link to a club\'s season page now previews with that club\'s own picture when it is shared.',
  ],
}
