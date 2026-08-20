export default {
  version: 'v9.38.0.1',
  date: '2026-08-20',
  sortKey: '2026-08-20T07:00:00Z',
  title: 'Sales Workspace: drawer header pinned right, history says who, and no more scroll jumps',
  items: [
    "The Contacted by dropdown and Extend Trial button sometimes wrapped onto the left of the drawer's header instead of staying in the top right. They're locked there now, whatever the club name or its associations run to.",
    "Every entry in a club's History — a logged call, a note, an email, an assignment, an extended trial — now names the rep or admin who did it.",
    'The Meta ad card no longer lists the raw landing URLs (each click carries its own tracking code, so the same page was showing up several times over) — the landing count and the date(s) it happened already say what matters.',
    'Ticking a Call status box (Not Contacted, Contacted, Followup, VM, Sent Email) was sometimes scrolling the page, depending on where the selected club sat in the list. A filter tweak never moves the viewport now — only an actual action (a logged call, a sent email, an assignment) still re-anchors to the open club so it stays on screen.',
  ],
}
