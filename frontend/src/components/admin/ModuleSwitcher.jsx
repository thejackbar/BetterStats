import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { dashboardTiles } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'

// Quick module switcher — one pill per Better module the club can reach, each in
// that module's own brand colour with its logo, the current module highlighted.
// Lives in every module layout's header so you can hop straight between module
// surfaces (BetterSelect → BetterIQ → BetterAdmin …) instead of going back
// through the admin dashboard. The leading "Stats" pill is the Core dashboard.
//
// Pills carry their OWN brand colour via inline styles, never --pb-accent (every
// module layout overrides that to its own colour), so each pill stays the right
// colour whatever surface it sits in. Neutral tones use the shared theme vars so
// it tracks light/dark and the club / IQ palettes.

// The leading pill is the admin dashboard (/admin) itself — BetterStats is now
// its own tile in the list, so this one is just "home". It keeps the Core green
// mark as the house brand.
const CORE = { key: 'stats', name: 'Dashboard', to: '/admin', title: 'Admin dashboard' }

const suffixOf = name => (name.startsWith('Better') ? name.slice('Better'.length) : name)

// A grouped tile (BetterAdmin = fees + comms, BetterSocials = post designer +
// website) is "current" for any of its members' paths as well as its own hub.
const tilePaths = tile => (tile.isGroup ? [tile.to, ...tile.members.map(m => m.to)] : [tile.to])

const pathIsActive = (pathname, paths) =>
  paths.some(p => pathname === p || pathname.startsWith(p + '/'))

function Pill({ to, brand, label, active, title, onNavigate, forceLabel, compact }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: compact ? '4px 8px' : '5px 10px', borderRadius: 999, fontSize: compact ? 11.5 : 12.5, lineHeight: 1,
    whiteSpace: 'nowrap', textDecoration: 'none', background: 'transparent',
    border: '1px solid transparent',
    transition: 'background .12s, color .12s, border-color .12s',
  }
  const style = active
    ? { ...base, color: brand.accent, fontWeight: 600,
        background: `color-mix(in srgb, ${brand.accent} 14%, transparent)`,
        borderColor: `color-mix(in srgb, ${brand.accent} 38%, transparent)` }
    : { ...base, color: 'var(--pb-faint)', fontWeight: 500 }
  return (
    <Link to={to} title={title} onClick={onNavigate} aria-current={active ? 'page' : undefined}
      className="shrink-0" style={style}
      onMouseEnter={active ? undefined : e => {
        e.currentTarget.style.color = 'var(--pb-text)'
        e.currentTarget.style.background = `color-mix(in srgb, ${brand.accent} 12%, transparent)`
        e.currentTarget.style.borderColor = `color-mix(in srgb, ${brand.accent} 26%, transparent)`
      }}
      onMouseLeave={active ? undefined : e => {
        e.currentTarget.style.color = 'var(--pb-faint)'
        e.currentTarget.style.background = 'transparent'
        e.currentTarget.style.borderColor = 'transparent'
      }}>
      <img src={brand.logo} alt="" className="shrink-0" style={{ width: compact ? 14 : 16, height: compact ? 14 : 16, borderRadius: compact ? 4 : 5 }} />
      <span className={(active || forceLabel) ? '' : 'hidden lg:inline'}>{label}</span>
    </Link>
  )
}

// `compact` — the smaller pill used in a module sidebar's footer, where the
// switcher lives now rather than in each screen header.
export default function ModuleSwitcher({ className = '', wrap = false, compact = false, onNavigate }) {
  const { hasModule } = useAuth()
  const { pathname } = useLocation()

  // Same entitlement rule the admin sidebar uses: built modules the club holds,
  // plus always-open umbrellas (BetterSocials carries the Core website).
  const tiles = dashboardTiles().filter(mod =>
    mod.built && (mod.alwaysOpen || (mod.isGroup ? mod.members.some(m => hasModule(m.key)) : hasModule(mod.key)))
  )

  return (
    <div className={`items-center gap-1 ${wrap ? 'flex-wrap' : 'overflow-x-auto pb-no-scrollbar'} ${className}`}>
      <Pill to={CORE.to} brand={moduleBrand(CORE.key)} label={suffixOf(CORE.name)}
        active={pathname === '/admin'} title={CORE.title} onNavigate={onNavigate} forceLabel={wrap} compact={compact} />
      {tiles.length > 0 && !compact && (
        <span aria-hidden className="shrink-0" style={{ width: 1, height: 18, margin: '0 3px', background: 'var(--pb-hairline2)' }} />
      )}
      {tiles.map(tile => (
        <Pill key={tile.key} to={tile.to} brand={moduleBrand(tile.key)}
          label={suffixOf(tile.name)} active={pathIsActive(pathname, tilePaths(tile))}
          title={tile.name} onNavigate={onNavigate} forceLabel={wrap} compact={compact} />
      ))}
    </div>
  )
}
