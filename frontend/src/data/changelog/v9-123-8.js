export default {
  version: 'v9.123.8',
  date: '2026-10-19',
  // Above v9.123.7's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-30T10:00:00Z',
  title: 'Import a template with its fields, ready for the players',
  items: [
    'On the Blank canvas, Content has a new "Import a template file". The file comes from the BetterCricket Canva app: a design made in Canva, with a text field for every word typed as {{player 1}}, {{opponent}}, {{date}} and so on. It brings the design in as the locked bottom layer and puts one text block on it for each field, in the same place, size and colour as in Canva.',
    'The Players, Opponent and Match Info panels now show on an imported template, with as many player places as the template has. Add players and slot 1 fills first, then slot 2, and so on. A slot with no player prints nothing, so a half-filled lineup does not read "PLAYER 9". Until a player is added the slot shows a sample so you can see where it is.',
    'A field can be one of: player 1 to 15 (also first, last or role), captain, keeper, opponent, team, headline, competition, round, venue, date, time or season. A word that is not one of these stays as plain text and the import says so. A font BetterPosts does not have falls back to Inter and the import says that too.',
    'Importing the same template again replaces its design and fields and leaves anything else you added. A file that is not a template, or a newer version than this editor reads, changes nothing and says why. In the editor, a field shows "Field: Player 3" when selected, with an Unbind button that turns it back into plain text.',
  ],
}
