export default {
  version: 'v9.128.13',
  date: '2026-10-23',
  // Above v9.128.12's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T10:00:00Z',
  title: 'Player dashboard: Update details, and every section starts closed',
  items: [
    'Players can update their own details from the dashboard. An "Update details" button opens a pop-up with their email, mobile, street address, suburb, state, postcode and an emergency contact name and mobile. They change what they want and save. Boxes they leave alone stay as they are, and a box they empty is cleared.',
    'Saving asks for their current PIN again, the last 4 digits of the mobile the club has for them now. Changing the mobile changes the PIN, and the pop-up says so. The button only appears when the club has the PIN switched on for the link, because without a PIN anyone holding the link could open anybody\'s page.',
    'Each change leaves a "Player details" entry in the BetterSelect audit history, naming the player and which details changed and keeping the old values so the club can put one back. The club\'s fee record moves with them only where it held their old email or mobile (or nothing); a different email there, such as a parent\'s, is left alone.',
    'Address and emergency contact now sit on the player\'s admin profile next to email and phone, so the club can see and correct them, and they carry across a player merge.',
    'On a first visit the dashboard\'s five sections all start closed, so it opens as five short lines (for example "1 to answer", "$60.00 owing"). A section a player opens stays open next time on that device.',
  ],
}
