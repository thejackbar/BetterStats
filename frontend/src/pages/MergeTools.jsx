import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'

function StatBadge({ label, value }) {
  return (
    <div className="text-center">
      <div className="text-lg font-bold text-white">{value ?? '—'}</div>
      <div className="text-xs text-slate-400 uppercase tracking-wide">{label}</div>
    </div>
  )
}

function PlayerCard({ player, isSelected, onSelect, label }) {
  const hasGrassroots = !!player.playhq_id
  return (
    <button
      onClick={onSelect}
      className={[
        'flex-1 rounded-lg border-2 p-4 text-left transition-all',
        isSelected ? 'border-accent bg-accent/10' : 'border-navy-600 bg-navy-800 hover:border-navy-400',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">{label}</div>
          <div className="text-white font-semibold text-lg leading-tight">{player.name}</div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {hasGrassroots && (
            <span className="text-xs bg-green-900/60 text-green-300 border border-green-700 rounded px-2 py-0.5">Grassroots</span>
          )}
          {player.claimed && (
            <span className="text-xs bg-accent/20 text-accent border border-accent/40 rounded px-2 py-0.5">Claimed</span>
          )}
          {!hasGrassroots && !player.claimed && (
            <span className="text-xs bg-navy-700 text-slate-400 border border-navy-600 rounded px-2 py-0.5">Scorecard only</span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <StatBadge label="Seasons" value={player.seasons_count} />
        <StatBadge label="Runs" value={player.total_runs} />
        <StatBadge label="Wkts" value={player.total_wickets} />
        <StatBadge label="Game Inn." value={player.game_level_innings} />
      </div>
      {isSelected && (
        <div className="mt-3 text-xs text-accent font-semibold text-center">✓ Keep this player</div>
      )}
    </button>
  )
}

// Autocomplete player search within an org's player list
function PlayerSearch({ players, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = query.trim().length >= 1
    ? players.filter(p => p.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 10)
    : []

  function select(player) {
    setQuery(player.name)
    setOpen(false)
    onChange(player)
  }

  function clear() {
    setQuery('')
    onChange(null)
  }

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <input
          type="text"
          value={value ? value.name : query}
          onChange={e => {
            if (value) onChange(null)
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => { if (!value) setOpen(true) }}
          placeholder={placeholder}
          className="w-full bg-navy-800 border border-navy-600 text-white text-sm rounded-lg px-3 py-2 pr-8 focus:outline-none focus:border-accent placeholder-slate-500"
        />
        {(value || query) && (
          <button onClick={clear} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-lg leading-none">×</button>
        )}
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-navy-800 border border-navy-600 rounded-lg shadow-xl max-h-52 overflow-y-auto">
          {filtered.map(p => (
            <button
              key={p.id}
              onMouseDown={() => select(p)}
              className="w-full text-left px-3 py-2 text-sm text-white hover:bg-navy-700 first:rounded-t-lg last:rounded-b-lg"
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ManualMerge({ orgId, onMerged }) {
  const [expanded, setExpanded] = useState(false)
  const [players, setPlayers] = useState([])
  const [selectedA, setSelectedA] = useState(null)
  const [selectedB, setSelectedB] = useState(null)
  const [infoA, setInfoA] = useState(null)
  const [infoB, setInfoB] = useState(null)
  const [keepId, setKeepId] = useState(null)
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (expanded && players.length === 0) {
      api.listPlayers(orgId).then(setPlayers).catch(() => {})
    }
  }, [expanded, orgId])

  async function handleSelectA(player) {
    setSelectedA(player)
    setInfoA(null)
    setKeepId(null)
    if (player) {
      const info = await api.getPlayerMergeInfo(player.id, orgId).catch(() => null)
      setInfoA(info)
    }
  }

  async function handleSelectB(player) {
    setSelectedB(player)
    setInfoB(null)
    setKeepId(null)
    if (player) {
      const info = await api.getPlayerMergeInfo(player.id, orgId).catch(() => null)
      setInfoB(info)
    }
  }

  useEffect(() => {
    if (infoA && infoB) {
      if (infoA.playhq_id && !infoB.playhq_id) setKeepId(infoA.id)
      else if (infoB.playhq_id && !infoA.playhq_id) setKeepId(infoB.id)
      else setKeepId(infoA.seasons_count >= infoB.seasons_count ? infoA.id : infoB.id)
    }
  }, [infoA, infoB])

  async function handleMerge() {
    if (!keepId || !infoA || !infoB) return
    const removeInfo = keepId === infoA.id ? infoB : infoA
    setMerging(true)
    setError(null)
    try {
      await api.mergePlayers(keepId, removeInfo.id, orgId)
      setSelectedA(null); setSelectedB(null); setInfoA(null); setInfoB(null); setKeepId(null)
      onMerged()
    } catch (e) {
      setError(e.message)
    } finally {
      setMerging(false)
    }
  }

  const canMerge = infoA && infoB && keepId && infoA.id !== infoB.id

  return (
    <div className="mb-8 border border-navy-600 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-4 bg-navy-800 hover:bg-navy-700 transition-colors text-left"
      >
        <div>
          <span className="text-white font-semibold">Manual Merge</span>
          <span className="text-slate-400 text-sm ml-3">Merge any two players by name — e.g. name changes after marriage</span>
        </div>
        <span className="text-slate-400 text-lg">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="bg-navy-900 p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="section-label text-xs mb-2 block">Player to remove</label>
              <PlayerSearch
                players={players.filter(p => p.id !== selectedB?.id)}
                value={selectedA}
                onChange={handleSelectA}
                placeholder="Search players…"
              />
            </div>
            <div>
              <label className="section-label text-xs mb-2 block">Player to keep</label>
              <PlayerSearch
                players={players.filter(p => p.id !== selectedA?.id)}
                value={selectedB}
                onChange={handleSelectB}
                placeholder="Search players…"
              />
            </div>
          </div>

          {infoA && infoB && (
            <>
              <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <PlayerCard player={infoA} isSelected={keepId === infoA.id} onSelect={() => setKeepId(infoA.id)} label="Player A" />
                <div className="flex items-center justify-center text-slate-600 font-bold shrink-0">vs</div>
                <PlayerCard player={infoB} isSelected={keepId === infoB.id} onSelect={() => setKeepId(infoB.id)} label="Player B" />
              </div>
              {infoA.id === infoB.id && (
                <p className="text-amber-400 text-sm mb-3">Select two different players.</p>
              )}
            </>
          )}

          {((infoA && !infoB) || (!infoA && infoB)) && (
            <p className="text-slate-500 text-sm mb-3">Select a second player to continue.</p>
          )}

          {error && (
            <div className="mb-3 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
          )}

          <button
            onClick={handleMerge}
            disabled={!canMerge || merging}
            className="btn-primary text-sm w-full disabled:opacity-40"
          >
            {merging ? 'Merging…' : 'Confirm Manual Merge'}
          </button>
        </div>
      )}
    </div>
  )
}

function MergePair({ pair, orgId, onMerged, onSkipped, onIgnored }) {
  const [keepId, setKeepId] = useState(() => {
    const a = pair.player_a
    const b = pair.player_b
    if (a.playhq_id && !b.playhq_id) return a.id
    if (b.playhq_id && !a.playhq_id) return b.id
    return a.seasons_count >= b.seasons_count ? a.id : b.id
  })
  const [merging, setMerging] = useState(false)
  const [ignoring, setIgnoring] = useState(false)
  const [error, setError] = useState(null)

  const removePlayer = keepId === pair.player_a.id ? pair.player_b : pair.player_a

  async function handleMerge() {
    setMerging(true)
    setError(null)
    try {
      await api.mergePlayers(keepId, removePlayer.id, orgId)
      onMerged()
    } catch (e) {
      setError(e.message)
      setMerging(false)
    }
  }

  async function handleIgnore() {
    setIgnoring(true)
    try {
      await api.ignorePair(pair.player_a.id, pair.player_b.id, orgId)
      onIgnored()
    } catch {
      setIgnoring(false)
    }
  }

  const busy = merging || ignoring

  return (
    <div className="bg-navy-900 border border-navy-700 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="section-label text-xs">Possible duplicate</span>
        <span className="text-xs text-slate-500 font-mono">"{pair.normalised_name}"</span>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <PlayerCard player={pair.player_a} isSelected={keepId === pair.player_a.id} onSelect={() => setKeepId(pair.player_a.id)} label="Player A" />
        <div className="flex items-center justify-center text-slate-600 font-bold text-lg sm:text-xl shrink-0">vs</div>
        <PlayerCard player={pair.player_b} isSelected={keepId === pair.player_b.id} onSelect={() => setKeepId(pair.player_b.id)} label="Player B" />
      </div>

      <div className="bg-navy-800 rounded-lg px-4 py-3 mb-4 text-sm text-slate-300">
        <span className="text-slate-400">Will keep: </span>
        <span className="text-white font-semibold">{keepId === pair.player_a.id ? pair.player_a.name : pair.player_b.name}</span>
        <span className="text-slate-400"> — merge all records from </span>
        <span className="text-amber-300 font-semibold">{removePlayer.name}</span>
        <span className="text-slate-400"> into it, then delete </span>
        <span className="text-amber-300 font-semibold">{removePlayer.name}</span>.
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
      )}

      <div className="flex gap-2">
        <button onClick={handleMerge} disabled={busy} className="btn-primary text-sm flex-1 disabled:opacity-50">
          {merging ? 'Merging…' : 'Confirm Merge'}
        </button>
        <button onClick={onSkipped} disabled={busy} className="btn-ghost border border-navy-600 text-sm px-4 disabled:opacity-50">
          Skip
        </button>
        <button
          onClick={handleIgnore}
          disabled={busy}
          title="Never suggest this pair again"
          className="btn-ghost border border-navy-700 text-slate-500 hover:text-red-400 hover:border-red-900 text-sm px-4 disabled:opacity-50"
        >
          {ignoring ? '…' : 'Ignore'}
        </button>
      </div>
    </div>
  )
}

function MergeHistory({ orgId, refreshKey }) {
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getMergeHistory(orgId).then(setHistory).catch(() => {})
  }, [orgId, refreshKey])

  async function handleUndo(entry) {
    setUndoing(entry.id)
    setError(null)
    try {
      await api.undoMerge(entry.id, orgId)
      setHistory(h => h.map(e => e.id === entry.id ? { ...e, undone: true } : e))
    } catch (e) {
      setError(e.message)
    } finally {
      setUndoing(null)
    }
  }

  if (history.length === 0) return null

  return (
    <div className="mt-10">
      <h2 className="text-white font-display font-bold text-lg uppercase tracking-wider mb-3">Merge History</h2>
      {error && (
        <div className="mb-3 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">{error}</div>
      )}
      <div className="flex flex-col gap-2">
        {history.map(entry => (
          <div key={entry.id} className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${entry.undone ? 'border-navy-700 bg-navy-900/40 opacity-50' : 'border-navy-700 bg-navy-900'}`}>
            <div className="flex-1 min-w-0">
              <span className="text-white font-medium">{entry.keep_player_name}</span>
              <span className="text-slate-500 mx-2">←</span>
              <span className="text-amber-300">{entry.removed_player_name}</span>
              <span className="text-slate-600 text-xs ml-3">{new Date(entry.merged_at).toLocaleDateString()}</span>
            </div>
            {entry.undone ? (
              <span className="text-xs text-slate-500 shrink-0">Undone</span>
            ) : (
              <button
                onClick={() => handleUndo(entry)}
                disabled={undoing === entry.id}
                className="btn-ghost border border-navy-600 text-xs px-3 py-1 shrink-0 disabled:opacity-50"
              >
                {undoing === entry.id ? 'Undoing…' : 'Undo'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function MergeTools() {
  const { orgId } = useParams()
  const [candidates, setCandidates] = useState(null)
  const [skipped, setSkipped] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mergedCount, setMergedCount] = useState(0)
  const [historyKey, setHistoryKey] = useState(0)

  function load() {
    setLoading(true)
    setError(null)
    api.getMergeCandidates(orgId)
      .then(data => { setCandidates(data); setSkipped(new Set()) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [orgId])

  const visible = candidates?.filter(c => !skipped.has(`${c.player_a.id}:${c.player_b.id}`)) ?? []

  if (loading) return <LoadingSpinner message="Scanning for duplicates…" />

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="accent-bar mb-3" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="section-label mb-1">Admin Tools</p>
            <h1 className="display-heading text-4xl text-white">MERGE DUPLICATES</h1>
          </div>
          <Link to={`/dashboard/${orgId}`} className="btn-ghost border border-navy-600 text-sm">← Dashboard</Link>
        </div>
        <p className="text-slate-400 mt-3 text-sm">
          Players with the same name from different data sources are shown below. Use Manual Merge for name changes (e.g. after marriage).
        </p>
      </div>

      <ManualMerge orgId={orgId} onMerged={() => { setMergedCount(c => c + 1); setHistoryKey(k => k + 1); load() }} />

      {error && (
        <div className="mb-6 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-4 py-3">{error}</div>
      )}

      {mergedCount > 0 && (
        <div className="mb-4 text-sm text-green-400 bg-green-900/20 border border-green-800 rounded px-4 py-3">
          {mergedCount} merge{mergedCount !== 1 ? 's' : ''} completed this session.
        </div>
      )}

      {visible.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <div className="text-5xl mb-4">✓</div>
          <div className="text-lg font-semibold text-white mb-2">No duplicates found</div>
          <p className="text-sm mb-6">
            {candidates?.length > 0
              ? 'All candidates were skipped or ignored. Refresh to see skipped pairs again.'
              : 'No players with matching names were detected in this club.'}
          </p>
          <button onClick={load} className="btn-ghost border border-navy-600 text-sm">Refresh</button>
        </div>
      ) : (
        <>
          <p className="text-slate-500 text-sm mb-5">{visible.length} candidate pair{visible.length !== 1 ? 's' : ''} found.</p>
          <div className="flex flex-col gap-5">
            {visible.map(pair => (
              <MergePair
                key={`${pair.player_a.id}:${pair.player_b.id}`}
                pair={pair}
                orgId={orgId}
                onMerged={() => { setMergedCount(c => c + 1); setHistoryKey(k => k + 1); load() }}
                onSkipped={() => setSkipped(s => new Set([...s, `${pair.player_a.id}:${pair.player_b.id}`]))}
                onIgnored={() => load()}
              />
            ))}
          </div>
        </>
      )}

      <MergeHistory orgId={orgId} refreshKey={historyKey} />
    </div>
  )
}
