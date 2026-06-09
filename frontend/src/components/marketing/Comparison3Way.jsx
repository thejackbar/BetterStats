import ComparisonTable from './ComparisonTable'
import { COMPARISONS } from '../../data/marketing'

/**
 * Backwards-compatible wrapper around the generic ComparisonTable.
 *
 * Existing pages import <Comparison3Way />. It now renders a named comparison
 * from COMPARISONS (default: the whole-platform comparison used on the home
 * page). Pass `which` to pick a different surface — e.g. which="betterstats".
 */
export default function Comparison3Way({
  id = 'compare',
  which = 'platform',
  heading,
  sub,
  showCTA = true,
  showBillingToggle = false,
}) {
  return (
    <ComparisonTable
      comparison={COMPARISONS[which] || COMPARISONS.platform}
      id={id}
      heading={heading}
      sub={sub}
      showCTA={showCTA}
      showBillingToggle={showBillingToggle}
    />
  )
}
