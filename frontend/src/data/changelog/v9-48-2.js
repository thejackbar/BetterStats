export default {
  version: 'v9.48.2',
  date: '2026-08-22',
  sortKey: '2026-08-22T20:00:00Z',
  title: 'Any follow-up can be handed to a named person, and Events can be filtered by who is responsible',
  items: [
    "Sales Workspace's \"Hand this follow-up to\" picker used to appear for only three call outcomes (Wants pricing, Wants more info, Wants a demo) — every other outcome that sets a follow-up date (Interested, Wants trial, Wants to subscribe, Wants trial extension, Wants committee discussion, Asked for a callback, Referred to someone else, Requested information) silently kept the event on whoever logged the call. Now every one of those offers the same picker: yourself, or any Super Admin.",
    'Both the Sales Workspace Events tab and the CRM Sales Pipeline Events tab now have a "Responsible" multi-select filter, so a Super Admin or sales rep can narrow the calendar or list to events one or several particular people own. The Sales Pipeline already had this; Sales Workspace gets the same picker, fed by a new endpoint open to both roles.',
  ],
}
