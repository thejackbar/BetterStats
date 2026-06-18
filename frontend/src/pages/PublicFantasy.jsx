// BetterFantasyCricket — public member play (FPL-style redesign).
//
// Reached via a per-club link (/fantasy/:token). Members register with a name,
// email and PIN, build a 12-man squad within budget and the role quota, captain
// it, then track the club ladder, mini-leagues, transfers, chips and the draft.
// White-labelled from the club's own accent, light or dark on a member toggle.
// Design: docs/design_handoff_betterfantasy_redesign.
import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import {
  ensureThemeCss, loadThemePref, saveThemePref, resolveTheme, DEFAULT_ACCENT,
} from './fantasy/theme'
import { FantasyCtx, crestText, DISP, useIsDesktop, ThemeToggle } from './fantasy/ui'
import { AppHeader, NavPills, Banner } from './fantasy/shell'
import Auth from './fantasy/Auth'
import MyTeam from './fantasy/Team'
import Pick from './fantasy/Pick'
import Transfers from './fantasy/Transfers'
import Chips from './fantasy/Chips'
import Points from './fantasy/Points'
import Live from './fantasy/Live'
import Fixtures from './fantasy/Fixtures'
import Ladder from './fantasy/Ladder'
import Leagues from './fantasy/Leagues'
import Draft from './fantasy/Draft'
import { PlayerProfile, Compare, StatsExplorer } from './fantasy/Players'
import Notifications, { unreadCount } from './fantasy/Notifications'
import Settings, { HowToPlay } from './fantasy/Settings'
import Share from './fantasy/Share'

const NAV = [['team', 'My Team'], ['points', 'Points'], ['pick', 'Pick'], ['ladder', 'Ladder'], ['leagues', 'Leagues'], ['draft', 'Draft']]
const QUICK = [['transfers', 'Transfers'], ['chips', 'Chips'], ['fixtures', 'Fixtures'], ['stats', 'Players'], ['live', 'Live'], ['share', 'Share']]
// Screens with a dedicated desktop layout that should use the full width.
const WIDE = new Set(['team', 'transfers', 'points', 'stats'])

