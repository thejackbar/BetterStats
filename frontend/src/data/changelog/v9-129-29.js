export default {
  version: 'v9.129.29',
  date: '2026-10-25',
  // Above v9.129.28's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-08T17:00:00Z',
  title: 'The player page says who you are logging in as',
  items: [
    'Players kept telling clubs that the last 4 digits of their mobile did not work. Most of the time they had tapped somebody else\'s name, or opened a link that already had someone else picked, and were typing their own number against that person.',
    'On the player page, the PIN step now opens with a box that says "You are logging in as" with the name in large type. The label asks for the last 4 digits of that person\'s mobile by name, and the button reads "Log in as" and the name.',
    'A wrong PIN now repeats who they are logging in as and tells them to pick their own name if it is not them. "This isn\'t me. Pick a different name" is a proper button in the box, not small grey text underneath.',
    'The list of names is headed "Who are you?" and says the mobile is checked against the name they tap. Once signed in, the top of the page reads "Signed in as" and the name beside the Not you? link.',
  ],
}
