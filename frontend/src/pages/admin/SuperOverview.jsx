import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { statusLabel, statusIsLive, SUBSCRIPTION_STATUSES, MODULE } from '../../lib/modules'
import { priceFor } from '../../data/pricing'
import AdminLayout from '../../components/admin/AdminLayout'

// Better HQ — the internal staff control room. Fleet KPIs, the platform tools
// laid out as module-style tiles, a "needs attention" worklist, subscription /
// module-adoption rollups, and a per-club health table that doubles as the club
// switcher (Manage re-scopes the whole admin app into that club).

const STALE_SYNC_DAYS = 30
const DORMANT_LOGIN_DAYS = 30

// HQ tool tiles — same visual language as the dashboard module cards.
const HQ_TOOLS = [
  { to: '/admin/super/clubs', name: 'All Clubs', blurb: 'Onboard, edit plans & subscriptions, sync or remove clubs.' },
  { to: '/admin/super/users', name: 'Users & Access', blurb: 'Staff and club-admin accounts, roles and password resets.' },
  { to: '/admin/usage', name: 'Usage Analytics', blurb: 'Traffic, features, visitors and per-club engagement.' },
  { to: '/admin/super/migration', name: 'KlubPro Migration', blurb: 'Import player profiles & sponsors from a legacy KlubPro club.' },
]

const ADOPTION = [
  { key: MODULE.SELECT, name: 'BetterSelect' },
  { key: MODULE.SOCIALS, name: 'BetterSocials' },
  { key: MODULE.FEES, name: 'BetterFees' },
  { key: MODULE.IQ, name: 'BetterIQ' },
  { key: MODULE.COMMS, name: 'BetterComms' },
]

function daysSince(iso) {
  if (!iso) return Infinity
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
}

function relativeDays(iso) {
  const d = daysSince(iso)
  if (d === Infinity) return 'never'
  if (d <= 0) return 'today'
  if (d === 1) return 'yesterday'
  if (d < 30) return `${d}d ago`
  if (d < 365) return `${Math.floor(d / 30)}mo ago`
  return `${Math.floor(d / 365)}y ago`
}

function fmtMoney(n) {
  return '$' + Math.round(n).toLocaleString('en-AU')
}

// Map backend module keys → the public modular pricing keys, so ARR uses the
// same prices as the public calculator. BetterAdmin = fees + comms.
const PRICING_KEY = { select: 'select', socials: 'socials', iq: 'iq', fees: 'admin', comms: 'admin' }

function clubAnnual(c) {
  const keys = [...new Set((c.modules || []).map(m => PRICING_KEY[m]).filter(Boolean))]
  return priceFor(keys).total
}

function Kpi({ label, value, sub, accent }) {
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</div>
      <div className="font-display font-bold text-2xl mt-1 tabular-nums" style={accent ? { color: 'var(--pb-accent)' } : { color: 'var(--pb-text)' }}>{value}</div>
      {sub && <div className="font-mono text-[10px] text-pb-faintest mt-0.5">{sub}</div>}
    </div>
  )
}

function ToolTile({ to, name, blurb }) {
  return (
    <Link
      to={to}
      className="block pb-card p-5 border-pb-accent/30 hover:border-pb-accent/50 transition-colors group"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}
    >
      <div className="flex items-center justify-between gap-4">
        <span className="font-display font-bold text-lg text-pb-text">{name}</span>
        <span className="text-2xl group-hover:translate-x-1 transition-transform" style={{ color: 'var(--pb-accent)' }}>→</span>
      </div>
      <div className="text-pb-faint text-sm mt-1">{blurb}</div>
    </Link>
  )
}

function Bar({ label, value, max, hint }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div>
      <div className="flex items-center justify-between font-mono text-[10px] mb-1">
        <span className="text-pb-faint uppercase tracking-wide2">{label}</span>
        <span className="text-pb-text tabular-nums">{value}{hint ? ` ${hint}` : ''}</span>
      </div>
      <div className="h-1.5 rounded bg-pb-surface2 overflow-hidden">
        <div className="h-full rounded" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
      </div>
    </div>
  )
}

const SORTS = {
  name: (a, b) => (a.name || '').localeCompare(b.name || ''),
  players: (a, b) => (b.players || 0) - (a.players || 0),
  games: (a, b) => (b.games || 0) - (a.games || 0),
  last_sync: (a, b) => daysSince(a.last_sync) - daysSince(b.last_sync),
  last_login: (a, b) => daysSince(a.last_login) - daysSince(b.last_login),
}

