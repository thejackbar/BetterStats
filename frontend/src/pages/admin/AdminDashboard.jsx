import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'
import { dashboardTiles, statusLabel, statusIsLive, MODULE_TOGGLES } from '../../lib/modules'
import { moduleBrand } from '../../lib/moduleBrand'
import AdminLayout from '../../components/admin/AdminLayout'
import SyncRunCard from '../../components/admin/SyncRunCard'
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

function ModuleTile({ mod, entitled, pendingKind, canSubscribe, requesting, onRequest }) {
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
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {pendingKind ? (
          <span className="font-mono text-[10px] text-amber-300/90 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-1">
            {pendingKind === 'subscribe' ? 'Subscription requested' : 'Trial requested'} — pending review
          </span>
        ) : (
          <>
            <button
              type="button"
              disabled={requesting}
              onClick={() => onRequest('trial')}
              className="font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border transition-colors disabled:opacity-50"
              style={{ color: 'var(--pb-accent)', borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, transparent)' }}
            >
              {requesting ? '…' : 'Request trial'}
            </button>
            {canSubscribe && (
              <button
                type="button"
                disabled={requesting}
                onClick={() => onRequest('subscribe')}
                className="font-mono text-[10px] tracking-wide2 px-2.5 py-1.5 rounded border pb-hairline text-pb-faint hover:text-pb-text transition-colors disabled:opacity-50"
              >
                Request to subscribe
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function AdminDashboard() {
  const { user, hasModule } = useAuth()
  const [settings, setSettings] = useState(null)
  const [seasons, setSeasons] = useState([])
  const [myRequests, setMyRequests] = useState([])
  const [requesting, setRequesting] = useState('')
  const [latestSyncRun, setLatestSyncRun] = useState(null)

  useEffect(() => {
    api.adminGetSettings().then(setSettings).catch(() => {})
    api.adminListSeasons().then(setSeasons).catch(() => {})
    api.listMyModuleRequests().then(d => setMyRequests(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  // Live sync progress — driven entirely by re-fetching sync_runs, so it's
  // correct on every fresh page load / re-login with no client-side state to
  // keep in sync itself (the running/finished status the admin sees is
  // whatever the backend says right now, not something remembered locally).
  // Polls only while the latest run is still going.
  useEffect(() => {
    if (!user?.club_id) return undefined
    let cancelled = false
    let intervalId = null
    const poll = async () => {
      try {
        const logs = await api.getSyncLogs(user.club_id)
        if (cancelled) return
        const latest = logs?.[0] || null
        setLatestSyncRun(latest)
        if (latest?.status !== 'running' && intervalId) {
          clearInterval(intervalId)
          intervalId = null
        }
      } catch {
        // best-effort — the section just won't show if this fails
      }
    }
    poll()
    intervalId = setInterval(poll, 4000)
    return () => { cancelled = true; if (intervalId) clearInterval(intervalId) }
  }, [user?.club_id])

  // Raise a trial / subscription request for a billable module (BetterAdmin covers
  // fees + comms + merch as one). Queued for a super admin to action.
  const requestModule = async (moduleKey, kind) => {
    setRequesting(moduleKey)
    try {
      await api.requestModule(moduleKey, kind)
      const d = await api.listMyModuleRequests()
      setMyRequests(Array.isArray(d) ? d : [])
    } catch {
      // best-effort; the locked tile just stays requestable
    } finally {
      setRequesting('')
    }
  }

  const isSuper = user?.role === 'super_admin'
  const planStatus = user?.entitlements?.status || 'active'
  const renewalDate = user?.entitlements?.renewal_date
  // One row per billable module (BetterAdmin as a single module, not its 3
  // underlying entitlement keys — see auth/modules.py::_billing_module_summary),
  // each labelled Trial or Subscribed. Only present when the club's per-module
  // subscription rows are loaded (every club synced since the per-module model
  // shipped); older/legacy data falls back to a plain grouped count below.
  const billingModules = user?.entitlements?.billing_modules || []
  // Fallback grouped count for a club with no subscription rows loaded (bare
  // module_overrides only) — groups fees/comms/merch into one "module" so the
  // count isn't inflated by BetterAdmin's 3 backend entitlement keys.
  const overrides = user?.entitlements?.overrides || []
  const fallbackGroupCount = new Set(
    overrides.map(ov => MODULE_TOGGLES.find(t => t.modules.includes(ov))?.key).filter(Boolean)
  ).size

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
          ) : billingModules.length ? (
            <>
              Plan:{' '}
              <span className="text-pb-faint">
                {billingModules.map((m, i) => (
                  <span key={m.module}>
                    {i > 0 && ', '}
                    {m.module === 'core' ? 'BetterStats (Core)' : m.name} - {m.status === 'trial' ? 'Trial' : 'Subscribed'}
                  </span>
                ))}
              </span>
              {renewalDate && <> · renews {new Date(renewalDate).toLocaleDateString('en-AU')}</>}
            </>
          ) : (
            <>
              Plan: <span className="text-pb-faint">{fallbackGroupCount ? `Core + ${fallbackGroupCount} module${fallbackGroupCount > 1 ? 's' : ''}` : 'Core (BetterStats)'}</span>
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
          {dashboardTiles().map(tile => {
            // tile.key is the billable module key (BetterAdmin = 'admin'), so a
            // request for the group is one request, not one per member.
            const pending = myRequests.find(r => r.status === 'outstanding' && r.module_key === tile.key)
            return (
              <ModuleTile
                key={tile.key}
                mod={tile}
                entitled={tile.alwaysOpen || (tile.isGroup ? tile.members.some(m => hasModule(m.key)) : hasModule(tile.key))}
                pendingKind={pending?.kind}
                canSubscribe={!!user?.is_primary_admin}
                requesting={requesting === tile.key}
                onRequest={(kind) => requestModule(tile.key, kind)}
              />
            )
          })}
        </div>

        {/* Data sync — the club's own most recent sync run, live while running.
            Re-fetched from sync_runs on every load, so it's correct regardless
            of navigation or logging out and back in. */}
        {latestSyncRun && (
          <>
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">Data sync</p>
            <div className="mb-8">
              <SyncRunCard entry={latestSyncRun} isLatest />
              <Link to="/admin/sync" className="inline-block mt-2 font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors">
                View full sync history →
              </Link>
            </div>
          </>
        )}

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
