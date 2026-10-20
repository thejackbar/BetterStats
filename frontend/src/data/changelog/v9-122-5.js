export default {
  version: 'v9.122.5',
  date: '2026-10-25',
  // Above v9.122.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-10-25T06:00:00Z',
  title: 'Accounts splits who owes membership from who owes match fees, with a CSV of whoever is listed',
  items: [
    'On Accounts, the Owes money button now has two partners: Owes membership and Owes match fees. Owes money still lists everyone who owes anything, so you get the combined view as before. Each button shows how many people are in it.',
    'Someone who owes both appears under both buttons. The Owed column shows the amount for the button you picked, and a small line under it shows the membership and match fee amounts side by side.',
    'The summary cards now show the membership owing and match fees owing totals for the season. Click either one, or Outstanding, to jump to that list.',
    'There is a new Export button next to Sync match days. It downloads a CSV of exactly the people listed, so it follows the owing button, the search box and the Membership, Role and More filters. The file has payable, paid and owing for membership and for match fees, plus the total, with email and mobile for the follow-up.',
    'On a phone, each person\'s card shows the same membership and match fee split.',
  ],
}
