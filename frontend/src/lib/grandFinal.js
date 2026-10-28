// Marking a hand-entered match as the grand final, shared by Manual Games and Upload Historical Scorecard.
//
// A grand final is always a final, so the two ticks move together: ticking Grand Final ticks Final, and
// unticking Final unticks Grand Final. The server holds the same rule (a grand final is stored as a final);
// this only keeps the screen from showing a combination the server would change.

export function withFinalTick(form, checked) {
  return { ...form, is_final: checked, is_grand_final: checked ? !!form.is_grand_final : false }
}

export function withGrandFinalTick(form, checked) {
  return { ...form, is_grand_final: checked, is_final: checked ? true : !!form.is_final }
}

// What the club is told straight after saving a match marked as the grand final, from the status the server
// returns (`grand_final`). It is the server's own reading of the winner and result line, the one the
// premierships are written from, so the words cannot differ from what happened. Null for a match that is not
// marked.
export function grandFinalMessage(status) {
  if (!status) return null
  const n = status.players || 0
  switch (status.state) {
    case 'won':
      return `Marked as the grand final. ${n} player${n === 1 ? '' : 's'} on the card ${n === 1 ? 'has' : 'have'} the premiership now, on their Honours and the Premierships page.`
    case 'lost':
      return 'Marked as the grand final. Your side did not win it, so no premiership is written.'
    case 'no_grade':
      return 'Marked as the grand final, but the game has no grade, so the premiership has no team to name. Choose a grade and save again.'
    case 'undecided':
      return `Marked as the grand final, but no premiership is written yet: ${status.reason || 'the winner is not clear'}. `
        + 'Fill in the winning team or the result line (for example "Won by 20 runs") and save again.'
    default:
      return null
  }
}

export const GRAND_FINAL_HELP =
  'If your side won it, the players on the card get the premiership automatically. Set the winning team to your '
  + 'side, or start the result line with "Won", so we can tell.'
