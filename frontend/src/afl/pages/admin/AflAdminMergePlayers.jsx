import { useEffect, useMemo, useState } from 'react'
import { aflApi } from '../../aflApi'
import { SectionTitle } from '../../components/bits'

function StatBadge({ label, value }) {
  return (
    <div className="text-center">
      <div className="pb-num text-sm font-semibold">{value}</div>
      <div className="text-[9px] font-mono uppercase text-pb-faint">{label}</div>
    </div>
  )
}

function PlayerCard({ info, selected, onSelect }) {
  if (!info) return <div className="pb-card p-3 text-sm text-pb-faint">—</div>
  return (
    <button
      onClick={onSelect}
      className={`pb-card p-3 text-left w-full transition-colors ${selected ? 'border-[var(--pb-accent)]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-medium truncate">{info.name}</span>
        {info.playhq_id
          ? <span className="text-[9px] font-mono uppercase text-[var(--pb-positive)] shrink-0">PlayHQ</span>
          : <span className="text-[9px] font-mono uppercase text-pb-faint shrink-0">Scorecard only</span>}
      </div>
      <div className="grid grid-cols-4 gap-2">
        <StatBadge label="Games" value={info.total_games} />
        <StatBadge label="Goals" value={info.total_goals} />
        <StatBadge label="Behinds" value={info.total_behinds} />
        <StatBadge label="BOGs" value={info.total_bogs} />
      </div>
      {selected && <div className="mt-2 text-[10px] text-[var(--pb-accent)] font-mono uppercase">Keep this one</div>}
    </button>
  )
}

function PlayerSearch({ players, value, onPick, exclude, placeholder }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    return players.filter(p => p.id !== exclude && (p.display_name || p.name || '').toLowerCase().includes(q)).slice(0, 10)
  }, [players, query, exclude])

  if (value) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="flex-1 truncate">{value.display_name || value.name}</span>
        <button onClick={() => onPick(null)} className="text-pb-faint hover:text-pb-text">×</button>
      </div>
    )
  }
  return (
    <div className="relative">
      <input value={query} onChange={e => setQuery(e.target.value)} placeholder={placeholder}
             className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
      {filtered.length > 0 && (
        <div className="absolute z-10 mt-1 w-full pb-card p-1 max-h-48 overflow-y-auto">
          {filtered.map(p => (
            <button key={p.id} onClick={() => { onPick(p); setQuery('') }}
                    className="block w-full text-left px-2 py-1.5 text-sm rounded hover:bg-pb-surface2">
              {p.display_name || p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function pickKeep(a, b) {
  if (!!a.playhq_id !== !!b.playhq_id) return a.playhq_id ? a.id : b.id
  return (a.seasons_count || 0) >= (b.seasons_count || 0) ? a.id : b.id
}

function ManualMerge({ players, onMerged }) {
  const [open, setOpen] = useState(false)
  const [a, setA] = useState(null)
  const [b, setB] = useState(null)
  const [infoA, setInfoA] = useState(null)
  const [infoB, setInfoB] = useState(null)
  const [keepId, setKeepId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { if (a) aflApi.playerMergeInfo(a.id).then(setInfoA).catch(() => {}); else setInfoA(null) }, [a])
  useEffect(() => { if (b) aflApi.playerMergeInfo(b.id).then(setInfoB).catch(() => {}); else setInfoB(null) }, [b])
  useEffect(() => {
    if (infoA && infoB) setKeepId(pickKeep(infoA, infoB))
  }, [infoA, infoB])

  const canMerge = infoA && infoB && keepId && infoA.id !== infoB.id

  const merge = async () => {
    const removeId = keepId === infoA.id ? infoB.id : infoA.id
    setBusy(true)
    setError(null)
    try {
      await aflApi.mergePlayers(keepId, removeId)
      setA(null); setB(null); setInfoA(null); setInfoB(null); setKeepId(null)
      onMerged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <button onClick={() => setOpen(o => !o)} className="text-sm font-semibold text-pb-text">
        {open ? '▾' : '▸'} Manually pick two players to merge
      </button>
      {open && (
        <div className="space-y-3">
          {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
          <div className="grid grid-cols-2 gap-3">
            <PlayerSearch players={players} value={a} onPick={setA} exclude={b?.id} placeholder="Search player A…" />
            <PlayerSearch players={players} value={b} onPick={setB} exclude={a?.id} placeholder="Search player B…" />
          </div>
          {infoA && infoB && (
            <div className="grid grid-cols-2 gap-3 items-start">
              <PlayerCard info={infoA} selected={keepId === infoA.id} onSelect={() => setKeepId(infoA.id)} />
              <PlayerCard info={infoB} selected={keepId === infoB.id} onSelect={() => setKeepId(infoB.id)} />
            </div>
          )}
          <button disabled={!canMerge || busy} onClick={merge}
                  className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {busy ? 'Merging…' : 'Confirm merge'}
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Split one record into two — the inverse of a merge, for two people an
 * Import Stats upload resolved to a single player because they share a name.
 *
 * Seasons are the unit, and they're pre-sorted newest first, so the usual
 * case (a father's career and a son's, decades apart) is a matter of ticking
 * the run at one end of the list.
 */
function SplitPlayer({ players, onSplit }) {
  const [open, setOpen] = useState(false)
  const [player, setPlayer] = useState(null)
  const [preview, setPreview] = useState(null)
  const [picked, setPicked] = useState(new Set())
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    setPicked(new Set())
    // The result line is only cleared when a NEW player is picked. A finished
    // split clears the picker itself, and clearing it here too would wipe the
    // "split done" message in the same commit that set it.
    if (!player) { setPreview(null); setNewName(''); return }
    setResult(null)
    setNewName(player.display_name || player.name || '')
    aflApi.splitPreview(player.id).then(setPreview).catch(e => setError(e.message))
  }, [player])

  const seasons = preview?.seasons || []
  const toggle = (id) => setPicked(s => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  // Splitting off every season would leave the original record empty and the
  // new one holding the whole career — a rename with extra steps, not a split.
  const canSplit = picked.size > 0 && picked.size < seasons.length && !!newName.trim()

  const split = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await aflApi.splitPlayer(player.id, [...picked], newName.trim())
      setResult(res)
      setPlayer(null)
      onSplit()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <button onClick={() => setOpen(o => !o)} className="text-sm font-semibold text-pb-text">
        {open ? '▾' : '▸'} Split one player into two
      </button>
      {open && (
        <div className="space-y-3">
          <p className="text-sm text-pb-dim max-w-2xl">
            Use this when one record is really two people with the same name: a father and
            son, or two players a generation apart. Pick the seasons that belong to the
            second person and they move onto a new record. To reverse it, merge the two
            back together above.
          </p>
          {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
          {result && (
            <p className="text-sm text-[var(--pb-positive)]">
              Split done — {result.seasons_moved} season{result.seasons_moved === 1 ? '' : 's'} moved
              to a new record for {result.new_player_name}.
            </p>
          )}

          <div className="max-w-sm">
            <PlayerSearch players={players} value={player} onPick={setPlayer}
                          placeholder="Search for the player to split…" />
          </div>

          {player && preview && (
            <>
              {seasons.length === 0 && (
                <p className="text-sm text-pb-faint">
                  This player has no seasons recorded, so there's nothing to split.
                </p>
              )}
              {seasons.length > 0 && (
                <>
                  <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
                    Seasons to move to the new record
                  </p>
                  <div className="pb-card p-2 max-h-72 overflow-y-auto">
                    {seasons.map(s => (
                      <label key={s.season_id}
                             className="flex items-center gap-3 px-2 py-1.5 rounded text-sm hover:bg-pb-surface2 cursor-pointer">
                        <input type="checkbox" checked={picked.has(s.season_id)}
                               onChange={() => toggle(s.season_id)}
                               className="h-4 w-4 accent-[var(--pb-accent)]" />
                        <span className="flex-1 truncate">{s.season_name}</span>
                        <span className="font-mono text-[11px] text-pb-faint whitespace-nowrap">
                          {s.games}g · {s.goals}gl
                        </span>
                      </label>
                    ))}
                  </div>
                  {preview.unattributed_imported_rows > 0 && (
                    <p className="text-[11px] text-pb-faintest">
                      {preview.unattributed_imported_rows} row
                      {preview.unattributed_imported_rows === 1 ? '' : 's'} aren't tied to a season
                      — an import that never resolved one, or a career-only adjustment — so
                      {preview.unattributed_imported_rows === 1 ? ' it stays' : ' they stay'} with
                      the original record.
                    </p>
                  )}
                  <div className="max-w-sm">
                    <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-1">
                      Name for the new record
                    </label>
                    <input value={newName} onChange={e => setNewName(e.target.value)}
                           className="w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm" />
                    <p className="text-[11px] text-pb-faintest mt-1">
                      Usually the same name. Tell them apart with Jnr/Snr if the club does.
                    </p>
                  </div>
                  <button disabled={!canSplit || busy} onClick={split}
                          className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
                    {busy ? 'Splitting…'
                      : picked.size === 0 ? 'Pick the seasons to move'
                      : picked.size === seasons.length ? 'Leave at least one season behind'
                      : `Split off ${picked.size} season${picked.size === 1 ? '' : 's'}`}
                  </button>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function MergePair({ pair, onMerged, onIgnored, onSkip, busyGlobal }) {
  const [keepId, setKeepId] = useState(pickKeep(pair.player_a, pair.player_b))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const merge = async () => {
    const removeId = keepId === pair.player_a.id ? pair.player_b.id : pair.player_a.id
    setBusy(true)
    setError(null)
    try {
      await aflApi.mergePlayers(keepId, removeId)
      onMerged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const ignore = async () => {
    setBusy(true)
    try {
      await aflApi.ignorePair(pair.player_a.id, pair.player_b.id)
      onIgnored()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const keepName = keepId === pair.player_a.id ? pair.player_a.name : pair.player_b.name
  const removeName = keepId === pair.player_a.id ? pair.player_b.name : pair.player_a.name

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <span className="font-mono uppercase text-pb-faint">
          {pair.kind === 'exact' ? 'Possible duplicate' : `Possible spelling mistake — ${Math.round((pair.confidence || 0) * 100)}% similar name`}
        </span>
        {pair.redacted && <span className="px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-faint">Manual review only</span>}
        {pair.kind === 'fuzzy' && <span className="px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-faint">Check it's the same person</span>}
      </div>
      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      <div className="grid grid-cols-2 gap-3">
        <PlayerCard info={pair.player_a} selected={keepId === pair.player_a.id} onSelect={() => setKeepId(pair.player_a.id)} />
        <PlayerCard info={pair.player_b} selected={keepId === pair.player_b.id} onSelect={() => setKeepId(pair.player_b.id)} />
      </div>
      <p className="text-xs text-pb-dim">Will keep <strong className="text-pb-text">{keepName}</strong> — merge all records from <strong className="text-pb-text">{removeName}</strong> into it, then delete it.</p>
      <div className="flex gap-2">
        <button disabled={busy || busyGlobal} onClick={merge} className="px-3 py-1.5 rounded text-sm font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          Confirm merge
        </button>
        <button disabled={busy || busyGlobal} onClick={onSkip} className="px-3 py-1.5 rounded text-sm border border-pb-hairline text-pb-text hover:bg-pb-surface2">
          Skip
        </button>
        <button disabled={busy || busyGlobal} onClick={ignore} className="px-3 py-1.5 rounded text-sm text-pb-faint hover:text-pb-text underline">
          Ignore permanently
        </button>
      </div>
    </div>
  )
}

function MergeHistory({ refreshKey }) {
  const [history, setHistory] = useState(null)
  const [query, setQuery] = useState('')
  const [showUndone, setShowUndone] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { aflApi.playerMergeHistory().then(setHistory).catch(() => setHistory([])) }, [refreshKey])

  if (history === null) return null

  const q = query.trim().toLowerCase()
  const rows = history
    .filter(h => showUndone || !h.undone)
    .filter(h => !q || (h.keep_player_name || '').toLowerCase().includes(q) || (h.removed_player_name || '').toLowerCase().includes(q))

  const undo = async (entry) => {
    if (!window.confirm(`Undo merging ${entry.removed_player_name} into ${entry.keep_player_name}?`)) return
    setBusy(true)
    try {
      await aflApi.undoMergePlayers(entry.id)
      setHistory(hs => hs.map(h => h.id === entry.id ? { ...h, undone: true } : h))
    } catch (err) {
      window.alert(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <SectionTitle>Merge history</SectionTitle>
        <div className="flex items-center gap-3">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search…"
                 className="bg-pb-surface2 border border-pb-hairline rounded px-2 py-1 text-xs" />
          <button onClick={() => setShowUndone(s => !s)} className="text-xs text-pb-dim hover:text-pb-text underline">
            {showUndone ? 'Hide undone' : 'Show undone'}
          </button>
        </div>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(h => (
            <tr key={h.id} className="pb-hairline-b last:border-0">
              <td className="px-2 py-1.5">
                <span className="font-medium">{h.keep_player_name}</span>
                <span className="text-pb-faint"> ← {h.removed_player_name}</span>
              </td>
              <td className="px-2 py-1.5 text-pb-faint text-right">{(h.merged_at || '').replace('T', ' ').slice(0, 16)}</td>
              <td className="px-2 py-1.5 text-right">
                {h.undone
                  ? <span className="text-pb-faint">Undone</span>
                  : <button disabled={busy} onClick={() => undo(h)} className="text-xs text-pb-dim hover:text-pb-text underline">Undo</button>}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={3} className="px-2 py-3 text-pb-faint">No merges yet.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export default function AflAdminMergePlayers() {
  const [candidates, setCandidates] = useState(null)
  const [players, setPlayers] = useState([])
  const [skipped, setSkipped] = useState(new Set())
  const [mergedCount, setMergedCount] = useState(0)
  const [historyKey, setHistoryKey] = useState(0)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkResult, setBulkResult] = useState(null)
  const [bulkProgress, setBulkProgress] = useState(null)
  const [bulkIgnoreBusy, setBulkIgnoreBusy] = useState(false)
  const [error, setError] = useState(null)

  const refreshCandidates = () => aflApi.mergeCandidates().then(setCandidates).catch(() => setCandidates([]))
  useEffect(() => { refreshCandidates(); aflApi.adminListPlayers().then(setPlayers).catch(() => {}) }, [])

  const visible = (candidates || []).filter(c => !skipped.has(`${c.player_a.id}:${c.player_b.id}`))
  const bulkEligible = visible.filter(c => c.kind !== 'fuzzy' && !c.redacted)
  const redactedCount = visible.filter(c => c.redacted).length

  const onMerged = () => {
    setMergedCount(n => n + 1)
    setHistoryKey(k => k + 1)
    refreshCandidates()
  }
  const onIgnored = () => refreshCandidates()
  // A split leaves two records with the same name, which is an exact-name
  // merge candidate — so the pair list has to be re-read, or the screen would
  // offer to merge back a split it can't see yet.
  const onSplitDone = () => {
    refreshCandidates()
    aflApi.adminListPlayers().then(setPlayers).catch(() => {})
  }
  const onSkip = (pair) => setSkipped(s => new Set(s).add(`${pair.player_a.id}:${pair.player_b.id}`))

  const bulkApprove = async () => {
    if (!window.confirm(`Merge ${bulkEligible.length} exact-duplicate pair(s) automatically? This can't be undone in bulk (each merge can still be undone individually).`)) return
    setBulkBusy(true)
    setError(null)
    setBulkResult(null)
    let merged = 0, failed = 0
    for (let i = 0; i < bulkEligible.length; i++) {
      setBulkProgress({ done: i, total: bulkEligible.length })
      const pair = bulkEligible[i]
      const keepId = pickKeep(pair.player_a, pair.player_b)
      const removeId = keepId === pair.player_a.id ? pair.player_b.id : pair.player_a.id
      try {
        await aflApi.mergePlayers(keepId, removeId)
        merged++
      } catch {
        failed++
      }
    }
    setBulkProgress(null)
    setBulkResult({ merged, failed })
    setHistoryKey(k => k + 1)
    refreshCandidates()
    setBulkBusy(false)
  }

  const bulkIgnoreRedacted = async () => {
    if (!window.confirm(`Ignore all ${redactedCount} pair(s) involving a private/redacted player ("********")? These can't be told apart to confirm as real duplicates, so they'll drop off this list.`)) return
    setBulkIgnoreBusy(true)
    setError(null)
    try {
      await aflApi.bulkIgnoreRedacted()
      refreshCandidates()
    } catch (e) {
      setError(e.message)
    } finally {
      setBulkIgnoreBusy(false)
    }
  }

  if (candidates === null) return <p className="text-sm text-pb-faint">Loading…</p>

  return (
    <div className="space-y-6">
      <SectionTitle>Merge Players</SectionTitle>
      <p className="text-sm text-pb-dim max-w-2xl">
        Combine duplicate player records into one — everything the removed
        player was credited with (games, goals, behinds, best-on-grounds,
        imported seasons and honours) moves onto the kept player. If the
        opposite has happened and one record is really two people, split it
        below.
      </p>

      {error && <p className="pb-card p-3 text-sm text-[var(--pb-negative)]">{error}</p>}
      {mergedCount > 0 && <p className="pb-card p-3 text-sm text-[var(--pb-positive)]">{mergedCount} merge{mergedCount === 1 ? '' : 's'} done this session.</p>}
      {bulkResult && (
        <p className="pb-card p-3 text-sm text-[var(--pb-positive)]">
          Bulk approve: {bulkResult.merged} merged{bulkResult.failed ? `, ${bulkResult.failed} failed` : ''}.
        </p>
      )}

      <ManualMerge players={players} onMerged={onMerged} />
      <SplitPlayer players={players} onSplit={onSplitDone} />

      {bulkEligible.length > 0 && (
        <div className="pb-card p-4 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-semibold text-sm">{bulkEligible.length} exact-name duplicate{bulkEligible.length === 1 ? '' : 's'} found</div>
            <div className="text-xs text-pb-faint">Safe to bulk-merge — fuzzy/spelling matches always need manual confirmation.</div>
          </div>
          <button disabled={bulkBusy} onClick={bulkApprove} className="px-4 py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
            {bulkBusy ? (bulkProgress ? `Merging ${bulkProgress.done}/${bulkProgress.total}…` : 'Merging…') : `Bulk approve ${bulkEligible.length}`}
          </button>
        </div>
      )}

      {redactedCount > 0 && (
        <div className="pb-card p-4 flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-semibold text-sm">{redactedCount} pair{redactedCount === 1 ? '' : 's'} involving a private/redacted player</div>
            <div className="text-xs text-pb-faint">CA hides a junior's name as "********" — two redacted players can never be confirmed as the same person, so there's nothing to review here.</div>
          </div>
          <button disabled={bulkIgnoreBusy} onClick={bulkIgnoreRedacted} className="px-4 py-2 rounded font-semibold border border-pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-50">
            {bulkIgnoreBusy ? 'Ignoring…' : `Ignore all ${redactedCount}`}
          </button>
        </div>
      )}

      <div className="space-y-3">
        {visible.map(pair => (
          <MergePair
            key={`${pair.player_a.id}:${pair.player_b.id}`}
            pair={pair}
            busyGlobal={bulkBusy}
            onMerged={onMerged}
            onIgnored={onIgnored}
            onSkip={() => onSkip(pair)}
          />
        ))}
        {visible.length === 0 && (
          <p className="pb-card p-4 text-pb-faint text-sm">No possible duplicates found.</p>
        )}
      </div>

      <MergeHistory refreshKey={historyKey} />
    </div>
  )
}
