import { useParams, Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
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
        isSelected
          ? 'border-accent bg-accent/10'
          : 'border-navy-600 bg-navy-800 hover:border-navy-400',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">{label}</div>
          <div className="text-white font-semibold text-lg leading-tight">{player.name}</div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {hasGrassroots && (
            <span className="text-xs bg-green-900/60 text-green-300 border border-green-700 rounded px-2 py-0.5">
              Grassroots
            </span>
          )}
          {player.claimed && (
            <span className="text-xs bg-accent/20 text-accent border border-accent/40 rounded px-2 py-0.5">
              Claimed
            </span>
          )}
          {!hasGrassroots && !player.claimed && (
            <span className="text-xs bg-navy-700 text-slate-400 border border-navy-600 rounded px-2 py-0.5">
              Scorecard only
            </span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2">
        <StatBadge label="Seasons" value={player.seasons_count} />
        <StatBadge label="Runs" value={player.total_runs} />
        <StatBadge label="Wkts" value={player.total_wickets} />
        <StatBadge label="Game innings" value={player.game_level_innings} />
      </div>
      {isSelected && (
        <div className="mt-3 text-xs text-accent font-semibold text-center">
          ✓ Keep this player
        </div>
      )}
    </button>
  )
}

function MergePair({ pair, orgId, onMerged, onSkipped }) {
  const [keepId, setKeepId] = useState(() => {
    // Default: prefer the player with Grassroots data, then by seasons count
    const a = pair.player_a
    const b = pair.player_b
    if (a.playhq_id && !b.playhq_id) return a.id
    if (b.playhq_id && !a.playhq_id) return b.id
    return a.seasons_count >= b.seasons_count ? a.id : b.id
  })
  const [merging, setMerging] = useState(false)
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

  return (
    <div className="bg-navy-900 border border-navy-700 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="section-label text-xs">Possible duplicate</span>
        <span className="text-xs text-slate-500 font-mono">"{pair.normalised_name}"</span>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <PlayerCard
          player={pair.player_a}
          isSelected={keepId === pair.player_a.id}
          onSelect={() => setKeepId(pair.player_a.id)}
          label="Player A"
        />
        <div className="flex items-center justify-center text-slate-600 font-bold text-lg sm:text-xl shrink-0">
          vs
        </div>
        <PlayerCard
          player={pair.player_b}
          isSelected={keepId === pair.player_b.id}
          onSelect={() => setKeepId(pair.player_b.id)}
          label="Player B"
        />
      </div>

      <div className="bg-navy-800 rounded-lg px-4 py-3 mb-4 text-sm text-slate-300">
        <span className="text-slate-400">Will keep: </span>
        <span className="text-white font-semibold">
          {keepId === pair.player_a.id ? pair.player_a.name : pair.player_b.name}
        </span>
        <span className="text-slate-400"> — merge all records from </span>
        <span className="text-amber-300 font-semibold">{removePlayer.name}</span>
        <span className="text-slate-400"> into it, then delete </span>
        <span className="text-amber-300 font-semibold">{removePlayer.name}</span>.
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleMerge}
          disabled={merging}
          className="btn-primary text-sm flex-1 disabled:opacity-50"
        >
          {merging ? 'Merging…' : 'Confirm Merge'}
        </button>
        <button
          onClick={onSkipped}
          disabled={merging}
          className="btn-ghost border border-navy-600 text-sm px-5 disabled:opacity-50"
        >
          Skip
        </button>
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
          <Link to={`/dashboard/${orgId}`} className="btn-ghost border border-navy-600 text-sm">
            ← Dashboard
          </Link>
        </div>
        <p className="text-slate-400 mt-3 text-sm">
          Players with the same name from different data sources (e.g. Grassroots vs scorecard import) are shown below.
          Select which record to keep, then confirm each merge. Skipped pairs won't be shown again until you refresh.
        </p>
      </div>

      {error && (
        <div className="mb-6 text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-4 py-3">
          {error}
        </div>
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
              ? 'All candidates were skipped. Refresh to see them again.'
              : 'No players with matching names were detected in this club.'}
          </p>
          <button onClick={load} className="btn-ghost border border-navy-600 text-sm">
            Refresh
          </button>
        </div>
      ) : (
        <>
          <p className="text-slate-500 text-sm mb-5">
            {visible.length} candidate pair{visible.length !== 1 ? 's' : ''} found.
          </p>
          <div className="flex flex-col gap-5">
            {visible.map(pair => (
              <MergePair
                key={`${pair.player_a.id}:${pair.player_b.id}`}
                pair={pair}
                orgId={orgId}
                onMerged={() => {
                  setMergedCount(c => c + 1)
                  load()
                }}
                onSkipped={() => {
                  setSkipped(s => new Set([...s, `${pair.player_a.id}:${pair.player_b.id}`]))
                }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
