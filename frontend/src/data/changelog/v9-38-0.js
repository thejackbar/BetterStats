export default {
  version: 'v9.38.0',
  date: '2026-08-20',
  sortKey: '2026-08-20T06:00:00Z',
  title: 'Engagement Score Parameters',
  items: [
    'Better HQ → CRM → Engagement Score Parameters: every number that decides a club\'s engagement score is now editable by a Super Admin, with no deploy.',
    'The membership floor is editable for the first time. It decided whether a club appears on the sales pipeline at all, and was hardcoded so that a single anonymous page view, or one auto-fired email open, created a deal card.',
    'Preview before you save. Scores every club under the proposed values without saving anything, and shows the before-and-after distribution, how many cards would join or leave the board, and how many clubs would cross the Twenty Opportunity line.',
    'Two known scoring defects are now switchable, and default to the old behaviour so nothing moves on upgrade: a direct enquiry could LOWER a busy prospect\'s score from 100 to 80, and the heartbeat sent every 25 seconds while a page is open counted towards the score, so one forgotten tab could max it out.',
    'Saving records who changed what, when and why, and kicks a full rescore.',
  ],
}
