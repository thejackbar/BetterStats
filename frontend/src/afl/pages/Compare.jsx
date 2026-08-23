import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { SectionTitle, displayName } from '../components/bits'

const ROWS = [
  { key: 'games', label: 'Games' },
  { key: 'goals', label: 'Goals' },
  { key: 'bogs', label: 'Best on Ground' },
  { key: 'seasons', label: 'Seasons' },
]

export default function Compare() {
  const { club } = useOutletContext()
  const [players, setPlayers] = useState(null)
  const [picked, setPicked] = useState([])
  const [search, setSearch] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    aflApi.listPlayers(club.id).then(d => setPlayers(d.players))
  }, [club.id])

  useEffect(() => {
    if (picked.length < 2) { setResult(null); return }
    setLoading(true)
    aflApi.comparePlayers(club.id, picked.map(p => p.player_id))
      .then(setResult)
      .finally(() => setLoading(false))
  }, [club.id, picked])

  const suggestions = useMemo(() => {
    if (!players || !search.trim()) return []
    const q = search.trim().toLowerCase()
    return players
      .filter(p => displayName(p).toLowerCase().includes(q))
      .filter(p => !picked.some(x => x.player_id === p.player_id))
      .slice(0, 8)
  }, [players, search, picked])

  if (players === null) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const best = (key) => Math.max(...(result?.players || []).map(p => p[key] ?? 0))

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Compare players</h1>

      <div className="pb-card p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {picked.map(p => (
            <span key={p.player_id} className="flex items-center gap-1.5 bg-pb-surface2 rounded-full pl-3 pr-1.5 py-1 text-sm">
              {displayName(p)}
              <button onClick={() => setPicked(x => x.filter(y => y.player_id !== p.player_id))}
                      className="h-5 w-5 rounded-full bg-pb-surface text-pb-faint hover:text-pb-text text-xs">✕</button>
            </span>
          ))}
          {picked.length < 4 && (
            <div className="relative">
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={picked.length === 0 ? 'Add a player…' : 'Add another…'}
                className="bg-pb-surface2 border border-pb-hairline rounded-full px-3 py-1 text-sm w-48"
              />
              {suggestions.length > 0 && (
                <div className="absolute z-10 top-full mt-1 left-0 w-64 pb-card shadow-xl">
                  {suggestions.map(p => (
                    <button key={p.player_id}
                            onClick={() => { setPicked(x => [...x, p]); setSearch('') }}
                            className="block w-full text-left px-3 py-2 text-sm hover:bg-pb-surface2">
                      {displayName(p)} <span className="text-pb-faintest text-xs">· {p.games} GP</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        {picked.length < 2 && <p className="text-sm text-pb-faint">Pick two to four players to compare careers.</p>}
      </div>

      {loading && <div className="pt-8 flex justify-center"><LoadingSpinner /></div>}

      {result && !loading && (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="pb-hairline-b">
              <tr>
                <th className="px-3 py-2 text-left font-mono text-[10px] uppercase text-pb-faint">Career</th>
                {result.players.map(p => (
                  <th key={p.player_id} className="px-3 py-2 text-right font-semibold text-pb-text">{displayName(p)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map(row => (
                <tr key={row.key} className="pb-hairline-b last:border-0">
                  <td className="px-3 py-2 text-pb-dim">{row.label}</td>
                  {result.players.map(p => (
                    <td key={p.player_id} className={clsx(
                      'px-3 py-2 text-right pb-num',
                      (p[row.key] ?? 0) === best(row.key) && best(row.key) > 0 && 'font-bold text-[var(--pb-accent)]',
                    )}>
                      {p[row.key] ?? 0}
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <td className="px-3 py-2 text-pb-dim">Span</td>
                {result.players.map(p => (
                  <td key={p.player_id} className="px-3 py-2 text-right pb-num text-pb-faint">
                    {p.first_year ? (p.first_year === p.last_year ? p.first_year : `${p.first_year}–${p.last_year}`) : '—'}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {result && !loading && (
        <div className="grid md:grid-cols-2 gap-4">
          {result.players.map(p => (
            <div key={p.player_id} className="pb-card p-4">
              <SectionTitle>{displayName(p)}, season by season</SectionTitle>
              <table className="w-full text-xs">
                <thead>
                  <tr>
                    {['Season', 'GP', 'G', 'BOG'].map((h, i) => (
                      <th key={h} className={`py-1 font-mono text-[9px] uppercase text-pb-faint ${i ? 'text-right' : 'text-left'}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(p.season_rows || []).map(s => (
                    <tr key={s.season_id} className="pb-hairline-b last:border-0">
                      <td className="py-1">{s.season_name}</td>
                      <td className="py-1 text-right pb-num">{s.games}</td>
                      <td className="py-1 text-right pb-num">{s.goals}</td>
                      <td className="py-1 text-right pb-num">{s.bogs}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
