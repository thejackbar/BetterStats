export default {
  version: 'v9.137.4.2',
  date: '2026-11-02',
  // Above v9.137.4.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T09:20:00Z',
  title: 'Emails greet people by first name',
  items: [
    'Fixed: the selection email said "You\'ve been selected, Oliphant," because it took the first word of a name stored as "Oliphant, Iain". Selection emails (the captain\'s team sheet, the player email and any template using the first name variable) now greet by first name.',
    'Fixed: the same mistake in the voting reminders (cricket and football), player card swap alerts, member portal sign-in and reminder emails, club diary reminders, webinar emails, invoice and trial emails, invites and the sales emails. Each now takes the given name whichever way the name is stored.',
    'Fixed: names printed inside a selection email (the captain, the side, the team sheet and the list of players with no mobile) now follow the club\'s name format under Settings, so a club on First Name Last Name reads "Iain Oliphant".',
    'The name variable in BetterComms now reads "Iain Oliphant" for a player stored as "Oliphant, Iain". Names a person typed in are left as typed. Card swap alerts name the other player the same way.',
  ],
}
