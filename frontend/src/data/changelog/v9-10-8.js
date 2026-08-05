export default {
  version: 'v9.10.8',
  date: '2026-08-05',
  sortKey: '2026-08-10T09:00:00Z',
  title: 'Won and Lost deals stay on the CRM board',
  items: [
    'Dragging a deal card onto Won or Lost/Dormant used to make it vanish from the sales pipeline altogether. Closing a deal changes its status as well as its stage, and the board only ever loaded open deals, so the card dropped out of view the moment it landed. Nothing was ever deleted, but there was no way back to it from the board.',
    'The board now shows every card in its own stage column, closed ones included. A won or lost card sits greyed out with its own tag, and you can drag it back to an earlier stage to reopen it.',
    'Open pipeline value, weighted value and the open count are still worked out from open deals only, so the figures across the top of the board have not moved.',
    'The Open, Won, Lost and All buttons still narrow the List view exactly as before.',
    'The Dashboard now has won and lost deals to count, so its trial conversion rate reads a real percentage instead of nothing.',
  ],
}
