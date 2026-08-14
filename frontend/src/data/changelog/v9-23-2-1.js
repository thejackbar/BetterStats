export default {
  version: 'v9.23.2.1',
  date: '2026-08-14',
  sortKey: '2026-08-14T13:00:00Z',
  title: 'Merging players could fail with "a data conflict blocked it"',
  items: [
    'Merging two players whose losing record had a BetterFees/Clubhouse member row attached (Accounts, committee roles, volunteer hours, etc.) could fail outright with "null value in column organisation_id of relation fee_members violates not-null constraint".',
    'Cause: the guard added to stop a member row linking to another club\'s player deletes the link by nulling BOTH sides of it when the linked player is removed, including the club it belongs to, which can never be null. Fixed so only the player link clears; the member stays exactly where it was, just unlinked from the merged-away player.',
  ],
}
