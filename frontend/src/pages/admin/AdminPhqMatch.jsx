import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const CONFIDENCE_LABEL = {
  auto: { label: 'Auto-linked', cls: 'text-pb-accent border-pb-accent/30', bg: 'bg-pb-accent/10' },
  high: { label: 'High confidence', cls: 'text-pb-amber border-pb-amber/30', bg: 'bg-pb-amber/10' },
  low: { label: 'Low confidence', cls: 'text-pb-faint', bg: 'bg-pb-surface2' },
}

function SuggestionRow({ s, players, onAction, loading }) {
  const [selectedPlayerId, setSelectedPlayerId] = useState(s.player_id || '')
  const conf = CONFIDENCE_LABEL[s.confidence] || CONFIDENCE_LABEL.low

  return (
    <div className={`pb-card p-4 ${s.status !== 'pending' ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className={`font-mono text-[10px] px-2 py-0.5 rounded border ${conf.cls} ${conf.bg}`}>
              {conf.label}
            </span>
            <span className="font-mono text-[10px] text-pb-faintest">{s.game_count} game{s.game_count !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-3">
            <div>
              <p className="text-pb-text font-medium text-sm">{s.phq_name}</p>
              <p className="font-mono text-[10px] text-pb-faintest mt-0.5">{s.phq_player_id}</p>
            </div>
            <svg className="w-4 h-4 text-pb-faintest shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            <div>
              {s.status === 'pending' ? (
                <select
                  value={selectedPlayerId}
                  onChange={e => setSelectedPlayerId(e.target.value)}
                  className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                >
                  <option value="">— select player —</option>
                  {players.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}{p.playhq_id ? ' ✓' : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-pb-dim text-sm">{s.player_name || '—'}</p>
              )}
              {s.player_current_phq_id && (
                <p className="font-mono text-[10px] text-pb-amber mt-0.5">already has PHQ: {s.player_current_phq_id}</p>
              )}
            </div>
          </div>
        </div>

        {s.status === 'pending' ? (
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => onAction(s.id, 'approve', selectedPlayerId)}
              disabled={loading || !selectedPlayerId}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {loading ? 'Saving…' : 'Approve Link'}
            </button>
            <button
              onClick={() => onAction(s.id, 'dismiss', null)}
              disabled={loading}
              className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors disabled:opacity-40"
            >
              Dismiss
            </button>
          </div>
        ) : (
          <span className={`font-mono text-[10px] px-2 py-0.5 rounded border capitalize ${
            s.status === 'approved'
              ? 'text-pb-accent border-pb-accent/30 bg-pb-accent/10'
              : 'text-pb-faint border-pb-hairline bg-pb-surface2'
          }`}>
            {s.status}
          </span>
        )}
      </div>
    </div>
  )
}

export default function AdminPhqMatch() {
  const [suggestions, setSuggestions] = useState([])
  const [players, setPlayers] = useState([])
  const [scanning, setScanning] = useState(false)
  const [loading, setLoading] = useState(null)
  const [msg, setMsg] = useState('')
  const [filter, setFilter] = useState('pending')

  const fetchAll = useCallback(async () => {
    try {
      const [res, pls] = await Promise.all([
        api.adminListPhqSuggestions(),
        api.adminListPlayers(),
      ])
      setSuggestions(res.suggestions || res || [])
      if (res.scanning) setScanning(true)
      setPlayers((pls || []).sort((a, b) => a.name.localeCompare(b.name)))
    } catch {
      // silent
    }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const handleScan = async () => {
    if (scanning) return
    setScanning(true)
    setMsg('')
    try {
      const res = await api.adminRunPhqSuggestions()
      if (res.status === 'already_running') {
        setMsg('A scan is already running — wait for it to finish, then refresh.')
      } else {
        setMsg('Scan started — takes 5-15 min. Refresh this page when done to see results.')
      }
    } catch (e) {
      setMsg(`Failed: ${e.message}`)
      setScanning(false)
    }
  }

  const handleAction = async (id, action, playerId) => {
    setLoading(id)
    try {
      await api.adminActionPhqSuggestion(id, action, playerId || null)
      await fetchAll()
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(null)
    }
  }

  const pending = suggestions.filter(s => s.status === 'pending')
  const resolved = suggestions.filter(s => s.status !== 'pending')
  const displayed = filter === 'pending' ? pending : filter === 'resolved' ? resolved : suggestions

  const autoLinked = resolved.filter(s => s.status === 'approved' && s.confidence === 'auto').length
  const manualApproved = resolved.filter(s => s.status === 'approved' && s.confidence !== 'auto').length
  const dismissed = resolved.filter(s => s.status === 'dismissed').length

  return (
    <AdminLayout>
      <div className="max-w-3xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-2">PHQ ID Match</h1>
        <p className="text-pb-faint text-sm mb-6 leading-relaxed">
          Scan scorecards to auto-link PlayHQ player UUIDs to your players. Exact name matches are linked
          automatically; ambiguous matches appear below for review.
        </p>

        <div className="pb-card p-5 mb-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-pb-text font-semibold text-sm mb-1">Run PHQ ID Scan</h2>
              <p className="font-mono text-[10px] text-pb-faint leading-relaxed max-w-sm">
                Scans all game appearances for this org. Auto-links exact matches; creates suggestions for ambiguous ones.
                Takes 5-15 minutes depending on history volume.
              </p>
            </div>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg flex items-center gap-2 shrink-0"
              style={{ background: 'var(--pb-accent)' }}
            >
              {scanning ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-pb-bg/30 border-t-pb-bg rounded-full animate-spin" />
                  Starting…
                </>
              ) : 'SCAN NOW'}
            </button>
          </div>
          {msg && <p className="font-mono text-[11px] text-pb-amber mt-3">{msg}</p>}
        </div>

        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-3 mb-5">
            {[
              { value: pending.length, label: 'Pending', accent: true },
              { value: autoLinked, label: 'Auto-linked' },
              { value: manualApproved, label: 'Approved' },
              { value: dismissed, label: 'Dismissed', dim: true },
            ].map(({ value, label, accent, dim }) => (
              <div key={label} className="pb-card px-4 py-3 text-center min-w-[80px]">
                <div className={`font-mono font-bold text-lg ${accent ? 'text-pb-accent' : dim ? 'text-pb-dim' : 'text-pb-text'}`}>{value}</div>
                <div className="font-mono text-[10px] text-pb-faint mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="flex gap-1 mb-4">
            {['pending', 'resolved', 'all'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`font-mono text-[10px] px-3 py-1.5 rounded capitalize transition-colors ${
                  filter === f
                    ? 'text-pb-text bg-pb-surface2'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
              >
                {f} {f === 'pending' ? `(${pending.length})` : f === 'resolved' ? `(${resolved.length})` : `(${suggestions.length})`}
              </button>
            ))}
            <button
              onClick={fetchAll}
              className="ml-auto font-mono text-[10px] text-pb-faint hover:text-pb-text transition-colors"
            >
              Refresh
            </button>
          </div>
        )}

        {displayed.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <p className="font-mono text-[11px] text-pb-faint">
              {suggestions.length === 0
                ? 'No suggestions yet — run a scan above.'
                : 'No suggestions in this filter.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {displayed.map(s => (
              <SuggestionRow
                key={s.id}
                s={s}
                players={players}
                onAction={handleAction}
                loading={loading === s.id}
              />
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
