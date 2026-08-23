export default {
  version: 'v8.73.3',
  date: '2026-07-18',
  sortKey: '2026-07-18T16:00:00Z',
  title: 'Setup Wizard round two: "doesn\'t apply", smarter buttons, live sync progress',
  items: [
    'Optional steps (Connect Square, Connect Xero, historical imports) now have a "Doesn\'t apply to us" button. Unlike skipping, it takes the step off your list entirely, no more being nagged about Square when your club doesn\'t use it. Reversible any time from the same step.',
    'Steps that tick themselves off automatically no longer show a manual "mark done" button. Do the thing and the wizard notices. Manual steps now offer both "Next" and "Mark done & next".',
    'The every-5th-visit reminder pop-up is gone. In its place, the Setup Wizard item in the side menu carries a small count of steps still to do.',
    'While your first full sync is running, locked steps now show its live progress instead of a dead-end message, and unlock themselves the moment it finishes.',
    'Your social post style (palette, font, background, saved designs) now saves to your club, not just this browser, and the palette setup step ticks itself off once you\'ve saved a style. The "roll members over" step was dropped from the wizard (it only matters from season two).',
    'Each step shows a rough time estimate, and the wrap-up screen can copy a plain-text setup summary for your committee chat.',
  ],
}
