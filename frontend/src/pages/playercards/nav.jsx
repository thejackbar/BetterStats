// The way round the Player Cards page: a sidebar on a wide screen, a thin rail of icons on a tablet, and a bottom bar of
// five on a phone (Home, Cards, Packs, Swaps, More). The count badges (packs waiting, swaps asking) show on all three, so a
// player sees what is waiting without opening anything.
import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { onColor } from '../../components/PlayerTradingCard'
import Icon from './icons'
import { usePC } from './context'

export const NAV = [
  { key: 'home', label: 'Home', icon: 'home', to: '', end: true },
  { group: 'Collection' },
  { key: 'book', label: 'My cards', icon: 'book', to: '/book' },
  { key: 'club', label: 'Club cards', icon: 'club', to: '/club' },
  { group: 'Packs' },
  { key: 'packs', label: 'Open packs', icon: 'packs', to: '/packs', badge: 'packs' },
  { group: 'Trading' },
  { key: 'swaps', label: 'Swaps', icon: 'swaps', to: '/swaps', badge: 'swaps' },
  { group: 'Help' },
  { key: 'how', label: 'How it works', icon: 'help', to: '/how' },
]

const MONO = "'JetBrains Mono', monospace"

function Badge({ n, accent, small }) {
  if (!n) return null
  return (
    <span data-nav-badge style={{ minWidth: small ? 15 : 20, height: small ? 15 : 20, padding: '0 5px', borderRadius: 10, background: accent, color: onColor(accent), font: `700 ${small ? 9 : 11}px ${MONO}`, display: 'inline-grid', placeItems: 'center' }}>{n}</span>
  )
}

function useCounts() {
  const { packsCount, swapsWaiting } = usePC()
  return { packs: packsCount, swaps: swapsWaiting }
}

function initials(name) {
  return (name || 'Club').split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 3).join('').toUpperCase()
}

