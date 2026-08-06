export default {
  version: 'v9.13.0',
  date: '2026-08-06',
  sortKey: '2026-08-12T09:00:00Z',
  title: 'A club a super admin creates is set up like one that signs itself up',
  items: [
    'Super Admin → All Clubs → New Club now does everything the self-serve trial signup does. Before this it created a bare club row and stopped there, so a staff-created club had no trial, no admin account, no data and nothing in the pipeline until somebody remembered each step.',
    'A Primary Club Admin is now required, not optional. The form takes their name, username, email and (optionally) mobile. No password is set by staff — that person is emailed a link to set their own, the same way Club Users → Invite admin already works.',
    'The club starts a free trial of every module, on the same trial length a self-serve signup gets, BetterStats included.',
    'The club’s first full historical sync starts the moment it is created, and its past-season yearbooks are built and published when that sync finishes.',
    'The setup wizard now opens for the primary admin on their first login, even when they accept their invite days after the club was created and its sync has long since finished.',
    'The club lands on the Sales Pipeline straight away as a deal marked Onboarding method = Super Admin Trial, with its engagement score worked out at creation instead of at the next overnight refresh.',
    'That score is deliberately lower than a club that registered itself. Staff setting a club up says less about how interested the club is, and the score is now honest about which of the two happened.',
  ],
}
