import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { getVisitorId } from '../../lib/visitor'
import { buildThemeCss } from '../../lib/theme'
import { Card, Kpi, Label, PageHeader } from '../../lib/presskit'
import { fmt2, fmtCount } from '../../lib/cricketFormat'
import brandWhite from '../../assets/bettercricket-white.svg'
import brandBlack from '../../assets/bettercricket-black.svg'
import { SUPPORT_EMAIL } from '../../data/marketing'

// A prospect club's own season, laid out as the club's dashboard would be, and
// reached by a link we emailed them, an ad, or by picking their club on /trial.
// It is built from Cricket Australia's public figures for ONE season, so it
// cannot be the whole product, and it does not pretend to be: every menu item,
// tile and row is a way to the same invitation to claim the club. Nothing here
// is a link into a screen we have no data for.
//
// It borrows the paid club's look on purpose: the same header, cards, KPI tiles
// and menu bar, the club's own crest, and the club's colours. The accent colour
// and light or dark are worked out from the club's logo on the server
// (club_teaser_theme) and applied through the same theme builder a paid club's
// white-labelling uses, so a colour or a contrast rule fixed there is fixed here.
// A club with no readable logo keeps BetterCricket's green on dark.
//
// What the page shows is decided server side (club_teaser.presentation): the
// season record only where it flatters, and one season only, named as such.
// Mobile first: the email and the ads this is reached from are opened on a phone.

const SHEET_ID = 'teaser-claim-sheet'
const PREVIEW_ROWS = 3   // rows shown in full; the rest are dimmed, claiming unlocks them

// What each menu item stands for, in plain terms. These are the real sections of
// a club's site (see components/Navbar.jsx); nothing here promises a figure.
const MENU = [
  { key: 'players', label: 'Players', title: (n) => `Every ${n} player, in one place`,
    line: 'A page for each player, with their career batting, bowling and fielding.' },
  { key: 'stats', label: 'Stats', menu: true, title: () => 'Leaderboards, records and Stat Lab',
    line: 'Leaderboards, club records, honour boards and a lab for digging into any figure.' },
  { key: 'games', label: 'Games', menu: true, title: () => 'Every result, fixture and ladder',
    line: 'Results, fixtures, lineups and ladders for every team in the club.' },
  { key: 'compare', label: 'Compare', title: () => 'Put two players side by side',
    line: 'Compare any two players across batting, bowling and fielding.' },
  { key: 'yearbook', label: 'Yearbook', title: () => 'A yearbook for every season',
    line: 'A season yearbook built from the club\'s own results.' },
  { key: 'website', label: 'Website', title: () => 'A club website that keeps itself up to date',
    line: 'News, pages and honours, fed by the same results.' },
]
const OTHER = {
  search: { title: () => 'Find any player the club has had', line: 'Search every player and open their career.' },
  dashboard: { title: () => 'A dashboard for every player', line: 'Each player gets their own page: availability, stats, fees and Fantasy.' },
  admin: { title: () => 'Run the club from one place', line: 'Set up the club, add your committee and manage the site.' },
  leaderboard: { title: () => 'The full leaderboard', line: 'Every batter, bowler and fielder, with filters for grade and match type.' },
  season: { title: () => 'Every season, every grade', line: 'Pick any season and grade, and see the figures for just that.' },
}