export function Sidebar() {
  const { basePath, base, club, me, onSwitch, accent } = usePC()
  const counts = useCounts()
  return (
    <aside data-sidebar className="hidden lg:flex flex-col shrink-0 w-[248px] sticky top-0 h-screen border-r pb-hairline py-5 px-3 overflow-y-auto" aria-label="Player Cards">
      <div className="flex items-center gap-3 px-2 mb-4">
        {club?.logo_url
          ? <img src={club.logo_url} alt="" className="w-10 h-10 rounded-lg object-contain bg-pb-surface2 p-0.5" />
          : <span className="w-10 h-10 rounded-lg flex items-center justify-center font-display font-bold text-sm" style={{ background: accent, color: onColor(accent) }}>{initials(club?.name)}</span>}
        <div className="min-w-0">
          <div className="font-display font-bold leading-tight truncate">{club?.name || 'Your club'}</div>
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Player Cards</div>
        </div>
      </div>
      <Link to={base} data-back-to-page className="flex items-center gap-2 px-2 py-2 mb-2 rounded-lg text-sm text-pb-dim hover:text-pb-text hover:bg-pb-surface2">
        <Icon name="back" size={16} /> Back to my page
      </Link>
      <nav className="flex flex-col gap-0.5">
        {NAV.map((n, i) => n.group ? (
          <div key={`g${i}`} className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faintest px-2 pt-4 pb-1">{n.group}</div>
        ) : (
          <NavLink key={n.key} to={`${basePath}${n.to}`} end={n.end} data-nav={n.key}
            className={({ isActive }) => `flex items-center gap-3 px-2.5 py-2 rounded-lg text-[14px] font-medium transition-colors ${isActive ? '' : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2'}`}
            style={({ isActive }) => (isActive ? { background: accent, color: onColor(accent) } : undefined)}>
            <Icon name={n.icon} />
            <span className="flex-1">{n.label}</span>
            <Badge n={counts[n.badge]} accent={accent} />
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto pt-6 px-2 text-[12px] text-pb-faint">
        <div className="truncate">{me?.player?.display_name}</div>
        <button type="button" onClick={onSwitch} data-not-you className="underline hover:text-pb-text">Not you?</button>
      </div>
    </aside>
  )
}

export function Rail() {
  const { basePath, base, accent } = usePC()
  const counts = useCounts()
  return (
    <aside data-rail className="hidden md:flex lg:hidden flex-col items-center shrink-0 w-[68px] sticky top-0 h-screen border-r pb-hairline py-4 gap-1" aria-label="Player Cards">
      <Link to={base} aria-label="Back to my page" title="Back to my page" className="w-10 h-10 grid place-items-center rounded-lg text-pb-dim hover:text-pb-text hover:bg-pb-surface2 mb-2"><Icon name="back" /></Link>
      {NAV.filter((n) => !n.group).map((n) => (
        <NavLink key={n.key} to={`${basePath}${n.to}`} end={n.end} data-nav={n.key} aria-label={n.label} title={n.label}
          className={({ isActive }) => `relative w-11 h-11 grid place-items-center rounded-lg ${isActive ? '' : 'text-pb-dim hover:text-pb-text hover:bg-pb-surface2'}`}
          style={({ isActive }) => (isActive ? { background: accent, color: onColor(accent) } : undefined)}>
          <Icon name={n.icon} />
          {counts[n.badge] > 0 && <span style={{ position: 'absolute', top: 1, right: 1 }}><Badge n={counts[n.badge]} accent={accent} small /></span>}
        </NavLink>
      ))}
    </aside>
  )
}

export function BottomBar() {
  const { basePath, base, accent, me, onSwitch } = usePC()
  const counts = useCounts()
  const { pathname } = useLocation()
  const [more, setMore] = useState(false)
  const rel = pathname.slice(basePath.length) || '/'
  const items = [
    { key: 'home', label: 'Home', icon: 'home', to: '', on: rel === '/' },
    { key: 'book', label: 'Cards', icon: 'book', to: '/book', on: rel.startsWith('/book') || rel.startsWith('/club') },
    { key: 'packs', label: 'Packs', icon: 'packs', to: '/packs', on: rel.startsWith('/packs'), badge: counts.packs },
    { key: 'swaps', label: 'Swaps', icon: 'swaps', to: '/swaps', on: rel.startsWith('/swaps'), badge: counts.swaps },
  ]
  const moreOn = !items.some((i) => i.on)
  const cell = 'relative flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-mono uppercase tracking-wide'
  return (
    <>
      <nav data-bottom-bar className="md:hidden fixed bottom-0 inset-x-0 z-30 grid grid-cols-5 border-t pb-hairline bg-pb-bg" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }} aria-label="Player Cards">
        {items.map((i) => (
          <Link key={i.key} to={`${basePath}${i.to}`} data-nav={i.key} className={cell} style={{ color: i.on ? accent : undefined }} aria-current={i.on ? 'page' : undefined}>
            <span className="relative"><Icon name={i.icon} size={22} />{i.badge > 0 && <span style={{ position: 'absolute', top: -5, right: -10 }}><Badge n={i.badge} accent={accent} small /></span>}</span>
            <span className={i.on ? '' : 'text-pb-faint'}>{i.label}</span>
          </Link>
        ))}
        <button type="button" onClick={() => setMore(true)} data-nav="more" className={cell} style={{ color: moreOn ? accent : undefined }}>
          <Icon name="more" size={22} /><span className={moreOn ? '' : 'text-pb-faint'}>More</span>
        </button>
      </nav>
      {more && (
        <div role="dialog" aria-modal="true" aria-label="More" data-more-sheet className="md:hidden fixed inset-0 z-40" onClick={() => setMore(false)} style={{ background: 'rgba(3,6,10,.7)' }}>
          <div onClick={(e) => e.stopPropagation()} className="absolute bottom-0 inset-x-0 rounded-t-2xl bg-pb-surface border-t pb-hairline p-4" style={{ paddingBottom: 'calc(16px + env(safe-area-inset-bottom, 0px))' }}>
            <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint mb-2">More</div>
            {[{ to: `${basePath}/club`, label: 'Club cards', icon: 'club' }, { to: `${basePath}/how`, label: 'How it works', icon: 'help' }, { to: base, label: 'Back to my page', icon: 'back' }].map((l) => (
              <Link key={l.label} to={l.to} onClick={() => setMore(false)} data-more-link className="flex items-center gap-3 px-2 py-3 rounded-lg hover:bg-pb-surface2"><Icon name={l.icon} />{l.label}</Link>
            ))}
            <div className="flex items-center justify-between px-2 pt-3 text-sm text-pb-faint border-t pb-hairline mt-2">
              <span>{me?.player?.display_name}</span>
              <button type="button" onClick={onSwitch} className="underline">Not you?</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// My cards and Club cards are two views of one thing; on a phone they share one slot in the bottom bar, so this switch sits at the top of both.
export function CardsSwitch() {
  const { basePath, accent } = usePC()
  const { pathname } = useLocation()
  const on = pathname.startsWith(`${basePath}/club`) ? 'club' : 'book'
  return (
    <div role="tablist" aria-label="Which cards" data-cards-switch className="md:hidden inline-flex rounded-xl border pb-hairline p-0.5 mb-4">
      {[['book', 'My cards'], ['club', 'Club cards']].map(([k, label]) => (
        <Link key={k} to={`${basePath}/${k}`} role="tab" aria-selected={on === k} data-switch={k}
          className="px-4 py-1.5 rounded-lg text-sm font-semibold" style={on === k ? { background: accent, color: onColor(accent) } : undefined}>{label}</Link>
      ))}
    </div>
  )
}
