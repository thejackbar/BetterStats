// How a matchday's teams are ordered and named, shared by the Selection board's
// team switcher and the draft table.

// Seniority rank for ordering a matchday's teams (1 = top team). Prefer the
// explicit Team.sequence; fall back to the first number in the team/grade name
// (mirrors the backend's _guess_sequence); unranked teams sink to the bottom.
export function teamSeq(f) {
  if (f?.team_sequence && f.team_sequence > 0) return f.team_sequence
  const m = (f?.team_name || f?.grade_name || '').match(/(\d+)/)
  return m ? parseInt(m[1], 10) : 999
}
export const teamNameOf = (f) => f?.team_name || f?.grade_name || f?.opponent_name || f?.label || 'Team'
export const oppLabelOf = (f) =>
  f?.home_away === 'BYE' ? 'BYE' : `${f?.home_away === 'AWAY' ? '@ ' : 'vs '}${f?.opponent_name || f?.label || 'TBC'}`

// Longest shared leading word-run across names, so a tag reads "2nd XI" not
// "Applecross 2nd XI" without hardcoding the club name.
export function commonPrefixWord(names) {
  if (names.length < 2) return ''
  let prefix = names[0]
  for (const n of names.slice(1)) {
    let i = 0
    while (i < prefix.length && i < n.length && prefix[i] === n[i]) i++
    prefix = prefix.slice(0, i)
    if (!prefix) break
  }
  const cut = prefix.lastIndexOf(' ')
  return cut > 0 ? prefix.slice(0, cut + 1) : ''
}
export const stripPrefix = (prefix, name) => (prefix && name?.startsWith(prefix) ? name.slice(prefix.length) : name)

// A matchday's teams, top side first.
export function sortTeams(fixtures) {
  return fixtures.slice().sort((a, b) => teamSeq(a) - teamSeq(b) || teamNameOf(a).localeCompare(teamNameOf(b)))
}
