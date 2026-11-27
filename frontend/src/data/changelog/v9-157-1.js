export default {
  version: 'v9.157.1',
  date: '2026-11-27',
  // Above v9.157.0's sortKey (2026-11-27T20:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-27T21:00:00Z',
  title: 'Trial sign-ups land on our contact list with their club, and a check for missing club admin contacts',
  items: [
    'Someone who signs up for a trial is put on BetterCricket’s own contact list as part of the registration, and now always with their club attached. A club that was not in the Clubs Directory yet used to get its admin filed with no club, so the club name and trial days left came out blank in emails.',
    'A new script, ensure_admin_directory_contacts, checks every club admin against the contacts already stored for their club in the Clubs Directory and adds the ones who are missing, with the name, email and mobile on their account. It is a dry run unless you add --apply, and it never edits or removes a contact that is already there.',
  ],
}
