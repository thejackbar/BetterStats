import { useParams, Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { PbSpinner } from '../lib/presskit'
import Dropdown from '../components/Dropdown'
import { ProgressBar } from '../components/ProgressBar'

function StatBadge({ label, value }) {
  return (
    <div className="text-center">
      <div className="font-mono text-base font-bold text-pb-text pb-num">{value ?? '—'}</div>
      <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide">{label}</div>
    </div>
  )
}

function PlayerCard({ player, isSelected, onSelect, label }) {
  const hasGrassroots = !!player.playhq_id
  return (
    <button
      onClick={onSelect}
      className={[
        'flex-1 rounded border-2 p-4 text-left transition-all',
        isSelected ? 'bg-pb-accent/10' : 'bg-pb-surface hover:bg-pb-surface2',
      ].join(' ')}
      style={{ borderColor: isSelected ? 'var(--pb-accent)' : 'var(--pb-hairline)' }}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">{label.toUpperCase()}</div>
          <div className="text-pb-text font-semibold text-base leading-tight">{player.name}</div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {hasGrassroots && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded border border-green-700 text-green-400">Grassroots</span>
          )}
          {player.claimed && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded border text-pb-accent" style={{ borderColor: 'var(--pb-accent)' }}>Claimed</span>
          )}
          {!hasGrassroots && !player.claimed && (
            <span className="font-mono text-[10px] px-2 py-0.5 rounded border pb-hairline text-pb-faint">Scorecard only</span>
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
        <div className="mt-3 font-mono text-[10px] tracking-wide2 text-center" style={{ color: 'var(--pb-accent)' }}>✓ Keep this player</div>
      )}
    </button>
  )
}

function PlayerSearch({ players, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

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
          className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 pr-8 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
        />
        {(value || query) && (
          <button onClick={clear} className="absolute right-3 top-1/2 -translate-y-1/2 text-pb-faint hover:text-pb-text text-lg leading-none">×</button>
        )}
      </div>
      <Dropdown
        anchorRef={ref}
        open={open && filtered.length > 0}
        onClose={() => setOpen(false)}
        maxHeight={208}
        className="bg-pb-surface border pb-hairline rounded shadow-xl pb-scroll"
      >
        {filtered.map(p => (
          <button
            key={p.id}
            onMouseDown={() => select(p)}
            className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
          >
            {p.name}
          </button>
        ))}
      </Dropdown>
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
    <div className="mb-8 border pb-hairline rounded overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-4 bg-pb-surface hover:bg-pb-surface2 transition-colors text-left"
      >
        <div>
          <span className="text-pb-text font-semibold">Manual Merge</span>
          <span className="text-pb-faint text-sm ml-3">Merge any two players by name — e.g. name changes after marriage</span>
        </div>
        <span className="text-pb-faint text-lg">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="bg-pb-surface2/20 p-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Player to remove</label>
              <PlayerSearch
                players={players.filter(p => p.id !== selectedB?.id)}
                value={selectedA}
                onChange={handleSelectA}
                placeholder="Search players…"
              />
            </div>
            <div>
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Player to keep</label>
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
                <div className="flex items-center justify-center text-pb-faint font-bold shrink-0">vs</div>
                <PlayerCard player={infoB} isSelected={keepId === infoB.id} onSelect={() => setKeepId(infoB.id)} label="Player B" />
              </div>
              {infoA.id === infoB.id && (
                <p className="text-pb-amber font-mono text-[11px] mb-3">Select two different players.</p>
              )}
            </>
          )}

          {((infoA && !infoB) || (!infoA && infoB)) && (
            <p className="text-pb-faint text-sm mb-3">Select a second player to continue.</p>
          )}

          {error && (
            <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
          )}

          <button
            onClick={handleMerge}
            disabled={!canMerge || merging}
            className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            {merging ? 'Merging…' : 'Confirm Manual Merge'}
          </button>
        </div>
      )}
    </div>
  )
}

function pickKeep(pair) {
  const a = pair.player_a
  const b = pair.player_b
  if (a.playhq_id && !b.playhq_id) return a.id
  if (b.playhq_id && !a.playhq_id) return b.id
  return a.seasons_count >= b.seasons_count ? a.id : b.id
}

