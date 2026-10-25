export default {
  version: 'v9.129.27.1',
  date: '2026-10-25',
  // Above v9.129.27's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T15:00:00Z',
  title: 'Fix: club pictures with long text are shrunk to fit instead of being skipped',
  items: [
    'Clubs whose picture had a long association name, a long grade name or long player names could not be drawn, because the text ran past the bottom of the picture and the drawer refused to save it. The picture now shrinks its text, a little at a time, until it fits inside its margins. An ordinary club\'s picture is exactly as before.',
    'A picture that cannot be made to fit even at 60 percent is still refused, and the message now says which size it was (card, feed or story).',
  ],
}
