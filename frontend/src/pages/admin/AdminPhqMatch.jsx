import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const CONFIDENCE_LABEL = {
  auto: { label: 'Auto-linked', color: 'text-accent bg-accent/10 border-accent/30' },
  high: { label: 'High confidence', color: 'text-amber-400 bg-amber-500/10 border-amber-500/30' },
  low: { label: 'Low confidence', color: 'text-slate-400 bg-navy-800 border-navy-700' },
}

function SuggestionRow({ s, players, onAction, loading }) {
  const [selectedPlayerId, setSelectedPlayerId] = useState(s.player_id || '')
  const conf = CONFIDENCE_LABEL[s.confidence] || CONFIDENCE_LABEL.low

  return (
    <div className={`bg-navy-900 border rounded-lg p-4 ${
      s.status === 'pending' ? 'border-navy-600' : 'border-navy-800 opacity-60'
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* PHQ side */}
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${conf.color}`}>
              {conf.label}
            </span>
            <span className="text-slate-500 text-xs">{s.game_count} game{s.game_count !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-3">
            <div>
              <p className="text-white font-medium">{s.phq_name}</p>
              <p className="font-mono text-xs text-slate-600 mt-0.5">{s.phq_player_id}</p>
            </div>
            <svg className="w-4 h-4 text-slate-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            <div>
              {s.status === 'pending' ? (
                <select
                  value={selectedPlayerId}
                  onChange={e => setSelectedPlayerId(e.target.value)}
                  className="bg-navy-800 border border-navy-600 rounded px-2 py-1 text-white text-sm focus:outline-none focus:border-accent"
                >
                  <option value="">— select player —</option>
                  {players.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}{p.playhq_id ? ' ✓' : ''}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-slate-300 text-sm">{s.player_name || '—'}</p>
              )}
              {s.player_current_phq_id && (
                <p className="text-xs text-amber-500/70 mt-0.5">already has PHQ: {s.player_current_phq_id}</p>
              )}
            </div>
          </div>
        </div>

        {s.status === 'pending' ? (
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => onAction(s.id, 'approve', selectedPlayerId)}
              disabled={loading || !selectedPlayerId}
              className="btn-primary text-xs disabled:opacity-40"
            >
              {loading ? 'Saving…' : 'Approve Link'}
            </button>
            <button
              onClick={() => onAction(s.id, 'dismiss', null)}
              disabled={loading}
              className="btn-ghost text-xs text-slate-400 disabled:opacity-40"
            >
              Dismiss
            </button>
          </div>
        ) : (
          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
            s.status === 'approved'
              ? 'bg-accent/10 border-accent/30 text-accent'
              : 'bg-navy-800 border-navy-700 text-slate-500'
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
  const [loading, setLoading] = useState(null) // suggestion id being actioned
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
    // intentionally NOT resetting scanning=false on success — button stays disabled until page reload
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
        <h1 className="text-2xl font-display font-bold text-white mb-2">PHQ ID Match</h1>
        <p className="text-slate-400 text-sm mb-6">
          Scan scorecards to auto-link PlayHQ player UUIDs to your players. Exact name matches are linked
          automatically; ambiguous matches appear below for review.
        </p>

        {/* Scan card */}
        <div className="bg-navy-900 border border-navy-700 rounded-lg p-5 mb-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-white font-semibold mb-1">Run PHQ ID Scan</h2>
              <p className="text-slate-500 text-xs">
                Scans all game appearances for this org. Auto-links exact matches; creates suggestions for ambiguous ones.
                Takes 5-15 minutes depending on history volume.
              </p>
            </div>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="btn-primary disabled:opacity-50 flex items-center gap-2 shrink-0"
            >
              {scanning ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Starting…
                </>
              ) : 'Scan Now'}
            </button>
          </div>
          {msg && <p className="text-amber-400 text-xs mt-3">{msg}</p>}
        </div>

        {/* Stats */}
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-3 mb-4">
            <div className="bg-navy-900 border border-navy-700 rounded px-3 py-2 text-center">
              <div className="text-accent font-mono font-bold text-lg">{pending.length}</div>
              <div className="text-slate-500 text-xs">Pending</div>
            </div>
            <div className="bg-navy-900 border border-navy-700 rounded px-3 py-2 text-center">
              <div className="text-white font-mono font-bold text-lg">{autoLinked}</div>
              <div className="text-slate-500 text-xs">Auto-linked</div>
            </div>
            <div className="bg-navy-900 border border-navy-700 rounded px-3 py-2 text-center">
              <div className="text-white font-mono font-bold text-lg">{manualApproved}</div>
              <div className="text-slate-500 text-xs">Approved</div>
            </div>
            <div className="bg-navy-900 border border-navy-700 rounded px-3 py-2 text-center">
              <div className="text-slate-400 font-mono font-bold text-lg">{dismissed}</div>
              <div className="text-slate-500 text-xs">Dismissed</div>
            </div>
          </div>
        )}

        {/* Filter tabs */}
        {suggestions.length > 0 && (
          <div className="flex gap-1 mb-4">
            {['pending', 'resolved', 'all'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`text-xs px-3 py-1.5 rounded capitalize transition-colors ${
                  filter === f ? 'bg-navy-700 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {f} {f === 'pending' ? `(${pending.length})` : f === 'resolved' ? `(${resolved.length})` : `(${suggestions.length})`}
              </button>
            ))}
            <button
              onClick={fetchAll}
              className="ml-auto text-slate-500 hover:text-white text-xs"
            >
              Refresh
            </button>
          </div>
        )}

        {/* Suggestions list */}
        {displayed.length === 0 ? (
          <div className="bg-navy-900 border border-navy-700 rounded-lg p-8 text-center">
            <p className="text-slate-500 text-sm">
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
