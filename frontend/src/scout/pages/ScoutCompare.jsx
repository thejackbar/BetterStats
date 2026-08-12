import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

// Mirrors PlayerComparison.jsx's getRowHighlights — a fraction of that page's
// complexity since BetterScout has no per-season filtering or batting/bowling
// tabs, just the one cached totals snapshot per player. Not imported: that
// function isn't exported, and this version doesn't need the filter-mode logic.
function rowHighlights(values, higher) {
  const nums = values.map((v) => {
    const n = parseFloat(v)
    return isNaN(n) ? null : n
  })
  const valid = nums.filter((n) => n !== null)
  if (valid.length < 2) return values.map(() => null)

  const best = higher ? Math.max(...valid) : Math.min(...valid)
  const worst = higher ? Math.min(...valid) : Math.max(...valid)
  if (best === worst) return values.map(() => null)

  const bestCount = valid.filter((n) => n === best).length
  const worstCount = valid.filter((n) => n === worst).length

  return nums.map((n) => {
    if (n === null) return null
    if (n === best && bestCount === 1) return 'best'
    if (n === worst && worstCount === 1) return 'worst'
    return null
  })
}

const TOTALS_ROWS = [
  ['matches', 'Matches', true],
  ['runs', 'Runs', true],
  ['average', 'Average', true],
  ['strike_rate', 'Strike rate', true],
  ['wickets', 'Wickets', true],
  ['economy', 'Economy', false],
  ['bowling_average', 'Bowling average', false],
  ['best', 'Best figures', true],
  ['catches', 'Catches', true],
]

function highlightStyle(h) {
  if (h === 'best') return { backgroundColor: 'rgba(34,197,94,0.14)', color: '#86efac' }
  if (h === 'worst') return { backgroundColor: 'rgba(239,68,68,0.14)', color: '#fca5a5' }
  return undefined
}

export default function ScoutCompare() {
  const [params, setParams] = useSearchParams()
  const [players, setPlayers] = useState(undefined) // undefined = loading
  const [error, setError] = useState(null)
  const selectedIds = useMemo(() => (params.get('players') || '').split(',').filter(Boolean), [params])

  useEffect(() => {
    scoutApi.listPlayers().then(setPlayers).catch((err) => setError(err.message))
  }, [])

  const toggle = (id) => {
    const set = new Set(selectedIds)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    const next = [...set]
    setParams(next.length ? { players: next.join(',') } : {})
  }

  const selected = useMemo(
    () => selectedIds.map((id) => players?.find((p) => p.id === id)).filter(Boolean),
    [selectedIds, players],
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Compare players</h1>
        <p className="text-sm text-pb-dim">Pick two or more tracked players to see them side by side.</p>
      </div>

      {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
      {players === undefined && !error && <p className="text-sm text-pb-dim">Loading…</p>}

      {players && players.length === 0 && (
        <p className="text-sm text-pb-dim">
          Nobody added yet — <Link to="/betterscout/app/discover" className="underline">discover a player</Link> to get started.
        </p>
      )}

      {players && players.length > 0 && (
        <div className="pb-card p-4">
          <div className="flex flex-wrap gap-2">
            {players.map((p) => {
              const active = selectedIds.includes(p.id)
              return (
                <button
                  key={p.id} onClick={() => toggle(p.id)}
                  className={`text-sm px-3 py-1.5 rounded-full border ${
                    active
                      ? 'border-[var(--pb-accent)] bg-[var(--pb-accent)] text-black font-medium'
                      : 'border-pb-hairline hover:bg-pb-surface2'
                  }`}
                >
                  {p.name}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {selected.length === 1 && (
        <p className="text-sm text-pb-dim">Pick at least one more player to compare.</p>
      )}

      {selected.length >= 2 && <ComparisonTables players={selected} />}
    </div>
  )
}

function ComparisonTables({ players }) {
  const withStats = players.filter((p) => p.stats?.totals)
  const noStats = players.filter((p) => !p.stats?.totals)

  const allYears = useMemo(() => {
    const years = new Set()
    for (const p of players) {
      for (const s of p.stats?.seasons || []) years.add(s.year)
    }
    return [...years].sort((a, b) => String(b).localeCompare(String(a)))
  }, [players])

  return (
    <div className="space-y-6">
      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-pb-dim text-xs uppercase font-mono">
            <tr className="border-b border-pb-hairline">
              <th className="text-left px-3 py-2">Career totals</th>
              {players.map((p) => (
                <th key={p.id} className="text-right px-3 py-2">
                  <Link to={`/betterscout/app/players/${p.id}`} className="hover:underline">{p.name}</Link>
                  {p.source === 'manual' && <div className="normal-case font-normal text-[10px]">Manual</div>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TOTALS_ROWS.map(([key, label, higher]) => {
              const values = players.map((p) => p.stats?.totals?.[key])
              const highlights = rowHighlights(values, higher)
              return (
                <tr key={key} className="border-b border-pb-hairline last:border-0">
                  <td className="px-3 py-2 text-pb-dim">{label}</td>
                  {values.map((v, i) => (
                    <td key={players[i].id} className="px-3 py-2 text-right rounded" style={highlightStyle(highlights[i])}>
                      {v ?? '—'}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
        {noStats.length > 0 && (
          <p className="px-3 py-2 text-xs text-pb-dim border-t border-pb-hairline">
            {noStats.map((p) => p.name).join(', ')} — no stats available (manually added).
          </p>
        )}
      </div>

      {withStats.length > 0 && allYears.length > 0 && (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-pb-dim text-xs uppercase font-mono">
              <tr className="border-b border-pb-hairline">
                <th className="text-left px-3 py-2">Season</th>
                {players.map((p) => (
                  <th key={p.id} colSpan={3} className="text-center px-3 py-2 border-l border-pb-hairline">{p.name}</th>
                ))}
              </tr>
              <tr className="border-b border-pb-hairline">
                <th></th>
                {players.map((p) => (
                  <Fragment key={p.id}>
                    <th className="text-right px-2 py-1 border-l border-pb-hairline">Runs</th>
                    <th className="text-right px-2 py-1">Avg</th>
                    <th className="text-right px-2 py-1">Wkts</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {allYears.map((year) => (
                <tr key={year} className="border-b border-pb-hairline last:border-0">
                  <td className="px-3 py-2">{year}</td>
                  {players.map((p) => {
                    const s = (p.stats?.seasons || []).find((s) => s.year === year)
                    return (
                      <Fragment key={p.id}>
                        <td className="px-2 py-2 text-right border-l border-pb-hairline">{s ? s.runs : '—'}</td>
                        <td className="px-2 py-2 text-right">{s ? (s.average ?? '—') : '—'}</td>
                        <td className="px-2 py-2 text-right">{s ? s.wickets : '—'}</td>
                      </Fragment>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
