export default {
  version: 'v8.60.2',
  date: '2026-07-14',
  sortKey: '2026-07-14T14:00:00Z',
  title: 'Club Users: edit email and mobile, reset a password properly, and a fixed invite email',
  items: [
    'The admin invite email had an awkward "<<first_name>> have been added as an admin" line with no greeting: it now reads "Hi <<name>>, you have been added as a Club Admin for <<club>> on BetterCricket."',
    'The Add User form now checks the email and mobile number look valid before sending the invite, matching what the server already checks.',
    'Editing an existing Club Admin can now update their email and mobile number, not just their display name.',
    'Setting a new password for a Club Admin directly now follows the same password rules (length, uppercase, number, special character, confirm match) as every other password-setting flow in BetterCricket, instead of a much weaker 6-character minimum.',
    'Added a "Email reset link" button on a Club Admin\'s edit panel, so a user can be sent a link to set their own new password instead of an admin typing one in for them.',
    'Email and mobile number only need to look like a valid email/number now. They no longer have to be unique across accounts.',
  ],
}
