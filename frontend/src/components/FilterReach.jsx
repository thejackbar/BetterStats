/**
 * Which panels the filter bar above them actually reaches.
 *
 * THE FILTER BAR IS PAGE-LEVEL — it sits above the tab bar, so every tab on a
 * player profile renders underneath it. Most panels honour it; a few do not,
 * and until now nothing on screen said which. A club filtering to Men's on
 * Batting found the women's grades back on the Milestones tab one click later
 * and had no way to tell whether that was a bug.
 *
 * The fix is not to filter everything. Some panels are RIGHT to ignore it, for
 * two different reasons, so a single generic disclaimer would be wrong in both
 * directions:
 *
 *   'enumeration'  the panel IS the list of every value of something. Filtering
 *                  Competitions to one competition gives a one-row table; the
 *                  Formats page filtered by format gives a one-column one.
 *   'career'       the figure is a fact about a whole career. "247 runs to
 *                  5,000" recomputed under a Men's-only filter is a number
 *                  nobody can act on, and it is what the notification bell
 *                  reports.
 *
 * IT FIRES ON WHAT THE PERSON PICKED, NEVER ON THE CLUB DEFAULT. A club with a
 * junior programme has a default scope active on every visit with nobody having
 * touched a control — and a note on six tabs about a filter they did not turn
 * on is exactly the "a note on everything teaches people to stop reading
 * notes" problem, gated behind a condition that is true by default for a large
 * share of clubs. The default is already announced once, by the header. So
 * `pick` is the raw selection off the URL (null when untouched), not the
 * resolved scope, and nothing here draws until something is genuinely picked.
 */

// What each filter is called on screen, in the order the bar draws them. Used
// to name only the filters that are actually ON — a note mentioning Match type
// when nobody has touched it reads as a fault in a control they never used.
const FILTER_LABELS = [
  ['competitions', 'Competition'],
  ['categories', 'Grade type'],
  ['formats', 'Match type'],
]

/** The filters the person has explicitly set, by the names on the bar. */
export function pickedFilterNames(pick) {
  if (!pick) return []
  return FILTER_LABELS.filter(([key]) => !!pick[key]).map(([, label]) => label)
}

function joinNames(names) {
  if (names.length <= 1) return names[0] || ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * One line saying this panel does not answer to the filter above it.
 *
 * Renders NOTHING when nothing has been picked, which is the common case and
 * most visits — the same rule the coverage note keeps.
 */
export function FilterReachNote({ pick, reason = 'enumeration', shows = null,
                                  className = '' }) {
  const names = pickedFilterNames(pick)
  if (!names.length) return null
  const which = joinNames(names)
  const plural = names.length > 1 ? 'filters' : 'filter'

  let text
  if (reason === 'career') {
    text = `Counted across the whole career. The ${which} ${plural} above `
         + `${names.length > 1 ? 'do' : 'does'} not change this.`
  } else {
    text = `Shows ${shows || 'everything'}, whatever is picked above — this panel `
         + `is the list, so the ${which} ${plural} ${names.length > 1 ? 'do' : 'does'} `
         + `not narrow it.`
  }

  return (
    <p className={`font-mono text-[10px] text-pb-dim tracking-wide2 ${className}`}>
      {text}
    </p>
  )
}

/**
 * A small mark on a tab label the picked filter will not reach, so a reader
 * knows BEFORE opening the tab rather than after. Drawn only while something
 * is picked, like the note. The title carries the reason for a hover.
 */
export function FilterReachDot({ pick, reason = 'enumeration' }) {
  const names = pickedFilterNames(pick)
  if (!names.length) return null
  const title = reason === 'career'
    ? `Whole-career figures. The ${joinNames(names)} filter does not change them.`
    : `Lists everything. The ${joinNames(names)} filter does not narrow it.`
  return (
    <span aria-label={title} title={title}
      className="inline-block w-1.5 h-1.5 rounded-full ml-1.5 align-middle"
      style={{ background: 'var(--pb-dim)' }} />
  )
}

export default FilterReachNote
