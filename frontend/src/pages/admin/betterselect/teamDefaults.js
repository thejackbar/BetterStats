// A team's starting filters for the Selection board (BetterSelect, Settings, Team
// defaults). The club writes them as rules: "the women's team starts on Gender =
// Women", "the 1st XI only sees the top three squads". The board applies the
// merged rules for the fixture's team as a STARTING view: the selector's own pick
// for a filter wins, and one click switches the defaults off for the match. They
// never remove anyone for good.

const GENDER_LABEL = { male: 'Men', female: 'Women' }

/** The rules for `teamId` merged into one starting view, or null when none apply.
 *  `squads` is the club's squads in XI order ([{ name, sequence }], unranked
 *  last), which is what "top N squads" is counted against. */
export function teamDefaultFor(rules, teamId, squads) {
  const mine = (rules || []).filter((r) => (r.team_ids || []).includes(String(teamId)))
  if (!mine.length) return null
  const ranked = (squads || []).filter((s) => (s.sequence || 0) > 0)
  const names = []
  let gender = ''
  let playedYears = null
  let top = null
  mine.forEach((r) => {
    if (r.gender && !gender) gender = r.gender
    if (r.played_years != null && playedYears == null) playedYears = r.played_years
    if (r.top_squads) top = top == null ? r.top_squads : Math.max(top, r.top_squads)
    ;(r.squads || []).forEach((n) => { if (!names.includes(n)) names.push(n) })
  })
  if (top) ranked.slice(0, top).forEach((s) => { if (!names.includes(s.name)) names.push(s.name) })
  if (!gender && !names.length && playedYears == null) return null
  return { gender, squads: names, playedYears, top }
}

const playedWords = (n) => (n === 0 ? 'played any time' : n < 0 ? 'played this season' : `played within ${n} year${n === 1 ? '' : 's'}`)

/** One line for the banner: "Women · 1st XI, 2nd XI, 3rd XI · played any time". */
export function teamDefaultSummary(d) {
  const bits = []
  if (d.gender) bits.push(GENDER_LABEL[d.gender] || d.gender)
  if (d.squads.length) bits.push(d.squads.length <= 4 ? d.squads.join(', ') : `${d.squads.slice(0, 3).join(', ')} +${d.squads.length - 3}`)
  if (d.playedYears != null) bits.push(playedWords(d.playedYears))
  return bits.join(' · ')
}
