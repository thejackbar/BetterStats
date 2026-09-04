/**
 * Which panels the filter bar above them actually reaches.
 *
 * THE FILTER BAR IS PAGE-LEVEL — it sits above the tab bar, so every tab on a
 * player profile renders underneath it. Eleven panels honour it and seven do
 * not, and until now nothing on screen said which. A club filtering to Men's
 * on Batting found the women's grades back on the Milestones tab one click
 * later and had no way to tell whether that was a bug.
 *
 * The fix is not to filter everything. Three of the seven are RIGHT to ignore
 * it, for two different reasons, so a single generic disclaimer would be
 * wrong in both directions:
 *
 *   'enumeration'  the panel IS the list of every value of something. Filtering
 *                  Competitions to one competition gives a one-row table; the
 *                  Formats page filtered by format gives a one-column one.
 *   'career'       the figure is a fact about a whole career. "247 runs to
 *                  5,000" recomputed under a Men's-only filter is a number
 *                  nobody can act on, and it is what the notification bell
 *                  reports.
 *   'unfiltered'   the panel simply does not take the scope. A gap, said out
 *                  loud until it is closed.
 *
 * ONE LIST, so a panel added later has to declare itself rather than quietly
 * inheriting a promise the filter bar cannot keep.
 */

// What each filter is called on screen, in the order the bar draws them. Used
// to name only the filters that are actually ON — a note mentioning Match type
// when nobody has touched it reads as a fault in a control they never used.
const FILTER_LABELS = [
  ['competition', 'Competition'],
  ['category', 'Grade type'],
  ['format', 'Match type'],
]

/** The filters currently doing something, by the names on the bar. */
export function activeFilterNames(scope) {
  if (!scope) return []
  return FILTER_LABELS
    .filter(([key]) => scope[`${key}_active`])
    .map(([, label]) => label)
}

function joinNames(names) {
  if (names.length <= 1) return names[0] || ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * One line saying this panel does not answer to the filter above it.
 *
 * Renders NOTHING when no filter is on, which is the common case and most
 * visits — the same rule the coverage note keeps. `shows` names what the panel
 * lists instead, for the enumeration case ("every competition").
 */
export function FilterReachNote({ scope, reason = 'unfiltered', shows = null,
                                  className = '' }) {
  const names = activeFilterNames(scope)
  if (!names.length) return null
  const which = joinNames(names)
  const plural = names.length > 1 ? 'filters' : 'filter'

  let text
  if (reason === 'enumeration') {
    text = `Shows ${shows || 'everything'}, whatever is filtered above.`
  } else if (reason === 'career') {
    text = `Counted across the whole career, whatever is filtered above.`
  } else {
    text = `The ${which} ${plural} above ${names.length > 1 ? 'do' : 'does'} `
         + `not apply here. This shows ${shows || 'everything'}.`
  }

  return (
    <p className={`font-mono text-[10px] text-pb-dim tracking-wide2 ${className}`}>
      {text}
    </p>
  )
}

export default FilterReachNote
