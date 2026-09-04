export default {
  version: 'v9.65.2',
  date: '2026-09-04',
  sortKey: '2026-09-11T10:00:00Z',
  title: 'A member’s tier stops disappearing, and every save button saves every change',
  items: [
    'Saving a member’s Membership panel in Accounts wiped their Membership Tier, so a member an admin had just filed under Senior Player came back reading “No tier assigned — fees won’t calculate.” A save now only changes the tier when the tier is what was edited.',
    'Ticking “Registered with PlayHQ” on the Accounts list did the same thing silently, with nothing on screen to say a tier had gone. That write leaves the tier alone as well.',
    'Membership, Membership Tier and Contact & Notes are three panels but one act of saving. Editing more than one and pressing any of the three buttons now saves all of them — before, whichever button was pressed kept its own panel and threw the others away.',
    'A panel you have edited is marked UNSAVED, and a button that is about to write another panel’s changes says so before you press it.',
  ],
}
