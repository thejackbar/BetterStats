export default {
  version: 'v9.84.2',
  date: '2026-09-21',
  // Above v9.84.1's sortKey (origin/main shipped a v9.84.1 for the Club Diary
  // while this was in flight, so this renumbered). Check origin/main at merge.
  sortKey: '2026-09-29T00:45:00Z',
  title: 'A general note about anyone in the Directory',
  items: [
    "The BetterAdmin Directory now has a Notes card on every person, for a free-text, multi-line note about them: a note to selectors, a reason they are unavailable for a stretch, whatever is worth writing down. It saves as you leave the box and reads back on the person's own record.",
    "It works for anybody, including a player who is only in the Directory read-through from Stats. Recording a note about them adds them to the member directory, the same as recording a kit size or assigning a role.",
    "Fixed along the way: the Add/Edit dialog carried a hidden note field that nothing showed but every save still sent, so editing a person's name could quietly wipe a note. Notes now have one home, the card, and editing a name never touches them.",
  ],
}
