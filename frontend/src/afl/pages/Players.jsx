import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import clsx from 'clsx'
import LoadingSpinner from '../../components/LoadingSpinner'
import { aflApi } from '../aflApi'
import { PlayerCell, displayName } from '../components/bits'

const COLS = [
  { key: 'games', label: 'GP' },
  { key: 'goals', label: 'Goals' },
  { key: 'behinds', label: 'Behinds' },
  { key: 'bogs', label: 'BOG' },
  { key: 'seasons', label: 'Seasons' },
]

export default function Players() {
  const { club } = useOutletContext()
  const [players, setPlayers] = useState(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState({ key: 'games', dir: 'desc' })
  const base = `/${club.slug}`

  useEffect(() => {
    aflApi.listPlayers(club.id).then(d => setPlayers(d.players))
  }, [club.id])

  const rows = useMemo(() => {
    if (!players) return []
    const q = search.trim().toLowerCase()
    let out = q ? players.filter(p => displayName(p).toLowerCase().includes(q)) : [...players]
    out.sort((a, b) => {
      const av = a[sort.key] ?? 0, bv = b[sort.key] ?? 0
      return sort.dir === 'desc' ? bv - av : av - bv
    })
    return out
  }, [players, search, sort])

  if (players === null) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const header = (col) => (
    <th
      key={col.key}
      onClick={() => setSort(s => ({ key: col.key, dir: s.key === col.key && s.dir === 'desc' ? 'asc' : 'desc' }))}
      className={clsx(
        'px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide cursor-pointer select-none',
        sort.key === col.key ? 'text-[var(--pb-accent)]' : 'text-pb-faint',
      )}
    >
      {col.label}{sort.key === col.key ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">Players</h1>
        <span className="text-sm text-pb-faint">{rows.length} of {players.length}</span>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search players…"
          className="ml-auto bg-pb-surface2 border border-pb-hairline rounded px-3 py-1.5 text-sm w-56"
        />
      </div>
      <div className="pb-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="pb-hairline-b">
            <tr>
              <th className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-pb-faint">Player</th>
              <th className="px-3 py-2 text-right font-mono text-[10px] uppercase tracking-wide text-pb-faint hidden sm:table-cell">Years</th>
              {COLS.map(header)}
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.player_id} className="pb-hairline-b last:border-0 hover:bg-pb-surface2/50">
                <td className="px-3 py-2">
                  <PlayerCell id={p.player_id} name={displayName(p)} base={base} photoUrl={p.photo_url} />
                </td>
                <td className="px-3 py-2 text-right pb-num text-pb-faint hidden sm:table-cell">
                  {p.first_year ? (p.first_year === p.last_year ? p.first_year : `${p.first_year}–${p.last_year}`) : '—'}
                </td>
                {COLS.map(c => (
                  <td key={c.key} className="px-3 py-2 text-right pb-num">{p[c.key] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
