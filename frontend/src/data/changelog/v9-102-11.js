export default {
  version: 'v9.102.11',
  date: '2026-10-02',
  sortKey: '2026-10-02T20:00:00Z',
  title: 'BetterSelect: two selectors no longer overwrite each other\'s draft',
  items: [
    'If two people have the same Selection board open, one can no longer wipe out the other\'s draft. A board with nothing unsaved picks up the other selector\'s changes within a few seconds and tells you who made them.',
    'If you have changes of your own that have not saved when someone else changes the draft, the board stops saving and asks. "Use their version" replaces your board with theirs. "Keep mine" saves yours over theirs. Nothing is overwritten until you choose.',
    'The same applies when someone else confirms or discards the draft while you are editing it. You can go back to the confirmed XI or keep yours as a new draft.',
    'The Selection overview now marks any team that has a draft with "Draft, not confirmed", and the button on that team reads "Continue draft", so you can see which sides were left part way.',
  ],
}
