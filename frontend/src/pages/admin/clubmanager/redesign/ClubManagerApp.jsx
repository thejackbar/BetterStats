import { useState, useEffect, useCallback } from 'react'
import BetterClubhouseLayout from '../../../../components/admin/BetterClubhouseLayout'
import Today from './screens/Today'
import Roster from './screens/Roster'
import Directory from './screens/Directory'
import Committee from './screens/Committee'
import ClubDiary from './screens/ClubDiary'
import Facilities from './screens/Facilities'
import Events from './screens/Events'
import AreasRoles from './screens/AreasRoles'
import InternalDirectory from './screens/InternalDirectory'

// The People and Club screens of BetterClubhouse.
//
// These used to be BetterClubManager: a self-contained fork with its own 232px
// sidebar, its own indigo accent and its own internal navigation. The merge
// took all three away — the sidebar and the module chrome are
// BetterClubhouseLayout's now, the accent is the shared amber, and each screen
// is reached by its own route rather than by a key held in this component. What
// is left here is the view state the screens share and the small amount of
// mutable entity state (roster slot assignments, bookings, requests, returned
// loans); everything else is still derived on read inside each screen.
//
// The screens keep drawing their own sticky headers for now, so the layout runs
// with `hideHeader`. Rebuilding them onto the shared header is the next pass.

const SCREENS = {
  overview: Today, roster: Roster, directory: Directory, committee: Committee,
  diary: ClubDiary, facilities: Facilities, events: Events, setup: AreasRoles,
  // BetterCricket's own directory, reached only while acting as the outreach
  // org. A separate screen from `directory`, not a mode inside it — see the
  // scope rule in its own file header.
  internal_directory: InternalDirectory,
}

export default function ClubManagerApp({ initialScreen = 'overview' }) {
  const [st, setSt] = useState(() => {
    const w = typeof window !== 'undefined' ? window.innerWidth : 1600
    return {
      screen: initialScreen,
      view: 'people',
      dragId: null, dragPerson: null, overCell: null,
      selected: null, person: null, task: null, toast: null,
      openExpanded: false,
      w, panelOpen: w >= 1280, navOpen: false,
      // per-screen locals
      diaryTab: 'plan', cadFilter: 'All', issuesOnly: false, diaryCollapsed: {},
      dirQuery: '', dirSeg: 'All', dirRole: null, dirExpiring: false, dirSel: null,
      facTab: 'availability', bookings: null, requests: null, returned: {},
      cteTab: 'meetings', cteMeeting: 'm5',
      event: 'e3',
      setupTab: 'roles',
      // configurable rostering settings (would become real club settings)
      enforceQualifications: true, weeklyShiftCap: 0,
    }
  })

  const patch = useCallback((p) => setSt(s => ({ ...s, ...(typeof p === 'function' ? p(s) : p) })), [])

  // Which screen shows is the route's business now. React can reuse this
  // component across two routes that both render it, so follow the prop rather
  // than trusting the state initialiser, which only ever runs once.
  useEffect(() => {
    setSt(s => (s.screen === initialScreen ? s : { ...s, screen: initialScreen }))
  }, [initialScreen])

  useEffect(() => {
    const onResize = () => setSt(s => ({ ...s, w: window.innerWidth, panelOpen: window.innerWidth >= 1280 ? true : (s.panelOpen && s.w >= 1280 ? false : s.panelOpen) }))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const opts = { enforceQualifications: st.enforceQualifications, weeklyShiftCap: st.weeklyShiftCap }
  const Screen = SCREENS[st.screen] || Today

  return (
    <BetterClubhouseLayout bare hideHeader>
      {/* `narrow` used to drive this fork's own off-canvas nav; the shell owns
          that now, so the screens' ☰ never renders. Their detail panes still
          collapse on their own width rule. */}
      <Screen st={st} patch={patch} opts={opts} narrow={false} />
    </BetterClubhouseLayout>
  )
}