function setRobots(content) {
  let el = document.querySelector('meta[name="robots"]#teaser-robots')
  if (!el) {
    document.querySelectorAll('meta[name="robots"]').forEach((m) => m.remove())
    el = document.createElement('meta')
    el.name = 'robots'
    el.id = 'teaser-robots'
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

const Chevron = () => (
  <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path d="M2 4l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

// The menu bar a subscribed club has. Every item opens the invitation.
function TeaserNav({ name, short, logo, mode, onMode, onOpen, registered }) {
  const [open, setOpen] = useState(false)
  const item = 'relative px-2.5 py-1.5 text-[11px] font-mono font-semibold tracking-wide3 whitespace-nowrap transition flex items-center gap-1 text-pb-faint hover:text-pb-dim'
  return (
    <header className="sticky top-0 z-30 bg-pb-surface pb-hairline-b" data-testid="teaser-nav">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6">
        <div className="flex items-center gap-0 h-14">
          <button type="button" onClick={() => onOpen(null)} className="flex items-center gap-3 mr-6 shrink-0 text-left">
            {logo && (
              <img src={logo} alt="" className="w-8 h-8 rounded object-contain" data-testid="teaser-nav-logo"
                   onError={(e) => { e.currentTarget.style.display = 'none' }} />
            )}
            <span className="hidden md:block leading-tight">
              <span className="block text-pb-text text-[13px] font-semibold tracking-tight">{name}</span>
              <span className="block text-pb-faint text-[10px] font-mono tracking-wide2">{short.toUpperCase()}</span>
            </span>
            <span className="md:hidden text-pb-text text-[13px] font-bold tracking-wide2 truncate max-w-[9rem]">{short}</span>
          </button>

          <nav className="hidden xl:flex items-center flex-1 min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Club menu">
            <button type="button" aria-current="page" className="relative px-2.5 py-1.5 text-[11px] font-mono font-semibold tracking-wide3 text-pb-text">
              Home
              <span className="absolute left-1 right-1 -bottom-[1px] h-[2px]" style={{ background: 'var(--pb-gradient)' }} />
            </button>
            {MENU.map((m) => (
              <button key={m.key} type="button" data-nav={m.key} onClick={() => onOpen(m.key)} className={item}>
                {m.label}{m.menu && <Chevron />}
              </button>
            ))}
          </nav>
          <div className="flex-1 xl:hidden" />

          <button type="button" data-nav="search" onClick={() => onOpen('search')}
                  className="hidden sm:flex shrink-0 items-center gap-2 w-36 2xl:w-56 rounded border pb-hairline px-2.5 py-1.5 text-left text-[12px] text-pb-faint hover:text-pb-dim">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" strokeLinecap="round" /></svg>
            Search players…
          </button>
          <button type="button" onClick={onMode} data-testid="teaser-mode-toggle" aria-label="Toggle colour theme"
                  title={mode === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
                  className="shrink-0 ml-2 w-8 h-8 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition">
            {mode === 'dark' ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
              </svg>
            ) : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
          <button type="button" data-nav="dashboard" onClick={() => onOpen('dashboard')}
                  style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                  className="shrink-0 ml-2 hidden sm:inline-flex items-center font-mono font-semibold text-[10px] tracking-wide2 rounded px-3 py-1.5 hover:opacity-90">
            PLAYER DASHBOARD
          </button>
          <button type="button" data-testid="teaser-header-cta" onClick={() => onOpen(null)}
                  className="shrink-0 ml-2 hidden sm:inline-flex items-center font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-2.5 py-1.5">
            {registered ? 'OPEN YOUR SITE' : 'CLAIM YOUR CLUB'}
          </button>
          <span className="hidden xl:flex items-center gap-1.5 shrink-0 ml-3" title="Powered by BetterCricket">
            <span className="hidden min-[1500px]:block text-pb-faint text-[9px] font-mono tracking-wide2 uppercase">Powered by</span>
            <img src={mode === 'light' ? brandBlack : brandWhite} alt="BetterCricket" className="h-6 w-auto opacity-80" />
          </span>
          <button type="button" className="xl:hidden ml-1 w-10 h-10 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2"
                  onClick={() => setOpen((o) => !o)} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} data-testid="teaser-menu-button">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={open ? 'M6 6l12 12M6 18L18 6' : 'M4 7h16M4 12h16M4 17h16'} />
            </svg>
          </button>
        </div>
      </div>
      {open && (
        <div className="xl:hidden border-t pb-hairline bg-pb-surface" data-testid="teaser-mobile-menu">
          <div className="px-4 py-2 flex flex-col">
            {MENU.map((m) => (
              <button key={m.key} type="button" data-nav={m.key} onClick={() => { setOpen(false); onOpen(m.key) }}
                      className="text-left py-2.5 text-[13px] font-mono font-semibold tracking-wide2 text-pb-dim hover:text-pb-text">{m.label}</button>
            ))}
            <button type="button" data-nav="dashboard" onClick={() => { setOpen(false); onOpen('dashboard') }}
                    className="text-left py-2.5 text-[13px] font-mono font-semibold tracking-wide2 text-pb-dim hover:text-pb-text">Player dashboard</button>
            <button type="button" data-nav="search" onClick={() => { setOpen(false); onOpen('search') }}
                    className="text-left py-2.5 text-[13px] font-mono font-semibold tracking-wide2 text-pb-dim hover:text-pb-text">Search players</button>
          </div>
        </div>
      )}
    </header>
  )
}

// A card on the dashboard that is, here, one big button: tapping it opens the
// invitation. A div with a button role rather than a button, because a card
// holds lists and headings.
function Tap({ section, onTap, className = '', children }) {
  return (
    <div role="button" tabIndex={0} data-tile={section} onClick={() => onTap(section)}
         onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onTap(section) } }}
         className={`cursor-pointer rounded-[inherit] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--pb-accent)] ${className}`}>
      {children}
    </div>
  )
}