function MergePair({ pair, orgId, onMerged, onSkipped, onIgnored, disabled }) {
  const [keepId, setKeepId] = useState(() => pickKeep(pair))
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

  const busy = merging || ignoring || disabled

  return (
    <div className="pb-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">POSSIBLE DUPLICATE</span>
        <span className="font-mono text-[10px] text-pb-faintest">"{pair.normalised_name}"</span>
        {pair.redacted && (
          <span
            className="font-mono text-[10px] px-2 py-0.5 rounded border text-pb-amber"
            style={{ borderColor: 'var(--pb-amber)' }}
            title="A CA-redacted name (********) — this pair is excluded from Bulk Approve"
          >
            Manual review only
          </span>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <PlayerCard player={pair.player_a} isSelected={keepId === pair.player_a.id} onSelect={() => setKeepId(pair.player_a.id)} label="Player A" />
        <div className="flex items-center justify-center text-pb-faint font-bold text-lg sm:text-xl shrink-0">vs</div>
        <PlayerCard player={pair.player_b} isSelected={keepId === pair.player_b.id} onSelect={() => setKeepId(pair.player_b.id)} label="Player B" />
      </div>

      <div className="bg-pb-surface2/30 border pb-hairline rounded px-4 py-3 mb-4 text-sm text-pb-dim">
        <span className="text-pb-faint">Will keep: </span>
        <span className="text-pb-text font-semibold">{keepId === pair.player_a.id ? pair.player_a.name : pair.player_b.name}</span>
        <span className="text-pb-faint"> — merge all records from </span>
        <span className="text-pb-amber font-semibold">{removePlayer.name}</span>
        <span className="text-pb-faint"> into it, then delete </span>
        <span className="text-pb-amber font-semibold">{removePlayer.name}</span>.
      </div>

      {error && (
        <div className="mb-4 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleMerge}
          disabled={busy}
          className="flex-1 py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          {merging ? 'Merging…' : 'Confirm Merge'}
        </button>
        <button
          onClick={onSkipped}
          disabled={busy}
          className="px-4 py-2.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition disabled:opacity-50"
        >
          Skip
        </button>
        <button
          onClick={handleIgnore}
          disabled={busy}
          title="Never suggest this pair again"
          className="px-4 py-2.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-red transition disabled:opacity-50"
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
  const [query, setQuery] = useState('')
  const [showUndone, setShowUndone] = useState(true)

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

  const q = query.trim().toLowerCase()
  const filtered = history.filter(e => {
    if (!showUndone && e.undone) return false
    if (!q) return true
    return (e.keep_player_name || '').toLowerCase().includes(q)
      || (e.removed_player_name || '').toLowerCase().includes(q)
  })
  const activeCount = history.filter(e => !e.undone).length

  function fmtWhen(iso) {
    if (!iso) return ''
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
    })
  }

  return (
    <div className="mt-10">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Merge History</p>
        <span className="font-mono text-[10px] text-pb-faintest">{activeCount} active · {history.length} total</span>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-3">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by player name…"
          className="flex-1 bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
        />
        <button
          onClick={() => setShowUndone(s => !s)}
          className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors shrink-0"
        >
          {showUndone ? 'Hide undone' : 'Show undone'}
        </button>
      </div>

      {error && (
        <div className="mb-3 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-3 py-2">{error}</div>
      )}

      {filtered.length === 0 ? (
        <p className="font-mono text-[11px] text-pb-faintest py-4">No merges match your search.</p>
      ) : (
        <>
          <p className="font-mono text-[10px] text-pb-faintest mb-2">Showing {filtered.length} of {history.length}</p>
          <div className="flex flex-col gap-2 max-h-[32rem] overflow-y-auto pb-scroll pr-1">
            {filtered.map(entry => (
              <div key={entry.id} className={`flex items-center gap-3 rounded border pb-hairline px-4 py-3 text-sm ${entry.undone ? 'opacity-40' : 'bg-pb-surface'}`}>
                <div className="flex-1 min-w-0">
                  <span className="text-pb-text font-medium">{entry.keep_player_name}</span>
                  <span className="text-pb-faint mx-2">←</span>
                  <span className="text-pb-amber">{entry.removed_player_name}</span>
                  <span className="font-mono text-[10px] text-pb-faintest ml-3">{fmtWhen(entry.merged_at)}</span>
                </div>
                {entry.undone ? (
                  <span className="font-mono text-[10px] text-pb-faintest shrink-0">Undone</span>
                ) : (
                  <button
                    onClick={() => handleUndo(entry)}
                    disabled={undoing === entry.id}
                    className="font-mono text-[10px] border pb-hairline rounded px-3 py-1 text-pb-faint hover:text-pb-text transition-colors shrink-0 disabled:opacity-50"
                  >
                    {undoing === entry.id ? 'Undoing…' : 'Undo'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function MergeTools({ embeddedOrgId }) {
  const params = useParams()
  const orgId = embeddedOrgId || params.orgId
  const [candidates, setCandidates] = useState(null)
  const [skipped, setSkipped] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [mergedCount, setMergedCount] = useState(0)
  const [historyKey, setHistoryKey] = useState(0)
  const [bulkMerging, setBulkMerging] = useState(false)
  const [bulkProgress, setBulkProgress] = useState(null) // { done, total }
  const [bulkResult, setBulkResult] = useState(null)

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
  const bulkEligible = visible.filter(c => !c.redacted)
  const bulkRedactedCount = visible.length - bulkEligible.length

  async function handleBulkApprove() {
    if (bulkEligible.length === 0) return
    const redactedNote = bulkRedactedCount > 0
      ? ` ${bulkRedactedCount} redacted-name pair${bulkRedactedCount !== 1 ? 's' : ''} will be left for manual review.`
      : ''
    if (!window.confirm(
      `Bulk merge ${bulkEligible.length} exact-name-match pair${bulkEligible.length !== 1 ? 's' : ''}?${redactedNote}`
    )) return

    setBulkMerging(true)
    setBulkResult(null)
    setError(null)
    const total = bulkEligible.length
    setBulkProgress({ done: 0, total })

    // Merged one pair at a time (not a single batch call) so the bar below
    // reflects real progress — each merge does several sequential DB writes,
    // so a fake "climbing" bar would badly mislead on a big batch.
    let merged = 0
    let failed = 0
    for (const pair of bulkEligible) {
      const keepPlayerId = pickKeep(pair)
      const removePlayerId = keepPlayerId === pair.player_a.id ? pair.player_b.id : pair.player_a.id
      try {
        await api.mergePlayers(keepPlayerId, removePlayerId, orgId)
        merged++
      } catch {
        failed++
      }
      setBulkProgress(p => ({ ...p, done: p.done + 1 }))
    }

    setBulkResult({ merged, skipped: bulkRedactedCount, failed })
    if (merged > 0) {
      setMergedCount(c => c + merged)
      setHistoryKey(k => k + 1)
    }
    setBulkProgress(null)
    setBulkMerging(false)
    load()
  }

  if (loading) return <PbSpinner message="Scanning for duplicates…" />

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="font-display font-bold text-3xl text-pb-text tracking-tight mb-2">Merge Duplicates</h1>
        <p className="text-pb-faint text-sm leading-relaxed">
          Players with the same name from different data sources are shown below. Use Manual Merge for name changes (e.g. after marriage).
        </p>
      </div>

      <ManualMerge orgId={orgId} onMerged={() => { setMergedCount(c => c + 1); setHistoryKey(k => k + 1); load() }} />

      {error && (
        <div className="mb-6 font-mono text-[11px] text-pb-red bg-pb-red/10 border border-pb-red/30 rounded px-4 py-3">{error}</div>
      )}

      {mergedCount > 0 && (
        <div className="mb-4 font-mono text-[11px] border rounded px-4 py-3" style={{ color: 'var(--pb-accent)', borderColor: 'var(--pb-accent)', background: 'var(--pb-accent)10' }}>
          {mergedCount} merge{mergedCount !== 1 ? 's' : ''} completed this session.
        </div>
      )}

      {bulkResult && (
        <div className="mb-4 font-mono text-[11px] border pb-hairline rounded px-4 py-3 text-pb-dim">
          Bulk approve: {bulkResult.merged} merged
          {bulkResult.skipped > 0 ? `, ${bulkResult.skipped} skipped (redacted names)` : ''}
          {bulkResult.failed > 0 ? `, ${bulkResult.failed} failed` : ''}.
        </div>
      )}

      {visible.length > 0 && (
        <div className="mb-5">
          {bulkMerging && bulkProgress ? (
            <ProgressBar
              pct={(bulkProgress.done / bulkProgress.total) * 100}
              label={`Merging ${bulkProgress.done} of ${bulkProgress.total}…`}
            />
          ) : (
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="font-mono text-[11px] text-pb-faint">
                {visible.length} candidate pair{visible.length !== 1 ? 's' : ''} found
                {bulkRedactedCount > 0 ? ` (${bulkRedactedCount} need manual review)` : ''}.
              </p>
              <button
                onClick={handleBulkApprove}
                disabled={bulkEligible.length === 0}
                title="Merges every exact-name-match pair below except redacted (********) names"
                className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold transition disabled:opacity-40 text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                Bulk Approve ({bulkEligible.length})
              </button>
            </div>
          )}
        </div>
      )}

      {visible.length === 0 ? (
        <div className="text-center py-16 text-pb-faint">
          <div className="text-5xl mb-4" style={{ color: 'var(--pb-accent)' }}>✓</div>
          <div className="font-display font-bold text-lg text-pb-text mb-2">No duplicates found</div>
          <p className="text-sm mb-6">
            {candidates?.length > 0
              ? 'All candidates were skipped or ignored. Refresh to see skipped pairs again.'
              : 'No players with matching names were detected in this club.'}
          </p>
          <button
            onClick={load}
            className="px-6 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
          >
            Refresh
          </button>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-5">
            {visible.map(pair => (
              <MergePair
                key={`${pair.player_a.id}:${pair.player_b.id}`}
                pair={pair}
                orgId={orgId}
                onMerged={() => { setMergedCount(c => c + 1); setHistoryKey(k => k + 1); load() }}
                onSkipped={() => setSkipped(s => new Set([...s, `${pair.player_a.id}:${pair.player_b.id}`]))}
                onIgnored={() => load()}
                disabled={bulkMerging}
              />
            ))}
          </div>
        </>
      )}

      <MergeHistory orgId={orgId} refreshKey={historyKey} />
    </div>
  )
}