export default function SuperOverview() {
  const { user, switchClub } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('name')
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    api.superOverview().then(setData).catch(e => setError(e?.message || 'Failed to load'))
  }, [])

  const t = data?.totals
  const allClubs = data?.clubs || []

  // Estimated ARR — annual list price (Core + modules, bundle discount applied)
  // of every club on a live subscription.
  const arr = useMemo(
    () => allClubs.filter(c => statusIsLive(c.subscription_status))
      .reduce((sum, c) => sum + clubAnnual(c), 0),
    [allClubs]
  )

  // Worklist: clubs that need a human to look at them, with the reasons why.
  const attention = useMemo(() => {
    const rows = []
    for (const c of allClubs) {
      const reasons = []
      let severity = 0
      if (!statusIsLive(c.subscription_status)) { reasons.push(statusLabel(c.subscription_status)); severity += 3 }
      if (!c.is_active) { reasons.push('Hidden'); severity += 2 }
      if (daysSince(c.last_sync) > STALE_SYNC_DAYS) { reasons.push(c.last_sync ? `No sync ${relativeDays(c.last_sync)}` : 'Never synced'); severity += 1 }
      if (daysSince(c.last_login) > DORMANT_LOGIN_DAYS) { reasons.push(c.last_login ? `No login ${relativeDays(c.last_login)}` : 'No admin logins'); severity += 1 }
      if (reasons.length) rows.push({ ...c, reasons, severity })
    }
    return rows.sort((a, b) => b.severity - a.severity).slice(0, 12)
  }, [allClubs])

  const clubs = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = q
      ? allClubs.filter(c => (c.name || '').toLowerCase().includes(q) || (c.slug || '').toLowerCase().includes(q))
      : allClubs.slice()
    return filtered.sort(SORTS[sort] || SORTS.name)
  }, [allClubs, query, sort])

  const manage = async (clubId) => {
    setBusyId(clubId)
    try {
      await switchClub(clubId)
    } catch (e) {
      setError(e?.message || 'Could not switch club')
      setBusyId(null)
    }
  }

  const adoptionMax = t ? Math.max(1, ...ADOPTION.map(m => t.module_adoption?.[m.key] || 0)) : 1

  return (
    <AdminLayout>
      <div className="max-w-6xl">
        <div className="flex items-center justify-between mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">
            Better<span style={{ color: 'var(--pb-accent)' }}>HQ</span>
          </h1>
          <Link to="/admin/usage" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5">
            USAGE ANALYTICS →
          </Link>
        </div>
        <p className="text-pb-faint text-sm mb-5">Platform control room. Pick any club's <strong>Manage</strong> to jump straight into administering it.</p>

        {error && <div className="font-mono text-[11px] text-pb-red mb-4">{error}</div>}
        {!data && !error && <div className="font-mono text-[11px] text-pb-faint">Loading…</div>}

        {t && (
          <>
            {/* KPI strip */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
              <Kpi label="Clubs" value={t.clubs} sub={`${t.active_clubs} active`} />
              <Kpi label="Est. ARR" value={fmtMoney(arr)} sub="live subs · list price" accent />
              <Kpi label="Users" value={t.users} sub={`${t.super_admins} staff`} />
              <Kpi label="Players" value={t.players.toLocaleString()} />
              <Kpi label="Games" value={t.games.toLocaleString()} />
              <Kpi label="On modules" value={allClubs.filter(c => (c.modules || []).length).length} sub={`of ${t.clubs} clubs`} />
            </div>

            {/* HQ tools — module-style tiles */}
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-2">Platform Tools</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-7">
              {HQ_TOOLS.map(tool => <ToolTile key={tool.to} {...tool} />)}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-7">
              {/* Needs attention */}
              <div className="lg:col-span-2 pb-card p-4">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-display font-bold text-sm text-pb-text">Needs attention</h2>
                  <span className="font-mono text-[10px] text-pb-faintest">{attention.length} flagged</span>
                </div>
                {attention.length === 0 && (
                  <div className="font-mono text-[11px] text-pb-faint py-4 text-center">All clubs healthy ✓</div>
                )}
                <div className="space-y-1.5">
                  {attention.map(c => (
                    <div key={c.id} className="flex items-center justify-between gap-3 py-1.5 px-2 rounded hover:bg-pb-surface2">
                      <div className="min-w-0">
                        <span className="text-pb-text text-sm">{c.name}</span>
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {c.reasons.map((r, i) => (
                            <span key={i} className="font-mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded border border-pb-red/30 text-pb-red/90">{r}</span>
                          ))}
                        </div>
                      </div>
                      <button
                        onClick={() => manage(c.id)}
                        disabled={busyId === c.id}
                        className="font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded text-pb-bg shrink-0 disabled:opacity-50"
                        style={{ background: 'var(--pb-accent)' }}
                      >
                        {busyId === c.id ? '…' : 'MANAGE'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Subscriptions + module adoption */}
              <div className="space-y-5">
                <div className="pb-card p-4">
                  <h2 className="font-display font-bold text-sm text-pb-text mb-3">Subscription status</h2>
                  <div className="space-y-2.5">
                    {SUBSCRIPTION_STATUSES.map(s => (
                      <Bar key={s.key} label={s.label} value={t.by_status?.[s.key] || 0} max={t.clubs} hint="clubs" />
                    ))}
                  </div>
                </div>

                <div className="pb-card p-4">
                  <h2 className="font-display font-bold text-sm text-pb-text mb-3">Module adoption</h2>
                  <div className="space-y-2.5">
                    {ADOPTION.map(m => (
                      <Bar key={m.key} label={m.name} value={t.module_adoption?.[m.key] || 0} max={adoptionMax} hint="clubs" />
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Fleet table */}
            <div className="flex items-center gap-3 mb-2">
              <h2 className="font-display font-bold text-sm text-pb-text mr-auto">All clubs</h2>
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search clubs…"
                className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent w-56"
              />
              <span className="font-mono text-[10px] text-pb-faintest">{clubs.length}</span>
            </div>

            <div className="pb-card overflow-hidden">
              <div className="grid grid-cols-[1.6fr_auto_auto_auto_auto_auto] gap-3 font-mono text-[10px] tracking-wide2 text-pb-faint px-4 py-2.5 bg-pb-surface2/40">
                <button className="text-left hover:text-pb-text" onClick={() => setSort('name')}>CLUB</button>
                <button className="text-right hover:text-pb-text" onClick={() => setSort('players')}>PLAYERS</button>
                <button className="text-right hover:text-pb-text" onClick={() => setSort('games')}>GAMES</button>
                <button className="text-right hover:text-pb-text" onClick={() => setSort('last_sync')}>SYNCED</button>
                <button className="text-right hover:text-pb-text" onClick={() => setSort('last_login')}>LOGIN</button>
                <span className="text-right">ACTION</span>
              </div>
              {clubs.map((c, i) => {
                const isCurrent = c.id === user?.club_id
                return (
                  <div
                    key={c.id}
                    className={`grid grid-cols-[1.6fr_auto_auto_auto_auto_auto] gap-3 items-center px-4 py-2.5 hover:bg-pb-surface2 ${i > 0 ? 'pb-hairline-t' : ''}`}
                  >
                    <div className="min-w-0">
                      <span className="text-pb-text text-sm">{c.name}</span>
                      <span className="font-mono text-[10px] text-pb-faintest ml-2">/{c.slug}</span>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border pb-hairline text-pb-faint" title={c.modules?.length ? `Modules: ${c.modules.join(', ')}` : 'Core only'}>{c.modules?.length ? `Core +${c.modules.length}` : 'Core'}</span>
                        <span className={`font-mono text-[9px] ${statusIsLive(c.subscription_status) ? 'text-pb-faintest' : 'text-pb-red'}`}>
                          {statusLabel(c.subscription_status)}
                        </span>
                        {!c.is_active && <span className="font-mono text-[9px] text-pb-faint">· hidden</span>}
                      </div>
                    </div>
                    <span className="text-right text-sm text-pb-text tabular-nums">{(c.players || 0).toLocaleString()}</span>
                    <span className="text-right text-sm text-pb-text tabular-nums">{(c.games || 0).toLocaleString()}</span>
                    <span className="text-right font-mono text-[10px] text-pb-faint">{relativeDays(c.last_sync)}</span>
                    <span className="text-right font-mono text-[10px] text-pb-faint">{relativeDays(c.last_login)}</span>
                    <div className="text-right">
                      {isCurrent ? (
                        <span className="font-mono text-[10px]" style={{ color: 'var(--pb-accent)' }}>● current</span>
                      ) : (
                        <button
                          onClick={() => manage(c.id)}
                          disabled={busyId === c.id}
                          className="font-mono text-[10px] tracking-wide2 px-2.5 py-1 rounded text-pb-bg disabled:opacity-50"
                          style={{ background: 'var(--pb-accent)' }}
                        >
                          {busyId === c.id ? '…' : 'MANAGE'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
              {clubs.length === 0 && (
                <div className="px-4 py-6 text-center font-mono text-[11px] text-pb-faint">No clubs match</div>
              )}
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
