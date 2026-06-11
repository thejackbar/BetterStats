import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import { dashboardTiles, statusLabel, statusIsLive } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import AdminLayout from '../../components/admin/AdminLayout'
import { formatSeason } from '../../lib/cricketFormat'

// Render "BetterX" with the suffix in the club accent colour, matching the
// existing BetterSelect treatment.
function ModuleName({ name }) {
  if (name.startsWith('Better')) {
    return (
      <span className="font-display font-bold text-lg">
        Better<span style={{ color: 'var(--pb-accent)' }}>{name.slice('Better'.length)}</span>
      </span>
    )
  }
  return <span className="font-display font-bold text-lg">{name}</span>
}

function ModuleTile({ mod, entitled }) {
  const brand = moduleBrand(mod.key)
  // Scope the module's accent colour to this tile only — every var(--pb-accent)
  // inside (the name suffix, arrow, tint, border) becomes the module colour.
  const brandVars = { '--pb-accent': brand.accent, '--pb-accent-rgb': brand.accentRgb }

  // Greenfield module (BetterIQ) — never opens yet, regardless of entitlement.
  if (!mod.built) {
    return (
      <div className="pb-card p-5 opacity-70" style={brandVars}>
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={brand.logo} alt="" className="w-8 h-8 rounded-lg shrink-0" />
            <ModuleName name={mod.name} />
          </div>
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5">SOON</span>
        </div>
        <div className="text-pb-faint text-sm mt-1">{mod.blurb}</div>
      </div>
    )
  }

  // Entitled → opens.
  if (entitled) {
    return (
      <Link
        to={mod.to}
        className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
        style={{ ...brandVars, background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src={brand.logo} alt="" className="w-8 h-8 rounded-lg shrink-0" />
            <ModuleName name={mod.name} />
          </div>
          <span className="text-2xl group-hover:translate-x-1 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
        </div>
        <div className="text-pb-faint text-sm mt-1">{mod.blurb}</div>
      </Link>
    )
  }

  // Locked → not entitled. It's an add-on the club can turn on.
  return (
    <div className="pb-card p-5 opacity-75" style={{ ...brandVars, borderStyle: 'dashed' }}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 text-pb-faint">
          <img src={brand.logo} alt="" className="w-8 h-8 rounded-lg shrink-0 grayscale opacity-70" />
          <ModuleName name={mod.name} />
        </div>
        <span className="font-mono text-[10px] tracking-wide2 text-pb-faint border pb-hairline rounded px-2 py-0.5 uppercase">
          Add-on
        </span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{mod.blurb}</div>
      <div className="text-pb-faintest text-xs mt-2">
        Available as an add-on. <Link to="/pricing" className="underline hover:text-pb-faint">See pricing</Link>.
      </div>
    </div>
  )
}

export default function AdminDashboard() {
  const { user, hasModule } = useAuth()
  const [settings, setSettings] = useState(null)
  const [seasons, setSeasons] = useState([])

  useEffect(() => {
    api.adminGetSettings().then(setSettings).catch(() => {})
    api.adminListSeasons().then(setSeasons).catch(() => {})
  }, [])

  const isSuper = user?.role === 'super_admin'
  const activeModules = user?.entitlements?.modules || []
  const planStatus = user?.entitlements?.status || 'active'
  const renewalDate = user?.entitlements?.renewal_date

  // Core admin tasks (BetterStats / Core — always available). BetterSocials is
  // now represented by its own module tile, so it's dropped from here.
  const quickLinks = [
    { to: '/admin/players', label: 'Manage Players', desc: 'Edit display names' },
    { to: '/admin/yearbook', label: 'Yearbooks', desc: 'Publish season yearbooks' },
    { to: '/admin/awards', label: 'Awards', desc: 'Add season awards & achievements' },
    { to: '/admin/merge', label: 'Merge Players', desc: 'Fix duplicate player entries' },
    { to: '/admin/milestones', label: 'Milestones', desc: 'Upcoming & achieved milestones report' },
    { to: '/admin/sync', label: 'Data Sync', desc: 'Trigger sync & view sync log' },
    { to: '/admin/games', label: 'View Matches', desc: 'Browse match results' },
    { to: '/admin/settings', label: 'Club Settings', desc: 'Name, colours, contact' },
  ]

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">
          Welcome{user?.display_name ? `, ${user.display_name}` : ''}
        </h1>
        {settings && (
          <p className="text-pb-faint text-sm mb-1">
            Managing <span className="text-pb-text">{settings.name}</span>
            {settings.slug && (
              <>
                {' · '}
                <Link
                  to={`/${settings.slug}`}
                  className="hover:underline transition-colors"
                  style={{ color: 'var(--pb-accent)' }}
                  target="_blank"
                >
                  View public page ↗
                </Link>
              </>
            )}
          </p>
        )}
        <p className="text-pb-faintest text-xs mb-6">
          {isSuper ? (
            'Super admin — all modules available'
          ) : (
            <>
              Plan: <span className="text-pb-faint">{activeModules.length ? `Core + ${activeModules.length} module${activeModules.length > 1 ? 's' : ''}` : 'Core (BetterStats)'}</span>
              {planStatus !== 'active' && (
                <span className={statusIsLive(planStatus) ? 'text-pb-faint' : 'text-pb-red'}> · {statusLabel(planStatus)}</span>
              )}
              {renewalDate && <> · renews {new Date(renewalDate).toLocaleDateString('en-AU')}</>}
            </>
          )}
        </p>

        {/* Better modules — entitled tiles open; locked tiles upsell. */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Modules</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
          {dashboardTiles().map(tile => (
            <ModuleTile
              key={tile.key}
              mod={tile}
              entitled={tile.alwaysOpen || (tile.isGroup ? tile.members.some(m => hasModule(m.key)) : hasModule(tile.key))}
            />
          ))}
        </div>

        {/* Core admin quick links */}
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Quick links</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
          {quickLinks.map(link => (
            <Link
              key={link.to}
              to={link.to}
              className="pb-card p-4 hover:bg-pb-surface2 transition-colors group"
            >
              <div className="font-medium text-pb-text group-hover:text-pb-accent transition-colors text-sm"
                onMouseEnter={e => e.currentTarget.style.color = 'var(--pb-accent)'}
                onMouseLeave={e => e.currentTarget.style.color = ''}
              >
                {link.label}
              </div>
              <div className="text-sm text-pb-faint mt-0.5">{link.desc}</div>
            </Link>
          ))}
        </div>

        {seasons.length > 0 && (
          <div>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Seasons</p>
            <div className="pb-card overflow-hidden">
              {seasons.slice(0, 5).map((s, i) => (
                <div key={s.id} className={`flex items-center justify-between px-5 py-3 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                  <span className="text-pb-text text-sm">{formatSeason(s)}</span>
                  <span className="font-mono text-[10px] text-pb-faintest">{s.year || '—'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
