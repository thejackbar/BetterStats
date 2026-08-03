import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../../lib/api'
import { C, MONO, ACCENT } from './ui'
import clubLogo from '../../../../assets/modules/betterclubmanager.svg'
import Today from './screens/Today'
import Roster from './screens/Roster'
import Directory from './screens/Directory'
import Committee from './screens/Committee'
import ClubDiary from './screens/ClubDiary'
import Facilities from './screens/Facilities'
import Events from './screens/Events'
import AreasRoles from './screens/AreasRoles'

// The redesigned BetterClubManager surface: one self-contained shell with its
// own 232px sidebar and eight internally-navigated screens, faithfully porting
// the reference prototype. All view state and the small amount of mutable entity
// state (roster slot assignments, bookings, requests, returned loans) live here;
// everything else is derived on read inside each screen.

const NAV_ICONS = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  roster: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9h18M8 3v3M16 3v3" /></>,
  directory: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 6.5a3 3 0 0 1 0 6M17.5 19a5.5 5.5 0 0 0-3-4.9" /></>,
  committee: <><rect x="4" y="3.5" width="16" height="17" rx="2" /><path d="M8 8.5h8M8 12h8M8 15.5h5" /></>,
  diary: <path d="M5 21V9M12 21V4M19 21v-8" />,
  facilities: <path d="M4 4v16M20 4v16M4 4h16M4 9h16M4 14h16M4 19h16M9 4v16M14 4v16" />,
  events: <><circle cx="12" cy="13" r="8" /><path d="M12 13V9M9 2h6M12 5V2" /></>,
  setup: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M22 12h-3M5 12H2M19.1 4.9l-2.1 2.1M7 17l-2.1 2.1M19.1 19.1L17 17M7 7L4.9 4.9" /></>,
}

const NAV = [
  { key: 'overview', label: 'Today' },
  { heading: 'PEOPLE' },
  { key: 'roster', label: 'Roster' },
  { key: 'directory', label: 'Directory' },
  { key: 'committee', label: 'Committee' },
  { heading: 'CLUB' },
  { key: 'diary', label: 'Club Diary' },
  { key: 'facilities', label: 'Facilities' },
  { key: 'events', label: 'Events' },
  { heading: 'SETUP' },
  { key: 'setup', label: 'Areas & Roles' },
]

function NavIcon({ name }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      {NAV_ICONS[name]}
    </svg>
  )
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

  // Real club branding for the shell header — same source the other module
  // layouts read (the acting-as club's own settings). The screens below still
  // run on demo data until their data layer is wired.
  const [club, setClub] = useState(null)
  useEffect(() => {
    let alive = true
    api.adminGetSettings().then(s => { if (alive && s) setClub(s) }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    const onResize = () => setSt(s => ({ ...s, w: window.innerWidth, panelOpen: window.innerWidth >= 1280 ? true : (s.panelOpen && s.w >= 1280 ? false : s.panelOpen) }))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const narrow = st.w < 1280
  const opts = { enforceQualifications: st.enforceQualifications, weeklyShiftCap: st.weeklyShiftCap }

  const goScreen = (key) => patch({ screen: key, navOpen: false })

  const SCREENS = {
    overview: Today, roster: Roster, directory: Directory, committee: Committee,
    diary: ClubDiary, facilities: Facilities, events: Events, setup: AreasRoles,
  }
  const Screen = SCREENS[st.screen] || Today

  return (
    <div style={{ minHeight: '100vh', display: 'flex', background: C.bg, color: C.text, fontFamily: 'Geist, Inter, system-ui, sans-serif', '--pb-accent': ACCENT, '--pb-accent-rgb': '99 102 241' }}>
      <style>{'@keyframes bcmRiseIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }'}</style>

      {/* Off-canvas backdrop */}
      {narrow && st.navOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 69, background: 'rgba(0,0,0,0.5)' }} onClick={() => patch({ navOpen: false })} />
      )}

      {/* Sidebar */}
      <aside className="pb-scroll" style={
        narrow
          ? (st.navOpen
            ? { width: 232, position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 70, borderRight: `1px solid ${C.hair}`, background: C.surface, display: 'flex', flexDirection: 'column', boxShadow: '0 0 40px rgba(0,0,0,0.5)' }
            : { display: 'none' })
          : { width: 232, flex: '0 0 232px', borderRight: `1px solid ${C.hair}`, background: C.surface, display: 'flex', flexDirection: 'column', position: 'sticky', top: 0, height: '100vh' }
      }>
        <div style={{ padding: 16, borderBottom: `1px solid ${C.hair}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {club?.logo_url
              ? <img src={club.logo_url} alt="" style={{ width: 32, height: 32, borderRadius: 4, objectFit: 'contain', background: C.surface2, flexShrink: 0 }} />
              : <span style={{ width: 32, height: 32, borderRadius: 4, background: 'rgba(99,102,241,0.15)', color: C.accent, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 15 }}>{(club?.name || 'C')[0]}</span>}
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14, lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={club?.name || ''}>{club?.name || 'Your club'}</div>
              <div style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, letterSpacing: '0.08em' }}>2026/27 SEASON</div>
            </div>
          </div>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
            <img src={clubLogo} alt="" style={{ width: 26, height: 26, borderRadius: 8, flexShrink: 0 }} />
            <span style={{ fontWeight: 700, fontSize: 14, lineHeight: 1 }}>Better<span style={{ color: C.accent }}>ClubManager</span></span>
          </span>
          <Link to="/admin" style={{ display: 'block', marginTop: 12, fontSize: 11, fontFamily: MONO, color: C.faintest }}>← Back to admin</Link>
        </div>
        <nav className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {NAV.map((item, idx) => {
            if (item.heading) {
              return <div key={`h${idx}`} style={{ padding: '16px 16px 4px', fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faint }}>{item.heading}</div>
            }
            const active = st.screen === item.key
            return (
              <button key={item.key} onClick={() => goScreen(item.key)}
                style={{ display: 'flex', alignItems: 'center', gap: 11, width: '100%', padding: '8px 16px', fontSize: 13.5, background: active ? 'rgba(99,102,241,0.1)' : 'transparent', color: active ? C.accent : C.faint, border: 'none', borderRight: active ? `2px solid ${C.accent}` : '2px solid transparent', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit' }}>
                <NavIcon name={item.key} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>
      </aside>

      {/* Main column */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <Screen st={st} patch={patch} opts={opts} narrow={narrow} />
      </div>

    </div>
  )
}