export default function PublicFantasy() {
  const { token } = useParams()
  const [phase, setPhase] = useState('loading')   // loading | dead | auth | app
  const [club, setClub] = useState(null)
  const [season, setSeason] = useState(null)
  const [manager, setManager] = useState(null)
  const [squad, setSquad] = useState(null)
  const [pool, setPool] = useState(null)
  const [rules, setRules] = useState(null)
  const [round, setRound] = useState(null)
  const [view, setViewRaw] = useState('team')
  const [params, setParams] = useState({})
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [unread, setUnread] = useState(0)

  const [themePref, setThemePref] = useState(loadThemePref())
  const [theme, setTheme] = useState(resolveTheme(loadThemePref()))
  const desktop = useIsDesktop()

  useEffect(() => { ensureThemeCss() }, [])
  // Resolve the member's theme preference; follow the OS when on Auto.
  useEffect(() => {
    setTheme(resolveTheme(themePref))
    if (themePref !== 'auto' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const on = () => setTheme(resolveTheme('auto'))
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [themePref])
  const setPref = (p) => { setThemePref(p); saveThemePref(p) }
  const onToggleTheme = () => setPref(theme === 'dark' ? 'light' : 'dark')
  const navItems = NAV.map(([k, l]) => [k, k === 'pick' && squad ? 'Edit' : l])

  const accent = club?.accent_color || club?.primary_color || DEFAULT_ACCENT
  const flash = (m) => { setMsg(m); setError(''); setTimeout(() => setMsg(''), 3500) }
  const fail = (e) => { setError(e.message || String(e)); setMsg(''); setTimeout(() => setError(''), 5000) }
  const nav = (v, p = {}) => { setParams(p); setViewRaw(v); setError(''); window.scrollTo?.(0, 0) }

  const loadApp = useCallback(async () => {
    const [m, p] = await Promise.all([api.fanMe(token), api.fanPool(token).catch(() => null)])
    setManager(m.manager); setSquad(m.squad); setRound(m.round)
    if (p) { setPool(p.players); setRules(p.rules) }
    return m
  }, [token])

  useEffect(() => {
    (async () => {
      try {
        const d = await api.fanLanding(token)
        setClub(d.club); setSeason(d.season)
        if (!d.season) { setPhase('dead'); return }
        setRules(d.season.rules)
        if (d.me) {
          setManager(d.me)
          const m = await loadApp()
          setViewRaw(m.squad ? 'team' : 'pick')
          setPhase('app')
        } else setPhase('auth')
      } catch { setPhase('dead') }
    })()
  }, [token, loadApp])

  // Notification badge (read-state is local to the device).
  const refreshNotifs = useCallback(() => {
    api.fanNotifications(token).then(d => setUnread(unreadCount(d.notifications))).catch(() => {})
  }, [token])
  useEffect(() => { if (phase === 'app') refreshNotifs() }, [phase, refreshNotifs, squad])

  const onAuthed = async () => { const m = await loadApp(); setViewRaw(m.squad ? 'team' : 'pick'); setPhase('app') }
  const logout = async () => { await api.fanLogout(token).catch(() => {}); setManager(null); setSquad(null); setPhase('auth') }

  const ctx = { club, crest: crestText(club), token }
  const rootSx = {
    minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)',
    fontFamily: "'Hanken Grotesk', -apple-system, sans-serif",
    '--pb-accent': accent,
  }

  const screen = () => {
    switch (view) {
      case 'team': return <MyTeam token={token} manager={manager} squad={squad} season={season} round={round} onChange={loadApp} flash={flash} fail={fail} nav={nav} desktop={desktop} />
      case 'pick': return <Pick token={token} pool={pool} rules={rules} squad={squad} season={season} onSaved={async () => { flash('Saved.'); await loadApp(); nav('team') }} fail={fail} flash={flash} nav={nav} />
      case 'transfers': return <Transfers token={token} squad={squad} pool={pool} rules={rules} round={round} onChange={loadApp} flash={flash} fail={fail} nav={nav} desktop={desktop} />
      case 'chips': return <Chips token={token} squad={squad} round={round} onChange={loadApp} flash={flash} fail={fail} nav={nav} />
      case 'points': return <Points token={token} nav={nav} desktop={desktop} />
      case 'live': return <Live token={token} nav={nav} />
      case 'fixtures': return <Fixtures token={token} season={season} nav={nav} />
      case 'ladder': return <Ladder token={token} season={season} />
      case 'leagues': return <Leagues token={token} flash={flash} fail={fail} />
      case 'draft': return <Draft token={token} flash={flash} fail={fail} />
      case 'player': return <PlayerProfile token={token} playerId={params.playerId} season={season} onBack={() => nav('team')} nav={nav} />
      case 'compare': return <Compare token={token} pool={pool} nav={nav} />
      case 'stats': return <StatsExplorer pool={pool} nav={nav} />
      case 'notifications': return <Notifications token={token} onSeen={() => setUnread(0)} />
      case 'settings': return <Settings token={token} manager={manager} squad={squad} themePref={themePref} setThemePref={setPref} onChange={loadApp} flash={flash} fail={fail} logout={logout} nav={nav} />
      case 'help': return <HowToPlay season={season} nav={nav} />
      case 'share': return <Share token={token} squad={squad} nav={nav} />
      default: return null
    }
  }

  return (
    <FantasyCtx.Provider value={ctx}>
      <div className="bfc-root" data-theme={theme} style={rootSx}>
        <div style={{ maxWidth: desktop ? 1180 : 540, margin: '0 auto', padding: desktop ? '22px 24px 64px' : '18px 16px 56px' }}>
          {phase !== 'app' && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', maxWidth: 440, margin: '0 auto 4px' }}>
              <ThemeToggle theme={theme} onToggle={onToggleTheme} />
            </div>
          )}

          {phase === 'loading' && <p style={{ textAlign: 'center', color: 'var(--faint)', marginTop: 64, font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>}

          {phase === 'dead' && (
            <div style={{ textAlign: 'center', marginTop: 48 }}>
              <div style={{ font: `800 22px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{club?.name || 'Fantasy Cricket'}</div>
              <div style={{ maxWidth: 440, margin: '12px auto 0' }}><Banner>This fantasy link isn't active yet. Check with your club.</Banner></div>
            </div>
          )}

          {phase === 'auth' && <div style={{ maxWidth: 440, margin: '0 auto' }}><Auth token={token} season={season} onAuthed={onAuthed} /></div>}

          {phase === 'app' && (
            <>
              <AppHeader
                season={season} manager={manager} unread={unread} desktop={desktop}
                theme={theme} onToggleTheme={onToggleTheme}
                onBell={() => nav('notifications')} onSearch={() => nav('stats')} onProfile={() => nav('settings')}
                inlineNav={desktop ? <NavPills items={navItems} value={view} onChange={(v) => nav(v)} inline /> : null}
              />
              {!desktop && <NavPills items={navItems} value={view} onChange={(v) => nav(v)} />}
              <div style={{ display: 'flex', gap: 6, padding: desktop ? '12px 0 12px' : '2px 0 10px', overflowX: 'auto', scrollbarWidth: 'none' }}>
                {QUICK.map(([k, l]) => {
                  const on = view === k
                  return (
                    <button key={k} onClick={() => nav(k)} style={{
                      padding: '5px 11px', borderRadius: 8, border: '1px solid var(--hairline)', cursor: 'pointer', whiteSpace: 'nowrap',
                      font: `${on ? 700 : 600} 11px 'Hanken Grotesk'`,
                      background: on ? 'color-mix(in srgb, var(--pb-accent, #8C82F0) 14%, transparent)' : 'transparent',
                      color: on ? 'var(--accent-strong)' : 'var(--dim)',
                    }}>{l}</button>
                  )
                })}
              </div>

              <Banner tone="ok">{msg}</Banner>
              <Banner>{error}</Banner>

              {desktop && !WIDE.has(view)
                ? <div style={{ maxWidth: 640, margin: '0 auto' }}>{screen()}</div>
                : screen()}
            </>
          )}
        </div>
      </div>
    </FantasyCtx.Provider>
  )
}
