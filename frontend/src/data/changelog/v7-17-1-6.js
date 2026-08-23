export default {
  "version": "v7.17.1.6",
  "date": "2026-05-26",
  "sortKey": "2026-05-26T00:00:37Z",
  "title": "Fix: notification bell unclickable + permanent changelog page",
  "items": [
    "Bell modal now opens immediately on click and fetches the summary in the background, previously a silent error in the summary fetch left the bell unresponsive",
    "Modal shows an explicit Loading / Error state instead of just doing nothing",
    "New Admin → Account → Changelog page keeps every release note around, so dismissed updates can still be referenced later",
    "Modal footer gained an 'All Updates' link straight to the new page"
  ]
}
