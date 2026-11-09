// What a result post says when nobody won. The editor keeps `winner: 'TIE'` as the
// "no winner" bucket (every layout, the bundle and Custom Edit already read it), and
// this says WHICH no-winner it is, so an abandoned game is not printed as a tie.

export const NO_WINNER_KINDS = [
  { key: 'TIE', label: 'Match tied', line: 'MATCH TIED', word: 'TIE' },
  { key: 'ABANDONED', label: 'Match abandoned', line: 'MATCH ABANDONED', word: 'ABANDONED' },
  { key: 'ABANDONED_WET', label: 'Abandoned due to wet weather', line: 'ABANDONED DUE TO WET WEATHER', word: 'ABANDONED' },
  { key: 'NO_RESULT', label: 'No result', line: 'NO RESULT', word: 'NO RESULT' },
  { key: 'CUSTOM', label: 'Type my own', line: '', word: '' },
]

const byKey = (key) => NO_WINNER_KINDS.find((k) => k.key === key) || NO_WINNER_KINDS[0]

// The big line ("MATCH ABANDONED"). `custom` is what the club typed for Type my own.
export function noWinnerLine(kind, custom) {
  if (kind === 'CUSTOM') return String(custom || '').trim().toUpperCase() || byKey('TIE').line
  return byKey(kind).line
}

// The one word a layout prints in a big slot ("TIE", "ABANDONED").
export function noWinnerWord(kind, custom) {
  if (kind === 'CUSTOM') return String(custom || '').trim().toUpperCase() || byKey('TIE').word
  return byKey(kind).word
}

// Read a Cricket Australia result line ("Match abandoned due to rain", "No result",
// "Match tied") into one of the kinds above. Null means the text names no such
// outcome, so the caller falls back to its own rule (equal scores read as a tie).
export function detectNoWinner(resultText) {
  const t = String(resultText || '').toUpperCase()
  if (!t) return null
  const wet = /\b(WET|RAIN|RAINED|WEATHER|WASHED|WASH ?OUT|STORM|LIGHTNING|WATERLOG)/.test(t)
  if (/ABANDON/.test(t)) return wet ? 'ABANDONED_WET' : 'ABANDONED'
  if (/\bWASH(ED)? ?OUT\b/.test(t)) return 'ABANDONED_WET'
  if (/\bNO ?RESULT\b/.test(t)) return 'NO_RESULT'
  if (/\b(TIE|TIED|DRAW|DREW)\b/.test(t)) return 'TIE'
  return null
}