function Rows({ rows, empty }) {
  if (!rows.length) return <p className="text-pb-faint text-sm py-2">{empty}</p>
  return (
    <ol className="flex flex-col">
      {rows.slice(0, 5).map((r, i) => (
        <li key={r.name + i} className={`flex items-center gap-3 py-2.5 ${i ? 'pb-hairline-t' : ''} ${i >= PREVIEW_ROWS ? 'opacity-45' : ''}`}>
          <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
          <div className="flex-1 min-w-0">
            <div className="text-pb-text text-[14px] font-semibold truncate">{r.name}</div>
            <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2 truncate">{r.sub}</div>
          </div>
          <span className="font-mono text-[14px] font-bold pb-num min-w-[3rem] text-right" style={{ color: 'var(--pb-accent)' }}>{r.main}</span>
        </li>
      ))}
    </ol>
  )
}

export default function TeaserPreview() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)      // null loading, false = not found
  const [sheet, setSheet] = useState(false)
  const [section, setSection] = useState(null)
  const [mode, setMode] = useState('dark')
  const viewed = useRef(false)
  const primaryRef = useRef(null)
  const lastFocus = useRef(null)

  useEffect(() => {
    let alive = true
    api.publicTeaser(token)
      .then((d) => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(false) })
    return () => { alive = false }
  }, [token])

  const name = data?.club?.name || 'Your club'
  const seasonName = data?.season?.name || 'this season'
  const accent = data?.theme?.accent || null
  const accent2 = data?.theme?.accent2 || null

  // The club's colours, through the same builder a paid club's theme uses.
  useEffect(() => {
    if (data?.theme?.mode) setMode(data.theme.mode)
  }, [data])
  useEffect(() => {
    if (!accent) return undefined
    let style = document.getElementById('club-theme')
    if (!style) {
      style = document.createElement('style')
      style.id = 'club-theme'
      document.head.appendChild(style)
    }
    // A one-colour logo has no secondary: the gradient is then that one colour
    // rather than the site's blue.
    style.textContent = buildThemeCss({ accent, accent2: accent2 || accent }, null)
    return () => { document.getElementById('club-theme')?.remove() }
  }, [accent, accent2])

  useEffect(() => {
    if (!data) return
    document.title = `${name}: your ${seasonName} | BetterCricket`
    setRobots('noindex, nofollow')
    if (viewed.current) return
    viewed.current = true
    api.publicTeaserEvent(token, 'view', null, getVisitorId()).catch(() => {})
    if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
      window.fbq('track', 'ViewContent', { content_name: 'Club teaser page', content_category: 'club_teaser' })
    }
  }, [data, name, seasonName, token])

  const openSheet = (key) => {
    lastFocus.current = document.activeElement
    api.publicTeaserEvent(token, key ? 'tile' : 'claim_open', key || 'header', getVisitorId()).catch(() => {})
    if (key) api.publicTeaserEvent(token, 'claim_open', key, getVisitorId()).catch(() => {})
    setSection(key)
    setSheet(true)
  }
  const closeSheet = () => {
    setSheet(false)
    lastFocus.current?.focus?.()
  }

  useEffect(() => {
    if (!sheet) return undefined
    const onKey = (e) => { if (e.key === 'Escape') closeSheet() }
    document.addEventListener('keydown', onKey)
    primaryRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [sheet])

  const registered = data?.registered
  const goClaim = () => {
    api.publicTeaserEvent(token, 'claim_go', null, getVisitorId()).catch(() => {})
    navigate(registered ? `/${registered.slug}` : `/trial?teaser=${encodeURIComponent(token)}`)
  }

  const batting = useMemo(() => (data?.batting || []).map((b) => ({
    name: b.name, main: fmtCount(b.runs),
    sub: [b.average != null ? `AVG ${fmt2(b.average)}` : '',
          b.high_score != null ? `HS ${b.high_score}${b.hs_not_out ? '*' : ''}` : ''].filter(Boolean).join(' · '),
  })), [data])
  const bowling = useMemo(() => (data?.bowling || []).map((b) => ({
    name: b.name, main: fmtCount(b.wickets),
    sub: [b.average != null ? `AVG ${fmt2(b.average)}` : '',
          b.economy != null ? `ECON ${fmt2(b.economy)}` : '',
          b.best ? `BEST ${String(b.best).replace('-', '/')}` : ''].filter(Boolean).join(' · '),
  })), [data])
  const fielding = useMemo(() => (data?.fielding || []).map((f) => ({
    name: f.name, main: fmtCount(f.catches),
    sub: ['CATCHES', f.stumpings ? `${f.stumpings} ST` : '', f.run_outs ? `${f.run_outs} RO` : ''].filter(Boolean).join(' · '),
  })), [data])

  if (data === null) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text" data-theme="dark">
        <div className="max-w-[1400px] mx-auto px-4 pt-16 space-y-3" aria-busy="true" data-testid="teaser-loading">
          {[120, 220, 160].map((h) => <div key={h} className="rounded-2xl bg-pb-surface animate-pulse" style={{ height: h }} />)}
        </div>
      </div>
    )
  }
  if (data === false) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-6" data-theme="dark">
        <div className="max-w-sm text-center" data-testid="teaser-missing">
          <img src={brandWhite} alt="BetterCricket" className="h-8 mx-auto mb-6" />
          <h1 className="text-xl font-semibold mb-2">This link is not valid any more</h1>
          <p className="text-sm text-pb-dim mb-5">
            It may have been copied wrongly. You can still find your club and start a free trial.
          </p>
          <Link to="/trial" className="inline-block rounded-lg bg-accent text-[#08110b] px-4 py-2.5 text-sm font-semibold">Find your club</Link>
        </div>
      </div>
    )
  }

  const { record, ladders_shown: ladders, club } = data
  const place = [club.suburb, club.state].filter(Boolean).join(', ')
  const short = name.replace(/ (Cricket )?Club$/i, '')
  const ctaLabel = registered ? `Open ${name}'s site` : `Claim ${name} free`
  const records = data.records || []
  const hasThird = records.length > 0 || fielding.length > 0
  const meta = [
    <span key="s">{seasonName.toUpperCase()}</span>,
    data.matches ? <span key="m">PLAYED <span className="text-pb-text">{fmtCount(data.matches)}</span></span> : null,
    data.teams ? <span key="t"><span className="text-pb-text">{fmtCount(data.teams)}</span> {data.teams === 1 ? 'GRADE' : 'GRADES'}</span> : null,
    place ? <span key="p">{place.toUpperCase()}</span> : null,
  ].filter(Boolean)
  const kpis = [
    record && record.win_rate != null ? { key: 'wr', label: 'WIN RATE', value: record.win_rate, suffix: '%', accent: true } : null,
    { key: 'pl', label: 'MATCHES PLAYED', value: data.matches || 0 },
    record ? { key: 'w', label: 'WON', value: record.won || 0 } : null,
    record ? { key: 'l', label: 'LOST', value: record.lost || 0 } : null,
    !record && data.teams ? { key: 'g', label: data.teams === 1 ? 'GRADE' : 'GRADES', value: data.teams } : null,
  ].filter(Boolean).slice(0, 4)
  const info = section ? (MENU.find((m) => m.key === section) || OTHER[section]) : null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text pb-28" data-theme={mode} data-mode={mode} data-testid="teaser-page">
      <TeaserNav name={name} short={short} logo={club.logo_url} mode={mode}
                 onMode={() => setMode((m) => (m === 'dark' ? 'light' : 'dark'))} onOpen={openSheet} registered={registered} />

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          gradient
          eyebrow={`${short} · CLUB DASHBOARD`}
          title={<span data-testid="teaser-club">{name}</span>}
          logo={club.logo_url}
          logoAlt={`${name} crest`}
          meta={meta}
          actions={
            <button type="button" data-nav="leaderboard" onClick={() => openSheet('leaderboard')}
                    className="font-mono text-[11px] tracking-wide2 px-3.5 py-2 rounded hover:opacity-90 transition"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
              Leaderboard →
            </button>
          }
        />

        {registered && (
          <div className="mb-5 rounded-xl border px-4 py-3 text-sm" data-testid="teaser-registered"
               style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)', background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' }}>
            {name} is already on BetterCricket. <Link className="font-semibold underline" to={`/${registered.slug}`}>Open the club's site</Link>.
          </div>
        )}

        <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
          <Label>SEASON</Label>
          <button type="button" data-nav="season" onClick={() => openSheet('season')}
                  className="flex items-center gap-2 rounded border pb-hairline bg-pb-surface px-3 py-2 text-[13px] text-pb-text hover:border-[var(--pb-accent)]">
            {seasonName}<Chevron />
          </button>
          <span className="text-pb-faint font-mono text-[11px] tracking-wide2">THIS SEASON ONLY</span>
        </div>

        <div className={`grid gap-3 mb-6 ${kpis.length >= 4 ? 'grid-cols-2 lg:grid-cols-4' : kpis.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}
             data-testid="teaser-record">
          {kpis.map((k) => (
            <Tap key={k.key} section={`kpi-${k.key}`} onTap={() => openSheet(null)} className="block">
              <Kpi label={k.label} value={k.value} suffix={k.suffix || ''} accent={k.accent} motion={false} />
            </Tap>
          ))}
        </div>

        <div className={`grid grid-cols-1 gap-3 mb-6 ${hasThird ? 'xl:grid-cols-3' : 'xl:grid-cols-2'}`}>
          <Tap section="batting" onTap={openSheet} className="h-full">
            <Card title={`TOP BATTERS · ${seasonName.toUpperCase()}`} className="h-full"
                  action={<span className="text-2xs font-mono tracking-wide2 text-pb-dim">ALL →</span>}>
              <Rows rows={batting} empty="No batting figures yet." />
            </Card>
          </Tap>
          <Tap section="bowling" onTap={openSheet} className="h-full">
            <Card title={`TOP BOWLERS · ${seasonName.toUpperCase()}`} className="h-full"
                  action={<span className="text-2xs font-mono tracking-wide2 text-pb-dim">ALL →</span>}>
              <Rows rows={bowling} empty="No bowling figures yet." />
            </Card>
          </Tap>
          {hasThird && (
            <Tap section="records" onTap={openSheet} className="h-full">
              <Card title="SEASON BEST" className="h-full"
                    action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">THIS SEASON</span>}>
                {records.length > 0 && (
                  <ul className="flex flex-col" data-testid="teaser-season-best">
                    {records.map((r, i) => (
                      <li key={r.label} className={`flex items-center gap-3 py-2.5 ${i ? 'pb-hairline-t' : ''}`}>
                        <div className="flex-1 min-w-0">
                          <div className="text-pb-text text-[14px] font-semibold truncate">{r.player}</div>
                          <div className="text-pb-faint font-mono text-[10.5px] tracking-wide2 truncate">{r.label.toUpperCase()}</div>
                        </div>
                        <span className="font-mono text-[14px] font-bold pb-num text-right" style={{ color: 'var(--pb-accent)' }}>{r.value}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {fielding.length > 0 && (
                  <div className={records.length ? 'mt-4 pt-3 pb-hairline-t' : ''} data-tile="fielding">
                    <Label>FIELDING</Label>
                    <div className="mt-1"><Rows rows={fielding.slice(0, 3)} empty="" /></div>
                  </div>
                )}
              </Card>
            </Tap>
          )}
        </div>

        {ladders?.length > 0 && (
          <Tap section="ladder" onTap={openSheet} className="block mb-6">
            <Card title="ON THE LADDER" action={<span className="text-2xs font-mono tracking-wide2 text-pb-faint">{seasonName.toUpperCase()}</span>}>
              <ul data-testid="teaser-ladders">
                {ladders.map((l, i) => (
                  <li key={l.grade} className={`flex items-center justify-between gap-3 py-2.5 ${i ? 'pb-hairline-t' : ''}`}>
                    <span className="min-w-0 truncate text-[14px] font-semibold text-pb-text">{l.grade}</span>
                    <span className="shrink-0 font-mono text-[13px] tabular-nums">
                      <strong className="font-bold" style={{ color: 'var(--pb-accent)' }}>{l.place}</strong>
                      <span className="text-pb-dim"> of {l.teams}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </Tap>
        )}

        <p className="mt-8 text-xs text-pb-dim leading-relaxed">
          These figures are one season of Cricket Australia's public match data, so the club's own site will show more.{' '}
          Something not right?{' '}
          <a className="underline" href={`mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(`${name} teaser page`)}`}>Tell us</a>.
        </p>
      </main>

      <div className="fixed bottom-0 inset-x-0 z-30 border-t pb-hairline backdrop-blur"
           style={{ background: 'color-mix(in srgb, var(--pb-bg) 94%, transparent)' }}>
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-3 flex items-center gap-3">
          <p className="hidden sm:block flex-1 text-sm text-pb-dim">
            {registered ? 'Already set up.' : 'Free, about 3 minutes, no card.'}
          </p>
          <button type="button" data-testid="teaser-bar-cta" onClick={() => openSheet(null)}
                  style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                  className="flex-1 sm:flex-none rounded-xl px-5 py-3 text-sm font-semibold hover:opacity-90">
            {ctaLabel}
          </button>
        </div>
      </div>

      {sheet && (
        <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center" role="presentation">
          <div className="absolute inset-0 bg-black/60" onClick={closeSheet} data-testid="teaser-sheet-backdrop" />
          <div id={SHEET_ID} role="dialog" aria-modal="true" aria-labelledby="teaser-sheet-title" data-testid="teaser-sheet"
               className="relative w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl border pb-hairline bg-pb-surface p-6 shadow-2xl">
            <h2 id="teaser-sheet-title" className="text-xl font-bold leading-snug">
              {registered ? `${name} is already on BetterCricket`
                : info ? info.title(name) : `This is ${name}'s season. Make it yours.`}
            </h2>
            {registered ? (
              <p className="mt-2 text-sm text-pb-dim">Open the club's own site to see every player, record and result.</p>
            ) : (
              <ul className="mt-3 space-y-2 text-sm text-pb-dim">
                {info ? <li data-testid="teaser-sheet-line">{info.line}</li>
                  : <li>Leaderboards, records and a club website that update after every match.</li>}
                <li>Free trial, no card, about 3 minutes to set up.</li>
              </ul>
            )}
            <div className="mt-5 flex flex-col gap-2">
              <button ref={primaryRef} type="button" data-testid="teaser-sheet-go" onClick={goClaim}
                      style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                      className="rounded-xl px-5 py-3 text-sm font-semibold hover:opacity-90">
                {ctaLabel}
              </button>
              <button type="button" data-testid="teaser-sheet-close" onClick={closeSheet}
                      className="rounded-xl px-5 py-2.5 text-sm text-pb-dim hover:text-pb-text">
                Not now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
