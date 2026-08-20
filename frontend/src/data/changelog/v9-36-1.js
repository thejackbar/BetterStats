export default {
  version: 'v9.36.1',
  date: '2026-08-20',
  sortKey: '2026-09-04T11:00:00Z',
  title: 'Sales Workspace: a faster detail pane, and where the club came from',
  items: [
    'Opening a club is quick for every club now. Three things were making some clubs slower than others: a suburb-boundary lookup that went out to OpenStreetMap for any club whose map had never been drawn, a website-analytics read that was scanning the whole visit log, and the trial-wizard lookup, which rebuilt a whole-platform table whenever its short cache had lapsed. The map and the origin cards load on their own now, so none of them hold up the pane.',
    'A new card says when a club came through a Meta ad: which ad and campaign, how many times they landed, on what page and when. The engagement breakdown already counted those clicks towards the score; now you can see what they actually were.',
    'The trial-page card says how far the club got through signing up, on the real eight-step funnel: "Gave up at verification code sent, step 4 of 8", or that they finished. It used to only say whether they had picked a club or reached the Terms step.',
    'Setup Wizard progress has its own row with a progress bar, instead of sitting in the middle of the run-on line of club facts. The total is the number of steps that apply to that club, which is why it is shown as "3 of 10" rather than against a fixed number.',
  ],
}
