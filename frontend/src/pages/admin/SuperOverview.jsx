import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'
import { tierLabel, statusLabel, statusIsLive } from '../../lib/modules'
import AdminLayout from '../../components/admin/AdminLayout'

// Better-staff platform dashboard: fleet KPIs + a per-club health table. The
// table doubles as the launchpad for club switching — "Manage" re-scopes the
// whole admin app into that club (super-admin only, served by /auth/switch-club).

function Kpi({ label, value, sub }) {
  return (
    <div className="pb-card p-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</div>
      <div className="font-display font-bold text-2xl text-pb-text mt-1 tabular-nums">{value}</div>
      {sub && <div className="font-mono text-[10px] text-pb-faintest mt-0.5">{sub}</div>}
    </div>
  )
}

function relativeDays(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const days = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

const SORTS = {
  name: (a, b) => (a.name || '').localeCompare(b.name || ''),
  players: (a, b) => (b.players || 0) - (a.players || 0),
  games: (a, b) => (b.games || 0) - (a.games || 0),
  last_sync: (a, b) => new Date(b.last_sync || 0) - new Date(a.last_sync || 0),
  last_login: (a, b) => new Date(b.last_login || 0) - new Date(a.last_login || 0),
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
  const clubs = useMemo(() => {
    if (!data?.clubs) return []
    const q = query.trim().toLowerCase()
    const filtered = q
      ? data.clubs.filter(c => (c.name || '').toLowerCase().includes(q) || (c.slug || '').toLowerCase().includes(q))
      : data.clubs.slice()
    return filtered.sort(SORTS[sort] || SORTS.name)
  }, [data, query, sort])

  const manage = async (clubId) => {
    setBusyId(clubId)
    try {
      await switchClub(clubId) // hard-reloads into /admin under the new scope
    } catch (e) {
      setError(e?.message || 'Could not switch club')
      setBusyId(null)
    }
  }

  const tierBreakdown = t ? ['best', 'better', 'good'].map(k => `${(t.by_tier?.[k] || 0)} ${tierLabel(k)}`).join(' · ') : ''

  return (
    <AdminLayout>
      <div className="max-w-5xl">
        <div className="flex items-center justify-between mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">Platform Overview</h1>
          <Link to="/admin/usage" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text border pb-hairline rounded px-3 py-1.5">
            USAGE ANALYTICS →
          </Link>
        </div>
        <p className="text-pb-faint text-sm mb-5">Fleet health across every Better club. Pick a club's <strong>Manage</strong> to jump straight into administering it.</p>

        {error && <div className="font-mono text-[11px] text-pb-red mb-4">{error}</div>}
        {!data && !error && <div className="font-mono text-[11px] text-pb-faint">Loading…</div>}

        {t && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
              <Kpi label="Clubs" value={t.clubs} sub={`${t.active_clubs} active`} />
              <Kpi label="Users" value={t.users} sub={`${t.super_admins} super`} />
              <Kpi label="Players" value={t.players.toLocaleString()} />
              <Kpi label="Games" value={t.games.toLocaleString()} />
              <Kpi label="By tier" value={t.by_tier?.best || 0} sub={tierBreakdown} />
              <Kpi label="Live subs" value={Object.entries(t.by_status || {}).filter(([k]) => statusIsLive(k)).reduce((n, [, v]) => n + v, 0)} sub={`of ${t.clubs}`} />
            </div>

            <div className="flex items-center gap-3 mb-2">
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search clubs…"
                className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent w-56"
              />
              <span className="font-mono text-[10px] text-pb-faintest">{clubs.length} club{clubs.length === 1 ? '' : 's'}</span>
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
                        <span className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded border pb-hairline text-pb-faint">{tierLabel(c.tier)}</span>
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
