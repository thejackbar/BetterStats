import { useState, useMemo } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import BetterSelectLayout, { NAV } from '../../../../components/admin/BetterSelectLayout'
import { SelectHeaderContext } from './ui'

// BetterSelect on football is cricket's module surface, not a section of the
// football admin sidebar: the same BetterSelectLayout (module-branded sidebar
// with the lockup, module switcher, header) on the same /admin/betterselect
// URLs, with football's own screens inside it. Cricket's layout takes the title
// as a prop, so the shell derives it from the route; each screen's PageHead
// carries its actions up into the header slot below, where cricket keeps them.
export default function AflSelectShell() {
  const { pathname } = useLocation()
  const [actionsEl, setActionsEl] = useState(null)
  const slot = useMemo(() => ({ actionsEl }), [actionsEl])

  const here = NAV.find(i => i.to && i.to !== '/admin/betterselect' && pathname.startsWith(i.to))
  const title = here?.label || 'Overview'

  return (
    <SelectHeaderContext.Provider value={slot}>
      <BetterSelectLayout
        title={title}
        actions={<div ref={setActionsEl}
          // The layout keeps its actions shrink-0, so the row has to be given a
          // ceiling to wrap against: the viewport less the page gutters, and on
          // md and up less the 15rem sidebar as well.
          className="flex flex-wrap items-center justify-end gap-2 max-w-[calc(100vw-2rem)] md:max-w-[calc(100vw-18rem)]" />}
      >
        <Outlet />
      </BetterSelectLayout>
    </SelectHeaderContext.Provider>
  )
}
